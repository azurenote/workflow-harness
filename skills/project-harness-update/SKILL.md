---
name: project-harness-update
description: Synchronize an existing project's workflow-harness local wrapper to the latest canonical wrapper. Show dry-run/diff and backup paths first, while preserving project-specific settings. In Codex, run this for `$project-harness-update ...` or requests such as "use the project-harness-update skill".
---

# project-harness-update - Local Harness Update

## Trigger Conditions

Apply this skill in the following situations:
- `$project-harness-update <target-project-root>`, or requests such as "harness update", "sync local harness", or "update wrapper"
- An existing project must be aligned after the `harness_core` public contract or canonical wrapper templates changed

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Instructions

**1. Confirm Target**

Confirm the target project root. If no argument is provided, use the current repo.

Values to check:
- absolute path to the target root
- existing `.claude/skill-config.yaml`
- existing `.claude/scripts/project.py`
- existing `.claude/scripts/harness_cli.py`
- existing `.claude/scripts/harness/`

**2. Preflight + Dry-run**

Before writing, always run dry-run.

```bash
python -m harness_core.scaffold update --target "<target-root>"
```

Or, if the console script is installed:

```bash
harness-update --target "<target-root>"
```

The preflight checks the minimum Python version, `uv`, and `git`. If it fails, write nothing and stop.

Check the dry-run output:
- `created`: missing canonical files to create
- `updated`: files that differ from the canonical template and will be replaced
- `unchanged`: files already canonical
- `skipped`: project-specific files to preserve
- `backed_up`: paths that will be backed up on apply
- `warnings`: conflicts or preflight warnings

**3. Confirm Preservation Boundaries**

The following files contain project-specific values and are preserved by default:
- `.claude/skill-config.yaml`
- `.claude/scripts/project.py`
- hooks, tracker-specific constants, and repo/remote settings
- local-only/custom files under `.claude/scripts/harness/`

Canonical wrapper files are updated by manifest/template version or content comparison. A legacy wrapper without a manifest can also be selected for update when its content differs.

**4. Apply**

If the user approves the dry-run, apply the update.

```bash
python -m harness_core.scaffold update --target "<target-root>" --apply
```

Or:

```bash
harness-update --target "<target-root>" --apply
```

If an update target already exists, back it up first under `.claude/scripts/.harness-backup/<timestamp>/` inside the target repo.

**5. Smoke Verification**

```bash
python "<target-root>/.claude/scripts/harness_cli.py" --help
```

If it fails, report the changed files and backup path. Do not auto-rollback; leave the state available for user inspection.

**6. Output**

- target root
- preflight result
- created/updated/unchanged/skipped/backed_up lists
- smoke result
- preserved project-specific file list

## Drift Guards

- Do not automatically scan sibling projects and write to them in bulk. Multiple targets are allowed only with explicit arguments and confirmation per target.
- Do not blindly overwrite `.claude/skill-config.yaml` or `.claude/scripts/project.py` with canonical templates.
- Do not implement complex merge/backup decisions with shell snippets. Treat `harness_core.scaffold` output as the source of truth.
