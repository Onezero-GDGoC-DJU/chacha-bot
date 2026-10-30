"""
세션 및 메시지 이력 API 모듈 (sessions.py)

명세서 B2(이력 조회 API) 및 B6(입력 검증), 4장(오류 공통 규격)을 구현합니다.
- 경로: GET /api/sessions/{sessionId}/messages
- 완료 조건 검증:
  1. GET /api/sessions/{sessionId}/messages 가 최근 100개를 시간순으로 돌려준다.
  2. 메시지가 없는 세션은 200과 빈 배열 {"messages": []}을 돌려준다.
  3. 잘못된 sessionId 형식은 400 INVALID_REQUEST 오류를 돌려준다.
"""

import uuid
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import aiosqlite

from app.db.database import get_db
from app.db.repository import MessageRepository

router = APIRouter()


class MessageItem(BaseModel):
    """
    단일 메시지 응답 스키마 (명세서 4장 & B2 규격: camelCase 필드명)
    """
    id: str = Field(description="메시지 고유 ID (UUID)")
    role: Literal["user", "assistant"] = Field(description="발화 주체 ('user' 또는 'assistant')")
    content: str = Field(description="메시지 텍스트 본문 (마크다운 원문)")
    status: Literal["done", "stopped"] = Field(description="메시지 상태 ('done' 또는 'stopped')")
    replyTo: Optional[str] = Field(default=None, description="AI 답변이 참조한 사용자 메시지 ID (사용자 메시지는 null)")
    createdAt: str = Field(description="메시지 생성 시각 (ISO 8601 UTC)")


class MessagesResponse(BaseModel):
    """
    이력 조회 성공 응답 스키마 (HTTP 200)
    """
    messages: List[MessageItem] = Field(default_factory=list, description="시간순으로 정렬된 메시지 목록")


class ErrorDetail(BaseModel):
    """
    명세서 4장 오류 응답 상세 스키마
    """
    code: str
    message: str


class ErrorResponse(BaseModel):
    """
    명세서 4장 공통 오류 응답 래퍼
    """
    error: ErrorDetail


@router.get(
    "/sessions/{sessionId}/messages",
    response_model=MessagesResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": MessagesResponse, "description": "이력 조회 성공"},
        400: {"model": ErrorResponse, "description": "잘못된 세션 ID 형식 (INVALID_REQUEST)"}
    },
    summary="세션별 대화 이력 조회",
    description="세션 ID에 해당하는 대화 이력을 최근 100개까지 오래된 순(시간순)으로 조회합니다 (명세서 B2)."
)
async def get_session_messages(
    sessionId: str,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    세션 대화 이력 조회 핸들러
    
    [완료 조건 검증]
    1. sessionId 유효성 검사 (UUID 형식 여부):
       - UUID 형식이 아니면 400 INVALID_REQUEST 반환 (명세서 4장 및 B6)
    2. 데이터베이스 조회:
       - 해당 세션의 최근 100개 메시지를 시간순(과거 -> 최신)으로 조회 (명세서 B2)
    3. 결과 반환:
       - 메시지가 존재하지 않아도 404가 아닌 200과 빈 배열 {"messages": []} 반환
    """
    # --------------------------------------------------------------------------
    # 1. 입력 검증 (명세서 B6 & 4장)
    # --------------------------------------------------------------------------
    try:
        # sessionId가 올바른 UUID 형식인지 검증
        uuid.UUID(sessionId)
    except (ValueError, AttributeError):
        # [완료 조건 4] 잘못된 sessionId 형식은 400 INVALID_REQUEST 반환
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "유효하지 않은 세션 ID입니다."
                }
            }
        )

    # --------------------------------------------------------------------------
    # 2. 데이터베이스에서 이력 조회 (명세서 B2: 최근 100개 시간순)
    # --------------------------------------------------------------------------
    raw_messages = await MessageRepository.get_messages_by_session(
        db=db,
        session_id=sessionId,
        limit=100
    )

    # --------------------------------------------------------------------------
    # 3. 응답 반환 (명세서 B2: 없으면 200 {"messages": []})
    # --------------------------------------------------------------------------
    return MessagesResponse(messages=raw_messages)
