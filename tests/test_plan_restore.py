"""#70: `plan-<id>.md` restored from the user's own last plan comment.

Reads are built the way each tracker prints them. `_i70_fj` is the live `fj`
shape (measured on #37·#45·#53·#54·#67·#70, 2026-09-26): the trailing newline
of a comment is gone, which is why the one-newline candidate exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness_core import plan_restore
from harness_core.exitcodes import ExitCode
from harness_core.plan_body import SUMMARY_LEAD, build, marker, revision

_I = "\u2068"
_J = "\u2069"
ME = "my"

PLAN = """# Plan: 복원 대상

## Intent Summary
의도.

## Definition of Done
- [ ] 조건
"""

OTHER = PLAN.replace("의도.", "다른 의도.")


def _i70_comment(plan: str, issue_id: str = "70", rev: str | None = None) -> str:
    """The comment `project-issue` posts for `plan`, as `plan_body.build` makes it."""
    rev = rev or revision(plan.encode("utf-8"))
    return build(plan, "forgejo", rev, issue_id).text


def _i70_quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.split("\n"))


def _i70_fj(body: str, *comments: tuple[str, str], labels: tuple[str, ...] = ()) -> str:
    """`fj … issue view` + `… comments` for (login, text) comments, live shape.

    Labels print as plain lines between the `By` line and the body
    (forgejo-cli `render_label_list`)."""
    out = (f'{_I}{_J}{_I}제목{_J} {_I}{_J}#{_I}70{_J}{_I}{_J}"\n'
           f"By {_I}{_J}{_I}{ME}{_J}{_I}{_J} — {_I}{_I}{_J}Open{_I}{_J}{_J}\n"
           + "".join(f"{label}\n" for label in labels)
           + f"\n{_i70_quote(body.rstrip(chr(10)))}\n\n\n{_I}{len(comments)}{_J} comments\n")
    for login, text in comments:
        out += (f"{_I}{_J}{_I}Name{_J}{_I}{_J} {_I}{_J}({_I}{login}{_J}){_I}{_J} said:\n"
                f"{_i70_quote(text.rstrip(chr(10)))}\n\n\n")
    return out


def _i70_gh(body: str, *comments: tuple[str, str]) -> str:
    return json.dumps({"body": body, "comments": [{"author": {"login": a}, "body": t} for a, t in comments]})


READS = {"forgejo": _i70_fj, "github": _i70_gh}
WHOAMI = {"forgejo": f"currently signed into {_I}{ME}{_J}@{_I}{_J}forge.test\n", "github": f"{ME}\n"}


@pytest.fixture
def main_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "main"
    (root / ".task" / "plan").mkdir(parents=True)
    monkeypatch.setattr(plan_restore, "main_worktree_root", lambda: root)
    linked = tmp_path / "linked"
    linked.mkdir()
    monkeypatch.chdir(linked)
    return root


def _i70_run(tmp_path: Path, tracker: str, read: str, *, issue: str = "70",
             whoami: str | None = None) -> tuple[int, Path]:
    io = tmp_path / "io"
    io.mkdir(exist_ok=True)
    (io / "read").write_bytes(read.encode("utf-8"))
    (io / "whoami").write_text(WHOAMI[tracker] if whoami is None else whoami, encoding="utf-8")
    rc = plan_restore.main([tracker, "--issue", issue, "--read", str(io / "read"), "--whoami", str(io / "whoami")])
    return rc, tmp_path / "main" / ".task" / "plan" / f"plan-{issue}.md"


def _i70_listing(root: Path) -> list[str]:
    return sorted(p.name for p in (root / ".task" / "plan").iterdir())


# ── Which comment ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tracker", sorted(READS))
def test_the_last_own_marker_comment_is_restored(tracker, main_root, tmp_path, capsys) -> None:
    read = READS[tracker]("이슈 본문", (ME, _i70_comment(OTHER)), (ME, _i70_comment(PLAN)))
    rc, target = _i70_run(tmp_path, tracker, read)
    out = capsys.readouterr().out.strip()
    rev = revision(PLAN.encode("utf-8"))
    assert rc == ExitCode.OK
    assert out == f"RESTORE=restored REV={rev} MARKERS=2 FOREIGN=0 PATH={target}"
    assert target.read_bytes() == PLAN.encode("utf-8")
    assert hashlib.sha1(target.read_bytes()).hexdigest()[:8] == rev


@pytest.mark.parametrize("tracker", sorted(READS))
@pytest.mark.parametrize("case", ["other id", "quoted", "mid-line", "second line", "in the body", "create-mode body"])
def test_only_a_first_line_marker_of_this_id_in_a_comment_counts(tracker, case, main_root, tmp_path, capsys) -> None:
    full = _i70_comment(PLAN)
    head = marker("70", revision(PLAN.encode("utf-8")))
    body, comments = "이슈 본문", []
    if case == "other id":
        comments = [(ME, _i70_comment(PLAN, issue_id="7"))]
    elif case == "quoted":
        comments = [(ME, "> " + full)]
    elif case == "mid-line":
        comments = [(ME, "앞 " + full)]
    elif case == "second line":
        comments = [(ME, "첫 줄\n" + full)]
    elif case == "in the body":
        body = full
    else:
        body = PLAN
    rc, target = _i70_run(tmp_path, tracker, READS[tracker](body, *comments))
    assert (rc, capsys.readouterr().out.strip()) == (ExitCode.OK, "RESTORE=none MARKERS=0 FOREIGN=0")
    assert not target.exists() and head  # nothing written


@pytest.mark.parametrize("tracker", sorted(READS))
def test_someone_elses_last_marker_is_refused_not_skipped(tracker, main_root, tmp_path, capsys) -> None:
    read = READS[tracker]("본문", (ME, _i70_comment(PLAN)), ("mallory", _i70_comment(OTHER)))
    rc, target = _i70_run(tmp_path, tracker, read)
    out = capsys.readouterr().out.strip()
    assert rc == ExitCode.FINDINGS
    assert out.startswith("RESTORE=refused (author) ") and out.endswith("MARKERS=2 FOREIGN=1")
    assert not target.exists()


@pytest.mark.parametrize("tracker", sorted(READS))
def test_only_foreign_markers_are_counted_and_refused(tracker, main_root, tmp_path, capsys) -> None:
    read = READS[tracker]("본문", ("a", _i70_comment(OTHER)), ("b", _i70_comment(PLAN)))
    rc, target = _i70_run(tmp_path, tracker, read)
    assert rc == ExitCode.FINDINGS
    assert capsys.readouterr().out.strip().endswith("(author) REV=" + revision(PLAN.encode()) + " MARKERS=2 FOREIGN=2")
    assert not target.exists()


def test_an_unreadable_forgejo_author_line_is_not_the_user(main_root, tmp_path, capsys) -> None:
    read = _i70_fj("본문", (ME, _i70_comment(PLAN))).replace(" said:", " wrote:")
    # A header fj no longer writes is a read that does not add up, not "no comments".
    assert _i70_run(tmp_path, "forgejo", read)[0] == ExitCode.REFUSED
    assert capsys.readouterr().out.strip() == "RESTORE=stopped (read)"
    odd = _i70_fj("본문", (ME, _i70_comment(PLAN))).replace(f"({_I}{ME}{_J})", "(two words)")
    assert _i70_run(tmp_path, "forgejo", odd)[0] == ExitCode.FINDINGS
    assert "(author)" in capsys.readouterr().out


# ── What is written ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("tracker", sorted(READS))
def test_a_summary_comment_is_refused_as_a_summary(tracker, main_root, tmp_path, monkeypatch, capsys) -> None:
    from harness_core import plan_body

    long_plan = PLAN + "\n## Current State\n" + "가" * 3000 + "\n"
    monkeypatch.setattr(plan_body, "LIMITS", {"github": 1000, "forgejo": 1000})
    summary = build(long_plan, "forgejo", revision(long_plan.encode()), "70")
    assert summary.kind == "summary"
    rc, target = _i70_run(tmp_path, tracker, READS[tracker]("본문", (ME, summary.text)))
    assert rc == ExitCode.FINDINGS
    assert capsys.readouterr().out.startswith("RESTORE=refused (summary) ")
    assert not target.exists()


@pytest.mark.parametrize("tracker", sorted(READS))
def test_a_changed_comment_is_refused_on_rev(tracker, main_root, tmp_path, capsys) -> None:
    changed = _i70_comment(PLAN).replace("의도.", "고친 의도.")
    rc, target = _i70_run(tmp_path, tracker, READS[tracker]("본문", (ME, changed)))
    assert rc == ExitCode.FINDINGS
    assert capsys.readouterr().out.startswith("RESTORE=refused (rev) ")
    assert not target.exists()


@pytest.mark.parametrize("tracker", sorted(READS))
def test_a_refused_last_comment_never_falls_back_to_an_earlier_one(tracker, main_root, tmp_path, capsys) -> None:
    broken = _i70_comment(OTHER).replace("다른 의도.", "손댄 의도.")
    rc, target = _i70_run(tmp_path, tracker, READS[tracker]("본문", (ME, _i70_comment(PLAN)), (ME, broken)))
    assert rc == ExitCode.FINDINGS
    assert capsys.readouterr().out.startswith("RESTORE=refused (rev) ")
    assert not target.exists()


@pytest.mark.parametrize("tracker", sorted(READS))
def test_a_full_plan_quoting_the_summary_line_is_restored(tracker, main_root, tmp_path) -> None:
    plan = PLAN + f"\n{SUMMARY_LEAD} 로 시작하는 줄을 인용한다.\n"
    rc, target = _i70_run(tmp_path, tracker, READS[tracker]("본문", (ME, _i70_comment(plan))))
    assert rc == ExitCode.OK and target.read_bytes() == plan.encode("utf-8")


def test_github_keeps_the_trailing_newline_and_forgejo_drops_it(main_root, tmp_path) -> None:
    """Both candidates are needed: GitHub restores as read, Forgejo with one newline."""
    comment = _i70_comment(PLAN)
    assert plan_restore.comments(_i70_gh("", (ME, comment)), "github")[0].text.endswith("\n")
    assert not plan_restore.comments(_i70_fj("", (ME, comment)), "forgejo")[0].text.endswith("\n")
    for tracker in ("github", "forgejo"):
        rc, target = _i70_run(tmp_path, tracker, READS[tracker]("", (ME, comment)))
        assert rc == ExitCode.OK and target.read_bytes() == PLAN.encode("utf-8")
        target.unlink()


def test_a_plan_without_a_final_newline_restores_as_read(main_root, tmp_path) -> None:
    plan = PLAN.rstrip("\n")
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(plan))))
    assert rc == ExitCode.OK and target.read_bytes() == plan.encode("utf-8")


def test_trailing_blank_lines_do_not_survive_forgejo_and_are_refused(main_root, tmp_path, capsys) -> None:
    plan = PLAN + "\n\n"
    rc, target = _i70_run(tmp_path, "forgejo", _i70_fj("", (ME, _i70_comment(plan))))
    assert rc == ExitCode.FINDINGS
    assert capsys.readouterr().out.startswith("RESTORE=refused (rev) ")
    assert not target.exists()


def test_isolates_inside_the_plan_survive_a_forgejo_read(main_root, tmp_path) -> None:
    plan = PLAN + f"\n`fj` 출력의 {_I}격리{_J} 문자.\n"
    rc, target = _i70_run(tmp_path, "forgejo", _i70_fj("", (ME, _i70_comment(plan))))
    assert rc == ExitCode.OK and target.read_bytes() == plan.encode("utf-8")


def test_crlf_is_not_normalized(main_root, tmp_path, capsys) -> None:
    comment = _i70_comment(PLAN).replace("\n", "\r\n")
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, comment)))
    assert rc == ExitCode.FINDINGS and not target.exists()
    assert "(rev)" in capsys.readouterr().out


# ── Where and how it is written ───────────────────────────────────────────────


def test_it_writes_to_the_main_checkout_not_the_cwd(main_root, tmp_path) -> None:
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    assert rc == ExitCode.OK and target.parent == main_root / ".task" / "plan"
    assert list((tmp_path / "linked").iterdir()) == [], "something was written under the CWD"
    assert _i70_listing(main_root) == ["plan-70.md"]


def test_it_creates_the_plan_directory(main_root, tmp_path) -> None:
    (main_root / ".task" / "plan").rmdir()
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    assert rc == ExitCode.OK and target.is_file()


def test_the_file_takes_the_umask_not_mkstemp_0600(main_root, tmp_path) -> None:
    import os

    old = os.umask(0o022)
    try:
        _, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    finally:
        os.umask(old)
    assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("kind", ["file", "dangling symlink"])
def test_an_existing_target_is_never_replaced(kind, main_root, tmp_path, capsys) -> None:
    target = main_root / ".task" / "plan" / "plan-70.md"
    if kind == "file":
        target.write_bytes(b"local")
    else:
        target.symlink_to(tmp_path / "nowhere")
    before = _i70_listing(main_root)
    rc, _ = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    captured = capsys.readouterr()
    assert rc == ExitCode.REFUSED
    assert captured.err.startswith("stop (exists): ") and captured.out.strip() == "RESTORE=stopped (exists)"
    assert _i70_listing(main_root) == before, "a temporary file was left behind"
    if kind == "file":
        assert target.read_bytes() == b"local"
    else:
        assert target.is_symlink() and not (tmp_path / "nowhere").exists()


def test_a_plan_directory_that_is_a_file_is_refused(main_root, tmp_path, capsys) -> None:
    plan_dir = main_root / ".task" / "plan"
    plan_dir.rmdir()
    plan_dir.write_bytes(b"")
    rc, _ = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    assert rc == ExitCode.REFUSED and capsys.readouterr().err.startswith("stop (plan dir): ")


def test_a_failed_link_leaves_nothing(main_root, tmp_path, monkeypatch, capsys) -> None:
    def fail(src, dst):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(plan_restore.os, "link", fail)
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    assert rc == ExitCode.REFUSED and capsys.readouterr().err.startswith("stop (write): ")
    assert _i70_listing(main_root) == [] and not target.exists()


def test_no_refusal_or_finding_leaves_a_file(main_root, tmp_path, capsys) -> None:
    cases = [
        ("github", _i70_gh("", ("x", _i70_comment(PLAN)))),
        ("github", _i70_gh("", (ME, _i70_comment(PLAN).replace("의도.", "?")))),
        ("github", "not json"),
    ]
    for tracker, read in cases:
        rc, _ = _i70_run(tmp_path, tracker, read)
        assert rc in (ExitCode.FINDINGS, ExitCode.REFUSED)
        assert _i70_listing(main_root) == []


# ── Reads it cannot use ───────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ["missing read", "not utf-8", "github not json", "github no comments key",
                                  "whoami empty", "fj whoami other text"])
def test_a_read_it_cannot_use_stops(case, main_root, tmp_path, capsys) -> None:
    tracker = "forgejo" if case.startswith("fj") else "github"
    read: bytes | None = _i70_gh("", (ME, _i70_comment(PLAN))).encode("utf-8")
    whoami = WHOAMI[tracker]
    if case == "missing read":
        read = None
    elif case == "not utf-8":
        read = b"\xff\xfe" + read
    elif case == "github not json":
        read = b"Error: not found"
    elif case == "github no comments key":
        read = json.dumps({"body": ""}).encode()
    elif case == "whoami empty":
        whoami = ""
    else:
        read, whoami = _i70_fj("", (ME, _i70_comment(PLAN))).encode("utf-8"), "not signed in\n"
    io = tmp_path / "io"
    io.mkdir()
    if read is not None:
        (io / "read").write_bytes(read)
    (io / "whoami").write_text(whoami, encoding="utf-8")
    rc = plan_restore.main([tracker, "--issue", "70", "--read", str(io / "read"), "--whoami", str(io / "whoami")])
    captured = capsys.readouterr()
    assert rc == ExitCode.REFUSED, case
    assert captured.err.startswith("stop (") and captured.out.strip().startswith("RESTORE=stopped (")
    assert _i70_listing(main_root) == []


def test_the_signed_in_user_is_read_from_both_clis() -> None:
    assert plan_restore.login(WHOAMI["forgejo"], "forgejo") == ME
    assert plan_restore.login("octocat\n", "github") == "octocat"
    for bad, tracker in (("two words\n", "github"), ("a\nb\n", "github"), ("signed in\n", "forgejo")):
        with pytest.raises(plan_restore.RestoreStop):
            plan_restore.login(bad, tracker)


def test_a_bad_issue_id_stops(main_root, tmp_path, capsys) -> None:
    rc, _ = _i70_run(tmp_path, "github", _i70_gh(""), issue="../x")
    assert rc == ExitCode.REFUSED and capsys.readouterr().err.startswith("stop (id): ")


@pytest.mark.parametrize("argv", [
    ["github", "--read", "r", "--whoami", "w"],
    ["github", "--issue", "70", "--whoami", "w"],
    ["github", "--issue", "70", "--read", "r"],
    ["jira", "--issue", "70", "--read", "r", "--whoami", "w"],
    ["github", "plan-70.md", "--issue", "70", "--read", "r", "--whoami", "w"],
])
def test_usage_errors_exit_refused(argv) -> None:
    with pytest.raises(SystemExit) as exc:
        plan_restore.main(argv)
    assert exc.value.code == ExitCode.REFUSED


# ── Forgejo reads that do not add up ─────────────────────────────────────────


def test_a_label_shaped_like_an_author_line_does_not_make_the_body_a_comment(main_root, tmp_path, capsys) -> None:
    """The body comes before the count line, whatever a label above it says."""
    read = _i70_fj(_i70_comment(PLAN), labels=(f"x ({ME}) said:", "3 comments"))
    rc, target = _i70_run(tmp_path, "forgejo", read)
    assert (rc, capsys.readouterr().out.strip()) == (ExitCode.OK, "RESTORE=none MARKERS=0 FOREIGN=0")
    assert not target.exists()


@pytest.mark.parametrize("case", ["no count line", "a comment more than counted", "a comment fewer"])
def test_a_forgejo_read_that_does_not_add_up_stops(case, main_root, tmp_path, capsys) -> None:
    read = _i70_fj("본문", (ME, _i70_comment(PLAN)))
    if case == "no count line":
        read = read.replace(f"{_I}1{_J} comments", "")
    elif case == "a comment more than counted":
        read += f"{_I}Name{_J} ({ME}) said:\n> 늦게 달린 코멘트\n\n"
    else:
        read = read.replace(f"{_I}1{_J} comments", f"{_I}2{_J} comments")
    rc, target = _i70_run(tmp_path, "forgejo", read)
    assert rc == ExitCode.REFUSED and capsys.readouterr().out.strip() == "RESTORE=stopped (read)"
    assert not target.exists()


def test_a_github_comment_body_that_is_not_text_stops(main_root, tmp_path, capsys) -> None:
    read = json.dumps({"body": "", "comments": [{"author": {"login": ME}, "body": 5}]})
    rc, _ = _i70_run(tmp_path, "github", read)
    assert rc == ExitCode.REFUSED and capsys.readouterr().out.strip() == "RESTORE=stopped (read)"


def test_a_failed_restore_takes_back_the_directories_it_made(main_root, tmp_path, monkeypatch) -> None:
    import shutil

    shutil.rmtree(main_root / ".task")
    monkeypatch.setattr(plan_restore.os, "link", lambda src, dst: (_ for _ in ()).throw(PermissionError(1, "no")))
    rc, _ = _i70_run(tmp_path, "github", _i70_gh("", (ME, _i70_comment(PLAN))))
    assert rc == ExitCode.REFUSED and not (main_root / ".task").exists()


def test_the_mirrors_match_plan_body() -> None:
    from harness_core import plan_body

    assert plan_restore._MARKER.fullmatch(plan_body.marker("70", "0123abcd")).groups() == ("70", "0123abcd")
    assert plan_restore._ISOLATES == plan_body._ISOLATES


# ── The comment's shape ──────────────────────────────────────────────────────


@pytest.mark.parametrize("lead", ["\n", "\ufeff", "\r\n"])
def test_a_first_line_is_read_as_seen_reads_it(lead, main_root, tmp_path, capsys) -> None:
    """A leading blank line or BOM does not hide the marker — `plan_body.seen`
    reads the same first line — so a mangled last comment is refused, never
    passed over for an older one."""
    read = _i70_gh("", (ME, _i70_comment(OTHER)), (ME, lead + _i70_comment(PLAN)))
    rc, target = _i70_run(tmp_path, "github", read)
    out = capsys.readouterr().out.strip()
    assert rc == ExitCode.FINDINGS and out.startswith("RESTORE=refused (rev) ") and "MARKERS=2" in out
    assert not target.exists()


def test_the_blank_line_after_the_marker_is_part_of_the_format(main_root, tmp_path, capsys) -> None:
    tight = _i70_comment(PLAN).replace(" -->\n\n", " -->\n", 1)
    rc, target = _i70_run(tmp_path, "github", _i70_gh("", (ME, tight)))
    assert rc == ExitCode.FINDINGS and "(rev)" in capsys.readouterr().out and not target.exists()


def test_a_bare_quote_line_is_a_blank_line_of_the_comment(main_root, tmp_path) -> None:
    read = _i70_fj("", (ME, _i70_comment(PLAN))).replace("\n> \n", "\n>\n")
    assert "\n>\n" in read
    rc, target = _i70_run(tmp_path, "forgejo", read)
    assert rc == ExitCode.OK and target.read_bytes() == PLAN.encode("utf-8")


def test_a_user_without_a_display_name_is_still_the_author(main_root, tmp_path) -> None:
    read = _i70_fj("", (ME, _i70_comment(PLAN))).replace(f"{_I}Name{_J}{_I}{_J} {_I}{_J}({_I}{ME}{_J}){_I}{_J} said:",
                                                         f"{_I}{ME}{_J} said:")
    assert f"{_I}{ME}{_J} said:" in read
    rc, target = _i70_run(tmp_path, "forgejo", read)
    assert rc == ExitCode.OK and target.is_file()
