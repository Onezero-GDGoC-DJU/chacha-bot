"""
스트리밍 엔드포인트 단위 테스트 (test_chat_stream.py)

이슈 #11 완료 조건 전수 검증:
1. start -> delta ... -> done 순서로 이벤트가 온다 (curl -N으로 확인 가능).
2. 클라이언트 연결이 끊기면 Gemini 스트림도 멈추고, 받은 데까지 stopped로 저장된다 (받은 게 없으면 미저장).
3. 도중 오류는 error 이벤트로 오고, AI 메시지는 저장되지 않는다.
4. 스트림을 열기 전 오류는 기존과 같은 JSON 오류 응답이다.
"""

import json
import uuid
import sqlite3
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db.database import get_db_path
from app.services.session_manager import session_manager
from google.genai import errors


def make_mock_chunk(text: str = "조각", finish_reason: str = None):
    """
    스트리밍 청크 모의 객체 생성
    """
    mock_chunk = MagicMock()
    mock_chunk.text = text
    if finish_reason:
        mock_cand = MagicMock()
        mock_cand.finish_reason = finish_reason
        mock_chunk.candidates = [mock_cand]
    else:
        mock_chunk.candidates = []
    return mock_chunk


async def async_chunk_generator(chunks):
    """
    모의 스트림 청크를 비동기로 방출하는 제너레이터
    """
    for c in chunks:
        yield c


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    각 테스트마다 격리된 임시 SQLite DB를 사용하는 fixture
    """
    temp_db_file = tmp_path / "chat_stream_test.db"
    monkeypatch.setattr(settings, "database_path", str(temp_db_file))

    with TestClient(app) as test_client:
        yield test_client


def parse_sse_events(raw_text: str):
    """
    SSE 원문 문자열을 파싱하여 (event_name, data_dict) 리스트로 반환하는 도우미 함수
    """
    events = []
    # SSE 블록은 \n\n으로 구분됨
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_name = None
        data = None
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split("event:", 1)[1].strip()
            elif line.startswith("data:"):
                data_str = line.split("data:", 1)[1].strip()
                try:
                    data = json.loads(data_str)
                except Exception:
                    data = data_str
        if event_name:
            events.append((event_name, data))
    return events


def test_post_chat_stream_success_flow(client):
    """
    [완료 조건 1]
    정상 스트리밍 시 start -> delta ... -> done 순서로 이벤트가 전달되고,
    AI 메시지가 status='done'으로 DB에 최종 저장된다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    mock_chunks = [
        make_mock_chunk(text="안녕"),
        make_mock_chunk(text="하세요! "),
        make_mock_chunk(text="반가워요.", finish_reason="STOP")
    ]

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content_stream = MagicMock(
            return_value=async_chunk_generator(mock_chunks)
        )

        response = client.post(
            "/api/chat/stream",
            json={
                "sessionId": session_id,
                "messageId": message_id,
                "message": "안녕 반가워"
            }
        )

    # 1. HTTP 200 및 SSE 헤더 검증
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers.get("x-accel-buffering") == "no"

    # 2. SSE 이벤트 순서 검증: start -> delta -> delta -> delta -> done
    events = parse_sse_events(response.text)
    assert len(events) >= 3

    event_names = [e[0] for e in events]
    assert event_names[0] == "start"
    assert "delta" in event_names
    assert event_names[-1] == "done"

    # start 이벤트 본문 검증
    start_data = events[0][1]
    assert "messageId" in start_data
    assert start_data["replyTo"] == message_id

    # delta 텍스트 합산 검증
    combined_text = "".join(e[1]["text"] for e in events if e[0] == "delta")
    assert combined_text == "안녕하세요! 반가워요."

    # done 이벤트 검증
    done_data = events[-1][1]
    assert done_data["messageId"] == start_data["messageId"]
    assert done_data["finishReason"] == "STOP"

    # 3. DB 저장 상태 검증: 사용자(done), AI(done)
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, status, reply_to FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC;",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2
    # 사용자 메시지
    assert rows[0][0] == message_id
    assert rows[0][1] == "user"
    assert rows[0][3] == "done"
    # AI 메시지
    assert rows[1][0] == start_data["messageId"]
    assert rows[1][1] == "assistant"
    assert rows[1][2] == "안녕하세요! 반가워요."
    assert rows[1][3] == "done"
    assert rows[1][4] == message_id


def test_post_chat_stream_client_disconnected_saves_stopped(client):
    """
    [완료 조건 2]
    클라이언트 연결이 도중에 끊기면(request.is_disconnected),
    Gemini 스트림 읽기를 멈추고 받은 데까지 status='stopped'로 저장된다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    mock_chunks = [
        make_mock_chunk(text="첫 번째 조각"),
        make_mock_chunk(text="두 번째 조각"),
        make_mock_chunk(text="세 번째 조각 (도달하지 않아야 함)")
    ]

    disconnect_call_count = 0

    async def mock_is_disconnected():
        nonlocal disconnect_call_count
        disconnect_call_count += 1
        # 2번째 청크 이후 연결 끊김 시뮬레이션
        return disconnect_call_count >= 2

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content_stream = MagicMock(
            return_value=async_chunk_generator(mock_chunks)
        )

        with patch("fastapi.Request.is_disconnected", side_effect=mock_is_disconnected):
            response = client.post(
                "/api/chat/stream",
                json={
                    "sessionId": session_id,
                    "messageId": message_id,
                    "message": "중단 테스트"
                }
            )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [e[0] for e in events]
    # 연결이 끊겼으므로 done 이벤트는 나가지 않아야 함
    assert "done" not in event_names

    # DB 확인: AI 메시지가 status='stopped'로 저장되어 있어야 함
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, status FROM messages WHERE session_id = ? AND role = 'assistant';",
        (session_id,)
    )
    ai_rows = cursor.fetchall()
    conn.close()

    assert len(ai_rows) == 1
    assert ai_rows[0][3] == "stopped"
    assert "첫 번째 조각" in ai_rows[0][2]


def test_post_chat_stream_disconnected_with_no_text_saves_nothing(client):
    """
    [완료 조건 2 보충]
    텍스트를 한 글자도 받지 못한 상태에서 연결이 끊기면 AI 메시지는 저장되지 않는다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    async def mock_is_disconnected():
        # 처음부터 즉시 연결 끊김
        return True

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content_stream = MagicMock(
            return_value=async_chunk_generator([make_mock_chunk("조각")])
        )

        with patch("fastapi.Request.is_disconnected", side_effect=mock_is_disconnected):
            response = client.post(
                "/api/chat/stream",
                json={
                    "sessionId": session_id,
                    "messageId": message_id,
                    "message": "즉시 중단 테스트"
                }
            )

    assert response.status_code == 200

    # DB 확인: AI 메시지는 저장되지 않아야 함 (사용자 메시지만 1개)
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role FROM messages WHERE session_id = ?;",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"


def test_post_chat_stream_midstream_error_sends_error_event_and_no_ai_save(client):
    """
    [완료 조건 3]
    스트리밍 도중 오류 발생 시(Gemini 500 오류 등) error 이벤트로 오고, AI 메시지는 저장되지 않는다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    async def error_chunk_generator():
        yield make_mock_chunk("첫 번째 정상 청크")
        # 두 번째 청크에서 APIError 발생
        raise errors.APIError(code=500, response_json={"error": {"code": 500, "message": "Upstream error"}})

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content_stream = MagicMock(
            return_value=error_chunk_generator()
        )

        response = client.post(
            "/api/chat/stream",
            json={
                "sessionId": session_id,
                "messageId": message_id,
                "message": "도중 에러 테스트"
            }
        )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [e[0] for e in events]

    assert "start" in event_names
    assert "error" in event_names
    assert "done" not in event_names

    # error 이벤트 데이터 검증
    error_data = next(e[1] for e in events if e[0] == "error")
    assert error_data["code"] == "UPSTREAM_ERROR"

    # DB 확인: AI 메시지는 전혀 저장되지 않아야 함
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role FROM messages WHERE session_id = ?;",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"


def test_post_chat_stream_pre_stream_error_returns_json(client):
    """
    [완료 조건 4]
    스트림을 열기 전에 발생한 오류(잘못된 요청 400, 동시 요청 409, 할당량 초과 429 등)는
    기존과 동일한 JSON 오류 응답을 돌려준다.
    """
    # 1. 입력 검증 실패 (잘못된 세션 UUID) -> 400 INVALID_REQUEST JSON
    resp_invalid = client.post(
        "/api/chat/stream",
        json={"sessionId": "invalid-uuid", "messageId": str(uuid.uuid4()), "message": "안녕"}
    )
    assert resp_invalid.status_code == 400
    assert resp_invalid.headers["content-type"] == "application/json"
    assert resp_invalid.json()["error"]["code"] == "INVALID_REQUEST"

    # 2. 동시 요청 충돌 -> 409 SESSION_BUSY JSON
    session_id = str(uuid.uuid4())
    asyncio.run(session_manager.acquire(session_id))
    try:
        resp_busy = client.post(
            "/api/chat/stream",
            json={"sessionId": session_id, "messageId": str(uuid.uuid4()), "message": "동시 요청"}
        )
        assert resp_busy.status_code == 409
        assert resp_busy.headers["content-type"] == "application/json"
        assert resp_busy.json()["error"]["code"] == "SESSION_BUSY"
    finally:
        asyncio.run(session_manager.release(session_id))

    # 3. 스트림 초기화 직전 Gemini 429 오류 발생 -> 429 UPSTREAM_QUOTA JSON
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content_stream = MagicMock(
            side_effect=errors.APIError(code=429, response_json={"error": {"code": 429, "message": "Quota exceeded"}})
        )

        resp_quota = client.post(
            "/api/chat/stream",
            json={"sessionId": str(uuid.uuid4()), "messageId": str(uuid.uuid4()), "message": "할당량 초과"}
        )
        assert resp_quota.status_code == 429
        assert resp_quota.headers["content-type"] == "application/json"
        assert resp_quota.json()["error"]["code"] == "UPSTREAM_QUOTA"
