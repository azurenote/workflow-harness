"""Tests for harness_core.git module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from harness_core.git import (
    derive_branch_name,
    main_worktree_root,
    create_branch,
    create_worktree,
    branch_exists,
    current_branch,
    clean_up_stale_branches,
    GitError,
)


class TestDeriveBranchName:
    def test_simple_title(self):
        result = derive_branch_name(42, "Upbit JWT Auth")
        assert result == "feat/issue-42-upbit-jwt-auth"

    def test_special_characters_stripped(self):
        result = derive_branch_name(
            153, "Harness Architecture Redesign for enseed-trader Workflow"
        )
        assert result == "feat/issue-153-harness-architecture-redesign-for-enseed-trader-wo"

    def test_fix_title(self):
        result = derive_branch_name(
            136, "Fix #136 — MasterDriven close no-op"
        )
        assert result == "feat/issue-136-fix-136-masterdriven-close-no-op"

    def test_truncation(self):
        long_title = "A" * 100
        result = derive_branch_name(1, long_title)
        assert len(result) <= len("feat/issue-1-") + 50

    def test_empty_title(self):
        result = derive_branch_name(1, "")
        assert result == "feat/issue-1-"


@pytest.fixture
def chdir(monkeypatch):
    def _chdir(path: Path) -> None:
        monkeypatch.chdir(path)
        main_worktree_root.cache_clear()
    return _chdir


@pytest.fixture
def _no_cache():
    main_worktree_root.cache_clear()
    yield
    main_worktree_root.cache_clear()


def _git(*args: str, cwd: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True,
        capture_output=True,
    )


def _rev(ref: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=str(cwd),
        capture_output=True, text=True,
    ).stdout.strip()


def _is_ancestor(ancestor: str, descendant: str, cwd: Path) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=str(cwd), capture_output=True,
    ).returncode == 0


def _has_upstream(branch: str, cwd: Path) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
        cwd=str(cwd), capture_output=True,
    ).returncode == 0


def _init_repo(path: Path, default_branch: str = "develop") -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-b", default_branch, cwd=path)
    (path / "f").write_text("0")
    _git("add", ".", cwd=path)
    _git("commit", "-m", "init", cwd=path)


def _add_branch_with_commit(repo: Path, branch: str, from_branch: str = "develop") -> str:
    """Create `branch` off `from_branch` with one extra commit; return its tip sha."""
    _git("checkout", from_branch, cwd=repo)
    _git("checkout", "-b", branch, cwd=repo)
    (repo / branch.replace("/", "_")).write_text("x")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", f"on {branch}", cwd=repo)
    tip = _rev("HEAD", repo)
    _git("checkout", from_branch, cwd=repo)
    return tip


class TestCreateBranchBaseRef:
    def test_none_uses_current_head(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        chdir(repo)
        head = _rev("HEAD", repo)
        create_branch("feat/sub")
        assert current_branch() == "feat/sub"
        assert _rev("HEAD", repo) == head

    def test_local_base_ref(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        integ = _add_branch_with_commit(repo, "feat/integration")
        chdir(repo)  # currently on develop
        create_branch("feat/sub", base_ref="feat/integration")
        assert current_branch() == "feat/sub"
        assert _rev("HEAD", repo) == integ
        assert _is_ancestor("feat/integration", "feat/sub", repo)
        assert not _has_upstream("feat/sub", repo)  # local base: no tracking

    def test_remote_only_base_ref_fetches(self, tmp_path, chdir):
        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git("init", "--bare", "-b", "develop", cwd=remote)
        repo = tmp_path / "repo"
        _init_repo(repo)
        _git("remote", "add", "origin", str(remote), cwd=repo)
        _git("push", "origin", "develop", cwd=repo)
        integ = _add_branch_with_commit(repo, "feat/integration")
        _git("push", "origin", "feat/integration", cwd=repo)
        # Forget the branch locally and its remote-tracking ref -> remote-only.
        _git("branch", "-D", "feat/integration", cwd=repo)
        _git("branch", "-dr", "origin/feat/integration", cwd=repo)
        chdir(repo)
        assert not branch_exists("feat/integration")
        assert not branch_exists("origin/feat/integration")

        create_branch("feat/sub", base_ref="feat/integration")
        assert current_branch() == "feat/sub"
        assert _rev("HEAD", repo) == integ
        assert not _has_upstream("feat/sub", repo)  # --no-track

    def test_missing_base_ref_raises_and_creates_nothing(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)  # no origin remote -> fetch fails
        chdir(repo)
        with pytest.raises(GitError):
            create_branch("feat/sub", base_ref="no/such/branch")
        assert not branch_exists("feat/sub")

    def test_duplicate_branch_raises(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        chdir(repo)
        create_branch("feat/sub")
        _git("checkout", "develop", cwd=repo)
        with pytest.raises(GitError):
            create_branch("feat/sub")


class TestCreateWorktreeBaseRef:
    def test_none_back_compat(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        chdir(repo)
        wt = tmp_path / "wt"
        create_worktree(str(wt), "feat/sub")
        assert (wt / ".git").exists()
        assert _rev("HEAD", wt) == _rev("develop", repo)

    def test_local_base_ref(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        integ = _add_branch_with_commit(repo, "feat/integration")
        chdir(repo)
        wt = tmp_path / "wt"
        create_worktree(str(wt), "feat/sub", base_ref="feat/integration")
        assert (wt / ".git").exists()
        assert _rev("HEAD", wt) == integ
        assert _is_ancestor("feat/integration", "feat/sub", repo)
        assert not _has_upstream("feat/sub", repo)

    def test_remote_only_base_ref_fetches(self, tmp_path, chdir):
        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git("init", "--bare", "-b", "develop", cwd=remote)
        repo = tmp_path / "repo"
        _init_repo(repo)
        _git("remote", "add", "origin", str(remote), cwd=repo)
        _git("push", "origin", "develop", cwd=repo)
        integ = _add_branch_with_commit(repo, "feat/integration")
        _git("push", "origin", "feat/integration", cwd=repo)
        _git("branch", "-D", "feat/integration", cwd=repo)
        _git("branch", "-dr", "origin/feat/integration", cwd=repo)
        chdir(repo)
        wt = tmp_path / "wt"
        create_worktree(str(wt), "feat/sub", base_ref="feat/integration")
        assert _rev("HEAD", wt) == integ
        assert not _has_upstream("feat/sub", repo)

    def test_missing_base_ref_raises(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        chdir(repo)
        wt = tmp_path / "wt"
        with pytest.raises(GitError):
            create_worktree(str(wt), "feat/sub", base_ref="no/such/branch")
        assert not branch_exists("feat/sub")


def _repo_with_remote(tmp_path: Path) -> Path:
    """Repo with an 'origin' bare remote and develop pushed (clean_up needs fetch)."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git("init", "--bare", "-b", "develop", cwd=remote)
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "develop", cwd=repo)
    return repo


def _merged_branch(repo: Path, branch: str) -> None:
    """Create `branch` with a commit and merge it into develop (so it is stale-merged)."""
    _git("checkout", "-b", branch, cwd=repo)
    (repo / branch.replace("/", "_")).write_text("x")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", f"on {branch}", cwd=repo)
    _git("checkout", "develop", cwd=repo)
    _git("merge", "--no-ff", branch, "-m", f"merge {branch}", cwd=repo)


def _gone_branch(repo: Path, branch: str) -> None:
    """Create `branch` with a UNIQUE commit (not merged), push with upstream, then
    delete the remote ref so its upstream is gone — stale via the gone path only."""
    _git("checkout", "-b", branch, cwd=repo)
    (repo / branch.replace("/", "_")).write_text("x")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", f"on {branch}", cwd=repo)
    _git("push", "-u", "origin", branch, cwd=repo)
    _git("push", "origin", "--delete", branch, cwd=repo)
    _git("checkout", "develop", cwd=repo)


class TestCleanUpStaleBranchesGuard:
    def test_declared_base_protected_others_deleted(self, tmp_path, chdir):
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/integration")  # declared as base by a plan
        _merged_branch(repo, "feat/orphan")        # not declared

        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()
        (plan_dir / "plan-364.md").write_text(
            "---\nbase_branch: feat/integration\nparent_issue: 364\n---\n# Plan: x"
        )
        (plan_dir / "plan-1.md").write_text("# Plan: no frontmatter")

        chdir(repo)
        result = clean_up_stale_branches(plan_dir=plan_dir)

        assert "feat/integration" in result["protected_branches"]
        assert "feat/integration" not in result["deleted_branches"]
        assert branch_exists("feat/integration")
        assert "feat/orphan" in result["deleted_branches"]
        assert not branch_exists("feat/orphan")

    def test_without_plan_dir_merged_branch_is_deleted(self, tmp_path, chdir):
        # Proves the guard is what protects it: same branch, no plan_dir -> deleted.
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/integration")
        chdir(repo)
        result = clean_up_stale_branches()
        assert "feat/integration" in result["deleted_branches"]
        assert result["protected_branches"] == []

    def test_declared_base_protected_on_gone_path(self, tmp_path, chdir):
        # The primary real-world trigger: an integration branch whose remote was
        # deleted (upstream gone), NOT merged into develop. Guard must protect it.
        repo = _repo_with_remote(tmp_path)
        _gone_branch(repo, "feat/integration")

        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()
        (plan_dir / "plan-364.md").write_text(
            "---\nbase_branch: feat/integration\n---\n# Plan: x"
        )

        chdir(repo)
        result = clean_up_stale_branches(plan_dir=plan_dir)
        assert "feat/integration" in result["protected_branches"]
        assert "feat/integration" not in result["deleted_branches"]
        assert branch_exists("feat/integration")

    def test_gone_branch_deleted_without_plan_dir(self, tmp_path, chdir):
        repo = _repo_with_remote(tmp_path)
        _gone_branch(repo, "feat/integration")
        chdir(repo)
        result = clean_up_stale_branches()
        assert "feat/integration" in result["deleted_branches"]
        assert not branch_exists("feat/integration")


class TestCleanUpDirtyWorktreeGuard:
    """A stale branch whose worktree has uncommitted work must survive intact.

    `worktree remove --force` deletes the working tree unconditionally, so
    without this guard `/clean` silently destroys in-progress work — the exact
    hazard a human blocked by hand in a prior session.
    """

    def test_dirty_worktree_is_skipped_and_preserved(self, tmp_path, chdir):
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/dirty")  # stale (merged into develop)
        wt = tmp_path / "wt-dirty"
        _git("worktree", "add", str(wt), "feat/dirty", cwd=repo)
        precious = wt / "uncommitted.txt"
        precious.write_text("work in progress")  # untracked -> dirty

        chdir(repo)
        result = clean_up_stale_branches()

        assert "feat/dirty" in result["skipped_dirty"]
        assert "feat/dirty" not in result["deleted_branches"]
        assert str(wt) not in result["removed_worktrees"]
        # The whole worktree and its uncommitted file survive.
        assert wt.exists()
        assert precious.read_text() == "work in progress"
        assert branch_exists("feat/dirty")

    def test_dirty_from_tracked_modification_is_skipped(self, tmp_path, chdir):
        # Not only untracked files — a modified tracked file counts as dirty too.
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/dirty")
        wt = tmp_path / "wt-mod"
        _git("worktree", "add", str(wt), "feat/dirty", cwd=repo)
        (wt / "f").write_text("mutated")  # 'f' is the tracked seed file

        chdir(repo)
        result = clean_up_stale_branches()

        assert "feat/dirty" in result["skipped_dirty"]
        assert wt.exists()
        assert branch_exists("feat/dirty")

    def test_clean_worktree_is_still_removed(self, tmp_path, chdir):
        # The guard must not over-reach: a clean stale worktree is removed as before.
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/clean")
        wt = tmp_path / "wt-clean"
        _git("worktree", "add", str(wt), "feat/clean", cwd=repo)

        chdir(repo)
        result = clean_up_stale_branches()

        assert result["skipped_dirty"] == []
        assert str(wt) in result["removed_worktrees"]
        assert not wt.exists()
        assert "feat/clean" in result["deleted_branches"]
        assert not branch_exists("feat/clean")

    def test_status_check_failure_fails_closed(self, tmp_path, chdir, monkeypatch):
        # If `git status` itself errors (a stale index.lock, permission, an
        # unavailable mount), it exits non-zero with EMPTY stdout. Treating that
        # as "clean" would force-remove a worktree that still holds work. The
        # guard must fail closed: unknown state == dirty, never removed.
        import harness_core.git as hc_git

        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/locked")
        wt = tmp_path / "wt-locked"
        _git("worktree", "add", str(wt), "feat/locked", cwd=repo)
        precious = wt / "wip.txt"
        precious.write_text("uncommitted work")

        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["git", "-C", str(wt)] and "status" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 128, stdout="", stderr="fatal: index.lock exists"
                )
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(hc_git.subprocess, "run", fake_run)

        chdir(repo)
        result = clean_up_stale_branches()

        assert "feat/locked" in result["skipped_dirty"]
        assert wt.exists()
        assert precious.read_text() == "uncommitted work"  # NOT force-removed
        assert branch_exists("feat/locked")
        assert any("status check failed" in warning for warning in result["warnings"])


class TestMainWorktreeRoot:
    def test_main_worktree_root_from_main(self, tmp_path, chdir, _no_cache):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        (repo / "seed").write_text("x")
        _git("add", "seed", cwd=repo)
        _git("commit", "-m", "init", cwd=repo)

        chdir(repo)
        assert main_worktree_root() == repo.resolve()

    def test_main_worktree_root_from_worktree(self, tmp_path, chdir, _no_cache):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        (repo / "seed").write_text("x")
        _git("add", "seed", cwd=repo)
        _git("commit", "-m", "init", cwd=repo)

        wt = tmp_path / "wt"
        _git("worktree", "add", "-b", "feature", str(wt), cwd=repo)

        chdir(wt)
        assert main_worktree_root() == repo.resolve()

    def test_main_worktree_root_non_git_fallback(self, tmp_path, chdir, _no_cache):
        outside = tmp_path / "outside"
        outside.mkdir()
        chdir(outside)
        assert main_worktree_root() == outside.resolve()

    def test_main_worktree_root_bare_repo(self, tmp_path, chdir, _no_cache):
        # Bare repos have no working tree, so `--git-common-dir` returns `.`
        # and `--is-bare-repository` returns "true". The helper must short-
        # circuit on the bare check and return CWD; otherwise it would call
        # `Path(".").resolve().parent` and climb one directory above the repo.
        bare = tmp_path / "bare.git"
        bare.mkdir()
        _git("init", "--bare", cwd=bare)
        chdir(bare)
        assert main_worktree_root() == bare.resolve()
