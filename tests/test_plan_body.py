"""harness_core.plan_body — the body project-issue posts for a plan (#45)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness_core import plan_body
from harness_core.exitcodes import ExitCode
from harness_core.git import MainWorktreeUnresolvedError
from harness_core.plan_body import LIMITS, build, main, marker, revision, seen, summarize

PLAN = """\
---
base_branch: feat/x
---
# Plan: 예시 플랜

## Intent Summary
의도 첫 줄.
의도 둘째 줄.

## Non-Goals
- 하지 않는 것 하나
  이어지는 줄은 빠진다
- 하지 않는 것 둘

## Drift Guards
- 경계 하나

```markdown
## Task Cards
- 펜스 안의 가짜 항목
```

## Definition of Done
- [ ] 첫 조건
  - [ ] 들여쓴 하위 조건은 빠진다
- [x] 둘째 조건

## Task Cards

### Task 1: 첫 태스크
본문

### Task 2: 둘째 태스크
"""

# The task body makes the plan longer than its summary, as a real one is.
PLAN = PLAN.replace("\n본문\n", "\n" + "긴 본문 " * 200 + "\n")

SUMMARY_TAIL = """\
---
base_branch: feat/x
---
# Plan: 예시 플랜

> 요약본이다. 플랜 전문이 {full:,} 문자로 한도 {limit:,} 문자를 넘어 고정 형식 요약을 올린다.

## Intent Summary
의도 첫 줄.
의도 둘째 줄.

## Non-Goals (항목 첫 줄)
- 하지 않는 것 하나
- 하지 않는 것 둘

## Drift Guards (항목 첫 줄)
- 경계 하나

## Task Cards (제목)
- Task 1: 첫 태스크
- Task 2: 둘째 태스크

## Definition of Done
- [ ] 첫 조건
- [x] 둘째 조건

전문: 로컬 {where} ({full:,} 문자, 한도 {limit:,} 문자 초과)
"""


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch):
    def set_limits(**values: int) -> None:
        monkeypatch.setattr(plan_body, "LIMITS", {**LIMITS, **values})
    return set_limits


@pytest.fixture
def main_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "main"
    (root / ".task" / "plan").mkdir(parents=True)
    monkeypatch.setattr(plan_body, "main_worktree_root", lambda: root)
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def test_the_limits_are_characters_for_two_trackers() -> None:
    assert LIMITS == {"github": 65536, "forgejo": 65536}


def test_characters_not_bytes_decide(limits) -> None:
    text = "가" * 100
    assert len(text) == 100 < len(text.encode("utf-8"))
    limits(github=len(text))  # bytes would be 300: over. Characters: exactly at the limit.
    assert build(text, "github", "r", None).kind == "full"


def test_the_boundary_is_inclusive_and_the_marker_counts(limits) -> None:
    text = PLAN
    limits(github=len(text))
    assert build(text, "github", "abcd1234", None).kind == "full"
    assert build(text, "github", "abcd1234", "45").kind == "summary", "the marker line was not measured"
    limits(github=len(text) - 1)
    assert build(text, "github", "abcd1234", None).kind == "summary"
    head = marker("45", "abcd1234") + "\n\n"
    limits(github=len(head + text))
    assert build(text, "github", "abcd1234", "45").kind == "full"


def test_each_tracker_uses_its_own_limit(limits) -> None:
    limits(github=len(PLAN), forgejo=len(PLAN) - 1)
    assert build(PLAN, "github", "r", None).kind == "full"
    assert build(PLAN, "forgejo", "r", None).kind == "summary"


def test_revision_is_the_sha1_prefix_of_the_file_bytes() -> None:
    data = PLAN.encode("utf-8")
    assert revision(data) == hashlib.sha1(data).hexdigest()[:8]
    assert revision(data.replace("첫 조건".encode(), "첫 조껀".encode())) != revision(data)


def test_summary_is_the_fixed_format() -> None:
    got = summarize(PLAN, where="`plan-45.md`", full_chars=70000, limit=65536)
    assert got == SUMMARY_TAIL.format(full=70000, limit=65536, where="`plan-45.md`")


@pytest.mark.parametrize("fence", ["````markdown\n```\n## Drift Guards\n- fake guard\n```\n````", "```\n```text\n- inside\n```"])
def test_summary_follows_commonmark_fences(fence: str) -> None:
    text = f"# Plan: t\n\n## Non-Goals\n{fence}\n- real\n\n## Drift Guards\n- guard\n"
    got = summarize(text, where="`x`", full_chars=1, limit=1)
    assert "## Non-Goals (항목 첫 줄)\n- real\n" in got
    assert "## Drift Guards (항목 첫 줄)\n- guard\n" in got
    assert "fake" not in got and "inside" not in got


def test_summary_takes_a_plain_dod_and_other_bullets() -> None:
    text = "# Plan: t\n\n## Non-Goals\n* 별표\n1. 번호\n\n## Definition of Done\n- 체크박스 없는 조건\n  - 하위\n"
    got = summarize(text, where="`x`", full_chars=1, limit=1)
    assert "## Non-Goals (항목 첫 줄)\n* 별표\n1. 번호\n" in got
    assert "## Definition of Done\n- 체크박스 없는 조건\n\n" in got


def test_summary_marks_missing_sections_and_empty_lists() -> None:
    got = summarize("# Plan: t\n\n## Non-Goals\n본문뿐\n", where="`x`", full_chars=1, limit=1)
    assert "## Intent Summary\n(섹션 없음)\n" in got
    assert "## Non-Goals (항목 첫 줄)\n(항목 없음)\n" in got
    assert "## Drift Guards (항목 첫 줄)\n(섹션 없음)\n" in got
    assert got.startswith("# Plan: t\n"), "a plan without frontmatter grew a frontmatter block"
    assert summarize("본문만\n", where="`x`", full_chars=1, limit=1).startswith("# Plan: (제목 없음)\n")


def test_summary_is_deterministic_and_ignores_crlf_and_bom() -> None:
    a = summarize(PLAN, where="`p`", full_chars=1, limit=1)
    assert a == summarize(PLAN, where="`p`", full_chars=1, limit=1)
    assert summarize("﻿" + PLAN.replace("\n", "\r\n"), where="`p`", full_chars=1, limit=1) == a


def test_create_mode_summary_names_the_file_to_come() -> None:
    text = PLAN
    got = plan_body.create_summary(text, "github")
    assert got.rstrip("\n").endswith(f"전문: 로컬 `plan-<이슈 번호>.md`(등록 뒤 이름) ({len(text):,} 문자, 한도 65,536 문자 초과)")


def test_a_summary_over_the_limit_is_refused(limits) -> None:
    limits(github=50)
    with pytest.raises(plan_body.PlanBodyError, match="stop \\(too large\\)"):
        build(PLAN, "github", "r", None)


_AUTHOR = "⁨⁩⁨W⁩⁨⁩ said:"


def _fj(*bodies: str) -> str:
    """A Forgejo `comments` read: an isolate-wrapped author line, then the body quoted."""
    return "".join(
        _AUTHOR + "\n" + "".join(f"> {l}\n" if l else "> \n" for l in b.split("\n")) + "\n\n" for b in bodies
    )


def _gh(body: str, *comments: str) -> str:
    return json.dumps({"body": body, "comments": [{"body": c} for c in comments]})


M = "<!-- plan-45 rev:abcd1234 -->"


@pytest.mark.parametrize("tracker, read, expected", [
    ("forgejo", _fj(f"{M}\n\n본문"), "revision"),
    ("github", _gh("사람 본문", f"{M}\n\n본문"), "revision"),
    ("forgejo", _fj("<!-- plan-45 rev:00000000 -->\n\n옛 플랜"), None),      # an older revision
    ("forgejo", _fj("<!-- plan-4 rev:abcd1234 -->"), None),                   # another issue
    ("forgejo", _fj("<!-- plan-450 rev:abcd1234 -->"), None),
    ("forgejo", _fj(f"> {M}"), None),                                          # quoted inside a comment
    ("github", _gh("", f"> {M}"), None),
    ("forgejo", _fj(f"설명 {M}"), None),                                       # not a whole line
    ("forgejo", _fj(f"{M} 뒤에 글"), None),                                    # text after the marker
    ("github", _gh("", f"첫 줄\n{M}"), None),                                  # not the first line
    ("forgejo", "", None),
    ("github", _gh(""), None),
])
def test_seen_needs_the_marker_as_an_entrys_first_line(tracker: str, read: str, expected: str | None) -> None:
    assert seen(read, tracker=tracker, issue_id="45", rev="abcd1234", bodies=()) == expected


QUOTED_PLAN = PLAN.replace("## Drift Guards\n", "## Drift Guards\n> 인용 줄이 있는 플랜\n>\n")


@pytest.mark.parametrize("tracker", ["forgejo", "github"])
def test_seen_finds_the_plan_as_a_whole_body(tracker: str) -> None:
    read = (_fj(QUOTED_PLAN) if tracker == "forgejo" else _gh(QUOTED_PLAN))
    assert seen(read, tracker=tracker, issue_id="45", rev="x", bodies=(QUOTED_PLAN,)) == "body"
    changed = QUOTED_PLAN.replace("둘째 태스크", "셋째 태스크")
    assert seen(read, tracker=tracker, issue_id="45", rev="x", bodies=(changed,)) is None
    # A comment that is this plan behind an older marker is still this plan.
    old = f"<!-- plan-45 rev:00000000 -->\n\n{QUOTED_PLAN}"
    read = (_fj(old) if tracker == "forgejo" else _gh("", old))
    assert seen(read, tracker=tracker, issue_id="45", rev="x", bodies=(QUOTED_PLAN,)) == "body"


@pytest.mark.parametrize("tracker", ["forgejo", "github"])
def test_seen_never_takes_a_prefix_for_the_plan(tracker: str) -> None:
    """A revision that only drops trailing lines is a prefix of the one before it."""
    shorter = PLAN.rsplit("### Task 2", 1)[0]
    read = (_fj(PLAN) if tracker == "forgejo" else _gh(PLAN))
    assert seen(read, tracker=tracker, issue_id="45", rev="x", bodies=(shorter,)) is None
    assert seen(read, tracker=tracker, issue_id="45", rev="x", bodies=(PLAN[:-3],)) is None
    unrelated = (_fj(f"앞 {PLAN} 뒤") if tracker == "forgejo" else _gh(f"앞 {PLAN} 뒤"))
    assert seen(unrelated, tracker=tracker, issue_id="45", rev="x", bodies=(PLAN,)) is None


def test_seen_reads_isolates_and_bare_quote_lines_on_forgejo() -> None:
    read = "⁨t⁩ #⁨45⁩\nBy ⁨me⁩ — Open\n\n" + "".join(
        ">\n" if not l else f"> ⁨{l}⁩\n" if l.startswith("## Intent") else f"> {l}\n"
        for l in PLAN.split("\n")
    )
    assert seen(read, tracker="forgejo", issue_id="45", rev="x", bodies=(PLAN,)) == "body"


def test_seen_refuses_a_github_read_that_is_not_json() -> None:
    with pytest.raises(plan_body.PlanBodyError, match="stop \\(read\\)"):
        seen("사람 본문\n댓글", tracker="github", issue_id="45", rev="x", bodies=(PLAN,))


# ── CLI ──────────────────────────────────────────────────────────────────


def test_cli_create_mode_in_limit_writes_the_plan_bytes(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-x.md", PLAN)
    out = tmp_path / "body"
    assert main(["github", str(plan), "--out", str(out)]) == 0
    assert out.read_bytes() == plan.read_bytes()
    rev = revision(plan.read_bytes())
    assert capsys.readouterr().out == f"KIND=full CHARS={len(PLAN)} LIMIT=65536 REV={rev}\n"


def test_cli_comment_mode_finds_plan_id_in_the_main_checkout(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    out = tmp_path / "body"
    assert main(["forgejo", "--issue", "45", "--out", str(out)]) == 0
    rev = revision(plan.read_bytes())
    assert out.read_text(encoding="utf-8") == f"{marker('45', rev)}\n\n{PLAN}"


def test_cli_summary_path(tmp_path: Path, main_root: Path, limits, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    limits(forgejo=len(PLAN))
    out = tmp_path / "body"
    assert main(["forgejo", "--issue", "45", "--out", str(out)]) == 0
    rev = revision(plan.read_bytes())
    full = len(marker("45", rev)) + 2 + len(PLAN)
    expected = f"{marker('45', rev)}\n\n" + SUMMARY_TAIL.format(full=full, limit=len(PLAN), where="`plan-45.md`")
    assert out.read_text(encoding="utf-8") == expected
    assert capsys.readouterr().out.startswith("KIND=summary ")


def test_cli_too_large_writes_nothing(tmp_path: Path, main_root: Path, limits, capsys) -> None:
    _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    limits(forgejo=40)
    out = _write(tmp_path / "body", "")
    assert main(["forgejo", "--issue", "45", "--out", str(out)]) == ExitCode.REFUSED
    assert out.read_bytes() == b""
    assert "stop (too large)" in capsys.readouterr().err


def test_cli_seen_exits_3_and_writes_nothing(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    rev = revision(plan.read_bytes())
    read = _write(tmp_path / "read", _fj(f"{marker('45', rev)}\n\nx"))
    out = _write(tmp_path / "body", "")
    assert main(["forgejo", "--issue", "45", "--seen", str(read), "--out", str(out)]) == ExitCode.NOOP
    assert out.read_bytes() == b""
    assert capsys.readouterr().out == f"SEEN=revision REV={rev}\n"

    _write(read, _fj(f"{marker('45', '00000000')}\n\nx"))
    assert main(["forgejo", "--issue", "45", "--seen", str(read), "--out", str(out)]) == 0
    assert out.read_bytes() != b""


def test_cli_seen_counts_a_create_mode_summary_body(tmp_path: Path, main_root: Path, limits) -> None:
    _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    limits(forgejo=len(PLAN) - 1)
    # Built from the literal format, not from create_summary: the CLI calls that.
    summary = SUMMARY_TAIL.format(full=len(PLAN), limit=65536, where="`plan-<이슈 번호>.md`(등록 뒤 이름)")
    read = _write(tmp_path / "read", _gh(summary, "딴 댓글"))
    assert main(["github", "--issue", "45", "--seen", str(read), "--dry-run"]) == ExitCode.NOOP


def test_cli_seen_is_checked_even_when_the_summary_is_too_large(tmp_path: Path, main_root: Path, limits) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    limits(forgejo=40)
    read = _write(tmp_path / "read", _fj(marker("45", revision(plan.read_bytes()))))
    assert main(["forgejo", "--issue", "45", "--seen", str(read), "--dry-run"]) == ExitCode.NOOP


def test_cli_expect_rev_mismatch_refuses(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    out = _write(tmp_path / "body", "")
    assert main(["forgejo", "--issue", "45", "--expect-rev", "00000000", "--out", str(out)]) == ExitCode.REFUSED
    assert out.read_bytes() == b"" and "stop (rev)" in capsys.readouterr().err
    rev = revision(plan.read_bytes())
    assert main(["forgejo", "--issue", "45", "--expect-rev", rev, "--out", str(out)]) == 0


def test_cli_dry_run_writes_nothing(tmp_path: Path, main_root: Path, capsys) -> None:
    _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    assert main(["github", "--issue", "45", "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("KIND=full ")
    assert list(tmp_path.iterdir()) == [main_root]


@pytest.mark.parametrize("argv, message", [
    (["forgejo", "--issue", "46", "--dry-run"], "reject (exists)"),
    (["forgejo", "--issue", "4x", "--dry-run"], "reject (id)"),
    (["forgejo", "{plan4}", "--issue", "45", "--dry-run"], "reject (name)"),
    (["forgejo", "{notes}", "--dry-run"], "reject (name)"),
    (["forgejo", "{stray}", "--issue", "45", "--dry-run"], "reject (plan dir)"),
    (["forgejo", "{empty}", "--dry-run"], "reject (empty)"),
    (["forgejo", "{plan45}", "--issue", "45", "--seen", "{missing}", "--dry-run"], "stop (read)"),
])
def test_cli_refusals(argv: list[str], message: str, main_root: Path, capsys) -> None:
    plan4 = _write(main_root / ".task" / "plan" / "plan-4.md", PLAN)
    plan45 = _write(main_root / ".task" / "plan" / "plan-45.md", PLAN)
    notes = _write(main_root / "notes.md", PLAN)
    stray = _write(main_root / "elsewhere" / "plan-45.md", PLAN)
    empty = _write(main_root / ".task" / "plan" / "plan-draft-empty.md", " \n")
    missing = main_root / "no-such-read"
    argv = [a.format(plan4=plan4, plan45=plan45, notes=notes, stray=stray, empty=empty, missing=missing) for a in argv]
    assert main(argv) == ExitCode.REFUSED
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["jira", "--issue", "45", "--dry-run"],
    ["gitea", "--issue", "45", "--dry-run"],
    ["forgejo", "--dry-run"],
    ["forgejo", "--issue", "45"],
])
def test_cli_usage_errors_exit_2(argv: list[str], main_root: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_cli_stops_when_the_main_checkout_cannot_be_resolved(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def unresolved() -> Path:
        raise MainWorktreeUnresolvedError("the first worktree entry /x has no work tree")
    monkeypatch.setattr(plan_body, "main_worktree_root", unresolved)
    for argv in (["forgejo", "--issue", "45", "--dry-run"], ["forgejo", "/abs/plan-draft-x.md", "--dry-run"]):
        assert main(argv) == ExitCode.REFUSED
        err = capsys.readouterr().err
        assert err.startswith("stop (main checkout):") and err.count("\n") == 1


# ── Step 2 screen (#65) ──────────────────────────────────────────────────────
#
# `--screen` prints project-issue Step 2's screen and a SCREEN= line. The
# goldens pin every byte but the hash (the path is a tmp path); the hash is
# checked by recomputing it here from what was printed, so a gap between what
# is shown and what is hashed goes red.

import os
import subprocess
import sys

from harness_core.local import read_plan_preview

SCREEN_PLAN = "# Plan: 화면 예시\n\n## Intent Summary\n의도.\n"
SCREEN_PLAN_FM = "---\nbase_branch: feat/x   # 통합 브랜치\n---\n" + SCREEN_PLAN
_CREATE_Q = "Are the Intent Summary and base branch correct? Create an issue from this file? [yes/no]"
_LINK_Q = "Are the Intent Summary and base branch correct? Link this file to #65 and post it as a comment? [yes/no]"
_LINK_ONLY_Q = "Are the Intent Summary and base branch correct? Link this file to #65? [yes/no]"
_I = "⁨"
_J = "⁩"


def _fj_read(title: str, number: str = "65", state: str = "Open", *, pull: bool = False) -> str:
    """`fj --style minimal issue view` as measured on #65 (issue) and #77 (pull request), 2026-09-26."""
    head = f"{_I}{_J}{_I}{title}{_J} {_I}{_J}#{_I}{number}{_J}{_I}{_J}"
    by = f"By {_I}{_J}{_I}my{_J}{_I}{_J} — {_I}{_I}{_J}{state}{_I}{_J}{_J}"
    if pull:
        return (f"{head}\n{by} — {_I}{_J}+{_I}1093{_J} {_I}{_J}-{_I}12{_J}{_I}{_J}\n"
                f"{_I}From `{_I}feat/x{_J}` into `{_I}main{_J}`{_J}\n\n")
    return f'{head}"\n{by}\npriority/1\n\n> 본문\n> By x — Closed\n'


def _gh_read(title: str, number: int = 65, state: str = "OPEN") -> str:
    return json.dumps({"number": number, "title": title, "state": state, "url": f"https://h/o/r/issues/{number}",
                       "body": "b", "labels": []})


def _split_screen(out: str) -> tuple[str, str, str | None]:
    """(screen body, SCREEN= value, SCREEN_MATCH= value or None) — the SCREEN= line exactly once."""
    lines = out.split("\n")
    assert lines[-1] == ""
    marks = [i for i, l in enumerate(lines) if l.startswith("SCREEN=")]
    assert len(marks) == 1, out
    i = marks[0]
    match = lines[i + 1].removeprefix("SCREEN_MATCH=") if lines[i + 1].startswith("SCREEN_MATCH=") else None
    assert lines[i + 1 + (match is not None):] == [""], out
    return "\n".join(lines[:i]) + "\n", lines[i].removeprefix("SCREEN="), match


def _own_hash(body: str, rev: str) -> str:
    return hashlib.sha256(("rev:" + rev + "\n" + body).encode("utf-8")).hexdigest()[:12]


def _screen(capsys, argv: list[str]) -> tuple[str, str, str | None]:
    assert main(argv) == ExitCode.OK
    return _split_screen(capsys.readouterr().out)


def test_i65_screen_readers_cover_the_trackers_with_limits() -> None:
    assert set(plan_body.ISSUE_READERS) == set(LIMITS)


@pytest.mark.parametrize("tracker", ["forgejo", "github"])
@pytest.mark.parametrize("text, base", [(SCREEN_PLAN, "main (default)"), (SCREEN_PLAN_FM, "feat/x")])
def test_i65_create_screen_golden(tracker: str, text: str, base: str, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", text)
    body, value, match = _screen(capsys, [tracker, str(plan), "--screen", "--default-base", "main"])
    head = "---\nbase_branch: feat/x   # 통합 브랜치\n---\n" if text is SCREEN_PLAN_FM else ""
    assert body == (
        f"file: {plan.resolve()}\n"
        "title: 화면 예시\n"
        f"base branch: {base}\n"
        "human preview:\n"
        f"{head}# Plan: 화면 예시\n\n## Intent Summary\n의도.\n"
        "\n"
        f"{_CREATE_Q}\n"
    )
    assert value == _own_hash(body, revision(plan.read_bytes())) and match is None


@pytest.mark.parametrize("tracker, read, state", [
    ("forgejo", _fj_read("이슈 제목 — #12 를 잇는다"), "Open"),
    ("github", _gh_read("이슈 제목 — #12 를 잇는다"), "OPEN"),
])
def test_i65_link_screen_golden(tracker: str, read: str, state: str, tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    issue_read = _write(tmp_path / "read", read)
    rev = revision(plan.read_bytes())
    body, value, _ = _screen(capsys, [tracker, str(plan), "--issue", "65", "--screen", "--issue-read", str(issue_read),
                                      "--default-base", "main"])
    chars = len(marker("65", rev)) + 2 + len(SCREEN_PLAN)
    assert body == (
        f"file: {plan.resolve()}\n"
        "title: 화면 예시\n"
        "base branch: main (default)\n"
        "human preview:\n"
        "# Plan: 화면 예시\n\n## Intent Summary\n의도.\n"
        "\n"
        f"issue: #65 이슈 제목 — #12 를 잇는다 ({state})\n"
        f"comment: plan-65.md after the rename — full, {chars}/65536 characters, rev {rev}\n"
        "\n"
        f"{_LINK_Q}\n"
    )
    assert value == _own_hash(body, rev)


@pytest.mark.parametrize("tracker", ["forgejo", "github"])
def test_i65_link_screen_over_the_limit_carries_the_refusal(tracker: str, tmp_path: Path, main_root: Path, limits,
                                                            capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    read = _fj_read("제목") if tracker == "forgejo" else _gh_read("제목")
    issue_read = _write(tmp_path / "read", read)
    limits(**{tracker: 40})
    body, value, _ = _screen(capsys, [tracker, str(plan), "--issue", "65", "--screen", "--issue-read", str(issue_read),
                                      "--default-base", "main"])
    lines = body.split("\n")
    assert lines[-4].startswith("comment: stop (too large): the summary is ")
    assert lines[-4].endswith(f"over the {tracker} limit of 40; nothing is posted")
    assert lines[-3:] == ["", _LINK_ONLY_Q, ""]
    assert value == _own_hash(body, revision(plan.read_bytes()))


def test_i65_screen_preview_is_the_step2_preview(main_root: Path, capsys) -> None:
    """The same 30 lines `local.read_plan_preview` gives, trailing blank lines aside."""
    long_plan = "---\nbase_branch: feat/x\n---\n\n# Plan: 긴 플랜\n" + "".join(f"줄 {i}\n" for i in range(1, 40))
    plan = _write(main_root / ".task" / "plan" / "plan-draft-long.md", long_plan)
    body, _, _ = _screen(capsys, ["forgejo", str(plan), "--screen"])
    shown = body.split("\n")
    start = shown.index("human preview:") + 1
    expected = read_plan_preview(plan).split("\n")
    assert shown[start:start + len(expected)] == expected
    assert expected[-1] == "줄 29" and shown[start + len(expected)] == ""


def test_i65_screen_is_the_same_for_the_same_inputs_and_moves_with_each(tmp_path: Path, main_root: Path,
                                                                        capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN + "".join(f"줄 {i}\n" for i in range(40)))
    read = _write(tmp_path / "read", _fj_read("제목"))
    link = ["forgejo", str(plan), "--issue", "65", "--screen", "--issue-read", str(read), "--default-base", "main"]
    create = ["forgejo", str(plan), "--screen", "--default-base", "main"]
    first = _screen(capsys, link)
    assert _screen(capsys, link) == first, "the same inputs gave another screen"
    created = _screen(capsys, create)

    # An edit past the 30 preview lines leaves the create screen's text as it
    # was: only the revision in the hash can see it.
    _write(plan, plan.read_text(encoding="utf-8") + "끝에 더한 줄\n")
    edited = _screen(capsys, create)
    assert edited[0] == created[0] and edited[1] != created[1]

    _write(plan, SCREEN_PLAN + "".join(f"줄 {i}\n" for i in range(40)))
    assert _screen(capsys, link) == first
    for changed in (_fj_read("다른 제목"), _fj_read("제목", state="Closed")):
        _write(read, changed)
        assert _screen(capsys, link)[1] != first[1], changed
    _write(read, _fj_read("제목"))
    moved = _write(main_root / ".task" / "plan" / "plan-draft-t.md", plan.read_text(encoding="utf-8"))
    assert _screen(capsys, [a if a != str(plan) else str(moved) for a in link])[1] != first[1]


def test_i65_comment_line_is_what_dry_run_reports(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", PLAN)
    read = _write(tmp_path / "read", _gh_read("제목"))
    body, _, _ = _screen(capsys, ["github", str(plan), "--issue", "65", "--screen", "--issue-read", str(read)])
    assert main(["github", str(plan), "--issue", "65", "--dry-run"]) == ExitCode.OK
    info = dict(kv.split("=") for kv in capsys.readouterr().out.split())
    comment = next(l for l in body.split("\n") if l.startswith("comment: "))
    assert comment == (f"comment: plan-65.md after the rename — {info['KIND']}, {info['CHARS']}/{info['LIMIT']} "
                       f"characters, rev {info['REV']}")


def test_i65_expect_screen_says_whether_it_matches(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    argv = ["forgejo", str(plan), "--screen", "--default-base", "main"]
    body, value, _ = _screen(capsys, argv)
    assert _screen(capsys, argv + ["--expect-screen", value]) == (body, value, "yes")
    assert _screen(capsys, argv + ["--expect-screen", "0" * 12]) == (body, value, "no")
    for near in ("", value[:6], value + "0", value.upper()):  # only the whole value, exactly
        assert _screen(capsys, argv + ["--expect-screen", near]) == (body, value, "no"), near


@pytest.mark.parametrize("read, expected", [
    (_fj_read("제목"), ("65", "제목", "Open")),
    (_fj_read("닫힌 제목", "40", "Closed"), ("40", "닫힌 제목", "Closed")),
    (_fj_read("제목 #12 — 그리고 #3", "7"), ("7", "제목 #12 — 그리고 #3", "Open")),
    (_fj_read("풀 리퀘스트", "77", pull=True), ("77", "풀 리퀘스트", "Open")),
    (_fj_read("By x — Closed — 제목이 By 로 시작한다"), ("65", "By x — Closed — 제목이 By 로 시작한다", "Open")),
    (_fj_read("끝에 공백 둘  "), ("65", "끝에 공백 둘", "Open")),
])
def test_i65_forgejo_read(read: str, expected: tuple[str, str, str]) -> None:
    got = plan_body.ISSUE_READERS["forgejo"](read)
    assert (got.number, got.title, got.state) == expected


@pytest.mark.parametrize("read", [
    "",
    "Error: not found\n",
    _fj_read("제목", state="Merged"),
    _fj_read("제목").replace("By ", "> By "),  # only the quoted body's `> By x — Closed` is left
    _fj_read("제목").replace("#", ""),  # no number after the title
])
def test_i65_forgejo_read_refuses_what_it_cannot_read(read: str) -> None:
    with pytest.raises(plan_body.PlanBodyError, match="stop \\(read\\)"):
        plan_body.ISSUE_READERS["forgejo"](read)


def test_i65_github_read() -> None:
    got = plan_body.ISSUE_READERS["github"](_gh_read("제목", 65, "CLOSED"))
    assert (got.number, got.title, got.state) == ("65", "제목", "CLOSED")
    for bad in ("not json", json.dumps({"number": "65", "title": "t", "state": "OPEN"}),
                json.dumps({"number": 65, "title": " ", "state": "OPEN"}), json.dumps({"title": "t"}), "[]",
                _gh_read("제목\nSCREEN=deadbeef0000"), _gh_read("제목\r"), json.dumps({"number": True, "title": "t", "state": "OPEN"}),
                _gh_read("제목", state="")):
        with pytest.raises(plan_body.PlanBodyError, match="stop \\(read\\)"):
            plan_body.ISSUE_READERS["github"](bad)


@pytest.mark.parametrize("argv, message", [
    (["forgejo", "--issue", "65", "--screen", "--issue-read", "{read}"], "reject (plan)"),
    (["forgejo", "{draft}", "--issue", "65", "--screen", "--default-base", "main"], "reject (read)"),
    (["forgejo", "{draft}", "--screen", "--issue-read", "{read}", "--default-base", "main"], "reject (read)"),
    (["forgejo", "{plan65}", "--issue", "65", "--screen", "--issue-read", "{read}", "--default-base", "main"],
     "reject (name)"),
    (["forgejo", "{draft}", "--screen"], "reject (base)"),
    (["forgejo", "{draft}", "--issue", "65", "--screen", "--issue-read", "{missing}", "--default-base", "main"],
     "stop (read)"),
    (["forgejo", "{draft}", "--issue", "65", "--screen", "--issue-read", "{garbled}", "--default-base", "main"],
     "stop (read)"),
    (["forgejo", "{draft}", "--issue", "66", "--screen", "--issue-read", "{read}", "--default-base", "main"],
     "stop (read): the read is issue #65, not #66"),
])
def test_i65_screen_refusals(argv: list[str], message: str, tmp_path: Path, main_root: Path, capsys) -> None:
    paths = {
        "draft": _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN),
        "plan65": _write(main_root / ".task" / "plan" / "plan-65.md", SCREEN_PLAN),
        "read": _write(tmp_path / "read", _fj_read("제목")),
        "garbled": _write(tmp_path / "garbled", "제목만 있다\n"),
        "missing": tmp_path / "no-such-read",
    }
    assert main([a.format(**paths) for a in argv]) == ExitCode.REFUSED
    err = capsys.readouterr()
    assert message in err.err and "SCREEN=" not in err.out


@pytest.mark.parametrize("extra", [
    ["--out", "x"], ["--dry-run"], ["--seen", "x"], ["--expect-rev", "abcd1234"],
])
def test_i65_screen_takes_no_body_flags(extra: list[str], main_root: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["forgejo", "/abs/plan-draft-s.md", "--screen", "--default-base", "main", *extra])
    assert exc.value.code == ExitCode.REFUSED


@pytest.mark.parametrize("extra", [
    ["--issue-read", "x"], ["--default-base", "main"], ["--expect-screen", "abc"],
])
def test_i65_screen_flags_need_screen(extra: list[str], main_root: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["forgejo", "/abs/plan-draft-s.md", "--dry-run", *extra])
    assert exc.value.code == ExitCode.REFUSED


def test_i65_bom_and_crlf_plans_read_the_same(main_root: Path, capsys) -> None:
    plain = _write(main_root / ".task" / "plan" / "plan-draft-a.md", SCREEN_PLAN_FM)
    odd = main_root / ".task" / "plan" / "plan-draft-b.md"
    odd.write_bytes(b"\xef\xbb\xbf" + SCREEN_PLAN_FM.replace("\n", "\r\n").encode("utf-8"))
    a, _, _ = _screen(capsys, ["forgejo", str(plain), "--screen"])
    b, _, _ = _screen(capsys, ["forgejo", str(odd), "--screen"])
    assert b.replace("plan-draft-b.md", "plan-draft-a.md") == a
    assert "base branch: feat/x\n" in b and "title: 화면 예시\n" in b


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_i65_screen_is_the_same_from_any_checkout_and_locale(tmp_path: Path) -> None:
    """A real repository with a linked worktree: relative or absolute path, main or linked CWD, any locale."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
    _git(root, "worktree", "add", "-q", str(tmp_path / "linked"), "-b", "side")
    plan = _write(root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    src = str(Path(plan_body.__file__).resolve().parents[1])

    def run(cwd: Path, path: str, **env: str) -> str:
        base = {"PATH": os.environ["PATH"], "PYTHONPATH": src, "HOME": str(tmp_path)}
        done = subprocess.run([sys.executable, "-m", "harness_core.plan_body", "forgejo", path, "--screen",
                               "--default-base", "main"], cwd=cwd, env={**base, **env}, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout.decode("utf-8")

    expected = run(root, str(plan))
    assert f"file: {plan.resolve()}\n" in expected
    assert run(root, ".task/plan/plan-draft-s.md") == expected
    assert run(tmp_path / "linked", ".task/plan/plan-draft-s.md") == expected
    assert run(tmp_path / "linked", str(plan), LC_ALL="C", LANG="C") == expected


def test_i65_screen_takes_only_a_draft_in_the_plan_directory(main_root: Path, capsys) -> None:
    """Step 1's checks, on the resolved file: a draft-named link to plan-65.md, or a draft elsewhere, is refused."""
    plan65 = _write(main_root / ".task" / "plan" / "plan-65.md", SCREEN_PLAN)
    link = main_root / ".task" / "plan" / "plan-draft-link.md"
    link.symlink_to(plan65)
    stray = _write(main_root / "elsewhere" / "plan-draft-s.md", SCREEN_PLAN)
    for path in (link, stray):
        assert main(["forgejo", str(path), "--screen", "--default-base", "main"]) == ExitCode.REFUSED
        captured = capsys.readouterr()
        assert "reject (name)" in captured.err and "SCREEN=" not in captured.out


def test_i65_screen_bytes_do_not_depend_on_the_output_encoding(tmp_path: Path) -> None:
    """A Latin-1 locale neither crashes the screen nor changes a byte of it."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    plan = _write(root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    src = str(Path(plan_body.__file__).resolve().parents[1])
    outs = []
    for extra in ({}, {"LC_ALL": "en_US.ISO8859-1", "PYTHONIOENCODING": "latin-1"}):
        done = subprocess.run([sys.executable, "-m", "harness_core.plan_body", "forgejo", str(plan), "--screen",
                               "--default-base", "main"], cwd=root, capture_output=True,
                              env={"PATH": os.environ["PATH"], "PYTHONPATH": src, "HOME": str(tmp_path), **extra})
        assert done.returncode == 0, done.stderr
        outs.append(done.stdout)
    assert outs[0] == outs[1] and "화면 예시".encode("utf-8") in outs[1]


def test_i65_file_line_is_the_real_path(main_root: Path, capsys) -> None:
    """A draft reached through a symlinked directory shows, and hashes, the path Step 1 prints."""
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    alias = main_root / "alias"
    alias.symlink_to(main_root / ".task" / "plan", target_is_directory=True)
    real = _screen(capsys, ["forgejo", str(plan), "--screen", "--default-base", "main"])
    through = _screen(capsys, ["forgejo", str(alias / "plan-draft-s.md"), "--screen", "--default-base", "main"])
    assert through == real and real[0].startswith(f"file: {plan.resolve()}\n")


def test_i65_screen_refuses_a_read_that_is_not_utf8(tmp_path: Path, main_root: Path, capsys) -> None:
    plan = _write(main_root / ".task" / "plan" / "plan-draft-s.md", SCREEN_PLAN)
    read = tmp_path / "read"
    read.write_bytes(_fj_read("제목").encode("utf-16"))
    argv = ["forgejo", str(plan), "--issue", "65", "--screen", "--issue-read", str(read), "--default-base", "main"]
    assert main(argv) == ExitCode.REFUSED
    assert "stop (read)" in capsys.readouterr().err


def test_i65_screen_stops_when_the_main_checkout_cannot_be_resolved(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def unresolved() -> Path:
        raise MainWorktreeUnresolvedError("the first worktree entry /x has no work tree")
    monkeypatch.setattr(plan_body, "main_worktree_root", unresolved)
    assert main(["forgejo", "/abs/plan-draft-s.md", "--screen", "--default-base", "main"]) == ExitCode.REFUSED
    captured = capsys.readouterr()
    assert captured.err.startswith("stop (main checkout):") and "SCREEN=" not in captured.out
