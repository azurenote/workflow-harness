---
name: project-iterate
description: Run the one-stop workflow: project-plan -> project-issue -> project-start -> project-done. Includes user confirmation between each phase. In Codex, run this for `$project-iterate ...` or requests such as "use the project-iterate skill".
---

# project-iterate - One-stop Workflow

## Trigger Conditions

Apply this skill in the following situations:
- Codex receives `$project-iterate <task description>` or a request such as "use the project-iterate skill for <task description>"
- Keywords such as "from start to finish", "one-stop", or "iterate"
- The user wants to go from plan writing to PR in one flow

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Output Language Guard

Generated workflow artifacts remain Korean by default even though the workflow `SKILL.md` files are written in English:
- `$project-plan` writes plan prose, requirements, DoD, task cards, and validation notes in Korean.
- `$project-adr` writes ADR documents in Korean.
- `$project-done` writes the impl-report / issue-report body in Korean.

Do not translate these artifacts to English while moving between phases unless the user explicitly requests English output for the artifact itself.

## Usage

```
$project-iterate <task description> [worktree] [adr]
```

- `<task description>`: task description (required)
- `[worktree]`: branch in worktree mode
- `[adr]`: include ADR writing, passed to both start and done

## Re-entry After Interruption

Re-entry must explicitly provide an issue ID in the form `$project-iterate <id>`.
- Without `<id>`, always start a new run from Phase 1 (Plan).
- `<id>` is a GitHub issue number or Jira ticket ID.

Determine phase completion using these checkpoints:

| Phase | Completion Signal | Check Method |
|-------|----------|----------|
| Plan | supported draft plan exists | same draft discovery contract as `$project-issue` Step 1 (`plan-draft-<lowercase-slug>.md` or lowercase hex UUID `plan-<uuid>.md`) |
| Issue | `plan-<id>.md` exists | `ls .task/plan/plan-<id>.md 2>/dev/null` (exact path, not glob) |
| Start | issue ID branch/worktree exists | `git branch -a \| grep <id>` or `git worktree list` |
| Done | PR exists or issue status is "In Review" | `gh pr list --head <branch-name>` |

Skip completed phases and continue from the next phase.

## Instructions

This skill calls four global skills in sequence.
For each phase's detailed procedure, follow that skill document (`~/.claude/skills/<name>/SKILL.md`).

---

### Phase 1: Plan

1. Extract the task description from `$ARGUMENTS` (excluding `worktree` and `adr` keywords).
2. Run the `plan` skill procedure:
   - analyze the codebase
   - create `plan-draft-<slug>.md`
   - write the human layer (`Intent Summary`, `Current State`, `Target State`, `Non-Goals`, `Drift Guards`) and agent layer (`Implementation Contract`, `Task Cards`, `Validation Plan`)
   - **write a detailed DoD** because `$project-done` later uses it as the verification standard
   - review the plan according to `Review Profile` policy
3. **User confirmation**: show the plan summary and get approval.
   - Confirm first that the Intent Summary and base branch are correct.
   - If changes are requested, apply them and confirm again.
   - On approval, continue to Phase 2.

---

### Phase 2: Issue

1. Run the `issue` skill procedure:
   - register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as an issue-tracker ticket
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
- From Phase 2: `$project-issue`
- From Phase 3: `$project-start <id>`
- From Phase 4: `$project-done <id>`
