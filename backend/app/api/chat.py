"""
메시지 전송 API 모듈 (chat.py)

명세서 B1(메시지 전송 API), B3(Gemini 연동), B4(맥락 구성), B6(입력 검증), B7(동시성 제어), 4장 오류 규격을 처리합니다.
- 엔드포인트: POST /api/chat
"""

import logging
from typing import Literal
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import aiosqlite

from app.db.database import get_db
from app.services.session_manager import session_manager
from app.services.chat_service import (
    validate_chat_input,
    prepare_user_message,
    load_system_instruction,
    build_context_contents,
    call_gemini,
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
        await prepare_user_message(
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
            current_message=clean_message
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
