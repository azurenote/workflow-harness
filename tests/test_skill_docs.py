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
            }
        )
    return rows


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
            assert str(tool[field]).strip(), f"{tool.get('id')} has an empty `{field}`"
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
    """A pointer to a file that is not there is worse than no pointer.

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
