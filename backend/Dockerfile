# ==============================================================================
# chacha-bot 백엔드 Dockerfile
#
# Base Image: Python 3.11 slim (가볍고 보안상 안전한 공식 경량 이미지)
# ==============================================================================
FROM python:3.11-slim

# 파이썬 표준 출력 버퍼링 비활성화 (로그 즉시 출력) 및 .pyc 바이트코드 생성 방지
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 컨테이너 내 작업 디렉토리 설정
WORKDIR /app

# Docker 헬스체크 및 네트워크 디버깅을 위한 curl 패키지 설치
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Docker 레이어 캐싱을 위해 의존성 목록 파일을 먼저 복사하여 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 코드 및 프롬프트 파일 복사
COPY app/ ./app/
COPY prompts/ ./prompts/

# 백엔드 서버 기본 포트 (I1 명세서: backend 포트 8000)
EXPOSE 8000

# 컨테이너 헬스체크 설정 (B8 명세서: GET /api/health 활용)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Uvicorn ASGI 서버 구동
# 0.0.0.0으로 바인딩하여 Docker 네트워크 및 nginx 리버스 프록시 요청을 수신
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
