"""Tests for harness_core.git module."""

from harness_core.git import derive_branch_name


class TestDeriveBranchName:
    def test_simple_title(self):
        result = derive_branch_name(42, "Upbit JWT Auth")
        assert result == "feat/issue-42-upbit-jwt-auth"

    def test_special_characters_stripped(self):
        result = derive_branch_name(
            153, "Harness Architecture Redesign for enseed-trader Workflow"
        )
        assert result == "feat/issue-153-harness-architecture-redesign-for-enseed-trader-wo"

    def test_fix_title(self):
        result = derive_branch_name(
            136, "Fix #136 — MasterDriven close no-op"
        )
        assert result == "feat/issue-136-fix-136-masterdriven-close-no-op"

    def test_truncation(self):
        long_title = "A" * 100
        result = derive_branch_name(1, long_title)
        assert len(result) <= len("feat/issue-1-") + 50

    def test_empty_title(self):
        result = derive_branch_name(1, "")
        assert result == "feat/issue-1-"
