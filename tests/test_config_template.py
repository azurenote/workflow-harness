"""Contract tests for the rendered project config template.

The commit that started plan #477 rewrote this template's ``plan_dir()`` /
``state_file()`` lru_cache functions into eager module constants, which ran a
``git`` subprocess at import and broke pytest collection in linked worktrees.
These tests pin the restored design: side-effect-free import, lazy upper-case
aliases, and the generic re-exports.
"""

from __future__ import annotations

import builtins
import importlib.util
import os
import subprocess
import sys
import threading
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

    def test_block_comes_back_without_a_reason(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, "github_project:\n  owner: <login>\n  number: 4\n")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_reason_ok")

        assert module.github_project_or_reason() == ({"owner": "<login>", "number": 4}, None)

    # Each cause of "no block", with a fragment only its own reason carries. The
    # fragments are pairwise distinct, so a reason that merged two causes back
    # into one message would fail the other cause's row.
    CAUSES = [
        pytest.param(None, "does not exist", id="no-file"),
        pytest.param(b"github_project: [unclosed\n", "not valid YAML: ParserError", id="bad-yaml"),
        # safe_load raises more than YAMLError; each of these escaped once.
        pytest.param(b"github_project:\n  d: 2020-13-45\n", "not valid YAML: ValueError", id="bad-date"),
        pytest.param(b"github_project:\n  n: !!int abc\n", "not valid YAML: ValueError", id="bad-tag"),
        pytest.param(
            b"github_project: " + b"[" * 5000 + b"]" * 5000 + b"\n",
            "not valid YAML: RecursionError",
            id="deep-nesting",
        ),
        pytest.param(b"\xff\xfe github_project:\n", "UnicodeDecodeError", id="not-utf8"),
        pytest.param(b"- github_project\n", "top level is a list", id="top-level-list"),
        # Falsy non-mappings: an `or {}` would fold these into "no block".
        pytest.param(b"[]\n", "top level is a list", id="top-level-empty-list"),
        pytest.param(b"false\n", "top level is a bool", id="top-level-false"),
        pytest.param(b"just a string\n", "top level is a str", id="top-level-scalar"),
        pytest.param(b"issue_tracker: forgejo\n", "has no github_project block", id="no-key"),
        pytest.param(b"", "has no github_project block", id="empty-file"),
        pytest.param(b"github_project: 4\n", "is a int, not a mapping", id="block-not-mapping"),
        # The key is present with no value — the commonest half-written block.
        # Not "no block": the key is there.
        pytest.param(b"github_project:\n", "is a NoneType, not a mapping", id="block-null"),
        # `if project:` in a caller would skip `{}` silently, reason None.
        pytest.param(b"github_project: {}\n", "is empty", id="block-empty"),
    ]

    @pytest.mark.parametrize("raw, fragment", CAUSES)
    def test_each_cause_is_a_reason_not_an_exception(self, tmp_path, monkeypatch, raw, fragment):
        if raw is not None:
            (tmp_path / ".claude").mkdir()
            (tmp_path / ".claude" / "skill-config.yaml").write_bytes(raw)
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_cause")

        block, reason = module.github_project_or_reason()

        assert block is None
        assert fragment in reason
        # Every file-level reason names the file it is about.
        assert str(tmp_path / ".claude" / "skill-config.yaml") in reason
        # The fail-open form stays None and still does not raise.
        assert module.github_project() is None

    def test_not_a_regular_file_is_a_reason(self, tmp_path, monkeypatch):
        (tmp_path / ".claude" / "skill-config.yaml").mkdir(parents=True)
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_dir")

        block, reason = module.github_project_or_reason()

        assert block is None
        assert "is not a regular file" in reason
        assert str(tmp_path / ".claude" / "skill-config.yaml") in reason
        assert module.github_project() is None

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
    def test_fifo_is_a_reason_not_a_hang(self, tmp_path, monkeypatch):
        # read_text() on a FIFO blocks until a writer opens it — forever, at
        # parser build. Run the call on a thread so a regression fails instead
        # of hanging the suite; a daemon thread left blocked dies with pytest.
        (tmp_path / ".claude").mkdir()
        os.mkfifo(tmp_path / ".claude" / "skill-config.yaml")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_fifo")
        result = []
        worker = threading.Thread(
            target=lambda: result.append(
                (module.github_project_or_reason(), module.github_project())
            ),
            daemon=True,
        )

        worker.start()
        worker.join(timeout=5)

        assert result, "reading the config blocked on a FIFO"
        (block, reason), cached = result[0]
        assert block is None
        assert "is not a regular file" in reason
        assert str(tmp_path / ".claude" / "skill-config.yaml") in reason
        assert cached is None

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file")
    def test_unreadable_file_is_a_reason(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, "github_project:\n  owner: <login>\n")
        config = tmp_path / ".claude" / "skill-config.yaml"
        config.chmod(0)
        try:
            module = self._module(tmp_path, monkeypatch, name="cfg_gh_unreadable")
            block, reason = module.github_project_or_reason()
            cached = module.github_project()
        finally:
            config.chmod(0o644)

        assert block is None
        assert "could not be read: PermissionError" in reason
        assert str(config) in reason
        assert cached is None

    @pytest.mark.skipif(os.geteuid() == 0, reason="root searches a mode-000 directory")
    def test_unsearchable_parent_is_not_called_absent(self, tmp_path, monkeypatch):
        # Python 3.14's is_file()/exists() return False here instead of
        # raising, which would report a present file as missing.
        self._write_config(tmp_path, "github_project:\n  owner: <login>\n")
        parent = tmp_path / ".claude"
        parent.chmod(0)
        try:
            module = self._module(tmp_path, monkeypatch, name="cfg_gh_parent")
            block, reason = module.github_project_or_reason()
        finally:
            parent.chmod(0o755)

        assert block is None
        assert "could not be read: PermissionError" in reason
        assert "does not exist" not in reason

    def test_dangling_symlink_says_so(self, tmp_path, monkeypatch):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "skill-config.yaml").symlink_to(tmp_path / "nowhere.yaml")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_dangling")

        block, reason = module.github_project_or_reason()

        assert block is None
        assert "symlink whose target does not exist" in reason
        assert str(tmp_path / ".claude" / "skill-config.yaml") in reason

    @pytest.mark.parametrize(
        "error",
        [UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"), RuntimeError("loop")],
        ids=["non-utf8-toplevel", "resolve-loop"],
    )
    def test_any_path_resolution_failure_is_a_reason(self, tmp_path, monkeypatch, error):
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_resolve")

        def _fail():
            raise error

        monkeypatch.setattr(module, "worktree_root", _fail)

        block, reason = module.github_project_or_reason()

        assert block is None
        assert f"working tree could not be resolved: {type(error).__name__}" in reason
        assert module.github_project() is None

    def test_reason_loader_is_not_cached(self, tmp_path, monkeypatch):
        # It is the diagnostic form: the reason must describe the file as it
        # is now, not as it was on the first call.
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_fresh")
        assert not hasattr(module.github_project_or_reason, "cache_clear")

        _, first = module.github_project_or_reason()
        self._write_config(tmp_path, "github_project:\n  owner: <login>\n")

        assert "does not exist" in first
        assert module.github_project_or_reason() == ({"owner": "<login>"}, None)

    def test_deleted_cwd_is_a_reason(self, tmp_path, monkeypatch):
        # The real worktree_root(), not a stand-in: git fails in a removed
        # directory and its fallback, Path.cwd(), raises FileNotFoundError.
        module = _load_rendered(tmp_path, "cfg_gh_gone")
        module.github_project.cache_clear()
        gone = tmp_path / "gone"
        gone.mkdir()
        monkeypatch.chdir(gone)
        gone.rmdir()

        block, reason = module.github_project_or_reason()

        assert block is None
        assert "working tree could not be resolved" in reason
        assert module.github_project() is None

    @pytest.mark.parametrize(
        "error",
        [ModuleNotFoundError("No module named 'yaml'"), ImportError("broken _yaml extension")],
        ids=["absent", "broken-extension"],
    )
    def test_pyyaml_not_importable_is_a_reason(self, tmp_path, monkeypatch, error):
        self._write_config(tmp_path, "github_project:\n  owner: <login>\n")
        module = self._module(tmp_path, monkeypatch, name="cfg_gh_noyaml")
        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name == "yaml":
                raise error
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _import)

        block, reason = module.github_project_or_reason()

        assert block is None
        assert "PyYAML is not importable" in reason
        assert str(error) in reason
        # Which interpreter, and how to fix it — the half a caller used to re-probe.
        assert f"{sys.executable} -m pip install pyyaml" in reason
        assert module.github_project() is None

    def test_import_needs_no_pyyaml(self, tmp_path, monkeypatch):
        # PyYAML is optional: without it, importing the config still works
        # and only the block read reports why. A module-level `import yaml`
        # would fail right here.
        monkeypatch.setitem(sys.modules, "yaml", None)
        module = _load_rendered(tmp_path, "cfg_gh_no_yaml_import")
        monkeypatch.setattr(module, "worktree_root", lambda: tmp_path)

        block, reason = module.github_project_or_reason()

        assert block is None
        assert "PyYAML is not importable" in reason

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
