"""Contract tests for workflow skill documentation."""

from __future__ import annotations

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
    assert "`full` review viewpoints" in text
    assert "`docs-light` review checklist" in text
    assert "review profile" in text
    assert "code, tests, build, CI, dependencies, runtime config" in text


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


def test_skill_config_defines_release_block_and_forgejo() -> None:
    text = read_skill("skills/SKILL-CONFIG.md")

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

    # forgejo is a documented lookup path with an explicit degradation rule
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
        "git merge-base --is-ancestor",
        "--sort=-v:refname",
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
        "$project-release-doc",
    ):
        assert token in text

    assert "exactly one release commit" in text
    assert "No confirmation means no mutation" in text
    assert "Do not delete already-created tags automatically" in text
    assert "instead of silently switching tools" in text


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
    assert "`$project-release`로 버전·commit·tag" in text
    assert "`$project-release-doc`으로 릴리즈/배포 문서" in text


def test_release_doc_rename_has_distinct_trigger_and_guard() -> None:
    preparation = read_skill("skills/project-release/SKILL.md")
    document = read_skill("skills/project-release-doc/SKILL.md")

    assert "name: project-release\n" in preparation
    assert "name: project-release-doc\n" in document
    assert "$project-release-doc <package> [<from>..<to>]" in document
    assert "$project-release <package> [<from>..<to>]" not in document
    assert "Do not run `cargo release`, version bumps, or tag creation" in document
