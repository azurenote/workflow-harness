---
name: project-start
description: Take an issue number, create a branch or worktree, move the issue to In Progress, read the plan Intent Summary, Drift Guards, and Task Cards, then start implementation.
---

# project-start - Start Work

## Trigger Conditions

Apply this skill in the following situations:
- The user invokes `project-start <issue-id>`, or asks to use the project-start skill to start <issue-id>
- `#<number>` or issue ID plus keywords such as "start", "begin", "implement", or "branch"
- Immediately after `project-issue` completes, when the user says to start

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

That document holds the common contract only. This skill additionally reads:

- `~/.claude/skills/_shared/references/review-guidelines.md` — `review_guidelines` schema and rules
- `~/.claude/skills/_shared/references/base-branch.md` — per-task base branch precedence
- `~/.claude/skills/_shared/references/hooks.md` — lifecycle hook points and failure policy
- `~/.claude/skills/_shared/references/worktree.md` — worktree CWD caveats

Read nothing else from the reference set; the rest does not apply here.

## Output Language Guard

When loading an existing plan, preserve its Korean prose and do not rewrite it into English.
If the `adr` path calls `project-adr`, the ADR document must follow the `project-adr` Korean-output guard.

## Execution Safety Rules

- Issue comments containing Markdown backticks must pass the final body as a single argument so the shell does not interpret them as command substitution.
  - Recommended:
    ```bash
    .claude/scripts/harness_cli.py add-comment 123 'ADR recorded: `docs/adr/example.md`'
    ```
  - Forbidden: passing a body with backticks unquoted, or inside double quotes without escaping.
- If a tracker or git API command (`harness_cli.py`, `gh`, `fj`, `jira`) fails, retry through the documented fallback path for that step. If it still fails, report it to the user and stop — do not invent a third path.
- Never run `codex`, `claude`, or any other LLM CLI through the shell to create a subagent. That path fails on sandbox permissions and is not a fallback.

Running under Codex: read `~/.claude/skills/_shared/references/codex.md` for the host mechanisms these rules map onto — escalation after a sandbox failure, the subagent API, shell quoting, and invocation syntax.

## Usage

```
project-start <issue-id> [worktree] [adr]
```

- `<issue-id>`: GitHub issue number or Jira ticket ID (required)
- `[worktree]`: git worktree mode
- `[adr]`: write ADR before implementation (`project-adr` internal call)

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

Branch push happens during `project-done`. Do not push here.

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
<harness_cli> add-progress "<node-id>"
# fallback (GitHub): gh issue edit <id> --add-label "in-progress" 2>/dev/null || true
# fallback (Jira):   jira issue move <ticket-id> "In Progress"
```

`add-progress` transitions the issue status only; it does not post a comment.
(The optional `--issue-number`/`--branch-name` flags are still accepted for
backward compatibility but are no-ops — no branch-notification comment is
posted.)

**4. ADR (conditional)**

If the `adr` argument is present, run the `project-adr <issue-id>` procedure.
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
If it fails, print only a warning and continue. See `~/.claude/skills/_shared/references/hooks.md`.

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

- `full`: run adversarial review from every role declared in `review_guidelines`, or from the default roles below when the project declares none.
- `docs-light`: run a documentation-only review pass. However, if changed files include code, tests, build, CI, dependencies, runtime config, or execution artifacts, escalate to `full`.
- `auto`: resolve to `docs-light` only when changed files and scope are limited to Markdown/MDX, docs/wiki/content paths, or static documentation assets. Resolve to `full` for any code-impacting change or uncertainty.

**8-A. Load review guidelines (`full` only)**

Read `review_guidelines` from `.claude/skill-config.yaml` before dispatching any reviewer. See `~/.claude/skills/_shared/references/review-guidelines.md` for the schema.

- Each role reads `common` plus its own `docs` **before** reviewing. Reviewers read the paths; never copy a summary of them into the prompt, the plan, or this skill — a copy diverges from the source.
- Pass each role's `focus` string through **verbatim**. Do not parse it, split it, or act on what it appears to reference. Those strings are project constants; interpreting them makes this shared skill language-specific.
- Iterate the roles the project declared. Do not hardcode role names. When `review_guidelines` is absent or declares no roles, degrade to the default roles below.
- A declared path that does not exist is a **warning, not a stop**: skip it, continue the review, and report the skipped path. A silently dropped guideline turns an ungrounded review into one that reports as grounded.

Default roles, used when the project declares no `focus` for them:

- **Architect**: architecture fit, consistency with existing patterns, scope compliance
- **Implementer**: logic bugs, security, edge cases
- **Test engineer**: missing tests, DoD satisfaction, and **whether each guard was verified by mutation**

The mutation duty is not optional and is not removed by a project override. A passing test is not evidence that a guard works. Break the thing the guard protects and confirm the guard actually goes red; only then is it satisfied. Record the mutation you performed, not the fact that the suite is green.

**8-B. Choose an execution path (`full` only)**

Review paths, in priority order. Take the first one available, and close the chain — the last entry always applies.

1. A first-class review tool provided by the host (see `skills/dependencies.yaml` for what this skillset declares and what each absence costs). Give it the role's guideline paths and `focus`.
2. Independent subagents, one per role, dispatched in parallel through the host's subagent mechanism.
3. The main agent performs each role directly, as separate passes, one role at a time.

Rules that hold on every path:

- Never spawn an LLM CLI (`codex`, `claude`, …) through the shell to create a reviewer. That path fails on sandbox permissions and is not a fallback.
- Availability is two questions, not one: a tool can be installed and still be unreachable from the host you are running under. If the declared tool does not actually respond, move down the chain and say so — do not report a path you did not use.
- Roles stay separate on every path. Collapsing three viewpoints into one call is not a cheaper review; it is a different, weaker one.

**8-C. `docs-light` review checklist**

- Can a reader understand the intent and procedure from the document alone?
- Do links, paths, commands, and file names match the current repo?
- Does the document change imply behavior changes in code?
- Does it preserve LLM wiki/docs-as-code structure contracts such as index, frontmatter, tags, and sidebar?

Each review should output findings first, grounded in file/line evidence. Collect feedback, apply fixes immediately, then rerun needed validation.

The final report must state `review profile`, resolved mode, rationale, which execution path from 8-B was used and why, **the guideline paths actually read** (and any skipped as missing), and the findings that were addressed.
