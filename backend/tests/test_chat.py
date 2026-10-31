"""
메시지 전송 및 Gemini 연동 API 단위 테스트 (test_chat.py)

이슈 7번 완료 조건 및 리뷰 반영 전수 검증:
1. 정상 요청에 200 과 AI 메시지를 돌려주고 두 메시지가 저장된다.
2. 같은 messageId 로 다시 보내도 사용자 메시지가 중복 저장되지 않는다 (재시도 지원).
3. 같은 세션에서 동시에 보내면 409 SESSION_BUSY.
4. 최근 CONTEXT_TURNS 턴만 맥락에 들어간다 (답 없는 실패 요청 제외).
5. Gemini 429·5xx·시간 초과·안전 차단이 4장의 코드로 바뀐다 (SDK Client 레벨 모킹으로 검증).
6. 실패하면 AI 메시지는 저장되지 않는다.
7. RequestValidationError 발생 시 422 대신 400 INVALID_REQUEST 반환.
"""

import uuid
import sqlite3
import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import aiosqlite
from google.genai import errors

from app.main import app
from app.config import settings
from app.db.database import get_db_path
from app.db.repository import MessageRepository
from app.services.session_manager import session_manager
from app.services.chat_service import (
    ChatServiceError,
    build_context_contents
)


def make_mock_response(text: str = "테스트 답변", finish_reason: str = "STOP", block_reason: str = None):
    """
    Gemini API generate_content 응답을 흉내내는 모의(Mock) 응답 객체 생성
    """
    mock_resp = MagicMock()
    mock_resp.text = text
    if block_reason:
        mock_feedback = MagicMock()
        mock_feedback.block_reason = block_reason
        mock_resp.prompt_feedback = mock_feedback
    else:
        mock_resp.prompt_feedback = None

    mock_candidate = MagicMock()
    mock_candidate.finish_reason = finish_reason
    mock_resp.candidates = [mock_candidate]
    return mock_resp


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    각 테스트마다 격리된 임시 SQLite DB를 사용하는 fixture (개발/운영 DB 오염 방지)
    """
    temp_db_file = tmp_path / "chat_test.db"
    monkeypatch.setattr(settings, "database_path", str(temp_db_file))

    with TestClient(app) as test_client:
        yield test_client


def test_post_chat_success_and_saves_both_messages(client):
    """
    [완료 조건 1]
    정상 요청에 200과 AI 메시지를 돌려주고 사용자/AI 두 메시지가 모두 DB에 저장된다.
    SDK 호출(google.genai.Client)을 모킹하여 call_gemini 내부 로직까지 실제 검증한다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    user_msg_text = "안녕? 반가워"
    ai_reply_text = "안녕! 나는 chacha야 ㅋㅋ 무엇을 도와줄까?"

    mock_resp = make_mock_response(text=ai_reply_text, finish_reason="STOP")

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

        response = client.post(
            "/api/chat",
            json={
                "sessionId": session_id,
                "messageId": message_id,
                "message": user_msg_text
            }
        )

    # 1. HTTP 200 응답 및 JSON 본문 검증
    assert response.status_code == 200, f"예상 코드는 200이지만 {response.status_code}를 받았습니다."
    data = response.json()
    assert "message" in data
    ai_msg = data["message"]
    assert ai_msg["role"] == "assistant"
    assert ai_msg["content"] == ai_reply_text
    assert ai_msg["replyTo"] == message_id
    assert ai_msg["status"] == "done"

    # 2. DB에 사용자/AI 메시지 2건 모두 정상 저장되었는지 검증
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, status, reply_to FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC;",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2, f"두 개의 메시지가 저장되어야 하지만 {len(rows)}개가 저장되었습니다."
    # 사용자 메시지 검증
    assert rows[0][0] == message_id
    assert rows[0][1] == "user"
    assert rows[0][2] == user_msg_text
    assert rows[0][4] is None

    # AI 메시지 검증
    assert rows[1][0] == ai_msg["id"]
    assert rows[1][1] == "assistant"
    assert rows[1][2] == ai_reply_text
    assert rows[1][4] == message_id


def test_post_chat_duplicate_message_id_retry_does_not_duplicate_user_message(client):
    """
    [완료 조건 2 & 리뷰 반영 3]
    같은 messageId로 재시도 요청을 보내도 사용자 메시지가 중복 저장되지 않으며,
    재시도 시 DB에 처음 저장된 내용이 유지된다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # 1. 첫 번째 시도: Gemini 호출 중 500 API 오류 발생 (사용자 메시지만 DB에 저장됨)
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=errors.APIError(code=500, response_json={"error": {"code": 500, "message": "Server Error"}})
        )
        resp1 = client.post(
            "/api/chat",
            json={"sessionId": session_id, "messageId": message_id, "message": "처음 전송한 질문"}
        )
        assert resp1.status_code == 502

    # 2. 두 번째 시도: 같은 messageId로 재시도 요청 (클라이언트가 메시지를 바꿨더라도 DB의 원래 내용 사용) -> 성공
    mock_resp = make_mock_response(text="재시도 성공 답변입니다.", finish_reason="STOP")
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        resp2 = client.post(
            "/api/chat",
            json={"sessionId": session_id, "messageId": message_id, "message": "수정한 질문"}
        )
        assert resp2.status_code == 200

    # 3. DB 확인: 사용자 메시지는 1개만 존재해야 하고, 내용은 처음 저장한 '처음 전송한 질문'이어야 함
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, role, content FROM messages WHERE session_id = ? AND role = 'user';", (session_id,))
    user_rows = cursor.fetchall()
    conn.close()

    assert len(user_rows) == 1, f"사용자 메시지가 1개여야 하지만 {len(user_rows)}개가 저장되었습니다."
    assert user_rows[0][2] == "처음 전송한 질문", "재시도 시 처음 저장된 사용자 메시지 내용이 유지되어야 합니다."


def test_post_chat_already_answered_returns_409(client):
    """
    [명세서 B1 규칙]
    이미 답변이 완료된 사용자 메시지를 동일한 messageId로 다시 요청하면 409 ALREADY_ANSWERED를 반환한다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    mock_resp = make_mock_response(text="첫 번째 답변 완료", finish_reason="STOP")
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

        resp1 = client.post(
            "/api/chat",
            json={"sessionId": session_id, "messageId": message_id, "message": "질문"}
        )
        assert resp1.status_code == 200

    # 2. 동일한 messageId로 중복 전송 시도
    resp2 = client.post(
        "/api/chat",
        json={"sessionId": session_id, "messageId": message_id, "message": "질문"}
    )
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error"]["code"] == "ALREADY_ANSWERED"


def test_post_chat_concurrent_request_returns_409_session_busy(client):
    """
    [완료 조건 3]
    같은 세션에서 동시에 보내면 409 SESSION_BUSY를 반환한다.
    """
    session_id = str(uuid.uuid4())

    # 세션 락을 인위적으로 획득하여 '답변 생성 중' 시뮬레이션
    asyncio.run(session_manager.acquire(session_id))

    try:
        response = client.post(
            "/api/chat",
            json={
                "sessionId": session_id,
                "messageId": str(uuid.uuid4()),
                "message": "동시 요청"
            }
        )
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "SESSION_BUSY"
        assert "이전 답변이 아직 끝나지 않았어요" in data["error"]["message"]
    finally:
        asyncio.run(session_manager.release(session_id))


def test_post_chat_context_includes_only_recent_n_turns_and_excludes_failed_msg(client):
    """
    [완료 조건 4]
    최근 CONTEXT_TURNS 턴만 맥락에 들어가고, 답이 없는 실패한 사용자 요청은 맥락에서 제외된다 (명세서 B4).
    """
    session_id = str(uuid.uuid4())
    db_path = get_db_path()
    base_time = datetime(2026, 10, 30, 10, 0, 0, tzinfo=timezone.utc)

    # 12턴(총 24개 메시지)의 정상 대화 + 1개의 답 없는 실패 요청을 DB에 직접 삽입
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 12턴(24개) 정상 대화 등록
    for i in range(12):
        u_id = f"u-{i}"
        a_id = f"a-{i}"
        t_user = (base_time + timedelta(seconds=i*2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        t_ai = (base_time + timedelta(seconds=i*2 + 1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        # user 메시지
        cursor.execute(
            "INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (u_id, session_id, "user", f"질문 {i}", "done", None, t_user)
        )
        # ai 메시지
        cursor.execute(
            "INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (a_id, session_id, "assistant", f"답변 {i}", "done", u_id, t_ai)
        )

    # 답이 없는 실패한 사용자 메시지 1개 삽입 (t=25초)
    t_failed = (base_time + timedelta(seconds=25)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    cursor.execute(
        "INSERT INTO messages (id, session_id, role, content, status, reply_to, created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
        ("failed-user-id", session_id, "user", "실패한 질문 (답변 없음)", "done", None, t_failed)
    )
    conn.commit()
    conn.close()

    # 이번 메시지로 맥락 구성 실행
    async def _check():
        async with aiosqlite.connect(db_path) as aio_db:
            aio_db.row_factory = aiosqlite.Row
            contents = await build_context_contents(
                db=aio_db,
                session_id=session_id,
                current_message_id="current-msg-id",
                current_message="이번 질문"
            )
            return contents

    contents = asyncio.run(_check())

    # 검증:
    # 1. 답이 없는 'failed-user-id'는 제외되어야 함
    for item in contents:
        assert item["parts"][0]["text"] != "실패한 질문 (답변 없음)", "답이 없는 사용자 메시지는 맥락에서 제외되어야 합니다."

    # 2. 최근 10턴(최대 20개 메시지) + 이번 메시지 1개 = 총 21개 메시지여야 함 (12턴 중 앞의 2턴은 슬라이싱되어 제외)
    assert len(contents) == 21, f"맥락 메시지 수는 21개여야 하지만 {len(contents)}개입니다."

    # 3. 가장 오래된 포함 메시지는 질문 2여야 함 (0, 1은 제외됨)
    assert contents[0]["parts"][0]["text"] == "질문 2"
    assert contents[-1]["parts"][0]["text"] == "이번 질문"


def test_post_chat_gemini_error_mapping_to_spec(client):
    """
    [완료 조건 5 & 리뷰 반영 1 & 2]
    call_gemini 내부의 SDK(google.genai.Client)를 모킹하여,
    Gemini 429, 5xx, 시간 초과, 안전/콘텐츠 차단(SAFETY, PROHIBITED_CONTENT 등), 빈 답변이
    명세서 4장의 코드로 정확히 변환되는지 실제 에러 판별 로직을 검증한다.
    """
    session_id = str(uuid.uuid4())

    cases = [
        # (mock_outcome, expected_status, expected_code)
        (errors.APIError(code=429, response_json={"error": {"code": 429, "message": "Quota exceeded"}}), 429, "UPSTREAM_QUOTA"),
        (errors.APIError(code=500, response_json={"error": {"code": 500, "message": "Internal error"}}), 502, "UPSTREAM_ERROR"),
        (errors.APIError(code=503, response_json={"error": {"code": 503, "message": "Service unavailable"}}), 502, "UPSTREAM_ERROR"),
        (asyncio.TimeoutError(), 504, "UPSTREAM_TIMEOUT"),
        (make_mock_response(text="", finish_reason="SAFETY"), 422, "BLOCKED"),
        (make_mock_response(text="", finish_reason="PROHIBITED_CONTENT"), 422, "BLOCKED"),
        (make_mock_response(text="", finish_reason="BLOCKLIST"), 422, "BLOCKED"),
        (make_mock_response(text="", finish_reason="SPII"), 422, "BLOCKED"),
        (make_mock_response(text="", finish_reason="STOP"), 502, "UPSTREAM_ERROR"),  # 빈 답변
        (make_mock_response(text="   ", finish_reason="STOP"), 502, "UPSTREAM_ERROR"), # 공백 답변
    ]

    for outcome, exp_status, exp_code in cases:
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            if isinstance(outcome, Exception):
                mock_client.aio.models.generate_content = AsyncMock(side_effect=outcome)
            else:
                mock_client.aio.models.generate_content = AsyncMock(return_value=outcome)

            msg_id = str(uuid.uuid4())
            resp = client.post(
                "/api/chat",
                json={"sessionId": session_id, "messageId": msg_id, "message": "에러 변환 검증 질문"}
            )
            assert resp.status_code == exp_status, f"{exp_code}의 상태 코드는 {exp_status}여야 하지만 {resp.status_code}를 받았습니다."
            data = resp.json()
            assert data["error"]["code"] == exp_code, f"에러 코드는 {exp_code}여야 하지만 {data['error']['code']}를 받았습니다."


def test_post_chat_failure_does_not_save_ai_message(client):
    """
    [완료 조건 6]
    실패하면 AI 메시지는 DB에 저장되지 않는다.
    """
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # 타임아웃 오류 시뮬레이션
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(side_effect=asyncio.TimeoutError())
        resp = client.post(
            "/api/chat",
            json={"sessionId": session_id, "messageId": message_id, "message": "타임아웃 발생 테스트"}
        )
        assert resp.status_code == 504

    # DB 확인: 사용자 메시지만 1개 남아있어야 하고, AI 메시지는 없어야 함
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM messages WHERE session_id = ?;", (session_id,))
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1, "사용자 메시지만 1개 저장되어야 합니다."
    assert rows[0][0] == "user", "저장된 메시지는 user 역할이어야 합니다."


def test_request_validation_error_returns_400_invalid_request(client):
    """
    [리뷰 반영 3]
    FastAPI의 RequestValidationError(누락된 필드, 잘못된 타입 등) 발생 시
    422(BLOCKED로 오인 가능)가 아닌 400 INVALID_REQUEST가 반환된다.
    """
    session_id = str(uuid.uuid4())

    # 1. message 필드가 숫자인 경우
    resp1 = client.post(
        "/api/chat",
        json={"sessionId": session_id, "messageId": str(uuid.uuid4()), "message": 12345}
    )
    assert resp1.status_code == 400
    data1 = resp1.json()
    assert data1["error"]["code"] == "INVALID_REQUEST"
    assert data1["error"]["message"] == "요청을 처리할 수 없어요."

    # 2. 필수 필드가 누락된 경우
    resp2 = client.post(
        "/api/chat",
        json={"sessionId": session_id}
    )
    assert resp2.status_code == 400
    data2 = resp2.json()
    assert data2["error"]["code"] == "INVALID_REQUEST"
