"""Contract tests for the GitHub tracker adapter.

Every test here drives the real handler through the real parser, with only the
``gh`` boundary replaced. A fake at any higher level would test the fake.

The fixtures name nothing real: ``<owner>``-shaped placeholders, invented field
and option names. That is not cosmetic — ``tests/**`` is inside the
published-surface scan, and an adapter whose *tests* hardcode a project's option
names has moved the constant rather than removed it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from harness_core.cli import DuplicateCommandError, build_core_parser, dispatch, subparsers
from harness_core.trackers import github


# Placeholder project shape. These names exist only in this file.
TYPE_NAMES = ["Chore", "Defect", "Capability"]
PRIORITY_FIELD = "Urgency"
SIZE_FIELD = "Effort"
STATUS_FIELD = "Status"
PRIORITY_OPTIONS = ["U0", "U1", "U2"]
SIZE_OPTIONS = ["Tiny", "Small", "Large"]
STATUS_OPTIONS = ["Queued", "Doing", "Reviewing"]

FIELD_NAMES = {"priority": PRIORITY_FIELD, "size": SIZE_FIELD}
PROJECT_ID = "project-node-1"
STATUS_FIELD_ID = "field-status"


def _field(field_id: str, name: str, options: list[str]) -> dict:
    return {
        "id": field_id,
        "name": name,
        "options": [{"id": f"{field_id}-opt-{o}", "name": o} for o in options],
    }


PROJECT_FIELDS_PAYLOAD = {
    "id": PROJECT_ID,
    "fields": {
        "nodes": [
            _field(STATUS_FIELD_ID, STATUS_FIELD, STATUS_OPTIONS),
            _field("field-urgency", PRIORITY_FIELD, PRIORITY_OPTIONS),
            _field("field-effort", SIZE_FIELD, SIZE_OPTIONS),
            {"id": "field-text", "name": "Notes"},  # not single-select: ignored
        ]
    },
}


class FakeGh:
    """Records every ``gh`` invocation and answers from scripted responses.

    Routing is by what the call *is* — a GraphQL document is matched by the
    operation it names — so a test states the shape of the API conversation, not
    the order the handler happens to make the calls in.
    """

    def __init__(self, **responses):
        self.calls: list[dict] = []
        self.responses = responses
        self.failures: dict[str, Exception] = {}

    def fail(self, kind: str, exc: Exception) -> None:
        self.failures[kind] = exc

    def __call__(self, argv, *, stdin=None):
        argv = list(argv)
        kind = self._classify(argv)
        self.calls.append({"argv": argv, "stdin": stdin, "kind": kind})
        if kind in self.failures:
            raise self.failures[kind]
        value = self.responses.get(kind)
        if value is None:
            raise AssertionError(f"unscripted gh call ({kind}): {argv}")
        if callable(value):
            value = value(self, argv, stdin)
        return value if isinstance(value, str) else json.dumps(value)

    @staticmethod
    def _classify(argv: list[str]) -> str:
        joined = " ".join(argv)
        if "graphql" in argv:
            for name in (
                "issueTypes",
                "projectV2(number",
                "addProjectV2ItemById",
                "updateProjectV2ItemFieldValue",
                "issues(first",
                "issue(number",
            ):
                if name in joined:
                    return {
                        "issueTypes": "types",
                        "projectV2(number": "fields",
                        "addProjectV2ItemById": "add_item",
                        "updateProjectV2ItemFieldValue": "set_option",
                        "issues(first": "list_issues",
                        "issue(number": "read_issue",
                    }[name]
            return "graphql?"
        if "-X" in argv and argv[argv.index("-X") + 1] == "POST":
            return "create"
        if "-X" in argv and argv[argv.index("-X") + 1] == "PATCH":
            return "patch"
        return "api"

    # -- helpers a test asserts on -------------------------------------------

    def kinds(self) -> list[str]:
        return [call["kind"] for call in self.calls]

    def mutations(self) -> list[dict]:
        return [
            call
            for call in self.calls
            if call["kind"] in {"create", "patch", "add_item", "set_option"}
            or "mutation" in " ".join(call["argv"])
        ]

    def option_ids_written(self) -> list[str]:
        written = []
        for call in self.calls:
            if call["kind"] != "set_option":
                continue
            for token in call["argv"]:
                if token.startswith("option="):
                    written.append(token.split("=", 1)[1])
        return written

    def field_ids_written(self) -> list[str]:
        written = []
        for call in self.calls:
            if call["kind"] != "set_option":
                continue
            for token in call["argv"]:
                if token.startswith("field="):
                    written.append(token.split("=", 1)[1])
        return written


def _types_response(names=TYPE_NAMES) -> dict:
    return {"data": {"repository": {"issueTypes": {"nodes": [{"name": n} for n in names]}}}}


def _fields_response(root="organization") -> dict:
    return {"data": {root: {"projectV2": PROJECT_FIELDS_PAYLOAD}}}


def _issue_response(
    *,
    number=7,
    title="a title",
    labels=("BE",),
    issue_type="Chore",
    project_number=4,
    field_values=None,
    item_id="item-1",
) -> dict:
    project_items = []
    if project_number is not None:
        nodes = [
            {"name": value, "field": {"name": name}}
            for name, value in (field_values or {}).items()
        ]
        project_items.append(
            {
                "id": item_id,
                "project": {"number": project_number},
                "fieldValues": {"nodes": nodes},
            }
        )
    return {
        "data": {
            "repository": {
                "issue": {
                    "number": number,
                    "title": title,
                    "id": f"issue-node-{number}",
                    "url": f"https://example.invalid/issues/{number}",
                    "issueType": {"name": issue_type} if issue_type else None,
                    "labels": {"nodes": [{"name": label} for label in labels]},
                    "projectItems": {"nodes": project_items},
                }
            }
        }
    }


def _created(number=7) -> dict:
    return {
        "number": number,
        "node_id": f"issue-node-{number}",
        "html_url": f"https://example.invalid/issues/{number}",
    }


@pytest.fixture(autouse=True)
def _no_cached_fields():
    github.clear_field_cache()
    yield
    github.clear_field_cache()


@pytest.fixture
def body_file(tmp_path) -> str:
    path = tmp_path / "plan-7.md"
    path.write_text("# Plan: placeholder", encoding="utf-8")
    return str(path)


def _parser(**overrides):
    parser = build_core_parser()
    config = {
        "owner": "<owner>",
        "repo": "<repo>",
        "project_number": 4,
        "initial_status": STATUS_OPTIONS[0],
        "field_names": FIELD_NAMES,
    }
    config.update(overrides)
    github.register_github_commands(subparsers(parser), **config)
    return parser


def _run(monkeypatch, fake, argv, **overrides) -> int:
    # The seam the module documents: patched on the module, reached by every
    # internal caller through a call-time lookup.
    monkeypatch.setattr(github, "run_gh", fake)
    return dispatch(_parser(**overrides), argv)


# ── Policy ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label",
    [
        *TYPE_NAMES,
        *[t.lower() for t in TYPE_NAMES],
        *PRIORITY_OPTIONS,
        *[p.lower() for p in PRIORITY_OPTIONS],
        *SIZE_OPTIONS,
        *[s.upper() for s in SIZE_OPTIONS],
    ],
)
def test_reserved_label_rejects(label) -> None:
    """Both sources, in every case variant. Drop one source and its cases fail."""
    violations = github.reserved_label_violations(
        [label],
        type_names=TYPE_NAMES,
        option_names={PRIORITY_FIELD: PRIORITY_OPTIONS, SIZE_FIELD: SIZE_OPTIONS},
    )
    assert violations, f"{label!r} should be reserved"


def test_reserved_label_allows_an_area_tag() -> None:
    assert github.reserved_label_violations(
        ["BE"],
        type_names=TYPE_NAMES,
        option_names={PRIORITY_FIELD: PRIORITY_OPTIONS, SIZE_FIELD: SIZE_OPTIONS},
    ) == []


def test_reserved_patterns_are_case_insensitive_globs() -> None:
    assert github.reserved_label_violations(["P1"], reserved_patterns=["p[0-9]"])
    assert github.reserved_label_violations(["needs-triage"], reserved_patterns=["needs-*"])


def test_allowed_labels_none_checks_only_patterns() -> None:
    assert github.reserved_label_violations(["anything"], allowed_labels=None) == []


def test_repo_without_issue_types_degrades_but_still_checks_options() -> None:
    violations = github.reserved_label_violations(
        [PRIORITY_OPTIONS[0]],
        type_names=[],
        option_names={PRIORITY_FIELD: PRIORITY_OPTIONS},
    )
    assert violations


# ── create-issue ─────────────────────────────────────────────────────────────


def test_stage_one_rejection_makes_no_gh_call(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh()
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "nope"],
        allowed_labels=["BE", "FE"],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.calls == [], "a label the project does not allow must cost no API call"
    assert captured.out == ""
    assert "not one of this project's labels" in captured.err


def test_no_mutation_before_validation(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", PRIORITY_OPTIONS[1]],
    )
    capsys.readouterr()

    assert code == 2
    assert fake.mutations() == [], f"mutated before validating: {fake.kinds()}"


def test_create_issue_prints_observed_not_requested(monkeypatch, capsys, body_file) -> None:
    """The read-back is the output. Remove it and `extra` disappears."""
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(
            labels=("BE", "extra"),
            field_values={STATUS_FIELD: STATUS_OPTIONS[0]},
        ),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "extra" in out["observed"]["labels"]
    assert any("extra" in sentence for sentence in out["drift"])


def test_create_issue_sets_initial_status(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    capsys.readouterr()

    assert code == 0
    expected = f"{STATUS_FIELD_ID}-opt-{STATUS_OPTIONS[0]}"
    assert expected in fake.option_ids_written(), (
        "the newly added item was left at whatever status the board defaulted to"
    )


def test_partial_failure_exit_3_keeps_number_on_stdout(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(number=11),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
    )
    fake.fail("set_option", github.GhError(["api", "graphql"], 1, "boom"))

    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert code == 3
    assert out["number"] == 11
    assert out["node_id"] == "issue-node-11"
    assert out["url"]
    assert out["error"]
    assert "requested" in out and "observed" in out
    assert "set-fields 11" in captured.err
    assert "Do not create it again" in captured.err


def test_readback_reports_requested_vs_observed(monkeypatch, capsys, body_file) -> None:
    """A mismatch is re-read once, then reported — and still exits 0.

    The issue exists and its fields were written; a board automation that
    overwrote one is a fact to report, not a failed command.
    """
    reads = {"n": 0}

    def read(fake, argv, stdin):
        reads["n"] += 1
        return json.dumps(
            _issue_response(field_values={PRIORITY_FIELD: PRIORITY_OPTIONS[2]})
        )

    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=read,
    )
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--label", "BE", "--priority", PRIORITY_OPTIONS[0],
        ],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert reads["n"] == 2, "a mismatch must be re-read once before it is reported"
    assert out["observed"]["priority"] == PRIORITY_OPTIONS[2]
    assert any("priority" in sentence for sentence in out["drift"])


def test_omitting_type_sends_no_type_key(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    _run(monkeypatch, fake, ["create-issue", "--title", "t", "--body-file", body_file])
    capsys.readouterr()

    payload = json.loads(next(c for c in fake.calls if c["kind"] == "create")["stdin"])
    assert "type" not in payload, "no --type must send no type key at all"


def test_type_is_canonicalized_against_the_repo(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--type", TYPE_NAMES[0].lower()],
    )
    capsys.readouterr()

    payload = json.loads(next(c for c in fake.calls if c["kind"] == "create")["stdin"])
    assert payload["type"] == TYPE_NAMES[0], "the repo's spelling wins over the caller's"


def test_unknown_type_is_rejected_before_creating(monkeypatch, capsys, body_file) -> None:
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--type", "Nonexistent"],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == []
    assert "not defined on" in captured.err


def test_no_project_with_priority_is_a_usage_error(monkeypatch, body_file) -> None:
    fake = FakeGh()
    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            fake,
            [
                "create-issue", "--title", "t", "--body-file", body_file,
                "--no-project", "--priority", PRIORITY_OPTIONS[0],
            ],
        )
    assert exc.value.code == 2
    assert fake.calls == []


def test_body_file_relative_path_resolves_under_main_worktree(
    monkeypatch, capsys, tmp_path
) -> None:
    """A relative --body-file is read from the main worktree, not from CWD."""
    main_root = tmp_path / "main"
    (main_root / ".task" / "plan").mkdir(parents=True)
    (main_root / ".task" / "plan" / "plan-7.md").write_text("MAIN BODY", encoding="utf-8")
    (tmp_path / ".task" / "plan").mkdir(parents=True)
    (tmp_path / ".task" / "plan" / "plan-7.md").write_text("CWD BODY", encoding="utf-8")

    from harness_core import local

    monkeypatch.setattr(local, "main_worktree_root", lambda: main_root)
    monkeypatch.chdir(tmp_path)

    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", ".task/plan/plan-7.md"],
    )
    capsys.readouterr()

    payload = json.loads(next(c for c in fake.calls if c["kind"] == "create")["stdin"])
    assert payload["body"] == "MAIN BODY"


# ── set-fields ───────────────────────────────────────────────────────────────


def test_set_fields_sends_no_status_field_id(monkeypatch, capsys) -> None:
    """Status is the board's to decide. Add a status write and this goes red."""
    fake = FakeGh(
        fields=_fields_response(),
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(
            field_values={STATUS_FIELD: STATUS_OPTIONS[1], PRIORITY_FIELD: PRIORITY_OPTIONS[0]}
        ),
    )
    code = _run(
        monkeypatch, fake, ["set-fields", "7", "--priority", PRIORITY_OPTIONS[0]]
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert STATUS_FIELD_ID not in fake.field_ids_written()
    written = " ".join(" ".join(call["argv"]) for call in fake.calls if call["kind"] == "set_option")
    assert STATUS_FIELD_ID not in written
    assert out["status_before"] == STATUS_OPTIONS[1]
    assert out["status_after"] == STATUS_OPTIONS[1]


def test_set_fields_on_unregistered_issue_adds_item_without_status(monkeypatch, capsys) -> None:
    responses = iter(
        [
            _issue_response(project_number=None),
            _issue_response(field_values={PRIORITY_FIELD: PRIORITY_OPTIONS[0]}),
        ]
    )
    fake = FakeGh(
        fields=_fields_response(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-new"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-new"}}}},
        read_issue=lambda *_: json.dumps(next(responses)),
    )
    code = _run(monkeypatch, fake, ["set-fields", "7", "--priority", PRIORITY_OPTIONS[0]])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "add_item" in fake.kinds()
    assert STATUS_FIELD_ID not in fake.field_ids_written()
    assert out["status_before"] is None


def test_option_not_found_lists_available_and_writes_nothing(monkeypatch, capsys) -> None:
    fake = FakeGh(
        fields=_fields_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    code = _run(monkeypatch, fake, ["set-fields", "7", "--priority", "Nonexistent"])
    captured = capsys.readouterr()

    assert code != 0
    assert all(option in captured.err for option in PRIORITY_OPTIONS), (
        "an unknown option must name the ones that exist, or the caller is guessing"
    )
    assert fake.option_ids_written() == []


def test_set_fields_writes_both_or_neither(monkeypatch, capsys) -> None:
    """A bad second value must not leave the first one written."""
    fake = FakeGh(
        fields=_fields_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    code = _run(
        monkeypatch,
        fake,
        ["set-fields", "7", "--priority", PRIORITY_OPTIONS[0], "--size", "Nonexistent"],
    )
    capsys.readouterr()

    assert code != 0
    assert fake.option_ids_written() == []


# ── get-issue ────────────────────────────────────────────────────────────────


def test_get_issue_keeps_legacy_keys(monkeypatch, capsys) -> None:
    """Existing callers read number/title/node_id/labels. This only adds."""
    fake = FakeGh(read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}))
    code = _run(monkeypatch, fake, ["get-issue", "7"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["number"] == 7
    assert out["title"] == "a title"
    assert out["node_id"] == "issue-node-7"
    assert out["labels"] == ["BE"]
    assert isinstance(out["labels"], list)
    assert out["type"] == "Chore"
    assert out["project"]["status"] == STATUS_OPTIONS[0]


def test_issue_in_zero_projects_reports_project_none(monkeypatch, capsys) -> None:
    fake = FakeGh(read_issue=_issue_response(project_number=None))
    _run(monkeypatch, fake, ["get-issue", "7"])
    out = json.loads(capsys.readouterr().out)

    assert out["project"] is None


def test_issue_in_two_projects_picks_configured_number(monkeypatch, capsys) -> None:
    payload = _issue_response(field_values={PRIORITY_FIELD: PRIORITY_OPTIONS[0]})
    items = payload["data"]["repository"]["issue"]["projectItems"]["nodes"]
    items.insert(
        0,
        {
            "id": "item-other",
            "project": {"number": 99},
            "fieldValues": {"nodes": [{"name": "wrong", "field": {"name": PRIORITY_FIELD}}]},
        },
    )
    fake = FakeGh(read_issue=payload)
    _run(monkeypatch, fake, ["get-issue", "7"])
    out = json.loads(capsys.readouterr().out)

    assert out["project"]["item_id"] == "item-1"
    assert out["project"]["priority"] == PRIORITY_OPTIONS[0]


# ── project field resolution ─────────────────────────────────────────────────


def test_project_fields_load_tries_organization_then_user(monkeypatch) -> None:
    calls = []

    def fake(argv, *, stdin=None):
        calls.append(" ".join(argv))
        if "organization(login" in " ".join(argv):
            return json.dumps({"data": {"organization": None}})
        return json.dumps(_fields_response(root="user"))

    monkeypatch.setattr(github, "run_gh", fake)
    fields = github.ProjectFields.load("<owner>", 4)

    assert fields.project_id == PROJECT_ID
    assert len(calls) == 2, "a user-owned project must fall through, not fail"
    assert "organization(login" in calls[0]
    assert "user(login" in calls[1]


def test_project_fields_are_loaded_once_per_process(monkeypatch) -> None:
    calls = []

    def fake(argv, *, stdin=None):
        calls.append(argv)
        return json.dumps(_fields_response())

    monkeypatch.setattr(github, "run_gh", fake)
    github.ProjectFields.load("<owner>", 4)
    github.ProjectFields.load("<owner>", 4)

    assert len(calls) == 1


def test_unknown_field_name_lists_available(monkeypatch) -> None:
    monkeypatch.setattr(github, "run_gh", lambda argv, **_: json.dumps(_fields_response()))
    fields = github.ProjectFields.load("<owner>", 4)
    with pytest.raises(github.FieldNotFoundError) as exc:
        fields.field("Nope")
    assert PRIORITY_FIELD in str(exc.value)


def test_option_names_skips_a_field_the_project_lacks(monkeypatch) -> None:
    monkeypatch.setattr(github, "run_gh", lambda argv, **_: json.dumps(_fields_response()))
    fields = github.ProjectFields.load("<owner>", 4)
    assert fields.option_names([PRIORITY_FIELD, "Missing"]) == {PRIORITY_FIELD: PRIORITY_OPTIONS}


# ── audit-fields ─────────────────────────────────────────────────────────────


def _issue_list_page(numbers, *, has_next, cursor=None, labels=("BE",)) -> dict:
    return {
        "data": {
            "repository": {
                "issues": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": [
                        {
                            "number": n,
                            "title": f"issue {n}",
                            "id": f"issue-node-{n}",
                            "url": f"https://example.invalid/issues/{n}",
                            "issueType": {"name": "Chore"},
                            "labels": {"nodes": [{"name": label} for label in labels]},
                            "projectItems": {
                                "nodes": [
                                    {
                                        "id": f"item-{n}",
                                        "project": {"number": 4},
                                        "fieldValues": {
                                            "nodes": [
                                                {"name": STATUS_OPTIONS[0], "field": {"name": STATUS_FIELD}},
                                                {"name": PRIORITY_OPTIONS[0], "field": {"name": PRIORITY_FIELD}},
                                                {"name": SIZE_OPTIONS[0], "field": {"name": SIZE_FIELD}},
                                            ]
                                        },
                                    }
                                ]
                            },
                        }
                        for n in numbers
                    ],
                }
            }
        }
    }


def test_audit_paginates_past_100_and_never_mutates(monkeypatch, capsys) -> None:
    pages = iter(
        [
            _issue_list_page(range(1, 101), has_next=True, cursor="cursor-1"),
            _issue_list_page(range(101, 106), has_next=False),
        ]
    )
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=lambda *_: json.dumps(next(pages)),
    )
    code = _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["scanned"] == 105, "the audit stopped at the first page"
    assert fake.mutations() == []
    listings = [c for c in fake.calls if c["kind"] == "list_issues"]
    assert len(listings) == 2
    assert not any(t.startswith("cursor=") for t in listings[0]["argv"])
    assert "cursor=cursor-1" in listings[1]["argv"], (
        "the second page must be fetched with the cursor the first one returned"
    )


def test_audit_reports_label_field_mismatch(monkeypatch, capsys) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=_issue_list_page([1], has_next=False, labels=("BE", PRIORITY_OPTIONS[0])),
    )
    _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert out["with_drift"] == 1
    assert any(PRIORITY_FIELD in sentence for sentence in out["issues"][0]["drift"])


def test_audit_reports_a_label_that_duplicates_the_issue_type(monkeypatch, capsys) -> None:
    """The most-cited shape of the drift: type `Bug` plus a `bug` label.

    An audit that only compared field options reported this issue as clean.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=_issue_list_page([1], has_next=False, labels=("BE", TYPE_NAMES[0].lower())),
    )
    _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert out["with_drift"] == 1
    assert any("issue type" in sentence for sentence in out["issues"][0]["drift"])


def test_audit_limit_stops_early(monkeypatch, capsys) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=_issue_list_page(range(1, 101), has_next=True, cursor="c"),
    )
    _run(monkeypatch, fake, ["audit-fields", "--limit", "3"])
    out = json.loads(capsys.readouterr().out)

    assert out["scanned"] == 3


# ── registration ─────────────────────────────────────────────────────────────


def test_registration_makes_no_gh_call(monkeypatch) -> None:
    """`--help` builds this tree offline, on a host with no gh and no network."""

    def boom(*args, **kwargs):
        raise AssertionError(f"registration hit the network: {args!r}")

    monkeypatch.setattr(github, "run_gh", boom)
    monkeypatch.setattr(github.subprocess, "run", boom)
    _parser()


def test_register_twice_raises_duplicate_command_error() -> None:
    parser = build_core_parser()
    sub = subparsers(parser)
    kwargs = dict(owner="<owner>", repo="<repo>", field_names=FIELD_NAMES)
    github.register_github_commands(sub, **kwargs)
    with pytest.raises(DuplicateCommandError):
        github.register_github_commands(sub, **kwargs)


def test_registration_accepts_a_raw_subparsers_action() -> None:
    """A project's own `main()` builds a parser directly, without the wrapper."""
    import argparse

    parser = argparse.ArgumentParser()
    action = parser.add_subparsers(dest="command", required=True)
    github.register_github_commands(action, owner="<owner>", repo="<repo>", field_names=FIELD_NAMES)
    assert {"create-issue", "get-issue", "set-fields", "audit-fields"} <= set(action.choices)


def test_every_registered_command_builds_help() -> None:
    parser = _parser()
    for command in ("create-issue", "get-issue", "set-fields", "audit-fields"):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([command, "--help"])
        assert exc.value.code == 0


# ── source-level guards ──────────────────────────────────────────────────────


SRC = Path(__file__).resolve().parents[1] / "src"


def test_no_hardcoded_project_ids_in_src() -> None:
    """A resolved node ID is fine; a written-down one is a project constant."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for prefix in ("PVT_", "PVTSSF_", "PVTI_", "PVTF_"):
                if prefix in line:
                    offenders.append(f"{path.relative_to(SRC)}:{lineno}: {prefix}")
    assert not offenders, "hardcoded Projects V2 ids in src/:\n" + "\n".join(offenders)


def test_no_option_name_literals_in_the_adapter() -> None:
    """The reserved set is derived. A literal option name means it was not.

    `Status` is exempt and named as such in the source: it is GitHub's own name
    for the field it creates, not a name this project chose.
    """
    source = (SRC / "harness_core" / "trackers" / "github.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    # Strip docstrings: the module explains the contract using example values.
    code = re.sub(r'"""(?:.|\n)*?"""', "", code)
    forbidden = re.findall(r'"(P[0-9]|X?[SML]|XL|Backlog|In [Pp]rogress|In [Rr]eview)"', code)
    assert not forbidden, f"option-name literals in the adapter: {forbidden}"


def test_gh_is_invoked_from_exactly_one_place() -> None:
    source = (SRC / "harness_core" / "trackers" / "github.py").read_text(encoding="utf-8")
    assert source.count("subprocess.run(") == 1, (
        "every gh call goes through run_gh, or monkeypatching it stops working"
    )


# ── The gh boundary itself ───────────────────────────────────────────────────
#
# Every test above replaces `run_gh`. That is the right seam, but it left the
# function it replaces executed by nothing: gutting it three different ways
# (never raising, returning stderr, not running gh at all) kept the suite green.
# Every `except GhError` degradation in the module depends on a raise that no
# test triggered from the real function.


class TestRunGh:
    """Drives the real `run_gh` against a stub executable on PATH."""

    @staticmethod
    def _stub(tmp_path, script: str):
        stub = tmp_path / "gh"
        stub.write_text("#!/bin/sh\n" + script, encoding="utf-8")
        stub.chmod(0o755)
        return stub

    def test_returns_stdout_on_success(self, tmp_path, monkeypatch) -> None:
        self._stub(tmp_path, 'echo "{\\"ok\\": true}"\n')
        monkeypatch.setenv("PATH", str(tmp_path))
        assert json.loads(github.run_gh(["api", "x"]))["ok"] is True

    def test_raises_on_nonzero_exit(self, tmp_path, monkeypatch) -> None:
        self._stub(tmp_path, 'echo "boom" >&2\nexit 4\n')
        monkeypatch.setenv("PATH", str(tmp_path))
        with pytest.raises(github.GhError) as exc:
            github.run_gh(["api", "x"])
        assert exc.value.returncode == 4
        assert exc.value.stderr == "boom"

    def test_does_not_return_stderr_as_stdout(self, tmp_path, monkeypatch) -> None:
        # A swap would make every read silently return the wrong stream.
        self._stub(tmp_path, 'echo "OUT"\necho "ERR" >&2\n')
        monkeypatch.setenv("PATH", str(tmp_path))
        assert github.run_gh(["api", "x"]).strip() == "OUT"

    def test_actually_invokes_gh_with_the_argv(self, tmp_path, monkeypatch) -> None:
        # A run_gh that never executes anything would satisfy a looser test.
        self._stub(tmp_path, 'printf "%s" "$*"\n')
        monkeypatch.setenv("PATH", str(tmp_path))
        assert github.run_gh(["api", "graphql", "-f", "q=1"]) == "api graphql -f q=1"

    def test_stdin_reaches_the_process(self, tmp_path, monkeypatch) -> None:
        self._stub(tmp_path, "/bin/cat\n")  # absolute: the stub inherits the emptied PATH
        monkeypatch.setenv("PATH", str(tmp_path))
        assert github.run_gh(["api", "x"], stdin='{"title":"t"}') == '{"title":"t"}'

    def test_missing_gh_is_a_gh_error_not_a_traceback(self, tmp_path, monkeypatch) -> None:
        # The `harness_enabled: false` world is where gh is most likely absent.
        monkeypatch.setenv("PATH", str(tmp_path))  # empty dir: no gh
        with pytest.raises(github.GhError) as exc:
            github.run_gh(["api", "x"])
        assert "not installed" in exc.value.stderr

    def test_error_message_does_not_echo_the_whole_payload(self, tmp_path, monkeypatch) -> None:
        # argv for a GraphQL call carries the mutation document and node IDs, and
        # this string is quoted into impl-reports and issue comments.
        self._stub(tmp_path, "exit 1\n")
        monkeypatch.setenv("PATH", str(tmp_path))
        with pytest.raises(github.GhError) as exc:
            github.run_gh(["api", "graphql", "-f", "query=mutation{secretLooking}", "-f", "item=PVTI_x"])
        assert "PVTI_x" not in str(exc.value)
        assert "mutation{" not in str(exc.value)


# ── The absences, which is what the drift actually looked like ───────────────
#
# The duplication half was tested; the absence half was not, and the absences
# are the plan's own evidence: an issue with a size *label* and an empty Size
# field, and issues with no type at all. Removing each of these sentences left
# the suite green.


class TestFieldDriftAbsences:
    OPTIONS = {PRIORITY_FIELD: PRIORITY_OPTIONS, SIZE_FIELD: SIZE_OPTIONS}

    def _meta(self, **over):
        meta = {
            "number": 581,
            "labels": ["BE"],
            "type": TYPE_NAMES[0],
            "project": {
                "item_id": "item-1",
                "status": STATUS_OPTIONS[0],
                "priority": PRIORITY_OPTIONS[0],
                "size": SIZE_OPTIONS[0],
            },
        }
        meta.update(over)
        return meta

    def test_a_clean_issue_reports_nothing(self) -> None:
        assert github.field_drift(
            self._meta(), option_names=self.OPTIONS, type_names=TYPE_NAMES
        ) == []

    def test_missing_issue_type_is_reported(self) -> None:
        drift = github.field_drift(
            self._meta(type=None), option_names=self.OPTIONS, type_names=TYPE_NAMES
        )
        assert any("no issue type" in s for s in drift)

    def test_issue_not_in_the_project_is_reported(self) -> None:
        drift = github.field_drift(
            self._meta(project=None), option_names=self.OPTIONS, type_names=TYPE_NAMES
        )
        assert any("not in the configured project" in s for s in drift)

    @pytest.mark.parametrize("slot", ["status", "priority", "size"])
    def test_an_empty_project_field_is_reported(self, slot) -> None:
        project = dict(self._meta()["project"])
        project[slot] = None
        drift = github.field_drift(
            self._meta(project=project), option_names=self.OPTIONS, type_names=TYPE_NAMES
        )
        assert any(f"{slot} field is empty" in s for s in drift), drift

    def test_a_repo_without_issue_types_is_not_drift(self) -> None:
        """`[]` means the repo defines none — every issue would otherwise flag."""
        drift = github.field_drift(
            self._meta(type=None), option_names=self.OPTIONS, type_names=[]
        )
        assert not any("no issue type" in s for s in drift)

    def test_the_observed_581_shape_reports_all_four_facts(self) -> None:
        # The real issue this contract was written for, as observed on
        # 2026-09-14: type Bug, labels BE/bug/P1/L, Priority set, Size empty.
        meta = {
            "number": 581,
            "type": TYPE_NAMES[1],
            "labels": ["BE", TYPE_NAMES[1].lower(), PRIORITY_OPTIONS[1], SIZE_OPTIONS[2]],
            "project": {
                "item_id": "i",
                "status": STATUS_OPTIONS[1],
                "priority": PRIORITY_OPTIONS[0],
                "size": None,
            },
        }
        drift = github.field_drift(meta, option_names=self.OPTIONS, type_names=TYPE_NAMES)
        assert len(drift) == 4, drift
        assert any("duplicates the issue type" in s for s in drift)
        assert any(PRIORITY_FIELD in s for s in drift)
        assert any(SIZE_FIELD in s for s in drift)
        assert any("size field is empty" in s for s in drift)


def test_mismatches_reports_a_requested_label_that_was_not_applied() -> None:
    """The superset branch was tested; the missing branch was not.

    A label the API silently refused (it does refuse some) read as clean.
    """
    drift = github._mismatches({"labels": ["BE", "FE"]}, {"labels": ["BE"]})
    assert any("not applied" in s and "FE" in s for s in drift), drift


def test_mismatches_reports_an_unrequested_extra() -> None:
    drift = github._mismatches({"labels": ["BE"]}, {"labels": ["BE", "auto"]})
    assert any("not requested" in s and "auto" in s for s in drift), drift


# ── Paths that previously ended in a traceback or a false success ────────────


def test_set_fields_type_is_resolved_before_the_type_is_written(monkeypatch, capsys) -> None:
    """A bad --priority must not leave a changed type behind.

    The PATCH used to run before priority/size were resolved, so this returned
    exit 2 — "nothing happened" — with the issue type already changed.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
        patch={"number": 7},
    )
    code = _run(
        monkeypatch,
        fake,
        ["set-fields", "7", "--type", TYPE_NAMES[1], "--priority", "Nonexistent"],
    )
    capsys.readouterr()

    assert code == 2
    assert "patch" not in fake.kinds(), "the type was written before validation finished"
    assert fake.mutations() == []


def test_set_fields_writes_the_type_over_rest(monkeypatch, capsys) -> None:
    fake = FakeGh(
        types=_types_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
        patch={"number": 7},
    )
    code = _run(monkeypatch, fake, ["set-fields", "7", "--type", TYPE_NAMES[1].lower()])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    patch = next(c for c in fake.calls if c["kind"] == "patch")
    assert json.loads(patch["stdin"]) == {"type": TYPE_NAMES[1]}, "the repo spelling wins"
    assert out["requested"]["type"] == TYPE_NAMES[1]


def test_set_fields_failure_after_a_write_exits_3_with_the_number(monkeypatch, capsys) -> None:
    fake = FakeGh(
        types=_types_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    fake.fail("patch", github.GhError(["api", "repos"], 1, "boom"))
    code = _run(monkeypatch, fake, ["set-fields", "7", "--type", TYPE_NAMES[1]])
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert code == 3
    assert out["number"] == 7
    assert out["error"]


def test_get_issue_not_found_exits_two_with_a_message(monkeypatch, capsys) -> None:
    fake = FakeGh(read_issue={"data": {"repository": {"issue": None}}})
    code = _run(monkeypatch, fake, ["get-issue", "9999"])
    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "9999" in captured.err


def test_create_issue_refuses_when_issue_types_cannot_be_read(monkeypatch, capsys, body_file) -> None:
    """A transient read failure used to create an untyped issue and exit 0.

    `repo_issue_type_names` returned [] on error, which is indistinguishable
    from "this repo has no types", so --type was dropped and the result was
    reported as clean — manufacturing the exact drift this module prevents.
    """
    fake = FakeGh(fields=_fields_response())
    fake.fail("types", github.GhError(["api", "graphql"], 1, "Bad credentials"))
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--type", TYPE_NAMES[0]],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == [], "an issue was created despite an unverifiable type"
    assert "could not read" in captured.err


def test_create_issue_validates_initial_status_before_creating(monkeypatch, capsys, body_file) -> None:
    """A typo in skill-config.yaml used to create an issue on every run, forever."""
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file],
        initial_status="Nonexistent",
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == []
    assert captured.out == ""
    assert all(option in captured.err for option in STATUS_OPTIONS)


def test_create_issue_read_back_failure_still_exits_3_with_the_number(
    monkeypatch, capsys, body_file
) -> None:
    """The read-back sat outside the exit-3 guarantee.

    It is the call most likely to fail — it runs last, right after three writes,
    and GitHub can legitimately 404 an issue it has just created. The failure
    produced a traceback with empty stdout, so the session's next move was to
    re-run create-issue and get a second issue for the same plan.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(number=42),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
    )
    fake.fail("read_issue", github.GhError(["api", "graphql"], 1, "secondary rate limit"))
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert code == 3
    assert out["number"] == 42
    assert out["node_id"] == "issue-node-42"
    assert out["url"]
    assert out["error"]
    assert "set-fields 42" in captured.err


def test_create_issue_read_back_404_exits_3_not_1(monkeypatch, capsys, body_file) -> None:
    # GraphQL replica lag on a just-created issue: repository.issue is null.
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(number=43),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue={"data": {"repository": {"issue": None}}},
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 3
    assert out["number"] == 43


def test_create_issue_unreadable_body_file_exits_two(monkeypatch, capsys, tmp_path) -> None:
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", str(tmp_path / "nope.md")],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == []
    assert "--body-file" in captured.err


def test_unreadable_project_refuses_before_creating(monkeypatch, capsys, body_file) -> None:
    """A board that cannot be read is a 2, not a create judged against nothing.

    This replaces a test that asserted the opposite: exit 0, the issue created,
    and the absence recorded in `drift` alone. `project-issue` branches on the
    exit code, so that contract reported a half-applied issue as a clean success
    — and the same unread board answered "nothing is reserved" to the label
    check on its way past.
    """
    fake = FakeGh(types=_types_response(), create=_created(), read_issue=_issue_response())
    fake.fail("fields", github.GhError(["api", "graphql"], 1, "missing 'project' scope"))
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "create" not in fake.kinds(), "an issue was created against an unread board"
    assert captured.out == ""
    assert "project #4" in captured.err


def test_audit_says_so_when_issue_types_cannot_be_read(monkeypatch, capsys) -> None:
    fake = FakeGh(
        fields=_fields_response(),
        list_issues=_issue_list_page([1], has_next=False, labels=("BE", TYPE_NAMES[0].lower())),
    )
    fake.fail("types", github.GhError(["api", "graphql"], 1, "Bad credentials"))
    code = _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["warnings"], "a half-audit reported as a clean audit"
    assert any("NOT audited" in w for w in out["warnings"])


@pytest.mark.parametrize(
    "state,expected", [("open", "OPEN"), ("all", None)]
)
def test_audit_state_reaches_the_query(monkeypatch, capsys, state, expected) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=_issue_list_page([1], has_next=False),
    )
    _run(monkeypatch, fake, ["audit-fields", "--state", state])
    capsys.readouterr()

    argv = next(c for c in fake.calls if c["kind"] == "list_issues")["argv"]
    sent = [tok for tok in argv if tok.startswith("state=")]
    assert sent == ([f"state={expected}"] if expected else [])


def test_audit_limit_zero_scans_nothing(monkeypatch, capsys) -> None:
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    _run(monkeypatch, fake, ["audit-fields", "--limit", "0"])
    out = json.loads(capsys.readouterr().out)

    assert out["scanned"] == 0
    assert "list_issues" not in fake.kinds()


def test_field_names_may_be_omitted_entirely(monkeypatch, capsys) -> None:
    """The documented schema and the starter template both allow this.

    Without the defaults it raised `KeyError: 'priority'` — from `set-fields`,
    the command create-issue's own failure message tells the caller to run.
    """
    fake = FakeGh(
        fields=_fields_response(),
        read_issue=_issue_response(field_values={STATUS_FIELD: STATUS_OPTIONS[0]}),
    )
    code = _run(monkeypatch, fake, ["set-fields", "7", "--priority", "P0"], field_names={})
    captured = capsys.readouterr()

    # The placeholder project has no "Priority" field, so this is a clean exit 2
    # naming the fields that exist — not a KeyError traceback.
    assert code == 2
    assert "Priority" in captured.err


def test_no_project_read_back_ignores_other_projects(monkeypatch, capsys, body_file) -> None:
    """`--no-project` must not report a different board's field values.

    The read-back used to pass project_number=None, which takes the *first*
    project item from any project — so on a repo with an auto-add automation it
    reported another project's priority as this issue's.
    """
    payload = _issue_response(field_values={PRIORITY_FIELD: PRIORITY_OPTIONS[0]})
    payload["data"]["repository"]["issue"]["projectItems"]["nodes"][0]["project"] = {"number": 99}
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=payload,
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--no-project"],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["observed"]["priority"] is None, "another project's field was reported"


# ── #19: an unread board is not a board with nothing on it ───────────────────
#
# The shape every defect below shares. `option_names={}` reads as "nothing is
# reserved", a skipped field write reads as "no field was asked for", and a
# fallback that raises reads as no fallback at all. Each test fails on the
# pre-#19 module.


def test_no_project_still_judges_labels_against_the_board(
    monkeypatch, capsys, body_file
) -> None:
    """`--no-project` says where the issue goes, not what a label means.

    A priority option is that field's value whether or not *this* issue joins
    the board, so the judgement needs the board's options either way. Tying the
    read to the registration let the option through as a label.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=_issue_response(project_number=None),
    )
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--no-project", "--label", PRIORITY_OPTIONS[1],
        ],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == [], f"created despite a reserved label: {fake.kinds()}"
    assert captured.out == ""
    assert PRIORITY_FIELD in captured.err


def test_unreadable_project_refuses_a_requested_field_before_creating(
    monkeypatch, capsys, body_file
) -> None:
    """The reported reproduction: rc 0, one issue, no board, drift only."""
    fake = FakeGh(types=_types_response(), create=_created(), read_issue=_issue_response())
    fake.fail("fields", github.GhError(["api", "graphql"], 1, "server error"))
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--label", "BE", "--priority", PRIORITY_OPTIONS[1], "--size", SIZE_OPTIONS[0],
        ],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == []
    assert captured.out == ""


def test_no_configured_project_degrades_and_still_reports_the_field(
    monkeypatch, capsys, body_file
) -> None:
    """A *declared* absence is a documented degrade, not an unread board.

    `register_github_commands`, the starter template and two reference documents
    all promise that a repo with no project still creates issues and reports the
    fields as not applied. The requested value has to survive into `requested`
    for that report to exist at all — dropping the key would turn "asked for and
    not applied" into "never asked for".
    """
    fake = FakeGh(
        types=_types_response(),
        create=_created(),
        read_issue=_issue_response(project_number=None),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--priority", PRIORITY_OPTIONS[1]],
        project_number=None,
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "fields" not in fake.kinds(), "a board was read with none configured"
    assert out["requested"]["priority"] == PRIORITY_OPTIONS[1]
    assert any(
        "priority" in sentence and "requested" in sentence for sentence in out["drift"]
    ), f"the unapplied field left no trace: {out['drift']}"
    assert any("no project configured" in sentence for sentence in out["drift"])


def test_unknown_option_value_is_rejected_before_creating(
    monkeypatch, capsys, body_file
) -> None:
    """The create-issue half of the option check `set-fields` already had."""
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--priority", "U9"],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.mutations() == []
    assert "U9" in captured.err


def test_no_project_writes_nothing_to_the_board(monkeypatch, capsys, body_file) -> None:
    """Reading the board must not become a reason to join it."""
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=_issue_response(project_number=None),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--no-project"],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "add_item" not in fake.kinds(), "--no-project put the issue on the board"
    assert "set_option" not in fake.kinds()
    assert any("--no-project" in sentence for sentence in out["drift"])


def test_create_failure_exits_four_because_the_outcome_is_unknown(
    monkeypatch, capsys, body_file
) -> None:
    """`gh` exiting non-zero does not establish that the issue does not exist.

    It exits non-zero for a 422 the server rejected and for a connection lost
    after the 201 was written. Exit 2 asserts "nothing exists; fix the argument
    and run it again", and that re-run files a second issue carrying the same
    plan body. Uncaught — the original behaviour — it was exit 1, which the
    skill has no rule for, so the re-run happened anyway.
    """
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    fake.fail("create", github.GhError(["api", "-X", "POST"], 1, "Validation Failed"))
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    captured = capsys.readouterr()

    assert code == 4
    assert captured.out == ""
    assert "not known whether the issue exists" in captured.err
    assert "Validation Failed" in captured.err


def test_an_unreadable_create_response_is_also_four(monkeypatch, capsys, body_file) -> None:
    """The POST returned 2xx — the issue exists — and its number was lost.

    `create_issue` reads `number`/`node_id`/`html_url` out of the response after
    `json.loads`. Both raise past an `except GhError`, through `dispatch`, as a
    traceback at exit 1.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create={"html_url": "https://example.invalid/issues/7"},
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "BE"],
    )
    captured = capsys.readouterr()

    assert code == 4
    assert captured.out == ""
    assert "not known whether the issue exists" in captured.err


def test_requested_records_the_boards_spelling(monkeypatch, capsys, body_file) -> None:
    """A case variant matches the option, so it must not be reported as drift.

    Option resolution ignores case; `_mismatches` does not. Recording what the
    caller typed made the two disagree about a value they had both accepted.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(
            labels=(),
            issue_type=None,
            field_values={
                STATUS_FIELD: STATUS_OPTIONS[0],
                PRIORITY_FIELD: PRIORITY_OPTIONS[1],
            },
        ),
    )
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--priority", PRIORITY_OPTIONS[1].lower(),
        ],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["requested"]["priority"] == PRIORITY_OPTIONS[1]
    assert out["drift"] == [], f"a case variant was reported as drift: {out['drift']}"


def test_allowed_labels_compare_exactly() -> None:
    """A label that only matches after folding is still POSTed as typed.

    GitHub's issue REST then creates that spelling as a new label — the implicit
    creation `allowed_labels` exists to stop.
    """
    assert github.reserved_label_violations(["be"], allowed_labels=["BE"]) == []
    assert github.reserved_label_violations(["B-E"], allowed_labels=["BE"])
    assert github.reserved_label_violations(["B.E"], allowed_labels=["BE"])
    assert github.reserved_label_violations(["USER_STORY"], allowed_labels=["user-story"])
    # Symmetric: the fold is absent on both sides, not just the caller's.
    assert github.reserved_label_violations(["BE"], allowed_labels=["B-E"])


def test_reserved_axis_still_ignores_separators() -> None:
    """The two axes keep different keys, and folding the reserved one is right."""
    option = PRIORITY_OPTIONS[1]
    assert github.reserved_label_violations(
        [f"{option[0]}-{option[1:]}"], option_names={PRIORITY_FIELD: PRIORITY_OPTIONS}
    )


def test_a_separator_variant_is_rejected_before_any_call(
    monkeypatch, capsys, body_file
) -> None:
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=_issue_response(),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--label", "B-E"],
        allowed_labels=["BE", "FE"],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert fake.calls == []
    assert "not one of this project's labels" in captured.err


def test_audit_degrades_to_labels_when_the_board_cannot_be_read(
    monkeypatch, capsys
) -> None:
    """The designed fallback. It raised UnboundLocalError instead of taking it."""
    fake = FakeGh(
        types=_types_response(),
        list_issues=_issue_list_page([1], has_next=False, labels=("BE", TYPE_NAMES[0].lower())),
    )
    fake.fail("fields", github.GhError(["api", "graphql"], 1, "missing 'project' scope"))
    code = _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert any("project fields could not be read" in w for w in out["warnings"])
    assert out["with_drift"] == 1, "the label axis stopped auditing too"
    assert any("issue type" in sentence for sentence in out["issues"][0]["drift"])


def test_audit_judges_status_options_like_create_issue(monkeypatch, capsys) -> None:
    """One judgement, one set of inputs.

    The audit derived its options from the *writable* slots, which excludes
    Status — so the one label shape the write path rejects by name was the one
    shape the audit could not see.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        list_issues=_issue_list_page([1], has_next=False, labels=("BE", STATUS_OPTIONS[1])),
    )
    code = _run(monkeypatch, fake, ["audit-fields"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["with_drift"] == 1
    assert any(STATUS_FIELD in sentence for sentence in out["issues"][0]["drift"])


def test_audit_exits_two_when_the_issue_list_cannot_be_read(monkeypatch, capsys) -> None:
    """With no issues read there is nothing to degrade to. It was a traceback."""
    fake = FakeGh(types=_types_response(), fields=_fields_response())
    fake.fail("list_issues", github.GhError(["api", "graphql"], 1, "Bad credentials"))
    code = _run(monkeypatch, fake, ["audit-fields"])
    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "could not list the issues" in captured.err


# ── Cells the first round left open, each one a surviving mutant ─────────────


def test_no_project_with_an_unreadable_board_still_refuses(
    monkeypatch, capsys, body_file
) -> None:
    """The crossing cell: `--no-project` **and** the board read fails.

    An implementation that reads the board unconditionally but refuses only when
    the issue is joining it restores defect 1 for exactly this cell — the same
    `option_names={}` answering "nothing is reserved" — while every other test
    stays green.
    """
    fake = FakeGh(types=_types_response(), create=_created(), read_issue=_issue_response())
    fake.fail("fields", github.GhError(["api", "graphql"], 1, "missing 'project' scope"))
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--no-project", "--label", "BE",
        ],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "create" not in fake.kinds(), "an issue was created against an unread board"
    assert captured.out == ""


def test_no_project_without_labels_never_reads_the_board(
    monkeypatch, capsys, body_file
) -> None:
    """A read whose result cannot change an outcome must not fail the command.

    With no labels and no registration there is nothing the board's options could
    decide. Refusing here closed the one escape a repo with an unreadable board
    has left: `--no-project`, which `project-issue` documents for that case.
    """
    fake = FakeGh(
        types=_types_response(),
        create=_created(),
        read_issue=_issue_response(project_number=None),
    )
    fake.fail("fields", github.GhError(["api", "graphql"], 1, "missing 'project' scope"))
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file, "--no-project"],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "fields" not in fake.kinds(), "a board was read that could decide nothing"
    assert any("--no-project" in sentence for sentence in out["drift"])


def test_create_judges_status_options_like_the_audit(monkeypatch, capsys, body_file) -> None:
    """The other half of "one judgement, one set of inputs".

    The audit side is pinned by `test_audit_judges_status_options_like_create_issue`;
    this is the side that actually rejects the write. Deriving stage two from the
    writable slots drops Status and every other test stays green.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=_issue_response(),
    )
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--label", STATUS_OPTIONS[1],
        ],
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "create" not in fake.kinds()
    assert STATUS_FIELD in captured.err


def test_initial_status_is_recorded_in_the_boards_spelling(
    monkeypatch, capsys, body_file
) -> None:
    """`initial_status` comes from config, not from an argument.

    So its spelling drift is permanent: a `skill-config.yaml` that lower-cases
    the option matches the board on every create and is reported as drift on
    every create. `--priority` pins the loop; this pins the status slot.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        add_item={"data": {"addProjectV2ItemById": {"item": {"id": "item-1"}}}},
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
        read_issue=_issue_response(
            labels=(),
            issue_type=None,
            field_values={STATUS_FIELD: STATUS_OPTIONS[0]},
        ),
    )
    code = _run(
        monkeypatch,
        fake,
        ["create-issue", "--title", "t", "--body-file", body_file],
        initial_status=STATUS_OPTIONS[0].lower(),
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["requested"]["status"] == STATUS_OPTIONS[0]
    assert out["drift"] == [], f"a config-cased status was reported as drift: {out['drift']}"


def test_reserved_type_axis_folds_on_both_sides() -> None:
    """The Drift Guard covers the whole reserved axis, not just its option half.

    Folding only the label leaves a separator in a *type name* unmatched, which
    is the same hole in the other direction.
    """
    assert github.reserved_label_violations(["userstory"], type_names=["User-Story"])
    assert github.reserved_label_violations(["User-Story"], type_names=["userstory"])


def test_set_fields_records_the_boards_spelling(monkeypatch, capsys) -> None:
    """`set-fields` carried defect 6 verbatim, and it is where exit 3 sends people.

    A false drift sentence is worst in the repair command: the caller arrives
    there because something already went wrong, and is told the repair drifted.
    """
    fake = FakeGh(
        fields=_fields_response(),
        read_issue=_issue_response(field_values={PRIORITY_FIELD: PRIORITY_OPTIONS[1]}),
        set_option={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item-1"}}}},
    )
    code = _run(
        monkeypatch,
        fake,
        ["set-fields", "7", "--priority", PRIORITY_OPTIONS[1].lower()],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["requested"]["priority"] == PRIORITY_OPTIONS[1]
    assert out["drift"] == [], f"a case variant was reported as drift: {out['drift']}"


def test_audit_exits_two_on_a_malformed_issue_node(monkeypatch, capsys) -> None:
    """`_shape_issue_node` raises LookupError, not GhError, on a missing key.

    `_get_issue_handler` catches that family for the same reads. The audit's new
    refusal caught GhError alone, so a malformed node stayed a traceback at
    exit 1 — the shape the refusal was added to remove.
    """
    page = _issue_list_page([1], has_next=False)
    del page["data"]["repository"]["issues"]["nodes"][0]["url"]
    fake = FakeGh(types=_types_response(), fields=_fields_response(), list_issues=page)
    code = _run(monkeypatch, fake, ["audit-fields"])
    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "could not list the issues" in captured.err


def test_no_project_with_labels_reads_the_board_but_writes_nothing(
    monkeypatch, capsys, body_file
) -> None:
    """Reading the board must not become a reason to join it.

    The sibling test reaches this with no labels, where the read is skipped
    entirely — so it cannot see the write gate at all. Here the board *is* read,
    the label passes stage two, and the create must still leave the board alone.
    """
    fake = FakeGh(
        types=_types_response(),
        fields=_fields_response(),
        create=_created(),
        read_issue=_issue_response(project_number=None),
    )
    code = _run(
        monkeypatch,
        fake,
        [
            "create-issue", "--title", "t", "--body-file", body_file,
            "--no-project", "--label", "BE",
        ],
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "fields" in fake.kinds(), "the board was not read, so this proves nothing"
    assert "add_item" not in fake.kinds(), "--no-project put the issue on the board"
    assert "set_option" not in fake.kinds()
    assert any("--no-project" in sentence for sentence in out["drift"])
