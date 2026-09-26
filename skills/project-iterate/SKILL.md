---
name: project-iterate
description: Run the one-stop workflow: project-plan -> project-issue -> project-start -> project-done. Asks for plan approval; after it, asks only on a condition the skill lists under Questions After Plan Approval.
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
project-iterate <task description> [in-place] [adr]
project-iterate <id> [in-place] [adr]
```

- `<task description>`: task description (required for a new run)
- `<id>`: an issue that already exists — re-entry, including an issue that has no plan yet (see below)
- `[in-place]`: branch in the main checkout itself; Phase 3 calls `project-start <id> in-place`
- `[adr]`: include ADR writing, passed to both start and done

Branching defaults to a worktree: unless `in-place` is given, Phase 3 calls `project-start <id>`, whose default is a worktree.
The `worktree` token is accepted as an alias of that default and changes nothing; when it is given, say in one line that a worktree is already the default.

Argument rules:
- The first token decides the form: an issue number or a Jira key is the `<id>` form, and a flag (`in-place`, `worktree`, `adr`) as the first token is an error — stop and show the correct order.
- The `<id>` form is the id followed only by flags; if any other token follows the id, stop and ask whether this is a new run or a re-entry.
- A flag counts only as a standalone token at the end of `$ARGUMENTS`, in exact lowercase, in any order among the trailing tokens; the same word in the middle of the description is part of the description.
- A trailing token that is a near spelling of a flag (`--in-place`, `inplace`, `In-place`, `--worktree`) is not guessed — ask the user which was meant.
- `in-place` and `worktree` together are a conflict — stop and have the user pick one.

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
<id>` does the same for either id form, but only in a project that has a harness_cli; this form needs
only git, and runs as one shell call (the resolving lines are the canonical main-checkout block kept in
the shared worktree reference):

```bash
case '<id>' in
  ''|*[!A-Za-z0-9_-]*) echo "reject (id): not an issue number or ticket key" >&2; exit 1 ;;
esac
printf '%s\n' '<id>' | LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*' || {
  echo "reject (id): not an issue number or ticket key" >&2; exit 1; }
FIRST_WORKTREE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"
[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {
  echo "could not resolve the main checkout"; exit 1; }
PLAN="$MAIN_CHECKOUT/.task/plan/plan-<id>.md"
[ -f "$PLAN" ] || { echo "no plan at $PLAN"; exit 1; }
printf 'PLAN=%s\n' "$PLAN"
```

- `<id>` 가 주어졌을 때 `plan-<id>.md` 가 없으면 초안이 있어도 Plan 완료로 판정하지 않는다 — 초안에는 이슈 번호가 없어서, 거기 있는 초안은 다른 어떤 작업의 것이어도 된다.
- 브랜치/워크트리는 있는데 `plan-<id>.md` 가 없으면 멈추고 사용자에게 보고한다. `project-start` 는 플랜 없이는 브랜치를 만들지 않으므로(Step 1-A) 이 상태는 손으로 만든 브랜치나 옛 실행에서만 나온다. Phase 4 로 넘겨도 `project-done` 이 플랜이 없어 멈춘다.

"Start" 상태에서는 Phase 4 를 브랜치가 이미 체크아웃된 자리에서 잇는다. 그 자리는 아래 순서로 정한다.

1. 로컬 브랜치만 접두 표지 없이 나열한다:

```bash
git branch --list "*issue-<id>-*" "*/<id>-*" --format='%(refname:lstrip=2)'
```

- 로컬 0개(원격에만 있음): 멈추고 두 선택지를 명령과 함께 보인다 — 제자리 `git checkout <branch>`, 또는 워크트리 `git worktree add "<main checkout>/.claude/worktrees/<project>-issue-<id>" <branch>`. 어느 쪽도 자동으로 실행하지 않는다.
- 로컬 2개 이상: 멈추고 보고한다.
- 로컬 1개: 그 브랜치로 2를 잇는다.

2. `git worktree list --porcelain` 레코드에서 그 브랜치가 체크아웃된 자리를 찾는다. `detached` 레코드는 그 브랜치를 rebase 하는 중일 때만 그 브랜치의 자리로 본다:

```bash
git worktree list --porcelain | python3 -c '
import os, subprocess, sys
branch, standard = "refs/heads/" + sys.argv[1], sys.argv[2]
records = [dict((l.split(" ", 1) + [""])[:2] for l in r.splitlines())
           for r in sys.stdin.read().strip().split("\n\n")]
def rebasing(path):
    for name in ("rebase-merge/head-name", "rebase-apply/head-name"):
        rel = subprocess.run(["git", "-C", path, "rev-parse", "--git-path", name],
                             capture_output=True, text=True).stdout.strip()
        head = os.path.join(path, rel) if rel else ""
        if head and os.path.isfile(head) and open(head).read().strip() == branch:
            return True
    return False
hit = [(i, r) for i, r in enumerate(records) if r.get("branch") == branch]
stuck = [r for r in records if "detached" in r
         and (r["worktree"].endswith(standard) or rebasing(r["worktree"]))]
if hit:
    i, r = hit[0]
    state = "prunable" if "prunable" in r else "missing" if not os.path.isdir(r["worktree"]) \
        else "main" if i == 0 else "linked"
    print(state, r["worktree"])
elif stuck:
    print("detached", stuck[0]["worktree"])
else:
    print("none")
' '<branch>' '/.claude/worktrees/<project>-issue-<id>'
```

- `main`: main checkout 에서 Phase 4 를 돈다.
- `linked`: 이 워크트리를 다른 세션이 쓰고 있을 수 있다고 먼저 알리고, 그 경로를 CWD 로 Phase 4 를 돈다.
- `prunable`: 멈춘다. 디렉터리를 옮겼으면 `git worktree repair <새 경로>` 를, 지웠으면 `git worktree prune` 을 안내한다 — 이 상태에서는 checkout 도 워크트리 추가도 실패한다.
- `missing`: 잠긴(locked) 워크트리의 디렉터리가 없다. 멈추고 `git worktree repair <새 경로>` 를 안내한다.
- `detached`: 그 브랜치를 rebase 하는 중인 checkout(main checkout 포함)이거나, 표준 경로의 워크트리가 rebase·bisect 같은 작업 중이다. 멈추고 보고한다.
- `none`: 어디에도 체크아웃돼 있지 않다. 1의 로컬 0개와 같이 두 선택지를 보이고 멈춘다.

3. 이 경로에서는 브랜치도 워크트리도 새로 만들지 않고, 분기 방식 플래그도 쓰지 않는다. 적용 중인 분기 방식(플래그가 없으면 기본값인 워크트리)이 기존 자리와 다르면 기존 자리를 따른다고 알린다.

"Issue" 상태의 Phase 3 은 새 실행과 같은 인자 규칙과 Phase 3 사전 확인을 따른다.

## Instructions

This skill calls four global skills in sequence.
For each phase's detailed procedure, follow that skill document (`~/.claude/skills/<name>/SKILL.md`).

**Main checkout first.**
Once the re-entry state is known, check the CWD before any phase runs.
Phases 1, 2 and 3 run from the main checkout — a new run, and re-entry in the "Issue" or "Issue only" state; from any other CWD, stop and print the main checkout path.
Re-entry in the "Start" state is exempt: Phase 4 runs where the branch is already checked out (`## Re-entry After Interruption`).
The main checkout is the work tree git reports for the first entry of `git worktree list --porcelain` — the canonical main-checkout block kept in the shared worktree reference. Run this fence as one shell call — shell variables do not survive to the next call:

```bash
FIRST_WORKTREE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"
[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {
  echo "could not resolve the main checkout"; exit 1; }
[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {
  echo "not the main checkout — rerun from: $MAIN_CHECKOUT"; exit 1; }
```

---

### Phase 1: Plan

1. Read `$ARGUMENTS` by the argument rules in `## Usage`: the task description is what remains once the trailing flags are taken off.
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
   - Carry on this same screen the Step 2 screen of the `issue` skill that Phase 2 will run — the create or link form that matches the run, down to its question line — so that one yes can answer both; Step 2 states when that yes counts.
   - Show the parsed task description and the parsed flags on separate lines — branch mode `worktree` (default) or `in-place`, and whether `adr` is set — so a misread argument is corrected at approval.
   - If changes are requested, apply them and confirm again.
   - On approval, continue to Phase 2.

---

### Phase 2: Issue

1. Run the `issue` skill procedure:
   - Phase 1 이 방금 만든 플랜 경로를 `project-issue` 에 위치 인자로 그대로 넘긴다. 경로는 이미 알려져 있으므로 자동 탐색을 다시 돌리지 않는다 — 초안이 여럿이면 그 탐색은 자기가 만든 파일조차 고르지 못하고 멈춘다.
   - `## Re-entry After Interruption` 의 "Issue only" 상태에서 왔다면 새 이슈를 만들지 않고 `project-issue <plan-path> --issue <id>` 로 연결 모드를 부른다 — 이슈가 이미 있는데 생성 모드로 부르면 같은 작업의 티켓이 둘이 된다.
   - Phase 1 승인이 `issue` 스킬 Step 2 의 대체 조건을 모두 채웠으면 Step 2 를 다시 묻지 않고, 하나라도 채우지 못했으면 Step 2 를 그대로 묻는다.
   - register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as an issue-tracker ticket (link mode: attach it to `<id>` instead)
   - rename the draft plan to `plan-<id>.md`
2. Print the issue ID / ticket URL, then automatically continue to Phase 3.

---

### Phase 3: Start + Implementation

1. Before calling `project-start`:
   - If Phase 1 was skipped ("Issue" re-entry), show the parsed flags before any check or branch — branch mode `worktree` (default) or `in-place`, and whether `adr` is set.
   - The Phase 3 checks are that flag display and `project-start` Step 1-C, which runs the base check and the ignore check from the main checkout; iterate does not run them a second time.

2. Run the `start` skill procedure with the issue ID from Phase 2:
   - by default, or with `worktree`: call `project-start <id> [adr]`, and run Phase 4 with the new worktree as the CWD
   - with `in-place`: call `project-start <id> in-place [adr]`, which branches in the main checkout
   - pass the `adr` argument when applicable, to write an ADR before implementation
   - read the Intent Summary and Drift Guards
   - print the Task Cards checklist and start implementation
   - review the implementation according to `Review Profile` policy
3. **Confirm only on a listed condition**: once the implementation and its review are done, check the conditions in `## Questions After Plan Approval`.
   - When none of them holds, do not ask; continue to Phase 4.
   - When one holds, show the implementation result summary and each condition that holds, and get approval.
   - If changes are requested, apply them and check the conditions again.
   - On approval, continue to Phase 4.

---

### Phase 4: Done

1. Run the `done` skill procedure with the issue ID from Phase 2:
   - pass the `adr` argument when applicable
   - verify the DoD
   - write the impl-report
   - commit -> push -> create PR, or merge for Jira
   - set issue status to "In Review"
   - once the DoD is confirmed, carry on from the impl-report through commit, push, the PR and the issue comment without asking; ask only on a condition in `## Questions After Plan Approval`.
2. Print the final result (commit hash, PR URL).

---

## Questions After Plan Approval

The plan approval opens the run: after it, this skill asks only when one of the conditions below holds.
On re-entry at Phase 3 or Phase 4, that approval is the one the issue skill's Step 2 took when it registered `plan-<id>.md`; when the plan was edited after that, or placed by hand, show its summary and ask once before going on.

1. A DoD item is not met.
2. The Review Profile review left a blocker unresolved.
3. A measurement contradicts the plan: a file, command or behavior differs from what the plan's Current State or Task Cards say, or the work would cross a Drift Guard.
4. The scope changed: the work needs a file, module or requirement the plan does not name, or drops one it does.
5. An external write — push, PR, issue comment — was blocked by the permission classifier.
6. A called skill asks a question its own document states; that question stays, and this list neither adds to those questions nor removes any.

When one holds, show which one and ask.
This list is the only statement of these conditions; every rule in Phase 3 and Phase 4 that carries on without asking points here.
A stop that a called skill documents is not a question: it still stops.

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
- From Phase 3: `project-start <id>`, or `project-start <id> in-place` for a run that was `in-place` (from the main checkout — `project-start` Step 1-C refuses `in-place` anywhere else). `project-iterate <id>` resumes the same point through the "Issue" state.
- From Phase 4: `project-done <id>`
