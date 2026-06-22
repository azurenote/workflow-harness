"""Tests for harness_core.config module."""

from harness_core.config import is_draft_plan, is_committed_plan, extract_issue_number


class TestFileNameRules:
    def test_uuid_is_draft(self):
        assert is_draft_plan(
            "plan-cf403d73-dccc-4b41-a0d9-bff26b89e0c1.md"
        )

    def test_slug_draft_is_draft(self):
        assert is_draft_plan("plan-draft-workflow-plan-readability.md")

    def test_slug_draft_with_numeric_suffix_is_draft(self):
        assert is_draft_plan("plan-draft-workflow-plan-readability-2.md")

    def test_number_is_not_draft(self):
        assert not is_draft_plan("plan-153.md")

    def test_arbitrary_name_is_not_draft(self):
        assert not is_draft_plan("harness-architecture-proposal.md")

    def test_malformed_slug_draft_is_not_draft(self):
        assert not is_draft_plan("plan-draft-.md")
        assert not is_draft_plan("plan-draft-Workflow-Plan.md")

    def test_number_is_committed(self):
        assert is_committed_plan("plan-153.md")

    def test_uuid_is_not_committed(self):
        assert not is_committed_plan(
            "plan-cf403d73-dccc-4b41-a0d9-bff26b89e0c1.md"
        )

    def test_extract_issue_number(self):
        assert extract_issue_number("plan-153.md") == 153

    def test_extract_issue_number_none(self):
        assert extract_issue_number("plan-abc.md") is None
