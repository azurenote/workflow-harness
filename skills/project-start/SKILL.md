---
name: project-start
description: Take an issue number, create a branch or worktree, move the issue to In Progress, read the plan Intent Summary, Drift Guards, and Task Cards, then start implementation. In Codex, run this for `$project-start ...` or requests such as "use the project-start skill".
---

# project-start - Start Work

## Trigger Conditions

Apply this skill in the following situations:
- Codex receives `$project-start <issue-id>` or a request such as "use the project-start skill to start <issue-id>"
- `#<number>` or issue ID plus keywords such as "start", "begin", "implement", or "branch"
- Immediately after `$project-issue` completes, when the user says to start

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Output Language Guard

When loading an existing plan, preserve its Korean prose and do not rewrite it into English.
If the `adr` path calls `$project-adr`, the ADR document must follow the `$project-adr` Korean-output guard.

## Execution Safety Rules

- Issue comments containing Markdown backticks must pass the final body as a single argument so the shell does not interpret them as command substitution.
  - Recommended:
    ```bash
    .claude/scripts/harness_cli.py add-comment 123 'ADR recorded: `docs/adr/example.md`'
    ```
  - Forbidden: passing a body with backticks unquoted, or inside double quotes without escaping.
- In Codex, if GitHub API commands such as `harness_cli.py`, `project.py`, or `gh` fail because of network/sandbox errors, immediately rerun the same command with `require_escalated`.
- In Codex, when Review Profile resolves to `full` and team review is performed, do not spawn separate `codex`/`claude` shell processes.
  - Use subagent tools only when user request or execution-environment policy allows them.
  - If no subagent tool is available or policy disallows it, the main agent performs three separate adversarial review passes directly.
  - State the review method and fallback, if any, in the final report.

### Claude Code Execution Rules

Apply the following instead of Codex-only mechanisms:

- **No `require_escalated`**: if GitHub API calls (`harness_cli.py`, `gh`) fail, retry via fallback paths; if they still fail, report to the user and stop.
- **Do not spawn LLM processes through the shell**: do not run `codex`, `claude`, or similar commands through the shell to create subagents. Same principle as Codex.
- **Subagents**: use the `Agent` tool instead of `multi_agent_v1.spawn_agent`.
- **When subagents are unnecessary**: the main agent performs the three viewpoints directly in sequence, same as the fallback path.

## Usage

```
$project-start <issue-id> [worktree] [adr]
```

- `<issue-id>`: GitHub issue number or Jira ticket ID (required)
- `[worktree]`: git worktree mode
- `[adr]`: write ADR before implementation (`$project-adr` internal call)

## Instructions

**1. Fetch issue info and derive branch name**

When `harness_enabled: true`:
```bash
<harness_cli> get-issue <issue-id>
```

When `harness_enabled: false` (GitHub):
```bash
gh issue view <issue-id> --json title,id,labels
```

Jira:
```bash
jira issue view <ticket-id>
```

Read `title`, `node_id` (GitHub) / ticket ID (Jira), and derive the branch name.
Branch naming rule: `feat/issue-<id>-<slug>` for GitHub, or `feat/<ticket-id>-<slug>` for Jira.

**1-B. Read base branch (frontmatter - no inference)**

Read the base declared in plan frontmatter. `/start` does **not infer** the base; it only follows this value.

```bash
<harness_cli> get-base <issue-id>    # {"base_branch": "<branch>" | null, "parent_issue": <num> | null}
```

Here, **"project default base"** means the `base_branch` from `skill-config.yaml` read by "Read Settings" (enseed-trader=`develop`, cosmos-forge=`main`). Do not compare against the literal string `develop`; this skill is shared by multiple projects.

- If `base_branch` is **non-null and different from the project default base**, that branch is both the PR review/merge target and the branch base. Pass `--base-ref "<base_branch>"` in 2-A/2-B below.
- If `base_branch` is `null` or equals the project default base, omit `--base-ref` and use **existing behavior** (branch from current HEAD, assuming the task starts on the default base). Do not add a new prompt.
- Fallback without harness: inspect the leading `base_branch:` line in `.task/plan/plan-<issue-id>.md` frontmatter directly. If absent, use the project default base.

**2-A. Normal Branch (default)**

```bash
# When base is declared
<harness_cli> create-branch "<branch-name>" --base-ref "<base_branch>"
# When base is undeclared (default)
<harness_cli> create-branch "<branch-name>"
# fallback (declared): git fetch origin "<base_branch>" 2>/dev/null; git checkout --no-track -b "<branch-name>" "<base_branch | origin/base_branch>"
# fallback (undeclared): git checkout -b "<branch-name>"
```

Branch push happens during `$project-done`. Do not push here.

**2-B. Worktree mode (when `worktree` argument is present)**

```bash
# When base is declared
<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>" --base-ref "<base_branch>"
# When base is undeclared (default)
<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>"
# fallback: git worktree add [--no-track] ".claude/worktrees/<project>-issue-<id>" -b "<branch-name>" ["<base_branch | origin/base_branch>"]
```

After this, perform all work inside `$WORKTREE_PATH`.

**2-C. Set tab name**

```bash
cmux rename-tab "task #<id>" 2>/dev/null || true
```

**3. Issue status -> In Progress**

```bash
<harness_cli> add-progress "<node-id>" --issue-number <id> --branch-name "<branch-name>"
# fallback (GitHub): gh issue edit <id> --add-label "in-progress" 2>/dev/null || true
# fallback (Jira):   jira issue move <ticket-id> "In Progress"
```

**4. ADR (conditional)**

If the `adr` argument is present, run the `$project-adr <issue-id>` procedure.
Keep the "Execution Safety Rules" above. In particular, do not expose Markdown backticks to shell command substitution when posting the ADR path as an issue comment.
Start implementation only after the ADR commit is complete.

**5. Load plan**

Read `.task/plan/plan-<issue-id>.md`. If the file is not local and the issue body is accessible, read the plan from the issue body using the same criteria.

Before implementation, read in this order:

1. `Intent Summary`: what changes and why.
2. `Current State` / `Target State`: current behavior and desired completed state.
3. `Non-Goals`: what this work intentionally does not do.
4. `Drift Guards`: dangerous misunderstandings and scope boundaries.
5. `Review Profile`: review intensity, expected mode, and rationale.
6. `Requirements` and `Definition of Done`: verifiable requirements.
7. `Implementation Contract` and `Task Cards`: files/modules, contracts, completion conditions, and validation method.

If an old plan lacks `Task Cards` but has `Task Breakdown`, use the latter as execution units while checking against Requirements/DoD to prevent drift where possible.

**5-H. `post_start` hook (only if present)**

If `.claude/skill-config.yaml` has `hooks.post_start`, run it through Bash.
If it fails, print only a warning and continue. See "Hook Execution" in `SKILL-CONFIG.md`.

**6. Start implementation**

First summarize Intent Summary, Drift Guards, and Review Profile. Then print `Task Cards` as a checklist and immediately start Task 1.
Do not wait for additional instruction.

**7. Formatting before commit**

After implementation is complete, run this before committing:

```bash
cargo fmt --all
```

**8. Adaptive Review**

When deciding that work is complete, read `## Review Profile` from the plan first. If absent, use the `review_profile` default from `~/.claude/skills/SKILL-CONFIG.md`. The goal is defect discovery, not approval.

Profile resolution rules:

- `full`: run adversarial review from architect, implementer, and test engineer viewpoints.
- `docs-light`: run a documentation-only review pass. However, if changed files include code, tests, build, CI, dependencies, runtime config, or execution artifacts, escalate to `full`.
- `auto`: resolve to `docs-light` only when changed files and scope are limited to Markdown/MDX, docs/wiki/content paths, or static documentation assets. Resolve to `full` for any code-impacting change or uncertainty.

`full` review viewpoints:

- **Architect**: architecture fit, consistency with existing patterns, scope compliance
- **Implementer**: logic bugs, security, edge cases
- **Test engineer**: missing tests, DoD satisfaction

Codex execution rules:

- If mode is `full` and subagent tools are allowed, delegate review in parallel to three independent subagents.
- Do not run `codex`, `claude`, or other LLM CLIs through shell commands to create subagents. That path repeatedly fails on sandbox permissions.
- If no subagent tool is available or policy disallows it, do not stop; the main agent performs the three viewpoints directly and separately.

Claude Code execution rules:

- If mode is `full` and the `Agent` tool is available, delegate review in parallel to three independent subagents.
- Do not run `codex`, `claude`, or other LLM CLIs through the shell. Same principle as Codex.
- When proceeding without subagents, the main agent performs the three viewpoints directly and separately.

`docs-light` review checklist:

- Can a reader understand the intent and procedure from the document alone?
- Do links, paths, commands, and file names match the current repo?
- Does the document change imply behavior changes in code?
- Does it preserve LLM wiki/docs-as-code structure contracts such as index, frontmatter, tags, and sidebar?

Each review should output findings first, grounded in file/line evidence. Collect feedback, apply fixes immediately, then rerun needed validation.
The final report must summarize `review profile`, resolved mode, rationale, review execution method (`subagents`, `main-agent fallback`, `docs-light`), and review findings that were addressed.
