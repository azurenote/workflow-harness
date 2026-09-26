<!-- Referenced from skills/SKILL-CONFIG.md. 이 문서는 SKILL-CONFIG.md 에서 갈라져
     나온 것이 아니라 새로 쓴 참조다. harness 명령의 종료코드를 읽고 분기하는 스킬이
     이 경로를 읽는다. 그 스킬이 말할 때만 읽는다. -->

# harness 종료코드 (`harness_core.exitcodes.ExitCode`)

harness 의 모든 명령은 아래 열거형의 값으로 끝난다. 이 표가 **정본**이다 — 명령의 docstring 과 스킬 본문은 열거형 이름을 쓰고 이 문서를 가리킨다. 표를 다른 곳에 옮겨 적지 않는다. `tests/test_exitcodes.py` 가 이 표와 열거형, 그리고 각 명령이 실제로 반환하는 이름을 대조한다.

## 열거형

| 값 | 이름 | 뜻 | 호출자 |
|---|---|---|---|
| 0 | `OK` | 완료. 읽기면 판정이 완결됐다 | 진행 |
| 1 | `CRASH` | 처리되지 않은 예외. **어느 명령도 의도적으로 쓰지 않는다** | 멈추고 보고한다(버그) |
| 2 | `REFUSED` | 부작용 전 거부: 사용법·검증·전제조건 | 입력을 고쳐 다시 실행해도 안전하다 |
| 3 | `INCOMPLETE` | 일부만 됐다. 쓰기는 복구가 필요하고, 읽기는 판정이 불완전하다. stdout 에 한 일이 있다 | 성공으로 취급하지 않는다 |
| 4 | `UNKNOWN` | 쓰기의 결과를 모른다 | 확인하기 전에는 다시 실행하지 않는다 |
| 5 | `NOOP` | 이미 되어 있어 할 일이 없다 | 성공으로 취급한다 |
| 6 | `FINDINGS` | 판정은 완결됐고, 호출자가 실패로 지정한 결과가 있다 | 게이트 실패 |

- 1 을 크래시 전용으로 두는 이유: 파이썬 트레이스백은 항상 1 로 끝난다. 1 에 다른 뜻을 주면 크래시와 구별할 수 없다. 그래서 린터 관례("발견 = 1") 대신 6 을 쓴다.
- 사용법 오류(argparse: 모르는 인자, 빠진 인자, `type=` 검증 실패)는 **모든 명령**에서 `REFUSED` 다. 아래 표는 그 밖의 경우를 적는다.
- `REFUSED` 에는 트래커·저장소 **읽기 실패**도 든다(`get-issue`·`set-fields`·`audit-fields`). 쓰기 전에 멈춘 것이라 다시 실행해도 안전하지만, 고칠 것은 입력이 아니라 읽기를 막은 원인(권한·네트워크)이다.

## 명령별

| 명령 | 이름 | 이 명령에서의 뜻 |
|---|---|---|
| `find-draft-plan` | `OK` · `REFUSED` | `REFUSED`: 초안이 없거나 여럿이거나 main checkout 을 해석하지 못했다. stderr 한 줄이 셋을 가른다 |
| `rename-plan` | `OK` · `REFUSED` | `REFUSED`: 초안 검증 실패, `plan-<id>.md` 가 이미 있음, main checkout 해석 불가. 파일은 그대로다 |
| `plan-file` | `OK` · `REFUSED` | `REFUSED`: `plan-<id>.md` 가 없거나 main checkout 을 해석하지 못했다 |
| `get-base` | `OK` · `REFUSED` | 플랜이 없으면 `OK` 에 두 값 `null`. `REFUSED`: main checkout 해석 불가 |
| `create-branch` | `OK` | git 실패는 처리하지 않은 예외로 올라간다(`CRASH`) |
| `create-worktree` | `OK` · `REFUSED` | `REFUSED`: main checkout 해석 불가. git 실패는 `CRASH` |
| `push-branch` | `OK` | git 실패는 `CRASH` |
| `clean-up` | `OK` · `REFUSED` | `REFUSED`: main checkout 해석 불가 |
| `create-issue` | `OK` · `REFUSED` · `INCOMPLETE` · `UNKNOWN` | `REFUSED`: 만들기 전에 거부했고 stdout 이 비었다. `INCOMPLETE`: 이슈는 생겼고 메타데이터가 불완전하다 — stdout 의 번호로 `set-fields` 를 부른다. `UNKNOWN`: 생성 요청이 이슈가 생겼는지 말하지 않고 실패했다 — 제목으로 검색하기 전에는 다시 만들지 않는다 |
| `get-issue` | `OK` · `REFUSED` | `REFUSED`: 이슈나 그 메타데이터를 읽지 못했다 — 입력이 아니라 읽기가 실패한 것이라, 원인(권한·네트워크)을 확인하고 다시 실행한다. 아무것도 쓰지 않았으므로 다시 실행해도 안전하다 |
| `set-fields` | `OK` · `REFUSED` · `INCOMPLETE` | `REFUSED`: 첫 쓰기 전에 거부했다. `INCOMPLETE`: 첫 쓰기 뒤에 실패했다 — stdout 에 적용된 것이 있다 |
| `audit-fields` | `OK` · `REFUSED` · `INCOMPLETE` · `FINDINGS` | `OK`: 모든 축을 읽었다(drift 가 있어도, `--fail-on-drift` 가 없으면). `REFUSED`: 이슈 목록을 읽지 못했다, stdout 이 비었다. `INCOMPLETE`: 읽지 못한 축이 있다 — `warnings` 가 이름을 댄다. `FINDINGS`: `--fail-on-drift` 이고 drift 가 1건 이상이다 |
| `plan_body` | `OK` · `REFUSED` · `NOOP` | `python -m harness_core.plan_body`. `REFUSED`: 플랜이 없거나 이름·위치가 틀림, id·rev 불일치, 인코딩이 UTF-8 이 아니거나 빈 파일, 요약도 한도를 넘음, 트래커 읽기 파일을 읽지 못함, main checkout 해석 불가. `NOOP`: 같은 내용이 이미 트래커에 있다(`SEEN=`) |
| `scaffold` | `OK` · `REFUSED` | `harness-init`·`harness-update`. `REFUSED`: 프리플라이트 실패 또는 `error:` 경고 — 파일을 쓰기 전에 돌아온다 |
| board 스텁 | `REFUSED` | 프로젝트 소유(`project.py` 템플릿의 fail-closed 선택지), 코드 검사 밖. 설정이 없어 명령을 쓸 수 없다는 이유를 출력한다 |

## `--fail-on-drift` 의 우선순위

`audit-fields --fail-on-drift` 에서 판정이 불완전한 것(`INCOMPLETE`)과 drift 가 확인된 것(`FINDINGS`)이 함께 성립하면 **`FINDINGS` 가 이긴다**. `INCOMPLETE` 를 허용하도록 설정한 CI(권한이 부족한 토큰 등)에서 이미 확인된 drift 가 가려지면 안 되기 때문이다. 불완전하다는 사실은 JSON 의 `warnings` 에 그대로 남는다. 플래그는 출력(JSON)을 바꾸지 않고 종료코드만 바꾼다.
