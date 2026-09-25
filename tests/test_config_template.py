"""Contract tests for the rendered project config template.

The commit that started plan #477 rewrote this template's ``plan_dir()`` /
``state_file()`` lru_cache functions into eager module constants, which ran a
``git`` subprocess at import and broke pytest collection in linked worktrees.
These tests pin the restored design: side-effect-free import, lazy upper-case
aliases, and the generic re-exports.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

from harness_core import scaffold
from harness_core.git import main_worktree_root
from harness_core.scaffold import RenderContext


def _render_config(base_branch: str = "develop") -> str:
    return scaffold._render_template(
        "harness/config.py.tmpl", RenderContext(project_name="t", base_branch=base_branch)
    )


def _load_rendered(tmp_path, name: str = "rendered_config"):
    path = tmp_path / f"{name}.py"
    path.write_text(_render_config())
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_runs_no_git_subprocess(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError(f"subprocess invoked during config import: {args!r}")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "check_output", _boom)

    module = _load_rendered(tmp_path)  # must not raise

    assert callable(module.plan_dir)
    assert callable(module.state_file)
    assert module.BASE_BRANCH == "develop"


def test_reexports_generic_patterns(tmp_path):
    module = _load_rendered(tmp_path)
    assert module.is_draft_plan("plan-draft-foo.md") is True
    assert module.is_committed_plan("plan-473.md") is True
    assert module.extract_issue_number("plan-473.md") == 473


def test_lazy_uppercase_aliases_split_by_tracked_or_ignored(tmp_path, monkeypatch):
    module = _load_rendered(tmp_path)
    # Rebind the names the module looked up so the functions and the
    # __getattr__ aliases resolve against controlled roots, no real repo needed.
    # Two different roots, or a path taken from the wrong one would still match.
    main = tmp_path / "main"
    tree = tmp_path / "tree"
    monkeypatch.setattr(module, "main_worktree_root", lambda: main)
    monkeypatch.setattr(module, "worktree_root", lambda: tree)
    module.plan_dir.cache_clear()
    module.state_file.cache_clear()

    # Gitignored: exists only in the main checkout.
    assert module.PLAN_DIR == main / ".task" / "plan"
    assert module.STATE_FILE == main / ".claude" / "state.json"
    assert module.plan_dir() == module.PLAN_DIR
    assert module.state_file() == module.STATE_FILE
    # Tracked: the current worktree's copy (#23).
    assert module.SKILL_CONFIG == tree / ".claude" / "skill-config.yaml"


def test_adr_dir_is_cwd_relative(tmp_path):
    module = _load_rendered(tmp_path)
    # CWD-relative on purpose: a branch's in-progress ADRs must be searchable.
    assert not module.ADR_DIR.is_absolute()
    assert str(module.ADR_DIR) == "docs/arch-decision-record"


def test_unknown_attribute_still_raises(tmp_path):
    module = _load_rendered(tmp_path)
    with pytest.raises(AttributeError):
        _ = module.NOPE


def _not_the_main_checkout():
    raise AssertionError("tracked config was resolved against the main checkout")


class TestGithubProjectBlock:
    """The GitHub metadata contract's coordinates, read lazily from the config.

    Owner, project number, status option names and field names are this
    project's constants. The library takes them as arguments, so they have to
    reach it from somewhere — this is that somewhere, and it must not turn
    `import harness.config` into a subprocess or a hard PyYAML dependency.
    """

    def _write_config(self, tmp_path, body: str) -> None:
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "skill-config.yaml").write_text(body)

    def _module(self, tmp_path, monkeypatch, name="cfg_gh"):
        module = _load_rendered(tmp_path, name)
        monkeypatch.setattr(module, "worktree_root", lambda: tmp_path)
        # The tracked config must not be looked up from the main checkout. A
        # stand-in that fails makes every test here catch that, instead of
        # quietly reading whatever this repo's own main checkout holds.
        monkeypatch.setattr(module, "main_worktree_root", _not_the_main_checkout)
        module.github_project.cache_clear()
        return module

    def test_block_is_read_from_skill_config(self, tmp_path, monkeypatch):
        self._write_config(
            tmp_path,
            "issue_tracker: github\n"
            "github_project:\n"
            "  owner: <login>\n"
            "  number: 4\n"
            "  status_names: {backlog: Queued}\n",
        )
        module = self._module(tmp_path, monkeypatch)

        assert module.GITHUB_PROJECT == {
            "owner": "<login>",
            "number": 4,
            "status_names": {"backlog": "Queued"},
        }

    def test_absent_block_is_none_not_an_error(self, tmp_path, monkeypatch):
        # A project on another tracker has no such block; every command then
        # reports the project fields as not applied rather than failing.
        self._write_config(tmp_path, "issue_tracker: forgejo\n")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_absent")

        assert module.GITHUB_PROJECT is None

    def test_missing_config_file_is_none(self, tmp_path, monkeypatch):
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_missing")
        assert module.GITHUB_PROJECT is None

    def test_malformed_yaml_degrades_instead_of_raising(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, "github_project: [unclosed\n")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_bad")
        assert module.GITHUB_PROJECT is None

    def test_reading_the_block_runs_no_subprocess_at_import(self, tmp_path, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError(f"subprocess invoked during config import: {args!r}")

        monkeypatch.setattr(subprocess, "run", _boom)
        monkeypatch.setattr(subprocess, "check_output", _boom)
        module = _load_rendered(tmp_path, "cfg_gh_lazy")  # must not raise

        assert callable(module.github_project)


def _git(*args: str, cwd: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True,
    )


def _commit_config(tree: Path, body: str, message: str) -> None:
    (tree / ".claude").mkdir(exist_ok=True)
    (tree / ".claude" / "skill-config.yaml").write_text(body)
    _git("add", ".claude/skill-config.yaml", cwd=tree)
    _git("commit", "-m", message, cwd=tree)


class TestTrackedConfigFollowsTheWorktree:
    """#23, end to end against real git: code and config from the same branch.

    The main checkout's branch has no `github_project` block; a linked
    worktree's branch adds one. Run from the worktree, the rendered config must
    see the block — the main checkout's copy would reject a board command the
    worktree's own branch is introducing.
    """

    @pytest.fixture(autouse=True)
    def _isolated_git(self, monkeypatch):
        # Under a git hook these point at the outer repo and override CWD.
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            monkeypatch.delenv(var, raising=False)
        main_worktree_root.cache_clear()
        yield
        main_worktree_root.cache_clear()

    def test_worktree_reads_its_own_branch_config(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-b", "main", cwd=repo)
        _commit_config(repo, "issue_tracker: github\n", "main: no block")
        wt = tmp_path / "wt"
        _git("worktree", "add", "-b", "feature", str(wt), cwd=repo)
        _commit_config(
            wt,
            "issue_tracker: github\n"
            "github_project:\n"
            "  owner: <login>\n"
            "  number: 7\n",
            "feature: add block",
        )
        module = _load_rendered(tmp_path, "cfg_gh_worktree")

        monkeypatch.chdir(wt)
        module.github_project.cache_clear()
        main_worktree_root.cache_clear()
        assert module.github_project() == {"owner": "<login>", "number": 7}
        assert module.SKILL_CONFIG == (wt / ".claude" / "skill-config.yaml").resolve()

        # Control: the same module from the main checkout sees main's config.
        # Without it, a fixture that leaked the block onto main would let the
        # assertion above pass whichever root is read.
        monkeypatch.chdir(repo)
        module.github_project.cache_clear()
        main_worktree_root.cache_clear()
        assert module.github_project() is None
