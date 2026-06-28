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
4. Remove worktrees linked to stale branches first with `git worktree remove --force`.
5. Delete branches: use `-d` for branches confirmed merged, and `-D` for branches that are gone only.
6. JSON result: `removed_worktrees`, `deleted_branches`, **`protected_branches`** (declared base branches that were protected), and `warnings`. Report `protected_branches` to the user so they can see which integration branches were preserved.

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
