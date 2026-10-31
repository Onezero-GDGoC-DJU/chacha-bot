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

**필요한 것**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (켜 둔 상태)
- Gemini API 키: [Google AI Studio](https://aistudio.google.com/apikey)에서 발급해요.

저장소 루트에서 실행해요.

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

- 백엔드 포트(8000)는 외부에 열지 않아요. API는 http://localhost/api/... 로만 호출해요.
- 최신 `main`을 받은 뒤에는 `--build`를 붙여 다시 실행해야 바뀐 코드가 반영돼요.
- 프론트·백엔드를 각각 개발 서버로 띄우는 방법은 [frontend/README.md](frontend/README.md), [backend/README.md](backend/README.md)를 보세요.

## 시연 배포 (ngrok)

내 PC에서 실행 중인 chacha를 ngrok으로 인터넷에 공개해요. 주소는 HTTPS라서 다른 기기에서도 바로 접속할 수 있어요.

**처음 한 번만**

1. [ngrok 다운로드 페이지](https://ngrok.com/download)에서 설치해요(Windows는 Microsoft Store 버전이 간단해요). `winget install ngrok.ngrok`으로 설치했다면 버전이 오래되었을 수 있으니 `ngrok update`를 한 번 실행해요.
   ```powershell
   ngrok version
   ```
2. [ngrok 대시보드](https://dashboard.ngrok.com/get-started/your-authtoken)에서 authtoken을 복사해 등록해요. authtoken은 비밀번호와 같아서 저장소나 채팅에 올리면 안 돼요.
   ```powershell
   ngrok config add-authtoken <내-authtoken>
   ```

**시연할 때**

1. [실행 방법](#실행-방법)대로 띄우고 http://localhost 가 열리는지 확인해요.
2. 새 터미널에서 터널을 열어요.
   ```powershell
   ngrok http 80
   ```
3. 터미널의 `Forwarding` 줄에 나온 `https://….ngrok-free.dev` 주소를 공유해요.
4. 처음 접속하면 ngrok 안내 페이지("You are about to visit…")가 한 번 나와요. **Visit Site**를 누르면 chacha가 열려요.

**끝낼 때**

1. ngrok 터미널에서 `Ctrl + C`를 눌러 터널을 닫아요. 이때부터 주소로 접속할 수 없어요.
2. `docker compose down`으로 컨테이너를 꺼요. 대화 이력은 남아요.

**주의할 점**
- 이 PC, Docker Desktop, ngrok 터미널이 모두 켜져 있는 동안만 접속돼요. 절전 모드도 꺼 두세요.
- 주소를 아는 사람은 누구나 우리 Gemini 무료 할당량을 쓸 수 있어요. 시연하는 동안만 터널을 열어 두세요.
- 한 사람(IP)당 1분에 10번까지 보낼 수 있어요(연속 3번까지는 바로 허용). 넘으면 "요청이 많아요. 잠시 후 다시 시도해 주세요."가 보여요.

## 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `docker compose up`에서 `.env` 파일을 찾을 수 없다는 오류 | `.env`가 없어요 | `copy .env.example .env` 후 키를 입력해요 |
| `ports are not available` … `80` | 다른 프로그램이 80번 포트를 쓰고 있어요 | 그 프로그램을 끄거나, `docker-compose.yaml`의 `"80:80"`을 `"8080:80"`으로 바꾸고 http://localhost:8080 · `ngrok http 8080`으로 접속해요 |
| 화면은 뜨는데 항상 "답변을 받지 못했어요." | API 키가 비었거나 틀렸어요 | `.env`의 `GEMINI_API_KEY`를 고친 뒤 `docker compose up -d`, 이어서 `docker compose restart nginx` |
| `/api` 요청이 502로 실패 | backend가 아직 켜지는 중이거나, backend만 다시 만들어서 nginx가 옛 주소를 기억해요 | `docker compose ps`에서 `(healthy)`를 확인하고, 그래도 안 되면 `docker compose restart nginx` |
| "요청이 많아요" | 우리 속도 제한(1분 10번) 또는 Gemini 무료 할당량 초과 | 잠시 기다려요. `docker compose logs backend`에 `Gemini API 오류: 429`가 있으면 할당량 문제예요 |
| 바뀐 코드가 화면에 안 보여요 | 예전 이미지로 실행 중이에요 | `git pull` 후 `docker compose up --build -d`, 브라우저에서 `Ctrl + Shift + R` |
| ngrok `ERR_NGROK_4018` | authtoken을 등록하지 않았어요 | `ngrok config add-authtoken <내-authtoken>` |
| ngrok `ERR_NGROK_108` | 다른 곳에서 ngrok이 이미 실행 중이에요(무료는 동시에 1개) | 다른 ngrok 창을 닫고 다시 실행해요 |
| ngrok 주소로 들어가면 `ERR_NGROK_8012` | 터널은 열렸는데 chacha가 꺼져 있어요 | `docker compose up -d`로 먼저 띄워요 |

## 개발 방식

- Issue를 먼저 만들고, 이슈마다 브랜치를 따서 PR로 `main`에 합쳐요(GitHub Flow).
- `main`에는 직접 push할 수 없어요. 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.

## 디자인

- Figma: [AI Chat – Dark](https://www.figma.com/design/ZWjMLY2hTleWgMPiLdY0zM)
- 핸드오프 문서: [design/spec.md](design/spec.md)
