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
