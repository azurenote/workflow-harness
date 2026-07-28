---
name: project-clean
description: Clean up gone branches and their linked worktrees after a PR is merged. In Codex, run this for `$project-clean` or requests such as "use the project-clean skill".
---

# project-clean - Branch and Worktree Cleanup

## Trigger Conditions

Apply this skill in the following situations:
- `$project-clean`, or keywords such as "branch cleanup", "worktree cleanup", "gone branch", or "clean"
- The user asks for cleanup after a PR has been merged

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

## Instructions

When `harness_enabled: true`:
```bash
<harness_cli> clean-up
```

Script behavior:
1. `git fetch --prune` - prune remote-tracking refs.
2. Collect gone branches (`git branch -vv`) and branches merged into `<base_branch>` (`git branch --merged <base_branch>`).
3. **Declared base protection**: any integration branch declared as `base_branch` in `.task/plan/plan-<id>.md` frontmatter is excluded from deletion even if it is stale (gone/merged). This is a local scan with no network access and prevents data loss while sub-PRs are open.
4. **Dirty-worktree guard**: before removing a stale branch's worktree, check `git -C <path> status --porcelain`. If it has any uncommitted change (modified or untracked), the branch is left completely alone — worktree kept, branch kept — and recorded under `skipped_dirty`. `git worktree remove --force` would destroy that work silently, so it is never run on a dirty tree.
5. Remove worktrees linked to *clean* stale branches with `git worktree remove --force`.
6. Delete branches: use `-d` for branches confirmed merged, and `-D` for branches that are gone only. Branches skipped as dirty are not deleted.
7. JSON result: `removed_worktrees`, `deleted_branches`, **`skipped_dirty`** (stale branches preserved because their worktree had uncommitted work), **`protected_branches`** (declared base branches that were protected), and `warnings`. Report both `skipped_dirty` and `protected_branches` to the user so they see which branches were preserved and why.

When `harness_enabled: false`:
> Warning: the fallback path does **not** apply declared base protection. If you run the commands below as-is, you may delete an integration branch that another sub-issue uses as its base. Collect the protected set manually before deletion and exclude it:
```bash
git fetch --prune

# Collect declared bases to protect from plan-*.md frontmatter (no network)
PROTECT=$(grep -hERo '^base_branch:[[:space:]]*\S+' .task/plan/plan-*.md 2>/dev/null \
  | sed -E 's/^base_branch:[[:space:]]*//' | sort -u)

# Gone branch list, excluding the protected set
git branch -vv | grep '\[origin/.*: gone\]' | awk '{print $1}' \
  | grep -vxF "$PROTECT" 2>/dev/null

# Worktree list
git worktree list

# Manually remove gone branches, excluding the protected set and default bases (develop/main)
git worktree remove --force ".claude/worktrees/<name>" 2>/dev/null || true
git branch -D <gone-branch>   # only when it is not in PROTECT and is not develop/main
```
