"""
메시지 전송 API 모듈 (chat.py)

명세서 B1(메시지 전송 API), B3(Gemini 연동), B4(맥락 구성), B6(입력 검증), B7(동시성 제어), 4장 오류 규격을 처리합니다.
- 엔드포인트: POST /api/chat
"""

import json
import uuid
import asyncio
import logging
from typing import Literal, List, Optional
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import aiosqlite

from app.db.database import get_db, get_db_path
from app.services.session_manager import session_manager
from app.services.chat_service import (
    validate_chat_input,
    prepare_user_message,
    load_system_instruction,
    build_context_contents,
    call_gemini,
    call_gemini_stream,
    save_ai_message,
    ChatServiceError
)

logger = logging.getLogger("chacha-backend.api.chat")
router = APIRouter()


class ChatRequest(BaseModel):
    """
    메시지 전송 요청 스키마 (명세서 B1)
    """
    sessionId: str = Field(description="클라이언트 세션 ID (UUID)")
    messageId: str = Field(description="클라이언트가 생성한 사용자 메시지 ID (UUID)")
    message: str = Field(description="사용자 입력 텍스트 본문")


class MessagePayload(BaseModel):
    """
    AI 응답 메시지 세부 스키마 (명세서 B1 & camelCase 필드명)
    """
    id: str
    role: Literal["assistant"] = "assistant"
    content: str
    status: Literal["done"] = "done"
    replyTo: str
    createdAt: str


class ChatResponse(BaseModel):
    """
    메시지 전송 성공 응답 스키마 (HTTP 200)
    """
    message: MessagePayload


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="메시지 전송 및 AI 답변 수신 (단건 동기 방식)",
    description="사용자 메시지를 받아 Gemini API로 답변을 생성하고 두 메시지를 저장 후 반환합니다 (명세서 B1)."
)
async def post_chat(
    req: ChatRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    메시지 전송 핸들러 (명세서 B1)
    
    [완료 조건 검증]
    1. 정상 요청에 200 과 AI 메시지를 돌려주고 두 메시지가 저장된다.
    2. 같은 messageId 로 다시 보내도 사용자 메시지가 중복 저장되지 않는다.
    3. 같은 세션에서 동시에 보내면 409 SESSION_BUSY.
    4. 최근 CONTEXT_TURNS 턴만 맥락에 들어간다.
    5. Gemini 429·5xx·시간 초과·안전 차단이 4장의 코드로 바뀐다.
    6. 실패하면 AI 메시지는 저장되지 않는다.
    """
    session_id = req.sessionId
    message_id = req.messageId
    raw_message = req.message

    # --------------------------------------------------------------------------
    # 1. 입력 유효성 검증 (명세서 B6)
    # --------------------------------------------------------------------------
    try:
        clean_message = validate_chat_input(
            session_id=session_id,
            message_id=message_id,
            message=raw_message
        )
    except ChatServiceError as err:
        return JSONResponse(
            status_code=err.http_status,
            content={"error": {"code": err.code, "message": err.message}}
        )

    # --------------------------------------------------------------------------
    # 2. 세션 동시성 제어 (명세서 B1 & B7)
    # [완료 조건 3] 같은 세션에서 동시에 보내면 409 SESSION_BUSY
    # --------------------------------------------------------------------------
    acquired = await session_manager.acquire(session_id)
    if not acquired:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "SESSION_BUSY",
                    "message": "이전 답변이 아직 끝나지 않았어요."
                }
            }
        )

    try:
        # ----------------------------------------------------------------------
        # 3. 사용자 메시지 저장 및 재시도 확인 (명세서 B1)
        # [완료 조건 2] 같은 messageId 재시도 시 중복 저장 방지
        # ----------------------------------------------------------------------
        user_message_record = await prepare_user_message(
            db=db,
            session_id=session_id,
            message_id=message_id,
            message_content=clean_message
        )

        # ----------------------------------------------------------------------
        # 4. 시스템 프롬프트 및 맥락 구성 (명세서 2장, B4)
        # [완료 조건 4] 최근 CONTEXT_TURNS 턴만 맥락에 포함 (답 없는 실패 요청 제외)
        # ----------------------------------------------------------------------
        system_instruction = load_system_instruction()
        contents = await build_context_contents(
            db=db,
            session_id=session_id,
            current_message_id=message_id,
            current_message=user_message_record["content"]  # 재시도 시 DB에 처음 저장된 내용 유지
        )

        # ----------------------------------------------------------------------
        # 5. Gemini API 호출 (명세서 B3 & 4장)
        # [완료 조건 5] 429·5xx·타임아웃·안전 차단을 명세서 4장 코드로 변환
        # ----------------------------------------------------------------------
        ai_text = await call_gemini(
            contents=contents,
            system_instruction=system_instruction
        )

        # ----------------------------------------------------------------------
        # 6. AI 메시지 DB 저장 (성공 시에만 저장)
        # [완료 조건 1 & 6] 정상 시 두 메시지 모두 저장, 실패 시 AI 메시지는 미저장
        # ----------------------------------------------------------------------
        ai_message = await save_ai_message(
            db=db,
            session_id=session_id,
            reply_to_message_id=message_id,
            content=ai_text
        )

        return ChatResponse(
            message=MessagePayload(
                id=ai_message["id"],
                role="assistant",
                content=ai_message["content"],
                status="done",
                replyTo=ai_message["replyTo"],
                createdAt=ai_message["createdAt"]
            )
        )

    except ChatServiceError as err:
        # 실패 시 AI 메시지는 저장되지 않고 오류 응답 반환 (명세서 4장)
        return JSONResponse(
            status_code=err.http_status,
            content={"error": {"code": err.code, "message": err.message}}
        )
    except Exception as exc:
        logger.error(f"예기치 못한 서버 오류: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "답변을 받지 못했어요."
                }
            }
        )
    finally:
        # 응답 처리 완료 후 세션 락 해제
        await session_manager.release(session_id)


async def _save_ai_message_safely(
    session_id: str,
    reply_to_message_id: str,
    content: str,
    message_id: str,
    status: str
) -> None:
    """
    스트리밍 완료(done) 또는 클라이언트 연결 중단(stopped) 시 AI 메시지를 안전하게 DB에 저장합니다.
    """
    async with aiosqlite.connect(get_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        await save_ai_message(
            db=conn,
            session_id=session_id,
            reply_to_message_id=reply_to_message_id,
            content=content,
            message_id=message_id,
            status=status
        )


@router.post(
    "/chat/stream",
    summary="메시지 전송 및 AI 답변 스트리밍 수신 (SSE)",
    description="사용자 메시지를 받아 Gemini API 스트리밍 답변을 SSE(Server-Sent Events)로 전송합니다 (명세서 6.1 S1~S6)."
)
async def post_chat_stream(
    req: ChatRequest,
    request: Request,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    스트리밍 메시지 전송 핸들러 (명세서 6.1 S1~S6)
    
    [완료 조건 검증]
    1. start -> delta ... -> done 순서로 이벤트가 온다 (curl -N으로 확인 가능).
    2. 클라이언트 연결이 끊기면 Gemini 스트림도 멈추고, 받은 데까지 stopped로 저장된다 (받은 게 없으면 미저장).
    3. 도중 오류는 error 이벤트로 오고, AI 메시지는 저장되지 않는다.
    4. 스트림을 열기 전 오류(입력 검증, 동시성, 이미 답변 등)는 기존과 같은 JSON 오류 응답이다.
    """
    session_id = req.sessionId
    message_id = req.messageId
    raw_message = req.message

    # --------------------------------------------------------------------------
    # 1. 입력 유효성 검증 (명세서 B6)
    # [완료 조건 4] 스트림을 열기 전 오류는 JSON 응답
    # --------------------------------------------------------------------------
    try:
        clean_message = validate_chat_input(
            session_id=session_id,
            message_id=message_id,
            message=raw_message
        )
    except ChatServiceError as err:
        return JSONResponse(
            status_code=err.http_status,
            content={"error": {"code": err.code, "message": err.message}}
        )

    # --------------------------------------------------------------------------
    # 2. 세션 동시성 제어 (명세서 B1 & B7)
    # --------------------------------------------------------------------------
    acquired = await session_manager.acquire(session_id)
    if not acquired:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "SESSION_BUSY",
                    "message": "이전 답변이 아직 끝나지 않았어요."
                }
            }
        )

    try:
        # ----------------------------------------------------------------------
        # 3. 사용자 메시지 저장 및 재시도 확인 (명세서 B1)
        # ----------------------------------------------------------------------
        user_message_record = await prepare_user_message(
            db=db,
            session_id=session_id,
            message_id=message_id,
            message_content=clean_message
        )

        # ----------------------------------------------------------------------
        # 4. 시스템 프롬프트 및 맥락 구성 (명세서 B4)
        # ----------------------------------------------------------------------
        system_instruction = load_system_instruction()
        contents = await build_context_contents(
            db=db,
            session_id=session_id,
            current_message_id=message_id,
            current_message=user_message_record["content"]
        )

        # ----------------------------------------------------------------------
        # 5. Gemini 스트림 호출 준비 (명세서 S1)
        # ----------------------------------------------------------------------
        stream_chunks = await call_gemini_stream(
            contents=contents,
            system_instruction=system_instruction
        )

    except ChatServiceError as err:
        # 스트림을 열기 전 발생한 오류 -> 세션 락 해제 후 JSON 응답 반환
        await session_manager.release(session_id)
        return JSONResponse(
            status_code=err.http_status,
            content={"error": {"code": err.code, "message": err.message}}
        )
    except Exception as exc:
        await session_manager.release(session_id)
        logger.error(f"스트림 준비 중 예기치 못한 오류: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "답변을 받지 못했어요."
                }
            }
        )

    # --------------------------------------------------------------------------
    # 6. SSE 스트림 이벤트 생성기 (명세서 S2~S5)
    # --------------------------------------------------------------------------
    async def sse_event_generator():
        ai_message_id = str(uuid.uuid4())
        accumulated_chunks: List[str] = []
        is_completed = False
        finish_reason = "STOP"

        try:
            # [이벤트 1] start 이벤트 전송 (AI 메시지 ID를 미리 전달)
            start_payload = {
                "messageId": ai_message_id,
                "replyTo": message_id
            }
            yield f"event: start\ndata: {json.dumps(start_payload, ensure_ascii=False)}\n\n"

            # [이벤트 2] delta 이벤트 스트리밍
            async for chunk in stream_chunks:
                # [완료 조건 2] 클라이언트 연결 끊김 감지 (S4)
                if await request.is_disconnected():
                    logger.info(f"클라이언트 연결 끊김 감지 (sessionId={session_id})")
                    break

                # 후보(candidate) 및 안전 차단 검사
                candidate = chunk.candidates[0] if (hasattr(chunk, "candidates") and chunk.candidates) else None
                if candidate and getattr(candidate, "finish_reason", None):
                    cand_finish_str = str(candidate.finish_reason).upper()
                    BLOCK_REASONS = ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")
                    if any(r in cand_finish_str for r in BLOCK_REASONS):
                        logger.warning(f"스트리밍 중 안전/콘텐츠 차단 발생: {cand_finish_str}")
                        yield f"event: error\ndata: {json.dumps({'code': 'BLOCKED', 'message': '이 질문에는 답변할 수 없어요.'}, ensure_ascii=False)}\n\n"
                        return

                    if "STOP" in cand_finish_str:
                        finish_reason = "STOP"
                    elif "MAX_TOKENS" in cand_finish_str:
                        finish_reason = "MAX_TOKENS"

                # 텍스트 청크 추출 및 delta 전송
                text_part = chunk.text if hasattr(chunk, "text") and chunk.text else ""
                if text_part:
                    accumulated_chunks.append(text_part)
                    delta_payload = {"text": text_part}
                    yield f"event: delta\ndata: {json.dumps(delta_payload, ensure_ascii=False)}\n\n"

            # [완료 조건 2] 클라이언트 연결이 끊겼는지 확인
            if await request.is_disconnected():
                full_text = "".join(accumulated_chunks)
                if full_text.strip():
                    logger.info(f"연결 중단: 받은 데까지 status='stopped'로 저장 (len={len(full_text)})")
                    await _save_ai_message_safely(
                        session_id=session_id,
                        reply_to_message_id=message_id,
                        content=full_text,
                        message_id=ai_message_id,
                        status="stopped"
                    )
                else:
                    logger.info("연결 중단: 받은 텍스트가 없어 AI 메시지 미저장")
                return

            # 전체 생성 완료 검증 (빈 답변 방지)
            full_text = "".join(accumulated_chunks)
            if not full_text.strip():
                logger.error("스트리밍 완료되었으나 생성된 텍스트가 비어 있습니다.")
                yield f"event: error\ndata: {json.dumps({'code': 'UPSTREAM_ERROR', 'message': '답변을 받지 못했어요.'}, ensure_ascii=False)}\n\n"
                return

            # [완료 조건 1 & S5] 받은 전체를 status='done'으로 DB 저장
            await _save_ai_message_safely(
                session_id=session_id,
                reply_to_message_id=message_id,
                content=full_text,
                message_id=ai_message_id,
                status="done"
            )
            is_completed = True

            # [이벤트 3] done 이벤트 전송
            done_payload = {
                "messageId": ai_message_id,
                "finishReason": finish_reason
            }
            yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"태스크 취소 감지 (sessionId={session_id}): 중단된 곳까지 저장 시도")
            full_text = "".join(accumulated_chunks)
            if full_text.strip() and not is_completed:
                await _save_ai_message_safely(
                    session_id=session_id,
                    reply_to_message_id=message_id,
                    content=full_text,
                    message_id=ai_message_id,
                    status="stopped"
                )
            raise
        except ChatServiceError as err:
            # [완료 조건 3] 도중 오류는 error 이벤트로 전송 (AI 메시지는 미저장)
            logger.error(f"스트리밍 도중 ChatServiceError: {err.code} {err.message}")
            yield f"event: error\ndata: {json.dumps({'code': err.code, 'message': err.message}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error(f"스트리밍 도중 예기치 못한 예외: {exc}")
            yield f"event: error\ndata: {json.dumps({'code': 'INTERNAL', 'message': '답변을 받지 못했어요.'}, ensure_ascii=False)}\n\n"
        finally:
            # 스트림 종료 시 세션 락 반드시 해제
            await session_manager.release(session_id)

    # 버퍼링 비활성화 헤더 전달 (명세서 S3)
    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
