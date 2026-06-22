"""Environment preflight checks for workflow-harness bootstrap commands."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_REQUIRES_PYTHON = ">=3.11"
DEFAULT_REQUIRED_TOOLS = ("uv", "git")

WhichFn = Callable[[str], str | None]
RunnerFn = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ToolStatus:
    """Result for one required executable."""

    name: str
    ok: bool
    executable: str | None
    version: str
    detail: str


@dataclass(frozen=True)
class PreflightResult:
    """Full preflight result.

    ``python`` is the current interpreter. ``tools`` contains external
    executables such as ``uv`` and ``git``.
    """

    required_python: str
    current_python: str
    python: ToolStatus
    tools: tuple[ToolStatus, ...]

    @property
    def ok(self) -> bool:
        return self.python.ok and all(tool.ok for tool in self.tools)

    @property
    def checks(self) -> tuple[ToolStatus, ...]:
        return (self.python, *self.tools)

    def failures(self) -> list[str]:
        return [check.detail for check in self.checks if not check.ok]


def read_requires_python(project_root: Path | str) -> str:
    """Read ``project.requires-python`` from pyproject.toml.

    The workflow-harness package owns the minimum Python contract. If the file
    or key is absent, keep the explicit repo default instead of guessing from
    the running interpreter.
    """

    pyproject = Path(project_root) / "pyproject.toml"
    if not pyproject.exists():
        return _metadata_requires_python()
    try:
        data = tomllib.loads(pyproject.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_REQUIRES_PYTHON
    value = data.get("project", {}).get("requires-python")
    return str(value) if value else DEFAULT_REQUIRES_PYTHON


def _metadata_requires_python() -> str:
    try:
        value = metadata.metadata("harness-core").get("Requires-Python")
    except metadata.PackageNotFoundError:
        value = None
    return value or DEFAULT_REQUIRES_PYTHON


def check_preflight(
    project_root: Path | str,
    *,
    required_tools: Sequence[str] = DEFAULT_REQUIRED_TOOLS,
    requires_python: str | None = None,
    python_version: tuple[int, ...] | None = None,
    python_executable: str | None = None,
    which: WhichFn | None = None,
    runner: RunnerFn | None = None,
) -> PreflightResult:
    """Validate the local environment before writing a target harness.

    Args:
        project_root: workflow-harness repository root, used for pyproject.
        required_tools: External executables to require and version-check.
        requires_python: Override for tests or callers that already read metadata.
        python_version: Override current interpreter version for tests.
        python_executable: Override current interpreter path for tests.
        which: Injectable executable resolver.
        runner: Injectable command runner for ``tool --version`` checks.
    """

    requires = requires_python or read_requires_python(project_root)
    current_tuple = python_version or tuple(sys.version_info[:3])
    current_python = _format_version(current_tuple)
    python_status = _check_python(
        requires,
        current_tuple,
        python_executable or sys.executable,
    )

    which_fn = which or shutil.which
    runner_fn = runner or _run_version_command
    tool_statuses = tuple(
        _check_tool(tool, which=which_fn, runner=runner_fn)
        for tool in required_tools
    )
    return PreflightResult(
        required_python=requires,
        current_python=current_python,
        python=python_status,
        tools=tool_statuses,
    )


def format_preflight_result(result: PreflightResult) -> str:
    """Render a human-readable preflight summary."""

    lines = [
        f"Python: {result.current_python} "
        f"(required {result.required_python}) - "
        f"{'ok' if result.python.ok else 'fail'}"
    ]
    for tool in result.tools:
        if tool.ok:
            lines.append(f"{tool.name}: {tool.version} ({tool.executable})")
        else:
            lines.append(f"{tool.name}: missing or unusable - {tool.detail}")
    return "\n".join(lines)


def preflight_to_dict(result: PreflightResult) -> dict:
    """Convert a preflight result to JSON-serializable data."""

    return {
        "ok": result.ok,
        "required_python": result.required_python,
        "current_python": result.current_python,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "executable": check.executable,
                "version": check.version,
                "detail": check.detail,
            }
            for check in result.checks
        ],
        "failures": result.failures(),
    }


def _check_python(
    requires_python: str,
    current_version: tuple[int, ...],
    executable: str,
) -> ToolStatus:
    minimum = _minimum_python_version(requires_python)
    current = _normalize_version(current_version)
    if minimum is None:
        return ToolStatus(
            name="python",
            ok=True,
            executable=executable,
            version=_format_version(current),
            detail=f"Could not parse requires-python '{requires_python}'; skipped",
        )
    ok = current >= minimum
    required = _format_version(minimum)
    actual = _format_version(current)
    detail = (
        f"Python {actual} satisfies {requires_python}"
        if ok
        else f"Python {actual} is below required {requires_python}"
    )
    return ToolStatus(
        name="python",
        ok=ok,
        executable=executable,
        version=actual,
        detail=detail if ok else f"{detail}; install Python {required}+",
    )


def _check_tool(
    name: str,
    *,
    which: WhichFn,
    runner: RunnerFn,
) -> ToolStatus:
    executable = which(name)
    if not executable:
        return ToolStatus(
            name=name,
            ok=False,
            executable=None,
            version="",
            detail=f"{name} not found on PATH",
        )
    result = runner([executable, "--version"])
    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else ""
    if result.returncode != 0:
        return ToolStatus(
            name=name,
            ok=False,
            executable=executable,
            version=first_line,
            detail=f"{name} --version failed with exit {result.returncode}",
        )
    return ToolStatus(
        name=name,
        ok=True,
        executable=executable,
        version=first_line or f"{name} present",
        detail=f"{name} is available",
    )


def _run_version_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def _minimum_python_version(requires_python: str) -> tuple[int, int, int] | None:
    match = re.search(r">=\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", requires_python)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return major, minor, patch


def _normalize_version(version: tuple[int, ...]) -> tuple[int, int, int]:
    parts = tuple(version[:3])
    return (*parts, *([0] * (3 - len(parts))))[:3]


def _format_version(version: tuple[int, ...]) -> str:
    normalized = _normalize_version(version)
    if normalized[2] == 0:
        return f"{normalized[0]}.{normalized[1]}"
    return ".".join(str(part) for part in normalized)
