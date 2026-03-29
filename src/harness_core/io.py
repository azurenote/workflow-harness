"""User interaction and logging utilities for harness workflow.

These functions produce structured output that Claude reads and presents
to the user. They do NOT interact with stdin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def format_plan_preview(
    plan_path: Path, title: str, preview_text: str
) -> str:
    """Format a plan file preview for user confirmation."""
    return (
        f"Found draft plan file:\n"
        f"  {plan_path}\n"
        f"\n"
        f"Title:\n"
        f"  {title}\n"
        f"\n"
        f"Preview:\n"
        + "\n".join(f"  {line}" for line in preview_text.splitlines())
    )


def format_step(step_name: str, status: str, detail: str = "") -> str:
    """Format a single step result for output."""
    icon = {"ok": "✓", "fail": "✗", "skip": "—"}.get(status, "?")
    msg = f"[{icon}] {step_name}"
    if detail:
        msg += f": {detail}"
    return msg


def format_result(steps: list[dict]) -> str:
    """Format a list of step results into a summary block."""
    lines = ["Steps:"]
    for step in steps:
        lines.append(
            "  "
            + format_step(
                step["name"], step["status"], step.get("detail", "")
            )
        )
    return "\n".join(lines)


def print_json(data: dict) -> None:
    """Print JSON to stdout (for Claude to parse)."""
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def print_error(message: str) -> None:
    """Print error message to stderr."""
    print(f"Error: {message}", file=sys.stderr)
