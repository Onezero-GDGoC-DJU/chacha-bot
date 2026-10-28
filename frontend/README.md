# frontend

웹 클라이언트. **아직 스택이 정해지지 않았어요.**

## 정해야 할 것
- [ ] 프레임워크 (예: 순수 HTML/JS, React, Svelte, Vue …)
- [ ] 빌드 도구·패키지 매니저
- [ ] 마크다운 렌더러 (AI 답변용)
- [ ] 배포 위치

## 이미 정해진 것
- 화면과 스타일은 [design/](../design/)을 따라요. `tokens.css`와 `components.css`를 그대로 가져다 써요.
- 세션 ID는 첫 실행 때 만들어 브라우저에 저장하고, 클라이언트마다 세션은 하나예요.
- AI 답변은 스트리밍으로 받아 이어 붙여요. 상태와 동작은 [design/spec.md](../design/spec.md)를 보세요.
