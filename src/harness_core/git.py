"""Git operations — branch and worktree management with error handling."""

from __future__ import annotations

import re
import subprocess


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


def create_branch(branch_name: str) -> str:
    """Create and checkout a new branch. Returns branch name."""
    _run_git("checkout", "-b", branch_name)
    return branch_name


def create_worktree(
    worktree_path: str, branch_name: str
) -> str:
    """Create a git worktree with a new branch. Returns worktree path."""
    _run_git("worktree", "add", worktree_path, "-b", branch_name)
    return worktree_path


def delete_branch(branch_name: str) -> None:
    """Delete a local branch (force, for rollback)."""
    _run_git("branch", "-D", branch_name)


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
