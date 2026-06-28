---
name: project-harness-init
description: Install the workflow-harness local wrapper into a new project. After Python/uv/git preflight and dry-run confirmation, create the project-local `.claude/scripts/` harness. In Codex, run this for `$project-harness-init ...` or requests such as "use the project-harness-init skill".
---

# project-harness-init - Initial Local Harness Install

## Trigger Conditions

Apply this skill in the following situations:
- `$project-harness-init <target-project-root>`, or requests such as "harness init", "install local harness", or "attach workflow-harness to a new project"
- A new repo needs `.claude/scripts/harness_cli.py`, `.claude/scripts/harness/`, and `.claude/skill-config.yaml` scaffolding

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Instructions

**1. Confirm Target**

Confirm the target project root. If no argument is provided, extract it from the current task intent; if unclear, ask the user.

Values to confirm:
- absolute path to the target root
- `base_branch` (default: configured `base_branch`)
- `issue_tracker` and repo/remote values
- whether `.claude/scripts/harness_cli.py` or `.claude/scripts/harness/` already exists

If a local harness already exists, do not overwrite it with init. Point the user to `$project-harness-update`, or handle overwrite only as a separate task when the user explicitly requests it.

**2. Preflight**

Before writing, always run the Python core preflight. If this step fails, write nothing to the target project.

```bash
python -m harness_core.scaffold init --target "<target-root>"
```

Or, if the console script is installed:

```bash
harness-init --target "<target-root>"
```

The preflight must verify at least:
- the current Python version satisfies `requires-python` in workflow-harness `pyproject.toml`
- `uv --version` succeeds
- `git --version` succeeds

On failure, report the current version, required version, missing tools, and recommended action, then stop. Do not auto-install tools.

**3. Dry-run Confirmation**

Check the dry-run output:
- `created`: files to create
- `updated`: should normally be empty during init
- `skipped`: preserved project-specific files
- `warnings`: preflight or existing-harness warnings

Show the target root and planned created files to the user and ask for confirmation.

**4. Apply**

If the user approves, run apply.

```bash
python -m harness_core.scaffold init \
  --target "<target-root>" \
  --base-branch "<base-branch>" \
  --issue-tracker "<forgejo|github|jira>" \
  --forgejo-remote "<remote-name>" \
  --forgejo-repo "<owner/repo>" \
  --apply
```

Or:

```bash
harness-init --target "<target-root>" --apply
```

**5. Smoke Verification**

Verify that the generated local CLI can be imported.

```bash
python "<target-root>/.claude/scripts/harness_cli.py" --help
```

If needed, run `uv sync` in the target repo and repeat the same smoke check.

**6. Output**

- target root
- preflight result (Python required/current, uv/git status)
- created file list
- preserved/skipped file list
- smoke result
- next step: run `$project-plan` in the target repo, or start the existing workflow

## Drift Guards

- Do not mix user-scope skill installation (`~/.codex/skills` or `~/.claude/skills`) with project-local harness init.
- Do not create files in the target project when Python/uv/git preflight has failed.
- Do not infer GitHub Projects, Forgejo, or Jira detailed IDs automatically. Leave needed values as placeholders or user input.
