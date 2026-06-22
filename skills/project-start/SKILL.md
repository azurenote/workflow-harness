---
name: project-start
description: 이슈 번호를 받아 브랜치(또는 worktree)를 생성하고, 이슈 상태를 In Progress로 전환한 뒤 플랜 Intent Summary, Drift Guards, Task Cards를 숙지하고 구현을 시작한다. Codex에서는 `$project-start ...` 또는 "project-start 스킬로 ..." 요청 시 실행.
---

# project-start — 작업 시작

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- Codex에서 `$project-start <issue-id>` 또는 "project-start 스킬로 <issue-id> 시작" 형태로 요청할 때
- `#<숫자>` 또는 이슈 ID + "시작", "착수", "구현", "브랜치" 키워드
- `$project-issue` 완료 직후 "시작하자"는 사용자 의도

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## 실행 안전 규칙

- Markdown 백틱이 포함된 이슈 코멘트는 셸에서 명령 치환으로 해석되지 않도록 최종 본문을 단일 인자로 전달한다.
  - 권장:
    ```bash
    .claude/scripts/harness_cli.py add-comment 123 'ADR recorded: `docs/adr/example.md`'
    ```
  - 금지: 백틱이 들어간 본문을 따옴표 없이 쓰거나, escaping 없이 double quote 안에 넣는 방식
- Codex에서 GitHub API를 호출하는 `harness_cli.py`, `project.py`, `gh` 명령이 네트워크/sandbox 오류로 실패하면 즉시 `require_escalated`로 같은 명령을 재실행한다.
- Codex에서 에이전트 팀 리뷰를 수행할 때는 셸 명령으로 별도 `codex`/`claude` 프로세스를 실행하지 않는다.
  - `multi_agent_v1.spawn_agent` 도구가 노출되어 있고 사용자 요청 또는 스킬 절차가 에이전트 팀 리뷰를 요구하는 경우에만 해당 도구로 서브에이전트를 생성한다.
  - 서브에이전트 도구가 없거나 권한 문제로 실패하면, 메인 에이전트가 아래 3개 관점을 분리된 적대적 리뷰 패스로 직접 수행한다.
  - 리뷰 방식이 fallback 되었음을 최종 보고에 명시한다.

### Claude Code 실행 규칙

Codex 전용 메커니즘 대신 다음을 적용한다:

- **`require_escalated` 없음**: GitHub API 호출(`harness_cli.py`, `gh`)이 실패하면 fallback 경로로 재시도하고, 그래도 실패하면 사용자에게 보고하고 중단한다.
- **셸로 LLM 프로세스 spawn 금지**: `codex`, `claude` 등을 셸 명령으로 실행하지 않는다 (Codex와 동일 원칙).
- **서브에이전트**: `multi_agent_v1.spawn_agent` 대신 `Agent` 툴로 서브에이전트를 생성한다.
- **서브에이전트 불필요 시**: 메인 에이전트가 3개 관점을 순서대로 직접 리뷰한다 (fallback 방식과 동일).

## Usage

```
$project-start <issue-id> [worktree] [adr]
```

- `<issue-id>`: GitHub 이슈 번호 또는 Jira 티켓 ID (필수)
- `[worktree]`: git worktree 모드
- `[adr]`: 구현 전 ADR 작성 (`$project-adr` 내부 호출)

## Instructions

**1. 이슈 정보 조회 및 브랜치명 도출**

`harness_enabled: true`:
```bash
<harness_cli> get-issue <issue-id>
```

`harness_enabled: false` (GitHub):
```bash
gh issue view <issue-id> --json title,id,labels
```

Jira:
```bash
jira issue view <ticket-id>
```

출력에서 `title`, `node_id`(GitHub) / 티켓 ID(Jira), 브랜치명을 획득한다.
브랜치명 규칙: `feat/issue-<id>-<slug>` (GitHub) / `feat/<ticket-id>-<slug>` (Jira)

**1-B. base branch 판독 (frontmatter — 추론 없음)**

플랜 frontmatter 가 선언한 base 를 읽는다. `/start` 는 base 를 **추론하지 않고** 이 값만 따른다.

```bash
<harness_cli> get-base <issue-id>    # {"base_branch": "<branch>" | null, "parent_issue": <num> | null}
```

여기서 **"프로젝트 기본 base"** = "설정 읽기"에서 읽은 `skill-config.yaml` 의 `base_branch`(enseed-trader=`develop`, cosmos-forge=`main`). 리터럴 `develop` 으로 비교하지 말 것 — 이 스킬은 여러 프로젝트가 공유한다.

- `base_branch` 가 **non-null 이고 프로젝트 기본 base 와 다르면** → 그 브랜치가 PR 리뷰·머지 타겟이자 분기 base 다. 아래 2-A/2-B 에서 `--base-ref "<base_branch>"` 로 전달한다.
- `null` 또는 프로젝트 기본 base 와 같으면 → `--base-ref` 없이 **기존 동작**(현재 HEAD 에서 분기; 기본 base 위에서 시작한다는 가정 유지). 신규 프롬프트 없음.
- harness 없을 때 fallback: 플랜 파일 `.task/plan/plan-<issue-id>.md` 선두 frontmatter 의 `base_branch:` 줄을 직접 확인한다(없으면 프로젝트 기본 base).

**2-A. 일반 브랜치 (기본)**

```bash
# base 선언 있을 때
<harness_cli> create-branch "<branch-name>" --base-ref "<base_branch>"
# base 미선언(develop)일 때
<harness_cli> create-branch "<branch-name>"
# fallback(선언): git fetch origin "<base_branch>" 2>/dev/null; git checkout --no-track -b "<branch-name>" "<base_branch | origin/base_branch>"
# fallback(미선언): git checkout -b "<branch-name>"
```

브랜치 push는 `$project-done` 단계에서 수행한다. 여기서는 push하지 않는다.

**2-B. Worktree 모드 (`worktree` 인자 있을 때)**

```bash
# base 선언 있을 때
<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>" --base-ref "<base_branch>"
# base 미선언(develop)일 때
<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>"
# fallback: git worktree add [--no-track] ".claude/worktrees/<project>-issue-<id>" -b "<branch-name>" ["<base_branch | origin/base_branch>"]
```

이후 모든 작업은 `$WORKTREE_PATH` 안에서 수행한다.

**2-C. 탭 이름 설정**

```bash
cmux rename-tab "task #<id>" 2>/dev/null || true
```

**3. 이슈 상태 → In Progress**

```bash
<harness_cli> add-progress "<node-id>" --issue-number <id> --branch-name "<branch-name>"
# fallback(GitHub): gh issue edit <id> --add-label "in-progress" 2>/dev/null || true
# fallback(Jira):   jira issue move <ticket-id> "In Progress"
```

**4. ADR (조건부)**

`adr` 인자가 있으면 `$project-adr <issue-id>` 절차를 실행한다.
이때 위 "실행 안전 규칙"을 유지한다. 특히 ADR 경로를 이슈 코멘트에 게시할 때 Markdown 백틱을 셸 명령 치환으로 노출하지 않는다.
ADR 커밋이 완료된 후에만 구현을 시작한다.

**5. 플랜 로드**

`.task/plan/plan-<issue-id>.md` 를 읽는다. 파일이 로컬에 없고 이슈 본문 접근이 가능하면 이슈 본문에 올라간 plan을 같은 기준으로 읽는다.

구현 전에 다음 순서로 숙지한다:

1. `Intent Summary`: 무엇을 바꾸고 왜 필요한지.
2. `Current State` / `Target State`: 현재 동작과 완료 후 상태.
3. `Non-Goals`: 이번 작업에서 하지 않는 것.
4. `Drift Guards`: 위험한 오해와 범위 이탈 금지사항.
5. `Requirements`와 `Definition of Done`: 검증 가능한 요구사항.
6. `Implementation Contract`와 `Task Cards`: 파일/모듈, 계약, 완료 조건, 검증 방법.

구형 plan에 `Task Cards`가 없고 `Task Breakdown`만 있으면 후자를 실행 단위로 사용하되, 가능한 범위에서 Requirements/DoD와 대조해 drift를 막는다.

**5-H. `post_start` 훅 (있을 때만)**

`.claude/skill-config.yaml`의 `hooks.post_start` 값이 있으면 Bash로 실행한다.
실패해도 경고만 출력하고 계속 진행한다. (`SKILL-CONFIG.md` "훅 실행" 참조)

**6. 구현 시작**

Intent Summary와 Drift Guards를 먼저 요약한 뒤, `Task Cards`를 체크리스트로 출력하고 Task 1을 즉시 시작한다.
추가 지시를 기다리지 않는다.

**7. 커밋 전 포매팅**

구현이 완료되면 커밋 전에 반드시 실행한다:

```bash
cargo fmt --all
```

**8. 에이전트 팀 코드 리뷰**

작업 완료 판단 시, 아래 3개 관점의 적대적 리뷰를 수행한다. 목표는 승인이 아니라 결함 발견이다.

Codex 실행 규칙:
- 우선 `multi_agent_v1.spawn_agent` 도구가 사용 가능하면 3개 독립 서브에이전트로 병렬 리뷰를 위임한다.
- 셸 명령으로 `codex`, `claude`, 기타 LLM CLI를 실행하여 서브에이전트를 만들지 않는다. sandbox 권한 실패가 반복되는 경로다.
- 서브에이전트 도구가 없거나 실패하면 중단하지 말고, 메인 에이전트가 세 관점을 순서대로 분리해서 리뷰한다.

Claude Code 실행 규칙:
- `Agent` 툴이 사용 가능하면 3개 독립 서브에이전트로 병렬 리뷰를 위임한다.
- 셸 명령으로 `codex`, `claude` 등 LLM CLI를 실행하지 않는다 (Codex와 동일 원칙).
- 서브에이전트 없이 진행할 때는 메인 에이전트가 세 관점을 순서대로 분리해서 리뷰한다.

리뷰 관점:
- **설계자**: 아키텍처 적합성, 기존 패턴 일관성, Scope 준수
- **구현자**: 로직 오류, 보안, 엣지케이스
- **테스트 엔지니어**: 테스트 누락, DoD 충족 여부

각 리뷰는 파일/라인 근거가 있는 findings 중심으로 출력한다. 피드백을 취합하여 즉시 수정 반영하고, 수정 후 필요한 검증을 다시 실행한다.
최종 보고에는 리뷰 수행 방식(`subagents` 또는 `main-agent fallback`)과 반영한 지적사항을 요약한다.
