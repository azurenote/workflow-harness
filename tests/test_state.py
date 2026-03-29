"""Tests for harness_core.state module."""

import pytest
from pathlib import Path
from harness_core.state import (
    TransactionLog,
    StateValidator,
    StateInconsistencyError,
)


class TestTransactionLog:
    def test_begin_creates_state_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()

        assert state_file.exists()
        assert tx.status == "in_progress"

    def test_log_steps(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("step_1", "ok", {"key": "value"})
        tx.log_step("step_2", "ok")

        assert len(tx.steps) == 2
        assert tx.steps[0]["name"] == "step_1"
        assert tx.steps[0]["status"] == "ok"
        assert tx.steps[0]["result"]["key"] == "value"

    def test_fail_sets_status(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("step_1", "ok")
        tx.log_step("step_2", "fail", {"error": "network"})

        assert tx.status == "failed"

    def test_commit_cleans_up(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("step_1", "ok")
        tx.commit()

        assert tx.status == "completed"
        assert not state_file.exists()

    def test_load_restores_state(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("step_1", "ok", {"number": 42})
        tx.log_step("step_2", "fail", {"error": "boom"})

        loaded = TransactionLog.load(state_file)
        assert loaded is not None
        assert loaded.operation == "test_op"
        assert loaded.status == "failed"
        assert len(loaded.steps) == 2

    def test_load_returns_none_if_missing(self, tmp_path):
        assert TransactionLog.load(tmp_path / "nope.json") is None

    def test_last_successful_step(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("a", "ok")
        tx.log_step("b", "ok")
        tx.log_step("c", "fail")

        assert tx.last_successful_step() == "b"

    def test_failed_step(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test_op", state_file)
        tx.begin()
        tx.log_step("a", "ok")
        tx.log_step("b", "fail", {"error": "x"})

        failed = tx.failed_step()
        assert failed is not None
        assert failed["name"] == "b"


class TestValidatePlanExists:
    def test_exists(self, tmp_path):
        (tmp_path / "plan-153.md").write_text("# Plan: Test")
        result = StateValidator.validate_plan_exists(153, tmp_path)
        assert result == tmp_path / "plan-153.md"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="plan-999.md"):
            StateValidator.validate_plan_exists(999, tmp_path)


class TestValidateWorktreeExists:
    def test_exists(self, tmp_path):
        (tmp_path / ".git").write_text("gitdir: /somewhere")
        StateValidator.validate_worktree_exists(str(tmp_path))

    def test_missing_raises(self, tmp_path):
        with pytest.raises(StateInconsistencyError, match="Worktree not found"):
            StateValidator.validate_worktree_exists(
                str(tmp_path / "nonexistent")
            )

    def test_no_git_dir_raises(self, tmp_path):
        with pytest.raises(StateInconsistencyError):
            StateValidator.validate_worktree_exists(str(tmp_path))


class TestValidateIssuePlanTitleSync:
    def test_matching_titles(self, tmp_path):
        (tmp_path / "plan-10.md").write_text(
            "# Plan: Harness Architecture Redesign"
        )
        StateValidator.validate_issue_plan_title_sync(
            10, "Harness Architecture Redesign", tmp_path
        )

    def test_plan_title_is_substring(self, tmp_path):
        (tmp_path / "plan-10.md").write_text(
            "# Plan: Harness Architecture Redesign"
        )
        StateValidator.validate_issue_plan_title_sync(
            10,
            "Harness Architecture Redesign for enseed-trader Workflow",
            tmp_path,
        )

    def test_mismatch_raises(self, tmp_path):
        (tmp_path / "plan-10.md").write_text("# Plan: Fix Bug X")
        with pytest.raises(StateInconsistencyError, match="mismatch"):
            StateValidator.validate_issue_plan_title_sync(
                10, "Add Feature Y", tmp_path
            )

    def test_no_plan_file_skips(self, tmp_path):
        StateValidator.validate_issue_plan_title_sync(
            999, "Anything", tmp_path
        )


class TestValidateNoStaleTransaction:
    def test_no_state_file(self, tmp_path):
        StateValidator.validate_no_stale_transaction(
            tmp_path / "state.json"
        )

    def test_completed_transaction_ok(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("test", state_file)
        tx.begin()
        tx.log_step("a", "ok")
        tx.status = "completed"
        tx.save()

        StateValidator.validate_no_stale_transaction(state_file)

    def test_in_progress_raises(self, tmp_path):
        state_file = tmp_path / "state.json"
        tx = TransactionLog("create_issue", state_file)
        tx.begin()
        tx.log_step("find_plan", "ok")

        with pytest.raises(
            StateInconsistencyError, match="Stale transaction"
        ):
            StateValidator.validate_no_stale_transaction(state_file)
