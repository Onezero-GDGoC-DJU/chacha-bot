# 기여 규칙

소규모 단기 프로젝트라서 규칙은 최소한으로 둬요.

## 흐름 (GitHub Flow)

```
Issue 생성 → 브랜치 생성 → 커밋 → PR → (리뷰) → main에 Squash merge → 브랜치 자동 삭제
```

1. **Issue 만들기**: 템플릿(기능 / 버그 / 작업)을 골라 작성해요.
2. **브랜치 만들기**: 최신 `main`에서 이슈 번호를 넣어 만들어요.
   ```bash
   git switch main && git pull
   git switch -c feat/12-chat-input
   ```
3. **PR 올리기**: 본문에 `Closes #12`를 적으면 머지할 때 이슈가 자동으로 닫혀요.
4. **머지**: Squash merge만 허용해요. PR 하나가 `main`의 커밋 하나가 돼요.

## 브랜치 이름

`<타입>/<이슈번호>-<짧은-설명>`

| 타입 | 용도 | 예시 |
|---|---|---|
| `feat` | 새 기능 | `feat/12-chat-input` |
| `fix` | 버그 수정 | `fix/20-scroll-jump` |
| `docs` | 문서 | `docs/7-api-spec` |
| `design` | 디자인 토큰·스타일 | `design/9-bubble-width` |
| `chore` | 설정·빌드·의존성 | `chore/3-setup-lint` |

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/) 형식에, 범위(scope)로 폴더를 적어요.

```
feat(frontend): 메시지 입력창 추가
fix(backend): 스트리밍 중단 시 연결 정리
docs: README 구조 설명 보강
```

Squash merge를 쓰니까 **PR 제목**이 최종 커밋 메시지가 돼요. PR 제목도 같은 형식으로 써 주세요.

## main 보호 규칙

| 규칙 | 내용 |
|---|---|
| 직접 push | 금지. 반드시 PR로 합쳐요. |
| 강제 push (`--force`) | 금지 |
| 브랜치 삭제 | 금지 |
| 예외(bypass) | 조직 Owner는 위 규칙을 모두 우회할 수 있어요(긴급 수정·히스토리 정리용). |

규칙은 GitHub 레포의 **Settings → Rules → Rulesets → `main protection`**에서 바꿀 수 있어요.
