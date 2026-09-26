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
- `~/.claude/skills/_shared/references/github-issue-fields.md` — GitHub issue metadata contract (`issue_tracker: github` only)

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

**1-A. Require the local plan (before any side effect)**

```bash
<harness_cli> plan-file <issue-id>
```

Without a harness_cli, use this fence — **run it as one shell invocation**. It is rooted at the main checkout, because `.task/plan/` is gitignored and exists only there; the four resolving lines are the canonical block in `~/.claude/skills/_shared/references/worktree.md`, and the id checks are the same as `project-done` Step 1's:

```bash
case '<issue-id>' in
  ''|*[!A-Za-z0-9_-]*) echo "reject (id): not an issue number or ticket key" >&2; exit 1 ;;
esac
printf '%s\n' '<issue-id>' | LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*' || {
  echo "reject (id): not an issue number or ticket key" >&2; exit 1; }
FIRST_WORKTREE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"
[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {
  echo "could not resolve the main checkout"; exit 1; }
PLAN="$MAIN_CHECKOUT/.task/plan/plan-<issue-id>.md"
[ -f "$PLAN" ] || { echo "no plan at $PLAN"; exit 1; }
printf 'PLAN=%s\n' "$PLAN"
```

- If `plan-<issue-id>.md` does not exist, stop here — before any branch, worktree, status change or ADR — and point the user to `project-iterate <issue-id>`, or to writing a draft and running `project-issue <plan-path> --issue <issue-id>`.
- **Pass the path on as a literal.** Either form prints the plan's absolute path in the main checkout — `plan-file` bare, the fallback as `PLAN=<path>`. That is `<plan-path>` for Steps 1-B and 5; after 2-B moves the work into a worktree a shell variable is gone and a rebuilt relative path finds nothing.

`project-done` stops on the same missing file (its Step 1), so going on without it only moves the
failure past the side effects of Steps 2–4. Worse, those side effects hide the cause: once the branch
exists, `project-iterate <issue-id>` reads the issue as started and never returns to plan it.
An issue whose body already is a plan is no exception — save the body as a draft and link it.

**1-B. Read base branch (frontmatter - no inference)**

Read the base declared in plan frontmatter. `/start` does **not infer** the base; it only follows this value.

```bash
<harness_cli> get-base <issue-id>    # {"base_branch": "<branch>" | null, "parent_issue": <num> | null}
```

Here, **"project default base"** means whatever `base_branch` the project's `skill-config.yaml` declares, read during "Read Settings". Do not compare against any literal branch name — this skill is shared by projects whose defaults differ, and naming one of them here is the bug the comparison is trying to avoid.

- If `base_branch` is **non-null and different from the project default base**, that branch is both the PR review/merge target and the branch base. Pass `--base-ref "<base_branch>"` in 2-A/2-B below.
- If `base_branch` is `null` or equals the project default base, omit `--base-ref` and use **existing behavior** (branch from current HEAD, assuming the task starts on the default base). Do not add a new prompt.
- Fallback without harness: inspect the leading `base_branch:` line in the frontmatter of `<plan-path>`. If absent, use the project default base.

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

**3. Issue status -> In Progress**

```bash
<harness_cli> add-progress "<node-id>"
# fallback (GitHub): gh project item-edit <github_project.number> --owner <github_project.owner> --url <issue-url> --field Status --value "<status_names.in_progress>" || echo "status not applied"
# fallback (Jira):   jira issue move "<ticket-id>" "<target-state>"   # then read it back, below
# fallback (Forgejo): none - see the Forgejo paragraph at the end of this step
```

Status is a project field, not a label. The fallback above writes that field; if it fails — no `github_project` block, a token without the `project` scope, a gh older than 2.97.0 — report the status as **not applied** and continue. Do not add a workflow-state label instead; see `~/.claude/skills/_shared/references/github-issue-fields.md`.

**The Jira fallback reads the result back.** A `jira issue move` that returns cleanly is not evidence that the issue moved.

```bash
jira issue move "<ticket-id>" "<target-state>"
jira issue view "<ticket-id>" --raw      # read the status field out of this response
```

- **Always pass the state argument.** `jira issue move <ticket-id>` with nothing after it opens an interactive picker (`Select desired state to transition %s to:`), and with no terminal attached the first entry of that list can be executed as-is. Never run the bare form from a skill.
- **Do not write a transition label into this document.** State names differ per workflow, so `<target-state>` is filled in from the project's own workflow. Pinning a name here is the coupling this skillset avoids everywhere else.
- **Judge from the re-read, not from the move's exit code.** If the status that comes back is not the intended one, report the status as **not applied** and continue — the same grade the paragraph above sets. This does not become a gate.
- **Do not substitute `jira issue list -q "key = <ticket-id>" --plain --columns status`.** `--plain` prints a header row, and `-q` is scoped to the configured project context, so a key from another project silently yields zero rows.

> Limitation: this skillset's own repo has no Jira project, so this path was checked against the installed CLI's flag surface and this document's internal consistency. It has not been executed against a live Jira.

`add-progress` transitions the issue status only; it does not post a comment.
(The optional `--issue-number`/`--branch-name` flags are still accepted for
backward compatibility but are no-ops — no branch-notification comment is
posted.)

**Forgejo 에는 상태 전환 `fj` 계약이 없다.** `harness_enabled` 와 무관하게 이 단계의 명령을 부르지 않고, 상태를 **미반영**으로 보고한 뒤 계속한다. 라벨로 In Progress 를 흉내 내지 않는다 — 근거는 `~/.claude/skills/SKILL-CONFIG.md` 의 "이슈 트래커" 절이다.

**4. ADR (conditional)**

If the `adr` argument is present, run the `project-adr <issue-id>` procedure.
Keep the "Execution Safety Rules" above. In particular, do not expose Markdown backticks to shell command substitution when posting the ADR path as an issue comment.
Start implementation only after the ADR commit is complete.

**5. Load plan**

Read `<plan-path>`, the absolute path Step 1-A printed in the main worktree's plan directory.

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

After implementation is complete, run the project's formatter before committing.

This skill is shared across projects and languages, so it carries no formatter of its own. The command comes from the project:

```yaml
# .claude/skill-config.yaml
hooks:
  pre_commit: <the project's format command>
```

If `hooks.pre_commit` is absent, empty, or null, skip this step silently — a project that does not declare a formatter has none, and inventing one here would run the wrong tool. If it fails, print a warning and continue; formatting is not a correctness gate, and `pre_done` is the blocking gate that already runs before commits. See `~/.claude/skills/_shared/references/hooks.md`.

**8. Adaptive Review**

When deciding that work is complete, read `## Review Profile` from the plan first. If absent, use the `review_profile` default from `~/.claude/skills/SKILL-CONFIG.md`. The goal is defect discovery, not approval.

Profile resolution rules:

- `full`: run adversarial review from every role declared in `review_guidelines`, or from the default roles below when the project declares none.
- `docs-light`: run a documentation-only review pass. However, if changed files include code, tests, build, CI, dependencies, runtime config, or execution artifacts, escalate to `full`.
- `auto`: resolve to `docs-light` only when changed files and scope are limited to Markdown/MDX, docs/wiki/content paths, or static documentation assets. Resolve to `full` for any code-impacting change or uncertainty.

**8-A. Load review guidelines (`full` only)**

Read `review_guidelines` from `.claude/skill-config.yaml` before dispatching any reviewer. See `~/.claude/skills/_shared/references/review-guidelines.md` for the schema, the interpretation rules, and the **canonical table of default roles** — that table is not reproduced here, because a second copy diverges from it.

- Each role reads `common` plus its own `docs` **before** reviewing. Reviewers read the paths; never copy a summary of them into the prompt, the plan, or this skill — a copy diverges from the source.
- Pass each role's `focus` string through **verbatim**. Do not parse it, split it, or act on what it appears to reference. Those strings are project constants; interpreting them makes this shared skill language-specific.
- Iterate the roles the project declared. Do not hardcode role names.
- Fall back per role, not all-or-nothing: a role the project declared but gave no `focus` takes its default `focus` from the reference; the default roles as a whole apply only when `review_guidelines` is absent or declares no roles at all.
- A declared path that does not exist is a **warning, not a stop**: skip it, continue the review, and report the skipped path. A silently dropped guideline turns an ungrounded review into one that reports as grounded.
- `review_guidelines` missing **entirely** is also a reportable condition, not a normal state. Say the review ran ungrounded; do not let `Guidelines Read: None` pass as routine.

Use the **구현 리뷰** table in the reference for defaults here.

The mutation duty stands regardless of which roles the project declares: every guard the change adds must be verified by breaking what it protects and confirming it goes red. A passing test is not evidence that a guard works. It is not removed by a project override, and it does not disappear when the project renames or replaces the tester role — assign it to one of the declared roles and say which. Record the mutation you performed, not the fact that the suite is green.

**8-B. Choose an execution path (`full` only)**

Review paths, in priority order. Take the first one available, and close the chain — the last entry always applies.

1. A first-class review tool provided by the host (see `~/.claude/skills/dependencies.yaml` for what this skillset declares and what each absence costs). Give it the role's guideline paths and `focus`.
2. Independent subagents, one per role, dispatched in parallel through the host's subagent mechanism.
3. The main agent performs each role directly, as separate passes, one role at a time.

Rules that hold on every path:

- Never spawn an LLM CLI (`codex`, `claude`, …) through the shell to create a reviewer. That path fails on sandbox permissions and is not a fallback.
- Availability is two questions, not one: a tool can be installed and still be unreachable from the host you are running under. If the declared tool does not actually respond, move down the chain and say so — do not report a path you did not use.
- Roles stay separate on every path. Collapsing the viewpoints into one call is not a cheaper review; it is a different, weaker one.

**8-C. `docs-light` review checklist**

- Can a reader understand the intent and procedure from the document alone?
- Do links, paths, commands, and file names match the current repo?
- Does the document change imply behavior changes in code?
- Does it preserve LLM wiki/docs-as-code structure contracts such as index, frontmatter, tags, and sidebar?

Each review should output findings first, grounded in file/line evidence. Collect feedback, apply fixes immediately, then rerun needed validation.

The final report must state `review profile`, resolved mode, rationale, which execution path from 8-B was used and why, **the guideline paths actually read** (and any skipped as missing), and the findings that were addressed.
