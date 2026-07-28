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
