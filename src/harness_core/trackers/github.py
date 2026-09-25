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

import json
import subprocess
from dataclasses import dataclass, field as dataclass_field
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

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
    """A ``gh`` invocation exited non-zero.

    Carries the command and stderr so a handler can report *what* failed, which
    is the difference between "retry the fields" and "the issue was never made".
    """

    def __init__(self, argv: Sequence[str], returncode: int, stderr: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr.strip()
        # Name the command, not the payload. argv for a GraphQL call carries the
        # whole mutation document plus every node ID, and this string is echoed
        # into the JSON that impl-reports and issue comments quote verbatim.
        super().__init__(f"gh {' '.join(self.argv[:2])} exited {returncode}: {self.stderr}")


class FieldNotFoundError(LookupError):
    """A configured field name does not exist in the project."""


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
        raise GhError(argv, proc.returncode, proc.stderr)
    return proc.stdout


def _run(run: Run | None) -> Run:
    """Resolve the runner, looking up :func:`run_gh` at call time."""
    return run if run is not None else run_gh


def _graphql(
    query: str, variables: Mapping[str, object], *, run: Run | None = None
) -> dict:
    """Execute a GraphQL document and return its ``data`` object."""
    argv = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        # -F types the value (ints stay ints); -f keeps a string a string, which
        # matters for node IDs that would otherwise be coerced.
        flag = "-F" if isinstance(value, (int, bool)) and not isinstance(value, str) else "-f"
        argv += [flag, f"{key}={value}"]
    payload = json.loads(_run(run)(argv))
    return payload.get("data") or {}


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
        points are different, so a failed ``organization`` lookup is a signal to
        try ``user`` — not an error. Results are cached per process: a command
        that writes two fields resolves the project once.
        """
        key = (owner, int(number))
        if use_cache and key in _FIELDS_CACHE:
            return _FIELDS_CACHE[key]

        project = None
        last_error: GhError | None = None
        for root in ("organization", "user"):
            try:
                data = _graphql(
                    cls._QUERY % root, {"owner": owner, "number": int(number)}, run=run
                )
            except GhError as exc:
                # A login that is not an organization is expected to fail here;
                # keep the error anyway, because a missing `project` token scope
                # fails identically and needs a completely different fix.
                last_error = exc
                continue
            project = (data.get(root) or {}).get("projectV2")
            if project:
                break
        if not project:
            _FIELDS_CACHE.pop(key, None)
            detail = f" (last gh error: {last_error.stderr})" if last_error else ""
            raise FieldNotFoundError(
                f"project #{number} not found for owner {owner!r} as an organization "
                f"or a user{detail}"
            )

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

        resolved = cls(
            project_id=project["id"], number=int(number), owner=owner, fields=fields
        )
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
    repository = data.get("repository") or {}
    nodes = (repository.get("issueTypes") or {}).get("nodes") or []
    return [node["name"] for node in nodes if node and node.get("name")]


_ISSUE_META_QUERY = """
  query($owner:String!,$repo:String!,$number:Int!){
    repository(owner:$owner,name:$repo){
      issue(number:$number){
        number title id url
        issueType { name }
        labels(first:100){ nodes { name } }
        projectItems(first:20){
          nodes{
            id
            project { number }
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

    Returns:
        ``{number, title, node_id, url, type, labels, project}`` where ``project``
        is ``None`` when the issue is in no matching project, and otherwise
        ``{item_id, fields, <slot>: <option name or None>, ...}``.
    """
    data = _graphql(
        _ISSUE_META_QUERY,
        {"owner": owner, "repo": repo, "number": int(number)},
        run=run,
    )
    issue = (data.get("repository") or {}).get("issue")
    if not issue:
        raise LookupError(f"{owner}/{repo}#{number} not found")
    return _shape_issue_node(
        issue, project_number=project_number, field_names=field_names
    )


_LIST_ISSUES_QUERY = """
  query($owner:String!,$repo:String!,$state:IssueState,$cursor:String){
    repository(owner:$owner,name:$repo){
      issues(first:100, after:$cursor, states:$state,
             orderBy:{field:CREATED_AT, direction:DESC}){
        pageInfo { hasNextPage endCursor }
        nodes{
          number title id url
          issueType { name }
          labels(first:100){ nodes { name } }
          projectItems(first:20){
            nodes{
              id
              project { number }
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
    state: str = "open",
    limit: int | None = None,
    run: Run | None = None,
) -> list[dict]:
    """Read issue metadata page by page. Reads only — never mutates.

    Cursor pagination, because the 100-issue first page is exactly where an
    audit stops being an audit: a repository past that point would report a
    clean bill of health for the 101st issue onward.
    """
    if limit is not None and limit <= 0:
        return []
    # One state or none. The query declares `$state: IssueState` and wraps it in
    # the list position itself, so nothing here depends on GraphQL's
    # scalar-to-list coercion — and a future second state has to change the
    # query, which is where it would be noticed.
    wanted_state = None if state == "all" else state.upper()
    collected: list[dict] = []
    cursor: str | None = None
    while True:
        variables: dict[str, object] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        if wanted_state:
            variables["state"] = wanted_state
        data = _graphql(_LIST_ISSUES_QUERY, variables, run=run)
        issues = ((data.get("repository") or {}).get("issues")) or {}
        for node in issues.get("nodes") or []:
            if node:
                collected.append(
                    _shape_issue_node(node, project_number=project_number, field_names=field_names)
                )
                if limit is not None and len(collected) >= limit:
                    return collected
        page = issues.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return collected
        cursor = page.get("endCursor")
        if not cursor:
            return collected


def _shape_issue_node(
    node: Mapping, *, project_number: int | None, field_names: Mapping[str, str]
) -> dict:
    """Shape one issue node into the observed-metadata dict.

    The single shaper: both the one-issue query and the list query select the
    same fields and go through here. It was briefly duplicated, which put the
    project-item selection rule in two places with two sets of tests.
    """
    labels = [n["name"] for n in (node.get("labels") or {}).get("nodes") or [] if n]
    item = None
    for candidate in (node.get("projectItems") or {}).get("nodes") or []:
        if not candidate:
            continue
        if project_number is None or (candidate.get("project") or {}).get("number") == int(project_number):
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
    """
    data = _graphql(
        _ADD_ITEM_MUTATION, {"project": project_id, "content": content_node_id}, run=run
    )
    return ((data.get("addProjectV2ItemById") or {}).get("item") or {})["id"]


def set_single_select(
    project_id: str, item_id: str, field_id: str, option_id: str, *, run: Run | None = None
) -> None:
    """Write one single-select field value on one project item."""
    _graphql(
        _SET_OPTION_MUTATION,
        {"project": project_id, "item": item_id, "field": field_id, "option": option_id},
        run=run,
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


def _observed_from_meta(meta: Mapping, slots: Iterable[str]) -> dict:
    """The requested-vs-observed view of one issue's metadata."""
    project = meta.get("project") or {}
    observed = {"type": meta.get("type"), "labels": list(meta.get("labels") or [])}
    for slot in slots:
        observed[slot] = project.get(slot)
    return observed


def _mismatches(requested: Mapping, observed: Mapping) -> list[str]:
    """Sentences for each requested value the read-back did not confirm.

    Labels are a *superset* check: a repository default label or an automation
    may add one, which is worth reporting but is not a failure to apply what was
    asked. Every other slot is exact.
    """
    drift: list[str] = []
    for key, want in requested.items():
        if want in (None, "", []):
            continue
        got = observed.get(key)
        if key == "labels":
            missing = [label for label in want if label not in (got or [])]
            extra = [label for label in (got or []) if label not in want]
            if missing:
                drift.append(f"labels requested but not applied: {missing}")
            if extra:
                drift.append(f"labels present but not requested: {extra}")
        elif got != want:
            drift.append(f"{key}: requested {want!r}, observed {got!r}")
    return drift


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


def _create_issue_handler(args) -> int:
    """Create one issue with its full metadata, then report what actually stuck.

    Exit codes are a contract the skill depends on:

    - **0** — created; stdout carries the read-back.
    - **2** — refused *before* anything was created; stdout is empty.
    - **3** — the issue exists but its metadata is incomplete; stdout carries
      the number so the caller repairs it instead of creating a second one.
    - **4** — the create request failed without saying whether the issue exists.
      Neither 2 nor 3 can be claimed: there is nothing to repair and nothing is
      safe to retry blind.

    Everything that can be checked without writing is checked first, including
    every option name, so a typo in the config is a 2 rather than an issue that
    can never be created cleanly. Everything after the create is inside the
    exit-3 guarantee — including the read-back, which is the call most likely to
    fail, since it runs last and GitHub can legitimately 404 an issue it has
    just created.

    "Checked without writing" includes reading the project's field options, and
    that read is a precondition rather than a step of joining the board: it is
    what tells a label apart from a field value. A board that cannot be read is
    therefore a 2, not a create judged against an empty option set — the empty
    set is exactly what let ``--label P1`` through.
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

    # Stage one: no network. A label the project does not allow is rejected
    # before anything exists to clean up.
    violations = reserved_label_violations(
        labels,
        allowed_labels=config["allowed_labels"],
        reserved_patterns=config["reserved_patterns"],
    )
    if violations:
        print_error("\n".join(violations))
        return 2

    # No `except GhError`: `repo_issue_type_names` turns a failed read into None,
    # which the next line already refuses on. Catching it as well was dead code.
    type_names = repo_issue_type_names(owner, repo)
    if type_names is None:
        # Proceeding would silently create an untyped issue and report success.
        print_error(
            f"could not read the issue types of {owner}/{repo}; refusing to create an "
            f"issue whose type cannot be verified"
        )
        return 2

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
            return 2
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
        return 2

    issue_type = args.type
    if issue_type:
        match = next((t for t in type_names if _normalize(t) == _normalize(issue_type)), None)
        if match is None:
            print_error(
                f"issue type {issue_type!r} is not defined on {owner}/{repo}; "
                f"available: {', '.join(type_names) or '(none)'}"
            )
            return 2
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
    pending: list[tuple[str, str]] = []
    # The board's own spelling of each value, which is what the read-back reports.
    resolved: dict[str, str] = {}
    if board is not None:
        try:
            if initial_status:
                status_field = board.field(slots["status"])
                option_id, resolved["status"] = status_field.option(initial_status)
                pending.append((status_field.id, option_id))
            for slot, value in (("priority", args.priority), ("size", args.size)):
                if value:
                    field = board.field(writable[slot])
                    option_id, resolved[slot] = field.option(value)
                    pending.append((field.id, option_id))
        except (FieldNotFoundError, OptionNotFoundError) as exc:
            print_error(str(exc))
            return 2

    try:
        body = _resolve_body(args.body_file)
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"--body-file could not be read: {exc}")
        return 2

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
        return 4

    # ── Past this point the issue exists. Nothing below may raise. ────────────
    # The board's spelling where there was a board to ask, the caller's where
    # there was not. Recording the value either way is what puts an unapplied
    # field into `drift`; dropping the key would report a silent absence as if
    # nothing had been asked for.
    requested: dict[str, object] = {"type": issue_type, "labels": labels}
    if initial_status:
        requested["status"] = resolved.get("status", initial_status)
    for slot, value in (("priority", args.priority), ("size", args.size)):
        if value:
            requested[slot] = resolved.get(slot, value)

    notes: list[str] = []
    if args.no_project:
        notes.append("--no-project: the issue was not added to any project")
    elif project_number is None:
        notes.append("no project configured for this repo; no project field was set")

    def _fail(exc: Exception) -> int:
        print_error(
            f"the issue was created but its metadata is not complete: {exc}\n"
            f"Do not create it again. Repair it in place:\n"
            f"  set-fields {created['number']}"
        )
        print_json(
            {
                **created,
                "title": args.title,
                "requested": requested,
                "observed": None,
                "drift": notes,
                "error": str(exc),
            }
        )
        return 3

    try:
        if board is not None:
            item_id = ensure_project_item(board.project_id, created["node_id"])
            for field_id, option_id in pending:
                set_single_select(board.project_id, item_id, field_id, option_id)
    except (GhError, FieldNotFoundError, OptionNotFoundError, KeyError, ValueError) as exc:
        return _fail(exc)

    def _observe() -> dict:
        meta = read_issue_meta(
            owner,
            repo,
            created["number"],
            project_number=project_number,
            field_names=slots,
        )
        return meta

    try:
        meta = _observe()
        observed = _observed_from_meta(meta, slots)
        drift = _mismatches(requested, observed)
        if drift:
            # One re-read: a project automation writing Status can land after the
            # create response, and reporting that race as drift trains the reader
            # to ignore the field that matters.
            meta = _observe()
            observed = _observed_from_meta(meta, slots)
            drift = _mismatches(requested, observed)
    except (GhError, LookupError, ValueError) as exc:
        return _fail(exc)

    print_json(
        {
            **created,
            "title": meta["title"],
            "requested": requested,
            "observed": observed,
            "drift": drift + notes,
        }
    )
    return 0


def _get_issue_handler(args) -> int:
    config = args.github
    try:
        meta = read_issue_meta(
            config["owner"],
            config["repo"],
            args.number,
            project_number=config["project_number"],
            field_names=_field_slots(config["field_names"]),
        )
    except (GhError, LookupError) as exc:
        print_error(str(exc))
        return 2
    print_json(meta)
    return 0


def _set_fields_handler(args) -> int:
    """Repair an existing issue's metadata. Never writes Status.

    Status belongs to the project's own automation once an item exists; a repair
    command that also reset it would undo a board state nobody asked it to
    touch. The before/after values are reported so the caller can see what the
    automation did with the item this command may have just added.

    This is the command ``create-issue`` sends its callers to on exit 3, so it
    carries the same contract: everything resolvable is resolved before the
    first write (the type included — resolving it after the PATCH would let a
    bad ``--priority`` leave a changed type behind and still report "nothing
    happened"), and a failure after the first write exits 3 rather than
    pretending nothing was applied.
    """
    config = args.github
    owner, repo = config["owner"], config["repo"]
    project_number = config["project_number"]
    slots = _field_slots(config["field_names"])
    writable = _writable_slots(config["field_names"])

    try:
        before = read_issue_meta(
            owner, repo, args.number, project_number=project_number, field_names=slots
        )
    except (GhError, LookupError) as exc:
        print_error(str(exc))
        return 2

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
            return 2
        issue_type = next(
            (t for t in type_names if _normalize(t) == _normalize(args.type)), None
        )
        if issue_type is None:
            print_error(
                f"issue type {args.type!r} is not defined on {owner}/{repo}; "
                f"available: {', '.join(type_names) or '(none)'}"
            )
            return 2

    wanted = {slot: value for slot, value in
              (("priority", args.priority), ("size", args.size)) if value}
    fields = None
    pending: list[tuple[str, str]] = []
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
                    pending.append((field.id, option_id))
            except (GhError, FieldNotFoundError, OptionNotFoundError, KeyError) as exc:
                print_error(str(exc))
                return 2

    # ── First write below this line. ─────────────────────────────────────────
    def _fail(exc: Exception, applied: list[str]) -> int:
        print_error(
            f"#{args.number} was partially updated ({', '.join(applied) or 'nothing'} "
            f"applied) and then failed: {exc}"
        )
        print_json(
            {
                "number": args.number,
                "url": before["url"],
                "requested": requested,
                "observed": None,
                "applied": applied,
                "error": str(exc),
            }
        )
        return 3

    applied: list[str] = []
    try:
        if issue_type:
            run_gh(
                ["api", f"repos/{owner}/{repo}/issues/{args.number}",
                 "-X", "PATCH", "--input", "-"],
                stdin=json.dumps({"type": issue_type}),
            )
            requested["type"] = issue_type
            applied.append("type")
        if pending:
            item_id = (before.get("project") or {}).get("item_id")
            if not item_id:
                # Adding the item is not setting its status: whatever the board's
                # automation assigns is the status, and it shows up in `after`.
                item_id = ensure_project_item(fields.project_id, before["node_id"])
                applied.append("project item")
            requested.update(resolved)
            for field_id, option_id in pending:
                set_single_select(fields.project_id, item_id, field_id, option_id)
            applied.extend(wanted)
    except (GhError, ValueError, KeyError) as exc:
        return _fail(exc, applied)

    try:
        after = read_issue_meta(
            owner, repo, args.number, project_number=project_number, field_names=slots
        )
    except (GhError, LookupError) as exc:
        return _fail(exc, applied)

    observed = _observed_from_meta(after, slots)
    print_json(
        {
            "number": after["number"],
            "url": after["url"],
            "requested": requested,
            "observed": observed,
            "status_before": (before.get("project") or {}).get("status"),
            "status_after": (after.get("project") or {}).get("status"),
            "drift": _mismatches(requested, observed) + notes,
        }
    )
    return 0


def _audit_fields_handler(args) -> int:
    """List metadata drift across the repository's issues. Reads only.

    Degrades one axis at a time: an axis that cannot be read drops out of the
    judgement and is named in ``warnings``, so a half audit never reads as a
    clean bill of health. The issue list is the exception — with no issues read
    there is nothing to degrade *to*, so that one is a 2.
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
        return 2
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
    return 0


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
        "project_owner": project_owner or owner,
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
    create.set_defaults(func=_create_issue_handler, github=config, _parser=create)

    get = sub.add_parser("get-issue", help="Read an issue's type, labels and project fields")
    get.add_argument("number", type=int)
    get.set_defaults(func=_get_issue_handler, github=config, _parser=get)

    repair = sub.add_parser("set-fields", help="Repair an issue's type and project fields")
    repair.add_argument("number", type=int)
    repair.add_argument("--type")
    repair.add_argument("--priority")
    repair.add_argument("--size")
    repair.set_defaults(func=_set_fields_handler, github=config, _parser=repair)

    audit = sub.add_parser("audit-fields", help="List issues whose metadata drifted (read-only)")
    audit.add_argument("--state", choices=("open", "all"), default="open")
    audit.add_argument("--limit", type=int)
    audit.set_defaults(func=_audit_fields_handler, github=config, _parser=audit)
