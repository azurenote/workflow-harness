"""Contract test: the core CLI surface, checked against the *live* parser.

Two jobs:

1. Pin the exact set of core subcommands that :func:`build_core_parser` exposes.
2. Resolve every ``<harness_cli> <cmd>`` invocation written in the skill docs
   against that live parser. A doc that calls a core command the parser does not
   expose (or with a flag it does not accept) fails here. Only *core* commands
   are asserted — project-surface commands are classified and left to the
   project's own golden test, because the core is deliberately blind to them.

A hand-written command list matched against hand-written docs proves nothing
(author agrees with author). The teeth are in step 2: the parser is executed,
not described.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from harness_core.cli import (
    DuplicateCommandError,
    build_core_parser,
    dispatch,
    subparsers,
)
from harness_core.exitcodes import ExitCode

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
CORE = ROOT / "src" / "harness_core"

# The exact core surface. build_core_parser() must expose precisely this set —
# no more (a project command leaking into the core), no fewer (a regression like
# e40d5a1 dropping plan-file/push-branch/clean-up).
CORE_COMMANDS = {
    "find-draft-plan",
    "rename-plan",
    "plan-file",
    "get-base",
    "create-branch",
    "create-worktree",
    "push-branch",
    "clean-up",
}

# Matches `<harness_cli> <cmd> ...` and `.../harness_cli.py <cmd> ...` command
# lines in the docs; ignores prose mentions like "harness_cli get-base" that
# lack the placeholder or the .py suffix.
_CALL_RE = re.compile(r"(?:<harness_cli>|harness_cli\.py)\s+([a-z][a-z0-9-]*)(.*)")


def _collect_calls() -> list[tuple[str, str, list[str]]]:
    """Return (source, command, flags) for every harness_cli doc invocation."""
    calls: list[tuple[str, str, list[str]]] = []
    for md in sorted(SKILLS.rglob("*.md")):
        for line in md.read_text(encoding="utf-8").splitlines():
            match = _CALL_RE.search(line)
            if not match:
                continue
            command = match.group(1)
            rest = match.group(2).split("#", 1)[0]  # drop trailing shell comment
            flags = re.findall(r"--[a-z][a-z0-9-]+", rest)
            calls.append((str(md.relative_to(ROOT)), command, flags))
    return calls


def _choices(parser) -> dict:
    return subparsers(parser).choices


def test_core_parser_exposes_exactly_the_core_commands() -> None:
    assert set(_choices(build_core_parser())) == CORE_COMMANDS


def test_core_doc_calls_resolve_against_live_parser() -> None:
    choices = _choices(build_core_parser())
    unresolved: list[str] = []
    for source, command, flags in _collect_calls():
        if command not in CORE_COMMANDS:
            continue  # project surface — asserted by the project's golden test
        if command not in choices:
            unresolved.append(f"{source}: core command {command!r} not in live parser")
            continue
        accepted = set(choices[command]._option_string_actions)
        for flag in flags:
            if flag not in accepted:
                unresolved.append(f"{source}: {command} does not accept {flag}")
    assert not unresolved, "\n".join(unresolved)


def test_every_documented_core_command_is_referenced() -> None:
    # Guards the classifier: if a core command stops appearing in any doc, either
    # the docs regressed or the command should not be core. Keeps the two lists
    # from silently drifting apart.
    referenced = {command for _, command, _ in _collect_calls() if command in CORE_COMMANDS}
    missing = CORE_COMMANDS - referenced
    assert not missing, f"core commands never referenced in skills docs: {sorted(missing)}"


def test_core_cli_module_has_no_tracker_strings() -> None:
    # The core is tracker-agnostic: build_core_parser() must never grow a gh /
    # github / jira / forgejo dependency. Scoped to cli.py (scaffold.py carries
    # forgejo render defaults by design).
    source = (CORE / "cli.py").read_text(encoding="utf-8")
    hits = re.findall(r"\b(gh|github|jira|forgejo)\b", source, re.IGNORECASE)
    assert not hits, f"tracker tokens leaked into core cli.py: {hits}"


def test_core_cli_does_not_import_trackers() -> None:
    """The core parser stays tracker-agnostic even as adapters land beside it.

    `harness_core.trackers.github` is opt-in: a project registers it from its own
    `project.py`. The moment cli.py reaches for it, every project on every other
    tracker pays for this one, and CORE_COMMANDS above stops describing what
    build_core_parser() exposes.
    """
    source = (CORE / "cli.py").read_text(encoding="utf-8")
    assert "trackers" not in source, "cli.py reached into the tracker adapters"


def test_no_core_module_imports_the_tracker_adapters() -> None:
    """The plan names three modules, not one.

    Only cli.py was asserted, so `git.py` or `local.py` could grow an import of
    `trackers` and the stated dependency direction would fail silently. The
    adapters sit downstream of these three; nothing upstream may reach down.
    """
    for module in ("cli.py", "git.py", "local.py", "config.py", "io.py", "state.py"):
        source = (CORE / module).read_text(encoding="utf-8")
        assert "trackers" not in source, f"core module {module} imports the tracker adapters"


def test_the_adapter_does_not_import_the_core_parser() -> None:
    """The reverse edge. An adapter that imports cli.py closes the loop.

    Registration takes a subparsers action as an argument precisely so the
    adapter never needs to know how the parser was built.
    """
    source = (CORE / "trackers" / "github.py").read_text(encoding="utf-8")
    for forbidden in ("from ..cli", "from .cli", "import cli"):
        assert forbidden not in source, f"the adapter reached back into the core parser: {forbidden}"


def test_importing_an_adapter_does_not_register_its_commands() -> None:
    """Opt-in has to mean opt-in *at registration*, not merely at import.

    Comparing two literals declared in this file would prove nothing, and
    re-asserting the core set duplicates the test above. What is worth pinning
    is the thing that could actually regress: importing the adapter must not
    register anything, and registering it must add exactly its four commands to
    a parser that did not have them.
    """
    from harness_core.trackers import github  # noqa: F401 — the import is the test

    parser = build_core_parser()
    assert set(_choices(parser)) == CORE_COMMANDS

    github.register_github_commands(
        subparsers(parser), owner="<owner>", repo="<repo>", field_names={}
    )
    added = set(_choices(parser)) - CORE_COMMANDS
    assert added == {"create-issue", "get-issue", "set-fields", "audit-fields"}


def test_core_cli_module_imports_no_project_package() -> None:
    # Dependency direction is project -> core, never the reverse. cli.py may
    # import stdlib and sibling harness_core modules (relative imports) only.
    source = (CORE / "cli.py").read_text(encoding="utf-8")
    for forbidden in ("import project", "from project", "from harness.", "import harness\n"):
        assert forbidden not in source, f"core cli.py must not contain {forbidden!r}"


def test_duplicate_command_name_raises() -> None:
    # A project command shadowing a core one must fail loudly. argparse silently
    # overwrites on Python <= 3.10, so the guard — not argparse — is the safety.
    parser = build_core_parser()
    sub = subparsers(parser)
    with pytest.raises(DuplicateCommandError):
        sub.add_parser("get-base")  # already a core command


def test_every_core_command_has_a_handler_and_help() -> None:
    # dispatch relies on set_defaults(func=...); a command with no handler would
    # crash at call time, not parse time. Also proves each core subparser builds
    # a usable --help (argparse SystemExit(0)).
    parser = build_core_parser()
    choices = _choices(parser)
    for command, subparser in choices.items():
        assert subparser.get_default("func") is not None, f"{command} has no handler"
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([command, "--help"])
        assert exc.value.code == 0


def test_dispatch_returns_zero_for_none_returning_handler() -> None:
    # Project handlers print and fall off the end (return None); dispatch must
    # normalize that to exit code 0 so both core (int) and project (None) work.
    parser = build_core_parser()
    subparsers(parser).add_parser("noop").set_defaults(func=lambda _a: None)
    assert dispatch(parser, ["noop"]) == 0


def test_rename_plan_reroots_relative_path_under_main_worktree(tmp_path, monkeypatch, capsys):
    # rename-plan given a relative path from a linked-worktree CWD must target the
    # MAIN worktree's plan file (plan-234), not CWD. Regression guard for the
    # dropped _abs_under_main re-rooting.
    from harness_core import cli

    main_root = tmp_path / "main"
    (main_root / ".task" / "plan").mkdir(parents=True)
    draft = main_root / ".task" / "plan" / "plan-draft-x.md"
    draft.write_text("# Plan: x")

    monkeypatch.setattr(cli, "main_worktree_root", lambda: main_root)
    monkeypatch.chdir(tmp_path)  # CWD is NOT the main worktree root

    dispatch(build_core_parser(), ["rename-plan", ".task/plan/plan-draft-x.md", "42"])
    capsys.readouterr()

    assert (main_root / ".task" / "plan" / "plan-42.md").exists()
    assert not draft.exists()


@pytest.fixture
def main_root(tmp_path, monkeypatch):
    """A fake main worktree with an empty plan dir; CWD is outside it."""
    from harness_core import cli

    root = tmp_path / "main"
    (root / ".task" / "plan").mkdir(parents=True)
    monkeypatch.setattr(cli, "main_worktree_root", lambda: root)
    monkeypatch.chdir(tmp_path)
    return root


def test_rename_plan_empty_path_leaves_main_worktree_alone(main_root, tmp_path, capsys):
    # #32: "" re-rooted to the main worktree root, which was then renamed to
    # ../plan-25.md with rc 0. Now a refusal: one line, REFUSED, nothing moved.
    assert dispatch(build_core_parser(), ["rename-plan", "", "25"]) == ExitCode.REFUSED
    assert main_root.is_dir()
    assert not (tmp_path / "plan-25.md").exists()
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("Error: reject (exists)") and err.count("\n") == 1


def test_rename_plan_accepts_ticket_key(main_root, capsys):
    draft = main_root / ".task" / "plan" / "plan-draft-x.md"
    draft.write_text("# Plan: x")

    assert dispatch(build_core_parser(), ["rename-plan", str(draft), "SYN-42"]) == 0
    target = main_root / ".task" / "plan" / "plan-SYN-42.md"
    assert capsys.readouterr().out.strip() == str(target)
    assert target.exists() and not draft.exists()


@pytest.mark.parametrize("command", [["rename-plan", ".task/plan/plan-draft-x.md"], ["plan-file"]])
@pytest.mark.parametrize("issue_id", ["../x", "", "SYN-0", "042"])
def test_bad_issue_id_is_a_usage_error(main_root, command, issue_id, capsys):
    draft = main_root / ".task" / "plan" / "plan-draft-x.md"
    draft.write_text("# Plan: x")

    with pytest.raises(SystemExit) as exc:
        dispatch(build_core_parser(), [*command, issue_id])
    assert exc.value.code == 2
    assert "not an issue number or ticket key" in capsys.readouterr().err
    assert sorted(p.name for p in draft.parent.iterdir()) == ["plan-draft-x.md"]


def test_plan_file_accepts_ticket_key(main_root, capsys):
    plan = main_root / ".task" / "plan" / "plan-SYN-42.md"
    plan.write_text("# Plan: x")

    assert dispatch(build_core_parser(), ["plan-file", "SYN-42"]) == 0
    assert capsys.readouterr().out.strip() == str(plan)


def test_plan_file_missing_is_refused_in_one_line(main_root, capsys):
    # A missing plan used to crash (traceback, rc 1). It is a precondition the
    # caller can fix, so it is REFUSED like a bad id — the stderr line tells the two apart.
    assert dispatch(build_core_parser(), ["plan-file", "999"]) == ExitCode.REFUSED
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("Error: Plan file not found:") and err.count("\n") == 1


class TestCleanUpBaseInjection:
    """`clean-up` must measure staleness against the *project's* base branch.

    The core cannot read a project's skill-config.yaml, so the base set is
    injected at composition time. Losing that injection is silent for a project
    whose base is already `develop`, and destructive for one whose base is not:
    an unprotected base branch is a branch clean-up may delete.
    """

    def test_injected_bases_reach_the_handler(self, monkeypatch, capsys) -> None:
        from harness_core import cli

        seen: dict = {}
        monkeypatch.setattr(
            cli, "clean_up_stale_branches",
            lambda bases=None, plan_dir=None: seen.setdefault("bases", bases) or {},
        )
        parser = build_core_parser(clean_up_bases=["develop", "main", "master"])
        dispatch(parser, ["clean-up"])
        capsys.readouterr()

        assert seen["bases"] == ["develop", "main", "master"]

    def test_default_is_none_so_the_core_default_applies(self, monkeypatch, capsys) -> None:
        from harness_core import cli

        seen: dict = {}
        monkeypatch.setattr(
            cli, "clean_up_stale_branches",
            lambda bases=None, plan_dir=None: seen.setdefault("bases", bases) or {},
        )
        dispatch(build_core_parser(), ["clean-up"])
        capsys.readouterr()

        assert seen["bases"] is None

    def test_two_parsers_do_not_share_injected_bases(self, monkeypatch, capsys) -> None:
        # Module-level state would let one parser read another's value; the bases
        # ride on the subparser instead. Tests build several parsers per process.
        from harness_core import cli

        seen: list = []
        monkeypatch.setattr(
            cli, "clean_up_stale_branches",
            lambda bases=None, plan_dir=None: seen.append(bases) or {},
        )
        first = build_core_parser(clean_up_bases=["develop"])
        second = build_core_parser(clean_up_bases=["master"])
        dispatch(first, ["clean-up"])
        dispatch(second, ["clean-up"])
        capsys.readouterr()

        assert seen == [["develop"], ["master"]]


class TestCoreRefusals:
    """Known preconditions refuse with one stderr line; everything else still crashes.

    The refusals are named per command. Catching wider — ``FileNotFoundError``,
    ``OSError``, ``Exception`` — would turn a missing ``git`` or a plain bug into
    a polite ``REFUSED``, and the ``still crashes`` rows below would go quiet.
    """

    @staticmethod
    def _one_line(capsys) -> str:
        out, err = capsys.readouterr()
        assert out == "", out
        assert err.startswith("Error: ") and err.count("\n") == 1, err
        return err

    def test_no_draft(self, main_root, capsys) -> None:
        assert dispatch(build_core_parser(), ["find-draft-plan"]) == ExitCode.REFUSED
        self._one_line(capsys)

    def test_several_drafts_fold_into_one_line(self, main_root, capsys) -> None:
        for name in ("plan-draft-a.md", "plan-draft-b.md"):
            (main_root / ".task" / "plan" / name).write_text("# Plan: x")
        assert dispatch(build_core_parser(), ["find-draft-plan"]) == ExitCode.REFUSED
        err = self._one_line(capsys)
        assert "plan-draft-a.md" in err and "plan-draft-b.md" in err

    def test_rename_onto_an_existing_plan(self, main_root, capsys) -> None:
        plans = main_root / ".task" / "plan"
        (plans / "plan-draft-x.md").write_text("# Plan: x")
        (plans / "plan-7.md").write_text("# Plan: y")
        assert dispatch(build_core_parser(), ["rename-plan", str(plans / "plan-draft-x.md"), "7"]) == ExitCode.REFUSED
        self._one_line(capsys)
        assert (plans / "plan-draft-x.md").read_text() == "# Plan: x"
        assert (plans / "plan-7.md").read_text() == "# Plan: y"

    @pytest.mark.parametrize("argv", [["plan-file", "7"], ["get-base", "7"], ["find-draft-plan"],
                                      ["rename-plan", "x", "7"], ["clean-up"], ["create-worktree", "wt", "b"]])
    def test_unresolved_main_checkout(self, monkeypatch, capsys, argv) -> None:
        from harness_core import cli, git
        from harness_core.git import MainWorktreeUnresolvedError

        def unresolved():
            raise MainWorktreeUnresolvedError("no main work tree (bare)")

        monkeypatch.setattr(cli, "main_worktree_root", unresolved)
        monkeypatch.setattr(git, "main_worktree_root", unresolved)
        monkeypatch.setattr(cli, "clean_up_stale_branches",
                            lambda bases=None, plan_dir=None: {"plan_dir": str(plan_dir)})
        assert dispatch(build_core_parser(), argv) == ExitCode.REFUSED
        assert "no main work tree" in self._one_line(capsys)

    @pytest.mark.parametrize("error", [FileNotFoundError("no git"), OSError("disk"), RuntimeError("bug")])
    def test_anything_else_still_crashes(self, main_root, monkeypatch, capsys, error) -> None:
        from harness_core import cli

        def boom(*_a, **_k):
            raise error

        monkeypatch.setattr(cli, "plan_file_for_issue", boom)
        with pytest.raises(type(error)):
            dispatch(build_core_parser(), ["plan-file", "7"])

    def test_git_failure_still_crashes(self, monkeypatch) -> None:
        from harness_core import cli
        from harness_core.git import GitError

        def fail(*_a, **_k):
            raise GitError("git checkout -b x", "already exists")

        monkeypatch.setattr(cli, "create_branch", fail)
        with pytest.raises(GitError):
            dispatch(build_core_parser(), ["create-branch", "x"])

    def test_a_project_handler_is_not_wrapped(self) -> None:
        from harness_core.local import PlanFileNotFoundError

        parser = build_core_parser()

        def project_command(_args):
            raise PlanFileNotFoundError("the project's own")

        subparsers(parser).add_parser("mine").set_defaults(func=project_command)
        with pytest.raises(PlanFileNotFoundError):
            dispatch(parser, ["mine"])

    @pytest.mark.parametrize("nothing", [None, "", [], {}, 0])
    def test_a_handler_that_returns_nothing_is_ok(self, nothing) -> None:
        # Falsy, not just None: `sys.exit("")` would print and exit 1.
        parser = build_core_parser()
        subparsers(parser).add_parser("quiet").set_defaults(func=lambda _args: nothing)
        assert dispatch(parser, ["quiet"]) == ExitCode.OK
