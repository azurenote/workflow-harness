"""Bring `plan-<id>.md` back from the issue it was posted to.

`project-issue` posts an approved plan to its issue as a comment whose first
line is ``<!-- plan-<id> rev:<8 hex> -->`` (`harness_core.plan_body`). When the
local file is gone — another machine, a fresh clone, a cleanup — that comment
is still the approved plan, and `project-iterate` restores it from there
instead of writing a new one:

- The candidate is the **last** comment, in read order, whose first line is
  this issue's marker. Markers of other ids, a marker below the first line and
  the issue body are not candidates. A refused last comment is never replaced
  by an earlier one: the earlier one is not the latest approved plan.
- Its author must be the user the tracker CLI is signed in as. Anyone who can
  comment can post a marker with a matching rev; only the user's own comment
  was posted behind the user's own approval. The check is who posted the
  comment, not who last edited it: someone allowed to edit another user's
  comments is trusted as far as the tracker trusts them.
- The text below the marker must hash to the marker's rev. The text as read is
  tried first, then with exactly one trailing newline (Forgejo drops it); no
  other normalization.
- The file is created, never overwritten, in the main checkout's plan
  directory, and nothing is left behind when it is not.

The skill fences call this module as ``python -m harness_core.plan_restore``;
it reads local files only and never calls a tracker. It exits ``OK`` when it
restored the plan or found no candidate, ``FINDINGS`` when the last candidate
was refused (author, summary, rev), and ``REFUSED`` when it stopped before
judging (a read it cannot use, an existing file, no main checkout); see
``skills/_shared/references/exit-codes.md``. Every outcome prints one
``RESTORE=`` line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .exitcodes import ExitCode
from .git import MainWorktreeUnresolvedError, main_worktree_root
from .local import InvalidIssueIdError, _checked_issue_id
from .plan_body import LIMITS, SUMMARY_LEAD, marker, revision

# Mirrors of `plan_body._ISOLATES` and of the marker `plan_body.marker` writes;
# a test holds them together.
_ISOLATES = str.maketrans("", "", "\u2068\u2069")
_MARKER = re.compile(r"<!-- plan-(\S+) rev:([0-9a-f]{8}) -->")
# `fj … comments` heads each comment with `<display name> (<login>) said:`, or
# `<login> said:` for a user without one (forgejo-cli's message catalogue; the
# first form measured 2026-09-26). Anything else reads as no author.
_FJ_AUTHOR = re.compile(r"^(?:.*\s)?\(([^()\s]+)\) said:$|^([^()\s]+) said:$")
_FJ_LOGIN = re.compile(r"signed into (\S+)@[^@\s]+$")
# The line `fj issue view` ends an issue with; the comments read follows it.
_FJ_COUNT = re.compile(r"^(\d+) comments$")


class RestoreStop(Exception):
    """A stop before judging: `ExitCode.REFUSED`, one stderr line."""

    def __init__(self, why: str, detail: str) -> None:
        super().__init__(f"stop ({why}): {detail}")
        self.why = why


@dataclass(frozen=True)
class Comment:
    author: str | None
    text: str  # as read, one level of `fj` quoting removed


@dataclass(frozen=True)
class Verdict:
    """What the read decides. `data` is set only for "restored"."""

    outcome: str  # "restored", "none" or "refused"
    why: str = ""  # for "refused": "author", "summary" or "rev"
    rev: str = ""
    markers: int = 0  # comments carrying this issue's marker
    foreign: int = 0  # of those, by someone else
    data: bytes = b""

    def line(self, path: Path | None = None) -> str:
        counts = f"MARKERS={self.markers} FOREIGN={self.foreign}"
        if self.outcome == "restored":
            return f"RESTORE=restored REV={self.rev} {counts} PATH={path}"
        if self.outcome == "refused":
            return f"RESTORE=refused ({self.why}) REV={self.rev} {counts}"
        return f"RESTORE=none {counts}"


def comments(read: str, tracker: str) -> list[Comment]:
    """The comments of a tracker read, each with its author; the issue body is left out.

    - github: `gh issue view --json body,comments` — `comments[].body` and
      `comments[].author.login`.
    - forgejo: the `fj … issue view` read followed by its `comments` read.
      The issue view ends on `<N> comments`; labels and the body come before
      it, so only what follows the **last** such line is read, and there every
      run of `> `-quoted lines belongs to the `… said:` line above it. The
      number of `said:` lines must be N — a read that does not add up (no
      count line, a changed header, a comment posted between the reads) stops
      rather than reading as fewer comments. The U+2068/U+2069 isolates are
      taken off unquoted lines only: inside a quoted line they are the plan's
      own characters.
    """
    if tracker == "github":
        try:
            data = json.loads(read)
            found = []
            for item in data["comments"] or []:
                login = (item.get("author") or {}).get("login")
                body = item.get("body") or ""
                if not isinstance(body, str):
                    raise TypeError("a comment body is not text")
                found.append(Comment(login if isinstance(login, str) else None, body))
            return found
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            raise RestoreStop("read", "the GitHub read is not `--json body,comments` output") from exc
    lines = read.split("\n")
    plain = [None if l.startswith("> ") or l == ">" else l.translate(_ISOLATES).strip() for l in lines]
    counts = [i for i, l in enumerate(plain) if l is not None and _FJ_COUNT.match(l)]
    if not counts:
        raise RestoreStop("read", "the Forgejo read has no `<N> comments` line")
    expected = int(_FJ_COUNT.match(plain[counts[-1]]).group(1))
    found = []
    headers = 0
    author: str | None = None
    current: list[str] | None = None
    for line, head in zip(lines[counts[-1] + 1:] + [""], plain[counts[-1] + 1:] + [""]):
        if head is None:
            current = [] if current is None else current
            current.append(line[2:])
            continue
        if current is not None:
            found.append(Comment(author, "\n".join(current)))
            current, author = None, None
        if head.endswith(" said:"):
            headers += 1
            match = _FJ_AUTHOR.match(head)
            author = (match.group(1) or match.group(2)) if match else None
    if headers != expected:
        raise RestoreStop("read", f"the Forgejo read counts {expected} comments and heads {headers}")
    return found


def login(whoami: str, tracker: str) -> str:
    """The signed-in user: `gh api user --jq .login`, or `fj whoami`."""
    lines = [l.translate(_ISOLATES).strip() for l in whoami.splitlines() if l.strip()]
    if tracker == "github":
        name = lines[0] if len(lines) == 1 else ""
        ok = bool(re.fullmatch(r"[^\s@]+", name))
    else:
        match = _FJ_LOGIN.search(lines[0]) if len(lines) == 1 else None
        name = match.group(1) if match else ""
        ok = bool(name)
    if not ok:
        raise RestoreStop("whoami", f"cannot read the signed-in user from {whoami.strip()[:80]!r}")
    return name


def _first_line(text: str) -> str:
    return text.lstrip("\ufeff").lstrip("\r\n").split("\n", 1)[0].rstrip()


def judge(read: str, *, tracker: str, issue_id: str, me: str) -> Verdict:
    """Decide from a tracker read; writes nothing."""
    wanted = []
    for comment in comments(read, tracker):
        match = _MARKER.fullmatch(_first_line(comment.text))
        if match and match.group(1) == issue_id:
            wanted.append((comment, match.group(2)))
    if not wanted:
        return Verdict("none")
    counts = {"markers": len(wanted), "foreign": sum(1 for c, _ in wanted if c.author != me)}
    last, rev = wanted[-1]
    if last.author != me:
        return Verdict("refused", "author", rev, **counts)
    head = marker(issue_id, rev) + "\n"
    body = last.text[len(head):] if last.text.startswith(head) else None
    if body is not None and body.startswith("\n"):
        body = body[1:]
        for candidate in (body, body.rstrip("\n") + "\n"):
            data = candidate.encode("utf-8")
            if revision(data) == rev:
                return Verdict("restored", "", rev, data=data, **counts)
    summary = any(l.startswith(SUMMARY_LEAD) for l in last.text.split("\n"))
    return Verdict("refused", "summary" if summary else "rev", rev, **counts)


def write_new(target: Path, data: bytes) -> None:
    """Create `target` with `data`, never over anything already there — a
    dangling symlink included — and leave no temporary file, and no directory
    this call made, behind when it does not."""
    made = [d for d in (target.parent.parent, target.parent) if not os.path.lexists(d)]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RestoreStop("plan dir", f"cannot use {target.parent}: {exc.strerror}") from exc
    tmp = None
    done = False
    try:
        if os.path.lexists(target):
            raise RestoreStop("exists", f"{target} already exists")
        fd, tmp = tempfile.mkstemp(prefix=".plan-restore-", dir=target.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, 0o666 & ~_umask())  # a plan file, not mkstemp's 0600
        os.link(tmp, target)
        done = True
    except FileExistsError as exc:
        raise RestoreStop("exists", f"{target} already exists") from exc
    except OSError as exc:
        raise RestoreStop("write", f"cannot write {target}: {exc.strerror}") from exc
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        for directory in [] if done else reversed(made):
            try:
                directory.rmdir()  # only what this call made, and only while empty
            except OSError:
                pass


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _read(path: str) -> str:
    try:
        return Path(path).read_bytes().decode("utf-8")
    except OSError as exc:
        raise RestoreStop("read", f"cannot read {path}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise RestoreStop("read", f"{path} is not UTF-8") from exc


def main(argv: list[str] | None = None) -> ExitCode:
    parser = argparse.ArgumentParser(
        prog="python -m harness_core.plan_restore",
        description="Restore plan-<id>.md from the user's own last plan comment on the issue.",
    )
    parser.add_argument("tracker", choices=sorted(LIMITS))
    parser.add_argument("--issue", required=True, help="the issue id the marker names")
    parser.add_argument("--read", required=True, help="a tracker read of the issue body and comments")
    parser.add_argument("--whoami", required=True, help="the tracker CLI's signed-in user")
    args = parser.parse_args(argv)

    try:
        try:
            issue_id = _checked_issue_id(args.issue)
        except InvalidIssueIdError as exc:
            raise RestoreStop("id", str(exc)) from exc
        me = login(_read(args.whoami), args.tracker)
        verdict = judge(_read(args.read), tracker=args.tracker, issue_id=issue_id, me=me)
        if verdict.outcome == "restored":
            try:
                target = main_worktree_root() / ".task" / "plan" / f"plan-{issue_id}.md"
            except MainWorktreeUnresolvedError as exc:
                raise RestoreStop("main checkout", str(exc)) from exc
            write_new(target, verdict.data)
    except RestoreStop as exc:
        print(exc, file=sys.stderr)
        print(f"RESTORE=stopped ({exc.why})")
        return ExitCode.REFUSED

    if verdict.outcome == "refused":
        print(verdict.line())
        return ExitCode.FINDINGS
    if verdict.outcome == "restored":
        print(verdict.line(target))
        return ExitCode.OK
    print(verdict.line())
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
