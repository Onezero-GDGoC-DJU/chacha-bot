"""
세션 동시성 제어 모듈 (session_manager.py)

명세서 B1 & B7 규격을 구현합니다.
- "이 세션에서 생성 중인 답변이 있으면 409 SESSION_BUSY를 돌려줘요."
- "생성 중 표시는 서버 메모리(세션 ID 집합)로 충분해요. 백엔드 컨테이너는 하나만 띄우니까요."
- 비동기 락을 통해 세션별 1개의 요청만 동시 처리되도록 보장합니다.
"""

import asyncio
from typing import Set


class SessionManager:
    """
    세션별 동시 요청 방지를 위한 인메모리 세션 잠금 관리자
    """

    def __init__(self):
        # 현재 답변 생성 중인 세션 ID 목록 (인메모리 Set)
        self._busy_sessions: Set[str] = set()
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> bool:
        """
        세션 잠금 획득 시도
        
        :param session_id: 요청 세션 ID
        :return: 잠금 획득 성공 시 True, 이미 생성 중이면 False (409 SESSION_BUSY 대상)
        """
        async with self._lock:
            if session_id in self._busy_sessions:
                return False
            self._busy_sessions.add(session_id)
            return True

    async def release(self, session_id: str) -> None:
        """
        세션 잠금 해제
        
        :param session_id: 처리 완료된 세션 ID
        """
        async with self._lock:
            self._busy_sessions.discard(session_id)


# 전역 세션 관리자 싱글톤 인스턴스
session_manager = SessionManager()
