# backend

chacha-bot의 API 서버입니다. Python **FastAPI**와 **Uvicorn** 기반으로 구축되어 있습니다.

---

## 1. 기술 스택

- **언어**: Python 3.11+
- **웹 프레임워크**: FastAPI
- **ASGI 서버**: Uvicorn
- **설정 관리**: Pydantic Settings / python-dotenv
- **데이터베이스**: SQLite (`aiosqlite`)
- **LLM 연동**: Google Gemini API (`google-genai`, 예정)
- **컨테이너**: Docker

---

## 2. 디렉토리 구조

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 앱 인스턴스, 라이프사이클(DB 초기화) 및 라우터 등록
│   ├── config.py        # 환경변수 로드 및 설정 (Pydantic Settings)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py    # 헬스 체크 엔드포인트 (GET /api/health)
│   │   └── sessions.py  # 세션별 이력 조회 (GET /api/sessions/{sessionId}/messages)
│   └── db/
│       ├── __init__.py
│       ├── database.py  # SQLite 연결 및 messages 테이블 초기화
│       └── repository.py# 메시지 CRUD 및 최근 100개 시간순 조회
├── prompts/
│   └── system.md        # 시스템 프롬프트 (PR로만 수정)
├── tests/
│   ├── __init__.py
│   ├── test_health.py   # 헬스 체크 테스트
│   └── test_messages.py # 저장소 및 이력 조회 API 단위 테스트
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

## 6. API 엔드포인트 확인

### 6.1 헬스 체크
서버 및 DB 가동 상태를 확인합니다 (명세서 B8).
```bash
curl -X GET http://localhost:8000/api/health
```
**응답 (HTTP 200):**
```json
{"status":"ok"}
```

### 6.2 세션별 대화 이력 조회 (명세서 B2)
세션 ID의 최근 대화 이력을 시간순(오래된 것부터)으로 조회합니다.
```bash
curl -X GET http://localhost:8000/api/sessions/{sessionId}/messages
```
- 올바른 세션 ID: HTTP 200 `{"messages": [...]}`
- 메시지가 없는 세션: HTTP 200 `{"messages": []}`
- 유효하지 않은 UUID 형식: HTTP 400 `{"error": {"code": "INVALID_REQUEST", "message": "..."}}`

---

## 7. 자동화 테스트 실행 (pytest)

`pytest`를 사용하여 작성된 단위 테스트를 실행합니다.

```bash
# backend 디렉토리 기준
pytest
```

**테스트 항목:**
- `test_messages.py`:
  - `test_init_db_creates_messages_table`: 서버 구동 시 `messages` 테이블 및 인덱스 자동 생성 검증
  - `test_get_messages_invalid_session_id_returns_400`: 잘못된 세션 ID 형식 검증 (`400 INVALID_REQUEST`)
  - `test_get_messages_empty_session_returns_200_and_empty_list`: 빈 세션 조회 시 200 및 빈 리스트 반환 검증
  - `test_get_messages_returns_recent_100_in_chronological_order`: 최근 100개 메시지의 시간순 정렬 조회 검증
  - `test_get_messages_same_timestamp_orders_by_rowid`: 동일 시각 메시지의 rowid(seq) 안정 정렬 검증
- `test_health.py`:
  - `test_health_check_returns_200`: `GET /api/health` 헬스 체크 검증 (DB 연결 확인 포함)
  - `test_root_endpoint`: 루트 경로 메타데이터 반환 검증
  - `test_lifespan_fails_when_system_prompt_missing`: 시스템 프롬프트 부재 시 서버 구동 실패 검증 (명세서 B3)
  - `test_lifespan_fails_when_system_prompt_empty`: 시스템 프롬프트 내용 공백 시 서버 구동 실패 검증 (명세서 B3)
