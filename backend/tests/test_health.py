"""
헬스 체크 API 테스트 (test_health.py)

명세서 B8 규격 검증:
1. GET /api/health 요청 시 HTTP 상태 코드 200 반환
2. 응답 JSON 본문이 {"status": "ok"}인지 확인
"""

from fastapi.testclient import TestClient
from app.main import app

# FastAPI 테스트 클라이언트 초기화
client = TestClient(app)


def test_health_check_returns_200():
    """
    [완료 조건 검증]
    GET /api/health 호출 시 200 {"status": "ok"}를 반환해야 한다.
    """
    # GET /api/health 요청 전송
    response = client.get("/api/health")

    # 1. 상태 코드 검증 (HTTP 200 OK)
    assert response.status_code == 200, f"예상 상태 코드는 200이지만 {response.status_code}를 받았습니다."

    # 2. 응답 JSON 데이터 검증 ({"status": "ok"})
    data = response.json()
    assert data == {"status": "ok"}, f"예상 응답은 {{'status': 'ok'}}이지만 {data}를 받았습니다."


def test_root_endpoint():
    """
    루트(/) 접속 시 기본 메타 정보 JSON 반환 검증
    """
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "healthCheck" in data
    assert data["healthCheck"] == "/api/health"
