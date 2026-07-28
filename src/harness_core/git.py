"""Git operations — branch and worktree management with error handling."""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path


class GitError(Exception):
    """A git operation failed."""

    def __init__(self, command: str, stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"git {command} failed: {stderr}")


def _run_git(*args: str) -> subprocess.CompletedProcess:
    """Run a git command and return the result.

    Raises:
        GitError: If git exits non-zero.
    """
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GitError(" ".join(args), result.stderr.strip())
    return result


def derive_branch_name(issue_number: int, title: str) -> str:
    """Derive branch name from issue number and title.

    Format: feat/issue-<number>-<slug>
    - lowercase, spaces to hyphens, strip special characters
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    slug = slug[:50].rstrip("-")
    return f"feat/issue-{issue_number}-{slug}"


def branch_exists(branch_name: str) -> bool:
    """Check if a local branch exists."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _resolve_base_ref(base_ref: str) -> str:
    """Resolve a base branch name to a git ref that exists locally.

    Resolution order:
      1. If ``base_ref`` already resolves locally (local branch, tag, or commit),
         use it verbatim.
      2. If its remote-tracking ref ``origin/<base_ref>`` already resolves, use that.
      3. Otherwise fetch the branch from origin and use ``origin/<base_ref>``.

    Raises:
        GitError: the ref cannot be resolved even after fetching. Raised before
            any branch/worktree is created, so callers never leave partial state.
    """
    if branch_exists(base_ref):
        return base_ref

    remote_tracking = base_ref if base_ref.startswith("origin/") else f"origin/{base_ref}"
    if branch_exists(remote_tracking):
        return remote_tracking

    fetch_target = base_ref[len("origin/"):] if base_ref.startswith("origin/") else base_ref
    try:
        _run_git("fetch", "origin", fetch_target)
    except GitError as exc:
        raise GitError(
            f"fetch origin {fetch_target}",
            f"base ref '{base_ref}' not found locally and could not be fetched: {exc.stderr}",
        )
    if branch_exists(remote_tracking):
        return remote_tracking
    raise GitError(
        f"rev-parse {base_ref}",
        f"base ref '{base_ref}' could not be resolved locally or as {remote_tracking}",
    )


def create_branch(branch_name: str, base_ref: str | None = None) -> str:
    """Create and checkout a new branch. Returns branch name.

    When ``base_ref`` is given the branch is cut from that ref (resolved via
    :func:`_resolve_base_ref`, fetching from origin if it is remote-only). When
    None, the branch is cut from the current HEAD (legacy behavior). ``--no-track``
    keeps a remote base from being adopted as the new branch's upstream, which
    would otherwise pollute ``git branch -vv`` and trip false "gone" cleanups.
    """
    if base_ref is None:
        _run_git("checkout", "-b", branch_name)
    else:
        resolved = _resolve_base_ref(base_ref)
        _run_git("checkout", "--no-track", "-b", branch_name, resolved)
    return branch_name


def create_worktree(
    worktree_path: str, branch_name: str, base_ref: str | None = None
) -> str:
    """Create a git worktree with a new branch. Returns worktree path.

    ``base_ref`` behaves as in :func:`create_branch`. ``--no-track`` is used for
    the same reason; on a git too old to accept it on ``worktree add`` (rejected
    before any worktree is created), we fall back to creating the worktree and
    then unsetting the upstream.
    """
    if base_ref is None:
        _run_git("worktree", "add", worktree_path, "-b", branch_name)
        return worktree_path

    resolved = _resolve_base_ref(base_ref)
    try:
        _run_git(
            "worktree", "add", "--no-track", "-b", branch_name, worktree_path, resolved
        )
    except GitError as exc:
        # Only fall back when this git is too old to accept --no-track on
        # `worktree add` (the option is rejected before any worktree is made).
        # Any other failure (duplicate branch, dirty path) must propagate —
        # retrying without --no-track would just fail again or mask the cause.
        stderr = (exc.stderr or "").lower()
        if not any(s in stderr for s in ("--no-track", "unknown option", "usage:")):
            raise
        _run_git("worktree", "add", "-b", branch_name, worktree_path, resolved)
        try:
            _run_git("-C", worktree_path, "branch", "--unset-upstream", branch_name)
        except GitError:
            pass  # no upstream was set — nothing to unset
    return worktree_path


def delete_branch(branch_name: str) -> None:
    """Delete a local branch (force, for rollback)."""
    _run_git("branch", "-D", branch_name)


def clean_up_stale_branches(
    bases: list[str] | None = None,
    plan_dir: "Path | str | None" = None,
) -> dict:
    """Fetch --prune, then delete stale branches and their worktrees.

    A branch is stale if its upstream ref is gone (`: gone]` in `git branch
    -vv`) or it is fully merged into any branch listed in `bases`.

    Worktrees on stale branches are removed with --force before branch
    deletion. Merged branches use `-d` (safe); gone-only branches use `-D`.

    A stale branch whose worktree holds uncommitted changes (any `git status
    --porcelain` output — modified or untracked) is left completely alone: the
    worktree is not removed and the branch is not deleted. `worktree remove
    --force` would destroy that work silently, so it is reported under
    ``skipped_dirty`` instead of acted on.

    Args:
        bases: Base branches to check merged status against.
               Defaults to ["develop", "main"]. Missing bases are skipped.
        plan_dir: If given, every ``base_branch`` declared in ``plan-*.md``
               frontmatter under this directory is protected from deletion even
               when it looks stale — an integration branch that sub-task plans
               still target must outlive its own merge into develop. Local scan
               only; no network.

    Returns:
        {"removed_worktrees": [...], "deleted_branches": [...],
         "skipped_dirty": [...], "protected_branches": [...], "warnings": [...]}
    """
    if bases is None:
        bases = ["develop", "main"]

    _run_git("fetch", "--prune")

    # Collect branches whose remote ref is gone
    result = subprocess.run(["git", "branch", "-vv"], capture_output=True, text=True)
    gone_branches: set[str] = set()
    for line in result.stdout.splitlines():
        if ": gone]" not in line:
            continue
        stripped = line.strip().lstrip("*+ ")
        branch = stripped.split()[0]
        if branch:
            gone_branches.add(branch)

    # Never treat a base/default branch as stale, even if its upstream shows
    # gone (e.g. a renamed remote default) — deleting develop/main is never safe.
    gone_branches -= set(bases)

    # Collect branches fully merged into any base
    merged_branches: set[str] = set()
    for base in bases:
        try:
            merged_result = _run_git("branch", "--merged", base)
        except GitError:
            continue  # base branch doesn't exist locally — skip
        for line in merged_result.stdout.splitlines():
            stripped = line.strip().lstrip("*+ ")
            if stripped and stripped not in ("develop", "main"):
                merged_branches.add(stripped)

    stale = gone_branches | merged_branches

    # Protect integration branches that live plans still declare as their base.
    protected: set[str] = set()
    if plan_dir is not None:
        from .local import collect_declared_base_branches

        protected = collect_declared_base_branches(Path(plan_dir))
        stale -= protected

    if not stale:
        return {
            "removed_worktrees": [],
            "deleted_branches": [],
            "skipped_dirty": [],
            "protected_branches": sorted(protected),
            "warnings": [],
        }

    # Build branch → worktree path map from porcelain output
    worktree_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    worktree_map: dict[str, str] = {}
    current_path: str | None = None
    for line in worktree_result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and current_path:
            worktree_map[line[len("branch refs/heads/"):]] = current_path

    # Remove worktrees before deleting their branches; a worktree with
    # uncommitted work is skipped whole (worktree kept, branch kept).
    removed_worktrees: list[str] = []
    skipped_dirty: list[str] = []
    warnings: list[str] = []
    for branch in stale:
        if branch not in worktree_map:
            continue
        path = worktree_map[branch]
        status = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if status.returncode != 0 or status.stdout.strip():
            # Uncommitted changes (modified or untracked) — or an inability to
            # even determine the state (a stale index.lock, a permission error, a
            # temporarily unavailable mount) — mean `worktree remove --force` could
            # destroy work without a trace. Fail closed: leave the whole branch
            # alone and surface it. A non-empty stdout is dirty; a failed check is
            # treated as dirty too, never as clean.
            skipped_dirty.append(branch)
            if status.returncode != 0:
                warnings.append(
                    f"status check failed for {path}; skipped to be safe: {status.stderr.strip()}"
                )
            continue
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", path],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            removed_worktrees.append(path)
        else:
            warnings.append(f"Could not remove worktree {path}: {result.stderr.strip()}")

    # Delete local branches, except those whose dirty worktree we just skipped.
    deleted_branches: list[str] = []
    for branch in sorted(stale):
        if branch in skipped_dirty:
            continue
        flag = "-d" if branch in merged_branches else "-D"
        result = subprocess.run(
            ["git", "branch", flag, branch], capture_output=True, text=True
        )
        if result.returncode == 0:
            deleted_branches.append(branch)
        else:
            warnings.append(f"Could not delete {branch}: {result.stderr.strip()}")

    return {
        "removed_worktrees": removed_worktrees,
        "deleted_branches": deleted_branches,
        "skipped_dirty": sorted(skipped_dirty),
        "protected_branches": sorted(protected),
        "warnings": warnings,
    }


def remove_worktree(worktree_path: str) -> None:
    """Remove a worktree (force)."""
    _run_git("worktree", "remove", "--force", worktree_path)


def push_branch(branch_name: str) -> None:
    """Push branch to origin."""
    _run_git("push", "origin", branch_name)


def current_branch() -> str:
    """Return the name of the current branch."""
    result = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    return result.stdout.strip()


@functools.lru_cache(maxsize=1)
def main_worktree_root() -> Path:
    """Return the absolute path of the main worktree root.

    In a linked worktree, `git rev-parse --git-common-dir` returns the shared
    `.git` directory of the main worktree; its parent is the main worktree
    root. In the main worktree itself, the common dir is the local `.git`,
    so the result still resolves to the main worktree root.

    Fallbacks:
        - bare repository: returns Path.cwd().resolve() (no worktree root).
        - non-git environment (git missing or CWD outside a repo):
          returns Path.cwd().resolve().

    Cached with lru_cache — tests that change CWD across worktrees must call
    main_worktree_root.cache_clear() between assertions.
    """
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        bare = subprocess.check_output(
            ["git", "rev-parse", "--is-bare-repository"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if bare == "true":
            return Path.cwd().resolve()
        return Path(common).resolve().parent
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd().resolve()
