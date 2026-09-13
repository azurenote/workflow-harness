---
name: project-issue
description: Register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as a ticket in the issue tracker, then rename it to `plan-<id>.md`.
---

# project-issue - Register Issue

## Trigger Conditions

Apply this skill in the following situations:
- The user invokes `project-issue`, or asks to use the project-issue skill to register an issue
- A `plan-draft-*.md` or `plan-<uuid>.md` draft exists and issue-registration intent is detected
- Keywords such as "register issue", "create ticket", "upload to GitHub", or "upload to Jira"

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

That document holds the common contract only. This skill additionally reads:

- `~/.claude/skills/_shared/references/base-branch.md` — per-task base branch precedence
- `~/.claude/skills/_shared/references/github-issue-fields.md` — GitHub issue metadata contract (`issue_tracker: github` only)

Read nothing else from the reference set; the rest does not apply here.

## Output Language Guard

Issue bodies created by this skill must preserve the plan file exactly as written.
Because `project-plan` writes plan prose in Korean by default, do not translate or summarize the plan body into English during issue creation. Upload the Korean plan with `--body-file` as-is, including frontmatter.

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
- **No files**: tell the user to run `project-plan` first. Stop.
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

> Plan frontmatter (`base_branch`/`parent_issue`) is propagated to the issue without any extra work: Step 6 uploads the entire plan file as the issue body with `--body-file`, and Step 8 renames without changing content, preserving frontmatter. Title inference (`--title`) and type/label inference use a frontmatter-aware parser, so the leading `---` block does not affect them.

**3. Infer Issue Type** (GitHub only)

Analyze the plan title and `Intent Summary` / `Current State` keywords:

| Condition | Type |
|------|------|
| `bug`, `fix`, `modify`, `bug`, `error` | `Bug` |
| `feat`, `add`, `improve`, `implement`, `introduce`, `feature` | `Feature` |
| otherwise | `Task` |

Bug keywords take priority. If the title is clear, skip body analysis.

The inferred name must be one the repository actually defines. The harness path validates it and refuses an unknown one before creating anything. On the gh path there is no `--json` field for it — `gh issue view --json` does not return the issue type — so read the repository's types with the `gh api graphql` query in the reference, or the repository's issue-type settings. Never guess: REST silently drops a `type` the token cannot set, so an unverified guess produces an untyped issue that reports as success.

**4. Infer Labels** (GitHub only)

Analyze "Files to modify" in `Scope`, or "Files / Modules" in `Task Cards`:

| Condition | Labels |
|------|--------|
| `backend/`, `entity/`, or `migration/` path | `["BE"]` |
| `frontend/`, `.tsx`, `.ts`, or `.css` | `["FE"]` |
| both sides | `["BE", "FE"]` |
| unclear | `["BE"]` (default) |

- Never encode type, priority, or size as a label; labels carry area tags only.

That rule is the whole point of the metadata contract, and the reserved names are not a list to memorize — they are derived at runtime from the repository's issue types and the project's field options. See `~/.claude/skills/_shared/references/github-issue-fields.md`.

**5. Infer Priority / Size** (GitHub only)

These are project field values, decided **before** the issue is created so one call can apply them.

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

The names above are this project's option names as an example; use whatever the project's fields actually offer. A value the field does not have is rejected with the available options listed.

**6. Create Issue**

Branch by `issue_tracker` value:

### GitHub (`issue_tracker: github`)

One call. Type, labels, priority, size and the initial project status are applied together, so there is no second call to forget:

```bash
DRAFT_PLAN="<draft-plan-path>"
<harness_cli> create-issue \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN" \
  --type "<Type>" \
  --label "<area tag>" \
  --priority "<Priority option>" \
  --size "<Size option>"
```

Exit codes:

- **0** — created. The JSON on stdout carries `number`, `node_id`, `url`, `requested`, `observed` and `drift`.
- **2** — refused *before* creating anything. Nothing exists; fix the argument and run it again.
- **3** — the issue exists but its fields did not all apply.

- On exit 3 the issue already exists: never re-run create-issue; run set-fields <number> instead.

Read `number` (ISSUE_NUMBER) and `node_id` (ISSUE_NODE_ID) from the output.

`add-backlog` is not part of this path. Call it on its own only after a deliberate `--no-project` creation, when the issue is later added to the board.

When `harness_enabled: false`:

```bash
DRAFT_PLAN="<draft-plan-path>"
gh issue create \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN" \
  --type "<Type>" \
  --label "<area tag>"
```

Then set the project fields on the created issue URL:

```bash
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.priority>" --value "<Priority option>"
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.size>" --value "<Size option>"
```

If the issue is not on the board yet, `gh project item-add <github_project.number> --owner <github_project.owner> --url <issue-url>` first. If these flags are unavailable (gh older than 2.97.0) or the token lacks the `project` scope, use the `gh api graphql` form in the reference. If that also fails, report the fields as **not applied** and continue — do not put the values in labels.

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

**7. Read Back** (GitHub only)

Before reporting, read what is actually on the issue:

```bash
<harness_cli> get-issue <ISSUE_NUMBER>
# fallback (GitHub): gh issue view <ISSUE_NUMBER> --json number,title,url,labels
```

On the gh path, `gh issue view --json` does not return the issue type or the project fields; add `gh project item-list <github_project.number> --owner <github_project.owner> --format json` for the fields, or use the reference's GraphQL query for both at once.

A `create-issue` exit of 0 already includes this read in its `observed`; repeat it only on the gh path.

**8. Rename File**

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

**9. Output**

- issue number / URL, or Jira ticket ID
- issue title
- **observed** Type / Labels / Priority / Size — the values read back in Step 7, not the values inferred in Steps 3-5. Where they differ, report both and say which is which.
- anything reported as not applied, and the command that would apply it later
- file rename result: `<draft-plan-path>` -> `plan-<id>.md`
- next step: `project-start <issue-number>`
