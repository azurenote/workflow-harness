"""Local file system operations for harness workflow.

All path-dependent functions require explicit plan_dir parameter, except
rename_plan_to_issue, whose plan_dir defaults to the main worktree's
.task/plan so the skill docs' two-argument call gets its checks too.
Project-level harness provides defaults via its own config.
"""

from __future__ import annotations

from pathlib import Path

from .config import is_draft_plan, is_issue_id
from .git import main_worktree_root


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


class InvalidIssueIdError(ValueError):
    """Issue id is neither an issue number nor a ticket key."""


def _checked_issue_id(issue_id: int | str) -> str:
    """Return issue_id as the string that goes into a plan file name.

    Always through str(): an isinstance(int) shortcut would let True through
    as "True" — bool is an int.
    """
    text = str(issue_id)
    if not is_issue_id(text):
        raise InvalidIssueIdError(
            f"reject (id): not an issue number or ticket key: {text!r}"
        )
    return text


def abs_under_main(
    path: Path, *, root: Path | None = None, expand_user: bool = True
) -> Path:
    """Re-root a relative path at the main worktree; absolute paths pass through.

    A positional path argument is typed from whatever CWD the session happens to
    be in — often a linked worktree — while the file it names may live only in
    the main worktree's gitignored ``.task/plan/``. A relative path must resolve
    there, not against CWD (plan-234).

    Args:
        path: The path as the caller typed it.
        root: Main worktree root. Defaults to :func:`main_worktree_root`. Passing
            it explicitly lets a caller that already resolved the root (and the
            tests that stub it) keep one seam instead of two.
        expand_user: Expand a leading ``~`` before deciding. Without this a path
            like ``~/notes.md`` is "relative" and would be re-rooted into the
            worktree, producing a path that does not exist.
    """
    if expand_user:
        path = Path(path).expanduser()
    if path.is_absolute():
        return path
    return ((root if root is not None else main_worktree_root()) / path).resolve()


def find_draft_plan_file(plan_dir: Path) -> Path:
    """Find the unique draft plan file in plan_dir.

    Returns:
        Path to the draft plan file.

    Raises:
        NoPlanFileError: No supported draft plan files found.
        MultiplePlanFilesError: More than one supported draft plan file.
    """
    if not plan_dir.exists():
        raise NoPlanFileError(
            f"Plan directory does not exist: {plan_dir}\n"
            "Run /project:plan first to create a plan."
        )

    drafts = sorted(
        f.name for f in plan_dir.glob("plan-*.md") if is_draft_plan(f.name)
    )

    if len(drafts) == 0:
        raise NoPlanFileError(
            f"No draft plan files in {plan_dir}/.\n"
            "Run /project:plan first to create a plan."
        )
    if len(drafts) > 1:
        raise MultiplePlanFilesError(drafts)

    return plan_dir / drafts[0]


def rename_plan_to_issue(
    plan_path: Path, issue_id: int | str, *, plan_dir: Path | None = None
) -> Path:
    """Rename a draft plan file to plan-{issue_id}.md.

    Every check runs before anything moves. Without them an empty path — which
    is ``.``, and the main worktree root once re-rooted — renamed the worktree
    directory itself (#32).

    A relative ``plan_path`` is resolved against CWD, not re-rooted at the main
    worktree; re-rooting is the caller's job (:func:`abs_under_main`). From a
    linked worktree such a path fails the plan-directory check, which is the
    safe way to fail.

    Args:
        plan_path: The draft to rename.
        issue_id: Issue number or ticket key.
        plan_dir: Directory the draft must sit directly in. Defaults to the main
            worktree's ``.task/plan``.

    Returns:
        New path after rename, resolved.

    Raises:
        InvalidIssueIdError: issue_id is not an issue number or ticket key.
        InvalidPlanFileError: plan_path is a symlink, is not an existing file,
            is not a draft plan name, or is not directly in plan_dir.
        FileExistsError: Target file already exists.
    """
    issue_id = _checked_issue_id(issue_id)
    if plan_dir is None:
        plan_dir = main_worktree_root() / ".task" / "plan"
    plan_dir = plan_dir.resolve()

    # A link would split the file judged from the file moved: a link to another
    # draft in the same directory moves that draft and leaves a dangling link.
    if plan_path.is_symlink():
        raise InvalidPlanFileError(f"reject (symlink): {plan_path}")
    source = plan_path.resolve()
    if not source.is_file():
        raise InvalidPlanFileError(f"reject (exists): not an existing file: {source}")
    if not is_draft_plan(source.name):
        raise InvalidPlanFileError(
            f"reject (is_draft_plan): not a draft plan name: {source.name}"
        )
    if source.parent != plan_dir:
        raise InvalidPlanFileError(
            f"reject (plan dir): {source.parent} is not {plan_dir}"
        )

    target = plan_dir / f"plan-{issue_id}.md"
    if target.exists():
        raise FileExistsError(
            f"Target already exists: {target}\n"
            f"Issue #{issue_id} may already have a plan file."
        )
    source.rename(target)
    return target


def plan_file_for_issue(issue_id: int | str, plan_dir: Path) -> Path:
    """Return path to plan-{issue_id}.md, raising if not found.

    Raises:
        InvalidIssueIdError: issue_id is not an issue number or ticket key.
        FileNotFoundError: The plan file does not exist.
    """
    path = plan_dir / f"plan-{_checked_issue_id(issue_id)}.md"
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
