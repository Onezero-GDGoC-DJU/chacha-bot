# frontend

Vite + React로 만든 chacha 채팅 화면이에요.

전체(nginx + 백엔드)를 한 번에 띄우는 방법은 [루트 README](../README.md#실행-방법)를 보세요. 이 문서는 화면을 고치면서 개발 서버로 띄우는 방법이에요.

## 필요한 것

- Node.js 20.19 이상 또는 22.12 이상 (Vite 8 기준). `node --version`으로 확인해요.
- **백엔드가 8000번 포트에서 실행 중**이어야 해요. `vite.config.js`가 `/api` 요청을 `http://localhost:8000`으로 넘겨요. 백엔드 실행은 [backend/README.md](../backend/README.md)를 보세요.
  - 백엔드 없이 띄우면 "대화를 불러오지 못했어요."가 보이는 게 정상이에요.

## 실행 방법

저장소 루트 폴더에서:

```powershell
cd frontend
npm install
npm run dev
```

http://localhost:5173 에 접속해요. 코드를 저장하면 화면이 바로 바뀌어요.

| 명령 | 하는 일 |
|---|---|
| `npm run dev` | 개발 서버 실행 |
| `npm run lint` | 코드 검사 (PR 올리기 전에 실행해요) |
| `npm run build` | 배포용 파일을 `dist/`에 만들기 |
| `npm run preview` | 만든 `dist/`를 미리 보기 |

## 파일 구성

```
src/
├─ main.jsx        앱 시작점
├─ App.jsx         화면 상태, 메시지 전송·다시 시도, 스크롤, 입력창
├─ Markdown.jsx    AI 답변 마크다운 표시, 코드 블록 복사
├─ time.js         시간 구분선 규칙과 표시 형식
├─ tokens.css      디자인 토큰 (design/tokens.css와 같아요)
├─ components.css  컴포넌트 스타일 (design/components.css와 같아요)
└─ App.css         디자인 CSS에 없는 앱 전용 스타일
```

- `tokens.css`와 `components.css`는 `design/` 폴더의 파일을 복사한 거예요. 고칠 때는 두 곳을 함께 고쳐요.
- AI 답변은 `react-markdown`으로 표시해요. 보안을 위해 원본 HTML을 그리지 않으니 **`rehype-raw`는 추가하지 마세요.**
