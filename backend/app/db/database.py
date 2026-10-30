"""
데이터베이스 연결 및 초기화 모듈 (database.py)

명세서 3.2(messages 테이블) 및 B5(저장소) 규격을 구현합니다.
- 비동기 SQLite 라이브러리인 aiosqlite를 사용하여 DB 연결을 관리합니다.
- 서버 시작 시 messages 테이블 및 인덱스가 존재하지 않으면 자동으로 생성합니다.
- 명세서 B8 헬스 체크를 위한 DB 연결 점검 함수를 제공합니다.
"""

import os
import logging
from pathlib import Path
from typing import AsyncGenerator
import aiosqlite

from app.config import settings

logger = logging.getLogger("chacha-backend.db")


def get_db_path() -> str:
    """
    환경변수에 지정된 데이터베이스 경로를 반환하며,
    해당 파일이 위치할 상위 디렉토리가 없으면 자동으로 생성합니다.
    """
    db_path_str = settings.database_path
    
    # Windows 환경에서 Linux 기본 경로(/data/chacha.db)로 설정되었을 경우 로컬 폴더(./data/chacha.db)로 유연하게 보정
    if os.name == "nt" and db_path_str.startswith("/data/"):
        db_path = Path("data") / Path(db_path_str).name
    else:
        db_path = Path(db_path_str)

    # DB 파일의 부모 디렉토리가 존재하지 않으면 생성
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    FastAPI 의존성 주입(Dependency) 및 비동기 컨텍스트용 DB 커넥션 제너레이터
    
    Row Factory를 aiosqlite.Row로 설정하여 컬럼 이름으로 결과에 접근할 수 있습니다.
    """
    db_path = get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    """
    서버 구동 시 데이터베이스 초기화 함수 (명세서 B5)
    
    [완료 조건 1 검증]
    - 서버 시작 시 'messages' 테이블이 없으면 생성합니다.
    - 검색 성능 최적화를 위해 (session_id, created_at) 복합 인덱스를 생성합니다 (명세서 3.2).
    - 별도의 마이그레이션 도구 없이 DDL 스크립트를 직접 실행합니다.
    """
    db_path = get_db_path()
    logger.info(f"데이터베이스 초기화 시작: {db_path}")

    # messages 테이블 DDL (명세서 3.2)
    # id: TEXT (UUID) PK
    # session_id: TEXT, NOT NULL
    # role: TEXT ('user' 또는 'assistant')
    # content: TEXT (본문)
    # status: TEXT ('done' 또는 'stopped')
    # reply_to: TEXT, UNIQUE, NULL 가능 (AI 답변이 답한 사용자 메시지 ID)
    # created_at: TEXT (ISO 8601 UTC 타임스탬프)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('done', 'stopped')),
        reply_to TEXT UNIQUE,
        created_at TEXT NOT NULL
    );
    """

    # 복합 인덱스 DDL: (session_id, created_at) (명세서 3.2 인덱스 규칙)
    create_index_query = """
    CREATE INDEX IF NOT EXISTS idx_messages_session_created 
    ON messages (session_id, created_at);
    """

    async with aiosqlite.connect(db_path) as db:
        await db.execute(create_table_query)
        await db.execute(create_index_query)
        await db.commit()

    logger.info("데이터베이스 및 messages 테이블 초기화 완료")


async def check_db_health() -> bool:
    """
    명세서 B8 헬스 체크용 DB 연결 확인 함수
    
    간단한 'SELECT 1' 쿼리를 수행하여 데이터베이스 읽기/연결 상태를 검증합니다.
    """
    try:
        db_path = get_db_path()
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT 1") as cursor:
                result = await cursor.fetchone()
                return result is not None and result[0] == 1
    except Exception as e:
        logger.error(f"DB 헬스체크 실패: {e}")
        return False
