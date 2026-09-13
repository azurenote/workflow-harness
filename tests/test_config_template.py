"""Contract tests for the rendered project config template.

The commit that started plan #477 rewrote this template's ``plan_dir()`` /
``state_file()`` lru_cache functions into eager module constants, which ran a
``git`` subprocess at import and broke pytest collection in linked worktrees.
These tests pin the restored design: side-effect-free import, lazy upper-case
aliases, and the generic re-exports.
"""

from __future__ import annotations

import importlib.util
import subprocess

import pytest

from harness_core import scaffold
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


def test_lazy_uppercase_aliases_resolve_from_main_worktree(tmp_path, monkeypatch):
    module = _load_rendered(tmp_path)
    # Rebind the name the module looked up so plan_dir()/state_file() and the
    # __getattr__ aliases resolve against a controlled root, no real repo needed.
    monkeypatch.setattr(module, "main_worktree_root", lambda: tmp_path)
    module.plan_dir.cache_clear()
    module.state_file.cache_clear()

    assert module.PLAN_DIR == tmp_path / ".task" / "plan"
    assert module.STATE_FILE == tmp_path / ".claude" / "state.json"
    assert module.SKILL_CONFIG == tmp_path / ".claude" / "skill-config.yaml"
    # plan_dir() and PLAN_DIR must agree — they are one value with two names.
    assert module.plan_dir() == module.PLAN_DIR


def test_adr_dir_is_cwd_relative(tmp_path):
    module = _load_rendered(tmp_path)
    # CWD-relative on purpose: a branch's in-progress ADRs must be searchable.
    assert not module.ADR_DIR.is_absolute()
    assert str(module.ADR_DIR) == "docs/arch-decision-record"


def test_unknown_attribute_still_raises(tmp_path):
    module = _load_rendered(tmp_path)
    with pytest.raises(AttributeError):
        _ = module.NOPE


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
        monkeypatch.setattr(module, "main_worktree_root", lambda: tmp_path)
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
