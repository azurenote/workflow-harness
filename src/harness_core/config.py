"""Plan file naming conventions — patterns and validation rules.

These rules are project-agnostic. Project-specific paths (PLAN_DIR, ADR_DIR, etc.)
belong in each project's own config module.
"""

import re

# Legacy draft plan: plan-{uuid}.md  (UUID v4 hex pattern)
UUID_PATTERN = re.compile(
    r"^plan-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.md$"
)

# Human-readable draft plan: plan-draft-{slug}.md
SLUG_DRAFT_PATTERN = re.compile(r"^plan-draft-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")

# Committed plan: plan-{issue_number}.md
ISSUE_NUMBER_PATTERN = re.compile(r"^plan-(\d+)\.md$")


def is_draft_plan(filename: str) -> bool:
    """Return True if filename matches a supported draft plan pattern."""
    return bool(UUID_PATTERN.match(filename) or SLUG_DRAFT_PATTERN.match(filename))


def is_committed_plan(filename: str) -> bool:
    """Return True if filename matches plan-{number}.md pattern."""
    return bool(ISSUE_NUMBER_PATTERN.match(filename))


def extract_issue_number(filename: str) -> int | None:
    """Extract issue number from plan-{number}.md, or None."""
    match = ISSUE_NUMBER_PATTERN.match(filename)
    return int(match.group(1)) if match else None
