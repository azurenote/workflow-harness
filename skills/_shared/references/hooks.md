<!-- Split out of skills/SKILL-CONFIG.md. Every skill used to read the whole
     config document at startup, including the parts that did not apply to it.
     Read this file only when the skill says it needs it. -->

# 훅 실행

설정에 `hooks` 키가 있으면 lifecycle 포인트마다 커맨드를 실행한다.

#### 포인트

| 포인트 | 스킬 · 위치 | 실패 처리 |
|--------|------------|-----------|
| `post_start` | `project-start` Step 6(구현 시작) 직전 | 경고 후 계속 |
| `pre_commit` | `project-start` Step 7(커밋 직전 포맷) | 경고 후 계속 |
| `pre_done` | `project-done` Step 3(ADR) 직전 — 모든 커밋 이전 | **중단** |
| `post_done` | `project-done` Step 9(이슈 코멘트) 직후 | 경고 후 계속 |

#### 실행 규칙

- `hooks.<point>` 키 없음 · 값이 `~`(null) · 값이 `""` → 조용히 skip
- 단일 문자열: Bash에 그대로 전달
- YAML literal block (`|`): 전체를 단일 Bash 호출로 전달 (여러 줄이 하나의 shell 세션에서 실행됨)
- `pre_done` 실패 시: 훅 실패 출력을 사용자에게 보고하고 절차를 중단한다. 이후 Step은 실행하지 않는다.
- `post_start` / `pre_commit` / `post_done` 실패 시: 경고 출력 후 계속 진행한다.
- `pre_commit` 이 **경고 후 계속**인 이유: 포맷은 정확성 게이트가 아니고, 커밋 이전의
  차단 게이트는 `pre_done` 이 이미 맡고 있다. 포매터 하나가 죽었다고 절차 전체를
  세우지 않는다.
- 공유 스킬에는 어떤 언어의 포맷 명령도 넣지 않는다. Rust 포맷 명령을 뺀 자리에
  다른 언어 상수를 넣는 것은 같은 실수를 이름만 바꿔 반복하는 것이다.
- CWD: 프로젝트 루트 (워크트리 사용 시 워크트리 루트)

#### YAML 예시

```yaml
hooks:
  pre_commit: <프로젝트의 포맷 명령>
  pre_done: cargo dylint --all -- -p backend
  post_done: |
    echo "build ok"
    .claude/scripts/notify.sh
```
