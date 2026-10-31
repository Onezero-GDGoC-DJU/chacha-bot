# chacha-bot

**[2026.10.28] 미니 프로젝트**

Gemini API 를 사용한 간단한 AI 챗봇 **chacha-bot**

## 저장소 구조

```
chacha-bot/
├─ frontend/   웹 클라이언트
├─ backend/    API 서버
├─ design/     디자인 토큰·컴포넌트 CSS·아이콘·핸드오프 문서
├─ nginx/      nginx 설정 (화면 제공, /api 프록시, 속도 제한)
├─ docs/       결정 기록 등 프로젝트 문서
├─ .github/    Issue·PR 템플릿
└─ docker-compose.yaml   전체 실행 설정
```

## 실행 방법

[Docker Desktop](https://www.docker.com/products/docker-desktop/)을 켜 두고, 저장소 루트에서 실행해요.

1. 환경변수 파일을 만들고 `GEMINI_API_KEY`를 입력해요. `.env`는 커밋되지 않아요.
   ```powershell
   copy .env.example .env
   ```
2. 이미지를 빌드하고 실행해요. 처음에는 빌드하느라 몇 분 걸려요.
   ```powershell
   docker compose up --build -d
   ```
3. http://localhost 에 접속해요. `docker compose ps`에서 `backend`가 `(healthy)`면 정상이에요.

| 하고 싶은 것 | 명령 |
|---|---|
| 로그 보기 | `docker compose logs -f` |
| 끄기 (대화 이력은 남아요) | `docker compose down` |
| 끄고 대화 이력까지 지우기 | `docker compose down -v` |

- `.env`가 없으면 실행되지 않아요.
- 백엔드 포트(8000)는 외부에 열지 않아요. API는 http://localhost/api/... 로만 호출해요.
- backend만 다시 만든 뒤 `/api` 요청이 502로 실패하면 `docker compose restart nginx`를 실행해요.
- 프론트·백엔드를 각각 개발 서버로 띄우는 방법은 [frontend/README.md](frontend/README.md), [backend/README.md](backend/README.md)를 보세요.

## 개발 방식

- Issue를 먼저 만들고, 이슈마다 브랜치를 따서 PR로 `main`에 합쳐요(GitHub Flow).
- `main`에는 직접 push할 수 없어요. 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.

## 디자인

- Figma: [AI Chat – Dark](https://www.figma.com/design/ZWjMLY2hTleWgMPiLdY0zM)
- 핸드오프 문서: [design/spec.md](design/spec.md)
