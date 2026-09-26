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
        "$project-start <issue-id> [in-place] [adr]",
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
        if "issue view" in inv and "<ISSUE_NUMBER>" in inv
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
    assert '(main_worktree_root() / ".task" / "plan").glob("plan-*.md")' in text, (
        "the discovery fallback no longer globs the main checkout's plan directory"
    )
    assert "**Two or more files**" in text, "the ambiguity branch is gone"


def test_codex_reference_shows_the_plan_path_argument() -> None:
    """Whole lines, not substrings: the old line is a prefix of the new one."""
    lines = [l.strip() for l in read_skill("skills/_shared/references/codex.md").splitlines()]

    assert "$project-issue [<plan-path>] [--issue <id>]" in lines
    assert "$project-issue [<plan-path>]" not in lines, "codex still shows project-issue without --issue"
    assert "$project-iterate <id> [in-place] [adr]" in lines, "codex does not show the <id> re-entry"


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
    assert 'git -C "$FIRST_WORKTREE" rev-parse --show-toplevel' in resolve[0], (
        f"the main checkout is no longer resolved by asking git for it: {resolve[0]!r}"
    )
    assert any("git worktree list" in c for c in _commands(merge, "FIRST_WORKTREE=")), (
        "the first worktree entry is no longer read from git worktree list"
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
        "- With `--issue` and no `<plan-path>`, discovery never runs: when `plan-<id>.md` already exists "
        "this is revision mode, and otherwise stop before Step 1, because discovery would take whatever "
        "single draft is there, and nothing in a draft names its issue."
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


def test_doc_id_pattern_is_the_code_definition() -> None:
    """The docs' inline id regex is a copy of `config.ISSUE_ID_PATTERN` (#32).

    `rename_plan_to_issue` and `plan-file` validate with the code definition;
    the skill commands validate with the inline copy before they get there. Two
    definitions that drift apart let one layer accept what the other refuses.
    """
    from harness_core.config import ISSUE_ID_PATTERN

    inline = re.search(r're\.fullmatch\(r"([^"]+)", $', _ID_PATTERN)
    assert inline, "_ID_PATTERN no longer has the shape this test reads"
    assert inline.group(1) == ISSUE_ID_PATTERN.pattern

    copies = [
        (str(md.relative_to(ROOT)), m.group(1))
        for md in sorted((ROOT / "skills").rglob("SKILL.md"))
        for m in re.finditer(r're\.fullmatch\(r"([^"]+)", ', md.read_text(encoding="utf-8"))
    ]
    # #50 moved the path-only checks to shell, so the copies are now `grep -Eqx`.
    copies += [
        (str(md.relative_to(ROOT)), m.group(1))
        for md in sorted((ROOT / "skills").rglob("SKILL.md"))
        for m in re.finditer(r"grep -Eqx '([^']+)'", md.read_text(encoding="utf-8"))
    ]
    assert len(copies) >= 5, f"the inline copies moved: {copies}"
    drifted = [c for c in copies if c[1] != ISSUE_ID_PATTERN.pattern]
    assert not drifted, f"an inline id regex differs from config.ISSUE_ID_PATTERN: {drifted}"


def test_step_8_revalidates_and_refuses_to_overwrite() -> None:
    text = _issue_skill()
    step8 = _step8()
    fenced = _fenced(step8)

    assert "mv " not in fenced, "Step 8 renames with mv again"
    mentions = [l.strip() for l in step8.splitlines() if "rename-plan" in l]
    assert len(mentions) == 1 and mentions[0].startswith("- `<harness_cli> rename-plan` is not used here"), (
        f"Step 8 offers rename-plan, which a project without a harness_cli cannot run: {mentions}"
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
        "- `<harness_cli> rename-plan` is not used here: this step has to run in projects that "
        "have no harness_cli, and the command above reaches the same `rename_plan_to_issue`, which "
        "itself refuses a source that is not a draft in the plan directory and an id that is not "
        "an issue number or ticket key."
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


def test_link_mode_comment_follows_the_tracker_row() -> None:
    """#45: a tracker with a Plan Body Rules row posts on Step 2's yes; one without asks on its own."""
    section = _link_mode()
    offer = section.index("5. **After Step 8, post the plan as a comment.**")
    assert offer > section.index("4. **Confirm, then rename.**"), "the comment is offered before the rename"

    assert_whole_line(section, (
        "- On a tracker with a row in `## Plan Body Rules`, Step 2's yes already covers the comment: run "
        "that section's post fence with `<rev>` — the `REV=` value on the screen that received the yes, "
        "never a new run of item 4 — and report the `COMMENT=` line it prints. Nothing is asked again."
    ))
    assert_whole_line(section, (
        "- On a tracker without a row, ask on its own — `Post plan-<id>.md to #<id> as a comment? [yes/no]` "
        "— separately from Step 2."
    ))
    assert_whole_line(section, (
        "- On a tracker without a row, the comment is posted only on its own yes; a no is not an error, "
        "because the local `plan-<id>.md` is the canonical plan either way."
    ))
    assert_whole_line(section, (
        "- If the issue body read in item 3 is the same text as the draft, the body already is "
        "this plan (a create-mode Step 8 failure being recovered): do not ask, and report the "
        "comment as skipped."
    ))

    lines = [l.strip() for l in section[offer:].splitlines()]
    assert "jira issue comment add \"<id>\" --template '<plan-file>' --no-input" in lines
    # The row trackers post through the Plan Body Rules fences, never a bare comment call here.
    for bare in ("gh issue comment", "fj -H <forgejo_host> issue comment"):
        assert not any(bare in l for l in lines), f"link mode posts outside the Plan Body Rules fence: {bare}"
    rules = _i45_rules()
    assert "gh issue comment \"<id>\" --body-file \"$BODY_FILE\"" in rules
    assert "fj -H <forgejo_host> issue comment '<forgejo_repo>#<id>' --body-file \"$BODY_FILE\"" in rules


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

    assert not re.search(r'(?<!\$MAIN_CHECKOUT/)\.task/plan/plan-<id>\.md', text), "the plan check is CWD-relative again"
    assert 'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<id>.md"' in fenced
    assert "LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*'" in fenced, "the plan check takes an unvalidated id"
    assert 'git branch -a --list "*issue-<id>-*" "*/<id>-*"' in fenced
    branch_lines = [l for l in fenced.splitlines() if "git branch" in l]
    assert not any("grep" in l for l in branch_lines) and "\\| grep" not in text, (
        "the branch check matches id prefixes again"
    )


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
    assert 'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<issue-id>.md"' in fenced, "the plan check is CWD-relative"
    assert "LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*'" in fenced, "the plan check takes an unvalidated id"
    assert '[ -f "$PLAN" ] || { echo "no plan at $PLAN"; exit 1; }' in fenced, (
        "a missing plan no longer ends the check non-zero"
    )
    assert_whole_line(section, (
        "- If `plan-<issue-id>.md` does not exist, stop here — before any branch, worktree, "
        "status change or ADR — and point the user to `project-iterate <issue-id>`, or to writing "
        "a draft and running `project-issue <plan-path> --issue <issue-id>`."
    ))

    step5 = skill_section(text, "**5. Load plan**")
    assert step5
    assert_whole_line(step5, "Read `<plan-path>`, the absolute path Step 1-A printed in the main worktree's plan directory.")
    assert "issue body" not in step5, "the issue-body fallback is back"
    assert not re.search(r'(?<!\$MAIN_CHECKOUT/)\.task/plan/plan-<issue-id>\.md', text), (
        "a CWD-relative plan path is back"
    )

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
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'REPORT_ROOT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
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
    '- **보고서는 절대 경로로 넘긴다.** `.task/plan/` 은 gitignore 되어 메인 체크아웃에만 있고, 작업 CWD 는 워크트리일 수 있다. 경로는 git 에게 메인 체크아웃을 물어 얻는다 — 작업 트리 루트나 현재 디렉터리에서 조립하면 워크트리에서 **절대 경로이지만 틀린 경로**가 된다. 해석 네 줄은 1단계 fallback 펜스와 바이트까지 같고(정본: `worktree.md`), `plan-file` 도 같은 규칙이라, 4단계가 쓴 `<report-path>` 가 여기서 그대로 나온다 — 파일이 없으면 PR 을 만들지 않고 멈추고, 4단계가 어디에 썼는지 확인한다.',
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
    '**Forgejo** check:',
    '```bash',
    'SEEN="$(mktemp)" || exit 1',
    'trap \'rm -f "$SEEN"\' EXIT',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >> "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'python -m harness_core.plan_body forgejo --issue \'<id>\' --seen "$SEEN" --dry-run',
    '```',
    '**Forgejo** post:',
    '```bash',
    'SEEN="$(mktemp)" || exit 1',
    'BODY_FILE="$(mktemp)" || exit 1',
    'trap \'rm -f "$SEEN" "$BODY_FILE"\' EXIT',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >> "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'python -m harness_core.plan_body forgejo --issue \'<id>\' --expect-rev \'<rev>\' --seen "$SEEN" --out "$BODY_FILE"',
    'RC=$?',
    '[ "$RC" = 3 ] && { echo "COMMENT=skipped"; exit 0; }',
    '[ "$RC" = 0 ] || { echo "COMMENT=미반영 (no body)"; exit 1; }',
    'fj -H <forgejo_host> issue comment \'<forgejo_repo>#<id>\' --body-file "$BODY_FILE"',
    'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<id>" comments >| "$SEEN" || { echo "COMMENT=미반영 (read-back failed)"; exit 1; }',
    'python -m harness_core.plan_body forgejo --issue \'<id>\' --expect-rev \'<rev>\' --seen "$SEEN" --dry-run > /dev/null',
    '[ "$?" = 3 ] && echo "COMMENT=posted" || { echo "COMMENT=미반영"; exit 1; }',
    '```',
    '- The Forgejo comment takes the repository in the issue argument: `issue comment` has no `-r`, and its `-R` names a git remote. Success prints nothing, so the read-back is the only evidence, as in `project-done` Step 9.',
    "- `fj` quotes every line of a body or comment with `> ` and wraps the lines between them in U+2068/U+2069; the module splits a Forgejo read into one entry per run of quoted lines, and takes GitHub's `--json body,comments` output as it is. The reads write with `>|` so a shell with `noclobber` set can still overwrite the file `mktemp` made.",
)

_GOLDEN_DONE_STEP8_FORGEJO = '**Forgejo 에는 상태 전환 `fj` 계약이 없다.** `harness_enabled` 와 무관하게 이 단계의 명령을 부르지 않고, 상태를 **미반영**으로 보고한 뒤 계속한다. 라벨로 In Review 를 흉내 내지 않는다 — 근거는 `~/.claude/skills/SKILL-CONFIG.md` 의 "이슈 트래커" 절이다.'

_GOLDEN_DONE_STEP8_FENCE = '# fallback (Forgejo): none - see the Forgejo paragraph at the end of this step'

_GOLDEN_DONE_STEP10_FORGEJO = 'Forgejo 에서는 프로젝트 harness 가 `clean-temp` 를 노출할 때만 실행한다. 없으면 이 단계를 건너뛰고 건너뛴 사실을 보고한다.'

_GOLDEN_CONFIG_CONTRACT = '`forgejo` 는 조회(read) 전체와, 쓰기(write) 중 **이슈 생성·이슈 코멘트·PR 생성**이 계약이다. 이슈 생성의 상세 절차 — 필수 플래그, 이슈 번호 추출, 라벨 적용과 읽기 확인 — 는 `project-issue` 본문의 `### Forgejo` 절에, 이슈 코멘트와 PR 생성의 상세 절차 — 저장소 지정 형태, 조용한 성공과 조회 확인 — 는 `project-done` 의 7·9단계에 있다. 여기에 복제하지 않고 가리킨다.'

_GOLDEN_CONFIG_WRITE_FAILURE = '**이슈 생성은 `fj` 가 1순위이고, 웹 UI 수동 처리는 그 뒤의 마지막 단**이다. 계약이 있는 쓰기에서 `fj` 경로가 실패하면 웹 UI 수동 처리를 안내한다. 뒤 단계가 결과를 입력으로 쓰는 쓰기(이슈 번호·PR 번호)는 수동 결과를 받아 이후 단계를 진행한다 — 읽기 실패는 "미확인" 으로 넘길 수 있지만 이 쓰기의 실패는 그럴 수 없다. 번호는 로컬에서 합성할 수 없고 `project-start` 와 `project-done` 의 뒷단계가 그것을 입력으로 요구한다.'

_GOLDEN_CONFIG_UNCONSUMED = '결과를 아무도 입력으로 쓰지 않는 쓰기 — 이슈 코멘트, 그리고 위 줄의 상태 전환 — 가 되지 않았으면 미반영으로 보고하고 계속한다.'

_GOLDEN_ISSUE_OUTPUT_COMMENT = '- the comment result from Step 1-L, on a tracker without a row: posted (with where it can be seen), declined, skipped for a recovery run, or 미반영 when the posted comment could not be read back. For every result but posted, include the Step 1-L command that would post `plan-<id>.md` later.'


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
        _issue_skill(), "**Forgejo** check:", "## Instructions",
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
    assert roots == ['REPORT_ROOT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"'], (
        f"the main checkout is not the work tree git reports for the first entry: {roots}"
    )
    assert [c for c in commands if c.startswith("FIRST_WORKTREE=")] == ['FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"'], (
        "the first worktree entry is not read from git worktree list"
    )
    guard = commands.index('[ -n "$REPORT_ROOT" ] && [ -d "$REPORT_ROOT" ] || {')
    assert commands[guard + 1] == 'echo "could not resolve the main checkout"; exit 1; }', (
        "an unresolved main checkout no longer stops the fence"
    )
    assert '[ -f "$REPORT" ] || { echo "no impl-report at $REPORT"; exit 1; }' in commands, (
        "a missing report no longer stops the fence before `--body-file` reads it"
    )
    for wrong in ("--show-toplevel", "--git-common-dir", "--path-format", "$PWD", "$(pwd)"):
        # The one allowed --show-toplevel asks about the first entry, not the CWD.
        offenders = [c for c in commands if wrong in c and c not in roots]
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


# --------------------------------------------------------------------------
# #38 — whether `.task/plan/` is ignored is asked of git, not of `.gitignore`'s
# text. A string comparison saw only its own literal line and appended a
# duplicate under an existing `.task/` (PR #44 did). These tests run the
# documented fence rather than read it: a wording check passes a snippet that
# is spelled right and behaves wrong.
# --------------------------------------------------------------------------

import os
import shutil
import subprocess

import pytest

_IGNORE_CHECK_START = "git check-ignore -q --no-index .task/plan/ && rc=0 || rc=$?"
_IGNORE_CHECK_STEPS = {
    "project-done": ("skills/project-done/SKILL.md", "**5. Commit source changes**"),
    "project-plan": ("skills/project-plan/SKILL.md", "**3. Create plan-draft-<slug>.md**"),
}


def _fence_blocks(text: str) -> list[list[str]]:
    """Each fenced block's lines, markers excluded, trailing space stripped.

    A fence closes only on a bare run of at least as many backticks as opened
    it, so a four-backtick fence holding a nested three-backtick one (as in
    project-release-doc) stays one block instead of flipping inside and out.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    opener = ""
    for line in text.splitlines():
        marker = re.match(r"\s*(`{3,})(.*)$", line)
        if current is None:
            if marker:
                current, opener = [], marker.group(1)
            continue
        if marker and marker.group(1).startswith(opener) and not marker.group(2).strip():
            blocks.append(current)
            current = None
            continue
        current.append(line.rstrip())
    return blocks


def _ignore_check_spans(block: list[str]) -> list[tuple[int, int]]:
    """(start, end) line indexes, inclusive, of each ignore check in one block."""
    spans = []
    for i, line in enumerate(block):
        if line.strip() == _IGNORE_CHECK_START:
            end = next((k for k in range(i + 1, len(block)) if block[k].strip() == "esac"), None)
            assert end is not None, f"an ignore check has no closing `esac`: {block[i:]}"
            spans.append((i, end))
    return spans


def _ignore_check_block(skill: str) -> tuple[int, list[str], list[list[str]]]:
    """The step's one ignore check: (its block index, its lines, all the step's blocks)."""
    path, heading = _IGNORE_CHECK_STEPS[skill]
    section = skill_section(read_skill(path), heading)
    assert section, f"{path} has no step starting {heading!r}"
    blocks = _fence_blocks(section)
    found = [(bi, s, e) for bi, block in enumerate(blocks) for s, e in _ignore_check_spans(block)]
    assert len(found) == 1, f"{skill}: expected one ignore check in {heading}, found {len(found)}"
    bi, start, end = found[0]
    return bi, blocks[bi][start:end + 1], blocks


def _ignore_check(skill: str) -> str:
    lines = _ignore_check_block(skill)[1]
    assert len(lines) > 2, f"{skill}: the ignore check is empty"
    return "\n".join(lines) + "\n"


def test_ignore_check_is_one_snippet_shared_by_both_steps() -> None:
    assert _ignore_check("project-done") == _ignore_check("project-plan"), (
        "project-done Step 5 and project-plan Step 3 drifted apart"
    )


def test_no_skill_decides_the_plan_ignore_by_reading_gitignore() -> None:
    """Fenced commands and inline code only — prose may name `.gitignore`."""
    offenders: list[str] = []
    for md in _skill_docs():
        text = md.read_text(encoding="utf-8")
        candidates = [l for block in _fence_blocks(text) for l in _logical_lines("\n".join(block))]
        candidates += [
            span for line, in_fence in _outside_fences(text) if not in_fence
            for span in re.findall(r"`([^`]+)`", line)
        ]
        for c in candidates:
            c = c.replace("\\", "")  # `\.task\/plan` is still task/plan
            if re.search(r"\b(grep|rg|awk|sed)\b", c) and ".gitignore" in c and "task/plan" in c:
                offenders.append(f"{md.relative_to(ROOT)}: {c}")
    assert not offenders, "the ignore is decided by .gitignore's text again:\n" + "\n".join(offenders)


def test_every_gitignore_write_in_the_skills_is_the_shared_check() -> None:
    """A stale second copy next to the snippet would run too."""
    snippets = 0
    offenders: list[str] = []
    for md in _skill_docs():
        for block in _fence_blocks(md.read_text(encoding="utf-8")):
            spans = _ignore_check_spans(block)
            snippets += len(spans)
            for i, line in enumerate(block):
                writes = re.search(r">>\s*\S*\.gitignore|\btee\b[^|]*\.gitignore", line)
                # Scoped to the plan directory: project-iterate's warning-only
                # `.claude/worktrees/` check (#42) asks git about another path
                # and writes nothing, so it is not a copy of this snippet.
                plan_check = "check-ignore" in line and "task/plan" in line
                if (plan_check or writes) and not any(
                    s <= i <= e for s, e in spans
                ):
                    offenders.append(f"{md.relative_to(ROOT)}: {line.strip()}")
    assert not offenders, "a .gitignore check or write outside the shared snippet:\n" + "\n".join(offenders)
    assert snippets == len(_IGNORE_CHECK_STEPS), f"expected {len(_IGNORE_CHECK_STEPS)} snippets, found {snippets}"


def test_ignore_check_runs_before_anything_it_guards() -> None:
    bi, lines, blocks = _ignore_check_block("project-done")
    assert [l for l in blocks[bi] if l.strip()] == lines, (
        "project-done's ignore check shares its fence; its stop exit must not sit among the commit lines"
    )
    adds = [k for k, block in enumerate(blocks) if any(l.strip() == "git add -A" for l in block)]
    assert len(adds) == 1 and bi < adds[0], "the ignore check no longer runs before `git add -A`"

    bi, lines, blocks = _ignore_check_block("project-plan")
    block = [l.strip() for l in blocks[bi]]
    start = block.index(_IGNORE_CHECK_START)
    assert "mkdir -p .task/plan" in block[:start], "project-plan checks before creating the plan dir"
    assert any(l.startswith("PLAN_FILE=") for l in block[start:]), "the plan is written before the check"


def test_ignore_check_prose_says_to_stop_and_to_run_it_whole() -> None:
    done = _done_step("**5. Commit source changes**")
    line = assert_rule(done, "leaves `.gitignore` untouched", starts_with="- **Only exit 1 appends.**")
    assert "do not go on to the commit below" in line, "the stop branch no longer stops the commit"
    line = assert_rule(
        done, "because the `case` reads the `rc` its first line sets",
        starts_with="`.task/plan/` must stay ignored; never stage it.",
    )
    assert "**run this fence as one shell invocation**" in line
    plan = skill_section(read_skill("skills/project-plan/SKILL.md"), "**3. Create plan-draft-<slug>.md**")
    line = assert_rule(
        plan, "stop and report it before writing any plan",
        starts_with="The ignore check is the same fence as `project-done` Step 5",
    )
    assert "**Run this fence as one shell invocation**" in line


# (name, starting .gitignore or None for absent, setup, expected .gitignore or
# None for unchanged, expected exit). `.task/plan` is absent unless a setup
# creates it: the trailing slash only matters while the directory is missing.
_ABSENT = None
_UNCHANGED = None


def _exclude_task(repo: Path, env: dict) -> None:
    (repo / ".git" / "info" / "exclude").write_text(".task/\n")


def _track_under_plan(repo: Path, env: dict) -> None:
    (repo / ".task" / "plan").mkdir(parents=True)
    (repo / ".task" / "plan" / "x").write_text("x\n")
    subprocess.run(["git", "add", "-f", ".task/plan/x"], cwd=repo, env=env, check=True)


_IGNORE_SCENARIOS = [
    ("absent", _ABSENT, None, b".task/plan/\n", 0),
    ("empty", b"", None, b".task/plan/\n", 0),
    ("ancestor", b".task/\n", None, _UNCHANGED, 0),
    ("directory-only rule", b".task/plan/\n", None, _UNCHANGED, 0),
    ("re-included", b".task/*\n!.task/plan/\n", None, b".task/*\n!.task/plan/\n.task/plan/\n", 0),
    ("other entry", b".venv\n", None, b".venv\n.task/plan/\n", 0),
    ("no final newline", b"node_modules", None, b"node_modules\n.task/plan/\n", 0),
    ("info/exclude", b"", _exclude_task, _UNCHANGED, 0),
    ("tracked under ignored", b".task/\n", _track_under_plan, _UNCHANGED, 0),
    ("not a repository", b"x\n", "no-repo", _UNCHANGED, 1),
]


def _isolated_git_env(tmp: Path) -> dict:
    """No global, system or user excludes: a `.task` in them would decide rows."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp),
        "XDG_CONFIG_HOME": str(tmp),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CEILING_DIRECTORIES": str(tmp),
    }


def _ignore_check_failures(snippet: str, shell: list[str], tmp: Path) -> list[str]:
    """Run the snippet through every scenario; describe each row it gets wrong."""
    tmp = tmp.resolve()
    env = _isolated_git_env(tmp)
    failures: list[str] = []
    for n, (name, start, setup, expected, rc) in enumerate(_IGNORE_SCENARIOS):
        repo = tmp / f"case-{n}"
        repo.mkdir()
        if setup != "no-repo":
            subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
        if start is not None:
            (repo / ".gitignore").write_bytes(start)
        if callable(setup):
            setup(repo, env)
        runs = 2 if rc == 0 else 1  # a second run must change nothing
        for attempt in range(runs):
            result = subprocess.run([*shell, "-c", snippet], cwd=repo, env=env, capture_output=True)
            gi = repo / ".gitignore"
            got = gi.read_bytes() if gi.exists() else None
            want = start if expected is _UNCHANGED else expected
            if result.returncode != rc or got != want:
                failures.append(
                    f"{name} (run {attempt + 1}): exit {result.returncode} (want {rc}), "
                    f".gitignore {got!r} (want {want!r}), stderr {result.stderr!r}"
                )
                break
    return failures


def _shells() -> list[list[str]]:
    shells = [["sh"], ["sh", "-e"]]
    if shutil.which("dash"):
        shells += [["dash"], ["dash", "-e"]]
    return shells


@pytest.mark.parametrize("skill", sorted(_IGNORE_CHECK_STEPS))
def test_ignore_check_behaves_in_every_scenario(skill: str, tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    snippet = _ignore_check(skill)
    assert ["sh", "-e"] in _shells(), "the `set -e` run is what catches an rc captured with `;`"
    for k, shell in enumerate(_shells()):
        work = tmp_path / f"shell-{k}"
        work.mkdir()
        failures = _ignore_check_failures(snippet, shell, work)
        assert not failures, f"{skill} under {' '.join(shell)}:\n" + "\n".join(failures)


def _mutants(snippet: str) -> dict[str, str]:
    """Each way of getting the check wrong that a reviewer or a regression could introduce."""
    guard = re.findall(r"if \[ -s \.gitignore \].*?; fi", snippet)
    assert len(guard) == 1, "the newline guard is not one `if … fi`; update the mutant"
    mutants = {
        "string comparison": 'grep -q "^\\.task/plan/" .gitignore || echo ".task/plan/" >> .gitignore\n',
        "no trailing slash": snippet.replace("--no-index .task/plan/ &&", "--no-index .task/plan &&"),
        "exit status via ||": 'git check-ignore -q --no-index .task/plan/ || echo ".task/plan/" >> .gitignore\n',
        # Only the guard goes; its line also carries the `1)` label, and
        # dropping that too would be caught by a syntax error, not a scenario.
        "no newline guard": snippet.replace(guard[0], ""),
        "no --no-index": snippet.replace("check-ignore -q --no-index", "check-ignore -q"),
        "exit status via ;": snippet.replace(" && rc=0 || rc=$?", "; rc=$?"),
        "stop arm continues": snippet.replace(">&2; exit 1 ;;", ">&2; : ;;"),
        "stop arm appends": snippet.replace(">&2; exit 1 ;;", '>&2; echo ".task/plan/" >> .gitignore; exit 1 ;;'),
    }
    for name, mutant in mutants.items():
        assert mutant != snippet, f"mutant {name!r} did not change the snippet"
    return mutants


# Each mutant and the scenario row, under the shell, that exists to catch it.
_MUTANT_CATCHERS = {
    "string comparison": ("ancestor", ("sh",)),
    "no trailing slash": ("directory-only rule", ("sh",)),
    "exit status via ||": ("not a repository", ("sh",)),
    "no newline guard": ("no final newline", ("sh",)),
    "no --no-index": ("tracked under ignored", ("sh",)),
    "exit status via ;": ("absent", ("sh", "-e")),
    "stop arm continues": ("not a repository", ("sh",)),
    "stop arm appends": ("not a repository", ("sh",)),
}


@pytest.mark.parametrize("mutant", sorted(_MUTANT_CATCHERS))
def test_ignore_check_scenarios_reject_each_mutant(mutant: str, tmp_path: Path) -> None:
    """A guard that stays green when its rule is broken proves nothing.

    Caught by the row meant for it, not by any failure: a mutant that merely
    breaks the syntax fails every row and would prove no row works.
    """
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    assert set(_MUTANT_CATCHERS) == set(_mutants(_ignore_check("project-done")))
    snippet = _mutants(_ignore_check("project-done"))[mutant]
    row, shell = _MUTANT_CATCHERS[mutant]
    failures = _ignore_check_failures(snippet, list(shell), tmp_path)
    assert any(f.startswith(f"{row} (") for f in failures), (
        f"the {row!r} row does not reject the {mutant!r} mutant under {' '.join(shell)}: {failures}"
    )
    assert not any("syntax error" in f for f in failures), f"the {mutant!r} mutant does not parse: {failures}"


def test_repo_gitignore_has_no_redundant_plan_entry(tmp_path: Path) -> None:
    """PR #44 appended `.task/plan/` under `.task/`; the entry `.task/` already covers it."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".task/" in lines, "the repo no longer ignores .task/"
    assert ".task/plan/" not in lines, "a redundant .task/plan/ entry is back"
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout, or git is not installed")
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", ".task/plan/"],
        cwd=ROOT, env={**_isolated_git_env(tmp_path), "GIT_CEILING_DIRECTORIES": ""},
    )
    assert result.returncode == 0, f"the repo's rules no longer cover .task/plan/ (exit {result.returncode})"


# --------------------------------------------------------------------------
# #42 — project-iterate branches in a worktree by default
#
# Several sessions share one repository, so a run that forgot `worktree`
# moved the main checkout's branch under its neighbours — and under the
# installed skills, which are symlinks into that checkout. The default is now
# a worktree and `in-place` is the explicit opt-out; `worktree` stays as an
# alias, because people and sessions still type it.
#
# A worktree default makes a session that stays in a linked worktree common,
# so iterate also refuses to start Phases 1–3 anywhere but the main checkout,
# refuses to branch while the main checkout sits off the default base, and on
# re-entry continues where the branch is already checked out instead of
# cutting a second checkout beside it.
#
# `project-start` took the same default in #43, and with it the base and
# ignore checks this block first wrote into Phase 3; their guards moved to the
# #43 block at the end of this file.
#
# Two layers, as in the Forgejo block above. The golden tuples pin each
# region this change wrote, fences included, line by line: a review showed
# whole-line rule pins surviving a contradicting line added beside them, a
# lost `exit 1`, and an `exit 0` slipped in for one mode. The shape tests
# say *why* a line matters and run what can be run. Editing one of these
# rules means editing its tuple here — deliberately.
#
# `### Phase N:` headings are not the bold step headings `skill_section`
# understands, so the Phase slicer is local.
# --------------------------------------------------------------------------

_G_USAGE = (
    '```',
    'project-iterate <task description> [in-place] [adr]',
    'project-iterate <id> [in-place] [adr]',
    '```',
    '- `<task description>`: task description (required for a new run)',
    '- `<id>`: an issue that already exists — re-entry, including an issue that has no plan yet (see below)',
    '- `[in-place]`: branch in the main checkout itself; Phase 3 calls `project-start <id> in-place`',
    '- `[adr]`: include ADR writing, passed to both start and done',
    'Branching defaults to a worktree: unless `in-place` is given, Phase 3 calls `project-start <id>`, whose default is a worktree.',
    'The `worktree` token is accepted as an alias of that default and changes nothing; when it is given, say in one line that a worktree is already the default.',
    'Argument rules:',
    '- The first token decides the form: an issue number or a Jira key is the `<id>` form, and a flag (`in-place`, `worktree`, `adr`) as the first token is an error — stop and show the correct order.',
    '- The `<id>` form is the id followed only by flags; if any other token follows the id, stop and ask whether this is a new run or a re-entry.',
    '- A flag counts only as a standalone token at the end of `$ARGUMENTS`, in exact lowercase, in any order among the trailing tokens; the same word in the middle of the description is part of the description.',
    '- A trailing token that is a near spelling of a flag (`--in-place`, `inplace`, `In-place`, `--worktree`) is not guessed — ask the user which was meant.',
    '- `in-place` and `worktree` together are a conflict — stop and have the user pick one.',
)

_G_REENTRY = (
    '"Start" 상태에서는 Phase 4 를 브랜치가 이미 체크아웃된 자리에서 잇는다. 그 자리는 아래 순서로 정한다.',
    '1. 로컬 브랜치만 접두 표지 없이 나열한다:',
    '```bash',
    'git branch --list "*issue-<id>-*" "*/<id>-*" --format=\'%(refname:lstrip=2)\'',
    '```',
    '- 로컬 0개(원격에만 있음): 멈추고 두 선택지를 명령과 함께 보인다 — 제자리 `git checkout <branch>`, 또는 워크트리 `git worktree add "<main checkout>/.claude/worktrees/<project>-issue-<id>" <branch>`. 어느 쪽도 자동으로 실행하지 않는다.',
    '- 로컬 2개 이상: 멈추고 보고한다.',
    '- 로컬 1개: 그 브랜치로 2를 잇는다.',
    '2. `git worktree list --porcelain` 레코드에서 그 브랜치가 체크아웃된 자리를 찾는다. `detached` 레코드는 그 브랜치를 rebase 하는 중일 때만 그 브랜치의 자리로 본다:',
    '```bash',
    "git worktree list --porcelain | python3 -c '",
    'import os, subprocess, sys',
    'branch, standard = "refs/heads/" + sys.argv[1], sys.argv[2]',
    'records = [dict((l.split(" ", 1) + [""])[:2] for l in r.splitlines())',
    'for r in sys.stdin.read().strip().split("\\n\\n")]',
    'def rebasing(path):',
    'for name in ("rebase-merge/head-name", "rebase-apply/head-name"):',
    'rel = subprocess.run(["git", "-C", path, "rev-parse", "--git-path", name],',
    'capture_output=True, text=True).stdout.strip()',
    'head = os.path.join(path, rel) if rel else ""',
    'if head and os.path.isfile(head) and open(head).read().strip() == branch:',
    'return True',
    'return False',
    'hit = [(i, r) for i, r in enumerate(records) if r.get("branch") == branch]',
    'stuck = [r for r in records if "detached" in r',
    'and (r["worktree"].endswith(standard) or rebasing(r["worktree"]))]',
    'if hit:',
    'i, r = hit[0]',
    'state = "prunable" if "prunable" in r else "missing" if not os.path.isdir(r["worktree"]) \\',
    'else "main" if i == 0 else "linked"',
    'print(state, r["worktree"])',
    'elif stuck:',
    'print("detached", stuck[0]["worktree"])',
    'else:',
    'print("none")',
    "' '<branch>' '/.claude/worktrees/<project>-issue-<id>'",
    '```',
    '- `main`: main checkout 에서 Phase 4 를 돈다.',
    '- `linked`: 이 워크트리를 다른 세션이 쓰고 있을 수 있다고 먼저 알리고, 그 경로를 CWD 로 Phase 4 를 돈다.',
    '- `prunable`: 멈춘다. 디렉터리를 옮겼으면 `git worktree repair <새 경로>` 를, 지웠으면 `git worktree prune` 을 안내한다 — 이 상태에서는 checkout 도 워크트리 추가도 실패한다.',
    '- `missing`: 잠긴(locked) 워크트리의 디렉터리가 없다. 멈추고 `git worktree repair <새 경로>` 를 안내한다.',
    '- `detached`: 그 브랜치를 rebase 하는 중인 checkout(main checkout 포함)이거나, 표준 경로의 워크트리가 rebase·bisect 같은 작업 중이다. 멈추고 보고한다.',
    '- `none`: 어디에도 체크아웃돼 있지 않다. 1의 로컬 0개와 같이 두 선택지를 보이고 멈춘다.',
    '3. 이 경로에서는 브랜치도 워크트리도 새로 만들지 않고, 분기 방식 플래그도 쓰지 않는다. 적용 중인 분기 방식(플래그가 없으면 기본값인 워크트리)이 기존 자리와 다르면 기존 자리를 따른다고 알린다.',
    '"Issue" 상태의 Phase 3 은 새 실행과 같은 인자 규칙과 Phase 3 사전 확인을 따른다.',
)

_G_INSTRUCTIONS_HEAD = (
    'This skill calls four global skills in sequence.',
    "For each phase's detailed procedure, follow that skill document (`~/.claude/skills/<name>/SKILL.md`).",
    '**Main checkout first.**',
    'Once the re-entry state is known, check the CWD before any phase runs.',
    'Phases 1, 2 and 3 run from the main checkout — a new run, and re-entry in the "Issue" or "Issue only" state; from any other CWD, stop and print the main checkout path.',
    'Re-entry in the "Start" state is exempt: Phase 4 runs where the branch is already checked out (`## Re-entry After Interruption`).',
    'The main checkout is the work tree git reports for the first entry of `git worktree list --porcelain` — the canonical main-checkout block kept in the shared worktree reference. Run this fence as one shell call — shell variables do not survive to the next call:',
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {',
    'echo "not the main checkout — rerun from: $MAIN_CHECKOUT"; exit 1; }',
    '```',
    '---',
)

_G_PHASE3 = (
    '1. Before calling `project-start`:',
    '- If Phase 1 was skipped ("Issue" re-entry), show the parsed flags before any check or branch — branch mode `worktree` (default) or `in-place`, and whether `adr` is set.',
    '- The Phase 3 checks are that flag display and `project-start` Step 1-C, which runs the base check and the ignore check from the main checkout; iterate does not run them a second time.',
    '2. Run the `start` skill procedure with the issue ID from Phase 2:',
    '- by default, or with `worktree`: call `project-start <id> [adr]`, and run Phase 4 with the new worktree as the CWD',
    '- with `in-place`: call `project-start <id> in-place [adr]`, which branches in the main checkout',
    '- pass the `adr` argument when applicable, to write an ADR before implementation',
    '- read the Intent Summary and Drift Guards',
    '- print the Task Cards checklist and start implementation',
    '- review the implementation according to `Review Profile` policy',
    '3. **User confirmation**: show the implementation result summary and get approval.',
    '- If changes are requested, apply them and confirm again.',
    '- On approval, continue to Phase 4.',
    '---',
)

_G_PRESERVED = (
    'To resume after interruption, call the relevant skill directly:',
    '- From Phase 2: `project-issue <plan-path>`, or `project-issue <plan-path> --issue <id>` when the issue already exists. Always name the path: discovery without it can pick up a draft that belongs to other work.',
    '- From Phase 3: `project-start <id>`, or `project-start <id> in-place` for a run that was `in-place` (from the main checkout — `project-start` Step 1-C refuses `in-place` anywhere else). `project-iterate <id>` resumes the same point through the "Issue" state.',
    '- From Phase 4: `project-done <id>`',
)

_G_ADR_STEP1 = (
    '**1. Decide ADR Content**',
    'Find the plan in the main worktree: `.task/plan/` is gitignored and exists only there, so a path relative to the CWD finds no plan when this step runs in a linked worktree, as it does under `project-start <issue-id> worktree adr`.',
    '```bash',
    '<harness_cli> plan-file <issue-id>',
    '```',
    'Without a harness_cli, use this fence — **run it as one shell invocation**; the four resolving lines are the canonical block in `~/.claude/skills/_shared/references/worktree.md`:',
    '```bash',
    "case '<issue-id>' in",
    "''|*[!A-Za-z0-9_-]*) echo \"reject (id): not an issue number or ticket key\" >&2; exit 1 ;;",
    'esac',
    "printf '%s\\n' '<issue-id>' | LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*' || {",
    'echo "reject (id): not an issue number or ticket key" >&2; exit 1; }',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<issue-id>.md"',
    '[ -f "$PLAN" ] || { echo "no plan at $PLAN"; exit 1; }',
    "printf 'PLAN=%s\\n' \"$PLAN\"",
    '```',
    'Either form prints the plan\'s absolute path in the main checkout — `plan-file` prints it bare, the fallback as `PLAN=<path>`. That path is `<plan-path>`; substitute it as a literal, since a shell variable does not survive into the next call.',
    'Read `<plan-path>` and the current branch diff to identify the architecture decision that should be documented.',
    'If the plan is missing, stop and report it.',
    'If the decision title is ambiguous, confirm it with the user.',
)


import shlex
import subprocess

_ITERATE_USAGE = (
    "project-iterate <task description> [in-place] [adr]",
    "project-iterate <id> [in-place] [adr]",
)

_MAIN_RESOLVE = (
    "FIRST_WORKTREE=\"$(git worktree list --porcelain | sed -n '1s/^worktree //p')\"",
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
)

_ITERATE_PHASE1_LINES = (
    "1. Read `$ARGUMENTS` by the argument rules in `## Usage`: the task description is what "
    "remains once the trailing flags are taken off.",
    "- Show the parsed task description and the parsed flags on separate lines — branch mode "
    "`worktree` (default) or `in-place`, and whether `adr` is set — so a misread argument is "
    "corrected at approval.",
)


def _region(text: str, start: str, end: str, *, inclusive: bool = False) -> list[str]:
    """Non-blank stripped lines from the one starting with `start` to the one starting with `end`."""
    lines = text.splitlines()
    first = [i for i, l in enumerate(lines) if l.startswith(start)]
    assert len(first) == 1, f"expected one line starting {start!r}, found {len(first)}"
    last = [i for i, l in enumerate(lines) if l.startswith(end) and i > first[0]]
    assert last, f"no {end!r} after {start!r}"
    return [l.strip() for l in lines[first[0] + (0 if inclusive else 1):last[0]] if l.strip()]


def _iterate_phase(text: str, number: int) -> str:
    """`### Phase N:` up to the next Phase heading or `## ` section, fences included."""
    out: list[str] = []
    for line, in_fence in _outside_fences(text):
        heading = not in_fence and (line.startswith("### Phase ") or line.startswith("## "))
        if heading and out:
            break
        if heading and line.startswith(f"### Phase {number}:"):
            out.append(line)
            continue
        if out:
            out.append(line)
    return "\n".join(out)


def _golden_fences(lines: list[str]) -> list[list[str]]:
    """Each fenced block's body lines, in order."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def _reentry_parser() -> str:
    """The parser body as written, indentation intact — `_region` strips it."""
    raw = _iterate_skill()
    start = raw.index("python3 -c '\n") + len("python3 -c '\n")
    return raw[start:raw.index("\n' '<branch>'", start)]


def test_iterate_regions_are_pinned_whole() -> None:
    text = _iterate_skill()
    for name, got, expected in (
        ("## Usage", _region(text, "## Usage", "## Re-entry After Interruption"), _G_USAGE),
        ("re-entry location rules", _region(
            text, "- 브랜치/워크트리는 있는데 `plan-<id>.md` 가 없으면", "## Instructions"), _G_REENTRY),
        ("## Instructions head", _region(text, "## Instructions", "### Phase 1:"), _G_INSTRUCTIONS_HEAD),
        ("Phase 3", _region(text, "### Phase 3:", "### Phase 4:"), _G_PHASE3),
    ):
        assert tuple(got) == expected, f"project-iterate {name} changed"
    lines = text.splitlines()
    preserved = lines.index("To resume after interruption, call the relevant skill directly:")
    assert tuple(l.strip() for l in lines[preserved:] if l.strip()) == _G_PRESERVED, (
        "the Preserved State resume list changed"
    )


def test_iterate_mode_words_live_only_in_pinned_lines() -> None:
    """A contradicting line elsewhere — "with no flag, branch in place" — is caught by vocabulary."""
    text = _iterate_skill()
    pinned = set(_G_USAGE + _G_REENTRY + _G_INSTRUCTIONS_HEAD + _G_PHASE3 + _G_PRESERVED
                 + _ITERATE_PHASE1_LINES)
    stray = [
        l.strip() for l in text.splitlines()
        if re.search(r"in-place|in place|`worktree`|flag|플래그", l, re.I) and l.strip() not in pinned
    ]
    assert not stray, "a branch-mode rule was stated outside the pinned lines:\n" + "\n".join(stray)


def test_iterate_usage_defaults_to_a_worktree() -> None:
    text = _iterate_skill()
    usage = _golden_fences(list(_G_USAGE))
    assert usage and tuple(usage[0]) == _ITERATE_USAGE
    assert "[worktree]" not in text, "project-iterate still advertises [worktree]"
    assert "(excluding `worktree` and `adr` keywords)" not in text, (
        "the old keyword-anywhere extraction line is back"
    )
    alias = rule_line(text, "The `worktree` token")
    assert "accepted" in alias and "say in one line" in alias, "the alias is no longer accepted and announced"
    for marker in RETRACTION_MARKERS:
        for line in _G_USAGE:
            assert marker not in line.lower(), f"a Usage rule reads as retracted ({marker!r}): {line!r}"


def test_iterate_phases_hold_their_own_lines() -> None:
    text = _iterate_skill()
    phase1 = _iterate_phase(text, 1)
    assert phase1 and _iterate_phase(text, 4), "a Phase heading is no longer findable"
    for line in _ITERATE_PHASE1_LINES:
        assert_whole_line(phase1, line)
    assert "pass the `worktree` argument when applicable" not in text

    # Every check, and every line about it, comes before the call it protects.
    handoff = _G_PHASE3.index("2. Run the `start` skill procedure with the issue ID from Phase 2:")
    for i, line in enumerate(_G_PHASE3):
        if "check-ignore" in line or "MAIN_CHECKOUT" in line or "base check" in line:
            assert i < handoff, f"a Phase 3 check sits after project-start is called: {line}"


def test_iterate_main_checkout_fences_resolve_and_stop() -> None:
    text = _iterate_skill()
    fences = _golden_fences(list(_G_INSTRUCTIONS_HEAD)) + _golden_fences(list(_G_PHASE3))
    assert len(fences) == 1, "expected the precondition fence only; the Phase 3 checks live in project-start 1-C"
    (precondition,) = fences
    assert tuple(precondition[:3]) == _MAIN_RESOLVE, f"the main checkout is resolved another way: {precondition[:3]}"
    assert not any("exit 0" in l for l in precondition), f"a fence can pass early: {precondition}"
    assert [l for l in precondition if "--show-toplevel" in l] == [
        _MAIN_RESOLVE[1],
        '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {'
    ], "--show-toplevel may only ask about the first entry, or be the other side of the comparison"
    assert precondition[-1].endswith("exit 1; }"), "the gate no longer stops"
    for banned in ("--git-common-dir", "$PWD"):
        assert banned not in text, f"the main checkout is derived from {banned}"


def test_iterate_reentry_record_parser_names_each_location(tmp_path: Path) -> None:
    """Run the documented parser on porcelain records for every state it names."""
    code = _reentry_parser()
    main, wt = tmp_path / "r", tmp_path / "r" / ".claude" / "worktrees" / "p-issue-1"
    wt.mkdir(parents=True)
    rebasing = tmp_path / "rebasing"
    subprocess.run(["git", "init", "-q", str(rebasing)], check=True)
    (rebasing / ".git" / "rebase-merge").mkdir()
    (rebasing / ".git" / "rebase-merge" / "head-name").write_text("refs/heads/feat/issue-1-x\n")

    on_branch = f"worktree {main}\nHEAD aaa\nbranch refs/heads/feat/issue-1-x\n"
    other = f"worktree {main}\nHEAD aaa\nbranch refs/heads/main\n"
    linked = f"worktree {wt}\nHEAD bbb\nbranch refs/heads/feat/issue-1-x\n"
    gone = f"worktree {tmp_path / 'moved'}\nHEAD bbb\nbranch refs/heads/feat/issue-1-x\nlocked\n"
    cases = {
        on_branch: f"main {main}",
        other + "\n" + linked: f"linked {wt}",
        other + "\n" + linked + "prunable gitdir file points to non-existent location\n": f"prunable {wt}",
        other + "\n" + gone: f"missing {tmp_path / 'moved'}",
        other + "\n" + f"worktree {wt}\nHEAD bbb\ndetached\n": f"detached {wt}",
        other + "\n" + f"worktree {rebasing}\nHEAD ccc\ndetached\n": f"detached {rebasing}",
        other + "\n" + f"worktree {tmp_path / 'elsewhere'}\nHEAD ccc\ndetached\n": "none",
        other: "none",
    }
    for porcelain, expected in cases.items():
        out = subprocess.run(
            [sys.executable, "-c", code, "feat/issue-1-x", "/.claude/worktrees/p-issue-1"],
            input=porcelain, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert out == expected, f"porcelain {porcelain!r} -> {out!r}, expected {expected!r}"


def test_iterate_reentry_lists_local_branches_only() -> None:
    fences = _golden_fences(list(_G_REENTRY))
    assert len(fences) == 2, "expected the branch-list fence and the parser fence"
    assert fences[0] == ["git branch --list \"*issue-<id>-*\" \"*/<id>-*\" --format='%(refname:lstrip=2)'"]
    assert fences[1][0] == "git worktree list --porcelain | python3 -c '"
    assert "grep" not in "\n".join(sum(fences, [])), "the location fence matches id prefixes again"


def test_project_adr_reads_the_plan_from_the_main_worktree() -> None:
    text = read_skill("skills/project-adr/SKILL.md")
    step1 = _region(text, "**1. Decide ADR Content**", "**2. Decide File Name**", inclusive=True)
    assert tuple(step1) == _G_ADR_STEP1, "project-adr Step 1 changed"
    assert not any(re.search(r'(?<!\$MAIN_CHECKOUT/)\.task/plan/plan-<issue-id>\.md', l) for l in step1), (
        "a CWD-relative plan path is back"
    )
    assert "LC_ALL=C grep -Eqx '[1-9][0-9]*|[A-Z][A-Z0-9_]*-[1-9][0-9]*'" in "\n".join(step1), (
        "the plan lookup takes an unvalidated id"
    )


def test_project_adr_fallback_finds_the_plan_from_a_linked_worktree(tmp_path: Path) -> None:
    """Run the documented fallback where it matters: in a linked worktree, plan only in main."""
    step1 = skill_section(read_skill("skills/project-adr/SKILL.md"), "**1. Decide ADR Content**")
    fences = [f for f in _fences_of(step1) if "FIRST_WORKTREE=" in f]
    assert len(fences) == 1, "project-adr Step 1 should hold exactly one shell fallback fence"
    code = fences[0]

    repo = tmp_path / "repo"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(git + ["-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    linked = tmp_path / "linked"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(linked), "-b", "feat/issue-7-x"], check=True)

    def run(issue: str) -> int:
        return subprocess.run(["sh", "-c", code.replace("<issue-id>", issue)], cwd=linked,
                              capture_output=True, text=True).returncode

    assert run("7") != 0, "the fallback found a plan that does not exist"
    (repo / ".task" / "plan").mkdir(parents=True)
    (repo / ".task" / "plan" / "plan-7.md").write_text("# Plan\n")
    assert run("7") == 0, "the fallback does not see the main worktree's plan from a linked worktree"
    assert run("../7") != 0, "the fallback accepts an id that is not an issue number"


def test_codex_reference_shows_the_iterate_default() -> None:
    lines = [l.strip() for l in read_skill(CODEX_REFERENCE).splitlines()]
    for usage in _ITERATE_USAGE:
        assert lines.count("$" + usage) == 1, f"codex does not show {usage!r}"
    assert not [l for l in lines if l.startswith("$project-iterate") and "[worktree]" in l]
    assert "$project-start <issue-id> [in-place] [adr]" in lines


def test_readme_iterate_row_names_the_worktree_default() -> None:
    assert_whole_line(read_skill("README.md"), (
        "| `project-iterate` | plan → issue → start → done 을 한 번에 실행(단계 사이 사용자 확인). "
        "기본은 워크트리에서 분기하고, `in-place` 를 붙이면 main checkout 에서 제자리 분기한다. "
        "`project-iterate <id>` 는 기존 이슈에서 출발하며, 플랜이 없으면 이슈 본문으로 쓰고 연결 모드로 붙인다 |"
    ))


# --------------------------------------------------------------------------
# project-done main-checkout paths (#31)
#
# `.task/plan/` is gitignored, so the plan and the report exist only in the
# main checkout; after `project-start … worktree` every step runs with a linked
# worktree as CWD. Step 1 used to fall back to `ls .task/plan/plan-<id>.md`, so
# a repo without a harness passed the start gate and then stopped at done, and
# Step 4 wrote the report into the worktree. Step 1 now resolves the main
# checkout once, prints absolute paths, and every later step takes them as
# literals. The fallback fence is run for real below, against a linked
# worktree, because a path that is absolute but wrong reads as correct.
# --------------------------------------------------------------------------

_DONE_STEP1 = "**1. Confirm plan file**"


def _fences_of(section: str) -> list[str]:
    fences, current, inside = [], [], False
    for line in section.splitlines():
        if line.strip().startswith("```"):
            if inside:
                fences.append("\n".join(current))
                current = []
            inside = not inside
            continue
        if inside:
            current.append(line)
    return fences


def _done_step1_fallback() -> str:
    """Step 1's fallback fence alone: the harness line's fence is not shell."""
    fallback = [f for f in _fences_of(_done_step(_DONE_STEP1)) if "REPORT_ROOT=" in f]
    assert len(fallback) == 1, f"Step 1 should hold exactly one fallback fence, found {len(fallback)}"
    assert "<harness_cli>" not in fallback[0], "the harness line was folded into the fallback fence"
    return fallback[0]


def _resolve_block(commands: list[str]) -> list[str]:
    roots = [i for i, c in enumerate(commands) if c.startswith("FIRST_WORKTREE=")]
    assert len(roots) == 1, f"expected one main-checkout resolution, got {len(roots)}"
    return commands[roots[0]:roots[0] + 4]


def test_done_has_no_cwd_relative_plan_or_report_path() -> None:
    text = _done_skill()
    # A bare `.task/plan/` names the directory (Step 5 asks git about it on
    # purpose); a file under it is only ever reached through the main checkout.
    offenders = [
        line.strip() for line in text.splitlines()
        if re.search(r"(?<!\$REPORT_ROOT/)\.task/plan/(?=[^\s`\"'])", line)
    ]
    assert not offenders, f"a plan or report path is built relative to the CWD: {offenders}"
    assert "ls .task/plan" not in text, "the CWD-relative plan check is back"
    # The regex cannot see `cd .task/plan` or "the plan under .task/plan", so
    # every line naming the directory is also pinned: a new one is a decision.
    mentions = [line.strip()[:48] for line in text.splitlines() if ".task/plan" in line]
    assert mentions == list(_DONE_TASK_PLAN_LINES), (
        "the lines naming .task/plan changed; if the new one is main-rooted or names the "
        f"directory on purpose, add it here:\n{mentions}"
    )


# Line starts, in document order: Step 1's prose and fence, Step 5's ignore
# check (which asks about the work tree's own rules on purpose), and Step 7's
# Forgejo fence and bullet.
_DONE_TASK_PLAN_LINES = (
    '`.task/plan/` is gitignored, so the plan and the',
    'PLAN="$REPORT_ROOT/.task/plan/plan-<issue-id>.md',
    'printf \'PLAN=%s\\nREPORT=%s\\n\' "$PLAN" "$REPORT_R',
    '- **Ask git for the main checkout; never build t',
    '`.task/plan/` must stay ignored; never stage it.',
    'git check-ignore -q --no-index .task/plan/ && rc',
    'echo ".task/plan/" >> .gitignore ;;',
    '- **Keep the trailing slash.** It tells git the ',
    '- **The append guards the last line.** A `.gitig',
    'git restore --staged ".task/plan/" 2>/dev/null |',
    '**Check that the commit actually moved.** When t',
    'REPORT="$REPORT_ROOT/.task/plan/impl-report-<id>',
    '- **보고서는 절대 경로로 넘긴다.** `.task/plan/` 은 gitignore',
)


def test_done_step1_fallback_resolves_the_main_checkout_in_order() -> None:
    commands = _logical_lines(_done_step1_fallback())
    starts = ("case '<issue-id>' in", "printf '%s\\n' '<issue-id>' | LC_ALL=C grep -Eqx",
              "REPORT_ROOT=", '[ -f "$PLAN" ]', "printf 'PLAN=%s\\nREPORT=%s\\n'")
    positions = []
    for start in starts:
        hits = [i for i, c in enumerate(commands) if c.startswith(start)]
        assert len(hits) == 1, f"expected one line starting {start!r}, got {len(hits)}"
        positions.append(hits[0])
    assert positions == sorted(positions), f"the fallback runs out of order: {list(zip(starts, positions))}"
    for wrong in ("--show-toplevel", "--git-common-dir", "--path-format", "$PWD", "$(pwd)", "harness_core"):
        offenders = [c for c in commands if wrong in c and c != 'REPORT_ROOT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"']
        assert not offenders, f"the main checkout is derived from {wrong}, wrong in a worktree: {offenders}"


def test_done_step1_and_forgejo_resolve_the_main_checkout_identically() -> None:
    step1 = _resolve_block(_logical_lines(_done_step1_fallback()))
    forgejo = _resolve_block(_logical_lines(_fenced(_done_forgejo())))
    assert step1 == forgejo, f"Step 1 and Step 7 resolve the main checkout differently:\n{step1}\n{forgejo}"
    assert step1[:2] == ['FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 'REPORT_ROOT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"']
    assert step1[3].endswith("exit 1; }"), "an unresolved main checkout no longer stops the fence"


def test_done_step1_id_regex_is_the_code_definition() -> None:
    from harness_core.config import ISSUE_ID_PATTERN

    found = re.findall(r"grep -Eqx '([^']+)'", _done_step1_fallback())
    assert found == [ISSUE_ID_PATTERN.pattern], f"Step 1's id regex drifted from config: {found}"


def test_done_step1_states_how_the_paths_travel() -> None:
    section = _done_step(_DONE_STEP1)
    assert_rule(section, "**Pass both paths on as literals.**",
                starts_with="- **Pass both paths on as literals.** Whichever form ran")
    line = rule_line(section, "**Pass both paths on as literals.**")
    for token in ("`<plan-path>`", "`<report-path>`", "Steps 1-B, 1-C, 2 and 4 and Step 7's GitHub path",
                  "a shell variable does not survive into the next call"):
        assert token in line, f"the literal-passing rule lost {token!r}"
    assert_rule(section, "**Ask git for the main checkout; never build the path from the CWD.**",
                starts_with="- **Ask git for the main checkout; never build the path from the CWD.**")
    assert_rule(section, "**The id is refused twice before it becomes a file name.**",
                starts_with="- **The id is refused twice before it becomes a file name.**")
    assert_whole_line(section, "If the file does not exist, stop and tell the user.")
    assert_whole_line(section, "<harness_cli> plan-file <issue-id>")
    assert "substitute those absolute paths" in line, "the literal-passing rule no longer says the paths are absolute"


def test_done_later_steps_read_the_step1_paths() -> None:
    for heading, token in (
        ("**1-B.", "- Fallback without harness: inspect leading frontmatter in `<plan-path>` directly"),
        ("**1-C.", "Read the `## Review Profile` section of `<plan-path>`."),
        ("**2. Verify Definition of Done**", "Check each DoD item in `<plan-path>`."),
        ("**4. Write impl-report**", "Create `<report-path>` — Step 1's absolute path in the main checkout — in Korean. "
                                     "A report written relative to the CWD lands in the linked worktree"),
    ):
        lines = [l.strip() for l in _done_step(heading).splitlines()]
        assert sum(l.startswith(token) for l in lines) == 1, f"{heading} no longer reads the Step 1 path: {token!r}"
    guard = rule_line(_done_skill(), "The completion report generated by this skill")
    assert "`<report-path>` from Step 1" in guard, "the language guard names a CWD-relative report path"


def test_done_github_pr_body_is_the_report_path() -> None:
    github = "\n".join(_stripped_lines(_done_skill(), "### GitHub (`issue_tracker: github`)", "### Jira"))
    bodies = re.findall(r"--body-file (\S+)", github)
    assert bodies == ['"<report-path>"'] * 4, f"the GitHub PR body is not Step 1's report path: {bodies}"


def test_done_commit_check_explains_why_the_report_is_not_staged() -> None:
    line = rule_line(_done_step("**5. Commit source changes**"), "**Check that the commit actually moved.**")
    assert "is in `.gitignore`" not in line, "the .gitignore string check is back as the explanation"
    assert "git ignores `.task/plan/` (the check above asked it)" in line
    assert "from a linked worktree the report is not even inside the work tree" in line


# Rows: (name, cwd, issue id, expected outcome). "ok" means the fence printed
# exactly the main checkout's plan and report paths.
_STEP1_ROWS = (
    ("worktree", "wt", "7", "ok"),
    ("worktree subdir", "wt/sub/dir", "7", "ok"),
    ("main", "main", "7", "ok"),
    ("underscore key", "wt", "AB_C-7", "ok"),
    ("missing", "wt", "8", "stop"),
    ("leading zero", "wt", "07", "stop"),
    ("multi-line id", "wt", "7\n8", "stop"),
    ("traversal", "wt", "x/../../plan/plan-7", "stop"),
    ("no repo", "norepo", "7", "unresolved"),
    # `git worktree list` (2.54) names the git dir as the main worktree here,
    # so the fence finds no plan and stops (a known limit). A git that names
    # the work tree instead may print its plan; anything else is wrong.
    ("separate git dir", "sep-wt", "7", "stop or sep"),
)


def test_done_step1_rows_are_all_present() -> None:
    names = [row[0] for row in _STEP1_ROWS]
    assert names == [
        "worktree", "worktree subdir", "main", "underscore key", "missing",
        "leading zero", "multi-line id", "traversal", "no repo", "separate git dir",
    ], f"a Step 1 behaviour row was dropped or renamed: {names}"


def _step1_repos(tmp: Path) -> dict:
    env = {
        **_isolated_git_env(tmp),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)

    git("init", "-q", "main", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=tmp / "main")
    git("worktree", "add", "-q", str(tmp / "wt"), cwd=tmp / "main")
    plans = tmp / "main" / ".task" / "plan"
    plans.mkdir(parents=True)
    for name in ("plan-7.md", "plan-07.md", "plan-7\n8.md", "plan-AB_C-7.md"):
        (plans / name).write_text("# Plan: t\n", encoding="utf-8")
    (plans / "plan-x").mkdir()
    (tmp / "wt" / "sub" / "dir").mkdir(parents=True)
    (tmp / "norepo").mkdir()
    git("init", "-q", f"--separate-git-dir={tmp / 'sep-git'}", "sep", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=tmp / "sep")
    git("worktree", "add", "-q", str(tmp / "sep-wt"), cwd=tmp / "sep")
    (tmp / "sep" / ".task" / "plan").mkdir(parents=True)
    (tmp / "sep" / ".task" / "plan" / "plan-7.md").write_text("# Plan: t\n", encoding="utf-8")
    return env


def _step1_failures(fence: str, shell: list[str], tmp: Path) -> list[str]:
    """Run the fence through every row; describe each row it gets wrong."""
    tmp = tmp.resolve()
    tmp.mkdir(parents=True, exist_ok=True)
    env = _step1_repos(tmp)
    plans = tmp / "main" / ".task" / "plan"
    failures = []
    for name, cwd, issue_id, expected in _STEP1_ROWS:
        result = subprocess.run(
            [*shell, "-c", fence.replace("<issue-id>", issue_id)],
            cwd=tmp / cwd, env=env, capture_output=True, text=True,
        )
        out = result.stdout + result.stderr
        if "syntax error" in out:
            failures.append(f"{name} (syntax error: {out.strip()})")
            continue
        if expected == "stop or sep" and result.returncode == 0:
            sep = tmp / "sep" / ".task" / "plan"
            values = [l.split("=", 1)[1] for l in result.stdout.splitlines() if "=" in l]
            if [Path(v).resolve() for v in values] != [(sep / "plan-7.md").resolve(), (sep / "impl-report-7.md").resolve()]:
                failures.append(f"{name} (printed paths outside the work tree: {result.stdout!r})")
            continue
        if expected == "ok":
            stem = "plan-%s.md" % issue_id
            lines = result.stdout.splitlines()
            keys = [l.split("=", 1)[0] for l in lines]
            if result.returncode != 0 or keys != ["PLAN", "REPORT"]:
                failures.append(f"{name} (rc {result.returncode}, stdout {result.stdout!r}, stderr {result.stderr!r})")
                continue
            values = [l.split("=", 1)[1] for l in lines]
            if not all(os.path.isabs(v) for v in values):
                failures.append(f"{name} (relative path printed: {values})")
            elif [Path(v).resolve() for v in values] != [(plans / stem).resolve(), (plans / ("impl-report-%s.md" % issue_id)).resolve()]:
                failures.append(f"{name} (not the main checkout's paths: {values})")
            if (tmp / "wt" / ".task").exists():
                failures.append(f"{name} (created .task/ inside the worktree)")
        else:
            if result.returncode == 0 or "PLAN=" in result.stdout:
                failures.append(f"{name} (did not stop: rc {result.returncode}, stdout {result.stdout!r})")
            elif expected in ("unresolved", "stop or sep") and "could not resolve the main checkout" not in out:
                failures.append(f"{name} (stopped without naming the unresolved checkout: {out!r})")
    return failures


def test_done_step1_fallback_behaves_in_every_row(tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    fence = _done_step1_fallback()
    for n, shell in enumerate(_shells()):
        failures = _step1_failures(fence, shell, tmp_path / f"shell-{n}")
        assert not failures, f"Step 1's fallback under {' '.join(shell)}:\n" + "\n".join(failures)


def _step1_mutants(fence: str) -> dict:
    """Each way of getting the fallback wrong that a regression could introduce."""
    lines = fence.splitlines()
    root = next(l for l in lines if l.startswith("REPORT_ROOT="))
    guard = [l for l in lines if l.startswith('[ -n "$REPORT_ROOT" ]') or l.strip().startswith('echo "could not resolve')]
    check = next(l for l in lines if l.startswith('[ -f "$PLAN" ]'))
    printed = next(l for l in lines if l.startswith("printf 'PLAN="))
    case = "\n".join(lines[:3])
    grep = "\n".join(lines[3:5])
    assert case.startswith("case ") and case.endswith("esac"), "the case block moved; update the mutant"
    assert "grep -Eqx" in grep, "the grep check moved; update the mutant"
    mutants = {
        "show-toplevel": fence.replace(root, 'REPORT_ROOT="$(git rev-parse --show-toplevel)"'),
        "pwd": fence.replace(root, 'REPORT_ROOT="$PWD"'),
        "every worktree": fence.replace("'1s/^worktree //p'", "'s/^worktree //p'"),
        "no guard": fence.replace("\n".join(guard) + "\n", ""),
        "no plan check": fence.replace(check + "\n", ""),
        "printed before check": fence.replace(check + "\n", "").replace(printed, printed + "\n" + check),
        "no case": fence.replace(case + "\n", ""),
        "no grep": fence.replace(grep + "\n", ""),
        "no -x": fence.replace("grep -Eqx", "grep -Eq"),
        "case refuses underscore": fence.replace("*[!A-Za-z0-9_-]*", "*[!A-Za-z0-9-]*"),
        "no id check": fence.replace(case + "\n", "").replace(grep + "\n", ""),
        "relative report": fence.replace('"$REPORT_ROOT/.task/plan/impl-report-', '".task/plan/impl-report-'),
        "report beside the plan dir": fence.replace('"$REPORT_ROOT/.task/plan/impl-report-', '"$REPORT_ROOT/.task/impl-report-'),
    }
    for name, mutant in mutants.items():
        assert mutant != fence, f"mutant {name!r} did not change the fence"
    return mutants


# Each mutant and the row that exists to catch it.
_STEP1_MUTANT_CATCHERS = {
    "show-toplevel": "worktree",
    "pwd": "worktree",
    "every worktree": "worktree",
    "no guard": "no repo",
    "no plan check": "missing",
    "printed before check": "missing",
    "no case": "multi-line id",
    "no grep": "leading zero",
    "no -x": "leading zero",
    "case refuses underscore": "underscore key",
    "no id check": "traversal",
    "relative report": "worktree",
    "report beside the plan dir": "worktree",
}


@pytest.mark.parametrize("mutant", sorted(_STEP1_MUTANT_CATCHERS))
def test_done_step1_rows_reject_each_mutant(mutant: str, tmp_path: Path) -> None:
    """Caught by the row meant for it, and not by a syntax error in every row."""
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    mutants = _step1_mutants(_done_step1_fallback())
    assert set(mutants) == set(_STEP1_MUTANT_CATCHERS)
    failures = _step1_failures(mutants[mutant], ["sh"], tmp_path)
    row = _STEP1_MUTANT_CATCHERS[mutant]
    assert any(f.startswith(f"{row} (") for f in failures), (
        f"the {row!r} row does not reject the {mutant!r} mutant: {failures}"
    )
    assert not any("syntax error" in f for f in failures), f"the {mutant!r} mutant does not parse: {failures}"


# --------------------------------------------------------------------------
# #40 — skill-doc consistency: fences that carry no shell variable across
# calls, `project-start` Step 3 on Forgejo, and one approval for two screens
#
# 1. The Forgejo create section of `project-issue` spread one set of shell
#    variables over four fences. Tool calls do not share a shell, so every
#    fence after the first read an empty `$TITLE` or `$ISSUE_NUMBER`, and fj
#    fails quietly: `issue search ""` catches any open issue, and
#    `edit "<repo>#" labels` targets nothing. The create fence now prints what
#    later steps need and those steps take `<ISSUE_NUMBER>` as a literal —
#    the shape `project-done` Step 7 already uses for `<PR_NUMBER>`. The
#    invariant is pinned for every fence in the document, not just these.
# 2. `project-start` Step 3 now says what `project-done` Step 8 says about a
#    Forgejo status — derived from that golden line, so the two cannot drift.
# 3. `project-iterate` Phase 1 and `project-issue` Step 2 asked the same
#    human-layer question twice. The approval now counts once, and only under
#    the conditions Step 2 states; the vocabulary scan keeps an unconditional
#    "skip Step 2" from being added beside the pinned lines.
#
# Helpers carry an `_i40_` prefix: a same-named `def _` later in this file
# silently replaces an earlier one (#46/#47), which the last test here checks.
# --------------------------------------------------------------------------

import ast

_I40_CREATE_DIRECTIVE = (
    "생성을 먼저 잡고, 번호는 그 출력에서 읽는다. 격리 제거가 그 추출의 한 단이다. "
    "**아래 펜스는 한 셸 호출로 실행한다** — 뒤 줄이 앞 줄의 변수를 읽고, 셸 변수는 다음 호출로 "
    "넘어가지 않으므로 뒤 단계가 쓸 값은 마지막 두 줄이 출력한다:"
)
_I40_TITLE = "TITLE=\"$(sed -n 's/^# Plan: //p' \"$DRAFT_PLAN\" | head -1)\""
_I40_TITLE_GUARD = '[ -n "$TITLE" ] || { echo "no \'# Plan: \' title line in $DRAFT_PLAN"; exit 1; }'
_I40_CREATE_FENCE = (
    # #45: single-quoted draft path, and the body file the Plan Body Rules choose.
    "DRAFT_PLAN='<draft-plan-path>'",
    "# Repo targeting: -r <forgejo_repo> as below, or -R <forgejo_remote> when the project",
    "# declares a remote that actually exists locally. Both are accepted by create/search/edit.",
    _I40_TITLE,
    _I40_TITLE_GUARD,
    'BODY_FILE="$(mktemp)" || exit 1',
    "trap 'rm -f \"$BODY_FILE\"' EXIT",
    'BODY="$(python -m harness_core.plan_body forgejo "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }',
    'CREATED="$(fj -H <forgejo_host> issue create "$TITLE" --body-file "$BODY_FILE" -r <forgejo_repo> --no-template)" || CREATE_FAILED=1',
    'ISSUE_NUMBER="$(printf \'%s\\n\' "$CREATED" \\',
    '  | python3 -c \'import sys; sys.stdout.write(sys.stdin.read().replace("\\u2068", "").replace("\\u2069", ""))\' \\',
    "  | sed -n 's/^created issue #\\([0-9][0-9]*\\).*/\\1/p')\"",
    'printf \'CREATE_FAILED=%s\\nISSUE_NUMBER=%s\\n%s\\n\' "${CREATE_FAILED:-0}" "$ISSUE_NUMBER" "$BODY"',
    'printf \'%s\\n\' "$CREATED"',
)
_I40_SEARCH_DIRECTIVE = (
    "이 펜스도 **한 셸 호출로 실행한다** — 앞 펜스의 `TITLE` 은 이 호출까지 살아 있지 않으므로 같은 "
    "줄로 초안에서 제목을 다시 읽고, 제목이 비면 검색하지 않고 멈춘다. 빈 제목의 `issue search` 는 "
    "아무 열린 이슈나 잡는다:"
)
_I40_SEARCH_FENCE = (
    "DRAFT_PLAN='<draft-plan-path>'",
    _I40_TITLE,
    _I40_TITLE_GUARD,
    'fj -H <forgejo_host> --style minimal issue search -r <forgejo_repo> "$TITLE"',
)
_I40_RECOVERY = (
    "- 생성은 됐는데 `ISSUE_NUMBER` 가 비었다 — 번호만 못 읽은 것이다. 먼저 펜스가 출력한 생성 출력 "
    "원문에서 번호를 읽는다. 읽을 수 없을 때만 아래 펜스로 방금 만든 제목을 찾아 잡힌 번호의 제목을 "
    "눈으로 대조하고, 그래도 없으면 웹 UI 마지막 단으로 간다. 번호 없이 8단계로 넘어가지 않는다."
)
_I40_PROVENANCE = (
    "라벨 적용과 읽기 확인 펜스의 `<ISSUE_NUMBER>` 는 리터럴로 치환한다 — 생성 펜스가 출력한 "
    "`ISSUE_NUMBER=` 값, 그것이 비었을 때 생성 출력 원문에서 읽은 번호, 재검색으로 잡아 제목을 대조한 "
    "번호, 웹 UI 에서 사람이 돌려준 번호 중 하나다. 8단계와 같은 이유로 앞 호출의 셸 변수를 넘기지 "
    "않는다: 살아남지 못한 변수는 빈 값으로 도착하고, 그러면 `\"<forgejo_repo>#\"` 는 대상 없는 호출이 된다."
)
_I40_LABEL = 'fj -H <forgejo_host> issue edit "<forgejo_repo>#<ISSUE_NUMBER>" labels -a "<area tag>"'
_I40_VIEW = 'fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<ISSUE_NUMBER>"'

_I40_STEP2_SUBSTITUTE = (
    "From `project-iterate`, Phase 1's approval is this step's confirmation only when that same run's "
    "Phase 1 screen carried this step's screen as written above — the create or link form that matches "
    "the mode, down to its question line — and the user answered yes; ask this step again instead if the "
    "plan file was edited after that yes (review fixes included), Step 1 resolved a different path than "
    "the screen showed, the Step 1-L read returns a title or state other than the screen's, this run had "
    "no Phase 1 approval (re-entry at Phase 2), or this skill runs on its own. Steps 1 and 1-L still run "
    "either way, so a refusal after that yes costs an approval but never bypasses a check, and the Step "
    "1-L comment follows the screen: posted on that yes where the screen carried the comment line, and "
    "asked on its own where it did not."
)
_I40_STEP2_KEPT = (
    "Do not create an issue without confirmation. This checkpoint is not just filename/title "
    "confirmation; it is a human-layer approval checkpoint. The user must review `Intent Summary`, "
    "`Current State`, `Target State`, `Non-Goals`, and `Drift Guards` and confirm that the work intent "
    "is correct."
)
_I40_ITERATE_PHASE1 = (
    "- Carry on this same screen the Step 2 screen of the `issue` skill that Phase 2 will run — the "
    "create or link form that matches the run, down to its question line — so that one yes can answer "
    "both; Step 2 states when that yes counts."
)
_I40_ITERATE_PHASE2 = (
    "- Phase 1 승인이 `issue` 스킬 Step 2 의 대체 조건을 모두 채웠으면 Step 2 를 다시 묻지 않고, "
    "하나라도 채우지 못했으면 Step 2 를 그대로 묻는다."
)

_I40_READ = re.compile(r"\$\{?([A-Z_][A-Z0-9_]*)")
# Command position only: `printf 'ISSUE_NUMBER=%s'` is not an assignment, and
# counting it as one would hide a fence that lost its `ISSUE_NUMBER=` line.
_I40_ASSIGN = re.compile(r"(?:^|\|\||&&|;)\s*([A-Z_][A-Z0-9_]*)=")


def _i40_fence_after(text: str, directive: str) -> list[str]:
    """The fence that opens on the first non-blank line after `directive`."""
    lines = text.splitlines()
    at = [i for i, l in enumerate(lines) if l.strip() == directive]
    assert len(at) == 1, f"expected the directive once, found {len(at)}: {directive[:40]!r}"
    i = at[0] + 1
    while not lines[i].strip():
        i += 1
    assert lines[i].startswith("```"), f"the directive is not followed by its fence: {lines[i]!r}"
    body: list[str] = []
    for line in lines[i + 1:]:
        if line.startswith("```"):
            return body
        body.append(line.rstrip())
    raise AssertionError("the fence after the directive never closes")


def _i40_unassigned_reads(block: list[str]) -> tuple[list[tuple[str, str]], set[str]]:
    """Reads of a variable this block has not assigned yet, and every name read."""
    assigned: set[str] = set()
    missing: list[tuple[str, str]] = []
    read: set[str] = set()
    for line in _logical_lines("\n".join(block)):
        if line.startswith("#"):
            continue
        for name in _I40_READ.findall(line):
            read.add(name)
            if name not in assigned:
                missing.append((name, line))
        assigned.update(_I40_ASSIGN.findall(line))
    return missing, read


def _i40_script(fence: list[str], draft: Path) -> str:
    script = "\n".join(fence)
    for placeholder, value in (
        ("<draft-plan-path>", str(draft)), ("<forgejo_host>", "forge.test"),
        ("<forgejo_repo>", "o/r"), ("<forgejo_remote>", "lab"),
    ):
        script = script.replace(placeholder, value)
    assert not re.search(r"<[a-z_-]+>", script), f"a placeholder is left for the shell to parse:\n{script}"
    return script


def _i40_fake_env(tmp_path: Path, mode: str) -> tuple[dict[str, str], Path]:
    """A PATH with a fake `fj` and no route to the real one (/opt/homebrew/bin holds it here)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / f"fj-{mode}.log"
    fj = bin_dir / "fj"
    fj.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do printf \'%s\\n\' "$a"; done > "$FJ_LOG"\n'
        # #45: the body file is a temp file the fence removes on exit, so keep a copy.
        'prev=; for a in "$@"; do [ "$prev" = --body-file ] && cat "$a" > "$FJ_LOG.body"; prev=$a; done\n'
        'if [ "$FAKE_MODE" = fail ]; then echo "Error: boom" >&2; exit 1; fi\n'
        "printf 'created issue #\\342\\201\\25041\\342\\201\\251: \\342\\201\\250t\\342\\201\\251\\n'\n"
    )
    python3 = bin_dir / "python3"
    python3.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    python = bin_dir / "python"  # #45: the create fence runs `python -m harness_core.plan_body`
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    for path in (fj, python3, python):
        path.chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "FJ_LOG": str(log), "FAKE_MODE": mode, "HOME": str(tmp_path)}
    return env, log


def _i40_shells() -> list[str]:
    return [s for s in ("bash", "sh", "zsh") if shutil.which(s)]


# A title a pasted literal would break three ways: a backtick, an apostrophe,
# and a command substitution that leaves a file behind if it ever runs.
_I40_HOSTILE_TITLE = "`x` it's $(touch pwned) title"


def test_i40_create_fence_prints_what_later_steps_need() -> None:
    assert tuple(_i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE)) == _I40_CREATE_FENCE, (
        "the Forgejo create fence changed"
    )


@pytest.mark.parametrize("shell", _i40_shells())
def test_i40_create_fence_runs_against_a_fake_fj(shell: str, tmp_path: Path) -> None:
    fence = _i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE)
    draft = tmp_path / "plan-draft-x.md"
    draft.write_text(f"# Plan: {_I40_HOSTILE_TITLE}\n\nbody\n")

    env, log = _i40_fake_env(tmp_path, "ok")
    ran = subprocess.run([shell, "-c", _i40_script(fence, draft)], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    out = ran.stdout.splitlines()
    assert ran.returncode == 0, ran.stderr
    assert out[:2] == ["CREATE_FAILED=0", "ISSUE_NUMBER=41"], f"the fence printed {out}"
    assert out[2].startswith("KIND=full "), f"the body kind is not printed after the number: {out}"
    assert any(l.startswith("created issue #") for l in out), "the raw create output is not printed"
    args = log.read_text().splitlines()
    body = args.index("--body-file")
    assert args[:body] + args[body + 2:] == [
        "-H", "forge.test", "issue", "create", _I40_HOSTILE_TITLE, "-r", "o/r", "--no-template",
    ]
    assert Path(f"{log}.body").read_bytes() == draft.read_bytes(), "the body within the limit is not the draft"
    assert not (tmp_path / "pwned").exists(), "the title ran as a command"

    env, log = _i40_fake_env(tmp_path, "fail")
    ran = subprocess.run([shell, "-c", _i40_script(fence, draft)], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert ran.stdout.splitlines()[:2] == ["CREATE_FAILED=1", "ISSUE_NUMBER="], ran.stdout

    untitled = tmp_path / "plan-draft-y.md"
    untitled.write_text("# Not a plan title\n")
    env, log = _i40_fake_env(tmp_path, "empty")
    ran = subprocess.run([shell, "-c", _i40_script(fence, untitled)], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert ran.returncode != 0 and not log.exists(), "an empty title reached fj issue create"


def test_i40_search_fence_reads_its_own_title() -> None:
    section = _forgejo_section()
    search = _i40_fence_after(section, _I40_SEARCH_DIRECTIVE)
    assert tuple(search) == _I40_SEARCH_FENCE, "the re-search fence changed"
    create = _i40_fence_after(section, _I40_CREATE_DIRECTIVE)
    titles = [l for l in create + search if l.startswith("TITLE=")]
    assert len(titles) == 2 and titles[0] == titles[1], "the two fences read the title differently"
    assert_whole_line(section, _I40_RECOVERY)


@pytest.mark.parametrize("shell", _i40_shells())
def test_i40_search_fence_never_searches_for_an_empty_title(shell: str, tmp_path: Path) -> None:
    search = _i40_fence_after(_forgejo_section(), _I40_SEARCH_DIRECTIVE)
    untitled = tmp_path / "plan-draft-y.md"
    untitled.write_text("# Not a plan title\n")
    env, log = _i40_fake_env(tmp_path, "empty")
    ran = subprocess.run([shell, "-c", _i40_script(search, untitled)], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert ran.returncode != 0 and not log.exists(), "an empty title reached fj issue search"

    draft = tmp_path / "plan-draft-x.md"
    draft.write_text(f"# Plan: {_I40_HOSTILE_TITLE}\n")
    env, log = _i40_fake_env(tmp_path, "ok")
    ran = subprocess.run([shell, "-c", _i40_script(search, draft)], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    assert log.read_text().splitlines() == [
        "-H", "forge.test", "--style", "minimal", "issue", "search", "-r", "o/r", _I40_HOSTILE_TITLE,
    ]


def test_i40_every_issue_fence_assigns_what_it_reads() -> None:
    """No fence in `project-issue` may lean on a variable an earlier call set."""
    blocks = _fence_blocks(_issue_skill())
    assert len(blocks) > 10, "the fence scanner found almost nothing"
    offenders = [f"{name}: {line}" for block in blocks for name, line in _i40_unassigned_reads(block)[0]]
    assert not offenders, "a fence reads a shell variable it never assigned:\n" + "\n".join(offenders)

    _, read = _i40_unassigned_reads(_i40_fence_after(_forgejo_section(), _I40_SEARCH_DIRECTIVE))
    assert {"DRAFT_PLAN", "TITLE"} <= read, "the scanner no longer sees the re-search fence's reads"


def test_i40_label_and_view_take_the_number_as_a_literal() -> None:
    section = _forgejo_section()
    assert_whole_line(section, _I40_LABEL)
    assert_whole_line(section, _I40_VIEW)
    assert_whole_line(section, _I40_PROVENANCE)
    lines = [l.strip() for l in section.splitlines()]
    assert lines.index(_I40_PROVENANCE) < lines.index(_I40_LABEL) < lines.index(_I40_VIEW), (
        "the literal's provenance is stated after the calls that use it"
    )
    create = set(_I40_CREATE_FENCE)
    stray = [l for l in section.splitlines() if "$ISSUE_NUMBER" in l and l.rstrip() not in create]
    assert not stray, "`$ISSUE_NUMBER` is used outside the fence that sets it:\n" + "\n".join(stray)


def test_i40_start_step3_reports_forgejo_status_as_not_applied() -> None:
    assert _GOLDEN_DONE_STEP8_FORGEJO.count("In Review") == 1
    expected = _GOLDEN_DONE_STEP8_FORGEJO.replace("In Review", "In Progress")
    step3 = skill_section(_start_skill(), "**3. Issue status")
    assert step3, "project-start has no Step 3"
    lines = [l.strip() for l in step3.splitlines()]
    assert_whole_line(step3, expected)
    assert_whole_line(step3, _GOLDEN_DONE_STEP8_FENCE)

    first = _fence_blocks(step3)[0]
    assert first[0].startswith("<harness_cli> add-progress") and _GOLDEN_DONE_STEP8_FENCE in first, (
        "the Forgejo fallback comment is not in the status fence"
    )
    limitation = next(i for i, l in enumerate(lines) if l.startswith("> Limitation:"))
    progress = next(i for i, l in enumerate(lines) if l.startswith("`add-progress` transitions"))
    assert lines.index(expected) > max(limitation, progress), (
        "the Forgejo paragraph sits where the GitHub/Jira paragraphs read as applying to it"
    )
    assert not _fj_invocations(step3), "Step 3 invokes fj, which has no status contract"
    forgejo = [l for l in lines if "forgejo" in l.lower()]
    assert forgejo == [_GOLDEN_DONE_STEP8_FENCE, expected], f"another Forgejo rule in Step 3: {forgejo}"
    labels = [l for l in lines if re.search(r"라벨|label", l, re.IGNORECASE)]
    assert len(labels) == 3 and expected in labels, f"a label line was added to the status step: {labels}"


def test_i40_step2_states_when_the_iterate_approval_counts() -> None:
    step2 = skill_section(_issue_skill(), "**2. User Confirmation**")
    assert step2, "project-issue has no Step 2"
    assert_whole_line(step2, _I40_STEP2_SUBSTITUTE)
    assert_whole_line(step2, _I40_STEP2_KEPT)
    lines = [l.strip() for l in step2.splitlines()]
    question = next(i for i, l in enumerate(lines) if l.endswith("Link this file to #<id>? [yes/no]"))
    assert lines.index(_I40_STEP2_SUBSTITUTE) > question, (
        "the substitution is stated before the screen it refers to"
    )

    iterate = _iterate_skill()
    phase1, phase2 = _iterate_phase(iterate, 1), _iterate_phase(iterate, 2)
    assert_whole_line(phase1, _I40_ITERATE_PHASE1)
    assert_whole_line(phase2, _I40_ITERATE_PHASE2)
    p1 = [l.strip() for l in phase1.splitlines()]
    assert p1.index(_I40_ITERATE_PHASE1) < p1.index("- On approval, continue to Phase 2."), (
        "the screen requirement comes after the approval it shapes"
    )


def test_i40_approval_substitution_lives_only_in_pinned_lines() -> None:
    """A bare "from iterate, skip Step 2" beside the pinned lines is caught by vocabulary.

    The net is wide on purpose — any line naming iterate or a Phase together
    with Step 2, a confirmation, or a skip — because an unconditional bypass
    can be phrased without any one verb ("no need to confirm again", "한 번만
    묻는다"). Lines already pinned elsewhere are listed by their exact text.
    """
    pinned = {_I40_STEP2_SUBSTITUTE, _I40_ITERATE_PHASE1, _I40_ITERATE_PHASE2}
    pinned |= set(_G_USAGE + _G_REENTRY + _G_INSTRUCTIONS_HEAD + _G_PHASE3 + _G_PRESERVED)
    pinned |= {
        "- On approval, continue to Phase 2.",
        "- Phase 1 이 방금 만든 플랜 경로를 `project-issue` 에 위치 인자로 그대로 넘긴다. 경로는 이미 알려져 "
        "있으므로 자동 탐색을 다시 돌리지 않는다 — 초안이 여럿이면 그 탐색은 자기가 만든 파일조차 고르지 "
        "못하고 멈춘다.",
    }
    context = re.compile(r"iterate|phase [12]", re.I)
    words = re.compile(
        r"step 2|skip|생략|다시|묻지|묻는다|confirm|확인|approv|승인|replace|대신|stands? in|in place of|"
        r"no need|once|한 번", re.I,
    )
    stray = [
        f"{path}: {l.strip()}"
        for path, text in (("project-issue", _issue_skill()), ("project-iterate", _iterate_skill()))
        for l in text.splitlines()
        if context.search(l) and words.search(l) and l.strip() not in pinned
    ]
    assert not stray, "an approval-substitution rule was stated outside the pinned lines:\n" + "\n".join(stray)


def test_i40_test_module_defines_each_name_once() -> None:
    """A second `def _x` or `_X =` at module level silently replaces the first."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names += [t.id for t in targets if isinstance(t, ast.Name)]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"defined more than once at module level: {duplicates}"


# --------------------------------------------------------------------------
# main checkout canonical resolution (#50)
#
# Two rules used to answer "where is the main checkout": the harness took the
# parent of `--git-common-dir`, the skill fences took the first
# `git worktree list` entry. Each is wrong in a different layout (a submodule,
# a --separate-git-dir clone, a bare repo), and wrong there means a directory
# that exists. The canonical rule — first entry, then git's own
# `--show-toplevel` for that entry, stop if there is none — lives once in
# skills/_shared/references/worktree.md and once in main_worktree_root(). The
# matrix below checks each form against an absolute expected answer per
# layout, not against each other: two forms broken the same way agree.
# --------------------------------------------------------------------------

_I50_REFERENCE = "skills/_shared/references/worktree.md"
_I50_STOP = "STOP"
_I50_RESOLVE_NAMES = ("MAIN_CHECKOUT", "REPORT_ROOT")

# (row, cwd, expected from the shell block, expected from main_worktree_root)
# Expected values are paths under the matrix root, or STOP. "sep" answers
# STOP today; a git that listed the work tree first would answer the work tree.
_I50_ROWS = (
    ("main", "main", "main", "main"),
    ("wt", "wt", "main", "main"),
    ("wt-sub", "wt/sub/dir", "main", "main"),
    ("super", "super", "super", "super"),
    ("sub", "super/sub", "super/sub", "super/sub"),
    ("subwt", "sub-wt", "super/sub", "super/sub"),
    ("sep", "sep", _I50_STOP, _I50_STOP),
    ("sepwt", "sep-wt", _I50_STOP, _I50_STOP),
    ("bare", "bare.git", _I50_STOP, _I50_STOP),
    ("barewt", "bare-wt", _I50_STOP, _I50_STOP),
    ("shim-wt", "wt", _I50_STOP, _I50_STOP),
    ("untrusted-wt", "wt", _I50_STOP, _I50_STOP),
    ("non-repo", "norepo", _I50_STOP, "norepo"),
)
# A git without the test hook behind "untrusted-wt" reads the repo normally and
# answers main; the row exists to catch the linked worktree coming back.
_I50_SEP_ANSWER = {"sep": "sep", "sepwt": "sep", "untrusted-wt": "main"}

# worktree.md's support table, row label -> matrix rows it describes.
_I50_TABLE_ROWS = {
    "일반 clone": ("main",),
    "링크드 워크트리": ("wt", "wt-sub"),
    "submodule": ("sub",),
    "submodule 의 링크드 워크트리": ("subwt",),
    "separate-git-dir": ("sep", "sepwt"),
    "bare": ("bare",),
    "bare 의 링크드 워크트리": ("barewt",),
}
_I50_TABLE_ANSWERS = {"main checkout": "main", "submodule checkout": "super/sub", "멈춤": _I50_STOP}

# Canonical copies per file; zero copies would make "every copy is canonical" vacuous.
_I50_COPIES = {
    "skills/_shared/references/worktree.md": 1,
    "skills/project-done/SKILL.md": 3,
    "skills/project-iterate/SKILL.md": 2,
    "skills/project-start/SKILL.md": 5,
    "skills/project-adr/SKILL.md": 1,
    "skills/project-clean/SKILL.md": 1,
}


def _i50_canonical() -> list[str]:
    fences = [f for f in _fences_of(read_skill(_I50_REFERENCE)) if "FIRST_WORKTREE=" in f]
    assert len(fences) == 1, f"{_I50_REFERENCE} should hold exactly one canonical block"
    lines = fences[0].splitlines()
    assert len(lines) == 4 and lines[0].startswith("FIRST_WORKTREE="), f"the canonical block changed shape: {lines}"
    return lines


def _i50_env(tmp: Path) -> dict:
    return {
        **_isolated_git_env(tmp),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "PYTHONPATH": str(ROOT / "src"),
    }


def _i50_repos(tmp: Path) -> dict:
    """Every layout in the matrix, under one root."""
    env = _i50_env(tmp)

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "protocol.file.allow=always", *args],
                       cwd=cwd, env=env, check=True, capture_output=True)

    git("init", "-q", "main", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=tmp / "main")
    git("worktree", "add", "-q", str(tmp / "wt"), cwd=tmp / "main")
    (tmp / "wt" / "sub" / "dir").mkdir(parents=True)
    git("init", "-q", "subsrc", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "s", cwd=tmp / "subsrc")
    git("init", "-q", "super", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=tmp / "super")
    git("submodule", "add", "-q", str(tmp / "subsrc"), "sub", cwd=tmp / "super")
    git("worktree", "add", "-q", str(tmp / "sub-wt"), cwd=tmp / "super" / "sub")
    git("init", "-q", f"--separate-git-dir={tmp / 'sep.git'}", "sep", cwd=tmp)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=tmp / "sep")
    git("worktree", "add", "-q", str(tmp / "sep-wt"), cwd=tmp / "sep")
    git("clone", "-q", "--bare", str(tmp / "main"), "bare.git", cwd=tmp)
    git("worktree", "add", "-q", str(tmp / "bare-wt"), "main", cwd=tmp / "bare.git")
    (tmp / "norepo").mkdir()
    shim = tmp / "shim"
    shim.mkdir()
    (shim / "git").write_text(
        '#!/bin/sh\n[ "$1" = worktree ] && [ "$2" = list ] && exit 1\nexec "%s" "$@"\n' % shutil.which("git"))
    (shim / "git").chmod(0o755)
    return env


def _i50_row_env(env: dict, tmp: Path, row: str) -> dict:
    if row == "shim-wt":
        return {**env, "PATH": f"{tmp / 'shim'}{os.pathsep}{env['PATH']}"}
    if row == "untrusted-wt":
        return {**env, "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}
    return env


def _i50_shell_answer(block: str, shell: list[str], cwd: Path, env: dict) -> str:
    """The block's answer as a matrix value, or a description of what went wrong."""
    result = subprocess.run([*shell, "-c", block + '\nprintf "%s\\n" "$MAIN_CHECKOUT"'],
                            cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout.strip() == "could not resolve the main checkout":
            return _I50_STOP
        return f"<failed without the stop message: rc {result.returncode}, {result.stdout!r}, {result.stderr!r}>"
    return result.stdout.strip()


def _i50_python_answer(cwd: Path, env: dict) -> str:
    code = ("from harness_core.git import main_worktree_root, MainWorktreeUnresolvedError\n"
            "try:\n    print(main_worktree_root())\n"
            "except MainWorktreeUnresolvedError:\n    print('" + _I50_STOP + "')\n")
    result = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        return f"<raised something else: {result.stderr.strip()[-200:]!r}>"
    return result.stdout.strip()


def _i50_matches(answer: str, expected: str, row: str, tmp: Path) -> bool:
    accepted = {expected}
    if row in _I50_SEP_ANSWER:
        accepted.add(_I50_SEP_ANSWER[row])
    for want in accepted:
        if want == _I50_STOP and answer == _I50_STOP:
            return True
        if want != _I50_STOP and os.path.isabs(answer) and Path(answer).resolve() == (tmp / want).resolve():
            return True
    return False


def _i50_block_failures(block: str, shell: list[str], tmp: Path, env: dict) -> list[str]:
    failures = []
    for row, cwd, want, _ in _I50_ROWS:
        answer = _i50_shell_answer(block, shell, tmp / cwd, _i50_row_env(env, tmp, row))
        if not _i50_matches(answer, want, row, tmp):
            failures.append(f"{row} (shell {' '.join(shell)}: {answer!r}, expected {want!r})")
    return failures


@pytest.fixture(scope="module")
def _i50_matrix(tmp_path_factory):
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    tmp = tmp_path_factory.mktemp("i50 matrix").resolve()
    return tmp, _i50_repos(tmp)


def test_canonical_rows_are_all_present() -> None:
    assert [r[0] for r in _I50_ROWS] == [
        "main", "wt", "wt-sub", "super", "sub", "subwt", "sep", "sepwt", "bare", "barewt", "shim-wt",
        "untrusted-wt", "non-repo",
    ], "a layout row was dropped or renamed"


def test_canonical_block_answers_every_layout(_i50_matrix) -> None:
    tmp, env = _i50_matrix
    block = "\n".join(_i50_canonical())
    failures = []
    for shell in _shells():
        failures += _i50_block_failures(block, shell, tmp, env)
    assert not failures, "the canonical shell block:\n" + "\n".join(failures)


def test_main_worktree_root_answers_every_layout(_i50_matrix) -> None:
    tmp, env = _i50_matrix
    failures = []
    for row, cwd, _, want in _I50_ROWS:
        answer = _i50_python_answer(tmp / cwd, _i50_row_env(env, tmp, row))
        if not _i50_matches(answer, want, row, tmp):
            failures.append(f"{row} ({answer!r}, expected {want!r})")
    assert not failures, "main_worktree_root():\n" + "\n".join(failures)


def test_worktree_reference_table_is_the_matrix() -> None:
    lines = read_skill(_I50_REFERENCE).splitlines()
    head = lines.index("| 레이아웃 | 답 |")
    table = {}
    for line in lines[head + 2:]:
        if not line.startswith("|"):
            break
        label, answer = [c.strip() for c in line.strip("|").split("|")]
        table[label] = answer
    assert set(table) == set(_I50_TABLE_ROWS), f"the support table's layouts changed: {sorted(table)}"
    rows = {r[0]: r for r in _I50_ROWS}
    for label, answer in table.items():
        assert answer in _I50_TABLE_ANSWERS, f"unknown answer {answer!r} for {label!r}"
        for row in _I50_TABLE_ROWS[label]:
            assert rows[row][2] == _I50_TABLE_ANSWERS[answer] == rows[row][3], (
                f"the table says {label!r} -> {answer!r}, the matrix says {rows[row][2:]!r}"
            )


def test_every_skill_resolution_is_the_canonical_block() -> None:
    canonical = _i50_canonical()
    counts = {}
    for md in sorted((ROOT / "skills").rglob("*.md")):
        rel = str(md.relative_to(ROOT))
        for fence in _fences_of(md.read_text(encoding="utf-8")):
            lines = [l.strip() for l in fence.splitlines()]
            for i, line in enumerate(lines):
                if not line.startswith("FIRST_WORKTREE="):
                    continue
                counts[rel] = counts.get(rel, 0) + 1
                got = lines[i:i + 4]
                name = next((n for n in _I50_RESOLVE_NAMES if got[1].startswith(n + "=")), None)
                assert name, f"{rel}: unknown variable in {got[1]!r}"
                want = [l.strip().replace("MAIN_CHECKOUT", name) for l in canonical]
                assert got == want, f"{rel} resolves the main checkout differently:\n{got}\n{want}"
    assert counts == _I50_COPIES, f"canonical copies per file changed: {counts}"


def test_no_other_main_checkout_resolution_in_skill_fences() -> None:
    """The one-liners the canonical block replaced, and the ones it bans, stay out."""
    idiom = "git worktree list --porcelain | sed -n '1s/^worktree //p'"
    for md in sorted((ROOT / "skills").rglob("*.md")):
        rel = str(md.relative_to(ROOT))
        for fence in _fences_of(md.read_text(encoding="utf-8")):
            for line in fence.splitlines():
                s = line.strip()
                for banned in ("--git-common-dir", "--path-format", "--absolute-git-dir"):
                    assert banned not in s, f"{rel}: a fence builds a path from {banned}: {s!r}"
                if idiom in s:
                    assert s.startswith("FIRST_WORKTREE="), f"{rel}: the first entry is used as the answer: {s!r}"


def test_skill_fences_have_no_cwd_relative_plan_paths() -> None:
    scoped = ("project-done", "project-iterate", "project-start", "project-adr", "project-clean", "project-issue")
    bare = re.compile(r'(?<!\$MAIN_CHECKOUT/)(?<!\$REPORT_ROOT/)(?<!"\$MAIN_CHECKOUT"/)\.task/plan/plan-')
    for skill in scoped:
        for fence in _fences_of(read_skill(f"skills/{skill}/SKILL.md")):
            for line in fence.splitlines():
                assert not bare.search(line), f"{skill}: a CWD-relative plan path: {line.strip()!r}"
                for banned in ('Path(".task/plan")', 'Path(".task") / "plan"', 'glob(".task/'):
                    assert banned not in line, f"{skill}: a CWD-relative plan directory: {line.strip()!r}"


def test_path_lookups_share_one_id_refusal() -> None:
    """done 1, start 1-A, iterate's plan check and adr 1 refuse a bad id with the same lines."""
    def refusal(text: str, heading: str | None, placeholder: str) -> str:
        section = skill_section(text, heading) if heading else text
        fences = [f for f in _fences_of(section) if "FIRST_WORKTREE=" in f and "case '" in f]
        assert len(fences) == 1, f"expected one shell plan lookup under {heading!r}"
        return "\n".join(fences[0].splitlines()[:5]).replace(placeholder, "<ID>")

    blocks = {
        "done": refusal(_done_skill(), "**1. Confirm plan file**", "<issue-id>"),
        "start": refusal(_start_skill(), "**1-A.", "<issue-id>"),
        "adr": refusal(read_skill("skills/project-adr/SKILL.md"), "**1. Decide ADR Content**", "<issue-id>"),
        "iterate": refusal(_region_text(_iterate_skill(), "## Re-entry After Interruption", "## Instructions"),
                           None, "<id>"),
    }
    assert len(set(blocks.values())) == 1, f"the id refusals drifted apart: {blocks}"
    for name, (fence, _) in _i50_plan_lookups().items():
        assert "harness_core" not in fence and "python" not in fence, f"{name}'s path lookup reaches for python"


def _region_text(text: str, start: str, end: str) -> str:
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(start))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith(end))
    return "\n".join(lines[i:j])


def _i50_plan_lookups() -> dict:
    """The shell plan lookups that print only PLAN=, with their id placeholder."""
    def one(section: str) -> str:
        fences = [f for f in _fences_of(section) if "FIRST_WORKTREE=" in f and "PLAN=" in f]
        assert len(fences) == 1
        return fences[0]
    return {
        "start": (one(skill_section(_start_skill(), "**1-A.")), "<issue-id>"),
        "adr": (one(skill_section(read_skill("skills/project-adr/SKILL.md"), "**1. Decide ADR Content**")), "<issue-id>"),
        "iterate": (one(_region_text(_iterate_skill(), "## Re-entry After Interruption", "## Instructions")), "<id>"),
    }


_I50_LOOKUP_ROWS = (
    ("worktree", "wt", "7", "ok"),
    ("worktree subdir", "wt/sub/dir", "7", "ok"),
    ("main", "main", "7", "ok"),
    ("underscore key", "wt", "AB_C-7", "ok"),
    ("missing", "wt", "8", "stop"),
    ("leading zero", "wt", "07", "stop"),
    ("multi-line id", "wt", "7\n8", "stop"),
    ("traversal", "wt", "x/../../plan/plan-7", "stop"),
    ("no repo", "norepo", "7", "unresolved"),
    ("separate git dir", "sep-wt", "7", "unresolved"),
)


def test_plan_lookup_rows_are_all_present() -> None:
    assert [r[0] for r in _I50_LOOKUP_ROWS] == [
        "worktree", "worktree subdir", "main", "underscore key", "missing", "leading zero",
        "multi-line id", "traversal", "no repo", "separate git dir",
    ], "a plan-lookup row was dropped or renamed"


@pytest.mark.parametrize("skill", ["start", "adr", "iterate"])
def test_plan_lookups_behave_in_every_row(skill: str, tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    fence, placeholder = _i50_plan_lookups()[skill]
    tmp = tmp_path.resolve()
    env = _step1_repos(tmp)
    plans = tmp / "main" / ".task" / "plan"
    for shell in _shells():
        for name, cwd, issue_id, expected in _I50_LOOKUP_ROWS:
            result = subprocess.run([*shell, "-c", fence.replace(placeholder, issue_id)],
                                    cwd=tmp / cwd, env=env, capture_output=True, text=True)
            where = f"{skill} {name} under {' '.join(shell)}"
            if expected == "ok":
                assert result.returncode == 0, f"{where}: {result.stdout!r} {result.stderr!r}"
                value = result.stdout.splitlines()
                assert len(value) == 1 and value[0].startswith("PLAN="), f"{where}: {result.stdout!r}"
                path = value[0][len("PLAN="):]
                assert os.path.isabs(path) and Path(path).resolve() == (plans / f"plan-{issue_id}.md").resolve(), where
                assert not (tmp / "wt" / ".task").exists(), f"{where}: created .task/ in the worktree"
            else:
                assert result.returncode != 0 and "PLAN=" not in result.stdout, f"{where}: did not stop"
                if expected == "unresolved":
                    assert "could not resolve the main checkout" in result.stdout, f"{where}: {result.stdout!r}"


def test_clean_protects_the_bases_declared_in_the_main_checkout(tmp_path: Path) -> None:
    """From a linked worktree the old relative grep found no plan and protected nothing."""
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    text = read_skill("skills/project-clean/SKILL.md")
    fences = [f for f in _fences_of(text) if "FIRST_WORKTREE=" in f]
    assert len(fences) == 1, "project-clean should hold one collecting fence"
    lines = fences[0].splitlines()
    upto = next(i for i, l in enumerate(lines) if l.startswith("printf 'PROTECT="))
    collect = "\n".join(l for l in lines[:upto + 1] if not l.startswith("git fetch"))
    exclude = next(l for l in lines if "grep -vxF" in l).strip()
    assert exclude.startswith("| grep -vxF \"$PROTECT\""), exclude

    tmp = (tmp_path / "with space").resolve()
    tmp.mkdir()
    env = _step1_repos(tmp)
    (tmp / "main" / ".task" / "plan" / "plan-9.md").write_text("---\nbase_branch: feat/x\n---\n# Plan: x\n")
    (tmp / "wt" / ".task" / "plan").mkdir(parents=True)
    (tmp / "wt" / ".task" / "plan" / "plan-9.md").write_text("---\nbase_branch: decoy\n---\n# Plan: d\n")
    result = subprocess.run(["sh", "-c", collect], cwd=tmp / "wt", env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "PROTECT=feat/x", f"the protected set was read elsewhere: {result.stdout!r}"
    kept = subprocess.run(["sh", "-c", "printf 'feat/x\\nfeat/y\\n' " + exclude],
                          env={**env, "PROTECT": "feat/x"}, capture_output=True, text=True)
    assert kept.stdout.split() == ["feat/y"], f"the protected branch is not excluded: {kept.stdout!r}"


def test_done_wording_matches_the_canonical_rule() -> None:
    text = _done_skill()
    assert not re.search(r"first entry.*always", text), "the 'first entry is always the main worktree' claim is back"
    assert "derive it differently" not in text
    bullet = rule_line(text, "**Resolve the main checkout by asking git for it")
    for token in ("separate-git-dir", ".git/modules", "--show-toplevel"):
        assert token in bullet, f"the Jira bullet no longer explains {token}"
    assert "stops when there is none" in bullet
    forgejo = rule_line(text, "**보고서는 절대 경로로 넘긴다.**")
    assert "--git-common-dir" not in forgejo and "해석 네 줄" in forgejo
    assert "the same rule as the fence below, so both give the same directory or both stop" in rule_line(
        text, "That form prints the path `main_worktree_root()` resolves")


def test_clean_and_config_name_the_canonical_block() -> None:
    clean = read_skill("skills/project-clean/SKILL.md")
    assert_rule(clean, "**run this fence as one shell invocation**",
                starts_with="Collect first — **run this fence as one shell invocation**.")
    assert "PROTECT` comes back empty" in rule_line(clean, "**run this fence as one shell invocation**")
    assert_whole_line(read_skill("skills/SKILL-CONFIG.md"),
                      "| `_shared/references/worktree.md` | 워크트리 CWD 주의사항, main checkout 해석 정본 | "
                      "project-start · project-done · project-clean · project-adr |")


def test_worktree_reference_rule_section_is_pinned_whole() -> None:
    lines = read_skill(_I50_REFERENCE).splitlines()
    start = lines.index("## main checkout 해석 정본")
    got = tuple(l.strip() for l in lines[start:] if l.strip())
    assert got == _I50_REFERENCE_SECTION, "the canonical rule's prose in worktree.md changed"


_I50_REFERENCE_SECTION = (
    '## main checkout 해석 정본',
    'main checkout 경로가 필요한 셸 단계(harness 가 없을 때의 fallback 포함)는 아래 블록을 **문자 그대로** 복사해 쓴다. 변수명만 `MAIN_CHECKOUT`',
    '또는 `REPORT_ROOT` 로 바꿀 수 있다. 이 파일이 원본이고, 스킬의 사본이 이 블록과 같은지는',
    '`tests/test_skill_docs.py` 가 검사한다. 스킬이 실행 중에 이 파일을 읽는 것은 아니다.',
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    '```',
    '규칙: `git worktree list --porcelain` 의 첫 항목을 얻고, **그 항목의 작업 트리를 git 에게 다시 묻는다**',
    '(`git -C <첫 항목> rev-parse --show-toplevel`). 답이 없으면 멈춘다. `main_worktree_root()` 도 같은 규칙이다.',
    '- 첫 항목을 그대로 쓰지 않는다. submodule 에서는 `.git/modules/<name>`, separate-git-dir 에서는 git dir 이 첫 항목으로 나온다.',
    '- `--git-common-dir` 의 부모로 만들지 않는다. submodule·separate-git-dir·bare 에서 **존재하는 엉뚱한 디렉터리**가 된다.',
    '- CWD 의 `--show-toplevel`·`$PWD` 로 만들지 않는다. 링크드 워크트리 자신이 나온다.',
    '- `[ -n "$FIRST_WORKTREE" ] &&` 를 빼지 않는다. `git -C ""` 는 CWD 에 머물러 링크드 워크트리를 답한다.',
    '- `|| :` 를 빼지 않는다. 대입문의 종료코드는 치환의 종료코드라서, 이게 없으면 `sh -e` 가 아래 메시지 전에 셸을 죽인다.',
    '| 레이아웃 | 답 |',
    '|----------|----|',
    '| 일반 clone | main checkout |',
    '| 링크드 워크트리 | main checkout |',
    '| submodule | submodule checkout |',
    '| submodule 의 링크드 워크트리 | submodule checkout |',
    '| separate-git-dir | 멈춤 |',
    '| bare | 멈춤 |',
    '| bare 의 링크드 워크트리 | 멈춤 |',
    'git dir 이름이 다른 디렉터리의 `.git` 인 separate-git-dir(`--separate-git-dir=/x/other/.git`)는 git 이 그 부모를 작업 트리로 보고하므로 이 규칙이 가려내지 못한다 — 드문 배치라 검사하지 않는다. 그 밖의 separate-git-dir 는 링크드 워크트리에서 main work tree 를 알아낼 방법이 없다(git dir 이 작업 트리를',
    '가리키지 않는다). 그래서 main 에서 부르든 링크드에서 부르든 똑같이 멈춘다. 저장소 밖에서는 셸 블록이 멈추고,',
    '`main_worktree_root()` 는 CWD 로 폴백한다.',
)



def test_plan_dir_propagates_the_unresolved_layout(tmp_path: Path, monkeypatch) -> None:
    """The CLI stops in a bare repo instead of treating CWD as the main checkout."""
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    from harness_core import cli
    from harness_core.git import MainWorktreeUnresolvedError, main_worktree_root

    bare = tmp_path / "b.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=_i50_env(tmp_path))
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(bare)
    main_worktree_root.cache_clear()
    try:
        with pytest.raises(MainWorktreeUnresolvedError):
            cli._plan_dir()
    finally:
        main_worktree_root.cache_clear()


def _i50_mutants(block: str) -> dict:
    lines = block.splitlines()
    assert lines[1].startswith("MAIN_CHECKOUT=")
    mutants = {
        "no empty check": block.replace('[ -n "$FIRST_WORKTREE" ] && ', ""),
        "no || :": block.replace(" || :)", ")"),
        "first entry as the answer": block.replace(lines[1], 'MAIN_CHECKOUT="$FIRST_WORKTREE"'),
        "common-dir parent": block.replace(lines[1], 'MAIN_CHECKOUT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd -P)"'),
        "cwd toplevel": block.replace(lines[1], 'MAIN_CHECKOUT="$(git rev-parse --show-toplevel)"'),
        "every worktree": block.replace("'1s/^worktree //p'", "'s/^worktree //p'"),
    }
    for name, mutant in mutants.items():
        assert mutant != block, f"mutant {name!r} did not change the block"
    return mutants


# Each mutant, the row that exists to catch it, and the shell it needs.
_I50_MUTANT_CATCHERS = {
    "no empty check": ("shim-wt", ("sh",)),
    "no || :": ("sep", ("sh", "-e")),
    "first entry as the answer": ("sub", ("sh",)),
    "common-dir parent": ("sub", ("sh",)),
    "cwd toplevel": ("wt", ("sh",)),
    "every worktree": ("wt", ("sh",)),
}


@pytest.mark.parametrize("mutant", sorted(_I50_MUTANT_CATCHERS))
def test_canonical_rows_reject_each_mutant(mutant: str, _i50_matrix) -> None:
    tmp, env = _i50_matrix
    mutants = _i50_mutants("\n".join(_i50_canonical()))
    assert set(mutants) == set(_I50_MUTANT_CATCHERS)
    row, shell = _I50_MUTANT_CATCHERS[mutant]
    failures = _i50_block_failures(mutants[mutant], list(shell), tmp, env)
    assert any(f.startswith(f"{row} (") for f in failures), (
        f"the {row!r} row does not reject the {mutant!r} mutant: {failures}"
    )
    assert not any("syntax error" in f for f in failures), failures


def test_main_worktree_root_without_the_toplevel_question_fails_the_sub_row(_i50_matrix, monkeypatch) -> None:
    """The harness side of 'first entry as the answer': the sub row catches it too."""
    from harness_core import git as hgit

    tmp, _ = _i50_matrix
    real = subprocess.run

    def first_entry_as_answer(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "-C"] and cmd[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(cmd, 0, cmd[2] + "\n", "")
        return real(cmd, *args, **kwargs)

    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    for key, value in _isolated_git_env(tmp).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(hgit.subprocess, "run", first_entry_as_answer)
    monkeypatch.chdir(tmp / "super" / "sub")
    hgit.main_worktree_root.cache_clear()
    try:
        answer = str(hgit.main_worktree_root())
    finally:
        hgit.main_worktree_root.cache_clear()
    assert not _i50_matches(answer, "super/sub", "sub", tmp), "the sub row accepts the first entry as the answer"


# Every fence line in skills/** that names the worktree list, rev-parse,
# main_worktree_root or .task/plan, with its count. A new way of finding the
# main checkout — awk over the listing, a dirname of --git-dir, a python
# one-liner — shows up here as a line nobody pinned.
_I50_RESOLUTION_LINES = (
    ('skills/_shared/references/worktree.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 1),
    ('skills/_shared/references/worktree.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 1),
    ('skills/project-adr/SKILL.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 1),
    ('skills/project-adr/SKILL.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 1),
    ('skills/project-adr/SKILL.md', 'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<issue-id>.md"', 1),
    ('skills/project-clean/SKILL.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 1),
    ('skills/project-clean/SKILL.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 1),
    ('skills/project-clean/SKILL.md', 'PROTECT=$(grep -hERo \'^base_branch:[[:space:]]*\\S+\' "$MAIN_CHECKOUT"/.task/plan/plan-*.md 2>/dev/null \\', 1),
    ('skills/project-clean/SKILL.md', 'git worktree list', 1),
    ('skills/project-clean/SKILL.md', 'git worktree remove --force "<worktree path from git worktree list>" 2>/dev/null || true', 1),
    ('skills/project-done/SKILL.md', 'BASE_BEFORE="$(git -C "$MAIN_CHECKOUT" rev-parse <base_branch>)"', 1),
    ('skills/project-done/SKILL.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 3),
    ('skills/project-done/SKILL.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 1),
    ('skills/project-done/SKILL.md', 'PLAN="$REPORT_ROOT/.task/plan/plan-<issue-id>.md"', 1),
    ('skills/project-done/SKILL.md', 'REPORT="$REPORT_ROOT/.task/plan/impl-report-<id>.md"', 1),
    ('skills/project-done/SKILL.md', 'REPORT_ROOT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 2),
    ('skills/project-done/SKILL.md', 'echo ".task/plan/" >> .gitignore ;;', 1),
    ('skills/project-done/SKILL.md', 'git check-ignore -q --no-index .task/plan/ && rc=0 || rc=$?', 1),
    ('skills/project-done/SKILL.md', 'git restore --staged ".task/plan/" 2>/dev/null || true', 1),
    ('skills/project-done/SKILL.md', 'printf \'PLAN=%s\\nREPORT=%s\\n\' "$PLAN" "$REPORT_ROOT/.task/plan/impl-report-<issue-id>.md"', 1),
    ('skills/project-issue/SKILL.md', 'from harness_core.git import main_worktree_root', 3),
    ('skills/project-issue/SKILL.md', 'plan_dir = (main_worktree_root() / ".task" / "plan").resolve()', 2),
    ('skills/project-issue/SKILL.md', 'python -c \'from harness_core.config import is_draft_plan; from harness_core.git import main_worktree_root; print("\\n".join(str(p) for p in sorted((main_worktree_root() / ".task" / "plan").glob("plan-*.md")) if is_draft_plan(p.name)))\'', 1),
    ('skills/project-issue/SKILL.md', 'target = main_worktree_root() / ".task" / "plan" / ("plan-%s.md" % sys.argv[1])', 1),
    ('skills/project-iterate/SKILL.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 2),
    ('skills/project-iterate/SKILL.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 2),
    ('skills/project-iterate/SKILL.md', 'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<id>.md"', 1),
    ('skills/project-iterate/SKILL.md', '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {', 1),
    ('skills/project-iterate/SKILL.md', "git worktree list --porcelain | python3 -c '", 1),
    ('skills/project-iterate/SKILL.md', 'rel = subprocess.run(["git", "-C", path, "rev-parse", "--git-path", name],', 1),
    ('skills/project-plan/SKILL.md', 'PLAN_FILE=".task/plan/plan-draft-${SLUG}-${N}.md"', 1),
    ('skills/project-plan/SKILL.md', 'PLAN_FILE=".task/plan/plan-draft-${SLUG}.md"', 1),
    ('skills/project-plan/SKILL.md', 'echo ".task/plan/" >> .gitignore ;;', 1),
    ('skills/project-plan/SKILL.md', 'git check-ignore -q --no-index .task/plan/ && rc=0 || rc=$?', 1),
    ('skills/project-plan/SKILL.md', 'mkdir -p .task/plan', 1),
    ('skills/project-release/SKILL.md', "REMOTE_TAG_SHA=$(git rev-parse 'FETCH_HEAD^{}')", 1),
    ('skills/project-release/SKILL.md', 'test "$(git rev-parse \'<tag>^{}\')" = "$RELEASE_SHA"', 1),
    ('skills/project-start/SKILL.md', 'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"', 5),
    ('skills/project-start/SKILL.md', 'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"', 5),
    ('skills/project-start/SKILL.md', 'PLAN="$MAIN_CHECKOUT/.task/plan/plan-<issue-id>.md"', 1),
    ('skills/project-start/SKILL.md', '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {', 1),
)


def test_resolution_lines_in_skill_fences_are_pinned() -> None:
    tokens = ("worktree list", "rev-parse", "main_worktree_root", ".task/plan")
    seen: dict = {}
    for md in sorted((ROOT / "skills").rglob("*.md")):
        rel = str(md.relative_to(ROOT))
        for fence in _fences_of(md.read_text(encoding="utf-8")):
            for line in fence.splitlines():
                if any(t in line for t in tokens):
                    seen[(rel, line.strip())] = seen.get((rel, line.strip()), 0) + 1
    got = tuple((rel, line, n) for (rel, line), n in sorted(seen.items()))
    assert got == _I50_RESOLUTION_LINES, (
        "fence lines that locate the main checkout or the plan directory changed; "
        "if the new line follows the canonical rule, pin it here:\n"
        + "\n".join(repr(e) for e in sorted(set(got) ^ set(_I50_RESOLUTION_LINES)))
    )


# --------------------------------------------------------------------------
# project-start defaults to a worktree too (#43, #42 D3 follow-up)
#
# #42 moved `project-iterate` to a worktree default and left `project-start`
# alone, so the two entry points disagreed. #43 gives `project-start` the same
# vocabulary (`in-place`, `worktree` as a lasting alias) and moves iterate's
# Phase 3 checks — base on the default branch in both modes, the ignore
# warning — into a new Step 1-C, so the one place both entry points pass
# through holds the only copy. The worktree is placed and cut from the main
# checkout from any CWD: by the harness (`create_worktree`, tested in
# test_git.py) and by the 2-B fallback fence.
#
# Two layers again: goldens pin the regions line by line, and scenarios run
# every fence in real repos. Each mutant below breaks one thing a fence
# protects and must turn its scenario red — a green scenario proves nothing
# unless a broken fence makes it fail. Linked-worktree scenarios give feat/x a
# commit of its own; without it "branched from the main checkout" cannot fail.
# --------------------------------------------------------------------------

_I43_PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*>")

_I43_START_1B = "- If `base_branch` is `null` or equals the project default base, omit `--base-ref` and branch from the main checkout's HEAD, which Step 1-C requires to be on the project default base. Do not add a new prompt."
_I43_START_2A = '**2-A. In-place branch (with `in-place`)**'
_I43_ITERATE_ANCHOR = '- The Phase 3 checks are that flag display and `project-start` Step 1-C, which runs the base check and the ignore check from the main checkout; iterate does not run them a second time.'
_I43_README_ROW = '| `project-start` | 브랜치/워크트리 생성 + 이슈 In Progress + 구현 시작. 기본은 main checkout 아래에 워크트리를 만들고(어느 CWD 에서 불러도 같다), `in-place` 를 붙이면 main checkout 에서 제자리 분기한다. 로컬 `plan-<id>.md` 가 없으면 브랜치를 만들기 전에 멈춘다 |'

_I43_START_USAGE = (
    '## Usage',
    '```',
    'project-start <issue-id> [in-place] [adr]',
    '```',
    '- `<issue-id>`: GitHub issue number or Jira ticket ID (required)',
    '- `[in-place]`: branch in the main checkout itself (Step 2-A) instead of in a worktree',
    '- `[adr]`: write ADR before implementation (`project-adr` internal call)',
    'Branching defaults to a worktree: unless `in-place` is given, Step 2-B creates one under the main checkout.',
    'The `worktree` token is accepted as an alias of that default and changes nothing; when it is given, say in one line that a worktree is already the default.',
    'Argument rules:',
    '- The first token is the issue id — an issue number or a Jira key; a flag (`in-place`, `worktree`, `adr`) as the first token is an error — stop and show the correct order.',
    '- The id is followed only by flags; if any other token follows it, stop and ask what was meant.',
    '- A flag counts only as a standalone token after the id, in exact lowercase, in any order.',
    '- A token that is a near spelling of a flag (`--in-place`, `inplace`, `In-place`, `--worktree`) is not guessed — ask the user which was meant.',
    '- `in-place` and `worktree` together are a conflict — stop and have the user pick one.',
)

_I43_START_1C = (
    '**1-C. Pre-branch checks**',
    'These run before any branch, worktree, status change or ADR. Run each fence below as one shell call — shell variables do not survive to the next call; `could not resolve the main checkout` from any fence means stop and report. The resolving lines are the canonical block in `~/.claude/skills/_shared/references/worktree.md`.',
    '- With `in-place` only: the CWD must be the main checkout, because 2-A branches wherever it runs; from any other CWD, stop and print the main checkout path. A worktree needs no such check: 2-B creates it under the main checkout from any CWD.',
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {',
    'echo "not the main checkout — rerun from: $MAIN_CHECKOUT"; exit 1; }',
    '```',
    '- In both modes, read the base Step 1-B found. If the plan declares no base, or declares the project default base, the main checkout must be on the project default base; if it is not, stop and report.',
    "- This base check holds in both modes: a branch cut while another session's in-place run has left the main checkout on a feature branch would stack on that feature. Stacking on purpose is what plan frontmatter `base_branch` is for.",
    '- A declared base other than the project default base skips this base check only; 2-A or 2-B then branches from that base. Fill `<project default base>` below with the `base_branch` that Read Settings found in `skill-config.yaml`.',
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    'CURRENT="$(git -C "$MAIN_CHECKOUT" branch --show-current)"',
    '[ "$CURRENT" = "<project default base>" ] || {',
    'echo "main checkout is on \'${CURRENT:-a detached HEAD}\', not <project default base>"; exit 1; }',
    '```',
    '- In worktree mode, check that the main checkout ignores `.claude/worktrees/`, whether or not the base check was skipped. The trailing slash is required: without it a directory-only pattern does not match.',
    '- Read the printed `check-ignore rc=<n>` line. `rc=0`: nothing to say.',
    '- `rc=1`: warn in one line and continue — an unignored worktree directory can be staged as a gitlink by `git add -A` in an in-place run; the line to add is `.claude/worktrees/` in `.gitignore` or `.git/info/exclude`.',
    '- Any other `rc=`: warn that ignoring could not be decided, and continue.',
    '- This check writes to no file and is not a gate.',
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    'git -C "$MAIN_CHECKOUT" check-ignore -q .claude/worktrees/',
    'echo "check-ignore rc=$?"',
    '```',
)

_I43_START_2B = (
    '**2-B. Worktree (default)**',
    '```bash',
    '# When base is declared',
    '<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>" --base-ref "<base_branch>"',
    '# When base is undeclared (default)',
    '<harness_cli> create-worktree ".claude/worktrees/<project>-issue-<id>" "<branch-name>"',
    '```',
    "`create-worktree` takes the relative path under the main checkout and runs there, from any CWD, and prints the worktree's absolute path. It stops before creating anything when the layout has no main work tree.",
    "Without a harness_cli, use this fence — **run it as one shell invocation**; the four resolving lines are the canonical block in `~/.claude/skills/_shared/references/worktree.md`. Fill `BASE` by Step 1-B's rule: empty when the plan declares no base or declares the project default base, so the worktree branches from the main checkout's HEAD; otherwise the declared base, which is resolved as a local branch first, then as `origin/<base>`, fetching that one branch when neither exists; a base written as `origin/<base>` skips the local branch. `--no-track` keeps either one from becoming the new branch's upstream.",
    '```bash',
    'FIRST_WORKTREE="$(git worktree list --porcelain | sed -n \'1s/^worktree //p\')"',
    'MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"',
    '[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {',
    'echo "could not resolve the main checkout"; exit 1; }',
    'WORKTREE_PATH="$MAIN_CHECKOUT/.claude/worktrees/<project>-issue-<id>"',
    "BASE='<base_branch, or empty>'",
    'if [ -z "$BASE" ]; then',
    'git -C "$MAIN_CHECKOUT" worktree add --no-track "$WORKTREE_PATH" -b "<branch-name>" || exit 1',
    'else',
    'B="${BASE#origin/}"',
    'if [ "$B" = "$BASE" ] && git -C "$MAIN_CHECKOUT" show-ref --verify -q "refs/heads/$B"; then',
    'REF="refs/heads/$B"',
    'else',
    'REF="refs/remotes/origin/$B"',
    'git -C "$MAIN_CHECKOUT" show-ref --verify -q "$REF" ||',
    'git -C "$MAIN_CHECKOUT" fetch origin "+refs/heads/$B:$REF" || exit 1',
    'fi',
    'git -C "$MAIN_CHECKOUT" worktree add --no-track "$WORKTREE_PATH" -b "<branch-name>" "$REF" || exit 1',
    'fi',
    'printf \'WORKTREE_PATH=%s\\n\' "$WORKTREE_PATH"',
    '```',
    '`$WORKTREE_PATH` is the absolute path either form printed — `create-worktree` bare, the fallback as `WORKTREE_PATH=<path>`; substitute it as a literal from here on.',
    'After this, perform all work inside `$WORKTREE_PATH`.',
)



def _i43_fill(fence: str, **subs: str) -> str:
    """Substitute the placeholders a caller fills; none may survive."""
    for key, value in subs.items():
        assert key in fence, f"placeholder {key!r} is not in the fence"
        fence = fence.replace(key, value)
    left = _I43_PLACEHOLDER.findall(fence)
    assert not left, f"placeholders left unfilled: {left}"
    return fence


def _i43_start_fences() -> dict:
    """The four shell fences #43 wrote into project-start, by name, indentation intact."""
    text = _start_skill()
    checks = _fences_of(skill_section(text, "**1-C."))
    assert len(checks) == 3, f"1-C should hold the in-place, base and ignore fences, found {len(checks)}"
    fallback = [f for f in _fences_of(skill_section(text, "**2-B.")) if "FIRST_WORKTREE=" in f]
    assert len(fallback) == 1, "2-B should hold exactly one fallback fence"
    return {"in-place": checks[0], "base": checks[1], "ignore": checks[2], "fallback": fallback[0]}


def _i43_git(env: dict, *args: str, cwd: Path) -> str:
    return subprocess.run(["git", "-c", "init.defaultBranch=main", *args], cwd=cwd, env=env,
                          check=True, capture_output=True, text=True).stdout.strip()


def _i43_commit(env: dict, cwd: Path, name: str) -> str:
    (cwd / name).write_text(name)
    _i43_git(env, "add", name, cwd=cwd)
    _i43_git(env, "commit", "-q", "-m", name, cwd=cwd)
    return _i43_git(env, "rev-parse", "HEAD", cwd=cwd)


def _i43_repos(tmp: Path) -> tuple[Path, Path, dict]:
    """A main checkout on `main` and a linked worktree on feat/x one commit ahead.

    The extra commit on feat/x is what lets "branched from the main checkout's
    HEAD" fail: without it the two HEADs are the same commit.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    tmp = tmp.resolve()
    env = _i50_env(tmp)
    main = tmp / "main"
    _i43_git(env, "init", "-q", str(main), cwd=tmp)
    _i43_commit(env, main, "init")
    linked = tmp / "linked"
    _i43_git(env, "worktree", "add", "-q", "-b", "feat/x", str(linked), cwd=main)
    _i43_commit(env, linked, "x")
    (main / "sub" / "dir").mkdir(parents=True)
    (linked / "sub" / "dir").mkdir(parents=True)
    return main, linked, env


def _i43_sh(code: str, cwd: Path, env: dict, shell: tuple = ("sh",)) -> subprocess.CompletedProcess:
    return subprocess.run([*shell, "-c", code], cwd=cwd, env=env, capture_output=True, text=True)


def _i43_inplace_failures(fence: str, tmp: Path) -> list[str]:
    main, linked, env = _i43_repos(tmp)
    failures = []
    for shell in (("sh",), ("sh", "-e")):
        for cwd, ok in ((main, True), (main / "sub" / "dir", True), (linked, False), (linked / "sub" / "dir", False)):
            r = _i43_sh(fence, cwd, env, shell)
            if ok and r.returncode != 0:
                failures.append(f"{shell} {cwd.name}: refused the main checkout: {r.stdout!r}")
            if not ok and (r.returncode == 0 or str(main) not in r.stdout):
                failures.append(f"{shell} {cwd}: let a linked worktree through or named no main path: {r.stdout!r}")
    return failures


def _i43_base_failures(fence: str, tmp: Path) -> list[str]:
    code = _i43_fill(fence, **{"<project default base>": "main"})
    main, linked, env = _i43_repos(tmp)
    failures = []
    for cwd in (main, linked):
        r = _i43_sh(code, cwd, env)
        if r.returncode != 0:
            failures.append(f"from {cwd.name} with main on main: refused ({r.stdout!r})")
    _i43_git(env, "checkout", "-q", "-b", "feat/other", cwd=main)
    r = _i43_sh(code, linked, env)
    if r.returncode == 0:
        failures.append("main checkout on feat/other: passed")
    _i43_git(env, "checkout", "-q", "--detach", cwd=main)
    r = _i43_sh(code, linked, env)
    if r.returncode == 0 or "a detached HEAD" not in r.stdout:
        failures.append(f"detached main checkout: {r.returncode} {r.stdout!r}")
    return failures


def _i43_tree_digest(root: Path) -> dict:
    """Every file's content under root, `.git/index` aside (git may refresh its stat cache)."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != "index"}


def _i43_ignore_failures(fence: str, tmp: Path) -> list[str]:
    tmp.mkdir(parents=True, exist_ok=True)
    failures = []
    # Main's branch ignores the directory with a directory-only pattern; feat/x,
    # cut before that commit, does not. The directory does not exist, so only
    # the trailing slash matches, and only the main checkout's .gitignore says so.
    main, linked, env = _i43_repos(tmp / "ignored")
    (main / ".gitignore").write_text(".claude/worktrees/\n")
    _i43_git(env, "add", ".gitignore", cwd=main)
    _i43_git(env, "commit", "-q", "-m", "ignore", cwd=main)
    unignored_main, unignored_linked, unignored_env = _i43_repos(tmp / "unignored")
    shim = tmp / "shim"
    shim.mkdir()
    (shim / "git").write_text('#!/bin/sh\nfor a in "$@"; do [ "$a" = check-ignore ] && exit 128; done\n'
                              'exec "%s" "$@"\n' % shutil.which("git"))
    (shim / "git").chmod(0o755)
    shim_env = {**env, "PATH": f"{shim}{os.pathsep}{env['PATH']}"}
    cases = (
        ("ignored, from main", main, env, "check-ignore rc=0"),
        ("ignored, from linked", linked, env, "check-ignore rc=0"),
        ("unignored", unignored_linked, unignored_env, "check-ignore rc=1"),
        ("git cannot answer", linked, shim_env, "check-ignore rc=128"),
    )
    before = _i43_tree_digest(tmp)
    for name, cwd, run_env, want in cases:
        r = _i43_sh(fence, cwd, run_env)
        if r.returncode != 0 or r.stdout.strip() != want:
            failures.append(f"{name}: rc {r.returncode}, {r.stdout.strip()!r}, expected {want!r}")
    if _i43_tree_digest(tmp) != before:
        failures.append("the ignore check changed a file")
    return failures


def _i43_origin(tmp: Path, env: dict, main: Path) -> dict:
    """An origin holding branches main has never fetched; returns their tips."""
    seed = tmp / "seed"
    _i43_git(env, "clone", "-q", str(main), str(seed), cwd=tmp)
    tips = {}
    for branch in ("feat/remote-only", "feat/prefixed", "feat/cached", "feat/narrow"):
        _i43_git(env, "checkout", "-q", "-b", branch, "main", cwd=seed)
        tips[branch] = _i43_commit(env, seed, branch.replace("/", "_"))
    _i43_git(env, "remote", "add", "origin", str(seed), cwd=main)
    return tips


def _i43_fallback_failures(fence: str, tmp: Path) -> list[str]:
    main, linked, env = _i43_repos(tmp)
    # With autoSetupMerge=always, only --no-track keeps a base from becoming the upstream.
    env = {**env, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "branch.autoSetupMerge",
           "GIT_CONFIG_VALUE_0": "always"}
    _i43_git(env, "branch", "feat/prefixed", cwd=main)  # a stale local namesake of origin/feat/prefixed
    tips = _i43_origin(tmp.resolve(), env, main)
    tips["feat/int"] = _i43_commit(env, main, "int-base")  # main moves on; feat/int is cut here
    _i43_git(env, "branch", "feat/int", cwd=main)
    _i43_git(env, "reset", "-q", "--hard", "HEAD~1", cwd=main)
    main_head = _i43_git(env, "rev-parse", "HEAD", cwd=main)
    feat_x = _i43_git(env, "rev-parse", "feat/x", cwd=main)
    failures = []

    def run(n: int, base: str) -> tuple[subprocess.CompletedProcess, str]:
        code = _i43_fill(fence, **{"<project>": "p", "<id>": str(n), "<branch-name>": f"feat/issue-{n}-y",
                                    "<base_branch, or empty>": base})
        return _i43_sh(code, linked, env), f"feat/issue-{n}-y"

    def created(n: int, r: subprocess.CompletedProcess, branch: str, want_tip: str) -> None:
        want = main / ".claude" / "worktrees" / f"p-issue-{n}"
        printed = [l[len("WORKTREE_PATH="):] for l in r.stdout.splitlines() if l.startswith("WORKTREE_PATH=")]
        if r.returncode != 0 or len(printed) != 1:
            failures.append(f"case {n}: rc {r.returncode}, {r.stdout!r}, {r.stderr!r}")
            return
        if not os.path.isabs(printed[0]) or os.path.realpath(printed[0]) != str(want):
            failures.append(f"case {n}: printed {printed[0]!r}, expected {want}")
        listed = _i43_git(env, "worktree", "list", "--porcelain", cwd=main)
        if f"worktree {want}" not in listed.splitlines():
            failures.append(f"case {n}: no worktree at {want}")
        if (linked / ".claude").exists():
            failures.append(f"case {n}: nested under the linked worktree")
        tip = _i43_git(env, "rev-parse", branch, cwd=main)
        if tip != want_tip:
            failures.append(f"case {n}: branched from {tip[:7]}, expected {want_tip[:7]} (feat/x is {feat_x[:7]})")
        upstream = subprocess.run(["git", "rev-parse", "--abbrev-ref", branch + "@{upstream}"], cwd=main,
                                  env=env, capture_output=True)
        if upstream.returncode == 0:
            failures.append(f"case {n}: {branch} tracks an upstream")

    r, b = run(1, "")
    created(1, r, b, main_head)
    r, b = run(2, "feat/int")
    created(2, r, b, tips["feat/int"])
    r, b = run(3, "feat/remote-only")
    created(3, r, b, tips["feat/remote-only"])
    r, b = run(4, "origin/feat/prefixed")
    created(4, r, b, tips["feat/prefixed"])
    _i43_git(env, "fetch", "-q", "origin", "+refs/heads/feat/cached:refs/remotes/origin/feat/cached", cwd=main)
    _i43_git(env, "remote", "set-url", "origin", str(tmp / "gone"), cwd=main)
    r, b = run(5, "feat/cached")
    created(5, r, b, tips["feat/cached"])
    _i43_git(env, "remote", "set-url", "origin", str(tmp.resolve() / "seed"), cwd=main)
    _i43_git(env, "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main", cwd=main)
    r, b = run(6, "feat/narrow")
    created(6, r, b, tips["feat/narrow"])
    for n, base, why in ((7, "feat/no-such", "a missing base"), (1, "", "an existing branch and path")):
        r, _ = run(n, base)
        if r.returncode == 0 or "WORKTREE_PATH=" in r.stdout:
            failures.append(f"{why}: rc {r.returncode}, {r.stdout!r}")
    return failures


_I43_SCENARIOS = {
    "in-place": _i43_inplace_failures,
    "base": _i43_base_failures,
    "ignore": _i43_ignore_failures,
    "fallback": _i43_fallback_failures,
}


def _i43_mutants(fences: dict) -> dict:
    """name -> (fence name, mutated fence). Each one breaks what a scenario protects.

    `-C "$MAIN_CHECKOUT"` is dropped only as a whole: on `show-ref` and `fetch`
    alone, or on the declared-base `worktree add` alone, it changes nothing a
    run can see — refs are shared by every worktree, the path is absolute and
    the start point explicit. The `_I43_START_2B` golden pins those.
    """
    f = fences
    mutants = {
        "in-place compares against the CWD": ("in-place", f["in-place"].replace(
            '= "$(cd "$MAIN_CHECKOUT" && pwd -P)"', '= "$(pwd -P)"')),
        "in-place does not stop": ("in-place", f["in-place"].replace(
            'rerun from: $MAIN_CHECKOUT"; exit 1; }', 'rerun from: $MAIN_CHECKOUT"; }')),
        "base asks the CWD": ("base", f["base"].replace(
            'git -C "$MAIN_CHECKOUT" branch --show-current', "git branch --show-current")),
        "base does not stop": ("base", f["base"].replace(
            'not <project default base>"; exit 1; }', 'not <project default base>"; }')),
        "ignore without the slash": ("ignore", f["ignore"].replace(
            "check-ignore -q .claude/worktrees/", "check-ignore -q .claude/worktrees")),
        "ignore asks the CWD": ("ignore", f["ignore"].replace(
            'git -C "$MAIN_CHECKOUT" check-ignore', "git check-ignore")),
        "ignore writes .gitignore": ("ignore", f["ignore"].replace(
            'echo "check-ignore rc=$?"', 'echo "check-ignore rc=$?"; echo ".claude/worktrees/" >> .gitignore')),
        "fallback adds from the CWD": ("fallback", f["fallback"].replace(
            'git -C "$MAIN_CHECKOUT" worktree add', "git worktree add")),
        "fallback tracks the undeclared base": ("fallback", f["fallback"].replace(
            'worktree add --no-track "$WORKTREE_PATH" -b "<branch-name>" || exit 1\nelse',
            'worktree add "$WORKTREE_PATH" -b "<branch-name>" || exit 1\nelse')),
        "fallback prefers a stale local branch": ("fallback", f["fallback"].replace(
            'if [ "$B" = "$BASE" ] && git', "if git")),
        "fallback keeps origin/": ("fallback", f["fallback"].replace('B="${BASE#origin/}"', 'B="$BASE"')),
        "fallback fetches without a refspec": ("fallback", f["fallback"].replace(
            'fetch origin "+refs/heads/$B:$REF"', 'fetch origin "$B"')),
        "fallback fetches before the cached ref": ("fallback", f["fallback"].replace(
            'git -C "$MAIN_CHECKOUT" show-ref --verify -q "$REF" ||', "false ||")),
        "fallback prints a relative path": ("fallback", f["fallback"].replace(
            'printf \'WORKTREE_PATH=%s\\n\' "$WORKTREE_PATH"',
            'printf \'WORKTREE_PATH=%s\\n\' "${WORKTREE_PATH#"$MAIN_CHECKOUT"/}"')),
        "fallback reports a failed add": ("fallback", f["fallback"].replace(
            '-b "<branch-name>" || exit 1\nelse', '-b "<branch-name>"\nelse')),
    }
    for name, (kind, mutant) in mutants.items():
        assert mutant != fences[kind], f"mutant {name!r} did not change the {kind} fence"
    return mutants


def test_i43_start_regions_are_pinned_whole() -> None:
    text = _start_skill()
    for name, got, expected in (
        ("## Usage", _region(text, "## Usage", "## Instructions", inclusive=True), _I43_START_USAGE),
        ("1-C", _region(text, "**1-C.", "**2-A.", inclusive=True), _I43_START_1C),
        ("2-B", _region(text, "**2-B.", "**3.", inclusive=True), _I43_START_2B),
    ):
        assert tuple(got) == expected, f"project-start {name} changed"
    assert_whole_line(text, _I43_START_1B)
    assert_whole_line(text, _I43_START_2A)


def test_i43_start_usage_defaults_to_a_worktree() -> None:
    text = _start_skill()
    assert _golden_fences(list(_I43_START_USAGE)) == [["project-start <issue-id> [in-place] [adr]"]]
    assert "[worktree]" not in text, "project-start still advertises [worktree]"
    for marker in RETRACTION_MARKERS:
        for line in _I43_START_USAGE:
            assert marker not in line.lower(), f"a Usage rule reads as retracted ({marker!r}): {line!r}"


def test_i43_start_mode_words_live_only_in_pinned_lines() -> None:
    """A contradicting line elsewhere — "with no flag, branch in place" — is caught by vocabulary.

    `flag` is not in the pattern: the Jira transition lines use it for CLI flags.
    """
    text = _start_skill()
    pinned = set(_I43_START_USAGE + _I43_START_1C + _I43_START_2B + (_I43_START_1B, _I43_START_2A))
    stray = [l.strip() for l, in_fence in _outside_fences(text)
             if not in_fence and re.search(r"in-place|in place|`worktree`|default is a worktree", l, re.I)
             and l.strip() not in pinned]
    assert not stray, "a branch-mode rule was stated outside the pinned lines:\n" + "\n".join(stray)


def test_i43_start_checks_come_before_any_side_effect() -> None:
    order = [h.split(".")[0] for h in _step_order(_start_skill())]
    for earlier, later in (("**1-A", "**1-B"), ("**1-B", "**1-C"), ("**1-C", "**2-A"), ("**2-A", "**2-B"),
                           ("**2-B", "**3")):
        assert order.index(earlier) < order.index(later), f"{earlier} no longer precedes {later}: {order}"
    checks = "\n".join(_I43_START_1C)
    for effect in ("worktree add", "checkout -b", "add-progress", "create-branch", "create-worktree", "project-adr"):
        assert effect not in checks, f"1-C performs a side effect: {effect}"


def test_i43_start_fences_resolve_and_stop() -> None:
    text = _start_skill()
    fences = _i43_start_fences()
    for banned in ("--git-common-dir", "$PWD"):
        assert banned not in text, f"the main checkout is derived from {banned}"
    for name, fence in fences.items():
        lines = [l.strip() for l in fence.splitlines()]
        assert tuple(lines[:3]) == _MAIN_RESOLVE, f"{name}: the main checkout is resolved another way"
        for bad in ("exit 0", "|| true"):
            assert bad not in fence, f"{name}: a fence can pass early ({bad})"
    assert [l.strip() for l in fences["in-place"].splitlines() if "--show-toplevel" in l] == [
        _MAIN_RESOLVE[1],
        '[ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" = "$(cd "$MAIN_CHECKOUT" && pwd -P)" ] || {',
    ], "--show-toplevel may only ask about the first entry, or be the other side of the comparison"
    for name in ("in-place", "base"):
        assert fences[name].rstrip().endswith("exit 1; }"), f"the {name} gate no longer stops"
    ignore = [shlex.split(l) for l in fences["ignore"].splitlines() if "check-ignore" in l and l.startswith("git")]
    assert ignore == [["git", "-C", "$MAIN_CHECKOUT", "check-ignore", "-q", ".claude/worktrees/"]]
    for banned in (">>", "info/exclude", ".gitignore", "tee", "config"):
        assert banned not in fences["ignore"], f"the ignore check writes a file ({banned})"


def test_i43_done_quotes_the_2b_sentence() -> None:
    quote = "perform all work inside `$WORKTREE_PATH`"
    assert quote in read_skill("skills/project-done/SKILL.md")
    assert "After this, " + quote + "." in _I43_START_2B, "project-done quotes a sentence 2-B no longer says"


@pytest.mark.parametrize("name", sorted(_I43_SCENARIOS))
def test_i43_start_fences_behave(name: str, tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    failures = _I43_SCENARIOS[name](_i43_start_fences()[name], tmp_path)
    assert not failures, f"the {name} fence:\n" + "\n".join(failures)


_I43_MUTANT_CATCHERS = {
    "in-place compares against the CWD": "in-place",
    "in-place does not stop": "in-place",
    "base asks the CWD": "base",
    "base does not stop": "base",
    "ignore without the slash": "ignore",
    "ignore asks the CWD": "ignore",
    "ignore writes .gitignore": "ignore",
    "fallback adds from the CWD": "fallback",
    "fallback tracks the undeclared base": "fallback",
    "fallback prefers a stale local branch": "fallback",
    "fallback keeps origin/": "fallback",
    "fallback fetches without a refspec": "fallback",
    "fallback fetches before the cached ref": "fallback",
    "fallback prints a relative path": "fallback",
    "fallback reports a failed add": "fallback",
}


@pytest.mark.parametrize("mutant", sorted(_I43_MUTANT_CATCHERS))
def test_i43_scenarios_reject_each_mutant(mutant: str, tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    mutants = _i43_mutants(_i43_start_fences())
    assert set(mutants) == set(_I43_MUTANT_CATCHERS)
    kind, fence = mutants[mutant]
    assert kind == _I43_MUTANT_CATCHERS[mutant]
    assert _I43_SCENARIOS[kind](fence, tmp_path), f"no {kind} scenario notices the mutant {mutant!r}"


def test_i43_fences_stop_where_the_main_checkout_is_unresolved(tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not installed on this host")
    tmp = tmp_path.resolve()
    env = _i50_repos(tmp)
    fences = _i43_start_fences()
    fills = {
        "base": {"<project default base>": "main"},
        "fallback": {"<project>": "p", "<id>": "9", "<branch-name>": "feat/issue-9-y", "<base_branch, or empty>": ""},
    }
    for name, fence in fences.items():
        r = _i43_sh(_i43_fill(fence, **fills.get(name, {})), tmp / "bare-wt", env)
        assert r.returncode != 0 and r.stdout.strip() == "could not resolve the main checkout", (name, r.stdout)
    assert not (tmp / "bare-wt" / ".claude").exists() and not (tmp / "bare.git" / ".claude").exists()

    r = _i43_sh(_i43_fill(fences["fallback"], **fills["fallback"]), tmp / "super" / "sub", env)
    assert r.returncode == 0, r.stderr
    assert (tmp / "super" / "sub" / ".claude" / "worktrees" / "p-issue-9").is_dir(), "the submodule row moved"


def test_i43_iterate_hands_the_checks_to_start() -> None:
    text = _iterate_skill()
    for gone in ("project-start <id> worktree", "check-ignore", "branch --show-current"):
        assert gone not in text, f"iterate still carries {gone!r}; the Phase 3 checks live in project-start 1-C"
    assert_whole_line(text, _I43_ITERATE_ANCHOR)
    assert_whole_line(text, _G_REENTRY[-1])
    assert "Phase 3 사전 확인" in _G_REENTRY[-1], "the re-entry line no longer names the checks the anchor defines"


def test_i43_surfaces_name_the_new_default() -> None:
    lines = [l.strip() for l in read_skill(CODEX_REFERENCE).splitlines()]
    assert lines.count("$project-start <issue-id> [in-place] [adr]") == 1
    assert not [l for l in lines if l.startswith("$project-start") and "[worktree]" in l]
    assert_whole_line(read_skill("README.md"), _I43_README_ROW)
    done = read_skill("skills/project-done/SKILL.md")
    assert "after `project-start` in worktree mode (the default) every step runs with a linked worktree as CWD" in done
    assert "project-start … worktree" not in done


# --------------------------------------------------------------------------
# #45 — the plan on the tracker: a character limit with a fixed-format
# summary, link mode posting on Step 2's yes, and a revision path
#
# `project-issue` posts a plan three ways — a create body, a link-mode
# comment, a revision comment — and `## Plan Body Rules` is the one rule for
# all three, applied to a tracker only when it has a row in that table. The
# numbers live in `harness_core.plan_body.LIMITS` too, and the first test
# here holds the two together. The fences run against a fake tracker that
# keeps state: a post adds a comment and a read prints what is there, so a
# fence that skips its read-back cannot report "posted" by accident.
#
# The Jira paths are sunset and stay byte-for-byte as 6359fd4 had them.
# Helpers carry an `_i45_` prefix (see the #40 name-uniqueness test).
# --------------------------------------------------------------------------

_I45_RULES_INTRO = "A plan reaches the tracker three ways: as a new issue's body (Step 6), as a comment on the issue it is linked to (Step 1-L item 5), and as a revision comment later (Step 1-R). One rule covers all three, and it applies only to a tracker with a row in this table:"
_I45_ROW_GITHUB = '| GitHub | 65,536 | Documented: the API refuses an issue or comment body over 65,536 characters. Not measured here, and whether GitHub counts code points or UTF-16 units is unverified. |'
_I45_ROW_FORGEJO = "| Forgejo | 65,536 | Measured on a Forgejo 15 instance (2026-09-26): a 65,536-character comment was accepted and read back intact. The server's own ceiling was not probed; this is the cap the rule sets. |"
_I45_RULE_CONSTANT = '- `harness_core.plan_body.LIMITS` holds the same numbers, and a test compares the two.'
_I45_RULE_NO_ROW = '- A tracker without a row has no plan body rules: its create body, its link-mode comment question and its comment command stay as they were, and Step 1-R stops.'
_I45_RULE_UNIT = '- Length is counted in characters of the UTF-8 text, never in bytes. A Korean plan is about three bytes a character, so a byte count would send a plan well inside the limit to the summary.'
_I45_RULE_BODY = '- A body within the limit is the plan file itself, byte for byte. A body over it is a fixed-format summary: the frontmatter, the title, a line saying it is a summary, `Intent Summary` in full, the first line of each `Non-Goals` and `Drift Guards` item, the `Task Cards` titles, the `Definition of Done` checklist, and a last line naming the local file with the full plan and its size. The summary is extracted mechanically, so the same plan always gives the same bytes.'
_I45_RULE_NO_CUT = '- A summary that is itself over the limit is never cut to fit: nothing is posted, and the step reports why.'
_I45_RULE_MARKER = "- Every comment starts with a marker line, `<!-- plan-<id> rev:<rev> -->`, where `<rev>` is the first 8 hex digits of the plan file's sha1, and the marker counts toward the limit. A create-mode body carries no marker, because it is the plan as written."
_I45_RULE_ONCE = '- The same content is never posted twice. Before posting, the issue body and comments are read, and the post is skipped when one of them starts with this marker line, or is this plan (or its create-mode summary) as a whole — an issue created from this plan. Each body and comment is compared on its own and in full, so a revision that only drops lines from the end is still posted.'
_I45_RULE_READ = '- A failed read is not an empty one. When the read before posting fails, nothing is posted and the comment is 미반영, and the fence exits 1. For these reads the exit code is the evidence, measured on Forgejo: an issue with no comments prints nothing and exits 0, and an issue that does not exist exits 1. Whether `gh issue view --json comments` returns every comment of a long thread is unverified.'
_I45_RULES_FENCES = 'The check fence reads the issue and prints what a comment would be — `KIND=full|summary CHARS=<n> LIMIT=<n> REV=<rev>`, or `SEEN=<why>` with exit 3 when it is already there — and posts nothing. The post fence posts it: `<rev>` is the `REV=` value the approval screen showed, so a plan edited after that yes is refused instead of posted, and its last line is `COMMENT=posted`, `COMMENT=skipped` or `COMMENT=미반영`. Both find `plan-<id>.md` in the main checkout from `<id>` alone. **Run each fence as one shell invocation** — later lines read the variables earlier ones set.'
_I45_INSTRUCTIONS_REVISION = '- With `--issue <id>` and no `<plan-path>`, go straight to Step 1-R: Steps 1, 1-L and 2–8 do not run, and the flow ends at Step 9.'
_I45_USAGE_REVISION = '- **Given alone, when `plan-<id>.md` already exists** — revision mode: that plan is posted to `<id>` again as a new comment; Step 1-R below runs.'
_I45_L2_POINTER = '- On a tracker with a row in `## Plan Body Rules`, to post that existing plan to `<id>` again instead, run `project-issue --issue <id>` with no plan path (Step 1-R).'
_I45_L4_SCREEN = "- On a tracker with a row in `## Plan Body Rules`, first print the comment line for Step 2's screen, and for any screen that carries Step 2's screen in its place. `<draft-plan-path>` is the path Step 1 printed, and the `REV=` value is the `<rev>` item 5 posts:"
_I45_L4_ONELINER = "python -m harness_core.plan_body '<issue_tracker>' '<draft-plan-path>' --issue '<id>' --dry-run"
_I45_L4_REFUSED = '- If it refuses because even the summary is over the limit, the screen carries that refusal as its comment line, the question is the link-only form, and item 5 reports the comment as 미반영.'
_I45_STEP2_ROW = 'On a tracker with a row in `## Plan Body Rules`, the link screen also carries the comment line Step 1-L item 4 printed, and one yes answers both:'
_I45_STEP2_COMMENT = 'comment: plan-<id>.md after the rename — <KIND>, <CHARS>/<LIMIT> characters, rev <REV>'
_I45_STEP2_QUESTION = 'Are the Intent Summary and base branch correct? Link this file to #<id> and post it as a comment? [yes/no]'
_I45_STEP2_FRONTMATTER = '> Plan frontmatter (`base_branch`/`parent_issue`) is propagated to the issue without any extra work: Step 6 uploads the entire plan file as the issue body with `--body-file` — or, over the limit, a summary that keeps the frontmatter (`## Plan Body Rules`) — and Step 8 renames without changing content, preserving frontmatter. Title inference (`--title`) and type/label inference use a frontmatter-aware parser, so the leading `---` block does not affect them.'
_I45_R_INTRO = 'Posts `plan-<id>.md` to issue `<id>` again, as a new comment, after the plan changed. Nothing is created or renamed, and the issue body stays as it is.'
_I45_R_1 = "1. Validate the id with Step 1-L item 1's command."
_I45_R_2 = "2. Stop when there is no `plan-<id>.md`, as `## Usage` says. Step 1-L item 2's command exits non-zero exactly when the plan exists, so here its exit 0 is the stop."
_I45_R_3 = '3. Stop when the tracker has no row in `## Plan Body Rules`: revision mode is those rules and nothing else.'
_I45_R_4 = "4. Read the issue with Step 1-L item 3's command, and judge it by the same content rule."
_I45_R_7 = '7. On yes, run the post fence with `<rev>` from the screen and report its `COMMENT=` line, then go to Step 9.'
_I45_R_SEEN = '- `SEEN=` means this revision, or this plan as the issue body, is already there: post nothing, and report the comment as skipped.'
_I45_R_TOO_LARGE = '- A refusal because even the summary is over the limit is reported as 미반영.'
_I45_R_5 = '5. Run the check fence in `## Plan Body Rules`.'
_I45_R_REVISION = 'revision: plan-<id>.md rev <REV> — <KIND>, <CHARS>/<LIMIT> characters'
_I45_R_QUESTION = 'Post this revision of plan-<id>.md to #<id> as a comment? [yes/no]'
_I45_R_6 = '6. Otherwise show the screen and ask:'
_I45_CREATE_QUOTE = "- The GitHub and Forgejo create fences take `<draft-plan-path>` in single quotes, as Step 1 requires: inside double quotes a `$(...)` or backtick in the path would run. A path that contains `'` is not substituted at all — stop and report it."
_I45_CREATE_BODY = '- On those two trackers the fence writes the body `## Plan Body Rules` chooses to `BODY_FILE` — the plan itself within the limit, else the summary — and prints its `KIND=` line for Step 9. `BODY_FAILED=1` means nothing was created: even the summary is over the limit, or the module could not run. It is not a failed create, so no create recovery applies; report it and stop.'
_I45_FORGEJO_BODY_FAILED = '- `BODY_FAILED=1` — 생성 호출 전에 멈췄으니 이슈는 **만들어지지 않았다**. 요약조차 한도를 넘었거나 모듈이 돌지 않은 것이다. 생성 실패가 아니므로 아래 두 복구를 타지 않고, 원인을 보고하고 멈춘다.'
_I45_OUT_BODY = '- the body, on a tracker with a row in `## Plan Body Rules`: the plan in full, or the summary put in its place with the full size and the limit — the `KIND=` line the create fence printed'
_I45_OUT_COMMENT_ROW = '- the comment result from Step 1-L, on a tracker with a row in `## Plan Body Rules`: the `COMMENT=` line of the post fence — posted (full or summary, with where it can be seen), skipped because this revision or this plan was already there, or 미반영 with its reason. For 미반영, include `project-issue --issue <id>`, which posts it later — except when even the summary is over the limit, which no later run posts until the plan is shorter.'
_I45_OUT_REVISION = 'In revision mode the output is the existing issue with the word "revision", the revision and its body kind (`KIND=`, `CHARS=`, `LIMIT=`), and the comment result — posted, skipped with its reason, or 미반영 with its reason and `project-issue --issue <id>` to post it later (not for a summary over the limit).'
_I45_LANG_GUARD = "The one exception is a plan over the tracker's limit: `## Plan Body Rules` puts a fixed-format summary in its place, extracted from the plan's own words."
_I45_TRIGGER = '- The user invokes `project-issue --issue <id>` with no plan path, or asks to post a revised `plan-<id>.md` to its issue'
_I45_DESCRIPTION = 'description: Register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as a ticket in the issue tracker, then rename it to `plan-<id>.md`. With `--issue <id>`, link the draft to an issue that already exists instead of creating one; with `--issue <id>` alone, post a revised `plan-<id>.md` to its issue as a new comment.'
_I45_GITHUB_CHECK = (
    'SEEN="$(mktemp)" || exit 1',
    'trap \'rm -f "$SEEN"\' EXIT',
    'gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'python -m harness_core.plan_body github --issue \'<id>\' --seen "$SEEN" --dry-run',
)
_I45_GITHUB_POST = (
    'SEEN="$(mktemp)" || exit 1',
    'BODY_FILE="$(mktemp)" || exit 1',
    'trap \'rm -f "$SEEN" "$BODY_FILE"\' EXIT',
    'gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read failed)"; exit 1; }',
    'python -m harness_core.plan_body github --issue \'<id>\' --expect-rev \'<rev>\' --seen "$SEEN" --out "$BODY_FILE"',
    'RC=$?',
    '[ "$RC" = 3 ] && { echo "COMMENT=skipped"; exit 0; }',
    '[ "$RC" = 0 ] || { echo "COMMENT=미반영 (no body)"; exit 1; }',
    'gh issue comment "<id>" --body-file "$BODY_FILE"',
    'gh issue view "<id>" --json body,comments >| "$SEEN" || { echo "COMMENT=미반영 (read-back failed)"; exit 1; }',
    'python -m harness_core.plan_body github --issue \'<id>\' --expect-rev \'<rev>\' --seen "$SEEN" --dry-run > /dev/null',
    '[ "$?" = 3 ] && echo "COMMENT=posted" || { echo "COMMENT=미반영"; exit 1; }',
)
_I45_GITHUB_HARNESS_CREATE = (
    "DRAFT_PLAN='<draft-plan-path>'",
    'BODY_FILE="$(mktemp)" || exit 1',
    'trap \'rm -f "$BODY_FILE"\' EXIT',
    'BODY="$(python -m harness_core.plan_body github "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }',
    'printf \'%s\\n\' "$BODY"',
    '<harness_cli> create-issue \\',
    '  --title "<plan title>" \\',
    '  --body-file "$BODY_FILE" \\',
    '  --type "<Type>" \\',
    '  --label "<area tag>" \\',
    '  --priority "<Priority option>" \\',
    '  --size "<Size option>"',
)
_I45_GITHUB_GH_CREATE = (
    "DRAFT_PLAN='<draft-plan-path>'",
    'BODY_FILE="$(mktemp)" || exit 1',
    'trap \'rm -f "$BODY_FILE"\' EXIT',
    'BODY="$(python -m harness_core.plan_body github "$DRAFT_PLAN" --out "$BODY_FILE")" || { echo "BODY_FAILED=1"; exit 1; }',
    'printf \'%s\\n\' "$BODY"',
    'gh issue create \\',
    '  --title "<plan title>" \\',
    '  --body-file "$BODY_FILE" \\',
    '  --type "<Type>" \\',
    '  --label "<area tag>"',
)
# Byte-for-byte what 6359fd4 carried: the Jira paths are sunset, and #45 leaves them alone.
_I45_JIRA_CREATE = (
    '### Jira (`issue_tracker: jira`)',
    '```bash',
    'DRAFT_PLAN="<draft-plan-path>"',
    'jira issue create \\',
    '--project "<jira_project>" \\',
    '--type "<Type>" \\',
    '--summary "<plan title>" \\',
    '--template "$DRAFT_PLAN" \\',
    '--no-input \\',
    '--raw',
    '```',
    '- **`jira issue create` has no `--description` flag.** Measured against the installed CLI (1.7.0): the body flags it accepts are `-b,--body` and `-T,--template`. Cobra aborts on an unknown flag, so a `--description` form does not degrade — it dies on the first call.',
    '- **`--template` closes a second problem at the same time**: it hands over the file instead of expanding the plan body on a command line, and plan bodies are full of backticks and `$`.',
    "- ★ **`-b/--body` wins over `--template`** (the CLI's own `EXAMPLES` say so). If someone later adds `-b` for convenience, the template is ignored **without a word** — the same silent precedence this skill guards against elsewhere.",
    '- **Pass the type inferred in Step 3.** The keyword matching in that step reads the plan, not the tracker, so running it on this path is sound even though its heading says "GitHub only". What is *not* portable is the vocabulary it emits: `Bug` / `Feature` / `Task` are GitHub\'s names, and Jira issue types are defined per project — `Feature` is not one of Jira\'s defaults. Map the inferred name onto a type the target project actually defines, the same way the GitHub path requires a type the repository defines. Do not hardcode a type in this call, and do not send an unmapped one.',
    '- **`--raw` returns the API response as JSON.** Read the issue key out of that response — for example `SYN-42`. Which field carries it is **not verified here** (see the limitation below), so do not write a field name into this document as though it were confirmed.',
    '- **`--no-input` is the flag that keeps this call unattended, and it is required.** It suppresses the prompts for non-required fields, the description editor among them; drop it and `--template` alone still opens `$EDITOR` pre-filled with the file, which blocks an unattended run indefinitely. Both flags are load-bearing and neither substitutes for the other.',
    'Then read the issue back before reporting anything about it, using the key from that response as `<TICKET_ID>` — the same name Step 8 consumes:',
    '```bash',
    'jira issue view "<TICKET_ID>" --raw',
    '```',
    'Compare the summary, type and project on the response with what was sent. This read-back stays **inside this section** — Step 7 is the GitHub path and is not generalized to cover other trackers.',
    "> Limitation: this skillset's own repo has no Jira project. Both calls above were checked against the installed CLI's flag surface and this document's internal consistency, and neither has been executed against a live Jira. Anything reported from this path should carry that qualification rather than read as verified.",
)
_I45_JIRA_COMMENT = (
    '- **Jira** — a positional body argument would silently win over `--template`, so never add one.',
    'Not executed against a live Jira, like every Jira call in this skill:',
    '```bash',
    'jira issue comment add "<id>" --template \'<plan-file>\' --no-input',
    '```',
)
# The #40 substitution paragraph as 6359fd4 had it; #45 rewrote only its last clause.
_I45_STEP2_BEFORE = "From `project-iterate`, Phase 1's approval is this step's confirmation only when that same run's Phase 1 screen carried this step's screen as written above — the create or link form that matches the mode, down to its question line — and the user answered yes; ask this step again instead if the plan file was edited after that yes (review fixes included), Step 1 resolved a different path than the screen showed, the Step 1-L read returns a title or state other than the screen's, this run had no Phase 1 approval (re-entry at Phase 2), or this skill runs on its own. Steps 1 and 1-L still run either way, so a refusal after that yes costs an approval but never bypasses a check, and the Step 1-L comment question is still asked on its own."
_I45_L5_ROW = "- On a tracker with a row in `## Plan Body Rules`, Step 2's yes already covers the comment: run that section's post fence with `<rev>` — the `REV=` value on the screen that received the yes, never a new run of item 4 — and report the `COMMENT=` line it prints. Nothing is asked again."
_I45_L5_ASK = '- On a tracker without a row, ask on its own — `Post plan-<id>.md to #<id> as a comment? [yes/no]` — separately from Step 2.'
_I45_L5_OWN_YES = '- On a tracker without a row, the comment is posted only on its own yes; a no is not an error, because the local `plan-<id>.md` is the canonical plan either way.'
_I45_L5_RECOVERY = '- If the issue body read in item 3 is the same text as the draft, the body already is this plan (a create-mode Step 8 failure being recovered): do not ask, and report the comment as skipped.'
_I45_FJ_REPO = '- The Forgejo comment takes the repository in the issue argument: `issue comment` has no `-r`, and its `-R` names a git remote. Success prints nothing, so the read-back is the only evidence, as in `project-done` Step 9.'
_I45_FJ_QUOTING = "- `fj` quotes every line of a body or comment with `> ` and wraps the lines between them in U+2068/U+2069; the module splits a Forgejo read into one entry per run of quoted lines, and takes GitHub's `--json body,comments` output as it is. The reads write with `>|` so a shell with `noclobber` set can still overwrite the file `mktemp` made."


import json

_I45_DRAFT = "DRAFT_PLAN='<draft-plan-path>'"
_I45_BODY_FILE = 'BODY_FILE="$(mktemp)" || exit 1'
_I45_BODY_TRAP = "trap 'rm -f \"$BODY_FILE\"' EXIT"
_I45_BODY = 'BODY="$(python -m harness_core.plan_body {tracker} "$DRAFT_PLAN" --out "$BODY_FILE")" || {{ echo "BODY_FAILED=1"; exit 1; }}'

# Every line of project-issue that names Jira, exactly as 6359fd4 had them.
_I45_JIRA_LINES = (
    '- Keywords such as "register issue", "create ticket", "upload to GitHub", or "upload to Jira"',
    '"jira": r"[A-Z][A-Z0-9_]*-[1-9][0-9]*",',
    '- **Jira**:',
    'jira issue view "<id>" --raw',
    '- **Jira** — a positional body argument would silently win over `--template`, so never add one.',
    'Not executed against a live Jira, like every Jira call in this skill:',
    'jira issue comment add "<id>" --template \'<plan-file>\' --no-input',
    '### Jira (`issue_tracker: jira`)',
    'jira issue create \\',
    '--project "<jira_project>" \\',
    '- **`jira issue create` has no `--description` flag.** Measured against the installed CLI (1.7.0): the body flags it accepts are `-b,--body` and `-T,--template`. Cobra aborts on an unknown flag, so a `--description` form does not degrade — it dies on the first call.',
    '- **Pass the type inferred in Step 3.** The keyword matching in that step reads the plan, not the tracker, so running it on this path is sound even though its heading says "GitHub only". What is *not* portable is the vocabulary it emits: `Bug` / `Feature` / `Task` are GitHub\'s names, and Jira issue types are defined per project — `Feature` is not one of Jira\'s defaults. Map the inferred name onto a type the target project actually defines, the same way the GitHub path requires a type the repository defines. Do not hardcode a type in this call, and do not send an unmapped one.',
    'jira issue view "<TICKET_ID>" --raw',
    "> Limitation: this skillset's own repo has no Jira project. Both calls above were checked against the installed CLI's flag surface and this document's internal consistency, and neither has been executed against a live Jira. Anything reported from this path should carry that qualification rather than read as verified.",
    '`<ISSUE_NUMBER>` on GitHub and Forgejo, `<TICKET_ID>` on Jira (for example `plan-SYN-42.md`). Do not',
    '- issue number / URL, or Jira ticket ID',
)

_I45_FAKE_TRACKER = r'''
import json, os, sys
from pathlib import Path
tool, args = sys.argv[1], sys.argv[2:]
store = Path(os.environ["STORE"])
(store / "comments").mkdir(parents=True, exist_ok=True)
with open(store / "calls", "a", encoding="utf-8") as log:
    log.write(json.dumps([tool, *args]) + "\n")
comments = sorted((store / "comments").iterdir(), key=lambda p: int(p.name))
def read(p):
    return p.read_text(encoding="utf-8")
def quoted(text):
    return "".join(("> " + l if l else "> ") + "\n" for l in text.rstrip("\n").split("\n"))
if "--body-file" in args:
    body = Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8")
    if "create" in args:
        (store / "created").write_text(body, encoding="utf-8")
        print("https://github.test/o/r/issues/41")
    elif os.environ.get("FAKE_POST") != "drop":
        (store / "comments" / str(len(comments))).write_text(body, encoding="utf-8")
    sys.exit(0)
if "view" in args:
    # FAKE_READ: "fail" fails every read; "fail-comments" only Forgejo's comments
    # surface; "fail-after-post" every read once a comment was posted.
    mode = os.environ.get("FAKE_READ", "")
    posted = any("--body-file" in json.loads(c) for c in (store / "calls").read_text(encoding="utf-8").splitlines())
    if mode == "fail" or (mode == "fail-comments" and args[-1] == "comments") or (mode == "fail-after-post" and posted):
        print("Error: not found", file=sys.stderr)
        sys.exit(1)
    body = read(store / "body") if (store / "body").exists() else "사람이 쓴 본문\n"
    if tool == "gh":
        assert args[args.index("--json") + 1] == "body,comments" and "--jq" not in args, args
        print(json.dumps({"body": body, "comments": [{"body": read(c)} for c in comments]}))
    elif args[-1] == "comments":
        for c in comments:
            sys.stdout.write("⁨⁩⁨W⁩⁨⁩ said:\n" + quoted(read(c)) + "\n\n")
    else:
        sys.stdout.write("⁨t⁩ #⁨45⁩\nBy ⁨me⁩ — Open\n\n" + quoted(body) + "\n")
    sys.exit(0)
sys.exit("fake %s: unexpected call %r" % (tool, args))
'''

_I45_PLAN = "# Plan: 작은 플랜\n\n## Intent Summary\n의도.\n\n## Definition of Done\n- [ ] 된다\n"

# Tokens #50 keeps to the canonical main-checkout block; no #45 fence resolves it itself.
_I45_MAIN_TOKENS = (
    "worktree list", "rev-parse", "show-toplevel", "git -C", "main_worktree_root",
    ".task/plan", '".task" / "plan"',
)


def _i45_rules() -> str:
    text = _issue_skill()
    assert text.count("\n## Plan Body Rules\n") == 1, "project-issue has no single Plan Body Rules section"
    return text.split("\n## Plan Body Rules\n", 1)[1].split("\n## Instructions\n", 1)[0]


def _i45_fences() -> dict[str, list[str]]:
    rules = _i45_rules()
    return {
        (tracker, kind): _i40_fence_after(rules, f"**{label}** {kind}:")
        for tracker, label in (("github", "GitHub"), ("forgejo", "Forgejo"))
        for kind in ("check", "post")
    }


def _i45_env(tmp_path: Path, **extra: str) -> tuple[dict[str, str], Path, Path]:
    """Fake `fj` and `gh` over one store, a `python` for the module, and a main checkout.

    The store is state, not a script: a post adds a comment and a read prints
    what is there, so "posted" is true only when the read-back finds the post.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = tmp_path / "fake_tracker.py"
    fake.write_text(_I45_FAKE_TRACKER, encoding="utf-8")
    for tool in ("fj", "gh"):
        shim = bin_dir / tool
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" {tool} "$@"\n')
        shim.chmod(0o755)
    for name in ("python", "python3"):
        shim = bin_dir / name
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        shim.chmod(0o755)
    main = tmp_path / "main"
    (main / ".task" / "plan").mkdir(parents=True, exist_ok=True)
    store = tmp_path / "store"
    (store / "comments").mkdir(parents=True, exist_ok=True)
    tmp = tmp_path / "tmp"  # mktemp writes here, so a leaked temp file is visible to the test
    tmp.mkdir(exist_ok=True)
    # macOS mktemp with no template ignores TMPDIR, so the fences' mktemp is a shim.
    shim = bin_dir / "mktemp"
    shim.write_text(f'#!/bin/sh\nexec /usr/bin/mktemp "{tmp}/tmp.XXXXXXXX"\n')
    shim.chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "STORE": str(store), "TMPDIR": str(tmp), **extra}
    return env, main, store


def _i45_script(fence: list[str], **values: str) -> str:
    script = "\n".join(fence)
    for placeholder, value in {
        "<forgejo_host>": "forge.test", "<forgejo_repo>": "o/r", "<id>": "45", **values,
    }.items():
        script = script.replace(placeholder, value)
    assert not re.search(r"<[^<>\n]*>", script), f"a placeholder is left for the shell to parse:\n{script}"
    return script


def _i45_run(shell: str, script: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([shell, "-c", script], cwd=cwd, env=env, capture_output=True, text=True)


def _i45_calls(store: Path) -> list[list[str]]:
    calls = store / "calls"
    return [json.loads(c) for c in calls.read_text(encoding="utf-8").splitlines()] if calls.exists() else []


def _i45_posts(store: Path) -> list[list[str]]:
    return [c for c in _i45_calls(store) if "comment" in c and "--body-file" in c]


# The one post each tracker makes, as argv, with the body file masked.
_I45_POST_ARGV = {
    "github": ["gh", "issue", "comment", "45", "--body-file", "<body>"],
    "forgejo": ["fj", "-H", "forge.test", "issue", "comment", "o/r#45", "--body-file", "<body>"],
}


def _i45_plan(main: Path, text: str = _I45_PLAN) -> str:
    from harness_core.plan_body import revision
    plan = main / ".task" / "plan" / "plan-45.md"
    plan.write_text(text, encoding="utf-8")
    return revision(plan.read_bytes())


def test_i45_rules_table_matches_the_module() -> None:
    from harness_core.plan_body import LIMITS
    rules = _i45_rules()
    rows = [l.strip() for l in rules.splitlines() if l.startswith("| ") and not l.startswith("| Tracker")]
    assert rows == [_I45_ROW_GITHUB, _I45_ROW_FORGEJO], f"the limit table changed: {rows}"
    table = {r.split("|")[1].strip().lower(): int(r.split("|")[2].strip().replace(",", "")) for r in rows}
    assert table == LIMITS, f"the table and harness_core.plan_body.LIMITS disagree: {table} vs {LIMITS}"
    assert "jira" not in table


def test_i45_rules_lines_are_pinned() -> None:
    rules = _i45_rules()
    for line in (
        _I45_RULES_INTRO, _I45_RULE_CONSTANT, _I45_RULE_NO_ROW, _I45_RULE_UNIT, _I45_RULE_BODY,
        _I45_RULE_NO_CUT, _I45_RULE_MARKER, _I45_RULE_ONCE, _I45_RULE_READ, _I45_RULES_FENCES,
        _I45_FJ_REPO, _I45_FJ_QUOTING,
    ):
        assert_whole_line(rules, line)
    assert not [l for l in rules.splitlines() if l.startswith("#")], (
        "a heading inside Plan Body Rules — a `### Forgejo` here moves every _forgejo_section() slice"
    )
    order = [l.strip() for l in _issue_skill().splitlines() if l.startswith("## ")]
    assert order.index("## Plan Body Rules") == order.index("## Instructions") - 1


def test_i45_no_second_limit_number() -> None:
    """A second limit written anywhere else in the skill would drift from the table."""
    number = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{5,}\b|KiB|MiB", re.I)
    context = re.compile(r"limit|한도|character|문자|KiB|MiB", re.I)
    stray = [
        l.strip() for l in _issue_skill().splitlines()
        if number.search(l) and context.search(l) and l.strip() not in (_I45_ROW_GITHUB, _I45_ROW_FORGEJO)
    ]
    assert not stray, "a limit is stated outside the Plan Body Rules table:\n" + "\n".join(stray)


def test_i45_rules_fences_are_pinned() -> None:
    fences = _i45_fences()
    assert tuple(fences["github", "check"]) == _I45_GITHUB_CHECK
    assert tuple(fences["github", "post"]) == _I45_GITHUB_POST
    forgejo = tuple(_GOLDEN_ISSUE_LINK_FORGEJO)
    assert tuple(fences["forgejo", "check"]) == forgejo[2:forgejo.index("```", 2)]
    # The two trackers differ only in their read and post commands.
    for kind in ("check", "post"):
        gh = [l for l in fences["github", kind] if not l.startswith(("gh ", "fj "))]
        fj = [l for l in fences["forgejo", kind] if not l.startswith(("gh ", "fj "))]
        assert [l.replace(" github ", " forgejo ") for l in gh] == fj, f"the {kind} fences drifted apart"


_I45_SCENARIOS = {
    # scenario: (env, last line, exit code, posts)
    "empty": ({}, "COMMENT=posted", 0, 1),
    "older": ({}, "COMMENT=posted", 0, 1),
    "shorter": ({}, "COMMENT=posted", 0, 1),
    "same": ({}, "COMMENT=skipped", 0, 0),
    "body": ({}, "COMMENT=skipped", 0, 0),
    "read_fail": ({"FAKE_READ": "fail"}, "COMMENT=미반영 (read failed)", 1, 0),
    "readback_fail": ({"FAKE_READ": "fail-after-post"}, "COMMENT=미반영 (read-back failed)", 1, 1),
    "drop": ({"FAKE_POST": "drop"}, "COMMENT=미반영", 1, 1),
    "rev": ({}, "COMMENT=미반영 (no body)", 1, 0),
}


@pytest.mark.parametrize("tracker", ["github", "forgejo"])
@pytest.mark.parametrize("scenario", list(_I45_SCENARIOS))
def test_i45_post_fence_against_a_stateful_tracker(tracker: str, scenario: str, tmp_path: Path) -> None:
    from harness_core.plan_body import marker
    extra, expected, code, n_posts = _I45_SCENARIOS[scenario]
    env, main, store = _i45_env(tmp_path, **extra)
    plan = _I45_PLAN + "\n## Validation Plan\n- 끝에 붙은 절\n" if scenario == "shorter" else _I45_PLAN
    rev = _i45_plan(main)
    if scenario == "same":
        (store / "comments" / "0").write_text(f"{marker('45', rev)}\n\n{_I45_PLAN}", encoding="utf-8")
    if scenario == "older":
        (store / "comments" / "0").write_text(f"{marker('45', '00000000')}\n\n옛 플랜\n", encoding="utf-8")
    if scenario == "shorter":  # the posted revision had one more section; this one only drops it
        (store / "comments" / "0").write_text(f"{marker('45', '00000000')}\n\n{plan}", encoding="utf-8")
    if scenario == "body":
        (store / "body").write_text(_I45_PLAN, encoding="utf-8")
    before = len(list((store / "comments").iterdir()))

    fence = _i45_fences()[tracker, "post"]
    ran = _i45_run("bash", _i45_script(fence, **{"<rev>": "deadbeef" if scenario == "rev" else rev}), env, main)
    last = ran.stdout.strip().splitlines()[-1] if ran.stdout.strip() else ""
    assert (last, ran.returncode) == (expected, code), f"{scenario}: {ran.stdout!r} {ran.stderr!r}"
    posts = _i45_posts(store)
    assert len(posts) == n_posts, f"{scenario}: expected {n_posts} posts, got {posts}"
    for post in posts:
        assert post[:-1] + ["<body>"] == _I45_POST_ARGV[tracker], f"the post argv changed: {post}"
    if expected == "COMMENT=posted":
        new = sorted((store / "comments").iterdir(), key=lambda p: int(p.name))[before]
        assert new.read_text(encoding="utf-8") == f"{marker('45', rev)}\n\n{_I45_PLAN}"
    assert not list((tmp_path / "tmp").iterdir()), "a temp file outlived the fence"


@pytest.mark.parametrize("scenario", ["fail-comments"])
def test_i45_forgejo_post_fence_needs_both_reads(scenario: str, tmp_path: Path) -> None:
    env, main, store = _i45_env(tmp_path, FAKE_READ=scenario)
    rev = _i45_plan(main)
    ran = _i45_run("bash", _i45_script(_i45_fences()["forgejo", "post"], **{"<rev>": rev}), env, main)
    assert ran.stdout.strip().splitlines()[-1] == "COMMENT=미반영 (read failed)" and ran.returncode == 1
    assert not _i45_posts(store), "a failed comments read was taken for an empty one"


@pytest.mark.parametrize("shell", _i40_shells())
@pytest.mark.parametrize("tracker", ["github", "forgejo"])
def test_i45_post_then_repost_in_every_shell(shell: str, tracker: str, tmp_path: Path) -> None:
    env, main, store = _i45_env(tmp_path)
    rev = _i45_plan(main)
    script = _i45_script(_i45_fences()[tracker, "post"], **{"<rev>": rev})
    first = _i45_run(shell, script, env, main)
    second = _i45_run(shell, script, env, main)
    assert first.stdout.strip().splitlines()[-1] == "COMMENT=posted", first.stdout + first.stderr
    assert second.stdout.strip().splitlines()[-1] == "COMMENT=skipped", second.stdout + second.stderr
    assert len(_i45_posts(store)) == 1, "the same revision was posted twice"


@pytest.mark.parametrize("tracker", ["github", "forgejo"])
def test_i45_check_fence_posts_nothing(tracker: str, tmp_path: Path) -> None:
    from harness_core.plan_body import marker
    env, main, store = _i45_env(tmp_path)
    rev = _i45_plan(main)
    script = _i45_script(_i45_fences()[tracker, "check"])
    ran = _i45_run("bash", script, env, main)
    assert ran.returncode == 0 and ran.stdout == f"KIND=full CHARS={len(marker('45', rev)) + 2 + len(_I45_PLAN)} LIMIT=65536 REV={rev}\n"
    (store / "comments" / "0").write_text(f"{marker('45', rev)}\n\nx\n", encoding="utf-8")
    ran = _i45_run("bash", script, env, main)
    assert ran.returncode == 3 and ran.stdout == f"SEEN=revision REV={rev}\n"
    assert not _i45_posts(store)


def test_i45_create_fences_share_the_body_lines() -> None:
    text = _issue_skill()
    forgejo = _i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE)
    blocks = _fence_blocks(text)
    assert [b for b in blocks if "<harness_cli> create-issue \\" in b] == [list(_I45_GITHUB_HARNESS_CREATE)]
    assert [b for b in blocks if "gh issue create \\" in b] == [list(_I45_GITHUB_GH_CREATE)]
    for fence, tracker in ((_I45_GITHUB_HARNESS_CREATE, "github"), (_I45_GITHUB_GH_CREATE, "github"), (forgejo, "forgejo")):
        for line in (_I45_DRAFT, _I45_BODY_FILE, _I45_BODY_TRAP, _I45_BODY.format(tracker=tracker)):
            assert fence.count(line) == 1, f"a create fence lost or doubled: {line}"
        assert sum('--body-file "$BODY_FILE"' in l for l in fence) == 1
        assert not any("--body-file \"$DRAFT_PLAN\"" in l for l in fence), "a create fence still posts the draft directly"
    assert_whole_line(text, _I45_CREATE_QUOTE)
    assert_whole_line(text, _I45_CREATE_BODY)
    assert_whole_line(_forgejo_section(), _I45_FORGEJO_BODY_FAILED)


def test_i45_double_quoted_draft_path_is_left_only_in_jira() -> None:
    text = _issue_skill()
    jira = "\n".join(_stripped_lines(text, "### Jira (`issue_tracker: jira`)", "### Forgejo"))
    everywhere = [l.strip() for l in text.splitlines() if '="<draft-plan-path>"' in l]
    in_jira = [l for l in jira.splitlines() if '="<draft-plan-path>"' in l]
    assert everywhere == in_jira == ['DRAFT_PLAN="<draft-plan-path>"'], everywhere


def _i45_over_limit(intent: str = "의도.") -> str:
    return (
        "# Plan: 큰 플랜\n\n## Intent Summary\n" + intent + "\n\n## Task Cards\n\n### Task 1: 큰 태스크\n"
        + ("가나다라마바사 " * 10 + "\n") * 900
    )


@pytest.mark.parametrize("shell", _i40_shells())
def test_i45_forgejo_create_fence_posts_the_summary_over_the_limit(shell: str, tmp_path: Path) -> None:
    from harness_core.plan_body import LIMITS, create_summary
    fence = _i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE)
    draft = tmp_path / "plan-draft-big.md"
    draft.write_text(_i45_over_limit(), encoding="utf-8")
    assert len(draft.read_text(encoding="utf-8")) > LIMITS["forgejo"]
    env, log = _i40_fake_env(tmp_path, "ok")
    ran = subprocess.run([shell, "-c", _i40_script(fence, draft)], cwd=tmp_path, env=env, capture_output=True, text=True)
    out = ran.stdout.splitlines()
    assert ran.returncode == 0, ran.stderr
    assert out[:2] == ["CREATE_FAILED=0", "ISSUE_NUMBER=41"] and out[2].startswith("KIND=summary "), out
    assert Path(f"{log}.body").read_text(encoding="utf-8") == create_summary(draft.read_text(encoding="utf-8"), "forgejo")


@pytest.mark.parametrize("case", ["summary_too_large", "module_fails"])
def test_i45_forgejo_create_fence_stops_before_create(case: str, tmp_path: Path) -> None:
    fence = _i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE)
    draft = tmp_path / "plan-draft-big.md"
    draft.write_text(_i45_over_limit("가" * 70000 if case == "summary_too_large" else "의도."), encoding="utf-8")
    env, log = _i40_fake_env(tmp_path, "ok")
    if case == "module_fails":
        (tmp_path / "bin" / "python").write_text("#!/bin/sh\necho 'No module named harness_core.plan_body' >&2\nexit 1\n")
    ran = subprocess.run(["bash", "-c", _i40_script(fence, draft)], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert ran.returncode != 0 and not log.exists(), "fj issue create ran without a body"
    assert "BODY_FAILED=1" in ran.stdout.splitlines()
    assert not any(l.startswith(("CREATE_FAILED=", "ISSUE_NUMBER=")) for l in ran.stdout.splitlines()), (
        "a body failure printed create-failure lines, which send the agent to the create recovery"
    )


def test_i45_gh_create_fence_uploads_the_draft_bytes(tmp_path: Path) -> None:
    env, main, store = _i45_env(tmp_path)
    draft = main / ".task" / "plan" / "plan-draft-x.md"
    draft.write_text(f"# Plan: {_I40_HOSTILE_TITLE}\n\n본문\n", encoding="utf-8")
    script = _i45_script(list(_I45_GITHUB_GH_CREATE), **{
        "<draft-plan-path>": str(draft), "<plan title>": "t", "<Type>": "Task", "<area tag>": "BE",
    })
    ran = _i45_run("bash", script, env, main)
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines()[0].startswith("KIND=full ")
    assert (store / "created").read_bytes() == draft.read_bytes()
    assert str(draft) not in (store / "calls").read_text(encoding="utf-8"), "gh received the draft path, not the body file"
    assert not (tmp_path / "pwned").exists()


def test_i45_link_mode_screen_and_post() -> None:
    link = _link_mode()
    for line in (_I45_L2_POINTER, _I45_L4_SCREEN, _I45_L4_REFUSED, _I45_L5_ROW, _I45_L5_ASK, _I45_L5_OWN_YES, _I45_L5_RECOVERY):
        assert_whole_line(link, line)
    assert _I45_L4_ONELINER in [l.strip() for l in _fenced(link).splitlines()], "item 4 lost its screen command"
    step2 = skill_section(_issue_skill(), "**2. User Confirmation**")
    for line in (_I45_STEP2_ROW, _I45_STEP2_COMMENT, _I45_STEP2_QUESTION):
        assert_whole_line(step2, line)
    lines = [l.strip() for l in step2.splitlines()]
    assert lines.count("Are the Intent Summary and base branch correct? Link this file to #<id>? [yes/no]") == 1, (
        "the link-only question for a tracker without a row is gone"
    )
    assert lines.index(_I45_STEP2_ROW) < lines.index(_I45_STEP2_COMMENT) < lines.index(_I45_STEP2_QUESTION)
    everywhere = [l for l in _issue_skill().splitlines() if "Post plan-<id>.md to #<id> as a comment? [yes/no]" in l]
    assert [l.strip() for l in everywhere] == [_I45_L5_ASK], f"the separate comment question escaped its row-less scope: {everywhere}"


def test_i45_revision_mode() -> None:
    text = _issue_skill()
    order = _step_order(text)
    heads = [h.split(".", 1)[0] for h in order]
    assert heads[:4] == ["**1", "**1-L", "**1-R", "**2"], order
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    assert lines.index(_I45_INSTRUCTIONS_REVISION) == lines.index("## Instructions") + 1, (
        "the revision branch is not the first thing Instructions says, so Step 1 discovery runs first"
    )
    section = skill_section(text, "**1-R.")
    for line in (_I45_R_INTRO, _I45_R_1, _I45_R_2, _I45_R_3, _I45_R_4, _I45_R_5, _I45_R_SEEN,
                 _I45_R_TOO_LARGE, _I45_R_6, _I45_R_REVISION, _I45_R_QUESTION, _I45_R_7):
        assert_whole_line(section, line)
    for command in _CREATE_COMMANDS + ("rename_plan_to_issue", "gh issue comment", "issue comment '"):
        assert command not in section, f"revision mode names {command}"
    for line in (_I45_USAGE_REVISION, _I45_TRIGGER, _I45_DESCRIPTION, _I45_LANG_GUARD, _I45_STEP2_FRONTMATTER):
        assert_whole_line(text, line)


def test_i45_step2_substitution_changed_only_its_last_clause() -> None:
    cut = _I45_STEP2_BEFORE.index("and the Step 1-L comment")
    assert _I40_STEP2_SUBSTITUTE[:cut] == _I45_STEP2_BEFORE[:cut], "the #40 conditions changed"
    assert _I40_STEP2_SUBSTITUTE[cut:] == (
        "and the Step 1-L comment follows the screen: posted on that yes where the screen carried the "
        "comment line, and asked on its own where it did not."
    )


def test_i45_output_lines() -> None:
    step9 = skill_section(_issue_skill(), "**9. Output**")
    for line in (_I45_OUT_BODY, _I45_OUT_COMMENT_ROW, _GOLDEN_ISSUE_OUTPUT_COMMENT, _I45_OUT_REVISION):
        assert_whole_line(step9, line)


def test_i45_jira_is_untouched() -> None:
    text = _issue_skill()
    jira = tuple(_stripped_lines(text, "### Jira (`issue_tracker: jira`)", "### Forgejo"))
    assert jira == _I45_JIRA_CREATE, "the Jira create section changed"
    bullet = tuple(_stripped_lines(text, "- **Jira** — a positional body argument", "**1-R."))
    assert bullet == _I45_JIRA_COMMENT, "the Jira comment bullet changed"
    for block in (jira, bullet):
        for token in ("plan_body", "BODY_FILE", "rev:", "Plan Body Rules"):
            assert not any(token in l for l in block), f"a Jira path gained {token}"
    new_text = [_i45_rules(), skill_section(text, "**1-R."), *[
        v for k, v in globals().items() if k.startswith("_I45_") and isinstance(v, str)
        and k not in ("_I45_STEP2_BEFORE", "_I45_FAKE_TRACKER")
    ]]
    assert not [t for t in new_text if re.search(r"jira", t, re.I)], "a line #45 added names Jira"


def test_i45_new_fences_leave_the_main_checkout_to_the_module() -> None:
    fences = [*_i45_fences().values(), list(_I45_GITHUB_HARNESS_CREATE), list(_I45_GITHUB_GH_CREATE),
              _i40_fence_after(_forgejo_section(), _I40_CREATE_DIRECTIVE),
              _i40_fence_after(_forgejo_section(), _I40_SEARCH_DIRECTIVE), [_I45_L4_ONELINER]]
    for fence in fences:
        assert fence, "a #45 fence went missing"
        found = [(t, l) for l in fence for t in _I45_MAIN_TOKENS if t in l]
        assert not found, f"a #45 fence resolves the main checkout itself: {found}"


def test_i45_no_escape_clause_about_posting() -> None:
    """Every prose line that talks about a comment together with skipping or asking is pinned."""
    pinned = {
        _I45_TRIGGER, _I45_RULE_ONCE, _I45_RULES_FENCES, _I45_L5_ROW, _I45_L5_ASK, _I45_L5_RECOVERY,
        _I45_R_SEEN, _I40_STEP2_SUBSTITUTE, _I45_OUT_COMMENT_ROW, _GOLDEN_ISSUE_OUTPUT_COMMENT, _I45_OUT_REVISION,
    }
    words = re.compile(r"comment|코멘트|게시|post", re.I)
    escape = re.compile(r"skip|건너|생략|declin|묻|ask|no need|unless|optional|선택", re.I)
    stray = [
        line.strip() for line, in_fence in _outside_fences(_issue_skill())
        if not in_fence and words.search(line) and escape.search(line) and line.strip() not in pinned
    ]
    assert not stray, "a posting rule was stated outside the pinned lines:\n" + "\n".join(stray)


def test_i45_every_line_naming_jira_is_as_6359fd4_had_it() -> None:
    """Jira is sunset: no line of project-issue that names it is added, dropped or changed."""
    lines = tuple(l.strip() for l in _issue_skill().splitlines() if re.search(r"jira", l, re.I))
    assert lines == _I45_JIRA_LINES, "a line naming Jira changed"


@pytest.mark.parametrize("shell", [s for s in ("bash", "zsh") if shutil.which(s)])
@pytest.mark.parametrize("tracker", ["github", "forgejo"])
def test_i45_post_fence_survives_noclobber(shell: str, tracker: str, tmp_path: Path) -> None:
    """A user shell with `noclobber` set must not turn every post into 미반영."""
    env, main, store = _i45_env(tmp_path)
    rev = _i45_plan(main)
    script = "set -o noclobber\n" + _i45_script(_i45_fences()[tracker, "post"], **{"<rev>": rev})
    ran = _i45_run(shell, script, env, main)
    assert ran.stdout.strip().splitlines()[-1] == "COMMENT=posted" and ran.returncode == 0, ran.stdout + ran.stderr
