"""
저장소 및 세션 이력 조회 API 단위 테스트 (test_messages.py)

이슈 6번 완료 조건 검증:
1. 서버 시작 시 messages 테이블이 없으면 만든다.
2. GET /api/sessions/{sessionId}/messages 가 최근 100개를 시간순으로 돌려준다.
3. 메시지가 없는 세션은 200 과 빈 배열을 돌려준다.
4. 잘못된 sessionId 형식은 400 INVALID_REQUEST를 돌려준다.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import aiosqlite

from app.main import app
from app.db.database import get_db_path, init_db
from app.db.repository import MessageRepository


@pytest.fixture(autouse=True)
def setup_test_db():
    """
    각 테스트 실행 전 테이블을 초기화하는 fixture
    """
    with TestClient(app) as client:
        # lifespan 이벤트가 실행되어 init_db()가 호출됨
        yield client


def test_init_db_creates_messages_table(setup_test_db):
    """
    [완료 조건 1]
    서버 시작 시 messages 테이블이 없으면 생성되는지 검증
    """
    import sqlite3
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # sqlite_master에서 messages 테이블 및 인덱스 존재 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages';")
    table = cursor.fetchone()
    assert table is not None, "messages 테이블이 생성되지 않았습니다."
    assert table[0] == "messages"

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_messages_session_created';")
    index = cursor.fetchone()
    assert index is not None, "idx_messages_session_created 인덱스가 생성되지 않았습니다."

    conn.close()


def test_get_messages_invalid_session_id_returns_400(setup_test_db):
    """
    [완료 조건 4]
    잘못된 sessionId 형식은 400 INVALID_REQUEST 오류를 돌려준다.
    """
    client = setup_test_db
    invalid_session_id = "invalid-session-uuid-1234"

    response = client.get(f"/api/sessions/{invalid_session_id}/messages")

    # 1. HTTP 400 Bad Request 검증
    assert response.status_code == 400, f"예상 상태 코드는 400이지만 {response.status_code}를 받았습니다."

    # 2. 명세서 4장 에러 본문 검증: {"error": {"code": "INVALID_REQUEST", ...}}
    data = response.json()
    assert "error" in data, "에러 응답에 'error' 키가 없습니다."
    assert data["error"]["code"] == "INVALID_REQUEST", f"에러 코드는 INVALID_REQUEST여야 하지만 {data['error']['code']}입니다."


def test_get_messages_empty_session_returns_200_and_empty_list(setup_test_db):
    """
    [완료 조건 3]
    메시지가 없는 세션은 200 과 빈 배열 {"messages": []}을 돌려준다 (404 아님).
    """
    client = setup_test_db
    valid_empty_session_id = str(uuid.uuid4())

    response = client.get(f"/api/sessions/{valid_empty_session_id}/messages")

    # 1. HTTP 200 OK 검증
    assert response.status_code == 200, f"예상 상태 코드는 200이지만 {response.status_code}를 받았습니다."

    # 2. 빈 배열 {"messages": []} 검증
    data = response.json()
    assert "messages" in data
    assert data["messages"] == [], f"빈 배열이어야 하지만 {data['messages']}가 반환되었습니다."


def test_get_messages_returns_recent_100_in_chronological_order(setup_test_db):
    """
    [완료 조건 2]
    GET /api/sessions/{sessionId}/messages 가 최근 100개를 시간순(오래된 것부터 -> 최신순)으로 돌려준다.
    
    검증 시나리오:
    1. 총 105개의 메시지를 1초 간격으로 생성하여 DB에 저장 (0번이 가장 오래됨, 104번이 가장 최신)
    2. API를 호출했을 때:
       - 정확히 최근 100개(5번 ~ 104번)만 반환되어야 함.
       - 정렬 순서는 과거 -> 최신(5번 -> 104번 순)이어야 함.
    """
    import sqlite3
    client = setup_test_db
    session_id = str(uuid.uuid4())
    db_path = get_db_path()

    base_time = datetime(2026, 10, 30, 10, 0, 0, tzinfo=timezone.utc)

    # 105개 메시지 삽입 (표준 sqlite3 동기 삽입 - 별도 async 플러그인 의존성 없이 실행)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for i in range(105):
        msg_id = str(uuid.uuid4())
        role = "user" if i % 2 == 0 else "assistant"
        content = f"메시지 {i}번 본문"
        created_at = (base_time + timedelta(seconds=i)).isoformat()
        
        cursor.execute(
            """
            INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (msg_id, session_id, role, content, "done", None, created_at)
        )
    conn.commit()
    conn.close()

    # API 호출
    response = client.get(f"/api/sessions/{session_id}/messages")
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]

    # 1. 최대 100개 제한 검증
    assert len(messages) == 100, f"100개의 메시지가 반환되어야 하지만 {len(messages)}개가 반환되었습니다."

    # 2. 최근 100개 (5번 ~ 104번) 포함 여부 및 시간순 정렬 검증
    assert messages[0]["content"] == "메시지 5번 본문"
    assert messages[-1]["content"] == "메시지 104번 본문"

    # 3. 시간순(오래된 순서대로 증가) 정렬 여부 검증
    for idx in range(len(messages) - 1):
        curr_time = messages[idx]["createdAt"]
        next_time = messages[idx + 1]["createdAt"]
        assert curr_time < next_time, f"메시지가 시간순으로 정렬되지 않았습니다: {curr_time} >= {next_time}"
