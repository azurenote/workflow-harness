"""The exit-code contract: one enum, one table, and handlers that use only the enum.

Three things are held together here. ``ExitCode`` is the enum;
``skills/_shared/references/exit-codes.md`` is the one table; and every command
handler returns only ``ExitCode`` members. The handlers are found by building
the real parsers, not from a list of names, so a new command is checked the
day it is registered.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from harness_core import cli, plan_body, plan_restore, scaffold
from harness_core.exitcodes import ExitCode
from harness_core.trackers import github

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "skills" / "_shared" / "references" / "exit-codes.md"
MODULES = (cli, plan_body, plan_restore, scaffold, github)


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section(title: str) -> str:
    text = _doc()
    start = text.index(f"## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


# ── Discovery ─────────────────────────────────────────────────────────────────


def _unwrap(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


def _registered() -> dict:
    """Every command the parsers register, name -> the function set as ``func``."""
    parser = cli.build_core_parser()
    github.register_github_commands(cli.subparsers(parser), owner="o", repo="r")
    choices = parser._subparsers._group_actions[0].choices  # noqa: SLF001
    return {name: sub.get_default("func") for name, sub in choices.items()}


def _commands() -> dict:
    """name -> (function as registered, handler behind any wrapper)."""
    found = {name: (func, _unwrap(func)) for name, func in _registered().items()}
    found["plan_body"] = (plan_body.main, plan_body.main)
    found["plan_restore"] = (plan_restore.main, plan_restore.main)
    found["scaffold"] = (scaffold.main, scaffold.main)
    return found


# ── What a handler returns ────────────────────────────────────────────────────


def _function_node(func) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef), func
    return node


def _own_nodes(fn: ast.FunctionDef):
    """Nodes of ``fn`` itself, not of the functions defined inside it."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _rebinds(scope: ast.FunctionDef, name: str) -> bool:
    """``name`` bound by anything but a plain ``name = value``."""
    for node in _own_nodes(scope):
        targets = []
        if isinstance(node, ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.NamedExpr):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = [t for t in node.targets if not isinstance(t, ast.Name)]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            targets = [i.optional_vars for i in node.items if i.optional_vars]
        if any(isinstance(n, ast.Name) and n.id == name for t in targets for n in ast.walk(t)):
            return True
    return False


def returned_names(fn: ast.FunctionDef, *, delegates: bool = False) -> tuple[set[str], list[str]]:
    """The ``ExitCode`` members ``fn`` can return, and every return it cannot read.

    A return value is read through conditional expressions, ``or``/``and``,
    calls to a function defined inside the handler, and local names bound only
    by plain assignments that read the same way. Anything else is a problem, not
    a guess. ``delegates`` also accepts a call to any other function as a leaf —
    for ``dispatch`` and the script entry points, whose code is another handler's.
    """
    names: set[str] = set()
    problems: list[str] = []
    nested = {n.name: n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef) and n is not fn}
    seen: set[str] = set()

    def value(expr, scope: ast.FunctionDef) -> None:
        if expr is None:
            problems.append(f"{scope.name}: bare return")
        elif (isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name)
              and expr.value.id == "ExitCode" and expr.attr in ExitCode.__members__):
            names.add(expr.attr)
        elif isinstance(expr, ast.IfExp):
            value(expr.body, scope)
            value(expr.orelse, scope)
        elif isinstance(expr, ast.BoolOp):
            for v in expr.values:
                value(v, scope)
        elif isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id in nested:
            closure = nested[expr.func.id]
            if closure.name not in seen:
                seen.add(closure.name)
                returns_of(closure)
        elif isinstance(expr, ast.Call) and delegates:
            pass
        elif isinstance(expr, ast.Name):
            if _rebinds(scope, expr.id):
                problems.append(f"{scope.name}: {expr.id} is rebound by more than a plain assignment")
            assigned = [n.value for n in _own_nodes(scope)
                        if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
                        and any(isinstance(t, ast.Name) and t.id == expr.id
                                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]
            if not assigned:
                problems.append(f"{scope.name}: {expr.id} has no assignment to read")
            for v in assigned:
                value(v, scope)
        else:
            problems.append(f"{scope.name}: cannot read `return {ast.unparse(expr)}`")

    def returns_of(scope: ast.FunctionDef) -> None:
        for node in _own_nodes(scope):
            if isinstance(node, ast.Return):
                value(node.value, scope)

    returns_of(fn)
    return names, problems


# ── Literal rc ────────────────────────────────────────────────────────────────


def _exit_call(node) -> bool:
    func = getattr(node, "func", None)
    return isinstance(node, ast.Call) and (
        isinstance(func, ast.Name) and func.id in ("SystemExit", "exit", "quit")
        or isinstance(func, ast.Attribute) and func.attr in ("exit", "_exit")
        and isinstance(func.value, ast.Name) and func.value.id in ("sys", "os")
    )


def literal_violations(tree: ast.AST, *, returns: bool = True) -> list[str]:
    """Exit codes written as numbers: in a return, a ``sys.exit`` or a ``SystemExit``.

    ``ExitCode(<n>)`` and ``int(...)`` count too — both are a number wearing
    the enum's name.
    """
    found = []

    def leaves(node):
        # The value itself, through the forms that pick between values. Not
        # into arguments or subscripts: `main(sys.argv[1:])` returns no 1.
        if isinstance(node, ast.IfExp):
            yield from leaves(node.body)
            yield from leaves(node.orelse)
        elif isinstance(node, ast.BoolOp):
            for v in node.values:
                yield from leaves(v)
        elif isinstance(node, ast.UnaryOp):
            yield from leaves(node.operand)
        else:
            yield node

    carriers = [n.value for n in ast.walk(tree) if returns and isinstance(n, ast.Return) and n.value]
    carriers += [a for n in ast.walk(tree) if _exit_call(n) for a in [*n.args, *(k.value for k in n.keywords)]]
    for carrier in carriers:
        for node in leaves(carrier):
            if (isinstance(node, ast.Constant) and type(node.value) is int
                    or isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("ExitCode", "int")):
                found.append(f"line {node.lineno}: {ast.unparse(carrier)}")
    return found


def _guarded_functions() -> list:
    funcs = [handler for _, handler in _commands().values()]
    funcs += [cli.dispatch, cli._refusing, scaffold.main_init, scaffold.main_update]  # noqa: SLF001
    return funcs


_DELEGATES = (cli.dispatch, scaffold.main_init, scaffold.main_update)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_enum_is_the_decided_table() -> None:
    assert [(m.name, m.value) for m in ExitCode] == [
        ("OK", 0), ("CRASH", 1), ("REFUSED", 2), ("INCOMPLETE", 3),
        ("UNKNOWN", 4), ("NOOP", 5), ("FINDINGS", 6),
    ]


def test_doc_enum_table_matches_the_enum() -> None:
    rows = re.findall(r"^\| (\d) \| `([A-Z]+)` \|", _section("열거형"), re.M)
    assert [(name, int(value)) for value, name in rows] == [(m.name, m.value) for m in ExitCode]


def _doc_commands() -> dict:
    rows = {}
    for line in _section("명령별").splitlines():
        match = re.match(r"^\| (`[a-z_-]+`|board 스텁) \| ((?:`[A-Z]+`(?: · )?)+) \| .+ \|$", line)
        if match:
            rows[match.group(1).strip("`")] = re.findall(r"`([A-Z]+)`", match.group(2))
    return rows


def test_doc_lists_every_registered_command_and_nothing_else() -> None:
    doc = _doc_commands()
    assert doc.pop("board 스텁") == ["REFUSED"], "the project-owned board stub row changed"
    assert set(doc) == set(_commands()), (
        f"table only: {sorted(set(doc) - set(_commands()))}, "
        f"code only: {sorted(set(_commands()) - set(doc))}"
    )


@pytest.mark.parametrize("command", sorted(_commands()))
def test_doc_row_matches_what_the_handler_returns(command: str) -> None:
    registered, handler = _commands()[command]
    names, problems = returned_names(_function_node(handler))
    assert not problems, problems
    assert "OK" in names, f"{command} never returns ExitCode.OK: {sorted(names)}"
    if getattr(registered, "_refusals", ()):
        names.add("REFUSED")
    # Usage errors are REFUSED everywhere and the table says so once, above it;
    # a row names what the command itself returns, no more and no less.
    assert set(_doc_commands()[command]) == names, command


@pytest.mark.parametrize("func", _DELEGATES, ids=lambda f: f.__qualname__)
def test_delegating_entry_points_return_only_members_or_calls(func) -> None:
    names, problems = returned_names(_function_node(func), delegates=True)
    assert not problems, problems


@pytest.mark.parametrize("func", _guarded_functions(), ids=lambda f: f"{f.__module__}.{f.__qualname__}")
def test_handlers_return_no_number(func) -> None:
    assert literal_violations(_function_node(func)) == []


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_module_exits_with_a_number(module) -> None:
    tree = ast.parse(inspect.getsource(module))
    assert literal_violations(tree, returns=False) == []


# What each core command refuses (one stderr line, REFUSED); the rest crash.
_REFUSALS = {
    "find-draft-plan": {"NoPlanFileError", "MultiplePlanFilesError", "MainWorktreeUnresolvedError"},
    "rename-plan": {"InvalidPlanFileError", "PlanFileExistsError", "MainWorktreeUnresolvedError"},
    "plan-file": {"PlanFileNotFoundError", "MainWorktreeUnresolvedError"},
    "get-base": {"MainWorktreeUnresolvedError"},
    "create-worktree": {"MainWorktreeUnresolvedError", "GitRefusedError"},
    "clean-up": {"MainWorktreeUnresolvedError", "GitRefusedError"},
    "create-branch": {"GitRefusedError"},
    "push-branch": {"GitRefusedError"},
}


def test_core_refusals_are_exactly_the_named_classes() -> None:
    """A wider class — ``FileExistsError`` for ``PlanFileExistsError``, an added
    ``OSError`` — turns a crash into a polite refusal; the set is pinned whole."""
    registered = _registered()
    got = {
        name: {cls.__name__ for cls in getattr(registered[name], "_refusals", ())}
        for name in _REFUSALS
    }
    assert got == _REFUSALS
    core = set(cli.build_core_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001
    assert core == set(_REFUSALS), "a core command without a row here"


def test_no_handler_returns_crash() -> None:
    for command, (_, handler) in _commands().items():
        names, _ = returned_names(_function_node(handler))
        assert "CRASH" not in names, command


# Each shape a number can take on its way out, as a handler would write it —
# next to an honest `return ExitCode.OK`, so neither guard can pass it on the
# absence of OK — and the guard that exists to catch it.
_FORBIDDEN = {
    "return 0": ("    return 0\n", "literal"),
    "conditional": ("    return 3 if a else ExitCode.OK\n", "literal"),
    "through a name": ("    rc = 3\n    return rc\n", "names"),
    "augmented name": ("    rc = ExitCode.OK\n    rc += 3\n    return rc\n", "names"),
    "loop-bound name": ("    for rc in (3,):\n        pass\n    return rc\n", "names"),
    "sys.exit": ("    sys.exit(1)\n", "literal"),
    "sys.exit keyword": ("    sys.exit(code=1)\n", "literal"),
    "builtin exit": ("    exit(1)\n", "literal"),
    "os._exit": ("    os._exit(3)\n", "literal"),
    "SystemExit": ("    raise SystemExit(2)\n", "literal"),
    "enum by value": ("    return ExitCode(3)\n", "literal"),
    "int()": ("    return int(a)\n", "literal"),
    "a foreign call": ("    return helper(a)\n", "names"),
    "in a closure": ("    def _fail():\n        return 3\n    return _fail()\n", "literal"),
}


@pytest.mark.parametrize("shape", sorted(_FORBIDDEN))
def test_guards_catch_every_shape(shape: str) -> None:
    body, guard = _FORBIDDEN[shape]
    fn = ast.parse(f"def h(a):\n    if a:\n        return ExitCode.OK\n{body}").body[0]
    names, problems = returned_names(fn)
    caught = {"literal": bool(literal_violations(fn)), "names": bool(problems)}
    assert caught[guard], f"the {guard} guard does not catch the {shape!r} shape: {caught}"


def test_guards_read_the_allowed_shapes() -> None:
    source = (
        "def h(a):\n"
        "    def _fail():\n"
        "        return ExitCode.INCOMPLETE\n"
        "    rc = ExitCode.REFUSED\n"
        "    if a:\n"
        "        return rc\n"
        "    if a > 1:\n"
        "        return _fail()\n"
        "    return ExitCode.FINDINGS if a else ExitCode.OK\n"
    )
    fn = ast.parse(source).body[0]
    assert returned_names(fn) == ({"REFUSED", "INCOMPLETE", "FINDINGS", "OK"}, [])
    assert literal_violations(fn) == []


_RC_IN_PROSE = re.compile(r"\bexit(?:s|ed)? [0-6]\b|\brc [0-6]\b|\*\*[0-6]\*\*")


@pytest.mark.parametrize("command", sorted(_commands()))
def test_handler_docs_point_at_the_table(command: str) -> None:
    """A handler's documentation names members and the table, never the numbers."""
    _, handler = _commands()[command]
    module = inspect.getmodule(handler)
    doc = inspect.getdoc(handler) if module is github else inspect.getdoc(module)
    assert doc and "exit-codes.md" in doc, f"{command}: no pointer to exit-codes.md"
    for text in (doc, inspect.getdoc(handler) or ""):
        # A number is allowed only as the value next to its name, e.g. `FINDINGS (6)`.
        bare = [m for m in _RC_IN_PROSE.findall(text)]
        assert not bare, f"{command}: an exit code as a number: {bare}"


def test_findings_means_a_finding_that_needs_a_person() -> None:
    """#70 widened FINDINGS from a gate's drift to any read-only check that found
    something a person must judge; the row names both of its users."""
    row = next(l for l in _section("열거형").splitlines() if l.startswith("| 6 | `FINDINGS` |"))
    meaning, caller = [c.strip() for c in row.strip("|").split("|")[2:4]]
    assert meaning.startswith("읽기 전용 검사가 사람 판단이 필요한 것을 찾았다.")
    assert "`audit-fields --fail-on-drift` 의 드리프트" in meaning
    assert "`plan_restore` 의 summary·rev·작성자 불일치" in meaning
    assert caller == "성공으로 취급하지 않는다. 게이트면 실패, 스킬 절차면 사람에게 묻는다"
    assert "**`FINDINGS` 가 이긴다**" in _doc(), "the FINDINGS-over-INCOMPLETE rule is gone"
