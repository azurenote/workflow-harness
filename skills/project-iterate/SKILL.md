---
name: project-iterate
description: Run the one-stop workflow: project-plan -> project-issue -> project-start -> project-done. Includes user confirmation between each phase.
---

# project-iterate - One-stop Workflow

## Trigger Conditions

Apply this skill in the following situations:
- The user invokes `project-iterate <task description>`, or asks to use the project-iterate skill for <task description>
- The user invokes `project-iterate <id>` for an issue that already exists, with or without a plan
- Keywords such as "from start to finish", "one-stop", or "iterate"
- The user wants to go from plan writing to PR in one flow

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

This skill needs no reference beyond the common contract.

## Output Language Guard

Generated workflow artifacts remain Korean by default even though the workflow `SKILL.md` files are written in English:
- `project-plan` writes plan prose, requirements, DoD, task cards, and validation notes in Korean.
- `project-adr` writes ADR documents in Korean.
- `project-done` writes the impl-report / issue-report body in Korean.

Do not translate these artifacts to English while moving between phases unless the user explicitly requests English output for the artifact itself.

## Usage

```
project-iterate <task description> [worktree] [adr]
project-iterate <id> [worktree] [adr]
```

- `<task description>`: task description (required for a new run)
- `<id>`: an issue that already exists — re-entry, including an issue that has no plan yet (see below)
- `[worktree]`: branch in worktree mode
- `[adr]`: include ADR writing, passed to both start and done

## Re-entry After Interruption

Re-entry must explicitly provide an issue ID in the form `project-iterate <id>`.
- Without `<id>`, always start a new run from Phase 1 (Plan).
- `<id>` is a GitHub or Forgejo issue number, or a Jira ticket ID.

With `<id>`, check these states in this order and continue from the first one that matches:

| State | Signal | Check Method | Continue from |
|-------|--------|--------------|---------------|
| Done | PR exists or issue status is "In Review" | `gh pr list --head <branch-name>` | nothing left — report it |
| Branch, no plan | branch/worktree for `<id>` exists, `plan-<id>.md` does not | the two checks below | stop and report |
| Start | branch/worktree for `<id>` exists and `plan-<id>.md` exists | the two checks below | Phase 4 |
| Issue | `plan-<id>.md` exists, no branch/worktree | the plan check below | Phase 3 |
| Issue only | none of the above | — | Phase 1 from the issue body, then Phase 2 in link mode |

The branch check matches the whole id segment of the branch names `project-start` creates —
`git branch -a | grep <id>` would let `2` match `issue-25`:

```bash
git branch -a --list "*issue-<id>-*" "*/<id>-*"
```

The plan check is rooted at the main worktree: `.task/plan/` is gitignored and exists only there, so a
check relative to the CWD reports every plan as missing from a linked worktree. `<harness_cli> plan-file
<id>` does the same for an integer id; it parses the id as an integer, so use this form for a Jira key:

```bash
python -c '
import re, sys
from harness_core.git import main_worktree_root
if not re.fullmatch(r"[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*", sys.argv[1]):
    sys.exit("reject (id): not an issue number or ticket key: %r" % sys.argv[1])
plan = main_worktree_root() / ".task" / "plan" / ("plan-%s.md" % sys.argv[1])
sys.exit(0 if plan.is_file() else "no plan: %s" % plan)
' '<id>'
```

- `<id>` 가 주어졌을 때 `plan-<id>.md` 가 없으면 초안이 있어도 Plan 완료로 판정하지 않는다 — 초안에는 이슈 번호가 없어서, 거기 있는 초안은 다른 어떤 작업의 것이어도 된다.
- 브랜치/워크트리는 있는데 `plan-<id>.md` 가 없으면 멈추고 사용자에게 보고한다. `project-start` 는 플랜 없이는 브랜치를 만들지 않으므로(Step 1-A) 이 상태는 손으로 만든 브랜치나 옛 실행에서만 나온다. Phase 4 로 넘겨도 `project-done` 이 플랜이 없어 멈춘다.

## Instructions

This skill calls four global skills in sequence.
For each phase's detailed procedure, follow that skill document (`~/.claude/skills/<name>/SKILL.md`).

---

### Phase 1: Plan

1. Extract the task description from `$ARGUMENTS` (excluding `worktree` and `adr` keywords).
   - In the "Issue only" re-entry state, the task description is the issue body instead. Read it with the read command in `project-issue` Step 1-L and judge it by that step's content rule; do not write a tracker command here.
   - If that read fails or the content rule rejects it (closed, another number, a pull request), stop and report it before writing any plan.
   - 기존 초안이 있으면 목록을 보여 주고, 사용자가 그중 하나를 이 이슈의 플랜으로 명시적으로 고를 때만 그 경로를 Phase 2 에 넘긴다. 고르지 않으면 이슈 본문으로 새 초안을 쓴다 — 초안 소유를 추측하지 않는다.
2. Run the `plan` skill procedure:
   - analyze the codebase
   - create `plan-draft-<slug>.md`
   - write the human layer (`Intent Summary`, `Current State`, `Target State`, `Non-Goals`, `Drift Guards`) and agent layer (`Implementation Contract`, `Task Cards`, `Validation Plan`)
   - **write a detailed DoD** because `project-done` later uses it as the verification standard
   - review the plan according to `Review Profile` policy
3. **User confirmation**: show the plan summary and get approval.
   - Confirm first that the Intent Summary and base branch are correct.
   - If changes are requested, apply them and confirm again.
   - On approval, continue to Phase 2.

---

### Phase 2: Issue

1. Run the `issue` skill procedure:
   - Phase 1 이 방금 만든 플랜 경로를 `project-issue` 에 위치 인자로 그대로 넘긴다. 경로는 이미 알려져 있으므로 자동 탐색을 다시 돌리지 않는다 — 초안이 여럿이면 그 탐색은 자기가 만든 파일조차 고르지 못하고 멈춘다.
   - `## Re-entry After Interruption` 의 "Issue only" 상태에서 왔다면 새 이슈를 만들지 않고 `project-issue <plan-path> --issue <id>` 로 연결 모드를 부른다 — 이슈가 이미 있는데 생성 모드로 부르면 같은 작업의 티켓이 둘이 된다.
   - register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as an issue-tracker ticket (link mode: attach it to `<id>` instead)
   - rename the draft plan to `plan-<id>.md`
2. Print the issue ID / ticket URL, then automatically continue to Phase 3.

---

### Phase 3: Start + Implementation

1. Run the `start` skill procedure with the issue ID from Phase 2:
   - pass the `worktree` argument when applicable
   - pass the `adr` argument when applicable, to write an ADR before implementation
   - read the Intent Summary and Drift Guards
   - print the Task Cards checklist and start implementation
   - review the implementation according to `Review Profile` policy
2. **User confirmation**: show the implementation result summary and get approval.
   - If changes are requested, apply them and confirm again.
   - On approval, continue to Phase 4.

---

### Phase 4: Done

1. Run the `done` skill procedure with the issue ID from Phase 2:
   - pass the `adr` argument when applicable
   - verify the DoD
   - write the impl-report
   - commit -> push -> create PR, or merge for Jira
   - set issue status to "In Review"
2. Print the final result (commit hash, PR URL).

---

## Preserved State After Interruption

| Interruption Point | Preserved Artifact |
|-----------|------------|
| after Phase 1 | `plan-draft-<slug>.md` or existing `plan-<uuid>.md` |
| after Phase 2 | issue ticket + `plan-<id>.md` |
| after Phase 3 | above + implementation code (uncommitted) |
| after Phase 4 complete | above + commit + PR + issue comment |

To resume after interruption, call the relevant skill directly:
- From Phase 2: `project-issue <plan-path>`, or `project-issue <plan-path> --issue <id>` when the issue already exists. Always name the path: discovery without it can pick up a draft that belongs to other work.
- From Phase 3: `project-start <id>`
- From Phase 4: `project-done <id>`
