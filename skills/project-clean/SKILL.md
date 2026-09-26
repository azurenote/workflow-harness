---
name: project-clean
description: Clean up gone branches and their linked worktrees after a PR is merged.
---

# project-clean - Branch and Worktree Cleanup

## Trigger Conditions

Apply this skill in the following situations:
- `project-clean`, or keywords such as "branch cleanup", "worktree cleanup", "gone branch", or "clean"
- The user asks for cleanup after a PR has been merged

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

That document holds the common contract only. This skill additionally reads:

- `~/.claude/skills/_shared/references/base-branch.md` — per-task base branch precedence
- `~/.claude/skills/_shared/references/worktree.md` — worktree CWD caveats

Read nothing else from the reference set; the rest does not apply here.

## Instructions

When `harness_enabled: true`:
```bash
<harness_cli> clean-up
```

Script behavior:
1. `git fetch --prune` - prune remote-tracking refs.
2. Collect gone branches (`git branch -vv`) and branches merged into `<base_branch>` (`git branch --merged <base_branch>`).
3. **Declared base protection**: any integration branch declared as `base_branch` in the frontmatter of a `plan-<id>.md` in the main checkout's `.task/plan/` is excluded from deletion even if it is stale (gone/merged). This is a local scan with no network access and prevents data loss while sub-PRs are open.
4. **Dirty-worktree guard**: before removing a stale branch's worktree, check `git -C <path> status --porcelain`. If it has any uncommitted change (modified or untracked), the branch is left completely alone — worktree kept, branch kept — and recorded under `skipped_dirty`. `git worktree remove --force` would destroy that work silently, so it is never run on a dirty tree.
5. Remove worktrees linked to *clean* stale branches with `git worktree remove --force`.
6. Delete branches: use `-d` for branches confirmed merged, and `-D` for branches that are gone only. Branches skipped as dirty are not deleted.
7. JSON result: `removed_worktrees`, `deleted_branches`, **`skipped_dirty`** (stale branches preserved because their worktree had uncommitted work), **`protected_branches`** (declared base branches that were protected), and `warnings`. Report both `skipped_dirty` and `protected_branches` to the user so they see which branches were preserved and why.

When `harness_enabled: false`:
> Warning: the fallback path does **not** apply declared base protection. If you run the commands below as-is, you may delete an integration branch that another sub-issue uses as its base. Collect the protected set with the fence below, and exclude it from every branch you delete by hand.

Collect first — **run this fence as one shell invocation**. The plans live only in the main checkout (`.task/plan/` is gitignored), so the protected set is read there; the four resolving lines are the canonical block in `~/.claude/skills/_shared/references/worktree.md`. Read relative to the CWD instead, a linked worktree finds no plan, `PROTECT` comes back empty, and the protection switches off without a word:

```bash
git fetch --prune
FIRST_WORKTREE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"
[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {
  echo "could not resolve the main checkout"; exit 1; }

# Collect declared bases to protect from plan-*.md frontmatter (no network)
PROTECT=$(grep -hERo '^base_branch:[[:space:]]*\S+' "$MAIN_CHECKOUT"/.task/plan/plan-*.md 2>/dev/null \
  | sed -E 's/^base_branch:[[:space:]]*//' | sort -u)
printf 'PROTECT=%s\n' "$PROTECT"

# Gone branches by bare name (for-each-ref prints no `*`/`+` marks), excluding the protected set and develop/main
git for-each-ref --format='%(refname:lstrip=2) %(upstream:track)' refs/heads \
  | awk '$2 == "[gone]" && $1 != "develop" && $1 != "main" {print $1}' \
  | grep -vxF "$PROTECT" 2>/dev/null

# Worktree list
git worktree list
```

Then remove by hand, one branch per run, from the main checkout. Fill in the two values — `BRANCH` from the gone list above, `WT` from `git worktree list`, which prints the path absolute — and run the fence as one shell call. Leave out any branch in `PROTECT`. The main checkout (the first entry of that list) is never a `WT`. An entry marked `prunable` has lost its directory: run `git worktree prune` first, then leave `WT` empty. If a value contains `'`, write it as `'\''`.

The removal applies the harness's dirty-worktree guard (step 4 above) with the same `skipped_dirty` word. When `git -C "$WT" status --porcelain` prints anything (a modified or untracked file), the fence removes nothing — worktree and branch both stay — and prints `skipped_dirty: <branch> (<path>)`; when that check cannot run at all, it does the same below git's own error and adds `— status check failed`. Report every `skipped_dirty` line to the user, with the branch and path, so they see what was preserved and why. A clean worktree is removed only when it has `BRANCH` checked out and the shell is not inside it, and the branch is deleted only after that removal succeeds. Nothing is silenced: git's own errors always show, and a refusal or a failed removal exits non-zero.

```bash
# One gone branch per run. Leave out any branch in PROTECT.
BRANCH='<gone-branch>'
WT='<its worktree path, absolute; leave empty when the branch has none>'
if [ -z "$WT" ]; then
  git branch -D "$BRANCH"
elif ! STATUS="$(git -C "$WT" status --porcelain)"; then
  echo "skipped_dirty: $BRANCH ($WT) — status check failed"
elif [ -n "$STATUS" ]; then
  echo "skipped_dirty: $BRANCH ($WT)"
elif [ "$(git -C "$WT" symbolic-ref -q HEAD)" != "refs/heads/$BRANCH" ]; then
  echo "refused: $WT does not have $BRANCH checked out" >&2; false
else
  case "$(pwd -P)/" in
    "$(cd -P -- "$WT" >/dev/null 2>&1 && pwd -P)/"*) echo "refused: this shell is inside $WT; run from the main checkout" >&2; false ;;
    *) git worktree remove --force "$WT" && git branch -D "$BRANCH" ;;
  esac
fi
```
