"""Tests for harness_core.local module."""

import pytest
from harness_core.local import (
    find_draft_plan_file,
    rename_plan_to_issue,
    extract_plan_title,
    plan_file_for_issue,
    NoPlanFileError,
    MultiplePlanFilesError,
)


class TestFindDraftPlanFile:
    def test_single_draft(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        draft = plan_dir / "plan-cf403d73-dccc-4b41-a0d9-bff26b89e0c1.md"
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

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(NoPlanFileError):
            find_draft_plan_file(tmp_path / "nonexistent")

    def test_ignores_non_uuid_files(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        (plan_dir / "harness-proposal.md").write_text("")
        (plan_dir / "plan-100.md").write_text("")

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
