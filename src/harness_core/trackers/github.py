"""GitHub issue metadata contract — policy, observation and writes.

One fact lives in one place: **type** is the issue type, **priority** / **size**
/ **status** are project (Projects V2) single-select fields, and **labels carry
area tags only**. The drift this module exists to stop is the same fact written
in two of those places at once — an issue typed ``Bug`` that also carries a
``bug`` label, a priority that is one value as a label and another as a field.

Three layers, in dependency order:

1. **Policy** — pure functions, no I/O. :func:`reserved_label_violations` and
   :func:`field_drift` decide what is wrong; they return sentences, not
   exceptions, because the caller decides whether a violation stops the run.
2. **The ``gh`` boundary** — :func:`run_gh` is the *only* function here that
   starts a subprocess. Every other function takes a ``run`` callable and
   defaults to looking this one up **as a module attribute at call time**, so
   ``monkeypatch.setattr(module, "run_gh", fake)`` reaches every call site. A
   default argument bound at def-time would not be reachable.
3. **Commands** — :func:`register_github_commands` adds this project's tracker
   commands to an existing subparsers action. Registration does no I/O.

Project constants are injected, never named here. The reserved-label set is
*derived at runtime* from the repository's issue type names and the option names
of the injected project fields — so a project that renames ``P1`` does not need
a change in this file. The one literal is :data:`DEFAULT_STATUS_FIELD`, which is
GitHub's own name for the field it creates in every project, and a caller that
renamed it injects its own.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import dataclass, field as dataclass_field
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from ..exitcodes import ExitCode
from ..io import print_error, print_json
from ..local import abs_under_main

# GitHub Projects creates every project with a single-select field named
# "Status". A project that renamed it injects `field_names["status"]`; this is
# only the fallback, and it is a platform name rather than a project constant.
DEFAULT_STATUS_FIELD = "Status"

# The field names GitHub Projects ships with, and the values the reference doc
# documents `field_names` as defaulting to. A project that renamed a field
# injects its own name; these exist so that omitting `field_names` — which the
# documented schema and the starter template both allow — yields a working
# command rather than a KeyError.
DEFAULT_FIELD_NAMES = {"priority": "Priority", "size": "Size", "status": DEFAULT_STATUS_FIELD}

Run = Callable[..., str]


class GhError(RuntimeError):
    """A ``gh`` invocation failed, or answered with something outside its contract.

    Mostly a non-zero exit. :class:`GraphQLError` is the other half: ``gh``
    answered, and the answer is not a usable result. Every handler catches this
    one class for both, so a response nobody can use takes the same exit code as
    a call that never returned.

    Carries the command and stderr so a handler can report *what* failed, which
    is the difference between "retry the fields" and "the issue was never made".
    ``stdout`` is kept too: ``gh`` exits 1 on a GraphQL error but still writes the
    response — ``errors[].type`` and ``path`` included — there, and that
    structure is the only way to tell one error from another without reading
    GitHub's wording. It is for reading, never for quoting: it is not in the
    message.
    """

    def __init__(self, argv: Sequence[str], returncode: int, stderr: str, stdout: str = "") -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr.strip()
        self.stdout = stdout
        # Name the command, not the payload. argv for a GraphQL call carries the
        # whole mutation document plus every node ID, and this string is echoed
        # into the JSON that impl-reports and issue comments quote verbatim.
        super().__init__(f"gh {' '.join(self.argv[:2])} exited {returncode}: {self.stderr}")


class GraphQLError(GhError):
    """A GraphQL call came back, but not with a usable ``data`` object.

    Real ``gh`` already exits 1 when a response carries ``errors``, so on the
    default runner that case arrives as a plain :class:`GhError`. This is the
    same judgement made where the response is read, so it holds whatever runs
    the call — and it also covers what ``gh`` passes through with exit 0:
    output that is not JSON, JSON that is not an object, no ``data``, and a
    mutation that answered without the object it exists to return.

    ``stderr`` holds the reason — the server's ``errors[].message`` where there
    are any — because :meth:`ProjectFields.load` quotes that attribute. Only the
    reason: the query and its variables are not assembled into it. ``errors``
    holds the server's ``errors`` as they came when that is why the response
    was refused, and is ``None`` otherwise — kept for the same reason
    :class:`GhError` keeps ``stdout`` and, like it, not in the message.
    """

    def __init__(self, argv: Sequence[str], reason: str, *, errors: object = None) -> None:
        super().__init__(argv, 0, reason)
        self.errors = errors
        # The inherited message says "exited 0", which reads as a success.
        self.args = (f"gh {' '.join(self.argv[:2])} returned an unusable response: {self.stderr}",)


class FieldNotFoundError(LookupError):
    """A configured field name does not exist in the project."""


class LinkTargetError(LookupError):
    """A parent or blocker that cannot be linked; ``reason`` says why."""

    def __init__(self, number: int, reason: str, detail: str = "") -> None:
        self.number, self.reason = number, reason
        super().__init__(f"#{number} {reason}" + (f": {detail}" if detail else ""))


class OptionNotFoundError(LookupError):
    """A requested option name does not exist on a single-select field."""


# ── Layer 1: policy (pure) ───────────────────────────────────────────────────


def _normalize(value: str) -> str:
    """Case-fold a name for exact lookup (field names, option names, types)."""
    return value.strip().casefold()


def _label_key(value: str) -> str:
    """Fold a label for *comparison* against a type or option name.

    Separators carry no meaning here: the drift this module exists to stop wrote
    ``In progress`` as the label ``in-progress`` and ``P1`` as ``P-1``. Matching
    on the case-folded string alone let both through. Kept distinct from
    :func:`_normalize` so that folding a label never merges two real option
    names that differ only by a separator.
    """
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def reserved_label_violations(
    labels: Iterable[str],
    *,
    type_names: Iterable[str] = (),
    option_names: Mapping[str, Iterable[str]] | None = None,
    allowed_labels: Iterable[str] | None = None,
    reserved_patterns: Iterable[str] = (),
) -> list[str]:
    """Return one sentence per label that breaks the metadata contract.

    Two stages, because they need different things. Stage one needs no network:
    ``allowed_labels`` (when the project declares a set) and
    ``reserved_patterns`` (case-insensitive :mod:`fnmatch` globs). Stage two
    needs one read first, and compares against ``type_names`` and
    ``option_names`` — the names that already have a home of their own.

    Call it with only the stage-one arguments to reject before touching the
    network, then again with the observed names. Both stages are the same
    judgement, so they are the same function.

    The stages do not have the same reach, and a project that declares no
    ``allowed_labels`` is the one that feels it: stage one then checks patterns
    only, so a label shaped like an issue type (``bug``) or a field option
    (``P1``) survives the offline stage and is caught in stage two, after the
    reads. Declaring ``allowed_labels`` moves that rejection ahead of every
    network call.

    This **rejects**; it never converts. Rewriting ``--label <priority option>``
    into ``--priority`` would guess at an intent only the caller knows, and a
    guess that is usually right is the worst kind for metadata nobody re-reads.

    Args:
        labels: The labels the caller wants to apply.
        type_names: Issue type names defined on the repository. Empty when the
            repository does not use issue types — the set degrades, the check
            does not disappear.
        option_names: ``{field name: option names}`` for the injected
            single-select fields. The field name is carried so the message can
            say where the value belongs.
        allowed_labels: The complete set of labels this project accepts. ``None``
            means "not declared" — stage one then checks only patterns. An empty
            *collection* means the project declared that no label is allowed.
            Compared case-insensitively but **exactly**: ``B-E`` is not ``BE``.
        reserved_patterns: Case-insensitive glob patterns the caller reserves.

    Returns:
        A list of sentences; empty means the labels pass.
    """
    # Materialize every iterable once. `reserved_patterns` is scanned per label
    # and `allowed_labels` is read twice (membership, then the message), so a
    # generator argument would be empty after the first use and silently pass
    # every label from the second one onward.
    labels = list(labels)
    allowed_list = None if allowed_labels is None else list(allowed_labels)
    patterns = list(reserved_patterns)

    # Two comparison keys, deliberately. The reserved axis folds separators away,
    # because `P-1` and `P1` are the same claim on the same field. The allowed
    # axis folds case only: a label that matches the list only once its
    # separators are stripped is a different label, and it goes out with the
    # spelling the caller typed. The fold is symmetric — a listed `B-E` does not
    # admit `BE` any more than a listed `BE` admits `B-E`.
    allowed = None if allowed_list is None else {_normalize(a) for a in allowed_list}
    types = {_label_key(t) for t in type_names}
    options: dict[str, str] = {}
    for field_name, names in (option_names or {}).items():
        for name in names:
            options.setdefault(_label_key(name), field_name)

    violations: list[str] = []
    for label in labels:
        key = _label_key(label)
        if key in types:
            violations.append(
                f"label {label!r} duplicates an issue type; set it with --type, not --label"
            )
        if key in options:
            where = options[key]
            violations.append(
                f"label {label!r} duplicates an option of the {where!r} project field; "
                f"set that field instead of adding a label"
            )
        for pattern in patterns:
            # Case-fold only. `_label_key` strips non-alphanumerics, which would
            # eat the glob's own `*`, `?` and `[...]` along with the separators.
            if fnmatch(_normalize(label), _normalize(pattern)):
                violations.append(
                    f"label {label!r} matches the reserved pattern {pattern!r}"
                )
        if allowed is not None and _normalize(label) not in allowed:
            listed = ", ".join(sorted(allowed_list)) or "(none)"
            violations.append(
                f"label {label!r} is not one of this project's labels: {listed}"
            )
    # A label repeated on the command line must not repeat its sentence.
    return list(dict.fromkeys(violations))


def field_drift(
    meta: Mapping[str, object],
    *,
    option_names: Mapping[str, Iterable[str]] | None = None,
    type_names: Iterable[str] | None = (),
) -> list[str]:
    """Describe how one observed issue departs from the metadata contract.

    Read-only judgement over the output of :func:`read_issue_meta`. Reports the
    same duplication :func:`reserved_label_violations` rejects at write time,
    plus the absences that duplication hides: no issue type, not in the project,
    an empty field whose value was written as a label instead.

    ``type_names`` is what catches the most common shape of all — an issue typed
    ``Bug`` that also carries a ``bug`` label. It has three states, and they mean
    different things: a non-empty list enables both the duplication check and the
    missing-type check; ``[]`` means the repository defines no issue types, so
    "no issue type" is not drift and is not reported; ``None`` means the types
    could not be read, and the caller is expected to say so rather than let a
    half-audit read as a clean one.
    """
    drift: list[str] = []
    number = meta.get("number")
    labels = list(meta.get("labels") or [])

    options: dict[str, str] = {}
    for field_name, names in (option_names or {}).items():
        for name in names:
            options.setdefault(_label_key(name), field_name)
    types = {_label_key(name) for name in (type_names or ())}

    for label in labels:
        if _label_key(label) in types:
            drift.append(f"#{number}: label {label!r} duplicates the issue type")
        where = options.get(_label_key(label))
        if where:
            drift.append(f"#{number}: label {label!r} duplicates the {where!r} field")

    # Only an issue in a repository that *has* types can be missing one. Flagging
    # it when the repository defines none would mark every issue as drifted.
    if type_names and not meta.get("type"):
        drift.append(f"#{number}: no issue type")

    project = meta.get("project")
    if not isinstance(project, Mapping) or not project:
        drift.append(f"#{number}: not in the configured project")
        return drift

    for slot in ("status", "priority", "size"):
        if slot in project and not project[slot]:
            drift.append(f"#{number}: {slot} field is empty")
    return drift


# ── Layer 2: the `gh` boundary ───────────────────────────────────────────────


def run_gh(argv: Sequence[str], *, stdin: str | None = None) -> str:
    """Run ``gh`` and return stdout; raise :class:`GhError` on a non-zero exit.

    The single subprocess call site in this module. Everything else reaches it
    through the ``run`` parameter, which defaults to this name looked up at call
    time — that is the seam tests replace.
    """
    try:
        proc = subprocess.run(
            ["gh", *argv], input=stdin, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        # The `harness_enabled: false` world is exactly where gh may be absent.
        # A raw FileNotFoundError traceback tells the caller nothing actionable.
        raise GhError(argv, 127, "gh is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise GhError(argv, proc.returncode, proc.stderr, proc.stdout)
    return proc.stdout


def _run(run: Run | None) -> Run:
    """Resolve the runner, looking up :func:`run_gh` at call time."""
    return run if run is not None else run_gh


def _graphql(
    query: str, variables: Mapping[str, object], *, run: Run | None = None
) -> dict:
    """Execute a GraphQL document and return its ``data`` object.

    Anything else is a :class:`GraphQLError`, including a response that carries
    ``data`` *and* ``errors``. That partial answer is refused rather than used:
    ``gh`` itself exits 1 on it, and accepting it here would make the outcome
    depend on which runner made the call. Returning ``{}`` for a response that
    could not be read — what this did — handed every caller a result that read
    as "nothing there", and the failure surfaced frames later as an
    ``AttributeError`` or ``KeyError`` that no handler catches.
    """
    argv = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, list):
            # `key[]=item` is gh's array syntax, one flag per element; a list
            # passed as `key=value` would arrive as the string "['OPEN']". An
            # empty list has no spelling in that syntax — no flag at all is an
            # omitted variable, which is `null`, not `[]` — so it is refused
            # rather than silently sent as something else.
            if not value:
                raise ValueError(f"GraphQL variable {key!r}: an empty list cannot be sent")
            # `-f` sends each element as a string; `True` would go out as the
            # string "True". Only string lists (enum values) are used today.
            if not all(isinstance(item, str) for item in value):
                raise TypeError(f"GraphQL variable {key!r}: only lists of strings are supported")
            for item in value:
                argv += ["-f", f"{key}[]={item}"]
            continue
        # -F types the value (ints stay ints); -f keeps a string a string, which
        # matters for node IDs that would otherwise be coerced.
        flag = "-F" if isinstance(value, (int, bool)) and not isinstance(value, str) else "-f"
        argv += [flag, f"{key}={value}"]
    out = _run(run)(argv)
    try:
        payload = json.loads(out)
    except ValueError as exc:
        raise GraphQLError(argv, f"the output is not JSON ({exc})") from None
    if not isinstance(payload, dict):
        raise GraphQLError(argv, f"expected a JSON object, got {type(payload).__name__}")
    errors = payload.get("errors")
    if errors:
        raise GraphQLError(argv, _graphql_error_text(errors), errors=errors)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GraphQLError(argv, "the response carries no data object")
    return data


def _graphql_error_text(errors: object) -> str:
    """The server's own messages out of an ``errors`` value of any shape.

    The spec says a list of objects with ``message``; this is the code that runs
    when a response already broke its contract, so it must not raise on one
    that breaks the spec as well.
    """
    entries = errors if isinstance(errors, list) else [errors]
    messages = []
    for entry in entries:
        message = entry.get("message") if isinstance(entry, dict) else None
        messages.append(message if isinstance(message, str) and message else repr(entry))
    return "; ".join(messages)


def _graphql_errors(exc: GhError) -> list[object] | None:
    """The server's ``errors`` behind a failed call, as structure, or ``None``.

    From a :class:`GraphQLError` they are the ones :func:`_graphql` refused;
    from any other :class:`GhError` they are in the response ``gh`` still wrote
    to stdout when it exited 1. A body that is missing or unreadable is
    ``None``, never an exception: this is read while reporting a failure.
    """
    if isinstance(exc, GraphQLError) and isinstance(exc.errors, list):
        return exc.errors
    try:
        body = json.loads(exc.stdout)
    except (TypeError, ValueError, RecursionError):
        return None
    errors = body.get("errors") if isinstance(body, dict) else None
    return errors if isinstance(errors, list) else None


# ── Layer 3: name resolution and observation ─────────────────────────────────


@dataclass(frozen=True)
class SingleSelectField:
    """One single-select project field and its options, both name- and id-keyed."""

    id: str
    name: str
    options: dict[str, tuple[str, str]] = dataclass_field(default_factory=dict)

    def option(self, option_name: str) -> tuple[str, str]:
        """``(id, canonical name)`` for one option, matched case-insensitively.

        The canonical name comes back with the id because the caller records what
        it asked for and then compares that record against the read-back.
        Recording the spelling the caller typed made ``--priority p1`` report
        ``requested 'p1', observed 'P1'`` — drift against the very option it had
        just matched.
        """
        try:
            return self.options[_normalize(option_name)]
        except KeyError:
            available = ", ".join(name for _, name in self.options.values()) or "(none)"
            raise OptionNotFoundError(
                f"{self.name!r} has no option {option_name!r}; available: {available}"
            ) from None

    def option_id(self, option_name: str) -> str:
        return self.option(option_name)[0]


@dataclass(frozen=True)
class ProjectFields:
    """A project's single-select fields, resolved from names to IDs.

    Only single-select fields are modelled. Text, number, date and iteration
    fields are not resolved here and writing them is not supported — the
    metadata contract this module enforces uses single-select fields only.
    """

    project_id: str
    number: int
    owner: str
    fields: dict[str, SingleSelectField] = dataclass_field(default_factory=dict)

    _QUERY = """
      query($owner:String!,$number:Int!){
        %s(login:$owner){
          projectV2(number:$number){
            id
            fields(first:50){
              nodes{
                ... on ProjectV2SingleSelectField { id name options { id name } }
              }
            }
          }
        }
      }
    """

    @classmethod
    def load(
        cls, owner: str, number: int, *, run: Run | None = None, use_cache: bool = True
    ) -> "ProjectFields":
        """Resolve a project's single-select fields, organization then user.

        A project owner may be either kind of account and the GraphQL entry
        points are different, so a failed ``organization`` lookup — or one whose
        board did not come back — is a signal to try ``user``, not an error.
        Results are cached per process: a command that writes two fields
        resolves the project once.

        "Not found" needs a root that said so: an account that is not there, or
        a NOT_FOUND error on the board itself. A board that comes back null
        with no error says nothing about whether it exists — the one place it
        has been seen is a user's own board hidden from a fine-grained token
        (2026-09-26).
        """
        key = (owner, int(number))
        if use_cache and key in _FIELDS_CACHE:
            return _FIELDS_CACHE[key]

        project = None
        # Why each root missed, in the order tried. A login that is not an
        # organization is expected to fail there — but a missing `project` token
        # scope fails there too and needs a completely different fix, and the
        # user root then fails with "Could not resolve to a User". Keeping only
        # the last error, which this did, reported that and dropped the scope.
        misses: list[tuple[str, str]] = []
        answered = False
        for root in ("organization", "user"):
            try:
                data = _graphql(
                    cls._QUERY % root, {"owner": owner, "number": int(number)}, run=run
                )
            except GhError as exc:
                # A NOT_FOUND on the board is GitHub's own "no such board" — or
                # one this token may not see: another organization's private
                # board answers the same way (measured). What an organization
                # board read without the token's Projects permission answers
                # was not measured. Keep asking: the other root may have it.
                answered = answered or _is_board_not_found(exc, root)
                # One line: this lands in audit JSON and in issue comments.
                reason = " ".join(exc.stderr.split())
                if not reason:
                    # Not "exited 0" for a GraphQLError: that reads as a success.
                    reason = (
                        "gh returned an unusable response with no message"
                        if isinstance(exc, GraphQLError)
                        else f"gh exited {exc.returncode} with no message"
                    )
                misses.append((root, reason))
                continue
            account = data.get(root)
            if not isinstance(account, dict):
                # A null account is an answer — no such account. Anything else
                # in its place is not one, the same as `repository: "x"`. (Real
                # `gh` sends a missing account as a NOT_FOUND error at [root],
                # which the handler above does not count; an errorless null
                # account comes only from other runners.)
                answered = answered or account is None
                misses.append((root, f"no {root} object"))
                continue
            # No value here is the account saying it has no such board. A null
            # with no error is how GitHub hides a board from this token (a
            # user's own board, measured 2026-09-26) — a board that does not
            # exist comes with a NOT_FOUND error instead, handled above. And
            # `"x"`, `{}` or the key missing judged nothing either, like an
            # account of the wrong shape. (A missing *account* key still reads
            # as null through `data.get` above and counts as an answer: a known
            # asymmetry, left as it was.)
            present = "projectV2" in account
            candidate = account.get("projectV2")
            if present and candidate is None:
                misses.append(
                    (
                        root,
                        f"project #{number} not visible (null without an error — "
                        "check that the token can read this account's projects)",
                    )
                )
                continue
            if not (isinstance(candidate, dict) and candidate):
                shape = _describe(candidate) if present else "missing"
                misses.append((root, f"unusable projectV2 ({shape})"))
                continue
            answered = True
            project = candidate
            break
        if project is None:
            _FIELDS_CACHE.pop(key, None)
            detail = "; ".join(f"{root}: {reason}" for root, reason in misses)
            # "Not found" is a judgement: a root had to say it — an account that
            # is not there, or a board NOT_FOUND. With none, nobody made it.
            verdict = "not found" if answered else "could not be resolved"
            raise FieldNotFoundError(
                f"project #{number} {verdict} for owner {owner!r} as an organization "
                f"or a user ({detail})"
            )

        # A project that came back in the wrong shape is a project whose fields
        # could not be read — the same answer as one that was not found, and the
        # one every caller already handles. Left alone, `"fields": null` or an
        # option without a name escaped as an AttributeError or a KeyError.
        try:
            project_id = project["id"]
            fields: dict[str, SingleSelectField] = {}
            for node in project.get("fields", {}).get("nodes") or []:
                if not node or "options" not in node:
                    continue  # not a single-select field
                options = {
                    _normalize(option["name"]): (option["id"], option["name"])
                    for option in node["options"]
                }
                fields[_normalize(node["name"])] = SingleSelectField(
                    id=node["id"], name=node["name"], options=options
                )
        except (KeyError, TypeError, AttributeError) as exc:
            _FIELDS_CACHE.pop(key, None)
            raise FieldNotFoundError(
                f"project #{number} of {owner!r} came back malformed "
                f"({type(exc).__name__}: {exc}); its fields could not be read"
            ) from None

        resolved = cls(project_id=project_id, number=int(number), owner=owner, fields=fields)
        # Refresh the entry even when the cache was bypassed for reading: a
        # `use_cache=False` call that left a stale entry behind would hand the
        # stale object straight back to the next default-argument caller.
        _FIELDS_CACHE[key] = resolved
        return resolved

    def field(self, name: str) -> SingleSelectField:
        try:
            return self.fields[_normalize(name)]
        except KeyError:
            available = ", ".join(f.name for f in self.fields.values()) or "(none)"
            raise FieldNotFoundError(
                f"project #{self.number} has no single-select field {name!r}; "
                f"available: {available}"
            ) from None

    def option_names(self, field_names: Iterable[str]) -> dict[str, list[str]]:
        """``{field name: option names}`` for the named fields that exist.

        A configured field that the project does not have is skipped rather than
        raised: this feeds the reserved-label derivation, and a misconfigured
        field name must not make every label pass.
        """
        collected: dict[str, list[str]] = {}
        for name in field_names:
            if not name:
                continue
            existing = self.fields.get(_normalize(name))
            if existing is None:
                continue
            collected[existing.name] = [display for _, display in existing.options.values()]
        return collected


_FIELDS_CACHE: dict[tuple[str, int], ProjectFields] = {}


def clear_field_cache() -> None:
    """Drop the per-process project-field cache (tests; long-lived processes)."""
    _FIELDS_CACHE.clear()


_ISSUE_TYPES_QUERY = """
  query($owner:String!,$repo:String!){
    repository(owner:$owner,name:$repo){
      issueTypes(first:50){ nodes { name } }
    }
  }
"""


def repo_issue_type_names(
    owner: str, repo: str, *, run: Run | None = None
) -> list[str] | None:
    """Issue type names defined on the repository.

    Three outcomes, and collapsing any two of them loses a fact the caller needs:

    - a list of names — the repository uses issue types;
    - ``[]`` — it defines none, which is a supported configuration;
    - ``None`` — they could not be read. Returning ``[]`` here would make a
      failed read look like a repository with no types, which silently drops
      ``--type`` and makes an audit report a clean bill of health.
    """
    try:
        data = _graphql(_ISSUE_TYPES_QUERY, {"owner": owner, "repo": repo}, run=run)
    except GhError:
        return None
    repository = data.get("repository")
    if not isinstance(repository, dict):
        # No repository object is not a repository without types; that
        # collapse is exactly the one this function's return values exist to
        # keep apart.
        return None
    issue_types = repository.get("issueTypes")
    if issue_types is None:
        return []
    nodes = issue_types.get("nodes") if isinstance(issue_types, dict) else None
    if nodes is None and isinstance(issue_types, dict):
        return []
    if not isinstance(nodes, list) or not all(isinstance(n, dict) or n is None for n in nodes):
        # Type names that cannot be read are not an empty list of them either.
        return None
    names = [node.get("name") for node in nodes if node]
    if not all(isinstance(name, str) for name in names):
        return None
    return [name for name in names if name]


_ISSUE_META_QUERY = """
  query($owner:String!,$repo:String!,$number:Int!){
    repository(owner:$owner,name:$repo){
      issue(number:$number){
        number title id url
        issueType { name }
        labels(first:100){ nodes { name } }
        parent { id number repository { nameWithOwner } }
        blockedBy(first:100){ totalCount nodes { id number repository { nameWithOwner } } }
        projectItems(first:20){
          nodes{
            id
            project {
              number
              owner { ... on Organization { login } ... on User { login } }
            }
            fieldValues(first:50){
              nodes{
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                  field { ... on ProjectV2SingleSelectField { name } }
                }
              }
            }
          }
        }
      }
    }
  }
"""


def read_issue_meta(
    owner: str,
    repo: str,
    number: int,
    *,
    project_number: int | None,
    field_names: Mapping[str, str],
    project_owner: str | None = None,
    run: Run | None = None,
) -> dict:
    """Read what is *actually* on an issue: type, labels and project fields.

    One query. The point of the module — every command reports what it read
    back, not what it asked for.

    Args:
        field_names: ``{slot: field name}``. Each slot becomes a key under
            ``project``; the caller names the fields because the names are its
            constants. ``status`` / ``priority`` / ``size`` are the slots the
            commands use.
        project_owner: Login that owns the board. Project numbers are per
            owner, so an issue on an organization's #4 and a user's #4 has two
            items with the same number; this picks the one on the configured
            board. ``None`` compares the number alone, which is only safe when
            the issue cannot sit on two owners' boards. Ignored when
            ``project_number`` is ``None``.

    Returns:
        ``{number, title, node_id, url, type, labels, project, parent,
        blocked_by, blocked_by_truncated}`` where ``project`` is ``None`` when
        the issue is in no matching project, and otherwise
        ``{item_id, fields, <slot>: <option name or None>, ...}``. ``parent`` is
        a number in this repository, ``owner/repo#N`` in another, or ``None``;
        ``blocked_by`` lists the same forms, sorted. The keys in
        ``_LINK_ID_KEYS`` carry the links' node ids for comparison, in the same
        order.

    Raises:
        LookupError: the repository answered and has no such issue.
        GraphQLError: the repository did not answer. That is not the same fact:
            reading ``repository: null`` as "no such issue" told the caller
            something about the issue that nobody had read.
    """
    data = _graphql(
        _ISSUE_META_QUERY,
        {"owner": owner, "repo": repo, "number": int(number)},
        run=run,
    )
    repository = data.get("repository")
    if not isinstance(repository, dict):
        raise GraphQLError(
            ["api", "graphql"], f"the response carries no repository object for {owner}/{repo}"
        )
    if "issue" not in repository:
        raise GraphQLError(
            ["api", "graphql"],
            f"the repository object for {owner}/{repo} carries no issue field",
        )
    # An explicit null is the repository's own answer: no such issue — or not
    # yet, for one created a moment ago. Only null: `{}` or `"x"` in its place
    # is an issue nobody could read, not one that is missing.
    issue = repository["issue"]
    if issue is None:
        raise LookupError(f"{owner}/{repo}#{number} not found")
    if not (isinstance(issue, dict) and issue):
        raise GraphQLError(
            ["api", "graphql"],
            f"the repository object for {owner}/{repo} carries an unreadable issue field",
        )
    # A missing or malformed parent/blockedBy is a GraphQLError too: see
    # _shape_links.
    meta = _shape_issue_node(
        issue,
        project_number=project_number,
        project_owner=project_owner,
        field_names=field_names,
    )
    meta.update(_shape_links(issue, owner, repo))
    return meta


def _link_ref(node: object, owner: str, repo: str, what: str) -> tuple[str, int | str]:
    """``(node id, display)`` of one linked issue; display is the number in this
    repository and ``owner/repo#N`` in any other.

    Identity is the node id: a number is only unique inside one repository, and
    an existing parent or blocker may live in another.
    """
    if not isinstance(node, dict):
        raise GraphQLError(["api", "graphql"], f"{what} is not an issue object: {node!r}")
    node_id, number = node.get("id"), node.get("number")
    where = (node.get("repository") or {}).get("nameWithOwner") if isinstance(
        node.get("repository"), dict) else None
    if not (isinstance(node_id, str) and node_id and isinstance(number, int)
            and not isinstance(number, bool) and isinstance(where, str) and where):
        raise GraphQLError(["api", "graphql"], f"{what} carries no readable id, number and repository")
    same = where.lower() == f"{owner}/{repo}".lower()
    return node_id, (number if same else f"{where}#{number}")


def _ref_key(ref: int | str) -> tuple:
    """This repository's numbers first, in order, then other repositories' by
    repository and number — ``o/r#9`` before ``o/r#10``."""
    if isinstance(ref, int):
        return (0, "", ref)
    where, _, number = ref.rpartition("#")
    return (1, where.lower(), int(number))


def _shape_links(issue: Mapping, owner: str, repo: str) -> dict:
    """The parent and blockers of one issue, read strictly.

    Only :func:`read_issue_meta` selects these fields, so the list query and
    :func:`iter_issue_meta` keep their shape. A field that is missing or
    malformed is an issue nobody could read — the same rule as a missing
    ``issue`` — not an issue without links: reading it as "no parent" would
    send a second ``addSubIssue`` or report drift that is not there.

    ``blocked_by_truncated`` marks a list longer than the page read; it is not a
    refusal, because every other command reading the issue would then fail on
    an issue with many blockers.
    """
    if "parent" not in issue or "blockedBy" not in issue:
        raise GraphQLError(["api", "graphql"], "the issue carries no parent or blockedBy field")
    parent = issue["parent"]
    parent_id, parent_ref = (None, None) if parent is None else _link_ref(parent, owner, repo, "parent")
    blocked = issue["blockedBy"]
    nodes = blocked.get("nodes") if isinstance(blocked, dict) else None
    total = blocked.get("totalCount") if isinstance(blocked, dict) else None
    if not isinstance(nodes, list) or not isinstance(total, int) or isinstance(total, bool):
        raise GraphQLError(["api", "graphql"], "blockedBy carries no readable nodes and totalCount")
    refs = sorted((_link_ref(node, owner, repo, "a blockedBy node") for node in nodes),
                  key=lambda pair: _ref_key(pair[1]))
    return {
        "parent": parent_ref,
        "parent_node_id": parent_id,
        "blocked_by": [ref for _, ref in refs],
        "blocked_by_node_ids": [node_id for node_id, _ in refs],
        "blocked_by_truncated": total > len(refs),
    }


# Node ids of the links, which the commands compare by and never print: a
# consumer reading them next to `blocked_by` would be reading internals.
_LINK_ID_KEYS = ("parent_node_id", "blocked_by_node_ids")


# Targets of a link are looked up before anything is written. `issueOrPullRequest`
# rather than `issue`: GitHub answers a pull-request number exactly as it answers
# a number that does not exist (NOT_FOUND on `issue`), and only this field says
# which of the two it was.
_LINK_TARGET_QUERY = """
  query($owner:String!,$repo:String!,$number:Int!){
    repository(owner:$owner,name:$repo){
      issueOrPullRequest(number:$number){
        __typename
        ... on Issue { id number state subIssuesSummary { total } }
      }
    }
  }
"""

# GitHub's cap on sub-issues per parent. A parent already at it passes a lookup
# and then refuses the link after the issue exists, on every retry.
SUB_ISSUE_LIMIT = 100



def read_link_target(owner: str, repo: str, number: int, *, run: Run | None = None) -> dict:
    """``{node_id, number, state, sub_issues}`` of an issue in this repository.

    Raises:
        LinkTargetError: ``reason`` is ``"does not exist"`` (the server's
            NOT_FOUND, read from its structure), ``"is a pull request"``, or
            ``"could not be read"`` — every other failure, because an answer
            nobody could read says nothing about the issue.
    """
    try:
        data = _graphql(
            _LINK_TARGET_QUERY, {"owner": owner, "repo": repo, "number": int(number)}, run=run
        )
    except GhError as exc:
        errors = _graphql_errors(exc)
        if errors and all(
            isinstance(e, dict) and e.get("type") == "NOT_FOUND"
            and e.get("path") == ["repository", "issueOrPullRequest"]
            for e in errors
        ):
            raise LinkTargetError(number, "does not exist") from None
        raise LinkTargetError(number, "could not be read", str(exc)) from None
    repository = data.get("repository")
    node = repository.get("issueOrPullRequest") if isinstance(repository, dict) else None
    if not isinstance(node, dict):
        raise LinkTargetError(number, "could not be read", "the answer carries no issue")
    if node.get("__typename") == "PullRequest":
        raise LinkTargetError(number, "is a pull request")
    summary = node.get("subIssuesSummary")
    total = summary.get("total") if isinstance(summary, dict) else None
    if not (node.get("__typename") == "Issue" and isinstance(node.get("id"), str) and node["id"]
            and node.get("number") == int(number) and node.get("state") in ("OPEN", "CLOSED")
            and isinstance(total, int) and not isinstance(total, bool)):
        raise LinkTargetError(number, "could not be read", "the answer is not a readable issue")
    return {"node_id": node["id"], "number": node["number"], "state": node["state"], "sub_issues": total}


_LIST_ISSUES_QUERY = """
  query($owner:String!,$repo:String!,$states:[IssueState!],$cursor:String){
    repository(owner:$owner,name:$repo){
      issues(first:100, after:$cursor, states:$states,
             orderBy:{field:CREATED_AT, direction:DESC}){
        pageInfo { hasNextPage endCursor }
        nodes{
          number title id url
          issueType { name }
          labels(first:100){ nodes { name } }
          projectItems(first:20){
            nodes{
              id
              project {
                number
                owner { ... on Organization { login } ... on User { login } }
              }
              fieldValues(first:50){
                nodes{
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2SingleSelectField { name } }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
"""


def iter_issue_meta(
    owner: str,
    repo: str,
    *,
    project_number: int | None,
    field_names: Mapping[str, str],
    project_owner: str | None = None,
    state: str = "open",
    limit: int | None = None,
    run: Run | None = None,
) -> list[dict]:
    """Read issue metadata page by page. Reads only — never mutates.

    Cursor pagination, because the 100-issue first page is exactly where an
    audit stops being an audit: a repository past that point would report a
    clean bill of health for the 101st issue onward.

    ``project_number``, ``project_owner`` and ``field_names`` select and shape
    each issue's project item exactly as in :func:`read_issue_meta`.

    A page that cannot be read is a :class:`GraphQLError`, on any page, and the
    pages before it are dropped with it. Read as an empty last page, which is
    what this did, ``repository: null`` on page one was ``scanned: 0`` — a clean
    audit of nothing — and on page two it was the first hundred issues passing
    for the whole repository.

    So is a node that is not an issue object, checked as each node is read:
    ``"x"`` used to escape ``_shape_issue_node`` as an ``AttributeError``, and
    ``null`` or ``{}`` was skipped — an issue gone from ``scanned`` with nothing
    to say it was never audited. Nodes past ``limit`` are not read, so they are
    not judged either.
    """
    if limit is not None and limit <= 0:
        return []
    # One state or none. `issues(states:)` takes `[IssueState!]`, and the query
    # declares `$states` with exactly that type. It used to declare a bare
    # `$state: IssueState` — which GitHub refuses at validation ("List dimension
    # mismatch") whatever the value, so the audit never ran against the real
    # API — while this comment claimed the query wrapped it in a list. It did
    # not; the fakes do not parse GraphQL, so nothing noticed. `all` omits the
    # variable rather than sending `[null]`, which breaks the non-null element.
    wanted_state = None if state == "all" else state.upper()
    collected: list[dict] = []
    cursor: str | None = None
    page_number = 0
    while True:
        page_number += 1
        variables: dict[str, object] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        if wanted_state:
            variables["states"] = [wanted_state]
        data = _graphql(_LIST_ISSUES_QUERY, variables, run=run)
        nodes, next_cursor = _read_list_page(data, page_number, owner, repo, after=cursor)
        for index, node in enumerate(nodes, start=1):
            # Only a non-empty object is an issue. The list enumerates what
            # exists, so unlike `issue(number:)` a null here answers nothing.
            # This judges the element only; what is inside it stays
            # `_shape_issue_node`'s (#24).
            if not (isinstance(node, dict) and node):
                what = f"node {index} is not an issue object ({_describe(node)})"
                raise _list_page_error(page_number, owner, repo, what)
            collected.append(
                _shape_issue_node(
                    node,
                    project_number=project_number,
                    project_owner=project_owner,
                    field_names=field_names,
                )
            )
            if limit is not None and len(collected) >= limit:
                return collected
        if next_cursor is None:
            return collected
        cursor = next_cursor


def _read_list_page(
    data: Mapping, page_number: int, owner: str, repo: str, *, after: str | None
) -> tuple[list, str | None]:
    """``(nodes, next cursor)`` of one list page, or a :class:`GraphQLError`.

    The next cursor is ``None`` on the last page and a non-empty string
    otherwise. Every container on the way down is checked, not only the first:
    checking ``repository`` alone moves the empty page one level down, to
    ``issues: {}``. A next page with no cursor to fetch it by is the same list
    cut short, and a cursor that does not move past ``after`` fetches the same
    page for ever.
    """

    def refuse(what: str) -> GraphQLError:
        return _list_page_error(page_number, owner, repo, what)

    repository = data.get("repository")
    if not isinstance(repository, dict):
        raise refuse("the response carries no repository object")
    issues = repository.get("issues")
    if not isinstance(issues, dict):
        raise refuse("the repository object carries no issues connection")
    nodes = issues.get("nodes")
    if not isinstance(nodes, list):
        raise refuse("issues.nodes is not a list")
    page = issues.get("pageInfo")
    if not isinstance(page, dict) or not isinstance(page.get("hasNextPage"), bool):
        raise refuse("issues.pageInfo carries no hasNextPage")
    if not page["hasNextPage"]:
        return nodes, None
    cursor = page.get("endCursor")
    if not (isinstance(cursor, str) and cursor):
        raise refuse("hasNextPage is true but there is no endCursor to fetch it by")
    if cursor == after:
        raise refuse("endCursor did not advance past the page it was read from")
    return nodes, cursor


def _list_page_error(page_number: int, owner: str, repo: str, what: str) -> GraphQLError:
    """The one spelling of "this list page could not be read", for pages and nodes alike."""
    return GraphQLError(
        ["api", "graphql"], f"issue list page {page_number} of {owner}/{repo}: {what}"
    )


def _describe(value: object) -> str:
    """Name a value that was not the object expected, without echoing it."""
    if value is None:
        return "null"
    if value == {}:
        return "empty object"
    return type(value).__name__


def _is_board_not_found(exc: GhError, root: str) -> bool:
    """Whether every error behind ``exc`` is a NOT_FOUND on ``root``'s board.

    Read from ``type`` and ``path``, not from the message: GitHub rewording
    "Could not resolve to a ProjectV2 …" must not quietly turn "not found" back
    into "could not be resolved". The path keeps the account's own NOT_FOUND
    (``[root]`` — not an organization, not a user) out; any other error beside
    it makes the answer something else, and no structure at all is no answer.
    """
    errors = _graphql_errors(exc)
    return bool(errors) and all(
        isinstance(error, dict)
        and error.get("type") == "NOT_FOUND"
        and error.get("path") == [root, "projectV2"]
        for error in errors
    )


def _is_configured_board(
    project: Mapping, project_number: int, project_owner: str | None
) -> bool:
    """Whether a ``projectItems`` node's project is the configured board.

    The number must match, and so must the owner's login when ``project_owner``
    is given — exactly, case aside. An owner that cannot be read never matches.
    """
    if project.get("number") != int(project_number):
        return False
    if project_owner is None:
        return True
    # Logins are case-insensitive on GitHub; the config and the API may spell
    # one differently. Not `_label_key`: that folds separators, and `a-b` and
    # `ab` are two accounts.
    login = (project.get("owner") or {}).get("login")
    return isinstance(login, str) and _normalize(login) == _normalize(project_owner)


def _shape_issue_node(
    node: Mapping,
    *,
    project_number: int | None,
    field_names: Mapping[str, str],
    project_owner: str | None = None,
) -> dict:
    """Shape one issue node into the observed-metadata dict.

    The single shaper: both the one-issue query and the list query select the
    same fields and go through here — except the parent and blockers, which only
    :func:`read_issue_meta` selects and :func:`_shape_links` adds. It was briefly duplicated, which put the
    project-item selection rule in two places with two sets of tests.

    An item is the board's when its number matches and, if ``project_owner`` is
    given, so does its owner's login. Numbers are per owner: matching on the
    number alone read — and let ``set-fields`` write — a same-numbered board of
    another owner. With ``project_owner`` given, an item whose owner cannot be
    read does not match; passing it would be that same wrong-board read with the
    check switched off.
    """
    labels = [n["name"] for n in (node.get("labels") or {}).get("nodes") or [] if n]
    item = None
    for candidate in (node.get("projectItems") or {}).get("nodes") or []:
        if not candidate:
            continue
        if project_number is None or _is_configured_board(
            candidate.get("project") or {}, project_number, project_owner
        ):
            item = candidate
            break
    project: dict | None = None
    if item is not None:
        values: dict[str, str] = {}
        for value in (item.get("fieldValues") or {}).get("nodes") or []:
            name = (value or {}).get("name")
            field_name = ((value or {}).get("field") or {}).get("name")
            if name and field_name:
                values[_normalize(field_name)] = name
        project = {"item_id": item["id"], "fields": values}
        for slot, field_name in field_names.items():
            project[slot] = values.get(_normalize(field_name))
    return {
        "number": node["number"],
        "title": node["title"],
        "node_id": node["id"],
        "url": node["url"],
        "type": (node.get("issueType") or {}).get("name"),
        "labels": labels,
        "project": project,
    }


# ── Layer 4: writes ──────────────────────────────────────────────────────────


def create_issue(
    owner: str,
    repo: str,
    *,
    title: str,
    body: str,
    issue_type: str | None = None,
    labels: Sequence[str] = (),
    run: Run | None = None,
) -> dict:
    """Create an issue over REST; return ``{number, node_id, url}``.

    REST rather than GraphQL because ``type`` is a first-class field on the REST
    create payload, and the body arrives on stdin so a plan of any size (and any
    quoting) reaches the API untouched.
    """
    payload: dict[str, object] = {"title": title, "body": body}
    if labels:
        payload["labels"] = list(labels)
    if issue_type:
        payload["type"] = issue_type
    out = _run(run)(
        ["api", f"repos/{owner}/{repo}/issues", "-X", "POST", "--input", "-"],
        stdin=json.dumps(payload),
    )
    created = json.loads(out)
    return {
        "number": created["number"],
        "node_id": created["node_id"],
        "url": created["html_url"],
    }


_ADD_ITEM_MUTATION = """
  mutation($project:ID!,$content:ID!){
    addProjectV2ItemById(input:{projectId:$project, contentId:$content}){
      item { id }
    }
  }
"""

_SET_OPTION_MUTATION = """
  mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project, itemId:$item, fieldId:$field,
      value:{singleSelectOptionId:$option}
    }){ projectV2Item { id } }
  }
"""


def ensure_project_item(
    project_id: str, content_node_id: str, *, run: Run | None = None
) -> str:
    """Add an issue to a project and return its item id. Idempotent.

    ``addProjectV2ItemById`` returns the existing item when the issue is already
    on the board, so this is safe to call on an issue a project automation has
    already picked up.

    An answer without the item's id is an add that cannot be shown to have
    happened. It used to escape as an ``AttributeError`` — after the issue had
    been created, past every handler — or as a ``KeyError`` whose whole message
    was ``'id'``; an empty id went on to be written against.
    """
    data = _graphql(
        _ADD_ITEM_MUTATION, {"project": project_id, "content": content_node_id}, run=run
    )
    result = data.get("addProjectV2ItemById")
    item = result.get("item") if isinstance(result, dict) else None
    item_id = item.get("id") if isinstance(item, dict) else None
    # Stricter than `set_single_select`, which only needs its answer to exist:
    # this id is sent on as the next mutation's variable.
    if not (isinstance(item_id, str) and item_id.strip()):
        raise GraphQLError(
            ["api", "graphql"],
            "addProjectV2ItemById returned no item id; the issue was not confirmed "
            "added to the project",
        )
    return item_id


def set_single_select(
    project_id: str, item_id: str, field_id: str, option_id: str, *, run: Run | None = None
) -> None:
    """Write one single-select field value on one project item.

    The mutation answers with the item it wrote. An answer without it is a write
    that cannot be shown to have happened, and discarding the response — what
    this did — reported it as done.
    """
    data = _graphql(
        _SET_OPTION_MUTATION,
        {"project": project_id, "item": item_id, "field": field_id, "option": option_id},
        run=run,
    )
    result = data.get("updateProjectV2ItemFieldValue")
    item = result.get("projectV2Item") if isinstance(result, dict) else None
    if not (isinstance(item, dict) and item.get("id")):
        raise GraphQLError(
            ["api", "graphql"],
            "updateProjectV2ItemFieldValue returned no item; the value was not confirmed written",
        )


_ADD_SUB_ISSUE_MUTATION = """
  mutation($parent:ID!,$child:ID!){
    addSubIssue(input:{issueId:$parent, subIssueId:$child}){
      issue { id }
      subIssue { id }
    }
  }
"""

_ADD_BLOCKED_BY_MUTATION = """
  mutation($issue:ID!,$blocker:ID!){
    addBlockedBy(input:{issueId:$issue, blockingIssueId:$blocker}){
      issue { id }
      blockingIssue { id }
    }
  }
"""


def add_sub_issue(parent_id: str, child_id: str, *, run: Run | None = None) -> None:
    """Link ``child_id`` under ``parent_id``. Never replaces an existing parent.

    ``replaceParent`` is deliberately not sent: a child already under another
    parent is refused before this is called, and the server refuses it here too
    rather than detaching the child silently.
    """
    data = _graphql(_ADD_SUB_ISSUE_MUTATION, {"parent": parent_id, "child": child_id}, run=run)
    result = data.get("addSubIssue")
    linked = result.get("subIssue") if isinstance(result, dict) else None
    if not (isinstance(linked, dict) and linked.get("id") == child_id):
        raise GraphQLError(
            ["api", "graphql"], "addSubIssue returned no sub-issue; the link was not confirmed"
        )


def add_blocked_by(issue_id: str, blocker_id: str, *, run: Run | None = None) -> None:
    """Record that ``issue_id`` is blocked by ``blocker_id``."""
    data = _graphql(_ADD_BLOCKED_BY_MUTATION, {"issue": issue_id, "blocker": blocker_id}, run=run)
    result = data.get("addBlockedBy")
    blocker = result.get("blockingIssue") if isinstance(result, dict) else None
    if not (isinstance(blocker, dict) and blocker.get("id") == blocker_id):
        raise GraphQLError(
            ["api", "graphql"], "addBlockedBy returned no blocking issue; the link was not confirmed"
        )


def apply_field_values(
    fields: ProjectFields,
    item_id: str,
    values: Mapping[str, str],
    *,
    run: Run | None = None,
) -> dict[str, str]:
    """Write ``{field name: option name}`` onto a project item.

    Returns what was written. Raises :class:`FieldNotFoundError` /
    :class:`OptionNotFoundError` **before** any mutation for a name the project
    does not have, so a typo in one of two fields does not leave the other half
    written.
    """
    resolved = [
        (fields.field(name).id, fields.field(name).option_id(option))
        for name, option in values.items()
        if option
    ]  # every name resolved before the first write, so a typo in the second
       # value cannot leave the first one written
    for field_id, option_id in resolved:
        set_single_select(fields.project_id, item_id, field_id, option_id, run=run)
    return {name: option for name, option in values.items() if option}


# ── Layer 5: command registration ────────────────────────────────────────────
#
# Registration is pure: it builds parsers and returns. Every option is validated
# inside a handler, because `--help` builds this tree on a host with no network,
# no `gh` and no credentials, and a consuming project's
# `test_every_command_builds_help` is an offline test.


def _observed_from_meta(meta: Mapping, slots: Iterable[str], *, links: bool = False) -> dict:
    """The requested-vs-observed view of one issue's metadata.

    ``links`` adds the parent and blockers — only when they were asked for, so
    a command that did not touch them reports exactly what it did before.
    """
    project = meta.get("project") or {}
    observed = {"type": meta.get("type"), "labels": list(meta.get("labels") or [])}
    for slot in slots:
        observed[slot] = project.get(slot)
    if links:
        observed["parent"] = meta["parent"]
        observed["blocked_by"] = list(meta["blocked_by"])
    return observed


def _mismatches(requested: Mapping, observed: Mapping) -> list[str]:
    """Sentences for each requested value the read-back did not confirm.

    Labels are a *superset* check: a repository default label or an automation
    may add one, which is worth reporting but is not a failure to apply what was
    asked. Every other slot is exact.

    Labels also compare by label identity — :func:`_normalize`, case folded —
    where every other slot records the board's spelling and compares exactly.
    The difference is where the canonical spelling lives. An option's is on the
    board, which the command has already read; a label's is on the repository,
    which it has not. GitHub keeps label names unique regardless of case and
    attaches its existing ``BE`` to a request for ``be``, so a case difference
    here is never a label that failed to apply — reporting it as one put two
    drift sentences on every such create. Separators still count: ``B-E`` and
    ``BE`` are two labels, which is why this is not :func:`_label_key`.
    """
    drift: list[str] = []
    for key, want in requested.items():
        if want in (None, "", []):
            continue
        got = observed.get(key)
        if key == "labels":
            wanted_keys = {_normalize(label) for label in want}
            got_keys = {_normalize(label) for label in (got or [])}
            # One sentence entry per label, not per spelling of it: `--label be
            # --label BE` asked for one label. The first spelling is kept.
            missing = _first_per_label(label for label in want if _normalize(label) not in got_keys)
            extra = _first_per_label(
                label for label in (got or []) if _normalize(label) not in wanted_keys
            )
            if missing:
                drift.append(f"labels requested but not applied: {missing}")
            if extra:
                drift.append(f"labels present but not requested: {extra}")
        elif key == "blocked_by":
            # Only what was asked for: an issue may rightly carry other blockers,
            # and one set earlier is not drift of this request. Order is ignored.
            missing = [number for number in want if number not in (got or [])]
            if missing:
                drift.append(f"blocked_by requested but not linked: {missing}")
        elif got != want:
            drift.append(f"{key}: requested {want!r}, observed {got!r}")
    return drift


def _canonical_labels(labels: Sequence[str], allowed_labels: Iterable[str] | None) -> list[str]:
    """The spelling ``create-issue`` records for each label it asked for.

    With ``allowed_labels`` declared, the declared spelling — the one stage one
    matched, and the only canonical spelling this command knows before the
    create. Only the *record* changes: the labels are sent as typed, because
    rewriting what goes out is the conversion :func:`reserved_label_violations`
    refuses to do. Without a declared list there is no canonical spelling to
    record, and the typed one stands.

    The first declaration of a name wins, surrounding whitespace is not part of
    it, and two requests for one label are recorded once.
    """
    if allowed_labels is None:
        return list(labels)
    canonical: dict[str, str] = {}
    for declared in allowed_labels:
        canonical.setdefault(_normalize(declared), declared.strip())
    return list(dict.fromkeys(canonical.get(_normalize(label), label) for label in labels))


def _first_per_label(labels: Iterable[str]) -> list[str]:
    """Labels in order, one per label identity, each in its first spelling."""
    seen: dict[str, str] = {}
    for label in labels:
        seen.setdefault(_normalize(label), label)
    return list(seen.values())


def _resolve_body(body_file: str) -> str:
    """Read a body file, re-rooting a relative path at the main worktree.

    The plan file the body comes from lives in gitignored ``.task/plan/``, which
    exists only in the main checkout — a relative path typed from a linked
    worktree must not resolve against CWD.
    """
    return abs_under_main(Path(body_file)).read_text(encoding="utf-8")


def _field_slots(field_names: Mapping[str, str]) -> dict[str, str]:
    """``{slot: field name}`` for the writable slots plus status.

    ``status`` is included so reads can report it; the write paths pick the
    slots they are allowed to touch out of this map rather than re-deriving it.

    Each slot falls back to :data:`DEFAULT_FIELD_NAMES`, which is what the
    documented schema promises ("생략 시 Priority / Size") and what the starter
    template relies on by passing ``field_names`` through as ``{}``. Without the
    fallback, following the documented schema produced a ``KeyError`` from the
    very command the failure message tells the caller to run.
    """
    return {
        slot: (field_names.get(slot) or default)
        for slot, default in DEFAULT_FIELD_NAMES.items()
    }


def _writable_slots(field_names: Mapping[str, str]) -> dict[str, str]:
    """The slots a command may write. Never ``status`` — see ``set-fields``."""
    return {
        slot: name for slot, name in _field_slots(field_names).items() if slot != "status"
    }


def _issue_number(value: str) -> int:
    """argparse ``type=`` for ``--parent``/``--blocked-by``: a positive number in
    this repository. ``owner/repo#N`` and URLs are refused — links are
    same-repository only."""
    if not (value.isascii() and value.isdigit()) or int(value) < 1:
        shown = value if len(value) <= 40 else value[:40] + "…"
        raise argparse.ArgumentTypeError(f"not an issue number in this repository: {shown!r}")
    return int(value)


# Pieces `set-fields` repairs when run again with the same flag. The rest cannot
# be repaired by it: it never writes Status, adds a board item only to write a
# field, and a failed read-back is fixed by reading, not writing.
_REPAIR_FLAGS = {"type": "--type", "priority": "--priority", "size": "--size", "parent": "--parent"}
_NOT_REPAIRABLE_HINTS = {
    "project_item": "add the issue to the board",
    "status": "set its Status on the board; set-fields never writes Status",
    "read_back": "read it with get-issue",
}


def _repair_report(number: int, failures: Sequence[tuple[str, str]], values: Mapping[str, object]) -> dict:
    """What an ``INCOMPLETE`` report says, as data. Never an exit code.

    ``failures`` is ``(piece, message)`` in the order the writes ran; a piece is
    ``type``, ``project_item``, ``status``, ``priority``, ``size``, ``parent``,
    ``blocked_by:#<N>`` or ``read_back``. The recovery line carries only the
    pieces that failed and that ``set-fields`` can repair, quoted for the shell;
    it is ``None`` when there are none. ``values`` holds what each repairable
    piece asked for.
    """
    argv = ["set-fields", str(number)]
    unrepairable: list[str] = []
    for piece, _ in failures:
        if piece in _REPAIR_FLAGS:
            argv += [_REPAIR_FLAGS[piece], str(values[piece])]
        elif piece.startswith("blocked_by:#"):
            argv += ["--blocked-by", piece.split("#", 1)[1]]
        else:
            unrepairable.append(piece)
    # `set-fields` adds the board item itself when it writes a field.
    if "project_item" in unrepairable and any(p in ("priority", "size") for p, _ in failures):
        unrepairable.remove("project_item")
    return {
        "errors": [{"piece": piece, "error": message} for piece, message in failures],
        "recovery": shlex.join(argv) if len(argv) > 2 else None,
        "unrepairable": unrepairable,
    }


def _repair_lines(number: int, report: Mapping) -> list[str]:
    lines = []
    if report["recovery"]:
        lines += ["Repair it in place:", f"  {report['recovery']}"]
    for piece in report["unrepairable"]:
        hint = _NOT_REPAIRABLE_HINTS.get(piece, "repair it by hand")
        if piece == "read_back":
            hint = f"{hint} {number}"
        lines.append(f"Not repairable by set-fields {number} — {piece}: {hint}")
    return lines


def _link_targets(owner: str, repo: str, parent: int | None, blockers: Sequence[int]) -> tuple[dict | None, list[tuple[int, dict]], list[str]]:
    """Look up every link target before the first write.

    Returns the parent's target, each blocker's, and the warnings to report
    (a closed target is linked, not refused). Raises :class:`LinkTargetError`
    for a target that does not exist, is a pull request or cannot be read. The
    sub-issue cap is the caller's: a parent the issue is already under is not
    one it is being added to.
    """
    warnings: list[str] = []
    parent_target = None
    if parent is not None:
        parent_target = read_link_target(owner, repo, parent)
        if parent_target["state"] == "CLOSED":
            warnings.append(f"parent #{parent} is closed")
    blocker_targets = []
    for number in blockers:
        target = read_link_target(owner, repo, number)
        if target["state"] == "CLOSED":
            warnings.append(f"blocker #{number} is closed")
        blocker_targets.append((number, target))
    return parent_target, blocker_targets, warnings


def _truncated_blockers(drift: list[str], notes: list[str]) -> tuple[list[str], list[str]]:
    """With a blocker list longer than the page read, a requested blocker that
    is not shown is unknown, not missing: move it from drift into a note."""
    unknown = [d for d in drift if d.startswith("blocked_by requested but not linked")]
    note = "blocked_by: the issue has more blockers than one page reads; one not shown may be past it"
    return ([d for d in drift if d not in unknown],
            notes + [note] + [d.replace("requested but not linked", "not confirmed") for d in unknown])


def _refuse_full_parent(number: int, target: Mapping) -> None:
    """Raise when a parent this issue would be *added* to is at GitHub's cap."""
    if target["sub_issues"] >= SUB_ISSUE_LIMIT:
        raise LinkTargetError(number, "already has the most sub-issues GitHub allows",
                              str(target["sub_issues"]))


def _create_issue_handler(args) -> ExitCode:
    """Create one issue with its full metadata, then report what actually stuck.

    Returns ``OK``, ``REFUSED``, ``INCOMPLETE`` or ``UNKNOWN`` — a contract the
    skill depends on; what each means for this command is in
    ``skills/_shared/references/exit-codes.md``. ``--parent`` and
    ``--blocked-by`` link the new issue; their targets are looked up before the
    create, so a target that does not exist is ``REFUSED`` with nothing made. ``UNKNOWN`` exists because a
    failed create request does not say whether the issue exists: neither
    ``REFUSED`` nor ``INCOMPLETE`` can be claimed, as there is nothing to repair
    and nothing is safe to retry blind.

    Everything that can be checked without writing is checked first, including
    every option name, so a typo in the config is ``REFUSED`` rather than an
    issue that can never be created cleanly. Everything after the create is
    inside the ``INCOMPLETE`` guarantee — including the read-back, which is the
    call most likely to fail, since it runs last and GitHub can legitimately 404
    an issue it has just created. Every piece after the create is attempted even
    when an earlier one failed, and the failures are reported together, with a
    ``set-fields`` line that repairs only what failed.

    "Checked without writing" includes reading the project's field options, and
    that read is a precondition rather than a step of joining the board: it is
    what tells a label apart from a field value. A board that cannot be read is
    therefore ``REFUSED``, not a create judged against an empty option set — the
    empty set is exactly what let ``--label P1`` through.
    """
    config = args.github
    owner, repo = config["owner"], config["repo"]
    project_number = config["project_number"]
    field_names = config["field_names"]
    slots = _field_slots(field_names)
    writable = _writable_slots(field_names)
    labels = list(args.label or [])
    wants_project = not args.no_project and project_number is not None

    if args.no_project and (args.priority or args.size):
        args._parser.error(
            "--no-project cannot be combined with --priority/--size: "
            "those are project fields"
        )
    blockers = list(dict.fromkeys(args.blocked_by or []))
    if args.parent is not None and args.parent in blockers:
        args._parser.error(f"#{args.parent} cannot be both the parent and a blocker")

    # Stage one: no network. A label the project does not allow is rejected
    # before anything exists to clean up.
    violations = reserved_label_violations(
        labels,
        allowed_labels=config["allowed_labels"],
        reserved_patterns=config["reserved_patterns"],
    )
    if violations:
        print_error("\n".join(violations))
        return ExitCode.REFUSED
    # Worked out now, not after the create: past that point nothing may raise.
    requested_labels = _canonical_labels(labels, config["allowed_labels"])

    # No `except GhError`: `repo_issue_type_names` turns a failed read into None,
    # which the next line already refuses on. Catching it as well was dead code.
    type_names = repo_issue_type_names(owner, repo)
    if type_names is None:
        # Proceeding would silently create an untyped issue and report success.
        print_error(
            f"could not read the issue types of {owner}/{repo}; refusing to create an "
            f"issue whose type cannot be verified"
        )
        return ExitCode.REFUSED

    # Read the board whenever one is configured *and* the read can change an
    # outcome — there are labels to judge, or this issue is joining the board.
    # `--no-project` does not excuse the read: a priority option belongs to the
    # priority field whether or not this issue joins, and skipping the read used
    # to leave `option_names={}`, which is not a degraded check but the check
    # answering "nothing is reserved". With no labels and no registration there
    # is nothing the board's options could decide, and failing the command on a
    # read whose result it would discard blocks the one escape (`--no-project`)
    # that a repo with an unreadable board has left.
    fields = None
    option_names: dict[str, list[str]] = {}
    if project_number is not None and (labels or wants_project):
        try:
            fields = ProjectFields.load(config["project_owner"], project_number)
        except (GhError, FieldNotFoundError) as exc:
            print_error(
                f"could not read the fields of project #{project_number}: {exc}; "
                f"refusing to create an issue whose labels cannot be checked "
                f"against them"
            )
            return ExitCode.REFUSED
        # Status options join the derivation: `in-progress` as a label is the
        # same drift as `P1` as a label, and it is the one the skills used to
        # instruct directly.
        option_names = fields.option_names(slots.values())

    # Stage two: the names that already have a home of their own.
    violations = reserved_label_violations(
        labels, type_names=type_names, option_names=option_names
    )
    if violations:
        print_error("\n".join(violations))
        return ExitCode.REFUSED

    issue_type = args.type
    if issue_type:
        match = next((t for t in type_names if _normalize(t) == _normalize(issue_type)), None)
        if match is None:
            print_error(
                f"issue type {issue_type!r} is not defined on {owner}/{repo}; "
                f"available: {', '.join(type_names) or '(none)'}"
            )
            return ExitCode.REFUSED
        issue_type = match

    # Resolve every option name now. These are all knowable before the write,
    # and a config typo that is only caught afterwards creates an issue on every
    # single invocation, forever, while telling the caller not to retry.
    initial_status = config["initial_status"] if wants_project else None
    # `fields` is the schema, read for the judgement above. `board` is the thing
    # this issue is written to, which `--no-project` turns off. They were one
    # name, and folding them back together puts a `--no-project` issue on the
    # board — every write below hangs off `board`.
    board = fields if wants_project else None
    pending: list[tuple[str, str, str]] = []
    # The board's own spelling of each value, which is what the read-back reports.
    resolved: dict[str, str] = {}
    if board is not None:
        try:
            if initial_status:
                status_field = board.field(slots["status"])
                option_id, resolved["status"] = status_field.option(initial_status)
                pending.append(("status", status_field.id, option_id))
            for slot, value in (("priority", args.priority), ("size", args.size)):
                if value:
                    field = board.field(writable[slot])
                    option_id, resolved[slot] = field.option(value)
                    pending.append((slot, field.id, option_id))
        except (FieldNotFoundError, OptionNotFoundError) as exc:
            print_error(str(exc))
            return ExitCode.REFUSED

    try:
        body = _resolve_body(args.body_file)
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"--body-file could not be read: {exc}")
        return ExitCode.REFUSED

    # Link targets last among the checks: they are the only ones that name other
    # issues, and each costs a query. Still before the create — a target that
    # does not exist is a refusal, not an issue left half-linked.
    try:
        parent_target, blocker_targets, link_warnings = _link_targets(owner, repo, args.parent, blockers)
        if parent_target is not None:
            _refuse_full_parent(args.parent, parent_target)
    except LinkTargetError as exc:
        print_error(f"cannot link: {exc}; nothing was created")
        return ExitCode.REFUSED
    for warning in link_warnings:
        print_error(f"warning: {warning}")

    try:
        created = create_issue(
            owner, repo, title=args.title, body=body, issue_type=issue_type, labels=labels
        )
    except (GhError, LookupError, ValueError) as exc:
        # A failed create does not say whether the issue exists. `gh` exits
        # non-zero both for a 422 the server rejected and for a connection lost
        # after the 201 was written; a response this module cannot parse means
        # the create landed and the number was lost. Calling that 2 would assert
        # "nothing exists; fix the argument and run it again", and the re-run
        # files a second issue carrying the same plan body. Uncaught — which is
        # what this was — it left as exit 1, which the skill has no rule for at
        # all, so the re-run happened anyway.
        print_error(
            f"the create request failed and it is not known whether the issue "
            f"exists: {exc}\n"
            f"Do not retry blind: search {owner}/{repo} for an issue titled "
            f"{args.title!r} first."
        )
        return ExitCode.UNKNOWN

    # ── Past this point the issue exists. Nothing below may raise. ────────────
    # The board's spelling where there was a board to ask, the caller's where
    # there was not. Recording the value either way is what puts an unapplied
    # field into `drift`; dropping the key would report a silent absence as if
    # nothing had been asked for.
    requested: dict[str, object] = {"type": issue_type, "labels": requested_labels}
    if initial_status:
        requested["status"] = resolved.get("status", initial_status)
    for slot, value in (("priority", args.priority), ("size", args.size)):
        if value:
            requested[slot] = resolved.get(slot, value)
    links = args.parent is not None or bool(blockers)
    if args.parent is not None:
        requested["parent"] = args.parent
    if blockers:
        requested["blocked_by"] = sorted(blockers)

    notes: list[str] = list(link_warnings)
    if args.no_project:
        notes.append("--no-project: the issue was not added to any project")
    elif project_number is None:
        notes.append("no project configured for this repo; no project field was set")

    # Every piece is attempted; one failing does not stop the next. Stopping at
    # the first left later pieces unwritten *and* unreported — the repair then
    # fixed only what it was told about.
    failures: list[tuple[str, str]] = []
    if board is not None:
        item_id = None
        try:
            item_id = ensure_project_item(board.project_id, created["node_id"])
        except (GhError, KeyError, ValueError) as exc:
            failures.append(("project_item", str(exc)))
        for slot, field_id, option_id in pending:
            if item_id is None:
                failures.append((slot, "skipped: the issue is not on the board"))
                continue
            try:
                set_single_select(board.project_id, item_id, field_id, option_id)
            except (GhError, KeyError, ValueError) as exc:
                failures.append((slot, str(exc)))
    if parent_target is not None:
        try:
            add_sub_issue(parent_target["node_id"], created["node_id"])
        except (GhError, KeyError, ValueError) as exc:
            failures.append(("parent", str(exc)))
    for number, target in blocker_targets:
        try:
            add_blocked_by(created["node_id"], target["node_id"])
        except (GhError, KeyError, ValueError) as exc:
            failures.append((f"blocked_by:#{number}", str(exc)))

    def _observe() -> dict:
        meta = read_issue_meta(
            owner,
            repo,
            created["number"],
            project_number=project_number,
            project_owner=config["project_owner"],
            field_names=slots,
        )
        return meta

    meta = observed = None
    drift: list[str] = []
    try:
        meta = _observe()
        observed = _observed_from_meta(meta, slots, links=links)
        drift = _mismatches(requested, observed)
        if drift and not failures:
            # One re-read: a project automation writing Status can land after the
            # create response, and reporting that race as drift trains the reader
            # to ignore the field that matters. After a failure the drift is
            # expected, so there is nothing to wait for.
            meta = _observe()
            observed = _observed_from_meta(meta, slots, links=links)
            drift = _mismatches(requested, observed)
    except (GhError, LookupError, ValueError) as exc:
        failures.append(("read_back", str(exc)))
        # Drift from an earlier read beside `observed: null` would say two
        # things about links nobody could confirm.
        meta, observed, drift = None, None, []
    if meta is not None and links and meta.get("blocked_by_truncated"):
        drift, notes = _truncated_blockers(drift, notes)

    def _incomplete() -> ExitCode:
        report = _repair_report(
            created["number"], failures, {**requested, **{k: v for k, v in (("priority", args.priority), ("size", args.size)) if v}}
        )
        print_error(
            "\n".join(
                [f"the issue was created but its metadata is not complete: {failures[0][1]}",
                 "Do not create it again."] + _repair_lines(created["number"], report)
            )
        )
        print_json(
            {
                **created,
                "title": meta["title"] if meta is not None else args.title,
                "requested": requested,
                "observed": observed,
                "drift": drift + notes,
                "error": failures[0][1],
                "errors": report["errors"],
            }
        )
        return ExitCode.INCOMPLETE

    if failures:
        return _incomplete()
    print_json(
        {
            **created,
            "title": meta["title"],
            "requested": requested,
            "observed": observed,
            "drift": drift + notes,
        }
    )
    return ExitCode.OK


def _get_issue_handler(args) -> ExitCode:
    """Print one issue's metadata.

    Returns ``OK`` or ``REFUSED`` (the issue or its metadata could not be read);
    see ``skills/_shared/references/exit-codes.md``.
    """
    config = args.github
    try:
        meta = read_issue_meta(
            config["owner"],
            config["repo"],
            args.number,
            project_number=config["project_number"],
            project_owner=config["project_owner"],
            field_names=_field_slots(config["field_names"]),
        )
    except (GhError, LookupError) as exc:
        print_error(str(exc))
        return ExitCode.REFUSED
    print_json({key: value for key, value in meta.items() if key not in _LINK_ID_KEYS})
    return ExitCode.OK


def _set_fields_handler(args) -> ExitCode:
    """Repair an existing issue's metadata. Never writes Status.

    Status belongs to the project's own automation once an item exists; a repair
    command that also reset it would undo a board state nobody asked it to
    touch. The before/after values are reported so the caller can see what the
    automation did with the item this command may have just added.

    This is the command ``create-issue`` sends its callers to on
    ``INCOMPLETE``, so it carries the same contract: everything resolvable is
    resolved before the first write (the type included — resolving it after the
    PATCH would let a bad ``--priority`` leave a changed type behind and still
    report "nothing happened"), so a refusal before it is ``REFUSED``, and a
    failure after the first write is ``INCOMPLETE`` rather than pretending
    nothing was applied. See ``skills/_shared/references/exit-codes.md``.

    ``--parent``/``--blocked-by`` link the issue, which is how an ``INCOMPLETE``
    create is finished. Identity is the node id: a parent already in place is
    success, another parent is ``REFUSED`` before any write (GitHub allows one),
    and a blocker already there is not written again. A request whose links are
    all in place and that asks nothing else is ``OK`` with a note rather than
    ``NOOP``: a repair caller reads success as success.
    """
    config = args.github
    owner, repo = config["owner"], config["repo"]
    project_number = config["project_number"]
    slots = _field_slots(config["field_names"])
    writable = _writable_slots(config["field_names"])
    blockers = list(dict.fromkeys(args.blocked_by or []))
    if args.number == args.parent or args.number in blockers:
        args._parser.error(f"#{args.number} cannot be linked to itself")
    if args.parent is not None and args.parent in blockers:
        args._parser.error(f"#{args.parent} cannot be both the parent and a blocker")
    links = args.parent is not None or bool(blockers)

    try:
        before = read_issue_meta(
            owner,
            repo,
            args.number,
            project_number=project_number,
            project_owner=config["project_owner"],
            field_names=slots,
        )
    except (GhError, LookupError) as exc:
        print_error(str(exc))
        return ExitCode.REFUSED

    requested: dict[str, object] = {}
    notes: list[str] = []

    # ── Resolve everything first. No write has happened yet. ─────────────────
    issue_type = None
    if args.type:
        # No `except GhError`: a failed read comes back as None. The third and
        # last copy of that dead catch.
        type_names = repo_issue_type_names(owner, repo)
        if type_names is None:
            print_error(f"could not read the issue types of {owner}/{repo}")
            return ExitCode.REFUSED
        issue_type = next(
            (t for t in type_names if _normalize(t) == _normalize(args.type)), None
        )
        if issue_type is None:
            print_error(
                f"issue type {args.type!r} is not defined on {owner}/{repo}; "
                f"available: {', '.join(type_names) or '(none)'}"
            )
            return ExitCode.REFUSED

    wanted = {slot: value for slot, value in
              (("priority", args.priority), ("size", args.size)) if value}
    fields = None
    pending: list[tuple[str, str, str]] = []
    # The board's own spelling, for the same reason `create-issue` keeps it: the
    # read-back reports that spelling, so recording the caller's turned
    # `--priority p1` into drift against the option it had just matched.
    resolved: dict[str, str] = {}
    if wanted:
        if project_number is None:
            notes.append("priority/size not applied: no project configured for this repo")
        else:
            try:
                fields = ProjectFields.load(config["project_owner"], project_number)
                for slot, value in wanted.items():
                    field = fields.field(writable[slot])
                    option_id, resolved[slot] = field.option(value)
                    pending.append((slot, field.id, option_id))
            except (GhError, FieldNotFoundError, OptionNotFoundError, KeyError) as exc:
                print_error(str(exc))
                return ExitCode.REFUSED

    # Links: targets looked up, and the issue's own links judged by node id,
    # before the first write — another parent is a refusal, not a half repair.
    parent_target = None
    blocker_targets: list[tuple[int, dict]] = []
    if links:
        try:
            parent_target, blocker_targets, link_warnings = _link_targets(owner, repo, args.parent, blockers)
        except LinkTargetError as exc:
            print_error(f"cannot link: {exc}; nothing was changed")
            return ExitCode.REFUSED
        for warning in link_warnings:
            print_error(f"warning: {warning}")
        notes.extend(link_warnings)
        if parent_target is not None:
            requested["parent"] = args.parent
            current = before["parent_node_id"]
            if current == parent_target["node_id"]:
                notes.append(f"parent: already under #{args.parent}")
                parent_target = None
            elif current is None:
                try:
                    _refuse_full_parent(args.parent, parent_target)
                except LinkTargetError as exc:
                    print_error(f"cannot link: {exc}; nothing was changed")
                    return ExitCode.REFUSED
            else:
                shown = before["parent"]
                shown = f"#{shown}" if isinstance(shown, int) else shown
                print_error(
                    f"#{args.number} is already under {shown}; GitHub allows one parent, "
                    f"and this command does not replace it. Nothing was changed."
                )
                return ExitCode.REFUSED
        if blockers:
            requested["blocked_by"] = sorted(blockers)
            present = set(before["blocked_by_node_ids"])
            for number, target in list(blocker_targets):
                if target["node_id"] in present:
                    notes.append(f"blocked_by: #{number} already recorded")
                    blocker_targets.remove((number, target))

    # ── First write below this line. Every piece is attempted. ───────────────
    applied: list[str] = []
    failures: list[tuple[str, str]] = []
    if issue_type:
        requested["type"] = issue_type
        try:
            run_gh(
                ["api", f"repos/{owner}/{repo}/issues/{args.number}",
                 "-X", "PATCH", "--input", "-"],
                stdin=json.dumps({"type": issue_type}),
            )
            applied.append("type")
        except (GhError, ValueError, KeyError) as exc:
            failures.append(("type", str(exc)))
    if pending:
        requested.update(resolved)
        item_id = (before.get("project") or {}).get("item_id")
        if not item_id:
            # Adding the item is not setting its status: whatever the board's
            # automation assigns is the status, and it shows up in `after`.
            try:
                item_id = ensure_project_item(fields.project_id, before["node_id"])
                applied.append("project item")
            except (GhError, ValueError, KeyError) as exc:
                failures.append(("project_item", str(exc)))
        for slot, field_id, option_id in pending:
            if not item_id:
                failures.append((slot, "skipped: the issue is not on the board"))
                continue
            try:
                set_single_select(fields.project_id, item_id, field_id, option_id)
                applied.append(slot)
            except (GhError, ValueError, KeyError) as exc:
                failures.append((slot, str(exc)))
    if parent_target is not None:
        try:
            add_sub_issue(parent_target["node_id"], before["node_id"])
            applied.append("parent")
        except (GhError, ValueError, KeyError) as exc:
            failures.append(("parent", str(exc)))
    for number, target in blocker_targets:
        try:
            add_blocked_by(before["node_id"], target["node_id"])
            applied.append(f"blocked_by:#{number}")
        except (GhError, ValueError, KeyError) as exc:
            failures.append((f"blocked_by:#{number}", str(exc)))

    def _fail() -> ExitCode:
        report = _repair_report(
            args.number, failures,
            {"type": issue_type, **wanted, "parent": args.parent},
        )
        print_error(
            "\n".join(
                [f"#{args.number} was partially updated ({', '.join(applied) or 'nothing'} "
                 f"applied) and then failed: {failures[0][1]}"] + _repair_lines(args.number, report)
            )
        )
        print_json(
            {
                "number": args.number,
                "url": before["url"],
                "requested": requested,
                "observed": None,
                "applied": applied,
                "drift": notes,
                "error": failures[0][1],
                "errors": report["errors"],
            }
        )
        return ExitCode.INCOMPLETE

    if failures:
        return _fail()

    try:
        after = read_issue_meta(
            owner,
            repo,
            args.number,
            project_number=project_number,
            project_owner=config["project_owner"],
            field_names=slots,
        )
    except (GhError, LookupError) as exc:
        failures.append(("read_back", str(exc)))
        return _fail()

    observed = _observed_from_meta(after, slots, links=links)
    drift = _mismatches(requested, observed)
    if links and after.get("blocked_by_truncated"):
        drift, notes = _truncated_blockers(drift, notes)
    print_json(
        {
            "number": after["number"],
            "url": after["url"],
            "requested": requested,
            "observed": observed,
            "status_before": (before.get("project") or {}).get("status"),
            "status_after": (after.get("project") or {}).get("status"),
            "drift": drift + notes,
        }
    )
    return ExitCode.OK


def _audit_fields_handler(args) -> ExitCode:
    """List metadata drift across the repository's issues. Reads only.

    Degrades one axis at a time: an axis that cannot be read drops out of the
    judgement and is named in ``warnings``, so a half audit never reads as a
    clean bill of health. The issue list is the exception — with no issues read
    there is nothing to degrade *to*, so that one is ``REFUSED`` with an empty
    stdout.

    The JSON says what the audit found, and is the same with or without
    ``--fail-on-drift``. The exit code says whether the judgement is complete —
    ``INCOMPLETE`` when an axis could not be read, even when nothing was found,
    because "no drift on the axes that could be read" is not "no drift" — and,
    only with ``--fail-on-drift``, whether it found drift: ``FINDINGS``. Without
    the flag drift alone is ``OK``. What each member means here is in
    ``skills/_shared/references/exit-codes.md``.

    ``INCOMPLETE`` rather than ``OK`` because ``warnings`` is a field nobody
    reads. #19 made ``create-issue`` refuse a board it could not read, instead of
    creating the issue and naming the gap in ``drift``, on exactly that
    observation: callers branch on the exit code. A gate that checks
    ``with_drift`` turned green here over a read that never happened. Unlike
    ``create-issue``'s ``INCOMPLETE`` it is not a repair instruction: nothing
    was written, and the fix is whatever stopped the read.

    ``FINDINGS`` wins over ``INCOMPLETE`` when both hold: a CI that tolerates an
    incomplete audit (a token short of a scope) must not see a drift that was
    found turn green. ``warnings`` still names what was not read.
    """
    config = args.github
    slots = _field_slots(config["field_names"])
    # Declared above the first degradation that appends to it. It used to sit
    # below, so the one path designed to degrade — "audit labels only" — raised
    # UnboundLocalError instead of taking its fallback.
    warnings: list[str] = []
    option_names: dict[str, list[str]] = {}
    if config["project_number"] is not None:
        try:
            fields = ProjectFields.load(config["project_owner"], config["project_number"])
            # The option set `create-issue` judges against, Status included.
            # Deriving it from the *writable* slots instead left the audit blind
            # to the one label the write path rejects: `in-progress`. The two
            # commands are one judgement and must not take two different inputs.
            option_names = fields.option_names(slots.values())
        except (GhError, FieldNotFoundError) as exc:
            warnings.append(f"project fields could not be read: {exc}")
            print_error(f"project fields unavailable, auditing labels only: {exc}")

    # No `except GhError`: `repo_issue_type_names` returns None on a failed read,
    # which the next line already handles. Catching it as well was dead code.
    type_names = repo_issue_type_names(config["owner"], config["repo"])
    if type_names is None:
        # Reporting zero findings because half the contract could not be read is
        # the failure this command exists to prevent, one level up.
        warnings.append(
            "issue types could not be read: type/label duplication was NOT audited"
        )
        print_error(warnings[-1])

    try:
        issues = iter_issue_meta(
            config["owner"],
            config["repo"],
            project_number=config["project_number"],
            project_owner=config["project_owner"],
            field_names=slots,
            state=args.state,
            limit=args.limit,
        )
    except (GhError, LookupError, ValueError) as exc:
        owner, repo = config["owner"], config["repo"]
        # `_get_issue_handler` catches the same family for the same reads: a
        # malformed node raises LookupError out of `_shape_issue_node`, not
        # GhError. Repeat the degradations above, so a run that lost three axes
        # does not read as one failure. stdout stays empty — there is no audit.
        for warning in warnings:
            print_error(warning)
        print_error(f"could not list the issues of {owner}/{repo}: {exc}")
        return ExitCode.REFUSED
    findings = []
    for meta in issues:
        drift = field_drift(meta, option_names=option_names, type_names=type_names)
        if drift:
            findings.append({"number": meta["number"], "url": meta["url"], "drift": drift})
    print_json(
        {
            "scanned": len(issues),
            "with_drift": len(findings),
            "warnings": warnings,
            "issues": findings,
        }
    )
    if args.fail_on_drift and findings:
        return ExitCode.FINDINGS
    return ExitCode.INCOMPLETE if warnings else ExitCode.OK


def register_github_commands(
    sub,
    *,
    owner: str,
    repo: str,
    project_number: int | None = None,
    project_owner: str | None = None,
    initial_status: str | None = None,
    field_names: Mapping[str, str] | None = None,
    allowed_labels: Iterable[str] | None = None,
    reserved_patterns: Iterable[str] = (),
) -> None:
    """Register the GitHub tracker commands onto a subparsers action.

    Opt-in: the core parser never calls this. A project's ``project.py`` does,
    which is why every project constant arrives as an argument.

    Accepts both the core's guarded subparsers wrapper and a raw argparse
    ``_SubParsersAction`` — a project's ``project.py`` has its own ``main()``
    that builds a parser directly. A name this project already defines raises
    through the guarded wrapper (``DuplicateCommandError``); the raw action
    would silently overwrite, so prefer the guarded one.

    Args:
        owner: Repository owner (``<owner>/<repo>``).
        repo: Repository name.
        project_number: Projects V2 number. ``None`` disables every project-field
            path — commands still run and report the fields as not applied.
        project_owner: Login that owns the project, when it is not ``owner``.
        initial_status: Status option ``create-issue`` sets on a newly added
            item. ``None`` leaves the status to the board's automation.
        field_names: ``{slot: field name}`` for ``priority`` / ``size``, and
            optionally ``status``. The names are this project's constants.
        allowed_labels: The complete set of labels this project accepts, or
            ``None`` to check only ``reserved_patterns`` in stage one. Passing a
            partial set rejects the labels it forgot.
        reserved_patterns: Case-insensitive glob patterns that are never labels.
    """
    config = {
        "owner": owner,
        "repo": repo,
        "project_number": project_number,
        # `str`: an all-digit login read from YAML arrives as an int, and the
        # owner comparison and the board query both need the login as text.
        "project_owner": str(project_owner or owner),
        "initial_status": initial_status,
        "field_names": dict(field_names or {}),
        "allowed_labels": None if allowed_labels is None else list(allowed_labels),
        "reserved_patterns": tuple(reserved_patterns),
    }

    create = sub.add_parser("create-issue", help="Create an issue with type, labels and project fields")
    create.add_argument("--title", required=True)
    create.add_argument("--body-file", required=True)
    create.add_argument("--type")
    create.add_argument("--label", action="append", default=[])
    create.add_argument("--priority")
    create.add_argument("--size")
    create.add_argument(
        "--no-project", action="store_true", help="Do not add the issue to the project"
    )
    create.add_argument(
        "--parent", type=_issue_number, help="Link the new issue under this issue (same repository)"
    )
    create.add_argument(
        "--blocked-by", type=_issue_number, action="append", default=[],
        help="Record the new issue as blocked by this issue (same repository; repeatable)",
    )
    create.set_defaults(func=_create_issue_handler, github=config, _parser=create)

    get = sub.add_parser("get-issue", help="Read an issue's type, labels and project fields")
    get.add_argument("number", type=int)
    get.set_defaults(func=_get_issue_handler, github=config, _parser=get)

    repair = sub.add_parser(
        "set-fields", help="Repair an issue's type, project fields, parent and blockers"
    )
    repair.add_argument("number", type=int)
    repair.add_argument("--type")
    repair.add_argument("--priority")
    repair.add_argument("--size")
    repair.add_argument(
        "--parent", type=_issue_number, help="Link the issue under this issue (same repository)"
    )
    repair.add_argument(
        "--blocked-by", type=_issue_number, action="append", default=[],
        help="Record the issue as blocked by this issue (same repository; repeatable)",
    )
    repair.set_defaults(func=_set_fields_handler, github=config, _parser=repair)

    audit = sub.add_parser("audit-fields", help="List issues whose metadata drifted (read-only)")
    audit.add_argument("--state", choices=("open", "all"), default="open")
    audit.add_argument("--limit", type=int)
    audit.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="exit FINDINGS (6) when any issue drifted; see skills/_shared/references/exit-codes.md",
    )
    audit.set_defaults(func=_audit_fields_handler, github=config, _parser=audit)
