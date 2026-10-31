"""
메시지 저장소(Repository) 모듈 (repository.py)

명세서 3.2 및 B2(이력 조회 API)에서 요구하는 데이터 접근 로직을 담당합니다.
- 세션별 최근 100개 메시지를 시간순(오래된 것부터)으로 조회
- 메시지 단건 등록 (테스트 및 향후 전송 API 연계)
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import aiosqlite

logger = logging.getLogger("chacha-backend.repository")


def now_iso() -> str:
    """
    명세서 3.2 및 4장 규격의 일관된 ISO 8601 UTC 타임스탬프를 생성합니다.
    형식: YYYY-MM-DDTHH:MM:SS.mmmZ (예: 2026-10-29T03:12:45.120Z)
    
    문자열 비교 시 시간 순서가 왜곡되지 않도록 밀리초 단위와 'Z' 접미사로 통일합니다.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MessageRepository:
    """
    messages 테이블에 대한 CRUD 데이터 접근 객체 (DAO)
    """

    @staticmethod
    async def get_messages_by_session(
        db: aiosqlite.Connection,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        [완료 조건 2 & 3 검증 로직]
        세션 ID에 해당하는 메시지 이력을 조회합니다.
        
        규칙 (명세서 B2):
        1. 최근 등록된 최대 100개(limit) 메시지를 가져옵니다.
        2. 대화 흐름에 맞게 시간순(오래된 것부터 -> 최신순, created_at ASC)으로 정렬하여 반환합니다.
        3. 동일 시각에 등록된 질문/답변의 순서가 뒤바뀌지 않도록 DB 삽입 순서(rowid, seq)를 동점 정렬 기준으로 사용합니다.
        4. 메시지가 없으면 빈 리스트 []를 반환합니다 (404 아님).
        
        쿼리 방식:
        - 내부 서브쿼리에서 최신 N개를 역순(DESC) 및 rowid DESC로 슬라이싱한 후,
        - 바깥 쿼리에서 다시 시간순(ASC) 및 seq ASC로 재정렬합니다.
        """
        query = """
        SELECT id, session_id, role, content, status, reply_to, created_at
        FROM (
            SELECT rowid AS seq, id, session_id, role, content, status, reply_to, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
        )
        ORDER BY created_at ASC, seq ASC;
        """

        async with db.execute(query, (session_id, limit)) as cursor:
            rows = await cursor.fetchall()
            
            # 조회된 Row 객체들을 딕셔너리 리스트로 변환
            messages = []
            for row in rows:
                messages.append({
                    "id": row["id"],
                    "sessionId": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "status": row["status"],
                    "replyTo": row["reply_to"],
                    "createdAt": row["created_at"],
                })
            return messages

    @staticmethod
    async def insert_message(
        db: aiosqlite.Connection,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        status: str,
        created_at: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        messages 테이블에 새 메시지 레코드를 추가합니다 (명세서 3.2).
        created_at이 제공되지 않으면 now_iso()로 표준 UTC ISO 포맷을 생성합니다.
        """
        timestamp = created_at or now_iso()
        query = """
        INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        await db.execute(
            query,
            (message_id, session_id, role, content, status, reply_to, timestamp)
        )
        await db.commit()

        return {
            "id": message_id,
            "sessionId": session_id,
            "role": role,
            "content": content,
            "status": status,
            "replyTo": reply_to,
            "createdAt": timestamp
        }

    @staticmethod
    async def get_message_by_id(
        db: aiosqlite.Connection,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        메시지 ID(PK)로 단건 메시지를 조회합니다.
        (재시도 여부 및 중복 메시지 검증용, 명세서 B1 & B6)
        """
        query = """
        SELECT id, session_id, role, content, status, reply_to, created_at
        FROM messages
        WHERE id = ?;
        """
        async with db.execute(query, (message_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "sessionId": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "status": row["status"],
                "replyTo": row["reply_to"],
                "createdAt": row["created_at"],
            }

    @staticmethod
    async def get_reply_for_message(
        db: aiosqlite.Connection,
        user_message_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        특정 사용자 메시지(reply_to)에 이미 생성된 AI 답변이 있는지 확인합니다.
        
        [명세서 B1 규칙]
        이미 답이 있는 사용자 메시지를 다시 요청하면 409 ALREADY_ANSWERED 오류를 반환합니다.
        """
        query = """
        SELECT id, session_id, role, content, status, reply_to, created_at
        FROM messages
        WHERE reply_to = ? AND role = 'assistant';
        """
        async with db.execute(query, (user_message_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "sessionId": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "status": row["status"],
                "replyTo": row["reply_to"],
                "createdAt": row["created_at"],
            }

    @staticmethod
    async def get_context_messages(
        db: aiosqlite.Connection,
        session_id: str,
        current_message_id: str,
        max_turns: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Gemini API 호출에 전달할 최근 대화 맥락을 조회합니다 (명세서 B4).
        
        [명세서 B4 맥락 구성 규칙]
        1. 이번 메시지 직전까지 최근 CONTEXT_TURNS 턴을 가져옵니다 (기본 10턴 = 메시지 최대 20개).
        2. status가 'stopped'인 답변도 사용자가 본 내용이므로 맥락에 포함합니다.
        3. 답이 없는 사용자 메시지(이전에 실패한 요청)는 제외합니다 (user와 model이 번갈아 와야 함).
        4. 현재 처리 중인 메시지(current_message_id)는 아직 완료되지 않은 상태이므로 제외하고 이전 대화만 가져옵니다.
        5. rowid(seq) 동점 기준을 적용하여 시간순(ASC)으로 정렬합니다.
        """
        max_messages = max_turns * 2
        query = """
        SELECT id, session_id, role, content, status, reply_to, created_at
        FROM (
            SELECT m.rowid AS seq, m.id, m.session_id, m.role, m.content, m.status, m.reply_to, m.created_at
            FROM messages m
            WHERE m.session_id = ? 
              AND m.id != ?
              AND (
                  -- AI 메시지인 경우 (done 또는 stopped)
                  m.role = 'assistant'
                  OR
                  -- 사용자 메시지인 경우: 반드시 이 메시지에 대한 AI 답변이 존재하는 경우만 포함 (답 없는 실패 요청 제외)
                  (m.role = 'user' AND EXISTS (
                      SELECT 1 FROM messages reply 
                      WHERE reply.reply_to = m.id AND reply.role = 'assistant'
                  ))
              )
            ORDER BY m.created_at DESC, m.rowid DESC
            LIMIT ?
        )
        ORDER BY created_at ASC, seq ASC;
        """
        async with db.execute(query, (session_id, current_message_id, max_messages)) as cursor:
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                messages.append({
                    "id": row["id"],
                    "sessionId": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "status": row["status"],
                    "replyTo": row["reply_to"],
                    "createdAt": row["created_at"],
                })
            return messages
