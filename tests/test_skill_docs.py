"""Contract tests for workflow skill documentation."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_skill(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
    assert "never copy a summary" in text
    # `focus` is passed through, not interpreted — that is what keeps the skill neutral.
    assert "verbatim" in text
    assert "Do not parse it" in text
    # Roles come from the project, not from this file.
    assert "Do not hardcode role names" in text
    # A missing path degrades loudly; it never silently drops.
    assert "warning, not a stop" in text
    # The report must carry the evidence that the delegation actually closed.
    assert "guideline paths actually read" in text


def test_project_start_review_requires_mutation_evidence() -> None:
    text = read_skill("skills/project-start/SKILL.md")

    assert "verified by mutation" in text
    assert "A passing test is not evidence that a guard works" in text
    # A project override must not be able to drop the duty.
    assert "not removed by a project override" in text


def test_project_start_review_path_chain_is_closed() -> None:
    """A priority chain whose last entry is conditional is not a fallback."""
    text = read_skill("skills/project-start/SKILL.md")

    assert "**8-B. Choose an execution path" in text
    assert "the last entry always applies" in text
    assert "The main agent performs each role directly" in text
    # Named tools may come and go; the procedure must not depend on one existing.
    assert "skills/dependencies.yaml" in text
    # Installed is not the same as reachable.
    assert "two questions, not one" in text
    # Never shell out to another LLM CLI to get a reviewer.
    assert "Never spawn an LLM CLI" in text
    # Roles stay separate on every path, including the fallback.
    assert "Roles stay separate on every path" in text


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
    # A plan review checks executability, not code that does not exist yet.
    assert "whether each DoD item could actually fail" in text
    # Same closed chain as project-start; no second, divergent copy of the rules.
    assert "project-start` §8-B" in text


def test_review_guidelines_reference_defines_injection() -> None:
    text = read_skill("skills/_shared/references/review-guidelines.md")

    assert "# 리뷰 가이드라인 주입 (`review_guidelines`)" in text
    # The key itself stays in the common key table so it is discoverable.
    assert "| `review_guidelines` |" in read_skill("skills/SKILL-CONFIG.md")

    # The schema the skills read.
    for token in ("common:", "roles:", "docs:", "focus:"):
        assert token in text

    # Neutrality: focus is transported, never interpreted; roles are not fixed.
    assert "`focus` 를 파싱하지 말 것" in text
    assert "역할 이름을 고정하지 말 것" in text
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
    """Parse the flat scalar-only manifest.

    Mirrors what install-skills.sh does with awk. The manifest must stay
    parseable both ways: a nested structure would break the shell reader.
    """
    text = read_skill(MANIFEST_PATH)
    try:
        import yaml

        return yaml.safe_load(text)["tools"]
    except ModuleNotFoundError:
        tools: list[dict[str, str]] = []
        for raw in text.splitlines():
            if raw.startswith("  - "):
                tools.append({})
                raw = "    " + raw[4:]
            if not raw.startswith("    ") or raw.strip().startswith("#"):
                continue
            key, sep, value = raw.strip().partition(":")
            if not sep or not tools:
                continue
            tools[-1][key.strip()] = value.strip().strip('"')
        return tools


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
    manifest = {t["id"]: t for t in _parse_manifest()}
    readme = {r["id"]: r for r in _parse_readme_prereq_table()}

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


def test_install_script_reports_prerequisites_without_gating() -> None:
    text = read_skill("install-skills.sh")

    assert "skills/dependencies.yaml" in text
    assert "installed_plugins.json" in text
    # Report only: no install command is ever executed by the script.
    assert "claude plugin install" not in text.replace(
        "run the install commands above", ""
    ), "the script must print install commands from the manifest, never run them"
    # Missing plugin database (Codex, CI) is a skip, not a finding.
    assert "prerequisites: skipped" in text
    # Field separator must not be IFS whitespace, or an empty optional field
    # collapses and shifts every field after it.
    assert "\\037" in text
    assert "IFS=$'\\t'" not in text


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
    for md in sorted((ROOT / "skills").glob("*/SKILL.md")):
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
    "project-adr": set(),
    "project-clean": {"base-branch", "worktree"},
    "project-done": {"review-guidelines", "base-branch", "hooks", "worktree"},
    "project-harness-init": {"base-branch"},
    "project-harness-update": set(),
    "project-issue": {"base-branch"},
    "project-iterate": set(),
    "project-plan": {"review-guidelines", "base-branch"},
    "project-release": {"release", "base-branch"},
    "project-release-doc": {"release"},
    "project-start": {"review-guidelines", "base-branch", "hooks", "worktree"},
}


def _declared_references(skill: str) -> set[str]:
    text = read_skill(f"skills/{skill}/SKILL.md")
    return set(re.findall(r"_shared/references/([a-z-]+)\.md", text)) - {"codex"}


def test_every_declared_reference_exists() -> None:
    """A pointer to a file that is not there is worse than no pointer."""
    dangling: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for name in re.findall(r"_shared/references/([a-z-]+)\.md", md.read_text(encoding="utf-8")):
            if not (ROOT / REFERENCE_DIR / f"{name}.md").exists():
                dangling.append(f"{md.relative_to(ROOT)} -> {name}.md")
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


def test_split_references_are_self_describing() -> None:
    """Each moved file says where it came from, so it is not read as orphaned."""
    for ref in sorted((ROOT / REFERENCE_DIR).glob("*.md")):
        if ref.name == "codex.md":
            continue
        text = ref.read_text(encoding="utf-8")
        assert "Split out of skills/SKILL-CONFIG.md" in text, ref.name
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
    for token in ("rename-tab", "set-tab", "tab name", "tab title"):
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


def test_frontend_project_coordinates_are_current() -> None:
    """`cosmos-forge` has had no commit since 2026-06-03; the FE canon is quantlab-front."""
    stale: list[str] = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "cosmos-forge" in line:
                stale.append(f"{md.relative_to(ROOT)}:{lineno}")
    assert not stale, "stale FE coordinates:\n" + "\n".join(stale)

    readme = read_skill("README.md")
    assert "quantlab-front" in readme
    # README keeps exactly one mention: the dormancy warning, which Task 4's
    # implementation contract requires so the next reader is not misled.
    assert readme.count("cosmos-forge") == 1
    assert "휴면" in readme
    assert "AGENTS.md` 도 stale" in readme


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

    assert "**11. Check CI on the PR**" in text
    assert 'Do not report "complete" while CI is unverified' in text
    # "no errors" is vacuous: a run that skipped the suite is also green.
    assert "which checks ran" in text
    assert "vacuous" in text
    # Unreadable CI is reported as unknown, never assumed green.
    assert "mark the CI state unknown rather than assuming it passed" in text
    # The final output carries the CI state, so it cannot be quietly omitted.
    assert "**12. Output**" in text
    assert "CI state:" in text
