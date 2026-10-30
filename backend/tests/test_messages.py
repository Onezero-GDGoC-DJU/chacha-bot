"""
저장소 및 세션 이력 조회 API 단위 테스트 (test_messages.py)

이슈 6번 완료 조건 검증:
1. 서버 시작 시 messages 테이블이 없으면 만든다.
2. GET /api/sessions/{sessionId}/messages 가 최근 100개를 시간순으로 돌려준다 (동점 시 rowid 순 보장).
3. 메시지가 없는 세션은 200 과 빈 배열을 돌려준다.
4. 잘못된 sessionId 형식은 400 INVALID_REQUEST를 돌려준다.

[피드백 반영]
- 실제 개발/운영 DB가 오염되지 않도록 pytest의 tmp_path와 monkeypatch를 사용하여
  테스트마다 독립된 임시 SQLite DB(test.db)를 생성하여 검증합니다.
"""

import uuid
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db.database import get_db_path
from app.db.repository import MessageRepository, now_iso


@pytest.fixture(autouse=True)
def client(tmp_path, monkeypatch):
    """
    각 테스트마다 격리된 임시 데이터베이스를 사용하는 fixture
    
    [피드백 1 반영]
    - 개발 및 운영 DB 파일 오염을 방지하기 위해 tmp_path 디렉토리에 test.db를 생성합니다.
    - TestClient(app)을 컨텍스트 매니저('with')로 감싸 lifespan(테이블 초기화 등)이 실행되도록 합니다.
    """
    temp_db_file = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(temp_db_file))

    with TestClient(app) as test_client:
        yield test_client


def test_init_db_creates_messages_table(client):
    """
    [완료 조건 1]
    서버 시작 시 messages 테이블 및 복합 인덱스가 없으면 생성되는지 검증
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # sqlite_master에서 messages 테이블 및 복합 인덱스 존재 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages';")
    table = cursor.fetchone()
    assert table is not None, "messages 테이블이 생성되지 않았습니다."
    assert table[0] == "messages"

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_messages_session_created';")
    index = cursor.fetchone()
    assert index is not None, "idx_messages_session_created 인덱스가 생성되지 않았습니다."

    conn.close()


def test_get_messages_invalid_session_id_returns_400(client):
    """
    [완료 조건 4]
    잘못된 sessionId 형식은 400 INVALID_REQUEST 오류를 돌려준다.
    """
    invalid_session_id = "invalid-session-uuid-1234"
    response = client.get(f"/api/sessions/{invalid_session_id}/messages")

    # 1. HTTP 400 Bad Request 검증
    assert response.status_code == 400, f"예상 상태 코드는 400이지만 {response.status_code}를 받았습니다."

    # 2. 명세서 4장 에러 본문 규격 검증: {"error": {"code": "INVALID_REQUEST", ...}}
    data = response.json()
    assert "error" in data, "에러 응답에 'error' 키가 없습니다."
    assert data["error"]["code"] == "INVALID_REQUEST", f"에러 코드는 INVALID_REQUEST여야 하지만 {data['error']['code']}입니다."


def test_get_messages_empty_session_returns_200_and_empty_list(client):
    """
    [완료 조건 3]
    메시지가 없는 세션은 200 과 빈 배열 {"messages": []}을 돌려준다 (404 아님).
    """
    valid_empty_session_id = str(uuid.uuid4())
    response = client.get(f"/api/sessions/{valid_empty_session_id}/messages")

    # 1. HTTP 200 OK 검증
    assert response.status_code == 200, f"예상 상태 코드는 200이지만 {response.status_code}를 받았습니다."

    # 2. 빈 배열 {"messages": []} 검증
    data = response.json()
    assert "messages" in data
    assert data["messages"] == [], f"빈 배열이어야 하지만 {data['messages']}가 반환되었습니다."


def test_get_messages_returns_recent_100_in_chronological_order(client):
    """
    [완료 조건 2 및 피드백 2 반영]
    GET /api/sessions/{sessionId}/messages 가 최근 100개를 시간순(오래된 것부터 -> 최신순)으로 돌려준다.
    
    검증 시나리오:
    1. 총 105개의 메시지를 1초 간격의 표준 ISO 8601 UTC 밀리초 포맷으로 생성하여 DB에 저장
       (0번이 가장 오래됨, 104번이 가장 최신)
    2. API를 호출했을 때:
       - 정확히 최근 100개(5번 ~ 104번)만 반환되어야 함.
       - 정렬 순서는 과거 -> 최신(5번 -> 104번 순)이어야 함.
    """
    session_id = str(uuid.uuid4())
    db_path = get_db_path()

    base_time = datetime(2026, 10, 30, 10, 0, 0, tzinfo=timezone.utc)

    # 105개 메시지 삽입 (표준 ISO 8601 UTC Z 포맷 사용)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for i in range(105):
        msg_id = str(uuid.uuid4())
        role = "user" if i % 2 == 0 else "assistant"
        content = f"메시지 {i}번 본문"
        # 명세서 표준 포맷: YYYY-MM-DDTHH:MM:SS.mmmZ
        created_at = (base_time + timedelta(seconds=i)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        
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

    # 2. 최근 100개 (5번 ~ 104번) 포함 여부 검증
    assert messages[0]["content"] == "메시지 5번 본문"
    assert messages[-1]["content"] == "메시지 104번 본문"

    # 3. 시간순(과거 -> 최신) 정렬 여부 검증
    for idx in range(len(messages) - 1):
        curr_time = messages[idx]["createdAt"]
        next_time = messages[idx + 1]["createdAt"]
        assert curr_time < next_time, f"메시지가 시간순으로 정렬되지 않았습니다: {curr_time} >= {next_time}"


def test_get_messages_same_timestamp_orders_by_rowid(client):
    """
    [피드백 2 추가 검증]
    동일한 생성 시각(created_at)을 가진 메시지들이라도 rowid(seq)에 의해
    질문(먼저 삽입) -> 답변(나중에 삽입)의 순서가 항상 안정적으로 유지되어야 한다.
    """
    session_id = str(uuid.uuid4())
    db_path = get_db_path()
    same_timestamp = now_iso()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 동일한 시각에 질문(user) 먼저 삽입 후 답변(assistant) 나중에 삽입
    user_id = str(uuid.uuid4())
    ai_id = str(uuid.uuid4())

    cursor.execute(
        """
        INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (user_id, session_id, "user", "동일 시각 질문", "done", None, same_timestamp)
    )
    cursor.execute(
        """
        INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (ai_id, session_id, "assistant", "동일 시각 답변", "done", user_id, same_timestamp)
    )
    conn.commit()
    conn.close()

    # API 호출
    response = client.get(f"/api/sessions/{session_id}/messages")
    assert response.status_code == 200
    messages = response.json()["messages"]

    assert len(messages) == 2
    # 동일 시각이어도 rowid 순서대로 user가 먼저, assistant가 다음에 나와야 함
    assert messages[0]["id"] == user_id
    assert messages[0]["role"] == "user"
    assert messages[1]["id"] == ai_id
    assert messages[1]["role"] == "assistant"
