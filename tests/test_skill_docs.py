"""Contract tests for workflow skill documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_skill(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")



# Names, hosts and addresses that belong to the consuming organization rather
# than to this skillset. They may appear in a project's own skill-config.yaml,
# never in the shared tree or the README.
INTERNAL_TOKENS = (
    "enseed-trader",
    "enseed-trading-dev",
    "quantlab-front",
    "quantlab-site",
    "cosmos-forge",
    "forge.lab.internal",
    "azurenote",
)


# --------------------------------------------------------------------------
# Anchoring helpers
#
# A substring assertion proves a sentence exists somewhere, not that it is
# still the rule. A review demonstrated the gap: every prose guard below
# survived having its rule inverted, because the asserted phrase was kept as a
# historical aside ("an earlier draft said ... no longer applies"). These
# helpers pin the *shape* of the rule line instead.
# --------------------------------------------------------------------------

# Words that turn a rule into a note about a rule that used to exist.
RETRACTION_MARKERS = (
    "earlier draft", "no longer applies", "previously", "old rule", "구 규칙",
    "이전 규칙", "was a warning", "used to be", "former rule", "deprecated",
)


def rule_line(text: str, anchor: str) -> str:
    """The one line stating a rule. Two lines means a copy crept in."""
    lines = [l.strip() for l in text.splitlines() if anchor in l]
    assert len(lines) == 1, (
        f"expected exactly one line containing {anchor!r}, found {len(lines)}:\n"
        + "\n".join(lines)
    )
    return lines[0]


def assert_rule(text: str, anchor: str, *, starts_with: str) -> str:
    """Pin a rule by the shape of its line, not by a word appearing anywhere.

    `starts_with` makes the line an instruction rather than a remark about one,
    and the retraction scan rejects keeping the phrase as history.
    """
    line = rule_line(text, anchor)
    assert line.startswith(starts_with), (
        f"rule line no longer states the rule.\n  expected start: {starts_with!r}\n  actual: {line!r}"
    )
    lowered = line.lower()
    for marker in RETRACTION_MARKERS:
        assert marker not in lowered, f"rule line reads as retracted ({marker!r}): {line!r}"
    return line


def test_common_review_profile_policy_is_defined() -> None:
    text = read_skill("skills/SKILL-CONFIG.md")

    for token in (
        "review_profile",
        "`auto`",
        "`full`",
        "`docs-light`",
        "Override 안전 규칙",
        "docs-light` 리뷰 체크리스트",
    ):
        assert token in text

    assert "문서 전용" in text
    assert "코드·테스트·빌드·CI·의존성·런타임 설정" in text

    # Behavior-defining markdown (skill instructions) is not docs-light.
    assert "동작을 정의하는 문서" in text
    assert "skills/**/SKILL.md" in text


def test_project_plan_template_declares_review_profile() -> None:
    text = read_skill("skills/project-plan/SKILL.md")

    assert "## Review Profile" in text
    assert "- Profile: `auto`" in text
    assert "Expected mode" in text
    assert "Docs-only examples" in text
    assert "Code-impact examples" in text
    assert "Review the plan according to Review Profile" in text


def test_project_start_uses_adaptive_review() -> None:
    text = read_skill("skills/project-start/SKILL.md")

    assert "**8. Adaptive Review**" in text
    assert "Profile resolution rules" in text
    assert "`docs-light` review checklist" in text
    assert "review profile" in text
    assert "code, tests, build, CI, dependencies, runtime config" in text


def test_project_start_review_loads_project_guidelines() -> None:
    """The layer lost in the move to shared skills: per-role review grounding.

    Before the move, each reviewer was handed specific project guideline
    documents and specific sections to look at. The shared skill had no way to
    say that. `review_guidelines` is that way back.
    """
    text = read_skill("skills/project-start/SKILL.md")

    assert "review_guidelines" in text
    assert "`.claude/skill-config.yaml`" in text

    # Guidelines are read, never summarized into a copy that drifts.
    assert_rule(
        text, "never copy a summary",
        starts_with="- Each role reads `common` plus its own `docs`",
    )
    # `focus` is transported, not interpreted — that is what keeps the skill neutral.
    assert_rule(
        text, "Do not parse it",
        starts_with="- Pass each role's `focus` string through **verbatim**.",
    )
    # Roles come from the project, not from this file.
    assert_rule(
        text, "Do not hardcode role names",
        starts_with="- Iterate the roles the project declared.",
    )
    # A missing path degrades loudly; it never silently drops.
    assert_rule(
        text, "warning, not a stop",
        starts_with="- A declared path that does not exist is a **warning, not a stop**",
    )
    # Per-role fallback, not all-or-nothing — these were two contradictory rules.
    assert_rule(
        text, "Fall back per role",
        starts_with="- Fall back per role, not all-or-nothing",
    )
    # The report must carry the evidence that the delegation actually closed.
    assert "guideline paths actually read" in text
    # The default role table lives in the reference; a copy here would diverge.
    assert "canonical table of default roles" in text
    assert "| architect |" not in text, "the default-role table was copied back in"


def test_project_start_review_requires_mutation_evidence() -> None:
    """The duty this repo keeps failing to hold itself to.

    A review turned this rule optional — "The mutation duty **is** optional and
    a project override **may** drop it" — and the old guard stayed green,
    because it only looked for the words, which the inverted text still had.
    """
    text = read_skill("skills/project-start/SKILL.md")

    line = assert_rule(
        text, "mutation duty",
        starts_with="The mutation duty stands regardless of which roles the project declares",
    )
    # The inverted forms, explicitly.
    for negation in ("is optional", "may drop", "may be skipped", "is not required", "optional and"):
        assert negation not in line.lower(), f"the duty was made optional: {line!r}"

    assert "A passing test is not evidence that a guard works." in text
    assert "not removed by a project override" in line
    # Renaming the tester role must not shed the duty.
    assert "does not disappear when the project renames or replaces the tester role" in text





def test_project_start_review_path_chain_is_closed() -> None:
    """A priority chain whose last entry is conditional is not a fallback.

    A review made the last rung conditional ("If subagents are unavailable and
    the user consents, ...") and the old guard passed, because the asserted
    sentence was still a substring.
    """
    text = read_skill("skills/project-start/SKILL.md")

    assert "**8-B. Choose an execution path" in text
    assert "the last entry always applies" in text

    line = rule_line(text, "The main agent performs each role directly")
    assert line.startswith("3. The main agent performs each role directly"), (
        f"the terminal rung is no longer the numbered last entry: {line!r}"
    )
    # Nothing may gate it — a conditional last rung leaves the chain open.
    for gate in ("if ", "when ", "unless ", "consent", "permitt", "allowed"):
        assert gate not in line.lower(), f"the terminal rung is conditional: {line!r}"

    # Named tools may come and go; the procedure must not depend on one existing.
    assert "dependencies.yaml" in text
    # Installed is not the same as reachable.
    assert "two questions, not one" in text
    assert_rule(text, "Never spawn an LLM CLI", starts_with="- Never spawn an LLM CLI")
    assert_rule(text, "Roles stay separate on every path", starts_with="- Roles stay separate on every path")


def test_project_iterate_delegates_to_review_profile() -> None:
    text = read_skill("skills/project-iterate/SKILL.md")

    assert "review the plan according to `Review Profile` policy" in text
    assert "review the implementation according to `Review Profile` policy" in text
    assert "에이전트 팀 리뷰" not in text
    assert "에이전트 팀 코드 리뷰" not in text


def test_project_done_reports_review_profile() -> None:
    text = read_skill("skills/project-done/SKILL.md")

    assert "**1-C. Read Review Profile**" in text
    assert "## Review" in text
    assert "Review Profile:" in text
    assert "Resolved Mode:" in text
    assert "Execution:" in text


def test_project_done_records_guidelines_actually_read() -> None:
    """The report must carry proof the review was grounded, not a claim that it was."""
    text = read_skill("skills/project-done/SKILL.md")

    assert "Guidelines Read:" in text
    assert "Guidelines Skipped:" in text
    assert "guideline paths that were actually read" in text
    # The execution enum has to be able to express the first-class-tool path.
    assert "`<review-tool | subagents | main-agent fallback | docs-light | not reported>`" in text


def test_project_plan_review_loads_project_guidelines() -> None:
    text = read_skill("skills/project-plan/SKILL.md")

    assert "review_guidelines" in text
    assert "verbatim and never parsed" in text
    # Plan review asks a different question from code review, and the reference
    # carries a separate default table for it.
    assert "**플랜 리뷰** table" in text
    assert "the code does not exist yet" in text
    # No second copy of the table here.
    assert "| architect |" not in text, "the default-role table was copied back in"
    assert "not reproduced here" in text
    # Same closed chain as project-start; no second, divergent copy of the rules.
    assert "project-start` §8-B" in text


def test_default_review_roles_are_declared_once() -> None:
    """One canonical table. The first attempt had three copies, already divergent
    at birth — the reference said the architect looks at 범위 준수 while
    project-plan said extensibility, in the same commit that wrote the rule
    forbidding copies."""
    reference = read_skill("skills/_shared/references/review-guidelines.md")

    assert "여기가 정본이다" in reference
    # Both review kinds are covered, and they differ on purpose.
    assert "**구현 리뷰**" in reference and "**플랜 리뷰**" in reference
    assert reference.count("| architect |") == 2
    assert reference.count("| implementer |") == 2
    assert reference.count("| tester |") == 2

    # Each role's default focus is pinned. Dropping the architect or the
    # implementer row used to leave the whole suite green.
    impl_review = reference.split("**구현 리뷰**", 1)[1].split("**플랜 리뷰**", 1)[0]
    assert "아키텍처 적합성, 기존 패턴과의 일관성, 범위 준수" in impl_review
    assert "로직 결함, 보안, 엣지 케이스" in impl_review
    assert "가드가 변이로 검증됐는지" in impl_review

    plan_review = reference.split("**플랜 리뷰**", 1)[1]
    assert "확장성" in plan_review
    assert "구현 실현 가능성" in plan_review
    assert "각 DoD 항목이 실제로 실패할 수 있는지" in plan_review

    # The mutation duty is stated as a step-level obligation, not as one cell of
    # the tester row — a project that renames the role must not shed it.
    assert "변이 검증 의무는 역할 선언과 무관하게 남는다" in reference
    assert "아무도 안 지는 상태는 허용되지 않는다" in reference

    # And nowhere else holds a copy of the table.
    for skill in ("project-start", "project-plan", "project-done"):
        body = read_skill(f"skills/{skill}/SKILL.md")
        assert "| architect |" not in body, f"{skill} copied the role table"


def test_review_guidelines_reference_defines_injection() -> None:
    text = read_skill("skills/_shared/references/review-guidelines.md")

    assert "# 리뷰 가이드라인 주입 (`review_guidelines`)" in text
    # The key itself stays in the common key table so it is discoverable.
    assert "| `review_guidelines` |" in read_skill("skills/SKILL-CONFIG.md")

    # The schema the skills read.
    for token in ("common:", "roles:", "docs:", "focus:"):
        assert token in text

    # Neutrality: focus is transported, never interpreted; roles are not fixed.
    assert_rule(text, "파싱하지 말 것", starts_with="- **`focus` 를 파싱하지 말 것.**")
    assert_rule(text, "역할 이름을 고정하지 말 것", starts_with="- **역할 이름을 고정하지 말 것.**")
    # Degradation is loud and never skips the review.
    assert "경고 후 건너뛴다" in text
    assert "리뷰를 건너뛰지 않는다" in text
    # The mutation duty survives a project override.
    assert "가드가 변이로 검증됐는지" in text
    # AGENTS.md holds a pointer, never a copy.
    assert "AGENTS.md" in text
    assert "내용을 복제하지 않는다" in text


def test_skill_config_defines_single_cli_address() -> None:
    text = read_skill("skills/SKILL-CONFIG.md")

    # harness_cli is the single entry point; project_py is documented only as the
    # cross-repo backward-compat entry, never an in-repo fallback layer.
    assert "단일 진입점" in text
    assert "크로스 레포" in text
    # The fallback chain is harness_cli -> gh, with no project.py layer between.
    assert "project.py` 계층은 없다" in text


def test_no_skill_invokes_project_py_as_a_command() -> None:
    # Every in-repo command converges on <harness_cli>. A `<project_py> <cmd>`
    # invocation would reintroduce the split addressing this plan removes.
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "<project_py>" in line:
                offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "in-repo commands must use <harness_cli>:\n" + "\n".join(offenders)


def test_project_done_clean_temp_goes_through_harness_cli() -> None:
    text = read_skill("skills/project-done/SKILL.md")
    assert "<harness_cli> clean-temp" in text
    assert "<project_py> clean-temp" not in text


def test_project_start_add_progress_is_silent() -> None:
    text = read_skill("skills/project-start/SKILL.md")
    # The command line carries no comment flags; the prose documents them as no-ops.
    assert '<harness_cli> add-progress "<node-id>"\n' in text
    assert "does not post a comment" in text


def test_project_clean_documents_dirty_worktree_guard() -> None:
    text = read_skill("skills/project-clean/SKILL.md")
    assert "skipped_dirty" in text
    assert "Dirty-worktree guard" in text


RELEASE_DOC_SECTIONS = (
    "## Release Summary",
    "## Change Inventory",
    "## Linked Issues",
    "## DB Migrations",
    "## Config Changes",
    "## Risk Assessment",
    "## Deployment Steps",
    "## Rollback Plan",
    "## Post-deploy Verification",
)

RELEASE_FRONTMATTER_KEYS = (
    "schema",
    "package",
    "from_ref",
    "to_ref",
    "risk_level",
    "generated",
)


def test_project_release_doc_skill_contract() -> None:
    text = read_skill("skills/project-release-doc/SKILL.md")

    # skill skeleton shared with the other workflow skills
    for token in (
        "## Trigger Conditions",
        "## Read Settings",
        "## Usage",
        "## Non-execution Guard",
        "## Output Language Guard",
        "## Instructions",
        "## Output",
    ):
        assert token in text

    # canonical document sections (fixed parsing contract)
    for section in RELEASE_DOC_SECTIONS:
        assert section in text

    # machine-layer frontmatter keys, pinned inside the template section itself
    template = text.split("## Release Document Template", 1)[1]
    for key in RELEASE_FRONTMATTER_KEYS:
        assert f"{key}:" in template

    # fixed step shape of the deployment/rollback checklist
    for token in ("### Step 1:", "- [ ] Done", "### R1:"):
        assert token in template

    # version-range resolution: sort, reachability, first-release fallback, dirty tree
    assert "--sort=-v:refname" in text
    assert "merge-base --is-ancestor" in text
    assert "rev-list --max-parents=0" in text
    assert "git status --porcelain" in text

    # risk rubric: levels, evidence duty, project constants delegated to config
    for token in ("| High |", "| Medium |", "| Low |", "critical_globs", "shared_globs"):
        assert token in text
    assert "MUST cite evidence" in text

    # issue lookup degrades to "미확인" instead of aborting; jira ref pattern differs
    assert "미확인" in text
    assert r"[A-Z]+-\d+" in text


def test_release_reference_defines_release_block() -> None:
    text = read_skill("skills/_shared/references/release.md")

    for token in (
        "release.doc_dir",
        "release.tag_format",
        "release.primary_component",
        "release.preflight_paths",
        "release.preflight_commands",
        ".kind",
        ".paths",
        ".cargo_package",
        ".release_with",
        "migrations_globs",
        "config_globs",
        "critical_globs",
        "shared_globs",
        "deploy_steps_template",
        "docs/release",
        "{package}-v{version}",
        ":(glob)",
    ):
        assert token in text


def test_skill_config_keeps_the_tracker_branch_rules() -> None:
    """Tracker branching is common contract — every skill needs it, so it stays."""
    text = read_skill("skills/SKILL-CONFIG.md")

    assert "issue_tracker = forgejo" in text
    assert "forgejo_host" in text
    assert "미확인" in text


def _parse_flat_frontmatter(block: str) -> dict[str, str]:
    """Minimal flat `key: value` parser — the release frontmatter contract is flat."""
    result: dict[str, str] = {}
    for line in block.strip().splitlines():
        key, sep, value = line.partition(":")
        assert sep, f"not a `key: value` line: {line!r}"
        result[key.strip()] = value.strip()
    return result


def test_release_sample_frontmatter_is_parseable() -> None:
    text = read_skill("skills/project-release-doc/SKILL.md")
    sample = text.split("## Mini Korean Sample", 1)[1]
    fence = sample.split("````markdown\n", 1)[1]  # anchor on the sample fence, not on prose
    block = fence.split("---\n", 2)[1]

    try:
        import yaml

        data = yaml.safe_load(block)
    except ModuleNotFoundError:
        data = _parse_flat_frontmatter(block)

    for key in RELEASE_FRONTMATTER_KEYS:
        assert key in data
    assert str(data["schema"]) == "1"
    assert data["risk_level"] in {"high", "medium", "low"}


def test_project_release_preparation_contract() -> None:
    text = read_skill("skills/project-release/SKILL.md")

    for token in (
        "## Trigger Conditions",
        "## Migration Notice",
        "## Read Settings",
        "## External-effect Guard",
        "git status --porcelain",
        "git fetch --no-tags origin <base_branch>",
        'git tag --list "<primary-pattern>" --sort=-version:refname',
        "git ls-remote --tags --refs --sort=-version:refname",
        "REMOTE_TAG_SHA",
        "FROM_SHA",
        "FETCH_HEAD^{}",
        "git merge-base --is-ancestor",
        "cargo metadata --format-version 1",
        "major",
        "minor",
        "patch",
        "skip",
        "미확정",
        "cargo release version",
        "--no-publish",
        "--no-push",
        "--no-commit",
        "--no-tag",
        "git commit",
        "cargo release tag --help",
        "git tag -a",
        "RELEASE_SHA",
        "git reset --hard",
        "publish: 수행하지 않음",
        "push: 수행하지 않음",
        "project-release-doc",
    ):
        assert token in text

    assert "exactly one release commit" in text
    assert "No confirmation means no mutation" in text
    assert "Do not delete already-created tags automatically" in text
    assert "instead of silently switching tools" in text
    assert "Do not use `git fetch --tags`" in text
    assert "git fetch --tags origin <base_branch>" not in text
    assert "all `git log` and `git diff` commands use the resolved immutable" in text
    assert "Local-only ref" in text
    assert "Remote-only ref" in text
    assert "same name but peel to different SHAs" in text
    assert "Older conflicting names" in text


def test_project_release_mixed_level_fixture_is_documented() -> None:
    text = read_skill("skills/project-release/SKILL.md")

    for token in (
        "backend-v1.0.2..864b825",
        "backend: 1.0.2 -> 1.1.0 (minor)",
        "domain: 1.0.2 -> 1.1.0 (minor)",
        "entity: 1.0.2 -> 1.1.0 (minor)",
        "migration: 1.0.2 -> 1.1.0 (minor)",
        "auth-lambda: 1.0.1 -> 1.0.2 (patch)",
        "commit_count: 1",
        "publish: false",
        "push: false",
    ):
        assert token in text


def test_readme_distinguishes_release_workflows() -> None:
    text = read_skill("README.md")

    assert "| `project-release` |" in text
    assert "| `project-release-doc` |" in text
    assert "migration notice" in text
    assert "`project-release`로 버전·commit·tag" in text
    assert "`project-release-doc`으로 릴리즈/배포 문서" in text


def test_release_doc_rename_has_distinct_trigger_and_guard() -> None:
    preparation = read_skill("skills/project-release/SKILL.md")
    document = read_skill("skills/project-release-doc/SKILL.md")

    assert "name: project-release\n" in preparation
    assert "name: project-release-doc\n" in document
    assert "project-release-doc <package> [<from>..<to>]" in document
    assert "project-release <package> [<from>..<to>]" not in document
    assert "Do not run `cargo release`, version bumps, or tag creation" in document


# --------------------------------------------------------------------------
# Prerequisite tool manifest (skills/dependencies.yaml)
#
# The manifest is the single machine-readable declaration; README's table is
# derived from it. These tests are what makes "derived" true instead of
# aspirational — delete an entry from the manifest and the parity test fails.
# --------------------------------------------------------------------------

MANIFEST_PATH = "skills/dependencies.yaml"

# Every CLI guard selects on `kind`, so the set of spellings is part of the
# contract rather than free text.
MANIFEST_KINDS = {"cli", "claude-plugin", "claude-plugin-group", "env-flag"}

# A version probe is an execution surface. Keep the accepted shape narrow.
VERSION_PROBE_FLAGS = {"--version", "version"}

MANIFEST_REQUIRED_FIELDS = (
    "id",
    "kind",
    "requirement",
    "presence",
    "install",
    "probe",
    "degrades",
    "used_by",
)


def _parse_manifest() -> list[dict[str, str]]:
    """Parse the manifest with a real YAML parser.

    An earlier version carried a hand-rolled fallback for hosts without pyyaml.
    It diverged from yaml.safe_load on six realistic edits — including a nested
    `members:` list, which flipped a test's verdict depending on whether pyyaml
    happened to be installed. pyyaml is a declared dev dependency; a second
    parser that disagrees with the first is worse than no fallback.

    The *shell* reader is a separate contract and is tested by running it, in
    tests/test_install_skills.py — not imitated here.
    """
    import yaml

    return yaml.safe_load(read_skill(MANIFEST_PATH))["tools"]


def _min_version_cell(row: dict) -> str:
    """The `최소 버전` value for one row — normalized in exactly one place.

    Both sides go through this. A tool with no declared floor (plugins, env
    flags) reads `-`, and that is the only accepted spelling of "none": an
    empty cell stays empty here and therefore fails against the manifest's
    `-`. Accepting both would make "I forgot to fill the column in" look
    identical to "this tool has no floor".
    """
    return str(row.get("min_version", "-")).strip()


def _parse_readme_prereq_table() -> list[dict[str, str]]:
    text = read_skill("README.md")
    section = text.split("### 전제 도구", 1)[1].split("### ", 1)[0]
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| 도구") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(
            {
                "id": cells[0].strip("`"),
                "requirement": cells[1],
                "install": cells[2].strip("`"),
                "degrades": cells[3],
                # A row that predates the column must fail readably ("the cell
                # is empty"), not raise IndexError — an exception reads as a
                # broken test rather than a missing column.
                "min_version": cells[4] if len(cells) > 4 else "",
            }
        )
    return rows


def _manifest_by_id() -> dict[str, dict[str, str]]:
    return {t["id"]: t for t in _parse_manifest()}


def test_dependency_manifest_declares_both_presence_and_probe() -> None:
    """Two axes, not one.

    "installed on this machine" and "reachable by the agent running right now"
    are different questions — the same CLI is reachable from a terminal-launched
    session and silently absent from a Desktop-launched one. A manifest that
    only carried presence would re-encode that bug as a contract.
    """
    tools = _parse_manifest()
    assert tools, "manifest declares no tools"

    for tool in tools:
        for field in MANIFEST_REQUIRED_FIELDS:
            assert field in tool, f"{tool.get('id')} is missing `{field}`"
            # Not `str(tool[field]).strip()`: a key with no value parses as
            # None and `str(None)` is non-empty, so that spelling accepts the
            # empty declaration it is meant to reject.
            value = tool[field]
            assert isinstance(value, str) and value.strip(), (
                f"{tool.get('id')} has an empty or non-string `{field}`: {value!r}"
            )
        assert tool["requirement"] in {"required", "optional"}

    # A group entry needs its members, or the "any one satisfies it" check is empty.
    for tool in tools:
        if tool["presence"] == "installed_plugins_any":
            assert tool.get("members"), f"{tool['id']} declares a group with no members"


def test_readme_prerequisite_table_matches_manifest() -> None:
    """README's table is derived. Divergence is a failure, not a style nit."""
    manifest_rows = _parse_manifest()
    readme_rows = _parse_readme_prereq_table()

    # Build the dicts only after checking for duplicates — `{r["id"]: r}` would
    # silently keep the last of two rows claiming the same tool.
    for label, rows in (("manifest", manifest_rows), ("README", readme_rows)):
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids)), f"duplicate ids in {label}: {ids}"

    manifest = {t["id"]: t for t in manifest_rows}
    readme = {r["id"]: r for r in readme_rows}

    assert set(manifest) == set(readme), (
        "README prerequisite table and skills/dependencies.yaml disagree.\n"
        f"  manifest only: {sorted(set(manifest) - set(readme))}\n"
        f"  README only:   {sorted(set(readme) - set(manifest))}"
    )

    for tool_id, row in readme.items():
        for field in ("requirement", "install", "degrades"):
            assert row[field] == manifest[tool_id][field], (
                f"README row `{tool_id}` field `{field}` diverged from the manifest"
            )
        assert _min_version_cell(row) == _min_version_cell(manifest[tool_id]), (
            f"README row `{tool_id}` minimum version "
            f"{_min_version_cell(row)!r} diverged from the manifest "
            f"{_min_version_cell(manifest[tool_id])!r}"
        )


def test_cli_tools_declare_a_version_floor_and_a_probe() -> None:
    """A CLI without a measured probe command is a CLI that gets misjudged.

    `fj --version` exits non-zero; `fj version` is the answer. Inferring the
    command reports an installed tool as missing, which is the exact failure
    this manifest exists to stop. The floor and the probe are declared per
    tool, never derived.
    """
    tools = _parse_manifest()
    clis = [t for t in tools if t["kind"] == "cli"]
    assert clis, "the manifest declares no CLI at all"

    # Every guard in this file selects CLIs with `kind == "cli"`, so an
    # unconstrained `kind` means one typo (`CLI`, `cli-tool`) silently removes a
    # tool from all of them while the script — which keys off `presence` — still
    # reports it. Demonstrated: `kind: CLI` plus a reverted `fj --version` left
    # the whole suite green.
    for tool in tools:
        assert tool["kind"] in MANIFEST_KINDS, (
            f"{tool['id']} declares kind {tool['kind']!r}, which no guard here selects; "
            f"known kinds are {sorted(MANIFEST_KINDS)}"
        )
        # The reverse implication. Without it, `kind` alone decides whether a
        # row is guarded, and `presence: on_path` is what the script acts on.
        if tool["presence"] == "on_path":
            assert tool["kind"] == "cli", (
                f"{tool['id']} is resolved by PATH lookup but declares kind {tool['kind']!r}"
            )

    for tool in clis:
        assert tool["presence"] == "on_path", (
            f"{tool['id']} is a CLI but its presence check is {tool['presence']!r}"
        )
        for field in ("min_version", "version_probe"):
            assert field in tool, f"{tool['id']} is missing `{field}`"
            value = tool[field]
            # Ask for the type, not for truthiness. `str(value).strip()` passes
            # for `None` — a mutation pass caught this exact assertion letting
            # an emptied `version_probe:` through. Both traps are YAML's:
            # a key with no value is None, and unquoted `3.11` is a float that
            # every later string comparison silently mishandles.
            assert isinstance(value, str), (
                f"{tool['id']} declares `{field}` as {value!r} "
                f"({type(value).__name__}); it must be a quoted, non-empty string"
            )
            assert value.strip(), f"{tool['id']} has an empty `{field}`"

        # A floor is printed verbatim to users and compared against pyproject
        # for python3. Unconstrained, `min_version: "banana"` passes.
        assert re.fullmatch(r"\d+(\.\d+){1,2}", tool["min_version"]), (
            f"{tool['id']} declares min_version {tool['min_version']!r}, "
            "which is not a dotted version"
        )

        # The probe is executed — by the local probe test, and by agents, which
        # `skills/SKILL-CONFIG.md` now points at this field. So its *shape* is
        # checked here, where it runs on every host, and not only in the
        # execution test that CI skips. `argv[0] == id` alone is not a boundary:
        # `git -c alias.v=!touch f v` satisfies it and still runs `touch`.
        probe = tool["version_probe"]
        assert not set(probe) & set("|;&$()<>`\n\\"), (
            f"{tool['id']} declares a version_probe containing shell metacharacters: {probe!r}"
        )
        argv = probe.split()
        assert argv[0] == tool["id"], (
            f"{tool['id']} declares a version_probe that invokes {argv[0]!r}"
        )
        assert len(argv) == 2 and argv[1] in VERSION_PROBE_FLAGS, (
            f"{tool['id']} declares version_probe {probe!r}; it must be the tool "
            f"plus one of {sorted(VERSION_PROBE_FLAGS)}. Widen this deliberately "
            "if a tool ever needs more — an argument list is an execution surface."
        )

        # CLI install is a docs URL, not a runnable command. `|` would shift the
        # README table's cells; trailing punctuation rides into the script's
        # output and the table cell verbatim.
        install = tool["install"]
        assert install.startswith("http"), (
            f"{tool['id']} declares install {install!r}; CLI rows carry an official docs URL"
        )
        assert "|" not in install, f"{tool['id']} install contains `|`, which breaks the README table"
        assert install[-1] not in ".,", f"{tool['id']} install ends in punctuation: {install!r}"


def test_python_floor_matches_pyproject() -> None:
    """The same floor is stated in two files. Let them disagree and the
    manifest starts describing a Python this package will not install on."""
    import tomllib

    from harness_core.preflight import _minimum_python_version

    requires_python = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["requires-python"]

    # One parser for both sides — a second one would be a third statement of
    # the same fact, free to drift from the first two.
    packaged = _minimum_python_version(requires_python)
    declared = _minimum_python_version(">=" + _manifest_by_id()["python3"]["min_version"])

    # `_minimum_python_version` returns None when its regex misses. Without
    # this, a pyproject moved to `~=3.11` and a mistyped floor both parse to
    # None and compare equal while the two files disagree.
    assert packaged is not None, f"could not parse requires-python {requires_python!r}"
    assert declared is not None, "could not parse the manifest python3 floor"
    assert declared == packaged, (
        f"skills/dependencies.yaml declares python3 >= {declared} but "
        f"pyproject.toml requires-python is {requires_python!r}"
    )


def test_gh_minimum_is_stated_once_and_cited() -> None:
    """The gh floor lives in prose in one reference file, with its reason.

    Pinned two ways: the number must match the manifest, and it must appear
    exactly once — a fourth copy of the same fact is how the first three
    diverged. The number is read from the manifest, never typed here.
    """
    floor = _manifest_by_id()["gh"]["min_version"]
    reference = "skills/_shared/references/github-issue-fields.md"
    text = read_skill(reference)

    # Delimited, not a substring: `count("2.97")` is 1 against the prose's
    # "2.97.0", so shortening the manifest floor to a prefix used to pass.
    delimited = rf"(?<![\d.]){re.escape(floor)}(?![\d.])"
    occurrences = len(re.findall(delimited, text))
    assert occurrences == 1, (
        f"gh minimum {floor!r} appears {occurrences} time(s) in {reference}; "
        "it must be stated exactly once there and must match skills/dependencies.yaml"
    )

    # And repo-wide: the number is also stated in project-issue and
    # project-start. The earlier version of this test checked one file while
    # its docstring claimed "exactly once", so bumping the floor everywhere the
    # red tests pointed still left two stale copies behind.
    stale = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if not re.search(r"(?<![A-Za-z0-9_])gh(?![A-Za-z0-9_])", line):
                continue
            for stated in re.findall(r"\d+\.\d+\.\d+", line):
                if stated != floor:
                    stale.append(f"{md.relative_to(ROOT)}:{lineno}: states {stated}")
    assert not stale, (
        f"a gh version other than the declared floor {floor} is stated in the shared layer:\n"
        + "\n".join(stale)
    )
    # A version floor with no reason attached is a number nobody can revise.
    assert "cli/cli#13807" in text, (
        "the gh minimum lost its citation; state what the release changed"
    )


def test_preflight_required_tools_are_declared() -> None:
    """Coverage in one direction only, and that is the whole claim.

    `harness_core.preflight` gates scaffolding on its own hardcoded tool list.
    This asserts every tool it demands is declared in the manifest, so the two
    lists cannot drift apart silently.

    What it does NOT catch: `preflight._check_tool` still hardcodes
    `--version` for every tool and never reads `version_probe`. Widen
    `DEFAULT_REQUIRED_TOOLS` to include `fj` and preflight will call
    `fj --version`, get a non-zero exit, and report an installed tool as
    unusable — with this test still green. That is a known follow-up, not
    something this assertion fixes.
    """
    from harness_core.preflight import DEFAULT_REQUIRED_TOOLS

    declared = {t["id"] for t in _parse_manifest() if t["kind"] == "cli"}
    undeclared = sorted(set(DEFAULT_REQUIRED_TOOLS) - declared)

    assert not undeclared, (
        f"preflight requires {undeclared} but skills/dependencies.yaml does not declare "
        f"them; declared CLIs are {sorted(declared)}"
    )


def test_readme_prerequisite_table_has_no_shifted_columns() -> None:
    """The header is not derived, only the data rows are.

    Dropping `최소 버전` from the header while leaving eleven 5-cell data rows
    renders a shifted table and left the suite green — the DoD relegated this
    to manual review, which is the one thing this ticket's design refuses to
    rely on everywhere else.
    """
    text = read_skill("README.md")
    section = text.split("### 전제 도구", 1)[1].split("### ", 1)[0]

    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|") and not set(line.strip()) <= set("|- ")
    ]
    assert rows, "no prerequisite table found"

    header, *body = rows
    assert header[0] == "도구" and header[-1] == "최소 버전", (
        f"prerequisite table header changed shape: {header}"
    )
    for row in body:
        assert len(row) == len(header), (
            f"row {row[0]!r} has {len(row)} cells but the header has {len(header)}"
        )


def test_readme_separates_presence_from_probe() -> None:
    text = read_skill("README.md")
    section = text.split("### 전제 도구", 1)[1].split("### ", 1)[0]

    assert "**presence**" in section
    assert "**probe**" in section
    # The report is not a gate — Codex and CI run with none of these installed.
    assert "exit 0" in section
    assert "게이트가 아니다" in section


def test_install_script_is_guarded_behaviourally_not_by_grep() -> None:
    """This file greps documents; the script is guarded by running it.

    An earlier version of this test grepped install-skills.sh for vocabulary.
    A review proved it vacuous: deleting the whole feature, or adding
    `eval "$inst"` so the script ran installs, both left it green. The real
    guards live in tests/test_install_skills.py, which executes the script.
    Pin that file's existence so the coverage cannot quietly go away.
    """
    behavioural = ROOT / "tests" / "test_install_skills.py"
    assert behavioural.exists(), "install-skills.sh lost its behavioural tests"

    text = behavioural.read_text(encoding="utf-8")
    assert "subprocess.run" in text, "the tests must run the script, not read it"
    for claim in (
        "def test_the_script_never_executes_an_install_command",
        "def test_a_manifest_id_cannot_execute_code",
        "def test_missing_tools_are_reported_and_exit_is_still_zero",
        "def test_no_plugin_database_is_a_skip_not_a_finding",
        "def test_a_partially_read_manifest_is_reported_loudly",
    ):
        assert claim in text, f"{claim} is missing"


# --------------------------------------------------------------------------
# Host neutrality (skills/_shared/references/codex.md)
#
# Codex is still a consumer. Its instructions were moved out of the skill
# bodies, not deleted — a grep proving the bodies are clean means nothing
# unless the same tokens are provably still readable somewhere.
# --------------------------------------------------------------------------

CODEX_REFERENCE = "skills/_shared/references/codex.md"


def test_skill_bodies_carry_no_host_specific_mechanism() -> None:
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        if md == ROOT / CODEX_REFERENCE:
            continue
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for token in ("In Codex", "Codex receives", "require_escalated",
                          "multi_agent_v1", "$project-"):
                if token in line:
                    offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {token}")
    assert not offenders, (
        "host-specific mechanisms belong in " + CODEX_REFERENCE + ":\n"
        + "\n".join(offenders)
    )


def test_codex_reference_still_carries_what_was_moved() -> None:
    """Moved, not deleted. Every mechanism removed above is readable here."""
    text = read_skill(CODEX_REFERENCE)

    for token in (
        "require_escalated",
        "multi_agent_v1.spawn_agent",
        "exec_command",
        "$project-start <issue-id> [worktree] [adr]",
        "$project-release-doc <package> [<from>..<to>]",
    ):
        assert token in text, f"{token} was deleted rather than moved"

    # Every skill's invocation must be listed, or a Codex user loses a skill.
    for skill_dir in sorted((ROOT / "skills").glob("project-*")):
        assert f"${skill_dir.name}" in text, f"{skill_dir.name} missing from the reference"

    # The rules that hold on every host are repeated here, not replaced by
    # Codex-only ones — that inversion is what made the old structure unreadable.
    assert "Never run `codex`, `claude`, or any other LLM CLI" in text
    assert "moved here" in text and "not deleted" in text


def test_skill_config_points_at_the_host_reference() -> None:
    """One pointer every skill reaches — all of them read SKILL-CONFIG first."""
    text = read_skill("skills/SKILL-CONFIG.md")

    assert "## 호스트별 참조" in text
    assert CODEX_REFERENCE.replace("skills/", "") in text
    assert "호스트 중립" in text


# --------------------------------------------------------------------------
# Progressive disclosure of the config document
#
# Every skill used to read SKILL-CONFIG.md whole, including the halves that did
# not apply to it. The split is a *path contract*: a skill names the references
# it needs, and those files exist. These tests are what keeps the split from
# decaying into dangling pointers.
# --------------------------------------------------------------------------

REFERENCE_DIR = "skills/_shared/references"

# What each skill actually consumes, asserted against what it declares.
SKILL_REFERENCE_NEEDS = {
    "project-adr": {"worktree"},
    "project-clean": {"base-branch", "worktree"},
    "project-done": {"review-guidelines", "base-branch", "hooks", "worktree", "github-issue-fields"},
    "project-harness-init": {"base-branch"},
    "project-harness-update": set(),
    "project-issue": {"base-branch", "github-issue-fields"},
    "project-iterate": set(),
    "project-plan": {"review-guidelines", "base-branch"},
    "project-release": {"release", "base-branch"},
    "project-release-doc": {"release"},
    "project-start": {"review-guidelines", "base-branch", "hooks", "worktree", "github-issue-fields"},
}


def _declared_references(skill: str) -> set[str]:
    text = read_skill(f"skills/{skill}/SKILL.md")
    return set(re.findall(r"_shared/references/([a-z-]+)\.md(?![a-z])", text)) - {"codex"}


def test_every_declared_reference_exists() -> None:
    r"""A pointer to a file that is not there is worse than no pointer.

    Match the whole filename, extension included. An earlier version matched
    `\.md` without a boundary, so a pointer renamed to `hooks.markdown` was read
    as `hooks` and reported as valid.
    """
    dangling: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for fname in re.findall(r"_shared/references/([A-Za-z0-9_.-]+)", md.read_text(encoding="utf-8")):
            fname = fname.rstrip(".,:;`)")
            if not (ROOT / REFERENCE_DIR / fname).exists():
                dangling.append(f"{md.relative_to(ROOT)} -> {fname}")
    assert not dangling, "dangling reference pointers:\n" + "\n".join(dangling)


def test_skills_declare_exactly_the_references_they_use() -> None:
    """Declaring too few breaks the skill; declaring too many undoes the split."""
    for skill, expected in SKILL_REFERENCE_NEEDS.items():
        assert _declared_references(skill) == expected, (
            f"{skill} declares {sorted(_declared_references(skill))}, "
            f"expected {sorted(expected)}"
        )


def test_project_clean_does_not_read_the_release_block() -> None:
    """The 53-line skill paid the same price as the rest. That was the point."""
    assert "release" not in _declared_references("project-clean")


def test_skill_config_indexes_every_reference() -> None:
    text = read_skill("skills/SKILL-CONFIG.md")
    assert "## 참조 파일" in text
    for ref in sorted((ROOT / REFERENCE_DIR).glob("*.md")):
        assert f"_shared/references/{ref.name}" in text, f"{ref.name} is not indexed"


def test_references_are_self_describing() -> None:
    """Every reference states its provenance, so none is read as an orphan.

    Two provenances exist and both count: a file *split out of* SKILL-CONFIG.md,
    and a file written directly as a reference. Asserting only the split wording
    would push a newly written reference to claim a history it does not have.
    """
    origins = ("Split out of skills/SKILL-CONFIG.md", "Referenced from skills/SKILL-CONFIG.md")
    for ref in sorted((ROOT / REFERENCE_DIR).glob("*.md")):
        if ref.name == "codex.md":
            continue
        text = ref.read_text(encoding="utf-8")
        assert any(origin in text for origin in origins), (
            f"{ref.name} states no provenance; expected one of {origins}"
        )
        assert text.count("\n# ") + text.startswith("# ") >= 1, f"{ref.name} has no title"


# --------------------------------------------------------------------------
# Host- and language-dependent assumptions
#
# These are contracts, not cleanups. `cmux rename-tab` was not dead code — it
# worked from a terminal-launched session and silently no-opped from a
# Desktop-launched one. A step whose result depends on the host, without
# surfacing that it did nothing, does not belong in a shared skill.
# --------------------------------------------------------------------------


def test_shared_skills_carry_no_host_or_language_command() -> None:
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for token in ("cmux", "cargo fmt"):
                if token in line:
                    offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {token}")
    assert not offenders, (
        "shared skills must not carry a host- or language-specific command "
        "(installed or not — this is the contract):\n" + "\n".join(offenders)
    )


def test_tab_naming_step_is_gone_not_replaced() -> None:
    """Deleted, not swapped for another host's session-naming API.

    A tab name is a terminal multiplexer's convenience, not an output of the
    workflow. Re-adding it through a different host API recreates the same
    silent no-op under Codex, CI, and headless runs.
    """
    text = read_skill("skills/project-start/SKILL.md")

    assert "**2-C." not in text

    # Structural, not a blocklist: the step numbering between worktree creation
    # and the issue transition must have no step in it at all. A renamed
    # reintroduction ("**2-D. Name the session**") walks past a word blocklist.
    between = text[text.index("**2-B."):text.index("**3. Issue status")]
    extra = re.findall(r"^\*\*(2-[A-Z])\.", between, re.MULTILINE)
    assert extra == ["2-B"], f"a step reappeared between worktree setup and step 3: {extra}"

    # And the concept itself, however spelled.
    for token in ("rename-tab", "set-tab", "set-title", "tab name", "tab title",
                  "session name", "name the session", "pane title"):
        assert token not in text.lower(), f"tab naming came back as {token!r}"
    # Later step numbers must not shift — other skills reference them by number.
    assert "**3. Issue status -> In Progress**" in text
    assert "**7. Formatting before commit**" in text
    assert "**8. Adaptive Review**" in text


def test_formatting_step_survives_with_the_command_injected() -> None:
    """The opposite treatment from cmux: the step stays, the command leaves."""
    text = read_skill("skills/project-start/SKILL.md")

    assert "**7. Formatting before commit**" in text
    assert "hooks:\n  pre_commit:" in text
    assert "carries no formatter of its own" in text
    # Absent hook is a silent skip, not a guessed default.
    assert "skip this step silently" in text


def test_hooks_reference_declares_pre_commit_failure_policy() -> None:
    text = read_skill("skills/_shared/references/hooks.md")

    assert "| `pre_commit` |" in text
    assert "`post_start` / `pre_commit` / `post_done` 실패 시: 경고 출력 후 계속" in text
    # The reason the policy is "warn", not "stop", is recorded — not just the policy.
    assert "포맷은 정확성 게이트가 아니고" in text
    # And the rule that stops the next person from re-adding a language constant.
    assert "어떤 언어의 포맷 명령도 넣지 않는다" in text


def test_readme_names_no_consumer_project() -> None:
    """This skillset is meant to be published; the README is its front door.

    An earlier revision put the FE repo's rename date and a dormant repo's name
    in the README as a note for teammates. That is internal coordinate data, and
    a public README is the wrong place for it — the shared layer already refuses
    to know which projects consume it (see the guard below), so the README must
    not reintroduce that knowledge in prose.
    """
    readme = read_skill("README.md")

    leaked: list[str] = []
    for lineno, line in enumerate(readme.splitlines(), 1):
        for token in INTERNAL_TOKENS:
            if token in line:
                leaked.append(f"README.md:{lineno}: {token}")
    assert not leaked, "internal project information in a public README:\n" + "\n".join(leaked)

    # The replacement states the principle instead of the instances.
    assert "소비 프로젝트의 이름·경로·브랜치 같은 상수는 이 저장소에 두지 않는다" in readme


def test_config_reading_is_described_as_an_action_not_a_tool() -> None:
    """Naming one host's tool pins a shared skill to that host."""
    text = read_skill("skills/SKILL-CONFIG.md")
    assert "Read 도구로" not in text
    assert "`.claude/skill-config.yaml` 을 읽는다." in text


# --------------------------------------------------------------------------
# Feedback that was recorded but never landed in a skill
# --------------------------------------------------------------------------


def test_project_plan_searches_symbols_before_text() -> None:
    """Structural duplicates have different names; text search will not find them."""
    text = read_skill("skills/project-plan/SKILL.md")

    assert "**2-A. Search for duplicates, symbols first**" in text
    assert "LSP" in text
    assert "definition, references, implementations" in text
    # Text search is the complement, not the primary.
    assert "Then text-level" in text
    # Losing the tool must change the plan's claims, not just the method.
    assert "structural duplicates may have been missed" in text
    assert "skills/dependencies.yaml" in text
    # Extend by default; creating anew is a decision that must be argued.
    assert "extending it is the default" in text


def test_project_done_verifies_ci_before_reporting_complete() -> None:
    """A PR URL is not an outcome. An unread check is an unknown, not a pass."""
    text = read_skill("skills/project-done/SKILL.md")

    assert "**11. Check CI**" in text
    assert_rule(
        text, "while CI is unverified",
        starts_with='- **Do not report "complete" while CI is unverified.**',
    )
    # "no errors" is vacuous: a run that skipped the suite is also green.
    assert "which checks ran" in text
    assert "vacuous" in text
    # Unreadable CI is reported as unknown, never assumed green.
    assert "mark the CI state unknown rather than assuming it passed" in text
    # The final output carries the CI state, so it cannot be quietly omitted.
    assert "**12. Output**" in text
    assert "CI state:" in text


def test_shared_layer_names_no_consumer_project_constant() -> None:
    """The shared skills must not know any project's values.

    Task 4 corrected `cosmos-forge` -> `quantlab-front` in four places rather
    than removing the duplication, so the next rename diverges again. The rule
    both new reference files state — 프로젝트 상수는 skill-config.yaml 에만 —
    has to hold in the tree that states it.
    """
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for name in INTERNAL_TOKENS:
                if name in line:
                    offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {name}")
    assert not offenders, (
        "a consumer project's constants leaked into the shared layer:\n" + "\n".join(offenders)
    )


def test_shared_layer_hardcodes_no_base_branch_name() -> None:
    """`develop` / `main` as a literal default is the same leak by another name."""
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "base" not in line.lower():
                continue
            for literal in ("`develop`", "origin/develop"):
                if literal in line:
                    offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {literal}")
    assert not offenders, (
        "a literal base branch name is pinned in the shared layer:\n" + "\n".join(offenders)
    )


def test_published_surface_names_no_consumer_project() -> None:
    """One guard over everything this repo ships.

    The skillset is meant to be published, so the consuming organization's repo
    names, hosts and addresses must not travel with it. Two files are excluded
    on purpose:

    - `.claude/skill-config.yaml` is this repo's *own* project config. Naming its
      tracker there is the mechanism working as designed — that file is what
      every consumer replaces with their own.
    - `docs/handoff/` records work handed between sessions and cites the issues
      it came from. Whether that history ships is a publishing decision, not a
      contract this test can make.
    """
    excluded = {
        Path(".claude/skill-config.yaml"),
        Path("docs/handoff"),
        Path("tests/test_skill_docs.py"),  # the guard has to name what it blocks
    }

    def is_excluded(rel: Path) -> bool:
        return any(rel == e or e in rel.parents for e in excluded)

    leaked: list[str] = []
    for pattern in ("*.md", "*.py", "*.yaml", "*.yml", "*.sh", "*.toml"):
        for f in sorted(ROOT.rglob(pattern)):
            rel = f.relative_to(ROOT)
            if any(part in {".git", ".task", ".venv", ".claude"} for part in rel.parts):
                if rel != Path(".claude/skill-config.yaml"):
                    continue
            if is_excluded(rel):
                continue
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                for token in INTERNAL_TOKENS:
                    if token in line:
                        leaked.append(f"{rel}:{lineno}: {token}")

    assert not leaked, (
        "consumer-organization names in the published surface:\n" + "\n".join(leaked)
    )


# --------------------------------------------------------------------------
# Documented `gh` invocations
#
# A fallback command is only a fallback if it runs. The skills document `gh`
# lines that no test ever executed, so a flag that does not exist (or that was
# renamed by a gh release) read as a working procedure right up until a session
# tried it. These tests resolve every documented flag against a committed
# snapshot of the real `gh --help` surface.
#
# The snapshot is a fixture, not a live probe: CI has no `gh`, and a test that
# skips on the host that runs it is not a gate. `gen_gh_flags.py` regenerates it
# from a real `gh`; the stale check below is what surfaces the drift, locally.
# --------------------------------------------------------------------------

GH_FLAGS_FIXTURE = ROOT / "tests" / "fixtures" / "gh_flags.yaml"

# Where documented `gh` commands are checked. Bounded on purpose: these are the
# files that carry the GitHub tracker procedure.
GH_DOC_PATHS = (
    "skills/project-issue/SKILL.md",
    "skills/project-start/SKILL.md",
    "skills/project-done/SKILL.md",
    "skills/_shared/references/github-issue-fields.md",
)

# A command line, optionally introduced by a `# fallback (GitHub): ` style
# comment. Anchored at line start so prose that merely mentions `gh` — "run it
# with gh this time" — is not parsed as an invocation.
_GH_LINE_RE = re.compile(r"^(?:#[^:]*:\s*)?(gh\s.*)$")


def _load_gh_flags() -> dict:
    import yaml

    return yaml.safe_load(GH_FLAGS_FIXTURE.read_text(encoding="utf-8"))


def _logical_lines(text: str) -> list[str]:
    """Join shell continuation lines (`\\` at end) into one logical line each."""
    joined: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.strip()
        if buffer:
            line = buffer + " " + line
            buffer = ""
        if line.endswith("\\"):
            buffer = line[:-1].strip()
            continue
        joined.append(line)
    if buffer:
        joined.append(buffer)
    return joined


def _gh_invocations(text: str) -> list[str]:
    """Every `gh ...` command line in a document, continuations already joined."""
    found = []
    for line in _logical_lines(text):
        match = _GH_LINE_RE.match(line)
        if match:
            found.append(match.group(1))
    return found


def _split_command(invocation: str, known: dict) -> tuple[str | None, list[str]]:
    """Resolve an invocation to a fixture key plus the flags it passes.

    The fixture is the authority on how deep a command nests: `gh api` takes an
    argument where `gh issue create` takes a subcommand, and guessing from token
    shape gets that wrong. Try the two-token key, then the one-token key.
    """
    tokens = invocation.split()
    key = None
    for depth in (3, 2):
        candidate = " ".join(tokens[:depth])
        if candidate in known:
            key = candidate
            break
    flags = [t.split("=", 1)[0] for t in tokens if t.startswith("-") and t != "-"]
    return key, flags


def test_documented_gh_flags_exist() -> None:
    """Every flag written in a documented `gh` command exists on that command."""
    fixture = _load_gh_flags()
    known = fixture["commands"]

    problems: list[str] = []
    for path in GH_DOC_PATHS:
        for invocation in _gh_invocations(read_skill(path)):
            key, flags = _split_command(invocation, known)
            if key is None:
                problems.append(f"{path}: no fixture entry for {invocation!r}")
                continue
            accepted = set(known[key]["long"]) | set(known[key]["short"])
            for flag in flags:
                if flag not in accepted:
                    problems.append(f"{path}: {key} does not accept {flag}")
    assert not problems, (
        "documented gh flags that gh does not accept "
        f"(fixture from {fixture['_gh_version']}):\n" + "\n".join(problems)
    )


def test_every_gh_doc_path_actually_documents_gh() -> None:
    """Guards the scanner itself.

    A regex that silently matches nothing turns this whole section green. If a
    documented procedure stops invoking `gh`, that is a real change to assert
    deliberately — not something to discover by the tests going quiet.
    """
    empty = [path for path in GH_DOC_PATHS if not _gh_invocations(read_skill(path))]
    assert not empty, f"no gh invocation parsed from: {empty}"


def test_gh_flags_fixture_matches_installed_gh() -> None:
    """Local-only staleness check: does the fixture still match this machine's gh?

    Deliberately not a CI gate. Pinning the fixture to whatever version a runner
    happens to install makes an unrelated gh release fail this repo's builds —
    which is exactly what happened: this test was written skipping only on a
    missing `gh`, on the assumption that CI has none. GitHub-hosted runners ship
    `gh` preinstalled, so the check ran there and failed on a newer build that
    had merely *added* a flag. The `CI` skip is the actual guard; the
    `which` skip only covers a developer machine without gh.

    The companion test that *is* a gate is `test_documented_gh_flags_exist`: it
    resolves the documented flags against the committed fixture and needs no gh
    at all. A newer gh adding flags cannot break it, which is the property that
    keeps the fixture useful offline.
    """
    import os
    import shutil

    import pytest

    if os.environ.get("CI"):
        pytest.skip("staleness is a local signal; a runner's gh version is not this repo's")
    if shutil.which("gh") is None:
        pytest.skip("gh is not installed on this host")

    sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
    try:
        import gen_gh_flags
    finally:
        sys.path.pop(0)

    fixture = _load_gh_flags()
    stale: list[str] = []
    for command, expected in fixture["commands"].items():
        longs, shorts = gen_gh_flags.flags_for(command)
        if longs != expected["long"] or shorts != expected["short"]:
            stale.append(
                f"{command}: fixture {expected['long']}/{expected['short']} "
                f"vs installed {longs}/{shorts}"
            )
    assert not stale, (
        f"tests/fixtures/gh_flags.yaml was generated from {fixture['_gh_version']} "
        "and no longer matches the gh on this machine. Regenerate it:\n"
        "  .venv/bin/python tests/fixtures/gen_gh_flags.py\n" + "\n".join(stale)
    )


# --------------------------------------------------------------------------
# The GitHub issue metadata contract
#
# The drift these guard against was not a session's mistake — the skills
# *instructed* it. `gh issue edit --add-label "in-progress"` put a workflow
# state in a label, and the issue-creation step inferred priority and size into
# a second call that nothing forced anyone to make.
# --------------------------------------------------------------------------


def test_project_issue_forbids_metadata_in_labels() -> None:
    text = read_skill("skills/project-issue/SKILL.md")

    assert_rule(
        text, "Never encode type, priority, or size as a label",
        starts_with="- Never encode",
    )
    # The reserved names are derived, so the skill must not carry a list of them.
    assert "derived at runtime" in text


def test_project_issue_creates_in_one_call() -> None:
    """`add-backlog` as a required second call is the failure mode itself.

    A step that can be skipped without anything noticing will be skipped; the
    observed drift came from exactly that. Type, labels, priority, size and the
    initial status go in the one call that also creates the issue.
    """
    text = read_skill("skills/project-issue/SKILL.md")

    create = text.split("**6. Create Issue**", 1)[1].split("### Jira", 1)[0]
    assert "<harness_cli> create-issue" in create
    for flag in ("--type", "--label", "--priority", "--size"):
        assert flag in create, f"the single create call does not pass {flag}"

    # add-backlog survives only as the deliberate --no-project follow-up.
    backlog = rule_line(text, "add-backlog")
    assert "--no-project" in backlog, (
        f"add-backlog is still documented as a routine second call: {backlog!r}"
    )


def test_project_issue_handles_partial_failure_without_recreating() -> None:
    assert_rule(
        read_skill("skills/project-issue/SKILL.md"),
        "On exit 3 the issue already exists",
        starts_with="- On exit 3",
    )


def test_project_issue_documents_the_unknown_create_outcome() -> None:
    """Exit 4 exists because `gh` exiting non-zero does not mean nothing was made.

    A skill that only knows 0/2/3 reads a 4 as an unhandled failure, and the
    generic recovery for that is to try again — which is the duplicate issue the
    code path was split to prevent.
    """
    text = read_skill("skills/project-issue/SKILL.md")

    assert_rule(
        text, "whether the issue exists",
        starts_with="- **4**",
    )
    assert_rule(
        text, "searched the repository for the title",
        starts_with="- On exit 4",
    )


def test_an_environment_refusal_does_not_fall_back_to_bare_gh() -> None:
    """The fallback carries no reserved-label judgement, so reaching it on a
    refusal reopens the defect the refusal exists to close — one layer up."""
    assert_rule(
        read_skill("skills/project-issue/SKILL.md"),
        'is **not** "the harness call failed"',
        starts_with="- An environment refusal",
    )
    assert_rule(
        read_skill("skills/_shared/references/github-issue-fields.md"),
        "는 호출이 성립하지 않은 경우다",
        starts_with="**\"실패\" 는 호출이 성립하지 않은 경우다.**",
    )


def test_project_issue_reports_observed_metadata() -> None:
    text = read_skill("skills/project-issue/SKILL.md")
    assert "**7. Read Back**" in text
    assert "not the values inferred" in text


def test_status_transitions_write_a_project_field_not_a_label() -> None:
    """The two skills that were instructing the drift directly."""
    start = read_skill("skills/project-start/SKILL.md")
    done = read_skill("skills/project-done/SKILL.md")

    assert_rule(
        start, '--field Status --value "<status_names.in_progress>"',
        starts_with="# fallback (GitHub): gh project item-edit",
    )
    assert_rule(
        done, '--field Status --value "<status_names.in_review>"',
        starts_with="# fallback (GitHub): gh project item-edit",
    )

    for name, text in (("project-start", start), ("project-done", done)):
        for label in ('--add-label "in-progress"', '--add-label "in-review"'):
            assert label not in text, f"{name} still writes a workflow state as a label: {label}"
        assert "not applied" in text, f"{name} does not say what happens when the write fails"


def test_readme_lists_trackers_module() -> None:
    """The adapter is opt-in, and a reader has to be able to learn that here.

    "It is in harness_core" reads as "it is already registered" — which is the
    one thing that must not be true of a tracker-specific command set.
    """
    text = read_skill("README.md")

    assert "trackers/github" in text
    assert "opt-in 어댑터" in text
    assert "register_github_commands" in text

    row = rule_line(text, "| `project-issue` |")
    assert "create-issue" in row, (
        f"the README still describes issue registration as tracker-shaped only: {row!r}"
    )


# --------------------------------------------------------------------------
# The forgejo (`fj`) command surface
#
# No fixture backs these the way `gh_flags.yaml` backs gh, deliberately. A
# fixture answers "does this flag exist", and a flag fj does not have fails
# loudly with a non-zero exit. Every failure guarded here is *silent*: omitting
# both `--body` and `--body-file` opens `$EDITOR` and hangs a headless run;
# `--web` opens a browser; a label that does not exist is refused with exit 0,
# an empty stderr, and the warning on stdout. Shape is what catches those.
#
# These guards were rewritten once already. The first draft asserted substring
# presence and an adversarial pass walked past twenty of them — deleting the
# isolate strip, exposing the title to command substitution, and turning a
# label add into a silent `--rm`, all with the suite green. Where a guard below
# looks pedantic about *position* or *argument role* rather than presence, that
# is why. Presence is what a mutation edits around.
# --------------------------------------------------------------------------

# Files that carry a forgejo procedure. Bounded like GH_DOC_PATHS, and asserted
# non-empty below: a scanner that quietly stops seeing a file takes every guard
# that reads it green.
FJ_DOC_PATHS = (
    "skills/project-issue/SKILL.md",
    "skills/SKILL-CONFIG.md",
    "skills/project-release-doc/SKILL.md",
)

# An fj call, however the surrounding document dresses it: a `# fallback: `
# comment, a `$ ` prompt, a list bullet, a `VAR="$(` capture, or inline
# backticks mid-sentence. The first draft anchored on a bare line start, and
# SKILL-CONFIG.md — which documents two real fj calls inside backticks — was
# invisible to every guard here. A `--web` create could be added there with the
# suite staying green.
_FJ_LINE_RE = re.compile(
    r"^(?:[-*>]\s+)?"
    r"(?:#[^:]*:\s*)?"
    r"(?:\$\s+)?"
    r"(?:(?P<capture>[A-Za-z_][A-Za-z0-9_]*=\"?\$\())?"
    r"(?P<tick>`)?"
    r"(?P<cmd>fj\s.*)$"
)

# Flags that consume the token after them, so an argument-role scan does not
# mistake a flag's value for a positional.
_FJ_VALUE_FLAGS = frozenset({
    "-H", "--host", "-R", "--remote", "-C", "--cwd", "-r", "--repo", "--rm",
    "-a", "--add", "--body", "--body-file", "--template", "--style",
    "-s", "--state", "-l", "--labels", "-c", "--creator", "--assignee",
})


def _fj_invocations(text: str) -> list[str]:
    """Every fj call in a document, continuations joined and wrappers trimmed."""
    found = []
    for line in _logical_lines(text):
        match = _FJ_LINE_RE.match(line)
        if not match:
            continue
        cmd = match.group("cmd")
        if match.group("tick"):
            cmd = cmd.split("`", 1)[0]
        if match.group("capture"):
            cmd = cmd.split(')"', 1)[0]
        for sep in (" || ", " && ", " ; ", " | "):
            cmd = cmd.split(sep, 1)[0]
        found.append(cmd.strip())
    return found


def _all_fj_invocations() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        rel = str(md.relative_to(ROOT))
        for invocation in _fj_invocations(md.read_text(encoding="utf-8")):
            found.append((rel, invocation))
    return found


def _forgejo_section() -> str:
    text = read_skill("skills/project-issue/SKILL.md")
    return text.split("### Forgejo", 1)[1].split("**7. Read Back**", 1)[0]


def _fj_positionals(invocation: str) -> list[str]:
    """Arguments that are not flags and not a flag's value."""
    tokens = invocation.split()
    positionals: list[str] = []
    skip = False
    for index, token in enumerate(tokens):
        if skip:
            skip = False
            continue
        if token.startswith("-"):
            if token in _FJ_VALUE_FLAGS and "=" not in token:
                skip = True
            continue
        positionals.append(token)
    # tokens[0] is `fj`, then the subcommand path (`issue`, `create`, `labels`…).
    return positionals


def test_fj_scanner_sees_every_documented_forgejo_file() -> None:
    """Guards the scanner, per file, the way the gh section does.

    `any(...)` over the whole tree was the first draft, and it let the entire
    read-back block be deleted from the Forgejo section while another file's
    `issue view` kept the assertion satisfied.
    """
    empty = [path for path in FJ_DOC_PATHS if not _fj_invocations(read_skill(path))]
    assert not empty, f"no fj invocation parsed from: {empty}"

    section = _fj_invocations(_forgejo_section())
    for shape in ("issue create", "issue edit", "issue view"):
        assert any(shape in inv for inv in section), (
            f"the Forgejo section no longer invokes `fj {shape}`"
        )


def test_documented_fj_issue_create_always_passes_body_file() -> None:
    """Without it — and without `--body` — fj opens `$EDITOR` and hangs."""
    offenders = [
        f"{path}: {inv}"
        for path, inv in _all_fj_invocations()
        if "issue create" in inv and "--body-file" not in inv
    ]
    assert not offenders, (
        "a documented `fj issue create` would open an editor and hang:\n" + "\n".join(offenders)
    )


def test_no_documented_fj_call_opens_a_browser() -> None:
    offenders = [f"{path}: {inv}" for path, inv in _all_fj_invocations() if "--web" in inv]
    assert not offenders, "a documented fj call opens a web browser:\n" + "\n".join(offenders)


def test_no_documented_fj_call_uses_dash_dash_version() -> None:
    """`fj --version` is an error; `fj version` is the probe."""
    offenders = [f"{path}: {inv}" for path, inv in _all_fj_invocations() if "--version" in inv]
    assert not offenders, (
        "`fj --version` is an error — the probe is `fj version`:\n" + "\n".join(offenders)
    )


def test_forgejo_section_follows_the_jira_section() -> None:
    """`test_project_issue_creates_in_one_call` slices the GitHub branch at
    `### Jira`. A Forgejo section before it falls inside that slice."""
    text = read_skill("skills/project-issue/SKILL.md")

    assert "### Jira" in text and "### Forgejo" in text
    assert text.index("### Jira") < text.index("### Forgejo")


def test_forgejo_section_claims_no_field_it_cannot_write() -> None:
    """fj has no type/priority/size flag, and a label is not a substitute.

    Checking only for the flags missed the bypass this rule exists to stop:
    `labels -a "priority/P1"` passes a flag scan while doing exactly the
    forbidden thing.
    """
    section = _forgejo_section()

    for inv in _fj_invocations(section):
        for flag in ("--type", "--priority", "--size"):
            assert flag not in inv, f"the Forgejo section passes {flag}, which fj lacks: {inv}"

        tokens = inv.split()
        for index, token in enumerate(tokens[:-1]):
            if token in ("-a", "--add"):
                value = tokens[index + 1].strip("\"'").lower()
                for reserved in ("type", "priority", "size"):
                    assert reserved not in value, (
                        f"a metadata field is being smuggled into a label: {inv}"
                    )

    assert_rule(
        section, "셋 다 **미반영**으로 보고하고",
        starts_with="type·priority·size 는 `fj` 에 대응 플래그가 없다",
    )


def test_forgejo_strips_isolates_before_extracting_the_number() -> None:
    """The strip must be a pipe stage *preceding* the extractor.

    Substring presence is not enough, twice over. Deleting the strip and
    appending `# \\x{2068} 는 무시된다` as a comment keeps the codepoints on the
    line; moving the strip *after* the sed keeps them too, and is worse than
    deletion because the document still reads as correct while the extraction
    can never match. Both leave `ISSUE_NUMBER` empty, and Step 8 then renames
    the draft to `plan-.md`.
    """
    lines = [l for l in _logical_lines(_forgejo_section()) if l.startswith("ISSUE_NUMBER=")]
    assert len(lines) == 1, f"expected one ISSUE_NUMBER pipeline, found {len(lines)}"

    stages = lines[0].split("|")
    strip = [i for i, s in enumerate(stages) if "2068" in s and "2069" in s]
    extract = [i for i, s in enumerate(stages) if "created issue #" in s]

    assert strip, "the issue-number pipeline no longer strips the directional isolates"
    assert extract, "the issue-number pipeline no longer extracts the number"
    assert min(strip) < min(extract), (
        "the isolate strip does not precede the extractor, so the number parses "
        f"empty: {lines[0]}"
    )


def test_forgejo_separates_create_failure_from_parse_failure() -> None:
    """`$?` of `"$(a | b | c)"` is c's, so a dead `fj` looks like a parse miss.

    They need different recoveries: a create that never happened must not be
    "recovered" by `issue search`, which defaults to open issues over free text
    and will happily bind a similar older ticket.
    """
    section = _forgejo_section()

    assert "CREATE_FAILED" in section, (
        "the create no longer captures its own exit status separately from parsing"
    )
    assert_rule(
        section, "생성 실패와 파싱 실패를 한 덩어리로 다루지 마라",
        starts_with="- **생성 실패와 파싱 실패를 한 덩어리로 다루지 마라.**",
    )


def test_forgejo_section_states_the_read_back_principle_first_and_once() -> None:
    """One statement, at the top, with the two cases hung off it.

    Uniqueness is checked against the whole file, not the section: a second copy
    parked in Step 9 is still a second copy. Position is checked because the DoD
    names this guard as the judge of "맨 앞", and an `assert_rule` alone would
    let the principle sink to the bottom.
    """
    text = read_skill("skills/project-issue/SKILL.md")
    assert_rule(
        text, "읽기 확인이 증거다",
        starts_with="**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다",
    )

    body = [l for l in _forgejo_section().splitlines() if l.strip()]
    assert body[1].startswith("**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다"), (
        f"the principle is no longer the first thing in the section: {body[1]!r}"
    )


def test_forgejo_label_edit_targets_the_issue_not_a_repo_flag() -> None:
    """`-r` reverses meaning between subcommands, and the damage is silent.

    On `fj issue create` it is `--repo`. On `fj issue edit <ISSUE> labels` there
    is no `--repo` and `-r` is `--rm`. The first draft only rejected a value
    containing `/`, which the placeholder `<forgejo_repo>` never does — so the
    check could not fire on this document at all.
    """
    labels = [
        inv for inv in _fj_invocations(_forgejo_section())
        if "issue edit" in inv and "labels" in inv
    ]
    assert labels, "no `fj issue edit ... labels` invocation in the Forgejo section"

    for inv in labels:
        tokens = inv.split()
        target = tokens[tokens.index("edit") + 1]
        assert "#" in target, (
            f"the label edit does not target the issue as <repo>#<N>: {inv}"
        )
        for flag in ("-r", "--rm"):
            assert flag not in tokens, (
                f"`{flag}` on a labels call is --rm: this removes labels silently: {inv}"
            )


def test_forgejo_create_never_puts_a_literal_title_in_the_command() -> None:
    """A quoted expansion is safe; a pasted literal is not — either quote style.

    The shell does not re-scan the result of a parameter expansion, so
    `"$TITLE"` is safe even when the title holds backticks. A literal is
    exposed: inside double quotes the backticks run, and inside single quotes
    one apostrophe in the title closes the quote and runs them anyway — which
    also leaves `--body-file` empty, so `$EDITOR` opens and a headless run
    hangs. `project-plan` titles name files and symbols in backticks as a matter
    of course, so this is the normal case, not the exotic one.
    """
    creates = [inv for inv in _fj_invocations(_forgejo_section()) if "issue create" in inv]
    assert creates, "no `fj issue create` invocation in the Forgejo section"

    quoted_variable = re.compile(r'^"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?"$')
    for inv in creates:
        # positionals[0:2] are `fj` and the `issue create` command path.
        for argument in _fj_positionals(inv)[3:]:
            assert quoted_variable.match(argument), (
                f"the title is a literal, exposed to command substitution: {argument} in {inv}"
            )


def test_no_skill_embeds_a_literal_directional_isolate() -> None:
    """U+2068/U+2069 are invisible; they must appear only as escape notation."""
    offenders: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for char, name in (("\u2068", "U+2068"), ("\u2069", "U+2069")):
                if char in line:
                    offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {name}")
    assert not offenders, (
        "a directional isolate is embedded literally; write it as \\x{2068}:\n"
        + "\n".join(offenders)
    )


def test_forgejo_section_records_what_it_could_not_verify() -> None:
    """The template retry path and the multi-label form were never measured.

    Both are reachable on a normal run — a repo with blank issues disabled, a
    plan touching both BE and FE — so dropping the "unverified" marking is how a
    guess gets read as a measurement.
    """
    section = _forgejo_section()

    assert "fj issue templates" in section and "--template" in section, (
        "the blank-issue retry path is gone"
    )
    assert "미검증" in section, "the section no longer marks its unverified claims"
    assert "-a" in section and "쉼표" in section, (
        "the multi-label form is no longer addressed"
    )


def test_forgejo_read_back_reads_the_body_surface_not_comments() -> None:
    """`fj issue view <ID>` defaults to `body`; comments need `view <ID> comments`.

    Reading the wrong surface looks exactly like a write that failed — the
    section says so, and this pins the read-back to the surface labels live on.
    """
    views = [
        inv for inv in _fj_invocations(_forgejo_section())
        if "issue view" in inv and "$ISSUE_NUMBER" in inv
    ]
    assert views, "the Forgejo section no longer reads the issue back"

    for inv in views:
        assert not inv.rstrip().endswith("comments"), (
            f"the read-back reads comments, where labels never appear: {inv}"
        )
    assert "comments" in _forgejo_section(), (
        "the warning about reading the wrong surface is gone"
    )


def test_forgejo_section_states_it_has_no_harness_branch() -> None:
    """No forgejo adapter exists, so `harness_enabled` must not send a reader
    looking for a path that was never written."""
    assert_rule(
        _forgejo_section(), "harness 분기는 없다",
        starts_with="harness 분기는 없다",
    )


def test_forgejo_does_not_share_a_parser_between_create_and_view() -> None:
    """The two outputs place the number differently; one parser breaks both."""
    assert_rule(
        _forgejo_section(), "create 용 번호 파서를 이 확인에 재사용하지 않는다",
        starts_with="- create 용 번호 파서를 이 확인에 재사용하지 않는다",
    )


def test_metadata_step_scope_markers_name_the_right_trackers() -> None:
    """Counting `(GitHub only)` is order-blind — swapping steps 3 and 4 keeps the
    count at three while inverting the contract. Assert the markers by step."""
    text = read_skill("skills/project-issue/SKILL.md")

    for marker in (
        "**3. Infer Issue Type** (GitHub only)",
        "**4. Infer Labels** (GitHub and Forgejo)",
        "**5. Infer Priority / Size** (GitHub only)",
        "**7. Read Back** (GitHub only)",
    ):
        assert marker in text, f"scope marker changed or moved: {marker}"


def test_output_step_says_what_forgejo_can_show() -> None:
    """Step 9's vocabulary was GitHub-only, leaving a forgejo run with no way to
    know what it is expected to report."""
    assert_rule(
        read_skill("skills/project-issue/SKILL.md"), "On forgejo the only observable one is Labels",
        starts_with="- On forgejo the only observable one is Labels",
    )


def test_project_issue_documents_the_explicit_plan_path_argument() -> None:
    """The argument exists so a human can settle what discovery cannot."""
    text = read_skill("skills/project-issue/SKILL.md")

    assert "## Usage" in text, "project-issue still documents no argument contract"
    assert "project-issue [<plan-path>]" in text

    assert_rule(
        text, "Step 1 does not run discovery at all",
        starts_with="- **Given**",
    )
    assert_rule(
        text, "never falling back to discovery",
        starts_with="- An explicit path is accepted only when",
    )


def test_explicit_path_validation_command_performs_all_three_checks() -> None:
    """Pinning the prose and not the command lets the command be gutted.

    The rule line can keep promising three checks while the snippet below it
    performs one. The name check is the only gate protecting Step 8's `mv`, and
    the plan-directory check is what stops the same input landing in two places
    depending on `harness_enabled`.
    """
    text = read_skill("skills/project-issue/SKILL.md")
    command = text.split("do not run discovery", 1)[1].split("```", 2)[1]

    assert "is_draft_plan(" in command, "the draft-name gate is gone from the command"
    assert "plan_dir" in command and "path.parent" in command, (
        "the plan-directory comparison is gone from the command"
    )
    assert "path.is_file()" in command, "the existence check is gone from the command"
    assert command.count("sys.exit(") == 3, (
        "each rejection must exit non-zero naming its check; "
        f"found {command.count('sys.exit(')} exits"
    )
    # Rooted at the main worktree, because `.task/plan/` is gitignored and exists
    # only there — resolving against CWD rejects every valid path from a linked
    # worktree (harness_core records the same fix as plan-234).
    # Asserted as calls, not as names: the `from harness_core.local import
    # abs_under_main` line keeps the name alive after the call is removed, and a
    # mutation walked past a name check on exactly that.
    assert "abs_under_main(Path(sys.argv[1]))" in command, (
        "the argument is resolved against CWD again; from a linked worktree that "
        "rejects every valid path, because .task/plan/ exists only in the main one"
    )
    assert "main_worktree_root() /" in command, (
        "the plan directory is no longer rooted at the main worktree"
    )


def test_draft_discovery_survives_the_new_argument() -> None:
    """The no-argument path must be untouched, not rewritten around the new one.

    Asserting on `is_draft_plan` alone is self-satisfying now: the new
    explicit-path snippet imports it too, so the whole discovery fallback could
    be deleted with this guard still green. Pin the fallback's own command.
    """
    text = read_skill("skills/project-issue/SKILL.md")

    assert "<harness_cli> find-draft-plan" in text, "the harness discovery call is gone"
    assert "Otherwise (or when no harness exists)" in text, "the discovery fallback is gone"
    assert 'Path(".task/plan").glob("plan-*.md")' in text, (
        "the discovery fallback no longer globs the plan directory"
    )
    assert "**Two or more files**" in text, "the ambiguity branch is gone"


def test_codex_reference_shows_the_plan_path_argument() -> None:
    """Whole lines, not substrings: the old line is a prefix of the new one."""
    lines = [l.strip() for l in read_skill("skills/_shared/references/codex.md").splitlines()]

    assert "$project-issue [<plan-path>] [--issue <id>]" in lines
    assert "$project-issue [<plan-path>]" not in lines, "codex still shows project-issue without --issue"
    assert "$project-iterate <id> [worktree] [adr]" in lines, "codex does not show the <id> re-entry"


def test_skill_config_scopes_the_forgejo_write_contract() -> None:
    """Issue creation, comments and PR creation are contracted; status transitions are not.

    Comments and PR creation were measured live and are documented in
    project-done; no skill documents an `fj` status-transition command.
    Declaring write support unscoped sends a reader hunting for a path that does
    not exist — which this document forbids two lines above ("확인 명령을 추측하지
    말 것"). The two halves sit on separate lines so each is pinned on its own.
    """
    text = read_skill("skills/SKILL-CONFIG.md")

    assert "조회(read) 경로만" not in text, "forgejo is still declared read-only"
    for retraction in ("읽기 전용", "read-only", "쓰기 계약이 아니"):
        assert retraction not in text, f"the write contract is retracted in prose: {retraction}"

    assert_rule(
        text, "쓰기(write) 중 **이슈 생성·이슈 코멘트·PR 생성**이 계약이다",
        starts_with="`forgejo` 는 조회(read) 전체와",
    )
    assert_whole_line(text, (
        "**상태 전환에는 아직 `fj` 계약이 없다** — 그 쓰기는 아래 웹 UI 수동 처리로 가거나, "
        "미반영으로 보고하고 계속한다."
    ))
    # Both fallbacks survive the correction, in substance and not just in word.
    assert_rule(
        text, '"미확인" 으로 표기한 뒤 절차를 계속한다',
        starts_with="조회가 실패하면",
    )
    assert_rule(
        text, "웹 UI 수동 처리는 그 뒤의 마지막 단",
        starts_with="**이슈 생성은 `fj` 가 1순위이고",
    )


def test_iterate_passes_the_plan_path_it_already_knows() -> None:
    """Phase 1 creates the file; Phase 2 rediscovering it is the waste.

    The re-entry branch has to be stated alongside it: entering at Phase 2 means
    the path is unknown, and that is precisely why the argument is optional.
    """
    text = read_skill("skills/project-iterate/SKILL.md")

    assert_rule(
        text, "위치 인자로 그대로 넘긴다",
        starts_with="- Phase 1 이 방금 만든 플랜 경로를",
    )
    # Re-entry used to fall back to argument-less discovery here, and discovery
    # hands Phase 2 whatever unrelated draft it finds — a second ticket for an
    # issue that already exists. Re-entry now always carries the path and links.
    assert_rule(
        text, "`project-issue <plan-path> --issue <id>` 로 연결 모드를 부른다",
        starts_with="- `## Re-entry After Interruption` 의 \"Issue only\" 상태에서 왔다면",
    )




# --------------------------------------------------------------------------
# Section slicing
#
# `project-done` and `project-start` number their steps with bold pseudo-
# headings (`**4. Write impl-report**`), not Markdown headings, so no off-the-
# shelf splitter finds them. Several rules below have to hold *in one step* and
# must stay silent about the rest of the file: `--stat` is banned in the
# impl-report step while `project-release-doc` uses it legitimately, and the
# pipe ban has to be asserted at two separate steps independently.
#
# The number pattern allows dotted steps (`**3.5. ...**`, which `project-adr`
# actually uses) — matching only `\d+` there would let a slice opened at step 3
# swallow step 3.5 whole and assert against the wrong body. Requiring the line
# to close with `**` keeps ordinary bolded prose from opening a section, and
# fenced regions are skipped so a code sample can never look like a heading.
# --------------------------------------------------------------------------

_STEP_HEADING = re.compile(r"^\*\*\d+(?:\.\d+)*(?:-[A-Za-z])?\.\s.*\*\*\s*$")


def _outside_fences(text: str):
    """Yield (line, in_fence) so scanners can ignore fenced code."""
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            yield line, True
            continue
        yield line, in_fence


def skill_section(text: str, title_starts_with: str) -> str:
    """The lines of one numbered step, heading included, next heading excluded.

    `title_starts_with` is matched against the heading line, so a caller names
    the step the way the document does. Returns "" when no such step exists;
    every caller asserts the slice is non-empty, because a whole-file scan that
    silently received nothing passes while proving nothing.
    """
    out: list[str] = []
    for line, in_fence in _outside_fences(text):
        if not in_fence and _STEP_HEADING.match(line):
            if out:
                break
            if line.startswith(title_starts_with):
                out.append(line)
            continue
        if out:
            out.append(line)
    return "\n".join(out)


def _step_order(text: str) -> list[str]:
    """Step headings in document order, so a reordering is visible to a test."""
    return [
        line.strip()
        for line, in_fence in _outside_fences(text)
        if not in_fence and _STEP_HEADING.match(line)
    ]


def _skill_docs() -> list[Path]:
    return sorted((ROOT / "skills").rglob("*.md"))


def _commands(text: str, starts_with: str) -> list[str]:
    """Command lines in a slice, shell continuations already joined."""
    return [line for line in _logical_lines(text) if line.startswith(starts_with)]


def test_project_done_diffs_from_the_merge_base() -> None:
    """The report must list this branch's work, not the base's, and all of it.

    `git diff --name-only <base>` compares against the branch *tip*, so every
    commit the base gained while this branch lived is reported as this ticket's.
    The fix diverges at the merge base — but only in a form that keeps three
    other properties, each of which is asserted here because each was a way of
    reintroducing the defect while the earlier version of this guard stayed
    green:

      * no `..HEAD` anywhere in the command (a commit-vs-commit range drops all
        uncommitted work, and this step runs *before* the commit step);
      * the `|| { ... }` on the substitution, without which a dead `merge-base`
        leaves an empty variable and `git diff --name-only "" --` returns the
        same silent empty list the change was written to remove;
      * a companion listing of untracked files, because `git diff` never
        reports them and nothing is staged yet at this point in the flow.
    """
    text = read_skill("skills/project-done/SKILL.md")
    section = skill_section(text, "**4. Write impl-report**")
    assert section, "the impl-report step is no longer findable by its heading"

    merge_base = _commands(section, "MERGE_BASE=")
    assert len(merge_base) == 1, (
        f"expected exactly one merge-base assignment, found {len(merge_base)}"
    )
    assert "git merge-base" in merge_base[0], "step 4 no longer derives a merge base"
    assert "||" in merge_base[0], (
        f"a failed merge-base is no longer caught: {merge_base[0]!r}"
    )

    commands = _commands(section, "git diff --name-only")
    assert len(commands) == 1, (
        f"expected exactly one file-list command in step 4, found {len(commands)}:\n"
        + "\n".join(commands)
    )
    command = commands[0]
    assert "$MERGE_BASE" in command, (
        f"the file list no longer reads the merge base: {command!r}"
    )
    # Substring, not `endswith`: the mandatory trailing `--` means an
    # `endswith("..HEAD")` check can never fire, so the regression it is named
    # for stays reintroducible.
    assert "..HEAD" not in command, (
        f"a commit-vs-commit range drops uncommitted work: {command!r}"
    )
    assert command.endswith("--"), f"the command is not closed with `--`: {command!r}"

    assert _commands(section, "git ls-files --others"), (
        "step 4 no longer lists untracked files, so every file this round "
        "created is missing from the report and from the PR body"
    )

    # `--stat` abbreviates long paths with `...`, and a reader expanding one
    # invents a path that does not exist. Banned in this step only:
    # `project-release-doc` uses it for a summary a human reads.
    #
    # Scoped to command lines *and* the report's placeholder line: the sentence
    # that states the ban contains `--stat` itself, so a whole-slice absence
    # scan is red the day the rule is written, while a scan of `git`-prefixed
    # lines alone misses the angle-bracket placeholder form the file used
    # before this change (`<git diff --stat ... 출력>`).
    statted = [
        line for line in section.splitlines()
        if "--stat" in line and not line.lstrip().startswith(("-", ">", "*"))
    ]
    assert not statted, f"step 4 took a file list with `--stat`: {statted}"
    assert_rule(
        section, "`--name-only` only",
        starts_with="**Take the file list with `--name-only` only.**",
    )

    # The superseded form must not survive anywhere in the tree. It is not a
    # substring of the new command, so this stays honest.
    old = 'git diff --name-only "<diff_base>"'
    docs = _skill_docs()
    assert docs, "no skill documents were scanned at all"
    offenders = [
        f"{path.relative_to(ROOT)}:{n}"
        for path in docs
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if old in line
    ]
    assert not offenders, f"the tip-based file list is back: {offenders}"


def test_project_done_writes_the_report_before_committing() -> None:
    """Step 4's whole rationale is that nothing is committed when it runs.

    The ban on `..HEAD` and the untracked-file listing are both justified by
    that ordering, in prose, inside step 4. Reordering the steps leaves every
    other guard green and turns that justification into a false statement, so
    the order itself has to be pinned.
    """
    order = _step_order(read_skill("skills/project-done/SKILL.md"))
    assert order, "no step headings were found at all"

    def index_of(prefix: str) -> int:
        matches = [i for i, line in enumerate(order) if line.startswith(prefix)]
        assert len(matches) == 1, f"expected one {prefix!r} step, found {matches}"
        return matches[0]

    assert index_of("**4. Write impl-report") < index_of("**5. Commit source changes"), (
        "the report is now written after the commit, which falsifies step 4's "
        "own reason for excluding `..HEAD` and listing untracked files"
    )


def test_jira_issue_create_uses_only_real_flags() -> None:
    """`jira issue create` has no `--description`; cobra dies on unknown flags.

    Measured against the installed CLI (1.7.0): the body flags are `-b,--body`
    and `-T,--template`, `--description` does not exist, and `--no-input` is
    what suppresses the description editor — `--template` alone still opens it.

    `-b/--body` is banned outright rather than merely unmentioned: the CLI's own
    examples state it takes precedence over `--template`, so adding it silently
    discards the plan file. That is the same silent-precedence class this ticket
    exists to remove, and an earlier version of this guard let it through.

    The zero-input assertion is load-bearing: this call appears exactly once in
    the whole tree, so deleting it would make every flag assertion below pass
    vacuously.
    """
    invocations = [
        (path, line)
        for path in _skill_docs()
        for line in _logical_lines(path.read_text(encoding="utf-8"))
        if line.startswith("jira issue create")
    ]
    assert invocations, "no `jira issue create` call is documented anywhere"

    for path, line in invocations:
        where = path.relative_to(ROOT)
        assert "--description" not in line, (
            f"{where}: `--description` does not exist on this CLI: {line!r}"
        )
        assert re.search(r"(?:^|\s)(?:-T|--template)(?:\s|=)", line), (
            f"{where}: the body is no longer passed as a file: {line!r}"
        )
        assert not re.search(r"(?:^|\s)(?:-b|--body)(?:\s|=)", line), (
            f"{where}: `-b/--body` silently overrides `--template`: {line!r}"
        )
        assert "--no-input" in line, (
            f"{where}: without `--no-input` the description editor opens and "
            f"an unattended run blocks: {line!r}"
        )
        assert "--raw" in line, (
            f"{where}: the response is no longer requested as JSON: {line!r}"
        )
        # Quote-insensitive, and not limited to one literal: any concrete type
        # name here is a hardcode, whichever one it is.
        type_arg = re.search(r"--type\s+(\S+)", line)
        assert type_arg, f"{where}: no issue type is passed at all: {line!r}"
        assert type_arg.group(1).strip("\"'").startswith("<"), (
            f"{where}: the type is hardcoded instead of inferred: {type_arg.group(1)!r}"
        )


def test_jira_create_is_followed_by_a_read_back() -> None:
    """The create path's read-back is a separate rule from the move path's.

    It lives in `project-issue` §6 rather than in Step 7, which is the GitHub
    path; nothing else in the tree asserts it, so deleting the block left every
    other guard green.
    """
    text = read_skill("skills/project-issue/SKILL.md")
    start = text.index("### Jira (`issue_tracker: jira`)")
    section = text[start:text.index("### Forgejo", start)]
    assert section, "the Jira subsection is no longer findable"

    assert _commands(section, "jira issue view"), (
        "the created issue is no longer read back before it is reported"
    )
    assert "--raw" in section, "the read-back no longer asks for the raw response"
    assert "Limitation:" in section, (
        "the note that this path was never run against a live Jira is gone"
    )


def _jira_transition_contract(path: str, heading: str) -> str:
    section = skill_section(read_skill(path), heading)
    assert section, f"{path}: the status step is no longer findable: {heading}"
    return section


def test_jira_move_is_followed_by_a_read_back() -> None:
    """A clean `jira issue move` is not evidence that the issue moved.

    Both sites that transition an issue carry the same contract, so both are
    asserted, and the two blocks are required to stay byte-identical — the
    substring assertions that preceded this let the copies drift in wording and
    rationale while staying green.

    Each rule is pinned with `assert_rule`, not with `in`. Every one of these
    survived being inverted in place, and one survived being replaced by a
    sentence that retracted it ("an earlier draft told you to ... skip it"),
    which is exactly what `RETRACTION_MARKERS` exists to catch.
    """
    sites = (
        ("skills/project-start/SKILL.md", "**3. Issue status -> In Progress**"),
        ("skills/project-done/SKILL.md", "**8. Project status -> In Review**"),
    )
    blocks = []
    for path, heading in sites:
        section = _jira_transition_contract(path, heading)

        assert _commands(section, "jira issue view"), (
            f"{path}: the transition is no longer read back"
        )
        assert_rule(
            section, "not from the move's exit code",
            starts_with="- **Judge from the re-read",
        )
        assert_rule(
            section, "Always pass the state argument",
            starts_with="- **Always pass the state argument.**",
        )
        assert "not applied" in section, (
            f"{path}: the existing 'not applied' grade was dropped or promoted"
        )
        assert "--plain" in section and "--columns status" in section, (
            f"{path}: the rejected `jira issue list` substitute is no longer warned against"
        )

        start = section.index("**The Jira fallback reads the result back.**")
        blocks.append(section[start:section.index("> Limitation:", start)])

    assert blocks[0] == blocks[1], (
        "the two copies of the Jira transition contract have drifted; they are "
        "duplicated verbatim on purpose, so any change belongs in both"
    )

    # Positive shape: the state argument is a placeholder, never a real label.
    # A ban on labels starting with `In ` (the earlier form) let `"Done"`,
    # `"Resolved"` and `"완료"` straight through, and a ban on the whole slice
    # would be red on the legitimate step headings and status-field fallbacks.
    moves = [
        (path, line)
        for path in _skill_docs()
        for line in _logical_lines(path.read_text(encoding="utf-8"))
        if re.search(r"(?:^|\s)jira issue move\s", line)
    ]
    assert moves, "no `jira issue move` call is documented anywhere"
    for path, line in moves:
        where = path.relative_to(ROOT)
        args = re.search(r"jira issue move\s+(\S+)\s+(\S+)", line)
        assert args, (
            f"{where}: the bare form opens an interactive picker and unattended "
            f"can run the first entry of the list: {line!r}"
        )
        assert args.group(2).strip("\"'").startswith("<"), (
            f"{where}: a workflow-specific state name is hardcoded: {line!r}"
        )


def test_gate_commands_are_not_piped() -> None:
    """A pipe hands you the last stage's exit code, so a red run reports green.

    The rule has to hold at *both* gates, which is why this is a slice-by-slice
    assertion rather than one `assert_rule` over the file: `rule_line` requires
    an anchor to appear exactly once per file, so the two sites are worded
    differently and anchored separately.

    The prose assertions are not enough on their own — the earlier version of
    this guard passed while the documented command was changed to
    `... 2>&1 | tee "<log-file>"`. The command lines in each slice are checked
    directly.
    """
    text = read_skill("skills/project-done/SKILL.md")

    # The verdict rule is anchored on the phrase that states BOTH sources are
    # required. Anchoring on "the verdict line" alone pinned nothing: the rule
    # survived being rewritten to "Read the result from the verdict line alone
    # — the exit code ... is noisy, so ignore it", which is the exact opposite
    # of the requirement and keeps both the anchor and the line-start intact.
    gates = (
        ("**2-H. `pre_done` hook", "**Do not pipe the hook command.**",
         "`$HOOK_RC` and the verdict line", "**Decide from two places"),
        ("**11. Check CI**", "- **Do not pipe the check command.**",
         "the exit code and the verdict line together",
         "- **Do not pipe the check command."),
    )
    for heading, opening, verdict_anchor, verdict_start in gates:
        section = skill_section(text, heading)
        assert section, f"the gate step is no longer findable: {heading}"

        assert_rule(section, "Do not pipe the", starts_with=opening)
        assert_rule(section, verdict_anchor, starts_with=verdict_start)
        assert "2>&1" in section, f"{heading}: no redirect-to-file alternative is given"
        assert "set -o pipefail" in section, (
            f"{heading}: the rule no longer says the caller's shell options are unknown"
        )

        piped = [line for line in _logical_lines(section) if "|" in line and (
            line.startswith("<the hooks") or line.startswith("gh ")
        )]
        assert not piped, f"{heading}: the documented command is piped: {piped}"

    # The existing bound on `--watch` is the neighbour this rule was placed
    # beside; losing it while adding the pipe ban would be a net loss.
    assert "blocking `--watch` without a bound" in text


def test_project_done_checks_that_commit_and_merge_moved() -> None:
    """An empty commit and an empty merge both end quietly, in opposite ways.

    `git commit` on an empty index exits 1 and the following steps push an
    unchanged branch and open a PR with nothing in it. `git merge` with nothing
    to merge exits 0, prints `Already up to date.` and creates no merge commit,
    so the history keeps no trace at all.

    Both verdicts are pinned with `assert_rule`: asserted as substrings they
    survived being reworded into their own opposites ("expected and harmless,
    so continue", "the normal case and is passed over as success") and into a
    retraction, all while the full suite stayed green.

    The `MERGE:` envelope is asserted absent: promoting these checks into an
    envelope contract is a separate, larger ticket, and importing the string
    early would claim a contract that does not exist.
    """
    text = read_skill("skills/project-done/SKILL.md")

    # Anchor on the DIRECTIVE, not on the symptom string. Anchoring on
    # `nothing to commit` / `Already up to date.` pins only the diagnosis: both
    # rules survived being rewritten, in the same line, into their opposites
    # ("expected and harmless, so continue to Step 6 anyway", "the normal case
    # and is passed over as success") because the symptom string and the bold
    # lead-in were both left intact. What has to be pinned is what to DO.
    commit = skill_section(text, "**5. Commit source changes**")
    assert commit, "the commit step is no longer findable by its heading"
    assert_rule(
        commit, "means **stop and report**",
        starts_with="**Check that the commit actually moved.**",
    )
    assert "nothing to commit" in commit, "the empty-index symptom is no longer named"

    merge = skill_section(text, "**7. PR / Branch handling**")
    assert merge, "the PR/branch step is no longer findable by its heading"
    assert_rule(
        merge, "is **reported**, not passed over as success",
        starts_with="- **Check that the merge actually moved.**",
    )
    assert "Already up to date." in merge, "the empty-merge symptom is no longer named"
    # `HEAD^2` is not a discriminator: after any earlier `--no-ff` merge the
    # base tip is already a merge commit, so it resolves happily following a
    # no-op and names the *previous* round's branch.
    assert not re.search(r"confirm that `git rev-parse HEAD\^2`", merge), (
        "`HEAD^2` is documented as a merge-happened check again"
    )
    assert "$BASE_BEFORE" in merge, "the before/after sha comparison is gone"

    assert "MERGE:" not in text, (
        "the envelope contract was imported before the ticket that defines it"
    )


def test_project_done_merges_from_the_main_checkout() -> None:
    """Defect 1-4: in worktree mode `git checkout <base>` fails and the chain no-ops.

    Nothing covered this fix, so deleting it whole left the suite green.

    The resolution must not be derived by walking up from `--git-common-dir`:
    wherever `.git` is not a directory beside the work tree (a submodule, a
    `--separate-git-dir` clone, a bare repo) the parent is a different
    directory that nonetheless *exists*, so `cd` succeeds and git quietly
    re-targets another repository.
    """
    merge = skill_section(read_skill("skills/project-done/SKILL.md"),
                          "**7. PR / Branch handling**")
    assert merge, "the PR/branch step is no longer findable by its heading"

    resolve = _commands(merge, "MAIN_CHECKOUT=")
    assert len(resolve) == 1, f"expected one main-checkout resolution, got {resolve}"
    assert "git worktree list" in resolve[0], (
        f"the main checkout is no longer resolved by asking git for it: {resolve[0]!r}"
    )
    # Scoped to command lines: the bullet explaining *why not* to walk up from
    # the git dir names both flags, so a whole-slice absence scan is red the day
    # the rule is written. This is the third rule in this change to need that
    # narrowing, and the reason `--stat` and `..HEAD` are scoped the same way.
    commands = [
        line for line in _logical_lines(merge)
        if line.startswith(("MAIN_CHECKOUT=", "BASE_BEFORE=", "git ", "cd "))
    ]
    assert commands, "the merge fence has no commands in it at all"
    for flag, why in (
        ("--git-common-dir",
         "lands in the wrong repository for a submodule or a --separate-git-dir clone"),
        # `--path-format` needs git 2.31; the manifest declares a floor of 2.23.
        ("--path-format",
         "raises the git floor above the one declared in skills/dependencies.yaml"),
    ):
        offenders = [line for line in commands if flag in line]
        assert not offenders, f"`{flag}` {why}: {offenders}"
    assert re.search(r'\[\s*-n\s*"\$MAIN_CHECKOUT"', merge), (
        "the resolved path is no longer checked for emptiness, and `cd \"\"` "
        "returns 0 while leaving you in the worktree"
    )
    assert_rule(
        merge, "Merge from the main checkout",
        starts_with="**Merge from the main checkout.**",
    )
    assert "git worktree remove -f -f" in merge, (
        "the ban on force-removing a worktree is gone"
    )


# --------------------------------------------------------------------------
# Link mode: attaching a plan to an issue that already exists (#25)
#
# Every guard below exists because the failure it stops is a *second ticket*,
# an *overwritten plan*, or a *renamed repository*, and all three are silent.
# Slices are asserted non-empty and carrying a sentinel before any absence
# check, because an absence check on an empty slice passes while proving
# nothing. Gate lines are compared whole: `assert_rule` pins a line's start and
# an anchor, and a review showed every gate surviving an escape clause appended
# to its end (", unless the user says to proceed anyway").
# --------------------------------------------------------------------------

_CREATE_COMMANDS = ("create-issue", "gh issue create", "issue create", "jira issue create")
_ISSUE_READS = ("gh issue view", 'issue view "<forgejo_repo>#', "jira issue view")
_ID_PATTERN = r're.fullmatch(r"[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*", '


def _issue_skill() -> str:
    return read_skill("skills/project-issue/SKILL.md")


def _iterate_skill() -> str:
    return read_skill("skills/project-iterate/SKILL.md")


def _start_skill() -> str:
    return read_skill("skills/project-start/SKILL.md")


def _link_mode() -> str:
    section = skill_section(_issue_skill(), "**1-L. Link Mode")
    assert section, "project-issue has no Step 1-L link-mode section"
    for read in _ISSUE_READS:
        assert read in section, f"the link-mode slice lost its issue read: {read}"
    return section


def _step8() -> str:
    section = skill_section(_issue_skill(), "**8. Rename File**")
    assert section and "rename_plan_to_issue(" in section, "Step 8 is gone"
    return section


def _fenced(text: str) -> str:
    return "\n".join(line for line, in_fence in _outside_fences(text) if in_fence)


def assert_whole_line(text: str, expected: str) -> None:
    """The gate line exists exactly once and says exactly this — nothing appended."""
    lines = [l.strip() for l in text.splitlines()]
    assert lines.count(expected) == 1, (
        f"gate line changed, moved or duplicated ({lines.count(expected)} exact matches):\n{expected}"
    )


def test_project_issue_documents_the_issue_argument() -> None:
    text = _issue_skill()
    lines = [l.strip() for l in text.splitlines()]

    assert "project-issue [<plan-path>] [--issue <id>]" in lines
    assert "project-issue [<plan-path>]" not in lines, "the usage block still omits --issue"
    assert_rule(
        text, "the draft is linked to issue `<id>` and no ticket is created",
        starts_with="- **Given** — link mode",
    )
    assert_whole_line(text, (
        "- With `--issue`, `<plan-path>` is required: stop before Step 1 if it is missing, "
        "because discovery would take whatever single draft is there, and nothing in a draft names its issue."
    ))
    description = rule_line(text, "description:")
    assert "--issue <id>" in description, "the skill description does not mention link mode"


def test_link_mode_runs_before_confirmation() -> None:
    order = _step_order(_issue_skill())
    link = [i for i, h in enumerate(order) if h.startswith("**1-L.")]
    confirm = [i for i, h in enumerate(order) if h.startswith("**2.")]
    detect = [i for i, h in enumerate(order) if h.startswith("**1.")]

    assert link and confirm and detect
    assert detect[0] < link[0] < confirm[0], f"Step 1-L is out of place: {order}"


def test_link_mode_creates_nothing() -> None:
    section = _link_mode()
    for command in _CREATE_COMMANDS:
        assert command not in section, f"link mode names a create command: {command}"


def test_link_mode_carries_no_shell_variable_across_turns() -> None:
    """An empty `$DRAFT_PLAN` resolves to the main worktree root, and Step 8
    then renames the repository. A review reproduced exactly that."""
    assert_whole_line(_link_mode(), (
        "- Never carry a shell variable from an earlier call into these commands; "
        "substitute `<id>` and every path as a literal."
    ))
    for name, section in (("Step 1-L", _link_mode()), ("Step 8", _step8())):
        fenced = _fenced(section)
        assert fenced, f"{name} has no commands"
        assert "$" not in fenced, f"{name} carries a shell variable into a command"


def test_link_mode_skips_straight_to_step_8() -> None:
    """Narrowing the range — or moving the line past Step 6 — runs the create."""
    text = _issue_skill()
    branch = "- In link mode (`--issue`), Steps 3–7 do not run: after Step 2's yes, go straight to Step 8."
    assert_whole_line(text, branch)

    lines = [l.strip() for l in text.splitlines()]
    head = lines.index("**3. Infer Issue Type** (GitHub only)")
    following = [l for l in lines[head + 1:] if l]
    assert following[0] == branch, "the link-mode branch is not the first line of Step 3"

    assert_whole_line(_link_mode(), (
        "4. **Confirm, then rename.** Step 2 runs with its link-mode additions, and the first line "
        "of Step 3 sends the flow to Step 8; nothing is inferred or created on the way, so the "
        "issue's type, labels, priority and size stay as the tracker has them."
    ))


def test_link_mode_stops_when_the_issue_cannot_be_read() -> None:
    section = _link_mode()
    assert_whole_line(section, (
        "- If the read fails, the issue is closed, the number read back is not `<id>`, "
        "or it is a pull request, stop before Step 8 and report which it was."
    ))
    assert_whole_line(section, (
        "- Judge the read by its content, never by its exit code: the number or key read back "
        "equals `<id>`, the title is non-empty, the state is open, and it is not a pull request "
        "(GitHub: `url` is an `/issues/` URL; Forgejo: no `From … into …` line)."
    ))


def test_link_mode_reads_each_tracker_through_its_contract() -> None:
    section = _link_mode()
    lines = [l.strip() for l in section.splitlines()]

    # state for the gate, body for project-iterate, labels for Step 9.
    assert 'gh issue view "<id>" --json number,title,state,url,body,labels' in lines
    assert 'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>"' in lines
    assert 'jira issue view "<id>" --raw' in lines
    # The core get-issue is not the gate: no state, and exit 2 on a board failure.
    assert "the core `get-issue` is not this gate" in section
    assert "One measurement is not a contract — the content rule below still decides." in section


def test_link_mode_refuses_an_existing_plan_before_confirmation() -> None:
    section = _link_mode()
    assert_whole_line(
        section, "- When `plan-<id>.md` already exists, link mode stops here, before Step 2's confirmation screen.",
    )
    exists = section.index("stop (exists)")
    assert "main_worktree_root()" in section[:exists], "the existence check is not main-rooted"
    assert exists < section.index("gh issue view"), "the plan check runs after the issue read"
    assert exists < section.index("4. **Confirm, then rename.**"), "the plan check runs after the confirmation"


def test_link_mode_validates_the_id_per_tracker() -> None:
    section = _link_mode()
    fenced = _fenced(section)
    assert "re.fullmatch(patterns[tracker], issue_id)" in fenced
    assert '"github": r"[1-9][0-9]*"' in fenced
    assert '"forgejo": r"[1-9][0-9]*"' in fenced
    assert '"jira": r"[A-Z][A-Z0-9_]*-[1-9][0-9]*"' in fenced
    assert "if tracker not in patterns:" in fenced, "an unknown tracker reaches the lookup"
    assert "' '<issue_tracker>' '<id>'" in fenced, "the id is not passed as a literal argument"
    assert "refuse an id containing anything but letters, digits and `-`" in section, (
        "a quote in the id can still close the literal and reach the shell"
    )


def test_link_mode_has_no_rename_of_its_own() -> None:
    fenced = _fenced(_link_mode())
    for rename in ("mv ", "rename-plan", "rename_plan_to_issue"):
        assert rename not in fenced, f"link mode carries its own rename: {rename}"
    assert_whole_line(_step8(), (
        "After issue creation succeeds — or, in link mode, after Step 2's yes. "
        "Both modes use this one step; link mode has no rename of its own."
    ))


def test_step_8_revalidates_and_refuses_to_overwrite() -> None:
    text = _issue_skill()
    step8 = _step8()
    fenced = _fenced(step8)

    assert "mv " not in fenced, "Step 8 renames with mv again"
    mentions = [l.strip() for l in step8.splitlines() if "rename-plan" in l]
    assert len(mentions) == 1 and mentions[0].startswith("- `<harness_cli> rename-plan` is not used here"), (
        f"Step 8 offers rename-plan, which checks neither path nor id: {mentions}"
    )
    assert "skip the rename" not in text, "an existing destination is skipped again, not refused"
    assert "abs_under_main(Path(sys.argv[1]))" in fenced, "the draft path is not main-rooted"
    assert (
        "if not draft.is_file() or not is_draft_plan(draft.name) or draft.parent != plan_dir:"
        in fenced
    ), "Step 8 no longer repeats Step 1's three checks"
    assert _ID_PATTERN + "issue_id)" in fenced, "the id pattern is weakened or gone"
    assert 'except FileExistsError as exc:\n    sys.exit("stop (exists)' in fenced, (
        "an existing destination does not end in a non-zero exit"
    )
    assert "' '<draft-plan-path>' '<ISSUE_ID>'" in fenced, "Step 8 does not take literals"

    assert_whole_line(step8, (
        "- `<harness_cli> rename-plan` is not used here: it checks neither that its source is a "
        "draft file nor its id, so an empty path renames the main worktree itself, and it parses "
        "its number as an integer, so a Jira key is an argument error."
    ))
    assert_whole_line(step8, (
        "- If `plan-<id>.md` already exists, the command stops with a non-zero exit and leaves the "
        "draft where it was: report it and stop, never overwrite the existing plan, and never "
        "delete the draft to finish the rename."
    ))
    assert_whole_line(step8, (
        "- If the rename fails for any other reason, keep the draft; when the issue was already "
        "created, recover with `project-issue <draft-plan-path> --issue <ISSUE_ID>`, which links "
        "instead of creating a second ticket."
    ))


def test_link_mode_comment_needs_its_own_yes_after_step_8() -> None:
    section = _link_mode()
    offer = section.index("5. **After Step 8, offer the plan as a comment.**")
    assert offer > section.index("4. **Confirm, then rename.**"), "the comment is offered before the rename"

    assert_whole_line(section, (
        "- The comment is posted only on its own yes; a no is not an error, because the local "
        "`plan-<id>.md` is the canonical plan either way."
    ))
    assert_whole_line(section, (
        "- If the issue body read in item 3 is the same text as the draft, the body already is "
        "this plan (a create-mode Step 8 failure being recovered): do not ask, and report the "
        "comment as skipped."
    ))

    lines = [l.strip() for l in section[offer:].splitlines()]
    assert "gh issue comment \"<id>\" --body-file '<plan-file>'" in lines
    assert "jira issue comment add \"<id>\" --template '<plan-file>' --no-input" in lines

    forgejo = section.split("- **Forgejo** — comments are part of the `fj` write contract", 1)
    assert len(forgejo) == 2, "the Forgejo comment branch is gone"
    assert "미반영" in forgejo[1] and "`comments` surface" in forgejo[1], (
        "the Forgejo comment is no longer read back, or a missing one is no longer reported"
    )
    # The one measured form: repository in the issue argument, body from the file.
    assert (
        "fj -H <forgejo_host> issue comment '<forgejo_repo>#<id>' --body-file '<plan-file>'" in lines
    ), "the Forgejo comment is not posted through the measured fj form"


def test_link_mode_changes_the_confirmation_and_the_output() -> None:
    text = _issue_skill()
    step2 = skill_section(text, "**2. User Confirmation**")
    assert step2
    assert "issue: #<id> <issue title> (<state>)" in step2
    assert "Link this file to #<id>? [yes/no]" in step2

    step9 = skill_section(text, "**9. Output**")
    assert step9
    assert_rule(
        step9, "link mode inferred nothing, so there is no requested value to compare with",
        starts_with="- metadata is what the Step 1-L read returned",
    )
    assert 'it says "linked", not "created"' in step9


def test_iterate_reentry_never_counts_a_draft_as_the_plan() -> None:
    text = _iterate_skill()

    assert "supported draft plan exists" not in text, "a draft still marks Plan complete"
    assert_whole_line(text, (
        "- `<id>` 가 주어졌을 때 `plan-<id>.md` 가 없으면 초안이 있어도 Plan 완료로 판정하지 않는다 "
        "— 초안에는 이슈 번호가 없어서, 거기 있는 초안은 다른 어떤 작업의 것이어도 된다."
    ))

    rows = [l.strip() for l in text.splitlines() if l.startswith("| ") and "Continue from" not in l]
    table = [r for r in rows if r.split("|")[1].strip() in
             ("Done", "Branch, no plan", "Start", "Issue", "Issue only")]
    assert table == [
        '| Done | PR exists or issue status is "In Review" | `gh pr list --head <branch-name>` | nothing left — report it |',
        "| Branch, no plan | branch/worktree for `<id>` exists, `plan-<id>.md` does not | the two checks below | stop and report |",
        "| Start | branch/worktree for `<id>` exists and `plan-<id>.md` exists | the two checks below | Phase 4 |",
        "| Issue | `plan-<id>.md` exists, no branch/worktree | the plan check below | Phase 3 |",
        "| Issue only | none of the above | — | Phase 1 from the issue body, then Phase 2 in link mode |",
    ], "the re-entry state table changed"
    assert_whole_line(text, (
        "- 브랜치/워크트리는 있는데 `plan-<id>.md` 가 없으면 멈추고 사용자에게 보고한다. "
        "`project-start` 는 플랜 없이는 브랜치를 만들지 않으므로(Step 1-A) 이 상태는 손으로 만든 "
        "브랜치나 옛 실행에서만 나온다. Phase 4 로 넘겨도 `project-done` 이 플랜이 없어 멈춘다."
    ))


def test_iterate_checks_are_main_rooted_and_bounded() -> None:
    text = _iterate_skill()
    fenced = _fenced(text)

    assert ".task/plan/plan-<id>.md" not in text, "the plan check is CWD-relative again"
    assert "main_worktree_root()" in fenced
    assert _ID_PATTERN + "sys.argv[1])" in fenced, "the plan check takes an unvalidated id"
    assert 'git branch -a --list "*issue-<id>-*" "*/<id>-*"' in fenced
    assert "grep" not in fenced and "\\| grep" not in text, "the branch check matches id prefixes again"


def test_iterate_reads_the_issue_through_project_issue() -> None:
    text = _iterate_skill()
    for cli in ("gh issue", "fj -H", "fj issue", "jira issue"):
        assert cli not in text, f"project-iterate writes its own tracker command: {cli}"
    assert_whole_line(text, (
        "- If that read fails or the content rule rejects it (closed, another number, a pull "
        "request), stop and report it before writing any plan."
    ))
    assert_whole_line(text, (
        "- 기존 초안이 있으면 목록을 보여 주고, 사용자가 그중 하나를 이 이슈의 플랜으로 명시적으로 "
        "고를 때만 그 경로를 Phase 2 에 넘긴다. 고르지 않으면 이슈 본문으로 새 초안을 쓴다 — 초안 "
        "소유를 추측하지 않는다."
    ))


def test_iterate_never_calls_project_issue_without_a_path() -> None:
    text = _iterate_skill()

    # The bare name is allowed once, in the rule that hands Phase 1's path over.
    # "`project-issue` Step 1-L" cites the document, and is not a call.
    bare = [
        l.strip() for l in text.splitlines()
        if re.search(r"`project-issue`(?! Step 1-L)", l)
    ]
    assert len(bare) == 1 and bare[0].startswith("- Phase 1 이 방금 만든 플랜 경로를"), bare

    allowed = ("- Phase 1 이 방금 만든 플랜 경로를", "- From Phase 2:")
    for word in ("탐색", "discovery", "no argument", "without argument", "인자 없이"):
        for line in (l.strip() for l in text.splitlines() if word in l):
            assert line.startswith(allowed), f"argument-less discovery is back: {line}"

    assert_whole_line(text, (
        "- `## Re-entry After Interruption` 의 \"Issue only\" 상태에서 왔다면 새 이슈를 만들지 않고 "
        "`project-issue <plan-path> --issue <id>` 로 연결 모드를 부른다 — 이슈가 이미 있는데 생성 "
        "모드로 부르면 같은 작업의 티켓이 둘이 된다."
    ))
    assert_whole_line(text, (
        "- From Phase 2: `project-issue <plan-path>`, or `project-issue <plan-path> --issue <id>` "
        "when the issue already exists. Always name the path: discovery without it can pick up a "
        "draft that belongs to other work."
    ))


def test_start_requires_the_local_plan_before_side_effects() -> None:
    text = _start_skill()
    order = _step_order(text)
    gate = [i for i, h in enumerate(order) if h.startswith("**1-A.")]
    branch = [i for i, h in enumerate(order) if h.startswith("**2-A.")]

    assert gate and branch and gate[0] < branch[0], f"the plan gate runs after branching: {order}"
    section = skill_section(text, "**1-A.")
    fenced = _fenced(section)
    assert "main_worktree_root()" in fenced, "the plan check is CWD-relative"
    assert _ID_PATTERN + "sys.argv[1])" in fenced, "the plan check takes an unvalidated id"
    assert 'sys.exit(0 if plan.is_file() else "no plan: %s" % plan)' in fenced, (
        "a missing plan no longer ends the check non-zero"
    )
    assert_whole_line(section, (
        "- If `plan-<issue-id>.md` does not exist, stop here — before any branch, worktree, "
        "status change or ADR — and point the user to `project-iterate <issue-id>`, or to writing "
        "a draft and running `project-issue <plan-path> --issue <issue-id>`."
    ))

    step5 = skill_section(text, "**5. Load plan**")
    assert step5
    assert_whole_line(step5, "Read the `plan-<issue-id>.md` that Step 1-A found in the main worktree's plan directory.")
    assert "issue body" not in step5, "the issue-body fallback is back"
    assert ".task/plan/plan-<issue-id>.md" not in text, "a CWD-relative plan path is back"

# --------------------------------------------------------------------------
# project-done's Forgejo branch (#28)
#
# Every procedure here was run live before it was written down, and every
# failure it guards is silent: a comment that posts nothing prints nothing, a
# comment that *did* post also prints nothing, `pr status` exits 0 on a check
# that will stay Pending forever, and a PR body read from a worktree-relative
# path is an absolute path to a file that is not there.
#
# Two layers, on purpose. The shape guards pin argument roles, raw command
# lines and redirects, and say *why* each shape matters. The golden tuples pin
# every Forgejo prose line whole: a review showed keyword and anchor guards
# surviving a rule inverted in its result clause ("warn and continue"), a
# contradicting bullet added beside it, and a lower-case "pending" read as a
# pass. A whole-line pin is the only shape none of those walk past, so editing
# a Forgejo rule means editing its tuple here — deliberately.
#
# `_fj_invocations` stays the scanner; the parser below is local because the
# shared `_FJ_VALUE_FLAGS` does not know `--base`/`--head` or the long aliases,
# and the shared helpers are not ours to widen from here.
# --------------------------------------------------------------------------

_DONE_SKILL = "skills/project-done/SKILL.md"
_DONE_FORGEJO_HEADING = "### Forgejo (`issue_tracker: forgejo`)"
_FJ_FLAG_ALIASES = {
    "--repo": "-r", "--remote": "-R", "--autofill": "-A", "--agit": "-a",
    "--web": "-w", "--host": "-H", "--cwd": "-C",
}
_DONE_FJ_VALUE_FLAGS = {"-H", "-C", "-r", "-R", "--base", "--head", "--body", "--body-file", "--style"}
_SINGLE_PIPE = re.compile(r"(?<!\|)\|(?!\|)")
_REDIRECTED = re.compile(r'>\s*"<[^"]+>"\s+2>&1$')

_GOLDEN_DONE_FORGEJO = (
    '### Forgejo (`issue_tracker: forgejo`)',
    '**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다 — 조회가 증거다.** `project-issue` 의 Forgejo 절이 이슈 생성에 세운 원칙과 같은 원칙이고, 이 절은 그것을 PR 생성에 적용한다.',
    'harness 분기는 없다. forgejo 어댑터가 존재하지 않으므로 `harness_enabled` 값과 무관하게 `fj` 직접 호출이 유일한 경로다. 전역 옵션(`-H`)은 서브커맨드 앞에 온다. 이 경로는 디렉터리를 바꾸지 않는다 — GitHub 경로처럼 작업 CWD 그대로 8단계로 간다.',
    'Forgejo 는 PR 이 있으므로 위 Jira 의 직접 병합 경로로 보내지 않는다. **아래 펜스는 한 셸 호출로 실행한다** — 뒤 줄이 앞 줄의 변수를 읽고, 셸 변수는 다음 호출로 넘어가지 않으므로 뒤 단계가 쓸 값은 마지막 두 줄이 출력한다:',
    '```bash',
    'REPORT_ROOT="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    '[ -n "$REPORT_ROOT" ] && [ -d "$REPORT_ROOT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    'REPORT="$REPORT_ROOT/.task/plan/impl-report-<id>.md"',
    '[ -f "$REPORT" ] || { echo "no impl-report at $REPORT"; exit 1; }',
    'grep -qxF "<trailer>" "$REPORT" || printf \'\\n%s\\n\' "<trailer>" >> "$REPORT"',
    'TITLE="$(sed -n \'s/^# 구현 보고서: //p\' "$REPORT" | head -1)"',
    '[ -n "$TITLE" ] || { echo "no \'# 구현 보고서: \' title line in $REPORT"; exit 1; }',
    'CREATED="$(fj -H <forgejo_host> pr create "$TITLE" --body-file "$REPORT" --base "<base_branch>" --head "<branch-name>" -r <forgejo_repo>)" || CREATE_FAILED=1',
    'PR_NUMBER="$(printf \'%s\\n\' "$CREATED" \\',
    '| python3 -c \'import sys; sys.stdout.write(sys.stdin.read().replace("\\u2068", "").replace("\\u2069", ""))\' \\',
    '| sed -n \'s/^created pull request #\\([0-9][0-9]*\\).*/\\1/p\')"',
    'printf \'REPORT=%s\\nCREATE_FAILED=%s\\nPR_NUMBER=%s\\n\' "$REPORT" "${CREATE_FAILED:-0}" "$PR_NUMBER"',
    'printf \'%s\\n\' "$CREATED"',
    '```',
    '- **보고서는 절대 경로로 넘긴다.** `.task/plan/` 은 gitignore 되어 메인 체크아웃에만 있고, 작업 CWD 는 워크트리일 수 있다. 경로는 git 에게 메인 체크아웃을 물어 얻는다 — 작업 트리 루트나 현재 디렉터리에서 조립하면 워크트리에서 **절대 경로이지만 틀린 경로**가 된다. 파일이 없으면 PR 을 만들지 않고 멈춘다. 이 확인은 4단계가 보고서를 어디에 썼는지 대신 정해 주지 않는다 — 작업 CWD 에 쓰인 보고서는 여기서 "없음" 으로 드러나고, 그때는 메인 체크아웃의 이 경로로 옮긴 뒤 다시 실행한다.',
    '- **본문에 닫는 트레일러가 있어야 한다.** `<trailer>` 는 5단계의 커밋 트레일러와 같은 줄이다 — 기본 base 면 `Closes #<id>`, 서브-PR 이면 `Part of #<parent_issue>`. 기본 base 의 `Closes` 줄은 4단계 템플릿에 없으므로 여기서 확인하고 없으면 덧붙인다. 병합 시 Forgejo 가 `Closes` 로 이슈를 닫는 것은 실측 네 건에서 확인됐다. 네 건 모두 본문과 커밋 트레일러 양쪽에 줄이 있었으므로, 어느 쪽이 닫았는지는 **가르지 못했다** — 그래서 둘 다 둔다.',
    '- **서브-PR 의 본문에는 `Closes #<id>` 가 없어야 한다.** 보고서에 습관처럼 그 줄이 남아 있으면 지운 뒤 펜스를 실행한다 — 5단계가 서브-PR 에서 `Closes` 를 뺀 이유가 본문에서 되살아나지 않게 한다.',
    '- **`--base`/`--head` 를 명시한다.** GitHub 절과 같은 이유다 — 세 계층이 한 출처에 합의해야 한다. 저장소는 `-r <forgejo_repo>` 로만 준다. 이 리프 명령에는 `-R` 이 없다.',
    '- **제목은 보고서 첫 줄 한 곳에서 읽어 변수로 넘긴다.** 리터럴로 붙여넣으면 백틱이 명령 치환으로 실행된다. 그 줄이 없으면(영어 보고서 등) 빈 제목으로 PR 을 만들지 않고 멈춘다. 제목이 `WIP: ` 로 시작하면 Forgejo 는 draft PR 로 만든다.',
    '- **본문을 대신 채우는 플래그를 쓰지 않는다.** 이 명령의 `-A`(`--autofill`)는 커밋에서 본문을 만들어 impl-report 를 버린다. `-a` 는 라벨이 아니라 `--agit` 이고, `-w` 는 `--web` 이다 — 셋 다 이 경로에서 쓰지 않는다.',
    '- **격리 제거는 추출보다 앞에 둔다.** 생성 출력은 `issue create` 와 같은 모양(`created pull request #N: <title>`)이고 번호가 양방향 격리 문자로 감싸여 있다. 빼거나 뒤로 옮기면 추출이 에러 없이 빈 문자열을 돌려준다.',
    '두 실패의 복구가 다르다. 생성과 추출을 한 파이프라인으로 합치지 않은 이유가 이것이다:',
    '- `CREATE_FAILED` 가 `1` — PR 은 **만들어지지 않았다**(같은 head 의 PR 이 이미 열려 있는 경우 포함). 웹 UI 에서 사람이 `<branch-name>` 의 PR 을 확인하거나 만들어 번호를 돌려받는다. 검색으로 번호를 추측하지 않는다.',
    '- 생성은 됐는데 `PR_NUMBER` 가 비었다 — 펜스가 출력한 생성 출력 원문에서 번호를 읽는다. 읽을 수 없으면 웹 UI 에서 `<branch-name>` 의 열린 PR 을 찾는다. 제목 검색은 쓰지 않는다 — 결과를 좁히지 못하고 출력에 head 브랜치가 없어 같은 제목의 다른 PR 과 가를 수 없다.',
    'PR URL 은 `https://<forgejo_host>/<forgejo_repo>/pulls/<PR_NUMBER>` 로 조립한다 — `pr view` 출력에는 URL 이 없다. 읽기 확인:',
    '```bash',
    'fj -H <forgejo_host> pr view "<forgejo_repo>#<PR_NUMBER>" > "<log-file>" 2>&1',
    'python3 -c \'import sys; sys.stdout.write(sys.stdin.read().replace("\\u2068", "").replace("\\u2069", ""))\' < "<log-file>"',
    '```',
    '- 격리 제거한 출력의 1행은 `<TITLE> #<PR_NUMBER>`, 2행의 상태는 `Open`, 3행은 `From` 뒤에 `<branch-name>`, `into` 뒤에 `<base_branch>` 가 백틱으로 감싸여 나온다. 셋 중 하나라도 다르면 PR 을 **잘못 만든 것**으로 보고한다 — GitHub 절의 세 계층 합의를 Forgejo 에서 확인하는 자리가 여기다.',
)

_GOLDEN_DONE_STEP9_FORGEJO = (
    'Forgejo 에서는 `harness_enabled` 와 무관하게 위 Forgejo 줄로 게시한다 — forgejo 어댑터가 없으므로 첫 줄의 `add-comment` 는 부르지 않는다.',
    "- **저장소는 이슈 인자에 넣는다.** 이 명령은 `-r` 을 받지 않는다(`unexpected argument '-r'`). `-R` 은 저장소가 아니라 로컬 git remote 이름이라, owner/repo 를 넣으면 `no repo info specified` 로 실패한다. remote 이름으로 게시하는 형태는 실측되지 않았으므로 쓰지 않는다. 형제 명령(`pr create` 는 `-r` 을 받는다)과 표면이 다르다 — 한쪽에 맞춰 통일하지 않는다.",
    '- **성공이 조용하다 — 게시 여부는 조회로만 확인한다.** 성공 시 stdout 이 0 바이트이므로 종료코드와 출력으로는 알 수 없다:',
    '```bash',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments > "<log-file>" 2>&1',
    '```',
    '- 로그에서 방금 쓴 PR URL 을 찾는다. 코멘트 본문 줄은 `> ` 로 시작하는 평문이다(격리 문자는 작성자 줄에만 있다).',
    '- **코멘트 개수 비교로 게시를 확인하지 않는다 — 기본 `issue view` 표면은 개수만 보여 주고 본문이 없다.**',
    '- 찾지 못하면 코멘트를 **미반영**으로 보고하고 웹 UI 게시를 안내한다.',
    '- 본문에 백틱이나 따옴표가 들어가면 위치 인자 대신 절대 경로 `--body-file` 로 넘긴다.',
)

_GOLDEN_DONE_STEP11_FORGEJO = (
    '- **PR path (Forgejo)**: `gh pr checks` 의 대응물은 `fj pr status` 다. 저장소의 작업 목록과 함께 파일로 받아 읽는다. `--wait` 는 끝이 없으므로 쓰지 않는다:',
    '```bash',
    'fj -H <forgejo_host> pr status "<forgejo_repo>#<PR_NUMBER>" > "<log-file>" 2>&1',
    'fj -H <forgejo_host> actions tasks -r <forgejo_repo> > "<tasks-log-file>" 2>&1',
    '```',
    '- 판정은 로그의 체크 줄이 한다. `pr status` 는 체크가 Pending 이어도 종료코드 0 으로 끝나므로 종료코드 0 은 통과의 증거가 아니다.',
    '- 종료코드가 0 이 아니거나(병합된 PR 에서 이 명령은 패닉한다) 로그를 읽을 수 없으면 CI 상태를 unknown 으로 보고한다.',
    '- 체크 줄에 실패가 하나라도 있으면 실패로, 모두 성공이면 통과로 보고한다.',
    '- Pending 이고 `actions tasks` 가 총 0건이면 러너가 작업을 받지 않은 것이다 — "no checks ran" 발견사항으로 보고하고 통과로 세지 않는다.',
    '- `actions tasks` 는 저장소 전체의 작업 이력이다. 과거에 작업이 한 번이라도 돌았다면 총 0건 분기는 나오지 않고 아래 1건 이상 분기로 간다.',
    '- Pending 이고 `actions tasks` 가 1건 이상이면 그 작업이 이 PR 의 것인지 가를 수 없다(목록은 저장소 전체다) — "CI pending" 으로 보고하고 한도를 두고 다시 읽는다.',
    '- 체크가 돌지 않았으면 CI 가 돌렸어야 할 스위트를 로컬에서 돌린 결과를 함께 적는다 — 대체 게이트일 뿐 CI 결과를 대신하지 않는다.',
)

_GOLDEN_ISSUE_LINK_FORGEJO = (
    '- **Forgejo** — comments are part of the `fj` write contract in `~/.claude/skills/SKILL-CONFIG.md`.',
    'The repository goes in the issue argument: this command takes no `-r`, and its `-R` names a git',
    'remote, not `owner/repo`. Success prints nothing, so read it back with the `comments` surface and',
    "look for the plan's title line, quoted as `> # Plan: <title>`; if it is not there, report the",
    'comment as 미반영 (`project-done` Step 9 applies the same read-back to its own comment):',
    '```bash',
    "fj -H <forgejo_host> issue comment '<forgejo_repo>#<id>' --body-file '<plan-file>'",
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments > "<log-file>" 2>&1',
    '```',
)

_GOLDEN_DONE_STEP8_FORGEJO = '**Forgejo 에는 상태 전환 `fj` 계약이 없다.** `harness_enabled` 와 무관하게 이 단계의 명령을 부르지 않고, 상태를 **미반영**으로 보고한 뒤 계속한다. 라벨로 In Review 를 흉내 내지 않는다 — 근거는 `~/.claude/skills/SKILL-CONFIG.md` 의 "이슈 트래커" 절이다.'

_GOLDEN_DONE_STEP8_FENCE = '# fallback (Forgejo): none - see the Forgejo paragraph at the end of this step'

_GOLDEN_DONE_STEP10_FORGEJO = 'Forgejo 에서는 프로젝트 harness 가 `clean-temp` 를 노출할 때만 실행한다. 없으면 이 단계를 건너뛰고 건너뛴 사실을 보고한다.'

_GOLDEN_CONFIG_CONTRACT = '`forgejo` 는 조회(read) 전체와, 쓰기(write) 중 **이슈 생성·이슈 코멘트·PR 생성**이 계약이다. 이슈 생성의 상세 절차 — 필수 플래그, 이슈 번호 추출, 라벨 적용과 읽기 확인 — 는 `project-issue` 본문의 `### Forgejo` 절에, 이슈 코멘트와 PR 생성의 상세 절차 — 저장소 지정 형태, 조용한 성공과 조회 확인 — 는 `project-done` 의 7·9단계에 있다. 여기에 복제하지 않고 가리킨다.'

_GOLDEN_CONFIG_WRITE_FAILURE = '**이슈 생성은 `fj` 가 1순위이고, 웹 UI 수동 처리는 그 뒤의 마지막 단**이다. 계약이 있는 쓰기에서 `fj` 경로가 실패하면 웹 UI 수동 처리를 안내한다. 뒤 단계가 결과를 입력으로 쓰는 쓰기(이슈 번호·PR 번호)는 수동 결과를 받아 이후 단계를 진행한다 — 읽기 실패는 "미확인" 으로 넘길 수 있지만 이 쓰기의 실패는 그럴 수 없다. 번호는 로컬에서 합성할 수 없고 `project-start` 와 `project-done` 의 뒷단계가 그것을 입력으로 요구한다.'

_GOLDEN_CONFIG_UNCONSUMED = '결과를 아무도 입력으로 쓰지 않는 쓰기 — 이슈 코멘트, 그리고 위 줄의 상태 전환 — 가 되지 않았으면 미반영으로 보고하고 계속한다.'

_GOLDEN_ISSUE_OUTPUT_COMMENT = '- the comment result from Step 1-L: posted (with where it can be seen), declined, skipped for a recovery run, or 미반영 when the posted comment could not be read back. For every result but posted, include the Step 1-L command that would post `plan-<id>.md` later.'


def _done_skill() -> str:
    return read_skill(_DONE_SKILL)


def _stripped_lines(text: str, start: str, end: str) -> list[str]:
    """Non-blank stripped lines from the one line starting `start` up to `end`."""
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip().startswith(start)]
    assert len(starts) == 1, f"expected one line starting {start!r}, got {len(starts)}"
    stop = next((k for k in range(starts[0] + 1, len(lines)) if lines[k].strip().startswith(end)), None)
    assert stop is not None, f"no {end!r} after {start!r}"
    return [l.strip() for l in lines[starts[0]:stop] if l.strip()]


def _done_forgejo() -> str:
    """Step 7's Forgejo section: its heading line up to Step 8's heading."""
    section = "\n".join(_stripped_lines(_done_skill(), _DONE_FORGEJO_HEADING, "**8. Project status"))
    assert "pr create" in section, "the Forgejo section lost its PR creation"
    return section


def _done_step(heading: str) -> str:
    section = skill_section(_done_skill(), heading)
    assert section, f"project-done has no step starting {heading!r}"
    return section


def _fj_argv(invocation: str) -> list[str]:
    """Shell words up to the first redirect, with flag spellings normalised.

    `--repo=x` becomes `-r x`, `-rX` becomes `-r X` for a value flag, a cluster
    such as `-Aw` becomes `-A -w`, and every long alias becomes its short form.
    Without this, each flag ban below is a string comparison that another
    spelling of the same flag walks past.
    """
    import shlex

    words: list[str] = []
    for token in shlex.split(invocation):
        if re.match(r"^\d*>", token):
            break
        if token.startswith("--") and "=" in token:
            flag, value = token.split("=", 1)
            words.extend([_FJ_FLAG_ALIASES.get(flag, flag), value])
        elif token.startswith("--"):
            words.append(_FJ_FLAG_ALIASES.get(token, token))
        elif re.fullmatch(r"-[A-Za-z]\S+", token):
            if token[:2] in _DONE_FJ_VALUE_FLAGS:
                words.extend([token[:2], token[2:]])
            else:
                words.extend("-" + ch for ch in token[1:])
        else:
            words.append(token)
    return words


def _fj_roles(invocation: str) -> tuple[dict[str, list[str]], list[str]]:
    """({flag: [values]}, positionals) — positionals include `fj` and the subcommand path.

    A value flag with no value after it (end of line, or another flag next) is
    recorded with the value `None`, so `--body-file` alone cannot pass as a body.
    """
    flags: dict[str, list] = {}
    positionals: list[str] = []
    words = _fj_argv(invocation)
    index = 0
    while index < len(words):
        word = words[index]
        if word.startswith("-"):
            value = None
            if word in _DONE_FJ_VALUE_FLAGS:
                nxt = words[index + 1] if index + 1 < len(words) else None
                if nxt is not None and not nxt.startswith("-"):
                    value = nxt
                    index += 1
            flags.setdefault(word, []).append(value)
        else:
            positionals.append(word)
        index += 1
    return flags, positionals


def _fenced_fj_lines(text: str) -> list[str]:
    return [l for l in _logical_lines(_fenced(text)) if re.search(r"\bfj\s", l)]


def _inline_fj_spans(text: str) -> list[str]:
    return re.findall(r"`(fj\s[^`]*)`", text)


def _all_done_fj() -> list[str]:
    return _fj_invocations(_done_skill()) + _inline_fj_spans(_done_skill())


def test_fj_parser_normalises_spellings_and_needs_values() -> None:
    """The parser is a guard too; a parser that mis-reads passes bad documents."""
    flags, positionals = _fj_roles("fj -H h pr create \"$T\" --repo=o/r -Aw --body-file")
    assert flags["-r"] == ["o/r"] and "-A" in flags and "-w" in flags
    assert flags["--body-file"] == [None], "a value flag with no value was read as satisfied"
    assert positionals == ["fj", "pr", "create", "$T"]
    flags, positionals = _fj_roles("fj -H h issue view \"o/r#1\" comments > \"<log>\" 2>&1")
    assert positionals == ["fj", "issue", "view", "o/r#1", "comments"] and "-H" in flags


def test_done_forgejo_section_sits_after_jira_and_before_step_8() -> None:
    lines = [l.strip() for l in _done_skill().splitlines()]
    assert lines.count(_DONE_FORGEJO_HEADING) == 1
    jira = lines.index("### Jira (`issue_tracker: jira`)")
    forgejo = lines.index(_DONE_FORGEJO_HEADING)
    step8 = next(i for i, l in enumerate(lines) if l.startswith("**8. Project status"))
    assert jira < forgejo < step8, "the Forgejo section is out of place"


def test_done_forgejo_prose_and_fences_are_pinned_whole() -> None:
    """Golden pins: every Forgejo line in project-done, SKILL-CONFIG and link mode."""
    text = _done_skill()
    assert tuple(_stripped_lines(text, _DONE_FORGEJO_HEADING, "**8. Project status")) == _GOLDEN_DONE_FORGEJO
    assert tuple(_stripped_lines(
        text, "Forgejo 에서는 `harness_enabled` 와 무관하게 위 Forgejo 줄로", "**9-H."
    )) == _GOLDEN_DONE_STEP9_FORGEJO
    assert tuple(_stripped_lines(
        text, "- **PR path (Forgejo)**", "- **Branch-merge path"
    )) == _GOLDEN_DONE_STEP11_FORGEJO
    assert tuple(_stripped_lines(
        _issue_skill(), "- **Forgejo** — comments are part of the `fj` write contract",
        "**2. User Confirmation**",
    )) == _GOLDEN_ISSUE_LINK_FORGEJO

    config = read_skill("skills/SKILL-CONFIG.md")
    for line in (_GOLDEN_CONFIG_CONTRACT, _GOLDEN_CONFIG_WRITE_FAILURE, _GOLDEN_CONFIG_UNCONSUMED):
        assert_whole_line(config, line)
    assert_whole_line(_issue_skill(), _GOLDEN_ISSUE_OUTPUT_COMMENT)
    assert_whole_line(_done_step("**10. Clean temporary files**"), _GOLDEN_DONE_STEP10_FORGEJO)


def test_done_every_fenced_fj_call_is_visible_to_the_scanner() -> None:
    """A call the scanner cannot see is a call no flag ban below applies to.

    `timeout 60 fj …`, `if fj …; then`, `env X=1 fj …` are all real shell and
    all invisible to `_FJ_LINE_RE`, so the count of fenced lines naming fj has
    to equal the count the scanner parsed.
    """
    text = _done_skill()
    fenced = _fenced_fj_lines(text)
    parsed = _fj_invocations(_fenced(text))
    assert len(fenced) == len(parsed), (
        "a fenced fj call is written in a form the scanner does not parse:\n" + "\n".join(fenced)
    )
    for shape in ("pr create", "pr view", "issue comment", "issue view", "pr status", "actions tasks"):
        assert any(shape in inv for inv in parsed), f"project-done no longer invokes `fj {shape}`"


def test_done_forgejo_pr_create_passes_what_it_must_and_nothing_it_must_not() -> None:
    section = _done_forgejo()
    creates = [inv for inv in _fj_invocations(section) if "pr create" in inv]
    everywhere = [inv for inv in _all_done_fj() if "pr create" in inv]
    assert len(creates) == 1 and len(everywhere) == 1, (
        f"expected exactly one documented `fj pr create`, got {everywhere}"
    )

    flags, positionals = _fj_roles(creates[0])
    for required in ("--base", "--head", "--body-file", "-r"):
        assert flags.get(required) and None not in flags[required], (
            f"`fj pr create` does not pass {required} with a value: {creates[0]}"
        )
    for banned in ("-A", "-a", "-w", "-R", "--body"):
        assert banned not in flags, f"`fj pr create` passes {banned}: {creates[0]}"
    assert flags["--body-file"] == ["$REPORT"], "the PR body is not the resolved absolute report path"
    assert positionals == ["fj", "pr", "create", "$TITLE"], (
        f"the title is not the one variable positional: {positionals}"
    )

    raw = [l for l in _fenced_fj_lines(section) if "pr create" in l]
    assert raw[0].startswith('CREATED="$(fj ') and raw[0].endswith("|| CREATE_FAILED=1"), (
        "PR creation is no longer captured on its own, apart from the parse"
    )
    commands = _logical_lines(_fenced(section))
    titles = [c for c in commands if c.startswith("TITLE=")]
    assert len(titles) == 1 and titles[0].startswith('TITLE="$(sed -n \'s/^# 구현 보고서: //p\' "$REPORT"'), (
        f"the title is not read from the report: {titles}"
    )
    title_at = commands.index(titles[0])
    assert commands[title_at + 1].startswith('[ -n "$TITLE" ] ||') and "exit 1" in commands[title_at + 1], (
        "an empty title is no longer stopped before `pr create`"
    )


def test_done_forgejo_prints_what_later_steps_need() -> None:
    """Shell variables die with the call; the fence has to print its results."""
    commands = _logical_lines(_fenced(_done_forgejo()))
    report = [c for c in commands if c.startswith("printf 'REPORT=%s")]
    assert len(report) == 1, "the fence no longer prints REPORT/CREATE_FAILED/PR_NUMBER"
    for var in ('"$REPORT"', '"${CREATE_FAILED:-0}"', '"$PR_NUMBER"'):
        assert var in report[0], f"the printed state lost {var}"
    assert commands[commands.index(report[0]) + 1] == "printf '%s\\n' \"$CREATED\"", (
        "the raw create output is no longer printed for a human to read"
    )


def test_done_forgejo_resolves_the_report_in_the_main_checkout() -> None:
    section = _done_forgejo()
    commands = _logical_lines(_fenced(section))

    roots = [c for c in commands if c.startswith("REPORT_ROOT=")]
    assert roots == ['REPORT_ROOT="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"'], (
        f"the main checkout is not the first worktree git reports: {roots}"
    )
    guard = commands.index('[ -n "$REPORT_ROOT" ] && [ -d "$REPORT_ROOT" ] || {')
    assert commands[guard + 1] == 'echo "could not resolve the main checkout"; exit 1; }', (
        "an unresolved main checkout no longer stops the fence"
    )
    assert '[ -f "$REPORT" ] || { echo "no impl-report at $REPORT"; exit 1; }' in commands, (
        "a missing report no longer stops the fence before `--body-file` reads it"
    )
    for wrong in ("--show-toplevel", "--git-common-dir", "--path-format", "$PWD", "$(pwd)"):
        offenders = [c for c in commands if wrong in c]
        assert not offenders, f"the report path is derived from {wrong}, wrong in a worktree: {offenders}"
    assert "MAIN_CHECKOUT" not in section, (
        "the Jira merge's variable is reused; Step 7's one-resolution guard counts it"
    )


def test_done_forgejo_puts_the_closing_trailer_in_the_pr_body() -> None:
    assert 'grep -qxF "<trailer>" "$REPORT" || printf \'\\n%s\\n\' "<trailer>" >> "$REPORT"' in (
        _logical_lines(_fenced(_done_forgejo()))
    ), "the PR body is no longer checked for its closing trailer"


def test_done_forgejo_isolate_strip_actually_yields_the_number() -> None:
    """Run the documented extraction on a real-shaped create output.

    A text check on order passed a `tr -d` rewrite that deletes the digits of
    the escape sequence along with the number. Running the pipeline is the
    check that cannot be satisfied by wording.
    """
    import subprocess

    lines = _logical_lines(_fenced(_done_forgejo()))
    extract = [l for l in lines if l.startswith("PR_NUMBER=")]
    assert len(extract) == 1, f"expected one PR number extraction, got {extract}"
    line = extract[0]
    assert line.index("\\u2068") < line.index("created pull request #"), (
        "the isolate strip runs after the extraction"
    )
    sample = "created pull request #\u2068" + "27" + "\u2069: \u2068t\u2069"
    result = subprocess.run(
        ["bash", "-c", line + '\nprintf "%s" "$PR_NUMBER"'],
        env={"CREATED": sample, "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
        capture_output=True, text=True,
    )
    assert result.stdout == "27", f"the extraction yields {result.stdout!r} (stderr {result.stderr!r})"

    strip = [l for l in lines if l.startswith("python3 -c") and l.endswith('< "<log-file>"')]
    assert len(strip) == 1, "the read-back no longer strips isolates before comparing"


def test_done_forgejo_reads_the_created_pr_back_and_never_searches() -> None:
    section = _done_forgejo()
    views = [l for l in _fenced_fj_lines(section) if "pr view" in l]
    assert len(views) == 1, f"expected one PR read-back, got {views}"
    _, positionals = _fj_roles(views[0])
    assert positionals == ["fj", "pr", "view", "<forgejo_repo>#<PR_NUMBER>"]
    assert _REDIRECTED.search(views[0]) and not _SINGLE_PIPE.search(views[0])
    searches = [inv for inv in _all_done_fj() if "search" in inv]
    assert not searches, f"a title search stands in for the PR number: {searches}"


def test_done_step8_reports_forgejo_status_as_not_applied() -> None:
    step8 = _done_step("**8. Project status")
    assert_whole_line(step8, _GOLDEN_DONE_STEP8_FORGEJO)
    assert_whole_line(step8, _GOLDEN_DONE_STEP8_FENCE)
    assert step8.index(_GOLDEN_DONE_STEP8_FORGEJO) > step8.index("> Limitation:"), (
        "the Forgejo paragraph sits where the GitHub-only paragraphs read as applying to it"
    )
    assert not _fj_invocations(step8), "Step 8 invokes fj, which has no status contract"
    labels = [l.strip() for l in step8.splitlines() if re.search(r"라벨|label", l, re.IGNORECASE)]
    assert len(labels) == 3 and _GOLDEN_DONE_STEP8_FORGEJO in labels, (
        f"a label line was added to the status step: {labels}"
    )
    edits = [inv for inv in _all_done_fj() if "issue edit" in inv or "labels" in inv]
    assert not edits, f"a label stands in for a status: {edits}"


def test_done_step9_posts_the_forgejo_comment_in_the_measured_form() -> None:
    step9 = _done_step("**9. Post issue comment**")
    invocations = _fj_invocations(step9)

    comments = [inv for inv in invocations if "issue comment" in inv]
    assert len(comments) == 1, f"expected one Forgejo comment call, got {comments}"
    flags, positionals = _fj_roles(comments[0])
    for banned in ("-r", "-R"):
        assert banned not in flags, f"`fj issue comment` passes {banned}: {comments[0]}"
    assert positionals[:4] == ["fj", "issue", "comment", "<forgejo_repo>#<id>"], positionals
    assert len(positionals) == 5 or (flags.get("--body-file") and None not in flags["--body-file"]), (
        "the comment has no body, so fj opens an editor"
    )

    views = [l for l in _fenced_fj_lines(step9) if "issue view" in l]
    assert len(views) == 1, f"expected one comment read-back, got {views}"
    _, positionals = _fj_roles(views[0])
    assert positionals == ["fj", "issue", "view", "<forgejo_repo>#<id>", "comments"], positionals
    assert _REDIRECTED.search(views[0]) and not _SINGLE_PIPE.search(views[0])


def test_done_step11_reads_forgejo_checks_without_trusting_the_exit_code() -> None:
    step11 = _done_step("**11. Check CI**")
    invocations = _fj_invocations(step11)

    statuses = [inv for inv in invocations if "pr status" in inv]
    tasks = [inv for inv in invocations if "actions tasks" in inv]
    assert len(statuses) == 1 and len(tasks) == 1, f"{statuses} / {tasks}"
    flags, positionals = _fj_roles(statuses[0])
    assert positionals == ["fj", "pr", "status", "<forgejo_repo>#<PR_NUMBER>"], positionals
    for banned in ("--wait", "-r", "-R"):
        assert banned not in flags, f"`fj pr status` passes {banned}"
    waits = [inv for inv in _all_done_fj() if "--wait" in _fj_argv(inv)]
    assert not waits, f"an unbounded `--wait` is documented: {waits}"

    for line in _fenced_fj_lines(step11):
        assert not _SINGLE_PIPE.search(line), f"a CI read is piped: {line}"
        assert _REDIRECTED.search(line), f"a CI read is not redirected to a file: {line}"

    # Across the whole step, not only the Forgejo group, and in any case: a
    # line anywhere in Step 11 that pairs pending with a pass is a pass rule.
    pinned = set(_GOLDEN_DONE_STEP11_FORGEJO) | {
        # The pre-existing shared rule, which says the opposite of a pass.
        '- **Do not report "complete" while CI is unverified.** A PR whose checks have not been '
        'read is an unknown, not a pass. Say "CI pending" and what you are waiting on.',
    }
    loose = [
        l.strip() for l in step11.splitlines()
        if re.search(r"pending|대기", l, re.IGNORECASE)
        and re.search(r"통과|\bpass|green|성공", l, re.IGNORECASE)
        and l.strip() not in pinned
    ]
    assert not loose, f"a line reads Pending as a pass: {loose}"


def test_done_step12_reports_the_forgejo_pr_url() -> None:
    assert_whole_line(
        _done_step("**12. Output**"), "- PR URL (GitHub/Forgejo), or merge commit hash (Jira)"
    )


def test_done_cites_the_principle_and_carries_no_language_command() -> None:
    text = _done_skill()
    assert "읽기 확인이 증거다" not in text, "project-issue's principle was copied, not cited"
    assert_rule(
        text, "조회가 증거다",
        starts_with="**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다",
    )
    for command in ("pytest", "uv run"):
        assert command not in text, f"a language-specific command leaked into project-done: {command}"


def test_skill_config_names_the_forgejo_surface_whole() -> None:
    assert_whole_line(read_skill("skills/SKILL-CONFIG.md"), (
        "issue_tracker = forgejo → fj CLI (forgejo-cli 필요) — 조회: issue view/search · "
        "생성: issue create · 코멘트: issue comment · PR: pr create"
    ))


def test_no_skill_still_says_comments_have_no_fj_contract() -> None:
    """SKILL-CONFIG and project-issue's link mode disagreed once; neither may regress alone."""
    offenders: list[str] = []
    for md in _skill_docs():
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            lowered = line.lower()
            if not re.search(r"comment|코멘트|댓글", lowered):
                continue
            if re.search(r"no `?fj`? contract|계약이 없|계약 밖|웹 UI 가 1순위", lowered):
                offenders.append(f"{md.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "comments are declared uncontracted again:\n" + "\n".join(offenders)
