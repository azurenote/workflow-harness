"""Local file system operations for harness workflow.

All path-dependent functions require explicit plan_dir parameter.
Project-level harness provides defaults via its own config.
"""

from __future__ import annotations

from pathlib import Path

from .config import is_draft_plan


class NoPlanFileError(Exception):
    """No draft plan file found."""


class MultiplePlanFilesError(Exception):
    """Multiple draft plan files found — user must choose."""

    def __init__(self, files: list[str]):
        self.files = files
        super().__init__(
            f"Multiple draft plan files found:\n"
            + "\n".join(f"  - {f}" for f in files)
            + "\nSpecify which one to use."
        )


class InvalidPlanFileError(Exception):
    """File does not follow naming convention."""


def find_draft_plan_file(plan_dir: Path) -> Path:
    """Find the unique draft plan file (UUID format) in plan_dir.

    Returns:
        Path to the draft plan file.

    Raises:
        NoPlanFileError: No UUID-named plan files found.
        MultiplePlanFilesError: More than one UUID-named plan file.
    """
    if not plan_dir.exists():
        raise NoPlanFileError(
            f"Plan directory does not exist: {plan_dir}\n"
            "Run /project:plan first to create a plan."
        )

    drafts = [
        f.name for f in plan_dir.glob("plan-*.md") if is_draft_plan(f.name)
    ]

    if len(drafts) == 0:
        raise NoPlanFileError(
            f"No draft plan files (UUID format) in {plan_dir}/.\n"
            "Run /project:plan first to create a plan."
        )
    if len(drafts) > 1:
        raise MultiplePlanFilesError(drafts)

    return plan_dir / drafts[0]


def rename_plan_to_issue(
    plan_path: Path, issue_number: int
) -> Path:
    """Rename plan-{uuid}.md to plan-{issue_number}.md.

    Returns:
        New path after rename.

    Raises:
        FileExistsError: Target file already exists.
    """
    target = plan_path.parent / f"plan-{issue_number}.md"
    if target.exists():
        raise FileExistsError(
            f"Target already exists: {target}\n"
            f"Issue #{issue_number} may already have a plan file."
        )
    plan_path.rename(target)
    return target


def plan_file_for_issue(issue_number: int, plan_dir: Path) -> Path:
    """Return path to plan-{issue_number}.md, raising if not found."""
    path = plan_dir / f"plan-{issue_number}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Plan file not found: {path}\n"
            f"Run /project:plan and /project:issue first."
        )
    return path


def extract_plan_title(plan_path: Path) -> str:
    """Extract title from first line: '# Plan: <title>'."""
    first_line = plan_path.read_text().split("\n", 1)[0]
    prefix = "# Plan: "
    if first_line.startswith(prefix):
        return first_line[len(prefix):].strip()
    return first_line.lstrip("# ").strip()


def read_plan_preview(plan_path: Path, max_lines: int = 30) -> str:
    """Read first N lines of a plan file for preview."""
    lines = plan_path.read_text().splitlines()[:max_lines]
    return "\n".join(lines)
