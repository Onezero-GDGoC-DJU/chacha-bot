# backend

chacha-bot의 API 서버입니다. Python **FastAPI**와 **Uvicorn** 기반으로 구축되어 있습니다.

---

## 1. 기술 스택

- **언어**: Python 3.11+
- **웹 프레임워크**: FastAPI
- **ASGI 서버**: Uvicorn
- **설정 관리**: Pydantic Settings / python-dotenv
- **LLM 연동**: Google Gemini API (`google-genai`, 예정)
- **컨테이너**: Docker

---

## 2. 디렉토리 구조

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 앱 인스턴스, 라이프사이클 및 라우터 등록
│   ├── config.py        # 환경변수 로드 및 설정 (Pydantic Settings)
│   └── api/
│       ├── __init__.py
│       └── health.py    # 헬스 체크 엔드포인트 (GET /api/health)
├── prompts/
│   └── system.md        # 시스템 프롬프트 (PR로만 수정)
├── .dockerignore        # 도커 빌드 제외 설정
├── Dockerfile           # 백엔드 컨테이너 빌드 파일
├── README.md            # 백엔드 가이드 문서
└── requirements.txt     # 파이썬 패키지 의존성 목록
```

---

## 3. 사전 요구사항

- Python 3.11 이상
- (선택) Docker

---

## 4. 로컬 실행 방법

### 4.1 가상환경 생성 및 활성화

**Windows (PowerShell):**
```powershell
# 프로젝트 루트 또는 backend 디렉토리에서 실행
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 4.2 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 4.3 환경변수 설정

프로젝트 루트의 `.env.example` 파일을 복사하여 `.env` 파일을 생성하고 필요한 값을 입력합니다.

```bash
# 프로젝트 루트에서 실행하는 경우
copy .env.example .env    # Windows
# cp .env.example .env    # macOS / Linux
```

> [!WARNING]
> `.env` 파일에는 Gemini API Key 등 민감한 정보가 포함되므로 **절대 git에 커밋하지 마세요.** (.gitignore 처리됨)

### 4.4 개발 서버 실행

```bash
# backend 디렉토리에서 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 실행 주소: `http://localhost:8000`
- API 문서 (Swagger UI): `http://localhost:8000/docs`
- 헬스 체크: `http://localhost:8000/api/health`

---

## 5. Docker 컨테이너 실행 방법

Docker를 사용하면 로컬에 파이썬을 설치하지 않고도 동일한 환경에서 서버를 구동할 수 있습니다.

### 5.1 Docker 이미지 빌드

```bash
# backend 디렉토리 기준
docker build -t chacha-backend .
```

### 5.2 Docker 컨테이너 실행

```bash
# 환경변수 파일(.env)을 주입하여 컨테이너 실행
docker run -d \
  --name chacha-backend \
  -p 8000:8000 \
  --env-file ../.env \
  chacha-backend
```

### 5.3 컨테이너 상태 및 로그 확인

```bash
# 컨테이너 상태 확인
docker ps

# 로그 실시간 확인
docker logs -f chacha-backend
```

---

## 6. API 확인 (헬스 체크)

서버가 정상적으로 구동 중인지 아래 명령어로 확인합니다.

```bash
curl -X GET http://localhost:8000/api/health
```

**응답 (HTTP 200):**
```json
{"status":"ok"}
```

---

## 7. 자동화 테스트 실행 (pytest)

`pytest`를 사용하여 작성된 헬스 체크 단위 테스트를 실행합니다.

```bash
# backend 디렉토리 기준
pytest
```

**테스트 항목:**
- `test_health_check_returns_200`: `GET /api/health` 호출 시 HTTP 200 및 `{"status": "ok"}` 반환 여부 검증 (명세서 B8 완료 조건)
- `test_root_endpoint`: 루트 경로 메타데이터 반환 검증

