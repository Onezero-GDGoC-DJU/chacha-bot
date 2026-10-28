# backend

API 서버. **아직 스택이 정해지지 않았어요.**

## 정해야 할 것
- [ ] 언어·프레임워크 (예: Node + Express/Fastify/Hono, Python + FastAPI …)
- [ ] LLM 제공사와 모델
- [ ] 대화 이력 저장소 (예: SQLite, PostgreSQL)
- [ ] 맥락 전달 방식 (최근 N턴 슬라이딩 윈도우부터 시작 예정)
- [ ] 배포 위치

## 이미 정해진 것
- 클라이언트는 `sessionId`와 새 메시지만 보내고, 이력은 서버가 저장하고 조회해요.
- 응답은 스트리밍(SSE)으로 보내요.
- API 키 같은 비밀값은 `.env`에만 두고 **절대 커밋하지 않아요**(이 레포는 public이에요).
