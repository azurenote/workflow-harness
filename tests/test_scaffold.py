"""Tests for harness_core.scaffold module."""

from __future__ import annotations

import os
import subprocess
import sys
from importlib import resources
from pathlib import Path

from harness_core import scaffold
from harness_core.preflight import PreflightResult, ToolStatus
from harness_core.scaffold import RenderContext, plan_init, plan_update


def _preflight(ok: bool = True) -> PreflightResult:
    python = ToolStatus(
        name="python",
        ok=ok,
        executable=sys.executable,
        version="3.11",
        detail="ok" if ok else "Python 3.10 is below required >=3.11",
    )
    tools = (
        ToolStatus("uv", ok, "/bin/uv" if ok else None, "uv 1", "ok" if ok else "uv missing"),
        ToolStatus("git", ok, "/bin/git" if ok else None, "git 2", "ok" if ok else "git missing"),
    )
    return PreflightResult(
        required_python=">=3.11",
        current_python="3.11" if ok else "3.10",
        python=python,
        tools=tools,
    )


def _context() -> RenderContext:
    return RenderContext(
        project_name="demo",
        base_branch="main",
        issue_tracker="forgejo",
        forgejo_remote="lab",
        forgejo_repo="my/demo",
    )


def _plan_shape(result):
    return [(file.path, file.action, file.backup_path) for file in result.files]


def test_init_apply_creates_project_local_harness_and_help_smoke(tmp_path):
    result = plan_init(
        tmp_path,
        context=_context(),
        apply=True,
        preflight=_preflight(),
        backup_id="fixed",
    )

    assert result.ok
    assert ".claude/skill-config.yaml" in result.by_action("create")
    assert (tmp_path / ".claude/scripts/harness_cli.py").exists()
    assert (tmp_path / ".claude/scripts/harness/config.py").exists()
    assert (tmp_path / ".claude/scripts/harness/.manifest.json").exists()

    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    help_result = subprocess.run(
        [sys.executable, str(tmp_path / ".claude/scripts/harness_cli.py"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "find-draft-plan" in help_result.stdout


def test_init_preflight_failure_writes_nothing(tmp_path):
    result = plan_init(
        tmp_path,
        context=_context(),
        apply=True,
        preflight=_preflight(ok=False),
    )

    assert not result.ok
    assert not (tmp_path / ".claude").exists()
    assert result.files == ()
    assert any("Python 3.10" in warning for warning in result.warnings)


def test_update_preserves_existing_project_specific_files(tmp_path):
    config = tmp_path / ".claude/skill-config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "issue_tracker: forgejo\n"
        "base_branch: develop\n"
        "adr_dir: docs/arch-decision-record\n"
        "forgejo_remote: lab\n"
        "forgejo_repo: my/demo\n"
        "hooks:\n"
        "  post_start: echo keep\n"
    )
    project_py = tmp_path / ".claude/scripts/project.py"
    project_py.parent.mkdir(parents=True)
    project_py.write_text(
        "# custom project operations\n"
        "GITHUB_PROJECT_ID = 'PVT_123'\n"
        "FORGEJO_OWNER = 'my'\n"
    )
    custom = tmp_path / ".claude/scripts/harness/custom.py"
    custom.parent.mkdir(parents=True)
    custom.write_text("# local only\n")

    result = plan_update(
        tmp_path,
        apply=True,
        preflight=_preflight(),
        backup_id="fixed",
    )

    assert result.ok
    config_text = config.read_text()
    assert "base_branch: develop" in config_text
    assert "adr_dir: docs/arch-decision-record" in config_text
    assert "forgejo_repo: my/demo" in config_text
    assert project_py.read_text() == (
        "# custom project operations\n"
        "GITHUB_PROJECT_ID = 'PVT_123'\n"
        "FORGEJO_OWNER = 'my'\n"
    )
    assert custom.read_text() == "# local only\n"
    assert ".claude/skill-config.yaml" in result.by_action("skip")
    assert ".claude/scripts/project.py" in result.by_action("skip")


def test_update_replaces_legacy_wrapper_with_backup(tmp_path):
    legacy = tmp_path / ".claude/scripts/harness/config.py"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        "from pathlib import Path\n"
        "PLAN_DIR = Path.cwd() / '.task' / 'plan'\n"
        "STATE_FILE = Path.cwd() / '.claude' / 'state.json'\n"
    )

    result = plan_update(
        tmp_path,
        context=_context(),
        apply=True,
        preflight=_preflight(),
        backup_id="fixed",
    )

    assert ".claude/scripts/harness/config.py" in result.by_action("update")
    assert "main_worktree_root" in legacy.read_text()
    backup = (
        tmp_path
        / ".claude/scripts/.harness-backup/fixed/.claude/scripts/harness/config.py"
    )
    assert "Path.cwd()" in backup.read_text()


def test_dry_run_and_apply_share_change_plan(tmp_path):
    harness_cli = tmp_path / ".claude/scripts/harness_cli.py"
    harness_cli.parent.mkdir(parents=True)
    harness_cli.write_text("# old\n")

    dry = plan_update(
        tmp_path,
        context=_context(),
        apply=False,
        preflight=_preflight(),
        backup_id="fixed",
    )
    applied = plan_update(
        tmp_path,
        context=_context(),
        apply=True,
        preflight=_preflight(),
        backup_id="fixed",
    )

    assert _plan_shape(dry) == _plan_shape(applied)
    assert ".claude/scripts/harness_cli.py" in applied.by_action("update")


def test_templates_are_importlib_resources():
    text = (
        resources.files("harness_core.templates")
        .joinpath("harness_cli.py.tmpl")
        .read_text()
    )

    assert "find-draft-plan" in text


def test_preflight_uses_harness_project_root_not_cwd(tmp_path, monkeypatch):
    seen = {}

    def fake_check_preflight(project_root):
        seen["project_root"] = Path(project_root)
        return _preflight()

    monkeypatch.setattr(scaffold, "check_preflight", fake_check_preflight)
    monkeypatch.chdir(tmp_path)

    result = scaffold.plan_update(tmp_path)

    assert result.ok
    assert (seen["project_root"] / "pyproject.toml").exists()
    assert seen["project_root"].name == "workflow-harness"


def test_cli_update_preserves_existing_config_context(tmp_path, monkeypatch):
    config = tmp_path / ".claude/skill-config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "issue_tracker: forgejo\n"
        "base_branch: develop\n"
        "forgejo_remote: upstream\n"
        "forgejo_repo: team/demo\n"
    )
    legacy = tmp_path / ".claude/scripts/harness/config.py"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("PLAN_DIR = 'old'\n")

    monkeypatch.setattr(scaffold, "check_preflight", lambda _root: _preflight())

    code = scaffold.main(["update", "--target", str(tmp_path), "--apply"])

    assert code == 0
    generated = legacy.read_text()
    assert 'BASE_BRANCH = "develop"' in generated
    assert config.read_text().startswith("issue_tracker: forgejo\nbase_branch: develop")
