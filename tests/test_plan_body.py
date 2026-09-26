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
