"""Structural contract for this repo's CI.

The whole point of plan #477's gate half is that these tests actually run on a
change. Pin the workflow's existence, its pull_request trigger, and that it
invokes pytest — so removing the gate fails the gate.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_tests_workflow_exists() -> None:
    assert WORKFLOW.exists(), "workflow-harness must have a CI workflow (it had none)"


def test_workflow_triggers_on_push_and_pull_request() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    try:
        import yaml

        # YAML parses the bare `on:` key as the boolean True; read it back either way.
        data = yaml.safe_load(text)
        triggers = data.get("on") or data.get(True)
        assert triggers is not None
        assert "pull_request" in triggers
        assert "push" in triggers
    except ModuleNotFoundError:
        assert "pull_request:" in text
        assert "push:" in text


def test_workflow_runs_pytest() -> None:
    assert "pytest tests" in WORKFLOW.read_text(encoding="utf-8")
