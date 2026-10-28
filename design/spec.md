# AI Chat (Dark) — 디자인 핸드오프

- **Figma**: [AI Chat – Dark](https://www.figma.com/design/ZWjMLY2hTleWgMPiLdY0zM)
  - `Screens` 페이지: Desktop 1440×900 / Mobile 390×844 × 상태 6개
  - `Components` 페이지: 컴포넌트 원본과 변형(variant)
- **코드 기준 파일**
  - [tokens.css](tokens.css): Figma Variables와 1:1로 대응하는 CSS 변수
  - [components.css](components.css): 컴포넌트 기본 스타일 (프레임워크 무관)
  - [icons/](icons/): 아이콘 SVG 5개 (`currentColor` 사용)
  - [preview.html](preview.html): 위 CSS로 만든 정적 미리보기. `#empty` `#loading` `#conversation` `#waiting` `#streaming` `#error` 해시로 상태 전환

> `preview.html`은 CSS가 상대 경로라서 파일을 직접 열면 스타일이 빠져요. 로컬 서버로 여세요.
> 예: `python -m http.server 5180 --directory design` → http://localhost:5180/preview.html

---

## 1. 범위

- 기능은 **채팅 보내기·보기** 하나뿐이에요.
- 세션 ID는 클라이언트 첫 실행 때 만들어 저장하고, 화면에는 보여주지 않아요.
- 세션 목록, 새 대화, 사이드바 같은 세션 관련 UI는 **없어요**.
- 다크 테마 하나만 있어요(`color-scheme: dark`).

## 2. 레이아웃

```
┌ Header (56px, 모바일 52px) ─────────────── 서비스명만 표시
├ Body (남은 높이, 세로 스크롤) ───────────── .chat-body
│   └ Thread (최대 768px, 가운데 정렬) ────── .chat-thread
│       메시지 사이 간격 24px
└ Footer (하단 고정) ─────────────────────── .chat-footer
    Composer (최대 768px) + 안내 문구
```

| 항목 | Desktop | Mobile (≤ 640px) |
|---|---|---|
| 좌우 여백 (`--page-gutter`) | 24px | 16px |
| 헤더 높이 (`--header-height`) | 56px | 52px |
| 스레드 폭 | 최대 768px | 화면 폭 − 32px |
| 사용자 말풍선 최대 폭 (`--bubble-max`) | 스레드의 70% | 스레드의 85% |

- 메시지가 적을 때는 스레드를 **아래쪽에 붙여요**(입력창 바로 위). 메시지가 많아지면 일반 스크롤이에요.
- 모바일은 `100dvh`와 `env(safe-area-inset-bottom)`으로 주소창과 홈 인디케이터를 피해요.

## 3. 화면 상태

| # | 상태 | Thread | Composer | 진입 조건 |
|---|---|---|---|---|
| 1 | Empty | `EmptyState` 세로 가운데 | Empty | 저장된 메시지 0개 |
| 2 | Loading history | `Skeleton/Message` × 2~3, 위쪽 정렬 | Empty | 첫 진입 시 이력 조회 중 |
| 3 | Conversation | 시간 구분선 + 메시지들 | Empty / Typing | 기본 |
| 4 | Waiting | … + 사용자 메시지 + `TypingIndicator` | **Responding** | 전송 후 첫 토큰 도착 전 |
| 5 | Streaming | … + AI 답변(끝에 커서) | **Responding** | 토큰 수신 중 |
| 6 | Response error | … + 사용자 메시지 + `Message/Error` | Empty | 요청 실패 또는 스트림 중단 |

상태 전이: `Conversation → (전송) → Waiting → (첫 토큰) → Streaming → (완료) → Conversation`
실패하면 `Waiting/Streaming → Response error`, 다시 시도하면 `Response error → Waiting`.

## 4. 컴포넌트 ↔ CSS 대응

| Figma 컴포넌트 | 변형 | CSS 클래스 |
|---|---|---|
| Header | — | `.chat-header`, `.chat-header__title` |
| TimeDivider | — | `.time-divider` |
| EmptyState | — | `.empty-state`, `__title`, `__description` |
| Message/User | Size=Desktop/Mobile | `.msg-user`, `.msg-user__bubble` |
| MD/Paragraph · MD/Heading · MD/List Item | — | `.msg-ai p`, `.msg-ai h1~h3`, `.msg-ai ol/ul li` |
| MD/Code Block | — | `.code-block`, `__header`, `__copy`, `pre` |
| (스트리밍 커서) | — | `.msg-ai--streaming` |
| TypingIndicator | — | `.typing-indicator > span × 3` |
| Message/Error | — | `.msg-error`, `__icon`, `__text`, `.btn-retry` |
| Skeleton/Message | Size=Desktop/Mobile | `.skeleton`, `__bubble`, `__lines`, `__line` |
| Composer | State=Empty/Typing/Multiline/Responding | `.composer`, `.composer__input` |
| SendButton | State=Disabled/Active/Stop | `.send-button` (`:disabled`, 아이콘 교체) |
| icon/* | arrow-up, stop, refresh, alert, copy | `icons/*.svg` |

Figma에서 `Composer`의 Typing·Multiline 상태 테두리는 CSS의 `:focus-within`에 해당하고, Empty와 Responding은 기본 테두리예요.

## 5. 동작 규칙

### 입력창 (Composer)
- **Enter**는 전송, **Shift+Enter**는 줄바꿈이에요.
- **한글 IME 주의**: 조합 중 Enter를 전송으로 처리하지 않아야 해요(`event.isComposing` 또는 `keyCode === 229`이면 무시). 처리하지 않으면 마지막 글자가 중복 전송돼요.
- 내용에 따라 높이가 늘어나고, 최대 200px(`--composer-max-height`)을 넘으면 내부 스크롤이에요. `field-sizing: content`를 지원하지 않는 브라우저에서는 JS로 `scrollHeight`를 반영해요.
- 공백만 입력됐으면 전송 버튼은 Disabled예요.
- 전송하면 입력창을 비우고 포커스를 유지해요.

### 전송 버튼 (SendButton)
| 상태 | 조건 | 아이콘 | `aria-label` |
|---|---|---|---|
| Disabled | 입력 없음 | arrow-up (회색) | 보내기 |
| Active | 입력 있음 | arrow-up (흰색) | 보내기 |
| Stop | AI 응답 중 | stop | 응답 중지 |

- AI 응답 중에도 입력은 할 수 있지만, 전송 대신 **중지**만 가능해요. 중지하면 `AbortController`로 요청을 끊고, 받은 데까지 답변을 남겨요.

### 메시지
- 사용자 메시지는 `white-space: pre-wrap`으로 입력한 줄바꿈을 유지해요.
- AI 답변은 마크다운으로 렌더링해요(문단, 제목, 목록, 굵게, 링크, 인라인 코드, 코드 블록, 인용, 표, 구분선).
- 한글 줄바꿈은 `word-break: keep-all`로 해요. Figma는 글자 단위로 줄을 바꿔서 화면과 조금 다를 수 있어요.
- 코드 블록은 줄바꿈 대신 가로 스크롤이에요. 복사를 누르면 라벨이 "복사됨"으로 1.5초 바뀌어요.
- 시간 구분선은 대화의 첫 메시지 위, 그리고 이전 메시지와 30분 이상 차이 날 때 넣어요.

### 스트리밍
- 첫 토큰이 오기 전에는 `TypingIndicator`, 토큰이 오면 AI 답변으로 교체해요.
- 스트리밍 중에는 `.msg-ai`에 `--streaming`을 붙여 마지막 블록 끝에 커서를 보여주고, 완료되면 떼요.
- 사용자가 맨 아래 근처(약 80px 이내)를 보고 있을 때만 자동으로 따라 스크롤해요.

### 오류
- 실패한 답변 자리에 `Message/Error`를 보여줘요. "다시 시도"는 같은 사용자 메시지로 다시 요청해요.

## 6. 접근성
- 스레드에 `role="log"`와 `aria-live="polite"`를 줘요. 스트리밍 중인 답변에는 `aria-busy="true"`를 붙여 토큰마다 읽히지 않게 해요.
- 오류 블록은 `role="alert"`이에요.
- 아이콘만 있는 버튼에는 `aria-label`을 줘요.
- 대비: 본문 `#ECECEC`/`#000`, 말풍선 `#FFF`/`#1B3A73`, 보조 텍스트 `#8E8E93`/`#000`(약 6:1)은 모두 WCAG AA(4.5:1)를 충족해요.
- **알려진 한계**: `--color-text-tertiary`(#6E6E73)는 입력창 배경(#1A1A1C) 위에서 약 3.4:1이라 AA에 못 미쳐요. 그래서 입력창 placeholder에만 써요. 엄격하게 맞추려면 `gray/500`을 `#838389` 정도로 올려야 해요(이 경우 보조 텍스트와 구분이 약해져요).
- `prefers-reduced-motion`이면 애니메이션을 꺼요.

## 7. 폰트
- 본문은 **Noto Sans KR**(400/500/700), 코드는 **JetBrains Mono**예요(Google Fonts).
- Pretendard는 Figma에 없어서 쓰지 않았어요. 바꾸려면 `--font-sans` 맨 앞에 넣고, Figma의 `font/family/sans` 변수도 같이 바꿔요.
- 코드 블록은 `font-variant-ligatures: none`이라서 `>=`가 `≥`로 합쳐지지 않아요(Figma 화면은 합쳐져 보여요).

## 8. 토큰 이름 규칙
Figma 변수 `color/bg/base`는 CSS `--color-bg-base`예요(슬래시를 하이픈으로). 변수마다 Figma의 Code syntax(WEB)에 `var(--...)`를 넣어 두어서, Dev Mode에서도 CSS 변수명이 그대로 보여요.
