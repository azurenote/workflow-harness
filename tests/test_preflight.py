"""Tests for harness_core.preflight module."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness_core.preflight import (
    check_preflight,
    format_preflight_result,
    read_requires_python,
)


def _which_factory(found: set[str]):
    def _which(name: str) -> str | None:
        return f"/bin/{name}" if name in found else None

    return _which


def _runner(args):
    name = Path(args[0]).name
    return subprocess.CompletedProcess(args, 0, stdout=f"{name} 1.2.3\n", stderr="")


def test_reads_requires_python_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\nrequires-python = '>=3.12'\n"
    )

    assert read_requires_python(tmp_path) == ">=3.12"


def test_preflight_success_with_injected_tools(tmp_path):
    result = check_preflight(
        tmp_path,
        requires_python=">=3.11",
        python_version=(3, 11, 2),
        python_executable="/bin/python3",
        which=_which_factory({"uv", "git"}),
        runner=_runner,
    )

    assert result.ok
    assert result.python.name == "python"
    assert [tool.name for tool in result.tools] == ["uv", "git"]
    assert "Python: 3.11.2 (required >=3.11) - ok" in format_preflight_result(result)


def test_preflight_fails_when_python_is_too_old(tmp_path):
    result = check_preflight(
        tmp_path,
        requires_python=">=3.11",
        python_version=(3, 10, 13),
        which=_which_factory({"uv", "git"}),
        runner=_runner,
    )

    assert not result.ok
    assert "below required" in result.python.detail
    assert any("Python 3.10.13" in failure for failure in result.failures())


def test_preflight_fails_when_uv_is_missing(tmp_path):
    result = check_preflight(
        tmp_path,
        requires_python=">=3.11",
        python_version=(3, 11, 0),
        which=_which_factory({"git"}),
        runner=_runner,
    )

    assert not result.ok
    uv = next(tool for tool in result.tools if tool.name == "uv")
    assert uv.executable is None
    assert uv.detail == "uv not found on PATH"


def test_preflight_fails_when_tool_version_command_fails(tmp_path):
    def runner(args):
        return subprocess.CompletedProcess(args, 2, stdout="", stderr="boom\n")

    result = check_preflight(
        tmp_path,
        requires_python=">=3.11",
        python_version=(3, 11, 0),
        which=_which_factory({"uv", "git"}),
        runner=runner,
    )

    assert not result.ok
    assert all("failed with exit 2" in tool.detail for tool in result.tools)
