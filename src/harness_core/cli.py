"""Core command-line surface for the workflow harness.

This module supplies the *project-independent* subcommands (plan-file / git /
worktree operations) as a reusable argparse tree. Projects own the entry-point
script (`.claude/scripts/harness_cli.py`); that script calls
:func:`build_core_parser` for these commands, then registers its own tracker
commands onto the same subparsers action.

The dependency direction is one-way: this module never imports a project
module. Core commands reach every project through the library; project commands
stay invisible to the core. See workflow-harness plan #477 (single-entrypoint
inversion).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .git import (
    clean_up_stale_branches,
    create_branch,
    create_worktree,
    main_worktree_root,
    push_branch,
)
from .io import print_json
from .local import (
    find_draft_plan_file,
    parse_frontmatter,
    plan_file_for_issue,
    rename_plan_to_issue,
)


def _plan_dir() -> Path:
    """Absolute path of ``.task/plan/`` rooted at the main worktree.

    ``.task/plan/`` is gitignored, so plan files exist only in the main worktree
    checkout. Resolving against :func:`main_worktree_root` keeps get-base /
    plan-file / find-draft-plan correct even when the CLI is invoked from a
    linked worktree CWD. Wrapped in a function (not a module constant) so import
    stays side-effect free and tests can monkeypatch it without a real repo.
    """
    return main_worktree_root() / ".task" / "plan"


def _abs_under_main(path: Path) -> Path:
    """Re-root a relative path at the main worktree; absolute paths pass through.

    A positional path argument (rename-plan's ``plan_path``) is typed from a
    linked-worktree CWD, but the plan file it names lives only in the main
    worktree's gitignored ``.task/plan/``. A relative path must resolve there,
    not against CWD (plan-234).
    """
    return path if path.is_absolute() else (main_worktree_root() / path).resolve()


class DuplicateCommandError(Exception):
    """A subcommand name was registered twice.

    argparse's ``add_parser`` silently overwrites a duplicate name on Python
    <= 3.10 (its ``conflict_handler`` never fires for subparsers), so a project
    command shadowing a core one would pass unnoticed. The guarded subparsers
    below raise this instead — the check is version-independent.
    """


class _GuardedSubparsers:
    """Wraps an ``add_subparsers`` action, refusing to silently overwrite a name.

    Exposes only what registration needs (``add_parser`` and ``choices``).
    ``add_parser`` raises :class:`DuplicateCommandError` when the name already
    exists.
    """

    def __init__(self, action: argparse._SubParsersAction) -> None:
        self._action = action

    def add_parser(self, name: str, **kwargs) -> argparse.ArgumentParser:
        if name in self._action.choices:
            raise DuplicateCommandError(f"duplicate subcommand: {name!r}")
        return self._action.add_parser(name, **kwargs)

    @property
    def choices(self) -> dict:
        return self._action.choices


# ── Core command handlers ────────────────────────────────────────────────────


def _find_draft_plan(_args: argparse.Namespace) -> int:
    print(find_draft_plan_file(_plan_dir()))
    return 0


def _rename_plan(args: argparse.Namespace) -> int:
    print(rename_plan_to_issue(_abs_under_main(args.plan_path), args.issue_number))
    return 0


def _plan_file(args: argparse.Namespace) -> int:
    print(plan_file_for_issue(args.issue_number, _plan_dir()))
    return 0


def _get_base(args: argparse.Namespace) -> int:
    plan_path = _plan_dir() / f"plan-{args.issue_number}.md"
    if plan_path.exists():
        frontmatter = parse_frontmatter(plan_path.read_text())
        base = (frontmatter.get("base_branch") or "").strip() or None
        parent = (frontmatter.get("parent_issue") or "").strip() or None
    else:
        base = parent = None
    print_json(
        {
            "base_branch": base,
            "parent_issue": int(parent) if parent and parent.isdigit() else parent,
        }
    )
    return 0


def _create_branch(args: argparse.Namespace) -> int:
    print(create_branch(args.branch_name, base_ref=args.base_ref))
    return 0


def _create_worktree(args: argparse.Namespace) -> int:
    print(create_worktree(args.path, args.branch_name, base_ref=args.base_ref))
    return 0


def _push_branch(args: argparse.Namespace) -> int:
    push_branch(args.branch_name)
    print_json({"branch": args.branch_name})
    return 0


def _clean_up(_args: argparse.Namespace) -> int:
    print_json(clean_up_stale_branches(plan_dir=_plan_dir()))
    return 0


# ── Registration ─────────────────────────────────────────────────────────────


def register_core(sub: _GuardedSubparsers) -> None:
    """Register the core subcommands onto a (guarded) subparsers action."""
    find = sub.add_parser("find-draft-plan", help="Find the unique draft plan file")
    find.set_defaults(func=_find_draft_plan)

    rename = sub.add_parser("rename-plan", help="Rename a draft plan to plan-<issue>.md")
    rename.add_argument("plan_path", type=Path)
    rename.add_argument("issue_number", type=int)
    rename.set_defaults(func=_rename_plan)

    plan_file = sub.add_parser("plan-file", help="Print the path to plan-<issue>.md")
    plan_file.add_argument("issue_number", type=int)
    plan_file.set_defaults(func=_plan_file)

    get_base = sub.add_parser(
        "get-base", help="Print base_branch/parent_issue from plan frontmatter"
    )
    get_base.add_argument("issue_number", type=int)
    get_base.set_defaults(func=_get_base)

    branch = sub.add_parser("create-branch", help="Create and checkout a branch")
    branch.add_argument("branch_name")
    branch.add_argument("--base-ref")
    branch.set_defaults(func=_create_branch)

    worktree = sub.add_parser(
        "create-worktree", help="Create a git worktree with a new branch"
    )
    worktree.add_argument("path")
    worktree.add_argument("branch_name")
    worktree.add_argument("--base-ref")
    worktree.set_defaults(func=_create_worktree)

    push = sub.add_parser("push-branch", help="Push a branch to origin")
    push.add_argument("branch_name")
    push.set_defaults(func=_push_branch)

    clean = sub.add_parser("clean-up", help="Delete stale local branches and their worktrees")
    clean.set_defaults(func=_clean_up)


def build_core_parser() -> argparse.ArgumentParser:
    """Return an ArgumentParser preloaded with the core subcommands.

    The returned parser's subparsers action is guarded against duplicate names.
    Retrieve it with :func:`subparsers` to register additional (project)
    commands onto the same tree.
    """
    parser = argparse.ArgumentParser(prog="harness_cli.py", description="Workflow harness CLI")
    action = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    register_core(_GuardedSubparsers(action))
    return parser


def subparsers(parser: argparse.ArgumentParser) -> _GuardedSubparsers:
    """Return the guarded subparsers wrapper for a build_core_parser() parser."""
    action = parser._subparsers._group_actions[0]  # noqa: SLF001 — no public accessor
    return _GuardedSubparsers(action)


def dispatch(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> int:
    """Parse ``argv`` and invoke the selected handler.

    Handlers set via ``set_defaults(func=...)`` may return an int exit code or
    None (treated as 0), so project handlers that ``print`` and fall off the end
    keep working unchanged.
    """
    args = parser.parse_args(argv)
    return args.func(args) or 0
