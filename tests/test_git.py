"""Tests for harness_core.git module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from harness_core.git import derive_branch_name, main_worktree_root


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
