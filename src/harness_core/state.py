"""State persistence and transaction tracking for harness workflow.

All path-dependent functions require explicit path parameters.
Project-level harness provides defaults via its own config.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TransactionLog:
    """Track operation steps for rollback on failure.

    Usage:
        tx = TransactionLog("create_issue", state_file)
        tx.begin()
        tx.log_step("find_plan", "ok", {"file": "plan-xxx.md"})
        tx.log_step("create_issue", "ok", {"number": 153})
        tx.log_step("add_backlog", "fail", {"error": "timeout"})
        tx.save()
    """

    def __init__(self, operation: str, state_file: Path):
        self.operation = operation
        self.state_file = state_file
        self.steps: list[dict[str, Any]] = []
        self.started_at: str | None = None
        self.status = "pending"

    def begin(self) -> "TransactionLog":
        """Mark transaction as started."""
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.status = "in_progress"
        self.save()
        return self

    def log_step(
        self,
        step_name: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Record a completed step."""
        self.steps.append(
            {
                "name": step_name,
                "status": status,
                "result": result or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if status == "fail":
            self.status = "failed"
        self.save()

    def commit(self) -> None:
        """Mark transaction as successfully completed and clean up."""
        self.status = "completed"
        self.save()
        if self.state_file.exists():
            self.state_file.unlink()

    def save(self) -> None:
        """Persist current state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "operation": self.operation,
            "status": self.status,
            "started_at": self.started_at,
            "steps": self.steps,
        }
        self.state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )

    @classmethod
    def load(cls, state_file: Path) -> "TransactionLog | None":
        """Load a previously saved transaction, or None if no state."""
        if not state_file.exists():
            return None
        data = json.loads(state_file.read_text())
        tx = cls(data["operation"], state_file)
        tx.status = data["status"]
        tx.started_at = data.get("started_at")
        tx.steps = data.get("steps", [])
        return tx

    def last_successful_step(self) -> str | None:
        """Return the name of the last step with status 'ok'."""
        for step in reversed(self.steps):
            if step["status"] == "ok":
                return step["name"]
        return None

    def failed_step(self) -> dict[str, Any] | None:
        """Return the first failed step, or None."""
        for step in self.steps:
            if step["status"] == "fail":
                return step
        return None


# ── State Validation ─────────────────────────────────────────────────────────


class StateInconsistencyError(Exception):
    """Local and remote state are out of sync."""


class StateValidator:
    """Validate consistency between local files, git, and GitHub."""

    @staticmethod
    def validate_plan_exists(
        issue_number: int, plan_dir: Path
    ) -> Path:
        """Check that plan-{issue_number}.md exists locally."""
        path = plan_dir / f"plan-{issue_number}.md"
        if not path.exists():
            raise FileNotFoundError(
                f"Plan file not found: {path}\n"
                f"Expected plan-{issue_number}.md in {plan_dir}/.\n"
                f"Run /project:plan and /project:issue first."
            )
        return path

    @staticmethod
    def validate_branch_exists(branch_name: str) -> None:
        """Check that a local git branch exists."""
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise StateInconsistencyError(
                f"Branch not found: {branch_name}\n"
                f"Expected branch to exist locally.\n"
                f"Run /project:start first."
            )

    @staticmethod
    def validate_worktree_exists(worktree_path: str) -> None:
        """Check that a git worktree exists at the given path."""
        path = Path(worktree_path)
        if not path.exists() or not (path / ".git").exists():
            raise StateInconsistencyError(
                f"Worktree not found: {worktree_path}\n"
                f"Expected a git worktree at this path.\n"
                f"Run /project:start with worktree option."
            )

    @staticmethod
    def validate_issue_plan_title_sync(
        issue_number: int,
        issue_title: str,
        plan_dir: Path,
    ) -> None:
        """Check that GitHub issue title matches local plan title."""
        from .local import extract_plan_title

        plan_path = plan_dir / f"plan-{issue_number}.md"
        if not plan_path.exists():
            return

        local_title = extract_plan_title(plan_path)
        if not _titles_match(issue_title, local_title):
            raise StateInconsistencyError(
                f"Issue/plan title mismatch for #{issue_number}:\n"
                f"  GitHub: {issue_title}\n"
                f"  Local:  {local_title}\n"
                f"Fix the plan file or update the GitHub issue."
            )

    @staticmethod
    def validate_no_stale_transaction(
        state_file: Path,
    ) -> None:
        """Check if a previous transaction was left incomplete."""
        tx = TransactionLog.load(state_file)
        if tx is not None and tx.status == "in_progress":
            last = tx.last_successful_step() or "(none)"
            raise StateInconsistencyError(
                f"Stale transaction found: {tx.operation}\n"
                f"  Status: {tx.status}\n"
                f"  Last successful step: {last}\n"
                f"Review state file and either:\n"
                f"  - Resume the operation manually\n"
                f"  - Delete the state file to start fresh"
            )


def _titles_match(github_title: str, plan_title: str) -> bool:
    """Fuzzy match: plan title may be a substring of issue title or vice versa."""
    g = github_title.lower().strip()
    p = plan_title.lower().strip()
    return g == p or g in p or p in g
