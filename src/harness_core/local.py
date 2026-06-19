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


# ── YAML frontmatter ───────────────────────────────────────────────────────
#
# Plan files may begin with a leading '---' fenced block declaring per-task
# metadata (e.g. base_branch, parent_issue). We parse it with a minimal,
# dependency-free key:value reader rather than pulling in PyYAML — the schema is
# flat strings/numbers, never nested. Anything we cannot parse degrades to "no
# frontmatter" so a malformed block never blocks the workflow.


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a document into (frontmatter_block, body).

    The frontmatter block is the raw text between a leading ``---`` fence and the
    next ``---`` fence (fences excluded). If the document does not start with a
    ``---`` fence, or the closing fence is missing, returns ``("", text)`` — the
    whole document is treated as body.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    return "", text


def _strip_inline_comment(value: str) -> str:
    """Drop a YAML-style ``#`` comment (one preceded by whitespace), respecting quotes."""
    in_single = in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index]
    return value


def _strip_quotes(value: str) -> str:
    """Remove a single matching pair of surrounding single/double quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a leading ``---`` frontmatter block into a flat ``{key: value}`` dict.

    Returns ``{}`` when no frontmatter is present. Tolerant of surrounding
    whitespace, quotes, blank lines, full-line ``#`` comments, and inline
    ``# ...`` comments. Later duplicate keys win.
    """
    block, _ = split_frontmatter(text)
    result: dict[str, str] = {}
    for raw_line in block.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(_strip_inline_comment(value).strip())
        result[key] = value
    return result


def extract_base_branch(plan_path: Path) -> str | None:
    """Return the declared ``base_branch`` from a plan's frontmatter, or None.

    None means "not declared" — callers treat that (and an explicit ``develop``)
    as the default base. The raw declared value is returned otherwise, including
    ``develop`` itself, so the distinction stays honest at this layer.
    """
    value = parse_frontmatter(plan_path.read_text()).get("base_branch", "").strip()
    return value or None


def collect_declared_base_branches(plan_dir: Path) -> set[str]:
    """Collect every ``base_branch`` declared across ``plan-*.md`` frontmatter.

    Pure local filesystem scan — no network. Used to protect integration
    branches that live sub-task plans still target as their base from being
    deleted by stale-branch cleanup. Returns an empty set when ``plan_dir`` is
    missing; unreadable or malformed files are skipped silently.
    """
    if not plan_dir.exists():
        return set()
    declared: set[str] = set()
    for path in plan_dir.glob("plan-*.md"):
        try:
            base = extract_base_branch(path)
        except OSError:
            continue
        if base:
            declared.add(base)
    return declared


def extract_plan_title(plan_path: Path) -> str:
    """Extract the plan title, skipping any leading frontmatter block.

    Reads the first non-empty body line; honors a ``# Plan: <title>`` prefix and
    otherwise strips leading heading hashes.
    """
    _, body = split_frontmatter(plan_path.read_text())
    first_line = next((line for line in body.split("\n") if line.strip()), "")
    prefix = "# Plan: "
    if first_line.startswith(prefix):
        return first_line[len(prefix):].strip()
    title = first_line.lstrip("# ").strip()
    # A degenerate doc (e.g. a lone unclosed '---' fence) must not yield '---'.
    if title and set(title) <= {"-"}:
        return ""
    return title


def read_plan_preview(plan_path: Path, max_lines: int = 30) -> str:
    """Preview a plan: the full frontmatter block (if any) plus the first N body lines.

    Keeping the frontmatter visible lets a human confirm the declared base branch
    during /issue, while the N-line budget always applies to real body content.
    """
    block, body = split_frontmatter(plan_path.read_text())
    body_lines = body.split("\n")
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    preview = body_lines[:max_lines]
    if block:
        return "\n".join(["---", block, "---", *preview])
    return "\n".join(preview)
