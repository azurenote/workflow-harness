"""Tests for harness_core.git module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from harness_core.git import (
    derive_branch_name,
    main_worktree_root,
    worktree_root,
    create_branch,
    create_worktree,
    branch_exists,
    current_branch,
    clean_up_stale_branches,
    GitError,
    MainWorktreeUnresolvedError,
)


class TestDeriveBranchName:
    def test_simple_title(self):
        result = derive_branch_name(42, "Upbit JWT Auth")
        assert result == "feat/issue-42-upbit-jwt-auth"

    def test_special_characters_stripped(self):
        result = derive_branch_name(
            153, "Harness Architecture Redesign for Downstream Workflows"
        )
        assert result == "feat/issue-153-harness-architecture-redesign-for-downstream-workf"

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


def _linked_feature(tmp_path: Path) -> tuple[Path, Path]:
    """Main checkout on develop, plus a linked worktree on feat/x one commit ahead.

    The extra commit is what makes "branched from the main checkout's HEAD" a
    claim that can fail: without it, feat/x and develop are the same commit.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    linked = tmp_path / "linked"
    _git("worktree", "add", "-b", "feat/x", str(linked), cwd=repo)
    (linked / "x").write_text("x")
    _git("add", ".", cwd=linked)
    _git("commit", "-m", "on feat/x", cwd=linked)
    return repo, linked


def _main_rooted_failures(tmp_path: Path, chdir) -> list[str]:
    """Call create_worktree with a relative path from a linked worktree; list what is wrong."""
    repo, linked = _linked_feature(tmp_path)
    chdir(linked)
    got = create_worktree(".claude/worktrees/p-issue-1", "feat/issue-1-y")
    want = os.path.realpath(repo / ".claude" / "worktrees" / "p-issue-1")
    failures = []
    if os.path.realpath(got) != want:
        failures.append(f"created at {got}, expected {want}")
    if not os.path.isabs(got):
        failures.append(f"returned a relative path: {got}")
    if (linked / ".claude").exists():
        failures.append("nested under the linked worktree")
    head = _rev("feat/issue-1-y", repo)
    if head != _rev("develop", repo) or head == _rev("feat/x", repo):
        failures.append("did not branch from the main checkout's HEAD")
    return failures


class TestCreateWorktreeMainRooted:
    """#43: the worktree is placed and cut from the main checkout, whatever the CWD."""

    @pytest.fixture(autouse=True)
    def _isolated_git_config(self, tmp_path, monkeypatch):
        # The host's config (commit.gpgsign, branch.autoSetupMerge, ...) must
        # not decide these rows; create_worktree's own git calls read it too.
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home"))

    def test_relative_path_from_a_linked_worktree(self, tmp_path, chdir):
        assert _main_rooted_failures(tmp_path, chdir) == []

    def test_without_the_main_root_the_scenario_fails(self, tmp_path, chdir, monkeypatch):
        # Mutation: drop `-C <root>` and let git run in the CWD, as before #43.
        import harness_core.git as hgit
        real = hgit._run_git

        def cwd_rooted(*args: str):
            if args[:1] == ("-C",) and "worktree" in args:
                args = args[2:]
            return real(*args)

        monkeypatch.setattr(hgit, "_run_git", cwd_rooted)
        # The path is already absolute under the root, so only the branch point
        # can tell — which is why the scenario gives feat/x a commit of its own.
        assert "did not branch from the main checkout's HEAD" in _main_rooted_failures(tmp_path, chdir)

    def test_relative_path_from_a_subdirectory_of_main(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        (repo / "sub" / "dir").mkdir(parents=True)
        chdir(repo / "sub" / "dir")
        got = create_worktree(".claude/worktrees/p-issue-2", "feat/issue-2-y")
        assert os.path.realpath(got) == os.path.realpath(repo / ".claude" / "worktrees" / "p-issue-2")
        assert not (repo / "sub" / "dir" / ".claude").exists()

    def test_home_is_expanded(self, tmp_path, chdir, monkeypatch):
        repo = tmp_path / "repo"
        _init_repo(repo)
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        chdir(repo)
        got = create_worktree("~/wt", "feat/home")
        assert os.path.realpath(got) == os.path.realpath(home / "wt")

    def test_dot_dot_is_normalized(self, tmp_path, chdir):
        repo = tmp_path / "repo"
        _init_repo(repo)
        chdir(repo)
        got = create_worktree("../beside", "feat/beside")
        assert ".." not in Path(got).parts
        assert os.path.realpath(got) == os.path.realpath(tmp_path / "beside")

    def test_undeclared_base_sets_no_upstream(self, tmp_path, chdir, monkeypatch):
        # branch.autoSetupMerge=always would make the main checkout's branch the
        # new branch's upstream; --no-track on this path too keeps it off.
        repo, linked = _linked_feature(tmp_path)
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "branch.autoSetupMerge")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
        chdir(linked)
        create_worktree(".claude/worktrees/p-issue-7", "feat/untracked")
        assert not _has_upstream("feat/untracked", repo)

    def test_declared_base_from_a_linked_worktree(self, tmp_path, chdir, monkeypatch):
        import harness_core.git as hgit
        repo, linked = _linked_feature(tmp_path)
        integ = _add_branch_with_commit(repo, "feat/integration")
        chdir(linked)
        real = hgit._run_git
        calls: list[tuple[str, ...]] = []
        monkeypatch.setattr(hgit, "_run_git", lambda *a: (calls.append(a), real(*a))[1])
        got = create_worktree(".claude/worktrees/p-issue-3", "feat/sub", base_ref="feat/integration")
        # Unobservable from the result (absolute path, explicit start point),
        # so pinned on the call: every `worktree add` runs at the main root.
        adds = [c for c in calls if "worktree" in c]
        assert adds and all(c[:2] == ("-C", str(main_worktree_root())) for c in adds), adds
        assert os.path.realpath(got) == os.path.realpath(repo / ".claude" / "worktrees" / "p-issue-3")
        assert _rev("feat/sub", repo) == integ
        assert not _has_upstream("feat/sub", repo)

    def test_old_git_retry_stays_main_rooted(self, tmp_path, chdir, monkeypatch):
        # A git that rejects `--no-track` on `worktree add` takes the retry path:
        # it must stay at the main root, and unset the upstream by absolute path.
        import harness_core.git as hgit
        repo, linked = _linked_feature(tmp_path)
        _add_branch_with_commit(repo, "feat/integration")
        chdir(linked)
        real = hgit._run_git
        calls: list[tuple[str, ...]] = []

        def old_git(*args: str):
            calls.append(args)
            if "--no-track" in args:
                raise GitError(" ".join(args), "error: unknown option `no-track'")
            return real(*args)

        monkeypatch.setattr(hgit, "_run_git", old_git)
        got = create_worktree(".claude/worktrees/p-issue-4", "feat/sub", base_ref="feat/integration")
        root = str(main_worktree_root())
        retry = [c for c in calls if "worktree" in c and "--no-track" not in c]
        assert retry and retry[0][:2] == ("-C", root), f"the retry left the main root: {retry}"
        unset = [c for c in calls if "--unset-upstream" in c]
        assert unset and os.path.isabs(unset[0][1]) and unset[0][1] == got, unset

    def test_bare_linked_worktree_stops_before_any_fetch(self, tmp_path, chdir):
        seed = tmp_path / "seed"
        _init_repo(seed, default_branch="main")
        bare = tmp_path / "bare.git"
        _git("clone", "--bare", str(seed), str(bare), cwd=tmp_path)
        # A bare clone has no fetch refspec; give it one, so a fetch that ran
        # would leave origin/feat/remote-only behind for the check below.
        _git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*", cwd=bare)
        _add_branch_with_commit(seed, "feat/remote-only", from_branch="main")
        wt = tmp_path / "wt"
        _git("worktree", "add", str(wt), "main", cwd=bare)
        chdir(wt)
        with pytest.raises(MainWorktreeUnresolvedError):
            create_worktree(".claude/worktrees/p-issue-5", "feat/sub", base_ref="feat/remote-only")
        assert not branch_exists("feat/sub")
        assert not branch_exists("origin/feat/remote-only")
        # A fetch from a linked worktree writes FETCH_HEAD under its own git dir.
        assert not list(bare.rglob("FETCH_HEAD")), list(bare.rglob("FETCH_HEAD"))
        assert not (wt / ".claude").exists()

    def test_cli_prints_the_absolute_path(self, tmp_path, chdir, capsys):
        from harness_core.cli import build_core_parser, dispatch
        repo, linked = _linked_feature(tmp_path)
        chdir(linked)
        assert dispatch(build_core_parser(), ["create-worktree", ".claude/worktrees/p-issue-6", "feat/cli"]) == 0
        out = capsys.readouterr().out.strip()
        assert os.path.isabs(out)
        assert os.path.realpath(out) == os.path.realpath(repo / ".claude" / "worktrees" / "p-issue-6")


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
        # A bare repo has no main work tree. The old rule returned CWD here,
        # and the `--git-common-dir` parent would climb above the repo; both
        # are directories that exist and are wrong, so the helper stops (#50).
        bare = tmp_path / "bare.git"
        bare.mkdir()
        _git("init", "--bare", cwd=bare)
        chdir(bare)
        with pytest.raises(MainWorktreeUnresolvedError, match="bare"):
            main_worktree_root()


class TestMainWorktreeRootLayouts:
    """The canonical rule per layout (#50): first worktree entry, then its toplevel.

    The shell block in skills/_shared/references/worktree.md follows the same
    rule; tests/test_skill_docs.py runs both against one matrix.
    """

    @pytest.fixture(autouse=True)
    def _no_git_env(self, monkeypatch):
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            monkeypatch.delenv(var, raising=False)

    def _commit(self, repo: Path) -> None:
        _git("commit", "--allow-empty", "-m", "init", cwd=repo)

    def test_submodule_and_its_linked_worktree_answer_the_submodule(self, tmp_path, chdir, _no_cache):
        tmp_path = tmp_path.resolve()
        src = tmp_path / "src"
        src.mkdir()
        _git("init", "-b", "main", cwd=src)
        self._commit(src)
        sup = tmp_path / "super"
        sup.mkdir()
        _git("init", "-b", "main", cwd=sup)
        self._commit(sup)
        _git("-c", "protocol.file.allow=always", "submodule", "add", str(src), "sub", cwd=sup)
        _git("worktree", "add", "-b", "feature", str(tmp_path / "sub-wt"), cwd=sup / "sub")
        for where in (sup / "sub", tmp_path / "sub-wt"):
            chdir(where)
            assert main_worktree_root() == (sup / "sub").resolve()
        chdir(sup)
        assert main_worktree_root() == sup.resolve()

    def test_separate_git_dir_stops_from_main_and_linked(self, tmp_path, chdir, _no_cache):
        tmp_path = tmp_path.resolve()
        main = tmp_path / "main"
        _git("init", "-b", "main", f"--separate-git-dir={tmp_path / 'main.git'}", str(main), cwd=tmp_path)
        self._commit(main)
        _git("worktree", "add", "-b", "feature", str(tmp_path / "wt"), cwd=main)
        for where in (main, tmp_path / "wt"):
            chdir(where)
            try:
                root = main_worktree_root()
            except MainWorktreeUnresolvedError as error:
                assert "separate-git-dir" in str(error)
            else:
                # A git that lists the work tree first would answer it; any
                # other directory is the wrong-but-existing answer this guards.
                assert root == main.resolve()

    def test_bare_with_linked_worktree_stops(self, tmp_path, chdir, _no_cache):
        tmp_path = tmp_path.resolve()
        seed = tmp_path / "seed"
        seed.mkdir()
        _git("init", "-b", "main", cwd=seed)
        self._commit(seed)
        _git("clone", "--bare", str(seed), str(tmp_path / "bare.git"), cwd=tmp_path)
        _git("worktree", "add", str(tmp_path / "wt"), "main", cwd=tmp_path / "bare.git")
        chdir(tmp_path / "wt")
        with pytest.raises(MainWorktreeUnresolvedError):
            main_worktree_root()

    def test_failed_listing_inside_a_repo_stops(self, tmp_path, chdir, _no_cache, monkeypatch):
        """Only a CWD outside any repository falls back to CWD."""
        tmp_path = tmp_path.resolve()
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        self._commit(repo)
        real = subprocess.run

        def fake(cmd, *args, **kwargs):
            if cmd[:3] == ["git", "worktree", "list"]:
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake)
        chdir(repo)
        with pytest.raises(MainWorktreeUnresolvedError, match="boom"):
            main_worktree_root()

    def test_untrusted_repository_stops_instead_of_answering_cwd(self, tmp_path, chdir, _no_cache, monkeypatch):
        """safe.directory refusal fails like 'not a repo' but must not fall back to CWD."""
        tmp_path = tmp_path.resolve()
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        self._commit(repo)
        _git("worktree", "add", "-b", "feature", str(tmp_path / "wt"), cwd=repo)
        real = subprocess.run
        refused = "fatal: detected dubious ownership in repository at '%s'\n" % repo

        def fake(cmd, *args, **kwargs):
            if cmd[:3] in (["git", "worktree", "list"], ["git", "rev-parse", "--git-dir"]):
                return subprocess.CompletedProcess(cmd, 128, "", refused)
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake)
        chdir(tmp_path / "wt")
        with pytest.raises(MainWorktreeUnresolvedError):
            main_worktree_root()


class TestWorktreeRoot:
    """The tracked-content root: the working tree that contains CWD.

    `main_worktree_root()` answers "where does gitignored state live"; this
    answers "which checkout's committed files are in play". In a linked
    worktree the two differ, and reading tracked config from the first is how
    code and config ended up on different branches (#23).
    """

    @pytest.fixture(autouse=True)
    def _no_git_env(self, monkeypatch):
        # Under a git hook these point at the outer repo, and `--show-toplevel`
        # then answers for it instead of for CWD.
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            monkeypatch.delenv(var, raising=False)

    def _repo_with_worktree(self, tmp_path: Path) -> tuple[Path, Path]:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        (repo / "sub").mkdir()
        (repo / "sub" / "seed").write_text("x")
        _git("add", "sub/seed", cwd=repo)
        _git("commit", "-m", "init", cwd=repo)
        wt = tmp_path / "wt"
        _git("worktree", "add", "-b", "feature", str(wt), cwd=repo)
        return repo, wt

    def test_from_main_checkout(self, tmp_path, chdir):
        repo, _ = self._repo_with_worktree(tmp_path)
        chdir(repo)
        assert worktree_root() == repo.resolve()

    def test_from_linked_worktree_is_the_worktree_not_main(self, tmp_path, chdir):
        repo, wt = self._repo_with_worktree(tmp_path)
        chdir(wt)
        assert worktree_root() == wt.resolve()
        assert main_worktree_root() == repo.resolve()

    def test_from_subdirectory_is_the_worktree_root(self, tmp_path, chdir):
        _, wt = self._repo_with_worktree(tmp_path)
        chdir(wt / "sub")
        assert worktree_root() == wt.resolve()

    def test_follows_cwd_without_cache_clearing(self, tmp_path, monkeypatch):
        # monkeypatch.chdir, not the `chdir` fixture: nothing is cleared here,
        # so a cache on worktree_root() would return the first answer twice.
        repo, wt = self._repo_with_worktree(tmp_path)
        monkeypatch.chdir(repo)
        first = worktree_root()
        monkeypatch.chdir(wt)
        assert first == repo.resolve()
        assert worktree_root() == wt.resolve()

    def test_non_git_fallback(self, tmp_path, chdir):
        outside = tmp_path / "outside"
        outside.mkdir()
        chdir(outside)
        assert worktree_root() == outside.resolve()

    def test_bare_repo_fallback(self, tmp_path, chdir):
        # `--show-toplevel` fails in a bare repo (no working tree); the failure
        # path, not a success value, is what lands on CWD.
        bare = tmp_path / "bare.git"
        bare.mkdir()
        _git("init", "--bare", cwd=bare)
        chdir(bare)
        assert worktree_root() == bare.resolve()


# ---------------------------------------------------------------------------
# #74 — a git failure in a core command ends REFUSED, INCOMPLETE or UNKNOWN,
# never CRASH. What was measured on git 2.54 decides each row: an existing
# path or an unwritable parent makes `worktree add -b` leave the branch, a
# failing post-checkout hook leaves the branch (and the worktree), and a
# pre-push hook fails a push whose ref has already landed.


@pytest.fixture
def _i74_repo(tmp_path, monkeypatch, chdir):
    """A repo on main with the host's git config cut off, as the CWD."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    _init_repo(repo, default_branch="main")
    chdir(repo)
    return repo


def _i74_failing_hook(repo: Path, name: str) -> None:
    """Point this repo's hooksPath at a dir whose ``name`` hook exits 1."""
    hooks = repo.parent / f"hooks-{repo.name}"
    hooks.mkdir(exist_ok=True)
    hook = hooks / name
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _git("config", "core.hooksPath", str(hooks), cwd=repo)


def _i74_run(argv: list[str], capsys) -> tuple[int, str, str]:
    from harness_core.cli import build_core_parser, dispatch
    capsys.readouterr()
    rc = dispatch(build_core_parser(), argv)
    out, err = capsys.readouterr()
    return rc, out, err


def _i74_branch(name: str, cwd: Path) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"],
        cwd=str(cwd), capture_output=True,
    ).returncode == 0


def _i74_registered(path: Path, cwd: Path) -> bool:
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], cwd=str(cwd), capture_output=True, text=True,
    ).stdout
    want = os.path.realpath(path)
    return any(l.startswith("worktree ") and os.path.realpath(l[9:]) == want for l in listing.splitlines())


def _i74_refused(rc: int, out: str, err: str) -> str:
    """Assert the REFUSED shape — one stderr line, empty stdout — and return the line."""
    from harness_core.exitcodes import ExitCode
    assert rc == ExitCode.REFUSED, (rc, out, err)
    assert out == "", out
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    return lines[0]


class TestI74CreateBranch:
    def test_existing_branch_is_refused(self, _i74_repo, capsys):
        _git("branch", "x", cwd=_i74_repo)
        line = _i74_refused(*_i74_run(["create-branch", "x"], capsys))
        assert "'x' already exists" in line
        assert current_branch() == "main"

    def test_a_tag_of_that_name_is_not_a_branch(self, _i74_repo, capsys):
        from harness_core.exitcodes import ExitCode
        _git("tag", "x", cwd=_i74_repo)
        rc, out, _ = _i74_run(["create-branch", "x"], capsys)
        assert rc == ExitCode.OK and out.strip() == "x"
        head = subprocess.run(["git", "symbolic-ref", "HEAD"], cwd=str(_i74_repo),
                              capture_output=True, text=True).stdout.strip()
        assert head == "refs/heads/x"

    def test_unresolvable_base_is_refused(self, _i74_repo, capsys):
        line = _i74_refused(*_i74_run(["create-branch", "x", "--base-ref", "no/such"], capsys))
        assert "no/such" in line
        assert not _i74_branch("x", _i74_repo)

    def test_checkout_that_creates_nothing_is_refused(self, _i74_repo, capsys):
        _add_branch_with_commit(_i74_repo, "other", from_branch="main")
        (_i74_repo / "other").write_text("dirty")  # untracked, and `other` tracks it
        line = _i74_refused(*_i74_run(["create-branch", "x", "--base-ref", "other"], capsys))
        assert "created nothing" in line
        assert not _i74_branch("x", _i74_repo)

    def test_hook_failure_after_the_branch_is_incomplete(self, _i74_repo, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        _i74_failing_hook(_i74_repo, "post-checkout")
        rc, out, _ = _i74_run(["create-branch", "x"], capsys)
        assert rc == ExitCode.INCOMPLETE
        done = json.loads(out)
        assert set(done) == {"branch", "branch_created", "checked_out", "error"}
        assert done["branch"] == "x" and done["branch_created"] is True
        # What the JSON says is what is there.
        assert _i74_branch("x", _i74_repo)
        assert done["checked_out"] == current_branch()


class TestI74CreateWorktree:
    def _refused_and_no_branch(self, repo, capsys, path, branch="b") -> str:
        line = _i74_refused(*_i74_run(["create-worktree", str(path), branch], capsys))
        assert not _i74_branch(branch, repo), "a refusal left the branch behind"
        return line

    def test_nonempty_path_is_refused_before_the_branch(self, _i74_repo, tmp_path, capsys):
        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / "y").write_text("y")
        assert "already exists" in self._refused_and_no_branch(_i74_repo, capsys, wt)

    def test_dangling_link_is_refused(self, _i74_repo, tmp_path, capsys):
        wt = tmp_path / "wt"
        wt.symlink_to(tmp_path / "nowhere")
        self._refused_and_no_branch(_i74_repo, capsys, wt)

    def test_empty_directory_is_refused(self, _i74_repo, tmp_path, capsys):
        # git would take it; refusing it keeps "there after a failure" meaning "ours".
        wt = tmp_path / "wt"
        wt.mkdir()
        self._refused_and_no_branch(_i74_repo, capsys, wt)

    def test_registered_path_with_no_directory_is_refused(self, _i74_repo, tmp_path, capsys):
        import shutil
        wt = tmp_path / "wt"
        _git("worktree", "add", "-b", "b0", str(wt), cwd=_i74_repo)
        shutil.rmtree(wt)
        self._refused_and_no_branch(_i74_repo, capsys, wt)

    def test_existing_branch_is_refused_before_the_path(self, _i74_repo, tmp_path, capsys):
        _git("branch", "b", cwd=_i74_repo)
        wt = tmp_path / "wt"
        _i74_refused(*_i74_run(["create-worktree", str(wt), "b"], capsys))
        assert not os.path.lexists(wt)

    def test_unresolvable_base_creates_nothing(self, _i74_repo, tmp_path, capsys):
        wt = tmp_path / "wt"
        line = _i74_refused(*_i74_run(["create-worktree", str(wt), "b", "--base-ref", "no/such"], capsys))
        assert "no/such" in line
        assert not _i74_branch("b", _i74_repo) and not os.path.lexists(wt)

    def test_nothing_left_behind_is_refused(self, _i74_repo, tmp_path, capsys):
        # An invalid name fails before git makes anything: the read-back finds nothing.
        wt = tmp_path / "wt"
        line = self._refused_and_no_branch(_i74_repo, capsys, wt, "bad..name")
        assert "created nothing" in line
        assert not os.path.lexists(wt) and not _i74_registered(wt, _i74_repo)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root writes through a read-only directory")
    def test_unwritable_parent_leaves_the_branch_and_is_incomplete(self, _i74_repo, tmp_path, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        ro = tmp_path / "ro"
        ro.mkdir()
        wt = ro / "wt"
        ro.chmod(0o555)
        try:
            rc, out, _ = _i74_run(["create-worktree", str(wt), "b"], capsys)
        finally:
            ro.chmod(0o755)
        assert rc == ExitCode.INCOMPLETE
        done = json.loads(out)
        assert set(done) == {"branch", "worktree", "branch_created", "worktree_created", "error"}
        assert (done["branch_created"], done["worktree_created"]) == (True, False)
        assert done["branch_created"] == _i74_branch("b", _i74_repo)
        assert done["worktree_created"] == (os.path.lexists(wt) or _i74_registered(wt, _i74_repo))

    def test_hook_failure_leaves_both_and_is_incomplete(self, _i74_repo, tmp_path, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        _i74_failing_hook(_i74_repo, "post-checkout")
        wt = tmp_path / "wt"
        rc, out, _ = _i74_run(["create-worktree", str(wt), "b"], capsys)
        assert rc == ExitCode.INCOMPLETE
        done = json.loads(out)
        assert (done["branch_created"], done["worktree_created"]) == (True, True)
        assert done["branch_created"] == _i74_branch("b", _i74_repo)
        assert done["worktree_created"] == (os.path.lexists(wt) or _i74_registered(wt, _i74_repo))
        assert os.path.realpath(done["worktree"]) == os.path.realpath(wt)

    def test_failed_fallback_retry_goes_through_the_read_back(self, _i74_repo, tmp_path, capsys, monkeypatch):
        import harness_core.git as hgit
        real = hgit._run_git

        def old_git(*args: str, **kwargs):
            if "worktree" in args and "--no-track" in args:
                raise GitError(" ".join(args), "error: unknown option `no-track'")
            if "worktree" in args:
                raise GitError(" ".join(args), "fatal: the retry failed too")
            return real(*args, **kwargs)

        monkeypatch.setattr(hgit, "_run_git", old_git)
        wt = tmp_path / "wt"
        line = self._refused_and_no_branch(_i74_repo, capsys, wt)
        # Both failures are reported, the first first: it says why the retry ran.
        assert "unknown option" in line and "retry failed" in line
        assert line.index("unknown option") < line.index("retry failed")


def _i74_remote(tmp_path: Path, repo: Path, name: str = "remote.git") -> Path:
    remote = tmp_path / name
    remote.mkdir()
    _git("init", "--bare", "-b", "main", cwd=remote)
    return remote


def _i74_pushed(tmp_path: Path, repo: Path) -> Path:
    """origin is a bare remote holding main and branch `b` at the local commit."""
    remote = _i74_remote(tmp_path, repo)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "origin", "main", cwd=repo)
    _add_branch_with_commit(repo, "b", from_branch="main")
    return remote


def _i74_git_calls(monkeypatch) -> list[tuple[list[str], dict | None]]:
    """Record every subprocess.run the git module makes: argv and env."""
    import harness_core.git as hgit
    real = subprocess.run
    calls: list[tuple[list[str], dict | None]] = []

    def spy(cmd, *args, **kwargs):
        calls.append((list(cmd), kwargs.get("env")))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(hgit.subprocess, "run", spy)
    return calls


def _i74_ran(calls, word: str) -> bool:
    return any(word in cmd for cmd, _ in calls)


class TestI74PushBranch:
    def test_non_fast_forward_is_refused_without_a_read_back(self, _i74_repo, tmp_path, capsys, monkeypatch):
        remote = _i74_pushed(tmp_path, _i74_repo)
        other = tmp_path / "other"
        _git("clone", "-q", str(remote), str(other), cwd=tmp_path)
        _git("checkout", "-b", "b", cwd=other)
        (other / "o").write_text("o")
        _git("add", ".", cwd=other)
        _git("commit", "-m", "theirs", cwd=other)
        _git("push", "origin", "b", cwd=other)
        calls = _i74_git_calls(monkeypatch)
        line = _i74_refused(*_i74_run(["push-branch", "b"], capsys))
        assert "rejected" in line and "hint:" not in line
        assert _i74_ran(calls, "push") and not _i74_ran(calls, "ls-remote"), calls

    def test_no_local_branch_is_refused_before_any_push(self, _i74_repo, tmp_path, capsys, monkeypatch):
        _i74_pushed(tmp_path, _i74_repo)
        calls = _i74_git_calls(monkeypatch)
        line = _i74_refused(*_i74_run(["push-branch", "nope"], capsys))
        assert "nope" in line
        assert not _i74_ran(calls, "push")

    def test_failure_after_the_ref_landed_is_ok(self, _i74_repo, tmp_path, capsys, monkeypatch):
        import json
        from harness_core.exitcodes import ExitCode
        _i74_pushed(tmp_path, _i74_repo)
        _git("push", "origin", "b", cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        calls = _i74_git_calls(monkeypatch)
        rc, out, err = _i74_run(["push-branch", "b"], capsys)
        assert rc == ExitCode.OK
        assert json.loads(out) == {"branch": "b"}
        assert len(err.strip().splitlines()) == 1 and "already has b" in err
        assert _i74_ran(calls, "ls-remote")

    def test_failure_with_the_branch_absent_is_refused(self, _i74_repo, tmp_path, capsys):
        _i74_pushed(tmp_path, _i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        line = _i74_refused(*_i74_run(["push-branch", "b"], capsys))
        assert "has no such branch" in line

    def test_failure_with_another_commit_there_is_refused(self, _i74_repo, tmp_path, capsys):
        # origin has `b`, just not the local commit: a branch being there is not OK.
        _i74_pushed(tmp_path, _i74_repo)
        _git("push", "origin", "b", cwd=_i74_repo)
        _git("checkout", "b", cwd=_i74_repo)
        (_i74_repo / "more").write_text("more")
        _git("add", ".", cwd=_i74_repo)
        _git("commit", "-m", "more", cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        line = _i74_refused(*_i74_run(["push-branch", "b"], capsys))
        assert "is at" in line

    def test_unreadable_origin_is_unknown(self, _i74_repo, tmp_path, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        _git("remote", "add", "origin", str(tmp_path / "missing.git"), cwd=_i74_repo)
        _add_branch_with_commit(_i74_repo, "b", from_branch="main")
        rc, out, _ = _i74_run(["push-branch", "b"], capsys)
        assert rc == ExitCode.UNKNOWN
        state = json.loads(out)
        assert set(state) == {"branch", "remote_head", "error"}
        assert state["branch"] == "b" and state["remote_head"] is None and state["error"]

    def test_push_and_read_back_run_in_the_c_locale(self, _i74_repo, tmp_path, capsys, monkeypatch):
        _i74_pushed(tmp_path, _i74_repo)
        _git("push", "origin", "b", cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        calls = _i74_git_calls(monkeypatch)
        _i74_run(["push-branch", "b"], capsys)
        network = [(cmd, env) for cmd, env in calls if "push" in cmd or "ls-remote" in cmd]
        assert {"push", "ls-remote"} <= {w for cmd, _ in network for w in cmd}
        for cmd, env in network:
            assert env is not None and env.get("LC_ALL") == "C", cmd
            assert env.get("PATH") == os.environ["PATH"], f"{cmd}: the environment was replaced, not extended"

    def test_read_back_asks_the_push_url(self, _i74_repo, tmp_path, capsys):
        from harness_core.exitcodes import ExitCode
        _i74_pushed(tmp_path, _i74_repo)  # origin url: `b` absent there
        pushed_to = _i74_remote(tmp_path, _i74_repo, "push.git")
        _git("push", str(pushed_to), "b", cwd=_i74_repo)
        _git("config", "remote.origin.pushurl", str(pushed_to), cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        rc, _, err = _i74_run(["push-branch", "b"], capsys)
        assert rc == ExitCode.OK, err


class TestI74CleanUp:
    def test_failed_fetch_is_refused(self, tmp_path, chdir, capsys):
        repo = tmp_path / "repo"
        _init_repo(repo)
        # With no remote at all `fetch --prune` succeeds; a remote that is gone does not.
        _git("remote", "add", "origin", str(tmp_path / "missing.git"), cwd=repo)
        _merged_branch(repo, "feat/merged")
        chdir(repo)
        line = _i74_refused(*_i74_run(["clean-up"], capsys))
        assert "fetch --prune" in line
        assert branch_exists("feat/merged"), "a refused clean-up deleted something"

    def test_a_failed_deletion_is_incomplete(self, tmp_path, chdir, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/current")
        _git("checkout", "feat/current", cwd=repo)  # the main checkout sits on it
        chdir(repo)
        rc, out, _ = _i74_run(["clean-up"], capsys)
        assert rc == ExitCode.INCOMPLETE
        result = json.loads(out)
        assert result["warnings"] and "feat/current" not in result["deleted_branches"]

    def test_a_failed_status_check_is_incomplete(self, tmp_path, chdir, capsys, monkeypatch):
        import json
        import harness_core.git as hgit
        from harness_core.exitcodes import ExitCode
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/locked")
        wt = tmp_path / "wt-locked"
        _git("worktree", "add", str(wt), "feat/locked", cwd=repo)
        real = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["git", "-C", str(wt)] and "status" in cmd:
                return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: index.lock exists")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(hgit.subprocess, "run", fake_run)
        chdir(repo)
        rc, out, _ = _i74_run(["clean-up"], capsys)
        assert rc == ExitCode.INCOMPLETE
        result = json.loads(out)
        assert "feat/locked" in result["skipped_dirty"]
        assert any("status check failed" in w for w in result["warnings"]), result

    def test_dirty_only_is_ok(self, tmp_path, chdir, capsys):
        import json
        from harness_core.exitcodes import ExitCode
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/dirty")
        wt = tmp_path / "wt-dirty"
        _git("worktree", "add", str(wt), "feat/dirty", cwd=repo)
        (wt / "wip").write_text("wip")
        chdir(repo)
        rc, out, _ = _i74_run(["clean-up"], capsys)
        result = json.loads(out)
        assert rc == ExitCode.OK, result
        assert result["skipped_dirty"] == ["feat/dirty"] and result["warnings"] == []


class TestI74ReviewFixes:
    """What the implementation review found, each measured on a real repository."""

    def test_an_injected_base_is_never_stale(self, tmp_path, chdir, capsys):
        from harness_core.exitcodes import ExitCode
        repo = _repo_with_remote(tmp_path)
        _git("branch", "master", cwd=repo)  # merged into develop, as a fresh base is
        chdir(repo)
        result = clean_up_stale_branches(bases=["develop", "main", "master"])
        assert "master" not in result["deleted_branches"] and branch_exists("master")
        _git("checkout", "master", cwd=repo)
        result = clean_up_stale_branches(bases=["develop", "main", "master"])
        assert result["warnings"] == [], "the checked-out base made every run incomplete"

    def test_the_main_worktree_is_never_removed(self, tmp_path, chdir):
        repo = _repo_with_remote(tmp_path)
        _merged_branch(repo, "feat/current")
        _git("checkout", "feat/current", cwd=repo)
        chdir(repo)
        result = clean_up_stale_branches()
        assert not any("Could not remove worktree" in w for w in result["warnings"]), result
        assert any("feat/current" in w for w in result["warnings"]), result

    def test_an_option_shaped_push_url_is_not_run(self, _i74_repo, tmp_path, capsys, monkeypatch):
        from harness_core.exitcodes import ExitCode
        _i74_pushed(tmp_path, _i74_repo)
        marker = tmp_path / "PWNED"
        _git("config", "remote.origin.pushurl", f"--upload-pack=touch {marker};false", cwd=_i74_repo)
        calls = _i74_git_calls(monkeypatch)
        rc, _, err = _i74_run(["push-branch", "b"], capsys)
        assert not marker.exists(), "the read-back ran the URL as an option"
        reads = [cmd for cmd, _ in calls if "ls-remote" in cmd]
        assert reads and all(cmd[cmd.index("ls-remote") + 1] == "--" for cmd in reads), reads
        assert rc in (ExitCode.REFUSED, ExitCode.UNKNOWN), err

    def test_several_push_urls_are_unknown(self, _i74_repo, tmp_path, capsys):
        from harness_core.exitcodes import ExitCode
        remote = _i74_pushed(tmp_path, _i74_repo)
        second = _i74_remote(tmp_path, _i74_repo, "second.git")
        _git("config", "--add", "remote.origin.pushurl", str(remote), cwd=_i74_repo)
        _git("config", "--add", "remote.origin.pushurl", str(second), cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        rc, out, _ = _i74_run(["push-branch", "b"], capsys)
        assert rc == ExitCode.UNKNOWN, out

    def test_a_tag_is_no_branch_for_the_worktree_either(self, _i74_repo, tmp_path, capsys):
        from harness_core.exitcodes import ExitCode
        _git("tag", "b", cwd=_i74_repo)
        rc, out, err = _i74_run(["create-worktree", str(tmp_path / "wt"), "b"], capsys)
        assert rc == ExitCode.OK, err
        assert _i74_branch("b", _i74_repo)

    def test_a_tag_is_no_branch_for_the_read_back(self, _i74_repo, capsys):
        # A tag named like the branch must not read back as "the branch was made".
        _git("tag", "x", cwd=_i74_repo)
        _add_branch_with_commit(_i74_repo, "other", from_branch="main")
        (_i74_repo / "other").write_text("dirty")
        line = _i74_refused(*_i74_run(["create-branch", "x", "--base-ref", "other"], capsys))
        assert "created nothing" in line

    def test_pre_checks_run_before_any_fetch(self, _i74_repo, tmp_path, capsys, monkeypatch):
        remote = _i74_remote(tmp_path, _i74_repo)
        _git("remote", "add", "origin", str(remote), cwd=_i74_repo)
        _git("push", "origin", "main", cwd=_i74_repo)
        _git("push", "origin", "main:feat/remote-only", cwd=_i74_repo)
        _git("branch", "-dr", "origin/feat/remote-only", cwd=_i74_repo)  # remote-only: resolving it fetches
        _git("branch", "b", cwd=_i74_repo)
        calls = _i74_git_calls(monkeypatch)
        _i74_refused(*_i74_run(["create-worktree", str(tmp_path / "wt"), "b", "--base-ref", "feat/remote-only"], capsys))
        _i74_refused(*_i74_run(["create-branch", "b", "--base-ref", "feat/remote-only"], capsys))
        assert not _i74_ran(calls, "fetch"), [c for c, _ in calls if "fetch" in c]

    def test_one_line_drops_hints_and_keeps_errors(self):
        from harness_core.git import _one_line
        stderr = "hint: Updates were rejected\nhint: see 'git push --help'\nerror: failed to push some refs\nfatal: the end"
        assert _one_line(stderr) == "error: failed to push some refs; fatal: the end"
        assert _one_line("hint: only a hint\nplain words") == "plain words"

    def test_a_push_url_with_a_space_is_read_back(self, _i74_repo, tmp_path, capsys):
        from harness_core.exitcodes import ExitCode
        _i74_pushed(tmp_path, _i74_repo)
        spaced = _i74_remote(tmp_path, _i74_repo, "with space.git")
        _git("push", str(spaced), "b", cwd=_i74_repo)
        _git("config", "remote.origin.pushurl", str(spaced), cwd=_i74_repo)
        _i74_failing_hook(_i74_repo, "pre-push")
        rc, _, err = _i74_run(["push-branch", "b"], capsys)
        assert rc == ExitCode.OK, err
