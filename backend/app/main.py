"""
메인 애플리케이션 진입점 (main.py)

FastAPI 애플리케이션 인스턴스를 생성하고 생명주기 이벤트 및 라우터를 등록합니다.
- 명세서 4장: API 경로는 모두 /api로 시작
- 명세서 B8: GET /api/health 제공
- 명세서 2.1 & B3: 서버 구동 시 backend/prompts/system.md 파일 유효성 검증
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.db.database import init_db

# 로깅 기본 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("chacha-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 수명 주기(Lifecycle) 핸들러
    
    서버 시작 시:
    - 시스템 프롬프트 파일(backend/prompts/system.md) 존재 및 유효성 검사 (명세서 B3)
    - 환경 설정 로그 출력
    
    서버 종료 시:
    - 리소스 정리
    """
    logger.info("=== chacha-bot 백엔드 서버를 시작합니다 ===")
    logger.info(f"바인딩 주소: http://{settings.host}:{settings.port}")
    logger.info(f"Gemini 모델: {settings.gemini_model}")
    logger.info(f"최근 맥락 턴 수: {settings.context_turns}턴")
    logger.info(f"최대 메시지 글자 수: {settings.max_message_chars}자")

    # [명세서 B3 규칙 사전 점검]
    # 시스템 프롬프트 파일이 없거나 비어 있으면 서버 시작 실패 처리 (명세서 B3: 서버가 시작하지 않아야 함)
    prompt_path = settings.system_prompt_path
    if not prompt_path.exists():
        raise RuntimeError(f"시스템 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")

    content = prompt_path.read_text(encoding="utf-8").strip()
    if not content:
        raise RuntimeError(f"시스템 프롬프트 파일이 비어 있습니다: {prompt_path}")

    logger.info(f"시스템 프롬프트 로드 완료: {prompt_path} ({len(content)}자)")

    # [명세서 B5 완료 조건]
    # 서버 시작 시 messages 테이블이 없으면 생성
    await init_db()

    yield  # 애플리케이션 가동

    logger.info("=== chacha-bot 백엔드 서버를 종료합니다 ===")


# FastAPI 애플리케이션 인스턴스 초기화
app = FastAPI(
    title="chacha-bot API",
    description="Gemini API를 사용한 간단한 AI 챗봇 chacha의 백엔드 API 서버입니다.",
    version="0.1.0",
    docs_url="/docs",       # Swagger UI 문서
    redoc_url="/redoc",     # ReDoc 문서
    lifespan=lifespan
)

# ------------------------------------------------------------------------------
# 라우터 등록
# 명세서 4장: 모든 API 경로는 '/api'로 시작합니다.
# ------------------------------------------------------------------------------
app.include_router(health_router, prefix="/api", tags=["Health"])
app.include_router(sessions_router, prefix="/api", tags=["Sessions"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])


@app.get("/", include_in_schema=False)
async def root_redirect():
    """
    루트(/) 접속 시 기본 안내 JSON 반환
    """
    return JSONResponse(
        content={
            "name": "chacha-bot API Server",
            "version": "0.1.0",
            "healthCheck": "/api/health",
            "documentation": "/docs"
        }
    )
