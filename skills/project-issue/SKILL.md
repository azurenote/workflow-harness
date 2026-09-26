---
name: project-issue
description: Register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as a ticket in the issue tracker, then rename it to `plan-<id>.md`. With `--issue <id>`, link the draft to an issue that already exists instead of creating one; with `--issue <id>` alone, post a revised `plan-<id>.md` to its issue as a new comment.
---

# project-issue - Register Issue

## Trigger Conditions

Apply this skill in the following situations:
- The user invokes `project-issue`, or asks to use the project-issue skill to register an issue
- The user invokes `project-issue <plan-path>`, naming the draft file to register
- The user invokes `project-issue [<plan-path>] --issue <id>`, or asks to attach a plan to an issue that already exists
- The user invokes `project-issue --issue <id>` with no plan path, or asks to post a revised `plan-<id>.md` to its issue
- A `plan-draft-*.md` or `plan-<uuid>.md` draft exists and issue-registration intent is detected
- Keywords such as "register issue", "create ticket", "upload to GitHub", or "upload to Jira"

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

That document holds the common contract only. This skill additionally reads:

- `~/.claude/skills/_shared/references/base-branch.md` — per-task base branch precedence
- `~/.claude/skills/_shared/references/github-issue-fields.md` — issue metadata contract. Written for `issue_tracker: github`; Step 4 and the Forgejo branch reuse its label rule, so forgejo reads it too.
- `~/.claude/skills/_shared/references/forgejo.md` — `fj` surface facts (`issue_tracker: forgejo` only)
- `~/.claude/skills/_shared/references/exit-codes.md` — what the harness commands this skill runs (`plan_body`, `create-issue`, the core commands) mean by each exit code

Read nothing else from the reference set; the rest does not apply here.

## Output Language Guard

Issue bodies created by this skill must preserve the plan file exactly as written.
Because `project-plan` writes plan prose in Korean by default, do not translate or summarize the plan body into English during issue creation. Upload the Korean plan with `--body-file` as-is, including frontmatter.
The one exception is a plan over the tracker's limit: `## Plan Body Rules` puts a fixed-format summary in its place, extracted from the plan's own words.

## Usage

```
project-issue [<plan-path>] [--issue <id>]
```

- `[<plan-path>]`: the draft plan file to register. Optional.
  - **Omitted** — Step 1 discovers the draft exactly as it always has. Nothing about that path changes.
  - **Given** — Step 1 does not run discovery at all. It validates this path and uses it.

The argument exists for the case discovery cannot resolve on its own: two or more drafts present.
The harness path refuses it outright (`find-draft-plan` exits `REFUSED`); the harness-free path can
still ask, but only interactively. Naming the file settles it in one step, and settles it non-interactively.

- `[--issue <id>]`: an issue that already exists. Optional.
  - **Given** — link mode: the draft is linked to issue `<id>` and no ticket is created; Step 1-L below runs.
  - **Given alone, when `plan-<id>.md` already exists** — revision mode: that plan is posted to `<id>` again as a new comment; Step 1-R below runs.
- With `--issue` and no `<plan-path>`, discovery never runs: when `plan-<id>.md` already exists this is revision mode, and otherwise stop before Step 1, because discovery would take whatever single draft is there, and nothing in a draft names its issue.

Link mode exists because issues often come first — a defect filed from a review has a number before
it has a plan. Without it the only way to attach a plan was to skip this skill and `mv` the file by
hand, which bypasses both Step 1's validation and Step 8's refusal to overwrite, or to run this skill
and get a second ticket for the same work.

## Plan Body Rules

A plan reaches the tracker three ways: as a new issue's body (Step 6), as a comment on the issue it is linked to (Step 1-L item 5), and as a revision comment later (Step 1-R). One rule covers all three, and it applies only to a tracker with a row in this table:

| Tracker | Limit (characters) | Basis |
|---|---|---|
| GitHub | 65,536 | Documented: the API refuses an issue or comment body over 65,536 characters. Not measured here, and whether GitHub counts code points or UTF-16 units is unverified. |
| Forgejo | 65,536 | Measured on a Forgejo 15 instance (2026-09-26): a 65,536-character comment was accepted and read back intact. The server's own ceiling was not probed; this is the cap the rule sets. |

- `harness_core.plan_body.LIMITS` holds the same numbers, and a test compares the two.
- A tracker without a row has no plan body rules: its create body, its link-mode comment question and its comment command stay as they were, and Step 1-R stops.
- Length is counted in characters of the UTF-8 text, never in bytes. A Korean plan is about three bytes a character, so a byte count would send a plan well inside the limit to the summary.
- A body within the limit is the plan file itself, byte for byte. A body over it is a fixed-format summary: the frontmatter, the title, a line saying it is a summary, `Intent Summary` in full, the first line of each `Non-Goals` and `Drift Guards` item, the `Task Cards` titles, the `Definition of Done` checklist, and a last line naming the local file with the full plan and its size. The summary is extracted mechanically, so the same plan always gives the same bytes.
- A summary that is itself over the limit is never cut to fit: nothing is posted, and the step reports why.
- Every comment starts with a marker line, `<!-- plan-<id> rev:<rev> -->`, where `<rev>` is the first 8 hex digits of the plan file's sha1, and the marker counts toward the limit. A create-mode body carries no marker, because it is the plan as written.
- The same content is never posted twice. Before posting, the issue body and comments are read, and the post is skipped when one of them starts with this marker line, or is this plan (or its create-mode summary) as a whole — an issue created from this plan. Each body and comment is compared on its own and in full, so a revision that only drops lines from the end is still posted.
- A failed read is not an empty one. When the read before posting fails, nothing is posted and the comment is 미반영, and the fence exits 1. For these reads the exit code is the evidence (the Forgejo surface: `~/.claude/skills/_shared/references/forgejo.md`). Whether `gh issue view --json comments` returns every comment of a long thread is unverified.

The check fence reads the issue and prints what a comment would be — `KIND=full|summary CHARS=<n> LIMIT=<n> REV=<rev>`, or `SEEN=<why>` and exits `NOOP` when it is already there — and posts nothing. The post fence posts it: `<rev>` is the `REV=` value the approval screen showed, so a plan edited after that yes is refused instead of posted, and its last line is `COMMENT=posted`, `COMMENT=skipped` or `COMMENT=미반영`. Both find `plan-<id>.md` in the main checkout from `<id>` alone. **Run each fence as one shell invocation** — later lines read the variables earlier ones set.

**GitHub** check:

```bash
SEEN="$(mktemp)" || exit 1
trap 'rm -f "$SEEN"' EXIT
gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
python -m harness_core.plan_body github --issue '<id>' --seen "$SEEN" --dry-run
```

**GitHub** post:

```bash
SEEN="$(mktemp)" || exit 1
BODY_FILE="$(mktemp)" || exit 1
trap 'rm -f "$SEEN" "$BODY_FILE"' EXIT
gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
python -m harness_core.plan_body github --issue '<id>' --expect-rev '<rev>' --seen "$SEEN" --out "$BODY_FILE"
RC=$?
[ "$RC" = 5 ] && { echo "COMMENT=skipped"; exit 0; }
[ "$RC" = 0 ] || { echo "COMMENT=미반영 (no body)"; exit 1; }
gh issue comment "<id>" --body-file "$BODY_FILE"
gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read-back failed)"; exit 1; }
python -m harness_core.plan_body github --issue '<id>' --expect-rev '<rev>' --seen "$SEEN" --dry-run > /dev/null
[ "$?" = 5 ] && echo "COMMENT=posted" || { echo "COMMENT=미반영"; exit 1; }
```

**Forgejo** check:

```bash
SEEN="$(mktemp)" || exit 1
trap 'rm -f "$SEEN"' EXIT
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >> "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
python -m harness_core.plan_body forgejo --issue '<id>' --seen "$SEEN" --dry-run
```

**Forgejo** post:

```bash
SEEN="$(mktemp)" || exit 1
BODY_FILE="$(mktemp)" || exit 1
trap 'rm -f "$SEEN" "$BODY_FILE"' EXIT
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >> "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }
python -m harness_core.plan_body forgejo --issue '<id>' --expect-rev '<rev>' --seen "$SEEN" --out "$BODY_FILE"
RC=$?
[ "$RC" = 5 ] && { echo "COMMENT=skipped"; exit 0; }
[ "$RC" = 0 ] || { echo "COMMENT=미반영 (no body)"; exit 1; }
fj -H <forgejo_host> issue comment '<forgejo_repo>#<id>' --body-file "$BODY_FILE"
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >| "$SEEN" || { echo "COMMENT=미반영 (read-back failed)"; exit 1; }
python -m harness_core.plan_body forgejo --issue '<id>' --expect-rev '<rev>' --seen "$SEEN" --dry-run > /dev/null
[ "$?" = 5 ] && echo "COMMENT=posted" || { echo "COMMENT=미반영"; exit 1; }
```

- The Forgejo comment takes the repository in the issue argument, and its success is silent, so the read-back is the only evidence; the surface behind both is in `~/.claude/skills/_shared/references/forgejo.md`.
- The module splits a Forgejo read into one entry per run of quoted lines — how `fj` prints bodies and comments is in `~/.claude/skills/_shared/references/forgejo.md` — and takes GitHub's `--json body,comments` output as it is. The reads write with `>|` so a shell with `noclobber` set can still overwrite the file `mktemp` made.

## Instructions

- With `--issue <id>` and no `<plan-path>`, go straight to Step 1-R: Steps 1, 1-L and 2–8 do not run, and the flow ends at Step 9.

**1. Detect Draft File**

When the call carried a `<plan-path>` argument, do not run discovery. Validate that path instead:

```bash
# The path is a single literal argument. Never interpolate it into a double-quoted
# shell assignment first: `PLAN_PATH="<plan-path>"` would run any `$(...)` or backtick
# the user typed, before python ever sees it.
DRAFT_PLAN="$(python -c '
import sys
from pathlib import Path
from harness_core.config import is_draft_plan
from harness_core.git import main_worktree_root
from harness_core.local import abs_under_main

path = abs_under_main(Path(sys.argv[1])).resolve()
plan_dir = (main_worktree_root() / ".task" / "plan").resolve()
if not path.is_file():
    sys.exit("reject (exists): no such file: %s" % path)
if not is_draft_plan(path.name):
    sys.exit("reject (is_draft_plan): not a draft plan name: %s" % path.name)
if path.parent != plan_dir:
    sys.exit("reject (plan dir): %s is not %s" % (path.parent, plan_dir))
print(path)
' '<plan-path>')"
```

- An explicit path is accepted only when it passes all three checks — the file exists, its name passes `is_draft_plan`, and its parent is the plan directory — and on any failure this skill reports which of the three failed and stops, never falling back to discovery.

The command exits non-zero and names the failed check, so a caller can branch on it. It prints the
**resolved** path and the rest of this skill uses that value — validating one path and then renaming
another is how a symlink lands Step 8's rename outside the plan directory.

`abs_under_main` and `main_worktree_root` are why the plan directory is not `Path(".task/plan")`:
`.task/plan/` is gitignored, so it exists only in the **main worktree**. Resolving against the CWD
rejects every valid path when this skill runs from a linked worktree (`harness_core/local.py`
records the same fix as plan-234).

Why each check is load-bearing:

- **Name check** — it is the only gate protecting Step 8's rename. Accept an arbitrary path here and Step 8 renames a file that was never a draft.
- **Plan-directory check** — Step 8 renames next to the source file on both of its paths. A draft outside the plan directory would become a `plan-<id>.md` that `project-start` and `project-done` never look for.
- **Stopping** — falling back to discovery would hand back the very ambiguity the argument was given to settle.

Without the argument, discover the draft as before.

When `harness_enabled: true`:
```bash
<harness_cli> find-draft-plan
```

Otherwise (or when no harness exists):
```bash
python -c 'from harness_core.config import is_draft_plan; from harness_core.git import main_worktree_root; print("\n".join(str(p) for p in sorted((main_worktree_root() / ".task" / "plan").glob("plan-*.md")) if is_draft_plan(p.name)))'
```

The fallback also uses `harness_core.config.is_draft_plan` as the single contract, and looks in the main checkout's plan directory for the same reason as the explicit-path check above. Valid draft file names are only `plan-draft-<lowercase-slug>.md` or lowercase hex UUID `plan-<uuid>.md`.

Handle the result:
- **No files**: tell the user to run `project-plan` first. Stop.
- **A non-zero exit** is not "no files" by itself. `find-draft-plan` exits `REFUSED` for no draft, several drafts and an unlocated plan directory alike, and its one stderr line says which: no draft and several drafts (the line lists them) take their own bullets in this list. From the fallback, a non-zero exit means the plan directory could not be located (a layout with no main work tree). An unlocated plan directory is reported, and the skill stops.
- **One file**: use that file.
- **Two or more files**: show the list and mtimes, then ask the user to choose.
  - If the user says "latest", automatically choose the file with the newest mtime.

**1-L. Link Mode (--issue)**

Runs only when the call carried `--issue <id>`, right after Step 1 has printed the resolved draft
path. Without `--issue`, skip this step.

Link mode attaches the draft to an issue that already exists. Every check that can refuse runs here,
before Step 2 asks a human to approve anything — a refusal after the approval is a wasted approval.
Each check below stops the skill on failure.

- Never carry a shell variable from an earlier call into these commands; substitute `<id>` and every path as a literal.

The calls in this skill are separate turns — Step 2 and the comment question wait on a human — and
shell variables do not survive between them. A variable that arrives empty does not fail: an empty
path resolves to the main worktree root.

1. **Validate the id.** It becomes part of a file name, so `../x` or `#25` must never reach Step 8.
   Before substituting it at all, refuse an id containing anything but letters, digits and `-`
   without running a command: a `'` in it would close the literal below and hand the rest to the
   shell. Then check its form:

   ```bash
   python -c '
   import re, sys
   patterns = {
       "github": r"[1-9][0-9]*",
       "forgejo": r"[1-9][0-9]*",
       "jira": r"[A-Z][A-Z0-9_]*-[1-9][0-9]*",
   }
   tracker, issue_id = sys.argv[1], sys.argv[2]
   if tracker not in patterns:
       sys.exit("reject (tracker): unknown issue_tracker %r" % tracker)
   if not re.fullmatch(patterns[tracker], issue_id):
       sys.exit("reject (id): %r is not a %s issue id" % (issue_id, tracker))
   ' '<issue_tracker>' '<id>'
   ```

2. **Refuse an issue that already has a plan.** The plan directory lives in the main worktree only,
   so the check is rooted there, not at the CWD:

   ```bash
   python -c '
   import sys
   from harness_core.git import main_worktree_root
   target = main_worktree_root() / ".task" / "plan" / ("plan-%s.md" % sys.argv[1])
   if target.exists():
       sys.exit("stop (exists): %s already has a plan: %s" % (sys.argv[1], target))
   ' '<id>'
   ```

   - When `plan-<id>.md` already exists, link mode stops here, before Step 2's confirmation screen.
   - On a tracker with a row in `## Plan Body Rules`, to post that existing plan to `<id>` again instead, run `project-issue --issue <id>` with no plan path (Step 1-R).

3. **Read the issue.** Keep the output — `project-iterate` reuses the body as its task description.

   - **GitHub**: the core `get-issue` is not this gate. It returns no `state`, and it exits `REFUSED` when the
     project board cannot be read, which would refuse the link for a reason unrelated to the issue.

     ```bash
     gh issue view "<id>" --json number,title,state,url,body,labels
     ```

   - **Forgejo**: the read contract from `~/.claude/skills/SKILL-CONFIG.md`. Strip the directional
     isolates from the wrapped fields (number, title, state) before comparing them, as the Forgejo
     section of Step 6 explains. What a missing number and a pull request number print — measured once — is in
     `~/.claude/skills/_shared/references/forgejo.md`. One measurement is not a contract — the content rule below still decides.

     ```bash
     fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>"
     ```

   - **Jira**:

     ```bash
     jira issue view "<id>" --raw
     ```

   - Judge the read by its content, never by its exit code: the number or key read back equals `<id>`, the title is non-empty, the state is open, and it is not a pull request (GitHub: `url` is an `/issues/` URL; Forgejo: no `From … into …` line).
   - If the read fails, the issue is closed, the number read back is not `<id>`, or it is a pull request, stop before Step 8 and report which it was.

   `~/.claude/skills/SKILL-CONFIG.md` lets a failed read be marked and passed over, and in the same
   paragraph refuses that for a failed write, because an issue number cannot be synthesized locally
   and `project-start` requires one. This read is the second case wearing the first one's clothes:
   Step 8 binds the local plan to `<id>`, and a plan bound to a number nobody could read sends
   `project-start` to an issue that may not exist.

4. **Confirm, then rename.** Step 2 runs with its link-mode additions, and the first line of Step 3 sends the flow to Step 8; nothing is inferred or created on the way, so the issue's type, labels, priority and size stay as the tracker has them.

   - On a tracker with a row in `## Plan Body Rules`, first print the comment line for Step 2's screen; a screen that carries Step 2's screen in its place takes that line from Step 2's screen fence instead. `<draft-plan-path>` is the path Step 1 printed, and the `REV=` value is the `<rev>` item 5 posts:

     ```bash
     python -m harness_core.plan_body '<issue_tracker>' '<draft-plan-path>' --issue '<id>' --dry-run
     ```

   - If it refuses because even the summary is over the limit, the screen carries that refusal as its comment line, the question is the link-only form, and item 5 reports the comment as 미반영.

5. **After Step 8, post the plan as a comment.**

   - On a tracker with a row in `## Plan Body Rules`, Step 2's yes already covers the comment: run that section's post fence with `<rev>` — the `REV=` value on the screen that received the yes, never a new run of item 4 — and report the `COMMENT=` line it prints. Nothing is asked again.
   - On a tracker without a row, ask on its own — `Post plan-<id>.md to #<id> as a comment? [yes/no]` — separately from Step 2.
   - On a tracker without a row, the comment is posted only on its own yes; a no is not an error, because the local `plan-<id>.md` is the canonical plan either way.
   - If the issue body read in item 3 is the same text as the draft, the body already is this plan (a create-mode Step 8 failure being recovered): do not ask, and report the comment as skipped.

   `<plan-file>` is the path Step 8 printed, substituted as a literal:

   - **Jira** — a positional body argument would silently win over `--template`, so never add one.
     Not executed against a live Jira, like every Jira call in this skill:

     ```bash
     jira issue comment add "<id>" --template '<plan-file>' --no-input
     ```

**1-R. Revision Mode (--issue without a plan path)**

Posts `plan-<id>.md` to issue `<id>` again, as a new comment, after the plan changed. Nothing is created or renamed, and the issue body stays as it is.

1. Validate the id with Step 1-L item 1's command.
2. Stop when there is no `plan-<id>.md`, as `## Usage` says. Step 1-L item 2's command exits non-zero exactly when the plan exists, so here its exit 0 is the stop.
3. Stop when the tracker has no row in `## Plan Body Rules`: revision mode is those rules and nothing else.
4. Read the issue with Step 1-L item 3's command, and judge it by the same content rule.
5. Run the check fence in `## Plan Body Rules`.
   - `SEEN=` means this revision, or this plan as the issue body, is already there: post nothing, and report the comment as skipped.
   - A refusal because even the summary is over the limit is reported as 미반영.
6. Otherwise show the screen and ask:

   ```
   issue: #<id> <issue title> (<state>)
   revision: plan-<id>.md rev <REV> — <KIND>, <CHARS>/<LIMIT> characters

   Post this revision of plan-<id>.md to #<id> as a comment? [yes/no]
   ```

7. On yes, run the post fence with `<rev>` from the screen and report its `COMMENT=` line, then go to Step 9.

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

> Plan frontmatter (`base_branch`/`parent_issue`) is propagated to the issue without any extra work: Step 6 uploads the entire plan file as the issue body with `--body-file` — or, over the limit, a summary that keeps the frontmatter (`## Plan Body Rules`) — and Step 8 renames without changing content, preserving frontmatter. Title inference (`--title`) and type/label inference use a frontmatter-aware parser, so the leading `---` block does not affect them.

In link mode the screen also carries the issue Step 1-L read, and the question changes:

```
issue: #<id> <issue title> (<state>)

Are the Intent Summary and base branch correct? Link this file to #<id>? [yes/no]
```

On a tracker with a row in `## Plan Body Rules`, the link screen also carries the comment line Step 1-L item 4 printed, and one yes answers both:

```
issue: #<id> <issue title> (<state>)
comment: plan-<id>.md after the rename — <KIND>, <CHARS>/<LIMIT> characters, rev <REV>

Are the Intent Summary and base branch correct? Link this file to #<id> and post it as a comment? [yes/no]
```

The issue title is the check no command above can make: it is how a human notices that `<id>` names
the wrong issue, or a pull request.

On a tracker with a row in `## Plan Body Rules`, the screen fence prints this step's screen for the mode — the lines above, filled in — and a last line `SCREEN=<hash>` over that screen and the plan's rev. A screen that carries this step's screen in its place shows that output as printed, `SCREEN=` line included, never retyped; run on its own, this step shows its screen as above, and the fence serves only a carried screen and the check below. `<draft-plan-path>` is the draft's path, and `<project default base>` is the `base_branch` from `.claude/skill-config.yaml`, shown only when the plan's frontmatter declares none. A link fence reads the issue again into a file the module parses, so the title and state on the screen are the tracker's own; when that read fails there is no screen. **Run each fence as one shell invocation.**

**GitHub** link screen:

```bash
READ="$(mktemp)" || exit 1
trap 'rm -f "$READ"' EXIT
gh issue view "<id>" --json number,title,state,url >| "$READ" || { echo "stop: the issue read failed; no screen"; exit 1; }
python -m harness_core.plan_body github '<draft-plan-path>' --issue '<id>' --screen --issue-read "$READ" --default-base '<project default base>'
```

**Forgejo** link screen:

```bash
READ="$(mktemp)" || exit 1
trap 'rm -f "$READ"' EXIT
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" >| "$READ" || { echo "stop: the issue read failed; no screen"; exit 1; }
python -m harness_core.plan_body forgejo '<draft-plan-path>' --issue '<id>' --screen --issue-read "$READ" --default-base '<project default base>'
```

Create screen, on either tracker:

```bash
python -m harness_core.plan_body '<issue_tracker>' '<draft-plan-path>' --screen --default-base '<project default base>'
```

From `project-iterate`, Phase 1's approval is this step's confirmation only when that same run's Phase 1 screen carried this step's screen, the user answered yes, and the check below for its tracker holds; ask this step again instead if that check fails, this run had no Phase 1 approval (re-entry at Phase 2), or this skill runs on its own. Steps 1 and 1-L still run either way, so a refusal after that yes costs an approval but never bypasses a check, and the Step 1-L comment follows the screen: posted on that yes where the screen carried the comment line, and asked on its own where it did not.

- On a tracker with a row in `## Plan Body Rules`, the carried screen is the screen fence's output for the mode, as printed, and the check is one run: this step's fence for the mode again, with the path Step 1 resolved and the same `<id>`, and `--expect-screen '<SCREEN>'` added to its `plan_body` line, where `<SCREEN>` is the `SCREEN=` value on the screen that received the yes, must print `SCREEN_MATCH=yes`. A plan edited after that yes (review fixes included), another path, or an issue title or state other than the screen's each print `SCREEN_MATCH=no`; this step then asks with the screen that run printed, `SCREEN=` line included.
- On a tracker without a row, the carried screen is this step's screen as written above — the create or link form that matches the mode, down to its question line — and the check is that the plan file was not edited after that yes (review fixes included), Step 1 resolved the path the screen showed, and the Step 1-L read returns the screen's title and state.

**3. Infer Issue Type** (GitHub only)

- In link mode (`--issue`), Steps 3–7 do not run: after Step 2's yes, go straight to Step 8.

Analyze the plan title and `Intent Summary` / `Current State` keywords:

| Condition | Type |
|------|------|
| `bug`, `fix`, `modify`, `bug`, `error` | `Bug` |
| `feat`, `add`, `improve`, `implement`, `introduce`, `feature` | `Feature` |
| otherwise | `Task` |

Bug keywords take priority. If the title is clear, skip body analysis.

The inferred name must be one the repository actually defines. The harness path validates it and refuses an unknown one before creating anything. On the gh path there is no `--json` field for it — `gh issue view --json` does not return the issue type — so read the repository's types with the `gh api graphql` query in the reference, or the repository's issue-type settings. Never guess: REST silently drops a `type` the token cannot set, so an unverified guess produces an untyped issue that reports as success.

**4. Infer Labels** (GitHub and Forgejo)

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

- The GitHub and Forgejo create fences take `<draft-plan-path>` in single quotes, as Step 1 requires: inside double quotes a `$(...)` or backtick in the path would run. A path that contains `'` is not substituted at all — stop and report it.
- On those two trackers the fence writes the body `## Plan Body Rules` chooses to `BODY_FILE` — the plan itself within the limit, else the summary — and prints its `KIND=` line for Step 9. `BODY_FAILED=1` means nothing was created: even the summary is over the limit, or the module could not run. It is not a failed create, so no create recovery applies; report it and stop.

### GitHub (`issue_tracker: github`)

One call. Type, labels, priority, size and the initial project status are applied together, so there is no second call to forget:

```bash
DRAFT_PLAN='<draft-plan-path>'
BODY_FILE="$(mktemp)" || exit 1
trap 'rm -f "$BODY_FILE"' EXIT
BODY="$(python -m harness_core.plan_body github "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }
printf '%s\n' "$BODY"
<harness_cli> create-issue \
  --title "<plan title>" \
  --body-file "$BODY_FILE" \
  --type "<Type>" \
  --label "<area tag>" \
  --priority "<Priority option>" \
  --size "<Size option>"
```

Exit codes (names from `~/.claude/skills/_shared/references/exit-codes.md`, whose `create-issue` row says what each one means; the items below say only what this skill does on each):

- On `OK` the JSON on stdout carries `number`, `node_id`, `url`, `requested`, `observed` and `drift`.
- On `REFUSED` read the reason on stderr: a **bad argument** you fix and run again; an **environment refusal** you report, because running it again changes nothing.
- On `INCOMPLETE` the issue already exists: never re-run create-issue; run the recovery line it printed on stderr as `<harness_cli> <line>` — `set-fields <number>` carrying only the pieces that failed — and handle each piece it names as not repairable by `set-fields` the way that line says.
- On `UNKNOWN` do not run create-issue again until you have searched the repository for the title: a blind re-run is how one plan becomes two issues.
- An environment refusal or an `UNKNOWN` outcome is **not** "the harness call failed": the judgement ran and answered. Do not drop to the bare `gh` fallback, which carries no reserved-label check at all.

On `OK` or `INCOMPLETE`, read `number` (ISSUE_NUMBER) and `node_id` (ISSUE_NODE_ID) from the JSON on stdout.

`add-backlog` is not part of this path. Call it on its own only after a deliberate `--no-project` creation, when the issue is later added to the board.

When `harness_enabled: false`:

```bash
DRAFT_PLAN='<draft-plan-path>'
BODY_FILE="$(mktemp)" || exit 1
trap 'rm -f "$BODY_FILE"' EXIT
BODY="$(python -m harness_core.plan_body github "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }
printf '%s\n' "$BODY"
gh issue create \
  --title "<plan title>" \
  --body-file "$BODY_FILE" \
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
  --type "<Type>" \
  --summary "<plan title>" \
  --template "$DRAFT_PLAN" \
  --no-input \
  --raw
```

- **`jira issue create` has no `--description` flag.** Measured against the installed CLI (1.7.0): the body flags it accepts are `-b,--body` and `-T,--template`. Cobra aborts on an unknown flag, so a `--description` form does not degrade — it dies on the first call.
- **`--template` closes a second problem at the same time**: it hands over the file instead of expanding the plan body on a command line, and plan bodies are full of backticks and `$`.
- ★ **`-b/--body` wins over `--template`** (the CLI's own `EXAMPLES` say so). If someone later adds `-b` for convenience, the template is ignored **without a word** — the same silent precedence this skill guards against elsewhere.
- **Pass the type inferred in Step 3.** The keyword matching in that step reads the plan, not the tracker, so running it on this path is sound even though its heading says "GitHub only". What is *not* portable is the vocabulary it emits: `Bug` / `Feature` / `Task` are GitHub's names, and Jira issue types are defined per project — `Feature` is not one of Jira's defaults. Map the inferred name onto a type the target project actually defines, the same way the GitHub path requires a type the repository defines. Do not hardcode a type in this call, and do not send an unmapped one.
- **`--raw` returns the API response as JSON.** Read the issue key out of that response — for example `SYN-42`. Which field carries it is **not verified here** (see the limitation below), so do not write a field name into this document as though it were confirmed.
- **`--no-input` is the flag that keeps this call unattended, and it is required.** It suppresses the prompts for non-required fields, the description editor among them; drop it and `--template` alone still opens `$EDITOR` pre-filled with the file, which blocks an unattended run indefinitely. Both flags are load-bearing and neither substitutes for the other.

Then read the issue back before reporting anything about it, using the key from that response as `<TICKET_ID>` — the same name Step 8 consumes:

```bash
jira issue view "<TICKET_ID>" --raw
```

Compare the summary, type and project on the response with what was sent. This read-back stays **inside this section** — Step 7 is the GitHub path and is not generalized to cover other trackers.

> Limitation: this skillset's own repo has no Jira project. Both calls above were checked against the installed CLI's flag surface and this document's internal consistency, and neither has been executed against a live Jira. Anything reported from this path should carry that qualification rather than read as verified.

### Forgejo (`issue_tracker: forgejo`)

**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다 — 읽기 확인이 증거다.**

이 원칙에 매다는 조용한 실패가 이 절에 둘 있다: 빈 채로 나오는 이슈 번호와, 적용되지 않았는데 성공처럼 끝나는 라벨. 두 사고의 표면 — 무엇이 어떻게 조용한가 — 은 `~/.claude/skills/_shared/references/forgejo.md` 에 있다. 이 절은 두 사고를 막는 절차다.

harness 분기는 없다. forgejo 어댑터가 존재하지 않으므로 `harness_enabled` 값과 **무관하게** `fj` 직접 호출이 유일한 경로다. 전역 옵션의 자리와 서브커맨드마다 다른 플래그 표면은 `~/.claude/skills/_shared/references/forgejo.md` 에 있다. 버전 확인 명령(`fj version`)과 최소 버전은 `~/.claude/skills/dependencies.yaml` 이 선언한다 — 여기서 추측하지 않는다.

생성을 먼저 잡고, 번호는 그 출력에서 읽는다. 격리 제거가 그 추출의 한 단이다. **아래 펜스는 한 셸 호출로 실행한다** — 뒤 줄이 앞 줄의 변수를 읽고, 셸 변수는 다음 호출로 넘어가지 않으므로 뒤 단계가 쓸 값은 마지막 두 줄이 출력한다:

```bash
DRAFT_PLAN='<draft-plan-path>'
# Repo targeting: -r <forgejo_repo> as below, or -R <forgejo_remote> when the project
# declares a remote that actually exists locally. create and search take both; edit takes -R only.
TITLE="$(sed -n 's/^# Plan: //p' "$DRAFT_PLAN" | head -1)"
[ -n "$TITLE" ] || { echo "no '# Plan: ' title line in $DRAFT_PLAN"; exit 1; }
BODY_FILE="$(mktemp)" || exit 1
trap 'rm -f "$BODY_FILE"' EXIT
BODY="$(python -m harness_core.plan_body forgejo "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }
CREATED="$(fj -H <forgejo_host> issue create "$TITLE" --body-file "$BODY_FILE" -r <forgejo_repo> --no-template)" || CREATE_FAILED=1
ISSUE_NUMBER="$(printf '%s\n' "$CREATED" \
  | python3 -c 'import sys; sys.stdout.write(sys.stdin.read().replace("\u2068", "").replace("\u2069", ""))' \
  | sed -n 's/^created issue #\([0-9][0-9]*\).*/\1/p')"
printf 'CREATE_FAILED=%s\nISSUE_NUMBER=%s\n%s\n' "${CREATE_FAILED:-0}" "$ISSUE_NUMBER" "$BODY"
printf '%s\n' "$CREATED"
```

- 격리 제거(`\u2068`/`\u2069`)는 군더더기가 아니다. 파이프 한 단으로 두고 **추출보다 앞에** 둔다 — 뒤에 두면 추출이 영영 매치하지 않는다. 빼면 추출이 **에러 없이 빈 문자열**을 돌려주고(생성 출력에서 격리 문자가 끼는 자리: `~/.claude/skills/_shared/references/forgejo.md`), 그 빈 값이 8단계로 흘러든다. 8단계의 id 검사가 `plan-.md` 는 막지만, 그때는 이미 만들어진 이슈의 번호를 잃은 채 멈추는 것이다. 실패가 조용하다는 것이 이 단계를 지켜야 하는 이유다.
- 출력 스타일 옵션에 기대지 않고 격리 제거를 펜스가 직접 한다 — 어느 옵션도 격리 문자를 없애지 않는다(`~/.claude/skills/_shared/references/forgejo.md`).
- **제목을 명령문에 리터럴로 붙여넣지 마라.** 파일에서 읽어 `"$TITLE"` 로 넘긴다. 셸은 파라미터 확장 결과를 다시 훑지 않으므로 따옴표 씌운 변수는 백틱이 들어 있어도 안전하다 — 위험한 것은 **리터럴**이다. `project-plan` 제목은 파일·심볼을 백틱으로 부르는 것이 상례라 이건 예외가 아니라 기본이다. 작은따옴표로 감싸는 것도 해결이 아니다: 제목 안의 아포스트로피 하나가 따옴표를 닫고 뒤따르는 백틱을 실행시키며, 그때 `--body-file` 이 빈 값을 받는다(그때 `fj` 가 하는 일: `~/.claude/skills/_shared/references/forgejo.md`).
- `--body-file` 은 선택이 아니다 — 빠졌을 때 `fj` 가 하는 일은 `~/.claude/skills/_shared/references/forgejo.md` 에 있고, 한국어 플랜을 있는 그대로 올린다는 계약도 이 플래그가 지킨다.
- `--web` 은 자동 경로에서 쓰지 않는다 — "웹에서 확인하려면" 같은 안내로도 넣지 않는다.
- `--no-template` 을 준다. 이 형태가 실패하면(언제 실패하는지: `~/.claude/skills/_shared/references/forgejo.md`) `fj issue templates` 로 목록을 얻어 `--template <T>` 로 재시도한다. **이 재시도 경로는 미검증이다** — 실측한 저장소에 템플릿이 없어 겪지 못했다.

- **생성 실패와 파싱 실패를 한 덩어리로 다루지 마라.** `"$(a | b | c)"` 의 종료코드는 `c` 의 것이라, 파이프라인 하나로 합치면 `fj` 가 죽어도 종료코드 0 에 빈 번호가 나와 **파싱 실패와 구별되지 않는다**. 위처럼 생성을 먼저 잡아 `CREATE_FAILED` 로 갈라둔다.

두 경우의 복구가 다르다. 갈라두는 이유가 이것이다:

- `BODY_FAILED=1` — 생성 호출 전에 멈췄으니 이슈는 **만들어지지 않았다**. 요약조차 한도를 넘었거나 모듈이 돌지 않은 것이다. 생성 실패가 아니므로 아래 두 복구를 타지 않고, 원인을 보고하고 멈춘다.
- `CREATE_FAILED` 가 `1` — 이슈는 **만들어지지 않았다**. 아래 웹 UI 마지막 단으로 간다. 여기서 검색으로 번호를 찾으려 하지 마라.
- 생성은 됐는데 `ISSUE_NUMBER` 가 비었다 — 번호만 못 읽은 것이다. 먼저 펜스가 출력한 생성 출력 원문에서 번호를 읽는다. 읽을 수 없을 때만 아래 펜스로 방금 만든 제목을 찾아 잡힌 번호의 제목을 눈으로 대조하고, 그래도 없으면 웹 UI 마지막 단으로 간다. 번호 없이 8단계로 넘어가지 않는다.

이 펜스도 **한 셸 호출로 실행한다** — 앞 펜스의 `TITLE` 은 이 호출까지 살아 있지 않으므로 같은 줄로 초안에서 제목을 다시 읽고, 제목이 비면 검색하지 않고 멈춘다. 빈 제목의 `issue search` 는 아무 열린 이슈나 잡는다:

```bash
DRAFT_PLAN='<draft-plan-path>'
TITLE="$(sed -n 's/^# Plan: //p' "$DRAFT_PLAN" | head -1)"
[ -n "$TITLE" ] || { echo "no '# Plan: ' title line in $DRAFT_PLAN"; exit 1; }
fj -H <forgejo_host> --style minimal issue search -r <forgejo_repo> "$TITLE"
```

`issue search` 는 제목이 비슷한 기존 열린 이슈를 **엉뚱한 번호로 잡을 수 있다**(`~/.claude/skills/_shared/references/forgejo.md`) — 생성 실패 경로에서 이걸 쓰면 안 되는 이유이고, 여기서도 잡힌 번호의 제목을 눈으로 대조한 뒤 쓴다. 검색 출력에는 create 용 파서를 돌리지 않는다.

라벨 적용과 읽기 확인 펜스의 `<ISSUE_NUMBER>` 는 리터럴로 치환한다 — 생성 펜스가 출력한 `ISSUE_NUMBER=` 값, 그것이 비었을 때 생성 출력 원문에서 읽은 번호, 재검색으로 잡아 제목을 대조한 번호, 웹 UI 에서 사람이 돌려준 번호 중 하나다. 8단계와 같은 이유로 앞 호출의 셸 변수를 넘기지 않는다: 살아남지 못한 변수는 빈 값으로 도착하고, 그러면 `"<forgejo_repo>#"` 는 대상 없는 호출이 된다.

라벨은 4단계에서 이미 추론한 area 태그를 재사용하고, 생성 후 두 번째 호출로 적용한다 — GitHub 절이 한 번의 호출을 고집하는 것과 갈리는 이유는 도구 표면의 차이(`~/.claude/skills/_shared/references/forgejo.md`)이지 절차 설계의 선택이 아니다:

```bash
fj -H <forgejo_host> issue edit "<forgejo_repo>#<ISSUE_NUMBER>" labels -a "<area tag>"
```

- 4단계가 태그를 둘 추론하면(`["BE", "FE"]`) `-a` 를 태그마다 하나씩 준다. 쉼표로 묶은 `-a "BE,FE"` 형태는 쓰지 않는다(`~/.claude/skills/_shared/references/forgejo.md`). 어느 쪽이든 판정은 아래 읽기 확인이다.

- 대상 저장소는 이슈를 `<forgejo_repo>#<N>` 형태로 주어 지정하고, 이 `labels` 호출에 `-r` 을 주지 않는다 — 이 호출에서 그 글자가 무엇을 하는지는 `~/.claude/skills/_shared/references/forgejo.md` 에 있다.
- 라벨 적용은 아래 읽기 확인으로만 확증된다. 붙지 않았으면 그 라벨을 **미반영**으로 보고한다.
- Forgejo 의 area 태그는 **best-effort** 다. 무엇이 유효한 라벨인지 미리 볼 수 없으므로(`~/.claude/skills/_shared/references/forgejo.md`) 한 번 시도하고, 읽어서 확인하고, 안 붙었으면 미반영으로 보고한다 — 없는 라벨을 새로 만들어 채우지 않는다.

type·priority·size 는 `fj` 에 대응 플래그가 없다. 셋 다 **미반영**으로 보고하고 9단계 출력에 싣는다. 4단계가 세운 규칙이 여기에도 그대로 걸린다 — 이 셋을 area 태그에 실어 보내는 우회는 금지다. 근거는 `~/.claude/skills/SKILL-CONFIG.md` 의 폴백 원칙과 `~/.claude/skills/_shared/references/github-issue-fields.md` 이며, 여기에 복제하지 않고 가리킨다. 미반영은 오류 상태가 아니라 Forgejo 의 정상 결과다.

읽기 확인. 조회 형태는 `~/.claude/skills/SKILL-CONFIG.md` 의 기존 조회 계약을 그대로 재사용한다 — 새 형태를 발명하지 않는다:

```bash
# forgejo (read path - see "이슈 트래커" in SKILL-CONFIG.md)
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<ISSUE_NUMBER>"
```

- 확인할 일은 둘이다: 이슈가 실재하는지, 그리고 라벨이 실제로 붙었는지. 위 원칙 때문에 라벨은 여기 말고 확인할 데가 없다.
- create 용 번호 파서를 이 확인에 재사용하지 않는다. 두 출력은 번호 자리와 격리 모양이 다르다(`~/.claude/skills/_shared/references/forgejo.md`). 하나의 파서로 둘을 다루면 둘 다 부서진다 — 여기서는 번호를 다시 파싱하는 것이 목적이 아니므로 격리 문자에 관대하게 읽는다.
- 격리 제거를 라벨 줄에까지 확장하지 마라. 격리 제거는 감싸인 필드에만 쓰는 **국소 처리**이지 모든 `fj` 출력에 거는 일괄 처리가 아니다. 반대로 라벨 줄을 보고 "fj 출력에는 격리 문자가 없다" 고 일반화해서도 안 된다. 어느 필드가 감싸이는지는 `~/.claude/skills/_shared/references/forgejo.md` 에 있다 — 두 과잉 적용이 모두 틀렸다.
- 올바른 표면을 읽어라. 이 절은 라벨만 확인하므로 기본 표면으로 충분하다 — 기본 표면과 `comments` 표면이 각각 무엇을 보여 주는지는 `~/.claude/skills/_shared/references/forgejo.md` 에 있고, 엉뚱한 표면을 읽으면 쓰기가 실패한 것과 똑같이 보인다.
- 등록된 뒤 이슈 본문을 파일에서 갱신하는 경로가 없다(`~/.claude/skills/_shared/references/forgejo.md`). 플랜을 있는 그대로 올린다는 것은 생성 시점의 계약이고, 등록된 뒤 로컬 파일과 이슈 본문이 갈라지면 되돌리기가 비싸다. 처음 올리는 것이 정확해야 하는 이유가 하나 더 있는 셈이다.

`fj` 쓰기 경로가 실패했을 때의 마지막 단은 웹 UI 수동 등록이며, 그 규칙은 `~/.claude/skills/SKILL-CONFIG.md` 의 "이슈 트래커" 절이 갖는다 — 여기에 복제하지 않는다. 사람이 돌려준 번호만 있으면 8단계는 그대로 진행된다.

8단계 rename 은 GitHub 과 같은 `plan-<ISSUE_NUMBER>.md` 규칙을 쓴다. forgejo 도 정수 이슈 번호이므로 새 분기를 만들지 않는다.


**7. Read Back** (GitHub only)

Before reporting, read what is actually on the issue:

```bash
<harness_cli> get-issue <ISSUE_NUMBER>
# fallback (GitHub): gh issue view <ISSUE_NUMBER> --json number,title,url,labels
```

On the gh path, `gh issue view --json` does not return the issue type or the project fields; add `gh project item-list <github_project.number> --owner <github_project.owner> --format json` for the fields, or use the reference's GraphQL query for both at once.

A `create-issue` `OK` already includes this read in its `observed`; repeat it only on the gh path.

**8. Rename File**

After issue creation succeeds — or, in link mode, after Step 2's yes. Both modes use this one step; link mode has no rename of its own.

Substitute two literals: `<draft-plan-path>`, the resolved path Step 1 printed, and `<ISSUE_ID>` —
`<ISSUE_NUMBER>` on GitHub and Forgejo, `<TICKET_ID>` on Jira (for example `plan-SYN-42.md`). Do not
pass a shell variable from an earlier call: this step runs after a confirmation turn, a variable
that did not survive it arrives empty, and an empty path resolves to the main worktree root.

```bash
python -c '
import re, sys
from pathlib import Path
from harness_core.config import is_draft_plan
from harness_core.git import main_worktree_root
from harness_core.local import abs_under_main, rename_plan_to_issue

draft, issue_id = abs_under_main(Path(sys.argv[1])).resolve(), sys.argv[2]
plan_dir = (main_worktree_root() / ".task" / "plan").resolve()
if not draft.is_file() or not is_draft_plan(draft.name) or draft.parent != plan_dir:
    sys.exit("reject (draft): not a draft plan in %s: %s" % (plan_dir, draft))
if not re.fullmatch(r"[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*", issue_id):
    sys.exit("reject (id): not an issue number or ticket key: %r" % issue_id)
try:
    print(rename_plan_to_issue(draft, issue_id))
except FileExistsError as exc:
    sys.exit("stop (exists): %s" % exc)
' '<draft-plan-path>' '<ISSUE_ID>'
```

It prints the new path; that is `<plan-file>` for Step 1-L's comment and for Step 9.

Step 1's three checks run again here because this is the call that moves the file, and the values
reach it across a turn: a check made in another call protects nothing when what arrives here is
different. The id check is here for the same reason as Step 1-L's — an empty number, the Forgejo
section's silent parse failure, would otherwise become `plan-.md`.

- `<harness_cli> rename-plan` is not used here: this step has to run in projects that have no harness_cli, and the command above reaches the same `rename_plan_to_issue`, which itself refuses a source that is not a draft in the plan directory and an id that is not an issue number or ticket key.
- If `plan-<id>.md` already exists, the command stops with a non-zero exit and leaves the draft where it was: report it and stop, never overwrite the existing plan, and never delete the draft to finish the rename.

`mv` is not used either: it overwrites an existing destination without a word, and a destination
written relative to the CWD does not exist from a linked worktree, where `.task/plan/` is absent.

- If the rename fails for any other reason, keep the draft; when the issue was already created, recover with `project-issue <draft-plan-path> --issue <ISSUE_ID>`, which links instead of creating a second ticket.

**9. Output**

- issue number / URL, or Jira ticket ID
- issue title
- **observed** Type / Labels / Priority / Size — the values read back in Step 7, not the values inferred in Steps 3-5. Where they differ, report both and say which is which.
  - On forgejo the only observable one is Labels, and it is observable only through the read-back in the Forgejo section. Type, Priority and Size have no field to land in there, so report all three as 미반영 — that is the normal result, not a failure.
- anything reported as not applied, and the command that would apply it later
- the body, on a tracker with a row in `## Plan Body Rules`: the plan in full, or the summary put in its place with the full size and the limit — the `KIND=` line the create fence printed
- file rename result: `<draft-plan-path>` -> `plan-<id>.md`
- next step: `project-start <issue-number>`

In link mode the output differs in three places:

- metadata is what the Step 1-L read returned, as the tracker holds it — link mode inferred nothing, so there is no requested value to compare with. Where the read carries no field for a value (project fields on GitHub's `gh issue view`, and the type on a gh that does not return `issueType`; everything but labels on Forgejo), say so rather than guessing it.
- the comment result from Step 1-L, on a tracker with a row in `## Plan Body Rules`: the `COMMENT=` line of the post fence — posted (full or summary, with where it can be seen), skipped because this revision or this plan was already there, or 미반영 with its reason. For 미반영, include `project-issue --issue <id>`, which posts it later — except when even the summary is over the limit, which no later run posts until the plan is shorter.
- the comment result from Step 1-L, on a tracker without a row: posted (with where it can be seen), declined, skipped for a recovery run, or 미반영 when the posted comment could not be read back. For every result but posted, include the Step 1-L command that would post `plan-<id>.md` later.
- the issue line is the existing issue, and it says "linked", not "created".

In revision mode the output is the existing issue with the word "revision", the revision and its body kind (`KIND=`, `CHARS=`, `LIMIT=`), and the comment result — posted, skipped with its reason, or 미반영 with its reason and `project-issue --issue <id>` to post it later (not for a summary over the limit).
