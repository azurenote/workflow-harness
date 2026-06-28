---
name: project-issue
description: Register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as a ticket in the issue tracker, then rename it to `plan-<id>.md`. In Codex, run this for `$project-issue` or requests such as "use the project-issue skill".
---

# project-issue - Register Issue

## Trigger Conditions

Apply this skill in the following situations:
- Codex receives `$project-issue` or a request such as "use the project-issue skill to register an issue"
- A `plan-draft-*.md` or `plan-<uuid>.md` draft exists and issue-registration intent is detected
- Keywords such as "register issue", "create ticket", "upload to GitHub", or "upload to Jira"

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Output Language Guard

Issue bodies created by this skill must preserve the plan file exactly as written.
Because `$project-plan` writes plan prose in Korean by default, do not translate or summarize the plan body into English during issue creation. Upload the Korean plan with `--body-file` as-is, including frontmatter.

## Instructions

**1. Detect Draft File**

When `harness_enabled: true`:
```bash
<harness_cli> find-draft-plan
```

Otherwise (or when no harness exists):
```bash
python -c 'from pathlib import Path; from harness_core.config import is_draft_plan; print("\n".join(str(p) for p in sorted(Path(".task/plan").glob("plan-*.md")) if is_draft_plan(p.name)))'
```

The fallback also uses `harness_core.config.is_draft_plan` as the single contract. Valid draft file names are only `plan-draft-<lowercase-slug>.md` or lowercase hex UUID `plan-<uuid>.md`.

Handle the result:
- **No files**: tell the user to run `$project-plan` first. Stop.
- **One file**: use that file.
- **Two or more files**: show the list and mtimes, then ask the user to choose.
  - If the user says "latest", automatically choose the file with the newest mtime.

**2. User Confirmation**

Show the file title, base branch, and first 30 body lines, then **always get confirmation**.
Do not create an issue without confirmation. This checkpoint is not just filename/title confirmation; it is a human-layer approval checkpoint. The user must review `Intent Summary`, `Current State`, `Target State`, `Non-Goals`, and `Drift Guards` and confirm that the work intent is correct.
The preview shows leading frontmatter as-is (`read_plan_preview`), so if the plan declares `base_branch`, explicitly name the merge target branch at confirmation time. If there is no frontmatter, show the project default base from `.claude/skill-config.yaml`.

```
file: <draft-plan-path>
title: <text after # Plan:>          # the real title, not '---', even with frontmatter (frontmatter-aware)
base branch: <frontmatter base_branch value, or "<project default base> (default)">
human preview: <full frontmatter + first 30 body lines>

Are the Intent Summary and base branch correct? Create an issue from this file? [yes/no]
```

> Plan frontmatter (`base_branch`/`parent_issue`) is propagated to the issue without any extra work: Step 5 uploads the entire plan file as the issue body with `--body-file`, and Step 7 renames without changing content, preserving frontmatter. Title inference (`--title`) and type/label inference use a frontmatter-aware parser, so the leading `---` block does not affect them.

**3. Infer Issue Type** (GitHub only)

Analyze the plan title and `Intent Summary` / `Current State` keywords:

| Condition | Type |
|------|------|
| `bug`, `fix`, `modify`, `bug`, `error` | `Bug` |
| `feat`, `add`, `improve`, `implement`, `introduce`, `feature` | `Feature` |
| otherwise | `Task` |

Bug keywords take priority. If the title is clear, skip body analysis.

**4. Infer Labels** (GitHub only)

Analyze "Files to modify" in `Scope`, or "Files / Modules" in `Task Cards`:

| Condition | Labels |
|------|--------|
| `backend/`, `entity/`, or `migration/` path | `["BE"]` |
| `frontend/`, `.tsx`, `.ts`, or `.css` | `["FE"]` |
| both sides | `["BE", "FE"]` |
| unclear | `["BE"]` (default) |

**5. Create Issue**

Branch by `issue_tracker` value:

### GitHub (`issue_tracker: github`)

When `harness_enabled: true`:
```bash
DRAFT_PLAN="<draft-plan-path>"
<project_py> create-issue \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN" \
  --type "<Bug|Feature|Task>" \
  --label "<BE|FE>"
```

When `harness_enabled: false`:
```bash
DRAFT_PLAN="<draft-plan-path>"
gh issue create \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN"
```

Read `number` (ISSUE_NUMBER) and `node_id` (ISSUE_NODE_ID) from the output.

### Jira (`issue_tracker: jira`)

```bash
DRAFT_PLAN="<draft-plan-path>"
jira issue create \
  --project "<jira_project>" \
  --summary "<plan title>" \
  --description "$(cat "$DRAFT_PLAN")" \
  --type Task
```

Read the ticket ID from output, for example `SYN-42`.

**6. Infer Priority / Size** (GitHub only)

| Type | Priority |
|------|----------|
| Bug + critical/urgent | P0 |
| Bug | P1 |
| Feature | P1 |
| Task | P2 |

| Task count | File count | Size |
|---------|---------|------|
| 1-2 | 1-2 | XS |
| 2-3 | 2-4 | S |
| 3-5 | 3-6 | M |
| 5-8 | 5-10 | L |
| 8+ | 10+ | XL |

```bash
<project_py> add-backlog "<ISSUE_NODE_ID>" --priority <P0|P1|P2> --size <XS|S|M|L|XL>
```

**7. Rename File**

After issue creation succeeds:

```bash
DRAFT_PLAN="<draft-plan-path>"
# GitHub
mv "$DRAFT_PLAN" .task/plan/plan-<ISSUE_NUMBER>.md

# Jira
mv "$DRAFT_PLAN" .task/plan/plan-<TICKET_ID>.md
# example: plan-SYN-42.md
```

Idempotency: if the destination file already exists, skip the rename.
If rename fails: keep the draft file and ask the user to enter the issue ID manually.

When a harness exists:
```bash
DRAFT_PLAN="<draft-plan-path>"
<harness_cli> rename-plan "$DRAFT_PLAN" <ISSUE_NUMBER>
```

**8. Output**

- issue number / URL, or Jira ticket ID
- issue title
- detected Type / Labels / Priority / Size, including rationale
- file rename result: `<draft-plan-path>` -> `plan-<id>.md`
- next step: `$project-start <issue-number>`
