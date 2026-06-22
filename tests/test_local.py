"""Tests for harness_core.local module."""

import pytest
from harness_core.local import (
    find_draft_plan_file,
    rename_plan_to_issue,
    extract_plan_title,
    plan_file_for_issue,
    parse_frontmatter,
    split_frontmatter,
    extract_base_branch,
    collect_declared_base_branches,
    read_plan_preview,
    NoPlanFileError,
    MultiplePlanFilesError,
)


class TestFindDraftPlanFile:
    def test_single_uuid_draft(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        draft = plan_dir / "plan-cf403d73-dccc-4b41-a0d9-bff26b89e0c1.md"
        draft.write_text("# Plan: Test")
        (plan_dir / "plan-100.md").write_text("# Plan: Old")

        result = find_draft_plan_file(plan_dir)
        assert result == draft

    def test_single_slug_draft(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        draft = plan_dir / "plan-draft-workflow-plan-readability.md"
        draft.write_text("# Plan: Test")
        (plan_dir / "plan-100.md").write_text("# Plan: Old")

        result = find_draft_plan_file(plan_dir)
        assert result == draft

    def test_no_drafts_raises(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        (plan_dir / "plan-100.md").write_text("# Plan: Old")

        with pytest.raises(NoPlanFileError):
            find_draft_plan_file(plan_dir)

    def test_multiple_drafts_raises(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        (plan_dir / "plan-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md").write_text("")
        (plan_dir / "plan-11111111-2222-3333-4444-555555555555.md").write_text("")

        with pytest.raises(MultiplePlanFilesError) as exc_info:
            find_draft_plan_file(plan_dir)
        assert len(exc_info.value.files) == 2

    def test_multiple_draft_styles_raise(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        (plan_dir / "plan-draft-readable-contract.md").write_text("")
        (plan_dir / "plan-11111111-2222-3333-4444-555555555555.md").write_text("")

        with pytest.raises(MultiplePlanFilesError) as exc_info:
            find_draft_plan_file(plan_dir)
        assert exc_info.value.files == [
            "plan-11111111-2222-3333-4444-555555555555.md",
            "plan-draft-readable-contract.md",
        ]

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(NoPlanFileError):
            find_draft_plan_file(tmp_path / "nonexistent")

    def test_ignores_non_draft_files(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        (plan_dir / "harness-proposal.md").write_text("")
        (plan_dir / "plan-100.md").write_text("")
        (plan_dir / "plan-draft-.md").write_text("")

        with pytest.raises(NoPlanFileError):
            find_draft_plan_file(plan_dir)


class TestRenamePlanToIssue:
    def test_rename_success(self, tmp_path):
        src = tmp_path / "plan-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md"
        src.write_text("# Plan: Test")

        result = rename_plan_to_issue(src, 153)
        assert result == tmp_path / "plan-153.md"
        assert result.exists()
        assert not src.exists()

    def test_rename_slug_draft_success(self, tmp_path):
        src = tmp_path / "plan-draft-readable-contract.md"
        src.write_text("# Plan: Test")

        result = rename_plan_to_issue(src, 153)
        assert result == tmp_path / "plan-153.md"
        assert result.exists()
        assert not src.exists()

    def test_rename_target_exists_raises(self, tmp_path):
        src = tmp_path / "plan-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md"
        src.write_text("# Plan: Test")
        (tmp_path / "plan-153.md").write_text("existing")

        with pytest.raises(FileExistsError):
            rename_plan_to_issue(src, 153)


class TestPlanFileForIssue:
    def test_exists(self, tmp_path):
        (tmp_path / "plan-42.md").write_text("# Plan: Test")
        result = plan_file_for_issue(42, tmp_path)
        assert result == tmp_path / "plan-42.md"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            plan_file_for_issue(999, tmp_path)


class TestExtractPlanTitle:
    def test_standard_title(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("# Plan: Harness Architecture Redesign\n\n## Background")
        assert extract_plan_title(f) == "Harness Architecture Redesign"

    def test_no_prefix(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("# Some Other Title\n\ncontent")
        assert extract_plan_title(f) == "Some Other Title"

    def test_title_with_frontmatter(self, tmp_path):
        # Regression: a leading '---' block must not be returned as the title.
        f = tmp_path / "plan.md"
        f.write_text(
            "---\n"
            "base_branch: feat/issue-364-strategy-engine-lua\n"
            "parent_issue: 364\n"
            "---\n"
            "# Plan: Sub-issue Title\n\n## Background"
        )
        assert extract_plan_title(f) == "Sub-issue Title"

    def test_title_with_frontmatter_and_blank_line(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text(
            "---\nbase_branch: develop\n---\n\n# Plan: Spaced Title\n"
        )
        assert extract_plan_title(f) == "Spaced Title"

    def test_title_no_prefix_after_frontmatter(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("---\nparent_issue: 12\n---\n# Bare Heading\n")
        assert extract_plan_title(f) == "Bare Heading"

    def test_lone_unclosed_fence_is_not_title(self, tmp_path):
        # A degenerate doc that is only an unclosed '---' must not yield '---'.
        f = tmp_path / "plan.md"
        f.write_text("---\n")
        assert extract_plan_title(f) == ""


class TestSplitFrontmatter:
    def test_present(self):
        block, body = split_frontmatter("---\na: 1\n---\nbody line\n")
        assert block == "a: 1"
        assert body == "body line\n"

    def test_absent(self):
        block, body = split_frontmatter("# Plan: No fm\nbody")
        assert block == ""
        assert body == "# Plan: No fm\nbody"

    def test_missing_closing_fence_is_treated_as_body(self):
        text = "---\na: 1\nno closing fence\n# Plan: x"
        block, body = split_frontmatter(text)
        assert block == ""
        assert body == text


class TestParseFrontmatter:
    def test_no_frontmatter_returns_empty(self):
        assert parse_frontmatter("# Plan: Title\n\nbody") == {}

    def test_basic_keys(self):
        fm = parse_frontmatter(
            "---\nbase_branch: feat/issue-364-foo\nparent_issue: 364\n---\n# Plan: x"
        )
        assert fm == {"base_branch": "feat/issue-364-foo", "parent_issue": "364"}

    def test_quotes_and_whitespace(self):
        fm = parse_frontmatter('---\n base_branch :  "feat/x"  \n---\n')
        assert fm["base_branch"] == "feat/x"

    def test_single_quotes(self):
        fm = parse_frontmatter("---\nbase_branch: 'feat/y'\n---\n")
        assert fm["base_branch"] == "feat/y"

    def test_inline_comment_stripped(self):
        fm = parse_frontmatter(
            "---\nbase_branch: feat/z   # PR target\n---\n"
        )
        assert fm["base_branch"] == "feat/z"

    def test_hash_without_space_is_literal(self):
        fm = parse_frontmatter("---\nbase_branch: feat/a#b\n---\n")
        assert fm["base_branch"] == "feat/a#b"

    def test_full_line_comment_and_blank_skipped(self):
        fm = parse_frontmatter(
            "---\n# a comment\n\nbase_branch: develop\n---\n"
        )
        assert fm == {"base_branch": "develop"}

    def test_line_without_colon_skipped(self):
        fm = parse_frontmatter("---\nnonsense\nbase_branch: develop\n---\n")
        assert fm == {"base_branch": "develop"}

    def test_duplicate_key_last_wins(self):
        fm = parse_frontmatter("---\nbase_branch: a\nbase_branch: b\n---\n")
        assert fm["base_branch"] == "b"

    def test_crlf_line_endings(self):
        # A literal \r must not leak into key or value.
        fm = parse_frontmatter("---\r\nbase_branch: feat/x\r\nparent_issue: 9\r\n---\r\n")
        assert fm == {"base_branch": "feat/x", "parent_issue": "9"}

    def test_keys_are_case_sensitive(self):
        fm = parse_frontmatter("---\nBase_Branch: feat/x\n---\n")
        assert "base_branch" not in fm  # only lowercase 'base_branch' is recognized
        assert fm["Base_Branch"] == "feat/x"


class TestExtractBaseBranch:
    def test_declared(self, tmp_path):
        f = tmp_path / "plan-364.md"
        f.write_text("---\nbase_branch: feat/issue-360-x\n---\n# Plan: x")
        assert extract_base_branch(f) == "feat/issue-360-x"

    def test_absent_returns_none(self, tmp_path):
        f = tmp_path / "plan-1.md"
        f.write_text("# Plan: no frontmatter")
        assert extract_base_branch(f) is None

    def test_empty_value_returns_none(self, tmp_path):
        f = tmp_path / "plan-2.md"
        f.write_text("---\nbase_branch:\n---\n# Plan: x")
        assert extract_base_branch(f) is None

    def test_develop_is_returned_verbatim(self, tmp_path):
        f = tmp_path / "plan-3.md"
        f.write_text("---\nbase_branch: develop\n---\n# Plan: x")
        assert extract_base_branch(f) == "develop"


class TestCollectDeclaredBaseBranches:
    def test_collects_unique_declared_bases(self, tmp_path):
        (tmp_path / "plan-364.md").write_text(
            "---\nbase_branch: feat/issue-364-engine\n---\n# Plan: a"
        )
        (tmp_path / "plan-378.md").write_text(
            "---\nbase_branch: feat/issue-364-engine\n---\n# Plan: b"  # same integration branch
        )
        (tmp_path / "plan-100.md").write_text("# Plan: no frontmatter")
        (tmp_path / "plan-200.md").write_text("---\nbase_branch: develop\n---\n# Plan: d")

        result = collect_declared_base_branches(tmp_path)
        assert result == {"feat/issue-364-engine", "develop"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert collect_declared_base_branches(tmp_path / "nope") == set()

    def test_ignores_non_plan_files(self, tmp_path):
        (tmp_path / "notes.md").write_text("---\nbase_branch: feat/x\n---\n")
        assert collect_declared_base_branches(tmp_path) == set()


class TestReadPlanPreview:
    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("# Plan: Title\nline2\nline3\n")
        preview = read_plan_preview(f, max_lines=2)
        assert preview == "# Plan: Title\nline2"

    def test_frontmatter_shown_plus_body_budget(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text(
            "---\nbase_branch: feat/issue-9-x\n---\n# Plan: Title\nline2\nline3\n"
        )
        preview = read_plan_preview(f, max_lines=2)
        # Frontmatter is shown in full; the 2-line budget applies to the body.
        assert preview == "---\nbase_branch: feat/issue-9-x\n---\n# Plan: Title\nline2"

    def test_new_plan_shape_preview_starts_with_human_layer(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text(
            "---\nbase_branch: feat/issue-1-parent\n---\n"
            "# Plan: Readable Workflow Contract\n\n"
            "## Intent Summary\n"
            "Make the plan understandable before task execution.\n\n"
            "## Current State\n"
            "Plans jump too quickly into checklist items.\n\n"
            "## Target State\n"
            "Directors can confirm intent from the first screen.\n\n"
            "## Non-Goals\n"
            "- Do not replace ADRs.\n\n"
            "## Drift Guards\n"
            "- Do not turn task cards into implementation algorithms.\n"
        )

        preview = read_plan_preview(f, max_lines=30)
        assert "base_branch: feat/issue-1-parent" in preview
        assert "## Intent Summary" in preview
        assert "Make the plan understandable" in preview
        assert "## Current State" in preview
        assert "## Target State" in preview
        assert "## Non-Goals" in preview
        assert "## Drift Guards" in preview
