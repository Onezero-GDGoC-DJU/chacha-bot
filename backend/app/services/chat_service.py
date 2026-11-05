"""
채팅 비즈니스 로직 및 Gemini 연동 서비스 (chat_service.py)

명세서 B1(메시지 전송 API), B3(Gemini 연동), B4(맥락 구성), B6(입력 검증), 4장 오류 코드를 구현합니다.
- 나중에 스트리밍([기능] 스트리밍 엔드포인트 #11)에서도 검증, 맥락 구성, 저장 로직을 그대로 재사용할 수 있도록
  각 단계를 독립적인 함수로 분리하여 모듈화합니다.
"""

import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional, AsyncIterator
import aiosqlite
from fastapi import status
# google-genai가 없으면 요청 시점이 아니라 서버 시작 시 바로 ImportError가 나도록 모듈 맨 위에서 import
from google import genai
from google.genai import types, errors

from app.config import settings
from app.db.repository import MessageRepository, now_iso

logger = logging.getLogger("chacha-backend.chat")

# 서버 시작 시(lifespan) 한 번 로드한 시스템 프롬프트를 보관하는 인메모리 캐시 (요청당 디스크 I/O 방지)
_cached_system_instruction: Optional[str] = None


def set_cached_system_instruction(instruction: str) -> None:
    """
    서버 시작 시(lifespan) 로드한 시스템 프롬프트를 전역 캐시에 등록합니다.
    """
    global _cached_system_instruction
    _cached_system_instruction = instruction


class ChatServiceError(Exception):
    """
    채팅 처리 중 발생하는 명세서 4장 규격의 비즈니스 예외
    """
    def __init__(self, http_status: int, code: str, message: str):
        self.http_status = http_status
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def validate_chat_input(session_id: str, message_id: str, message: str) -> str:
    """
    [명세서 B6 입력 검증]
    1. sessionId: 올바른 UUID 형식인지 검증
    2. messageId: 올바른 UUID 형식인지 검증
    3. message: 문자열이고, 앞뒤 공백 제거 후 1자 이상 MAX_MESSAGE_CHARS자 이하인지 검증
    
    실패 시: 400 INVALID_REQUEST 발생
    """
    # 1. sessionId 검증
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        raise ChatServiceError(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST",
            message="유효하지 않은 세션 ID입니다."
        )

    # 2. messageId 검증
    try:
        uuid.UUID(message_id)
    except (ValueError, AttributeError):
        raise ChatServiceError(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST",
            message="유효하지 않은 메시지 ID입니다."
        )

    # 3. message 길이 검증 (공백 제거 후 1자 이상 MAX_MESSAGE_CHARS자 이하)
    trimmed_message = message.strip()
    if len(trimmed_message) < 1 or len(trimmed_message) > settings.max_message_chars:
        raise ChatServiceError(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST",
            message=f"메시지는 1자 이상 {settings.max_message_chars}자 이하여야 합니다."
        )

    return trimmed_message


async def prepare_user_message(
    db: aiosqlite.Connection,
    session_id: str,
    message_id: str,
    message_content: str
) -> Dict[str, Any]:
    """
    [명세서 B1 처리 순서 3: 사용자 메시지 저장 및 재시도 확인]
    
    1. messageId로 기존 메시지 확인:
       - 다른 세션에 속한 messageId인 경우: 400 INVALID_REQUEST (명세서 B6)
       - 이미 답이 달린 메시지인 경우: 409 ALREADY_ANSWERED (명세서 B1)
       - 이미 저장되어 있지만 답이 없는 경우: 직전 요청 실패에 따른 재시도이므로 중복 저장 없이 기존 메시지 재사용 (완료 조건 2)
    2. 새로운 메시지인 경우:
       - DB에 role='user', status='done', reply_to=None으로 저장
    """
    existing_message = await MessageRepository.get_message_by_id(db, message_id)

    if existing_message:
        # 다른 세션에 속한 messageId 방지 (명세서 B6)
        if existing_message["sessionId"] != session_id:
            raise ChatServiceError(
                http_status=status.HTTP_400_BAD_REQUEST,
                code="INVALID_REQUEST",
                message="다른 세션에 속한 메시지 ID입니다."
            )

        # 이미 AI 답변이 생성된 메시지인지 확인 (명세서 B1)
        reply = await MessageRepository.get_reply_for_message(db, message_id)
        if reply:
            raise ChatServiceError(
                http_status=status.HTTP_409_CONFLICT,
                code="ALREADY_ANSWERED",
                message="이미 답변이 완료된 메시지입니다."
            )

        # 답이 없는 사용자 메시지(직전 실패 요청에 대한 재시도) -> 중복 저장하지 않고 진행
        logger.info(f"재시도 요청 감지 (messageId={message_id}): 사용자 메시지 중복 저장 방지")
        return existing_message

    # 새로운 사용자 메시지 등록 (ISO 8601 UTC 표준 시각)
    new_user_message = await MessageRepository.insert_message(
        db=db,
        message_id=message_id,
        session_id=session_id,
        role="user",
        content=message_content,
        status="done",
        created_at=now_iso(),
        reply_to=None
    )
    return new_user_message


def load_system_instruction() -> str:
    """
    [명세서 2.1 & B3 시스템 프롬프트 로드]
    서버 시작 시 캐시된 프롬프트를 반환하며, 캐시가 없는 경우 파일에서 직접 로드합니다.
    """
    global _cached_system_instruction
    if _cached_system_instruction:
        return _cached_system_instruction

    prompt_path = settings.system_prompt_path
    if not prompt_path.exists():
        logger.error(f"시스템 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
        raise ChatServiceError(
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message="시스템 프롬프트 설정을 찾을 수 없습니다."
        )

    content = prompt_path.read_text(encoding="utf-8").strip()
    if not content:
        logger.error("시스템 프롬프트 내용이 비어 있습니다.")
        raise ChatServiceError(
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message="시스템 프롬프트 설정이 올바르지 않습니다."
        )

    _cached_system_instruction = content
    return content


async def build_context_contents(
    db: aiosqlite.Connection,
    session_id: str,
    current_message_id: str,
    current_message: str
) -> List[Dict[str, Any]]:
    """
    [명세서 B4 맥락 구성]
    1. 순서: 시스템 프롬프트(systemInstruction으로 분리 전달) -> 최근 대화 -> 이번 메시지
    2. 최근 대화는 이번 메시지 직전까지 최근 CONTEXT_TURNS턴 (기본 10턴 = 최대 20개 메시지)
    3. role 변환:
       - DB 'user' -> Gemini 'user'
       - DB 'assistant' -> Gemini 'model'
    4. status='stopped' 답변도 포함 (사용자가 이미 본 내용)
    5. 답이 없는 사용자 메시지는 제외 (MessageRepository.get_context_messages에서 처리)
    6. 마지막에 이번 사용자 메시지 추가
    """
    history_messages = await MessageRepository.get_context_messages(
        db=db,
        session_id=session_id,
        current_message_id=current_message_id,
        max_turns=settings.context_turns
    )

    contents: List[Dict[str, Any]] = []

    # 이전 대화 기록 변환 및 추가
    for msg in history_messages:
        gemini_role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": gemini_role,
            "parts": [{"text": msg["content"]}]
        })

    # 이번에 전송한 최신 사용자 메시지 추가
    contents.append({
        "role": "user",
        "parts": [{"text": current_message}]
    })

    return contents


async def call_gemini(
    contents: List[Dict[str, Any]],
    system_instruction: str
) -> str:
    """
    [명세서 B3 Gemini API 연동 및 4장 오류 변환]
    
    1. SDK: google-genai 공식 라이브러리 사용
    2. 시간 제한: 60초 (초과 시 504 UPSTREAM_TIMEOUT)
    3. 오류 대응:
       - 429 / RESOURCE_EXHAUSTED -> 429 UPSTREAM_QUOTA
       - 5xx / 네트워크 오류 -> 502 UPSTREAM_ERROR
       - 프롬프트 차단(promptFeedback) 또는 SAFETY 차단 -> 422 BLOCKED
       - MAX_TOKENS -> 정상 완료로 취급
       - 응답 message에 Gemini 원문 오류나 API 키를 노출하지 않음
    """
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        # 60초 타임아웃 적용 (명세서 B3)
        async def _generate():
            return await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )

        response = await asyncio.wait_for(_generate(), timeout=60.0)

    except asyncio.TimeoutError:
        logger.error("Gemini API 호출 시간 초과 (60초 초과)")
        raise ChatServiceError(
            http_status=status.HTTP_504_GATEWAY_TIMEOUT,
            code="UPSTREAM_TIMEOUT",
            message="답변을 받지 못했어요."
        )
    except errors.APIError as exc:
        logger.error(f"Gemini API 오류: {exc.code} {exc}")
        if exc.code == 429:
            raise ChatServiceError(
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                code="UPSTREAM_QUOTA",
                message="요청이 많아요. 잠시 후 다시 시도해 주세요."
            )
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )
    except ChatServiceError:
        raise
    except Exception as exc:
        # 네트워크 오류 및 기타 예기치 못한 호출 실패
        logger.error(f"Gemini 호출 실패: {exc}")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    # 응답 안전성 및 차단 여부 검사 (명세서 B3)
    if hasattr(response, "prompt_feedback") and response.prompt_feedback:
        block_reason = getattr(response.prompt_feedback, "block_reason", None)
        if block_reason:
            logger.warning(f"Gemini 프롬프트 차단 발생: {block_reason}")
            raise ChatServiceError(
                http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="BLOCKED",
                message="이 질문에는 답변할 수 없어요."
            )

    # 후보 응답(candidate) 검사
    if not response.candidates:
        logger.error("Gemini 응답에 후보(candidate)가 없습니다.")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    candidate = response.candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    finish_reason_str = str(finish_reason).upper() if finish_reason else ""

    # 차단 사유 확장 (SAFETY, PROHIBITED_CONTENT, BLOCKLIST, SPII)
    BLOCK_REASONS = ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")
    if any(r in finish_reason_str for r in BLOCK_REASONS):
        logger.warning(f"Gemini 답변 생성 중 안전/콘텐츠 필터 차단 (finishReason={finish_reason_str})")
        raise ChatServiceError(
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="BLOCKED",
            message="이 질문에는 답변할 수 없어요."
        )

    # 답변 텍스트 추출 및 빈 답변 검증 (빈 문자열이 done으로 저장되지 않도록 방지)
    if not response.text or not response.text.strip():
        logger.error("Gemini 답변 텍스트가 비어 있습니다.")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    return response.text


async def call_gemini_stream(
    contents: List[Dict[str, Any]],
    system_instruction: str
) -> AsyncIterator[Any]:
    """
    [명세서 S1 Gemini 스트리밍 호출]
    
    1. SDK: client.aio.models.generate_content_stream 사용
    2. 시간 제한: 60초 타임아웃
    3. 오류 발생 시 명세서 4장 규격의 ChatServiceError로 변환
    """
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    from google import genai
    from google.genai import types
    from google.genai import errors

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        # SDK 스트림 요청 초기화
        stream_res = client.aio.models.generate_content_stream(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
        )
        if asyncio.iscoroutine(stream_res) or hasattr(stream_res, "__await__"):
            stream = await stream_res
        else:
            stream = stream_res

    except errors.APIError as exc:
        logger.error(f"Gemini 스트림 초기화 오류: {exc.code} {exc}")
        if exc.code == 429:
            raise ChatServiceError(
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                code="UPSTREAM_QUOTA",
                message="요청이 많아요. 잠시 후 다시 시도해 주세요."
            )
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )
    except ChatServiceError:
        raise
    except Exception as exc:
        logger.error(f"Gemini 스트림 초기화 실패: {exc}")
        raise ChatServiceError(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_ERROR",
            message="답변을 받지 못했어요."
        )

    # 스트림 소비 제너레이터 (청크 스트리밍 도중 발생하는 예외 변환 및 타임아웃 감시)
    start_time = asyncio.get_event_loop().time()

    async def _stream_wrapper():
        try:
            async for chunk in stream:
                # 60초 전체 타임아웃 검사
                if asyncio.get_event_loop().time() - start_time > 60.0:
                    raise asyncio.TimeoutError()
                yield chunk
        except asyncio.TimeoutError:
            logger.error("Gemini 스트림 수신 시간 초과 (60초 초과)")
            raise ChatServiceError(
                http_status=status.HTTP_504_GATEWAY_TIMEOUT,
                code="UPSTREAM_TIMEOUT",
                message="답변을 받지 못했어요."
            )
        except errors.APIError as exc:
            logger.error(f"Gemini 스트림 수신 중 API 오류: {exc.code} {exc}")
            if exc.code == 429:
                raise ChatServiceError(
                    http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                    code="UPSTREAM_QUOTA",
                    message="요청이 많아요. 잠시 후 다시 시도해 주세요."
                )
            raise ChatServiceError(
                http_status=status.HTTP_502_BAD_GATEWAY,
                code="UPSTREAM_ERROR",
                message="답변을 받지 못했어요."
            )
        except ChatServiceError:
            raise
        except asyncio.CancelledError:
            # 클라이언트 연결 끊김으로 인한 비동기 태스크 취소는 상위로 전달
            raise
        except Exception as exc:
            logger.error(f"Gemini 스트림 수신 중 예기치 못한 오류: {exc}")
            raise ChatServiceError(
                http_status=status.HTTP_502_BAD_GATEWAY,
                code="UPSTREAM_ERROR",
                message="답변을 받지 못했어요."
            )

    return _stream_wrapper()


async def save_ai_message(
    db: aiosqlite.Connection,
    session_id: str,
    reply_to_message_id: str,
    content: str,
    message_id: Optional[str] = None,
    status: str = "done"
) -> Dict[str, Any]:
    """
    [명세서 B1 & S5 AI 메시지 저장]
    
    1. message_id가 전달되지 않으면 서버가 새 UUID를 발급 (스트리밍 시에는 미리 발급된 ID 사용)
    2. status: 'done'(정상 완료) 또는 'stopped'(사용자 중단/연결 끊김)
    3. reply_to=사용자 messageId로 저장
    4. 실패 시에는 호출되지 않으므로 실패한 AI 답변은 저장되지 않음 (완료 조건 6 & S5)
    """
    ai_message_id = message_id or str(uuid.uuid4())
    ai_message = await MessageRepository.insert_message(
        db=db,
        message_id=ai_message_id,
        session_id=session_id,
        role="assistant",
        content=content,
        status=status,
        created_at=now_iso(),
        reply_to=reply_to_message_id
    )
    return ai_message
