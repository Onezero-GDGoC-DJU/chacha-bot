"""
헬스 체크 API 및 서버 시작 검증 테스트 (test_health.py)

명세서 B8 규격 검증:
1. GET /api/health 요청 시 HTTP 상태 코드 200 반환
2. 응답 JSON 본문이 {"status": "ok"}인지 확인

명세서 B3 시스템 프롬프트 사전 점검 검증:
3. 시스템 프롬프트(system.md) 파일이 없거나 비어 있으면 서버 시작 시 RuntimeError 발생
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


@pytest.fixture
def client():
    """
    FastAPI TestClient fixture
    
    [중요]
    TestClient(app)을 단순히 호출하면 lifespan(서버 시작 단계)이 실행되지 않습니다.
    'with TestClient(app) as client:' 구문으로 감싸야 lifespan이 동작하여
    서버 시작 시의 시스템 프롬프트 검증 및 초기화 로직이 정상 실행됩니다.
    """
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_returns_200(client):
    """
    [완료 조건 검증]
    GET /api/health 호출 시 200 {"status": "ok"}를 반환해야 한다.
    """
    response = client.get("/api/health")

    # 1. 상태 코드 검증 (HTTP 200 OK)
    assert response.status_code == 200, f"예상 상태 코드는 200이지만 {response.status_code}를 받았습니다."

    # 2. 응답 JSON 데이터 검증 ({"status": "ok"})
    data = response.json()
    assert data == {"status": "ok"}, f"예상 응답은 {{'status': 'ok'}}이지만 {data}를 받았습니다."


def test_root_endpoint(client):
    """
    루트(/) 접속 시 기본 메타 정보 JSON 반환 검증
    """
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "healthCheck" in data
    assert data["healthCheck"] == "/api/health"


def test_lifespan_fails_when_system_prompt_missing(monkeypatch, tmp_path):
    """
    [명세서 B3 검증]
    system.md 파일이 존재하지 않는 경우 서버 시작 시 RuntimeError가 발생해야 한다.
    """
    # 존재하지 않는 가상의 경로로 설정 변경
    non_existent_path = tmp_path / "prompts" / "non_existent_system.md"
    monkeypatch.setattr(settings, "system_prompt_path", non_existent_path)

    # with TestClient(app) 구문으로 lifespan 실행 시 RuntimeError 발생 여부 검증
    with pytest.raises(RuntimeError, match="시스템 프롬프트 파일을 찾을 수 없습니다"):
        with TestClient(app):
            pass


def test_lifespan_fails_when_system_prompt_empty(monkeypatch, tmp_path):
    """
    [명세서 B3 검증]
    system.md 파일 내용이 비어 있는 경우 서버 시작 시 RuntimeError가 발생해야 한다.
    """
    # 비어 있는 가상의 system.md 파일 생성
    empty_prompt_file = tmp_path / "system.md"
    empty_prompt_file.write_text("   \n   ", encoding="utf-8")
    monkeypatch.setattr(settings, "system_prompt_path", empty_prompt_file)

    # with TestClient(app) 구문으로 lifespan 실행 시 RuntimeError 발생 여부 검증
    with pytest.raises(RuntimeError, match="시스템 프롬프트 파일이 비어 있습니다"):
        with TestClient(app):
            pass
