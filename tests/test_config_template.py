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
