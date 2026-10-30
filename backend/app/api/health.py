"""
헬스 체크 API 모듈 (health.py)

명세서 B8 규격을 따르는 헬스 체크 엔드포인트입니다.
- 경로: GET /api/health
- 응답: HTTP 200 {"status": "ok"}
- 목적: Docker Compose의 healthcheck 및 로드밸런서의 가동 상태 확인용
- 주의: Gemini API는 호출하지 않음 (할당량 절약)
"""

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """
    헬스 체크 응답 스키마
    명세서 B8: {"status": "ok"}
    """
    status: str = "ok"


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="서버 가동 상태(헬스 체크) 확인",
    description="서버가 정상적으로 동작 중인지 확인합니다. Gemini API는 호출하지 않습니다 (명세서 B8)."
)
async def check_health() -> HealthResponse:
    """
    서버 헬스 체크 핸들러

    [명세서 B8 규칙]
    1. GET /api/health 요청 시 200 {"status": "ok"}를 반환합니다.
    2. 데이터베이스 연결 상태를 점검할 수 있으며, Gemini API는 호출하지 않습니다.
    3. Docker Compose의 healthcheck 및 컨테이너 오케스트레이션에서 사용됩니다.
    """
    # 추후 이슈 3(저장소) 구현 시, DB 연결 상태를 확인하는 로직이 여기에 추가될 수 있습니다.
    # 예: await check_db_connection()
    
    return HealthResponse(status="ok")
