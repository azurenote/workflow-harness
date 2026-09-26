"""What `project-issue` posts when a plan goes to an issue tracker.

A plan reaches the tracker three ways — as a new issue's body, as a comment on
an issue it is linked to, and as a revision comment later. All three share one
rule, kept here so the skill document and the code cannot hold two versions:

- A body is measured in **characters**, not bytes. Plans are mostly Korean, and
  a byte count would push a plan well inside the limit onto the summary path.
- A body over the tracker's limit is replaced by a fixed-format summary,
  extracted mechanically, so the same plan always yields the same bytes. A
  summary that is itself over the limit is never truncated; the caller stops.
- Every comment starts with a marker line, ``<!-- plan-<id> rev:<8 hex> -->``.
  Reading the issue back for that line — or for the plan text itself, which is
  what a create-mode body is — is how the same content is never posted twice.

The skill fences call this module as ``python -m harness_core.plan_body``; it
reads and writes local files only and never calls a tracker. It exits ``OK``
with the body chosen, ``REFUSED`` on a plan, id, revision or size it will not
post, and ``NOOP`` when the tracker already holds the content (``SEEN=``); see
``skills/_shared/references/exit-codes.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import is_draft_plan
from .exitcodes import ExitCode
from .git import MainWorktreeUnresolvedError, main_worktree_root
from .local import InvalidIssueIdError, _checked_issue_id, abs_under_main, plan_file_for_issue, split_frontmatter

# Characters. The skill's `## Plan Body Rules` table carries the same numbers,
# and a test compares the two. A tracker without a row here has no plan body
# rules: the skill leaves its path as it was.
LIMITS = {"github": 65536, "forgejo": 65536}

_SECTION_MISSING = "(섹션 없음)"
_NO_ITEMS = "(항목 없음)"
_ISOLATES = str.maketrans("", "", "\u2068\u2069")
_NO_TITLE = "(제목 없음)"


class PlanBodyError(Exception):
    """A refusal the CLI reports as one line and ``ExitCode.REFUSED``."""


@dataclass(frozen=True)
class PlanBody:
    kind: str  # "full" or "summary"
    text: str
    chars: int  # of the body chosen
    full_chars: int  # of the full candidate, marker included
    limit: int
    rev: str

    def info(self) -> str:
        return f"KIND={self.kind} CHARS={self.chars} LIMIT={self.limit} REV={self.rev}"


def revision(data: bytes) -> str:
    """The first 8 hex digits of the plan file's sha1."""
    return hashlib.sha1(data).hexdigest()[:8]


def marker(issue_id: str, rev: str) -> str:
    return f"<!-- plan-{issue_id} rev:{rev} -->"


def _normalized(text: str) -> str:
    """The text a reader sees: no BOM, LF line ends."""
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


class _Fences:
    """Tracks fenced code the way CommonMark closes it.

    A fence opens on three or more backticks or tildes and closes only on a
    line of the same character, at least as long, with nothing after it — so a
    four-backtick fence holding a three-backtick example stays one block, and
    a ```` ```text ```` line inside a fence does not close it.
    """

    def __init__(self) -> None:
        self.open = ""

    def step(self, line: str) -> bool:
        """Feed one line; True when it is part of a fence (markers included)."""
        stripped = line.strip()
        if self.open:
            run = re.match(r"(`+|~+)$", stripped)
            if run and run.group(1)[0] == self.open[0] and len(run.group(1)) >= len(self.open):
                self.open = ""
            return True
        opener = re.match(r"(`{3,}|~{3,})", line.lstrip())
        if opener:
            self.open = opener.group(1)
            return True
        return False


def _sections(body: str) -> tuple[str, dict[str, list[str]]]:
    """The first `# ` line and each `## ` section's lines, fenced code skipped.

    Only a heading outside a code fence counts: plans quote Markdown in fences,
    and a `## ` line inside one is an example, not a section.
    """
    title = ""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    fences = _Fences()
    for line in body.split("\n"):
        if fences.step(line):
            if current is not None:
                current.append(line)
            continue
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
            continue
        if not title and line.startswith("# "):
            title = line[2:].strip()
            title = title[len("Plan: "):].strip() if title.startswith("Plan: ") else title
            continue
        if current is not None:
            current.append(line)
    return title, sections


def _outside_fences(lines: list[str]) -> list[str]:
    fences = _Fences()
    return [line for line in lines if not fences.step(line)]


def _trimmed(lines: list[str]) -> str:
    text = "\n".join(line.rstrip() for line in lines).strip("\n")
    return text


_ITEM = re.compile(r"(?:[-*+]|\d+[.)]) ")


def _bullets(lines: list[str] | None) -> list[str]:
    """Top-level list items, first line only; nested items and prose are left out."""
    if lines is None:
        return [_SECTION_MISSING]
    items = [l.rstrip() for l in _outside_fences(lines) if _ITEM.match(l)]
    return items or [_NO_ITEMS]


def _task_titles(lines: list[str] | None) -> list[str]:
    if lines is None:
        return [_SECTION_MISSING]
    items = [f"- {l[4:].strip()}" for l in _outside_fences(lines) if l.startswith("### ")]
    return items or [_NO_ITEMS]


def _checklist(lines: list[str] | None) -> list[str]:
    if lines is None:
        return [_SECTION_MISSING]
    items = [l.rstrip() for l in _outside_fences(lines) if re.match(r"[-*+] \[[ xX]\] ", l)]
    # A Definition of Done written as plain bullets is still the checklist.
    return items or _bullets(lines)


def summarize(text: str, *, where: str, full_chars: int, limit: int) -> str:
    """The fixed-format summary that stands in for a plan over the limit.

    `where` names the local file that holds the full plan — a file name, never
    a path, so the same plan summarizes the same on every machine.
    """
    block, body = split_frontmatter(_normalized(text))
    title, sections = _sections(body)
    intent = sections.get("Intent Summary")
    out: list[str] = []
    if block:
        out += ["---", block, "---"]
    out += [
        f"# Plan: {title or _NO_TITLE}",
        "",
        f"> 요약본이다. 플랜 전문이 {full_chars:,} 문자로 한도 {limit:,} 문자를 넘어 고정 형식 요약을 올린다.",
        "",
        "## Intent Summary",
        _trimmed(intent) if intent is not None and _trimmed(intent) else _SECTION_MISSING,
        "",
        "## Non-Goals (항목 첫 줄)",
        *_bullets(sections.get("Non-Goals")),
        "",
        "## Drift Guards (항목 첫 줄)",
        *_bullets(sections.get("Drift Guards")),
        "",
        "## Task Cards (제목)",
        *_task_titles(sections.get("Task Cards")),
        "",
        "## Definition of Done",
        *_checklist(sections.get("Definition of Done")),
        "",
        f"전문: 로컬 {where} ({full_chars:,} 문자, 한도 {limit:,} 문자 초과)",
    ]
    return "\n".join(out) + "\n"


_CREATE_WHERE = "`plan-<이슈 번호>.md`(등록 뒤 이름)"


def build(text: str, tracker: str, rev: str, issue_id: str | None) -> PlanBody:
    """Choose the body: the full plan when it fits, else the summary.

    With `issue_id` this is a comment, and the marker line is part of what is
    measured. Raises PlanBodyError when even the summary is over the limit.
    """
    limit = LIMITS[tracker]
    head = f"{marker(issue_id, rev)}\n\n" if issue_id else ""
    where = f"`plan-{issue_id}.md`" if issue_id else _CREATE_WHERE
    full = head + text
    if len(full) <= limit:
        return PlanBody("full", full, len(full), len(full), limit, rev)
    summary = head + summarize(text, where=where, full_chars=len(full), limit=limit)
    if len(summary) <= limit:
        return PlanBody("summary", summary, len(summary), len(full), limit, rev)
    raise PlanBodyError(
        f"stop (too large): the summary is {len(summary):,} characters, "
        f"over the {tracker} limit of {limit:,}; nothing is posted"
    )


def create_summary(text: str, tracker: str) -> str:
    """The summary a create-mode body would carry — what a recovery run may find."""
    return summarize(text, where=_CREATE_WHERE, full_chars=len(text), limit=LIMITS[tracker])


def _block(text: str) -> str:
    """Text as compared: no BOM, LF line ends, no trailing space, no edge blank lines."""
    return "\n".join(l.rstrip() for l in _normalized(text).split("\n")).strip("\n")


def entries(read: str, tracker: str) -> list[str]:
    """The issue body and each comment in a tracker read, one entry each.

    - github: the JSON of `gh issue view --json body,comments`, taken as it is.
    - forgejo: `fj` output, where every line of a body or comment is quoted
      with `> ` (a blank one as `> `) and the lines between them — the title
      and author lines, wrapped in U+2068/U+2069 — are not. Each run of quoted
      lines is one entry, with that one level of quoting removed.

    Raises PlanBodyError when a GitHub read is not the JSON it should be.
    """
    if tracker == "github":
        try:
            data = json.loads(read)
            return [data.get("body") or ""] + [c.get("body") or "" for c in data.get("comments") or []]
        except (ValueError, AttributeError, TypeError) as exc:
            raise PlanBodyError("stop (read): the GitHub read is not `--json body,comments` output") from exc
    found: list[str] = []
    current: list[str] | None = None
    for line in read.translate(_ISOLATES).split("\n"):
        if line.startswith("> ") or line == ">":
            current = [] if current is None else current
            current.append(line[2:])
        elif current is not None:
            found.append("\n".join(current))
            current = None
    if current is not None:
        found.append("\n".join(current))
    return found


def seen(read: str, *, tracker: str, issue_id: str | None, rev: str, bodies: tuple[str, ...]) -> str | None:
    """Why this content is already on the issue, or None.

    Compared entry by entry, never as a substring of the whole read: a revision
    that only drops trailing lines is a prefix of the one before it, and must
    still be posted. An entry is this revision when its first line is this
    marker; it is this plan when, with a leading marker line taken off, it
    equals one of `bodies`.
    """
    wanted = marker(issue_id, rev) if issue_id else None
    candidates = {_block(b) for b in bodies if _block(b)}
    for entry in entries(read, tracker):
        lines = _block(entry).split("\n")
        if wanted and lines[0] == wanted:
            return "revision"
        if re.fullmatch(r"<!-- plan-\S+ rev:[0-9a-f]{8} -->", lines[0]):
            lines = lines[1:]
        if "\n".join(lines).strip("\n") in candidates:
            return "body"
    return None


def resolve_plan(path_arg: str | None, issue_id: str | None) -> Path:
    """The plan to post: a draft Step 1 validated, or plan-<id>.md in the main checkout."""
    try:
        plan_dir = main_worktree_root() / ".task" / "plan"
        if not path_arg:
            try:
                return plan_file_for_issue(issue_id, plan_dir)
            except FileNotFoundError as exc:
                raise PlanBodyError(f"reject (exists): no such plan: {plan_dir / f'plan-{issue_id}.md'}") from exc
        path = abs_under_main(Path(path_arg))
    except MainWorktreeUnresolvedError as exc:
        raise PlanBodyError(f"stop (main checkout): {exc}") from exc
    if is_draft_plan(path.name):
        pass
    elif issue_id and path.name == f"plan-{issue_id}.md":
        if path.resolve().parent != plan_dir.resolve():
            raise PlanBodyError(f"reject (plan dir): {path.parent} is not {plan_dir}")
    else:
        raise PlanBodyError(f"reject (name): not a draft or plan-{issue_id or '<id>'}.md: {path.name}")
    if not path.is_file():
        raise PlanBodyError(f"reject (exists): no such plan: {path}")
    return path


def main(argv: list[str] | None = None) -> ExitCode:
    parser = argparse.ArgumentParser(
        prog="python -m harness_core.plan_body",
        description="Choose the body project-issue posts for a plan (full or summary).",
    )
    parser.add_argument("tracker", choices=sorted(LIMITS))
    parser.add_argument("plan", nargs="?", help="plan file; omitted with --issue: plan-<id>.md")
    parser.add_argument("--issue", help="comment mode: the issue id the marker names")
    parser.add_argument("--out", help="file to write the body to")
    parser.add_argument("--seen", help="a tracker read of the issue body and comments")
    parser.add_argument("--expect-rev", help="the revision the approval screen showed")
    parser.add_argument("--dry-run", action="store_true", help="print the choice, write nothing")
    args = parser.parse_args(argv)
    if not args.plan and not args.issue:
        parser.error("give a plan file, --issue <id>, or both")
    if not args.dry_run and not args.out:
        parser.error("--out is required unless --dry-run")

    try:
        issue_id = _checked_issue_id(args.issue) if args.issue else None
        plan = resolve_plan(args.plan, issue_id)
        raw = plan.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlanBodyError(f"reject (encoding): {plan.name} is not UTF-8") from exc
        if not text.strip():
            raise PlanBodyError(f"reject (empty): {plan.name} has no content")
        rev = revision(raw)
        if args.expect_rev is not None and args.expect_rev != rev:
            raise PlanBodyError(
                f"stop (rev): {plan.name} changed since the screen: expected {args.expect_rev}, now {rev}"
            )
        body, too_large = None, None
        try:
            body = build(text, args.tracker, rev, issue_id)
        except PlanBodyError as exc:
            too_large = exc
        if args.seen is not None:
            try:
                read = Path(args.seen).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise PlanBodyError(f"stop (read): cannot read {args.seen}: {exc.strerror}") from exc
            why = seen(read, tracker=args.tracker, issue_id=issue_id, rev=rev,
                       bodies=(text, create_summary(text, args.tracker)))
            if why:
                print(f"SEEN={why} REV={rev}")
                return ExitCode.NOOP
        if too_large is not None:
            raise too_large
    except (PlanBodyError, InvalidIssueIdError) as exc:
        print(exc, file=sys.stderr)
        return ExitCode.REFUSED

    assert body is not None
    if not args.dry_run:
        Path(args.out).write_bytes(body.text.encode("utf-8"))
    print(body.info())
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
