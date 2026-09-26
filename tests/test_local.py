"""Tests for harness_core.local module."""

from pathlib import Path

import pytest
from harness_core.local import (
    abs_under_main,
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
    InvalidIssueIdError,
    InvalidPlanFileError,
)
from harness_core.config import is_draft_plan


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
    """rename_plan_to_issue refuses anything but a draft in the plan dir (#32).

    Every refusal asserts which guard fired (several guards can refuse the same
    input, and one masking another is how a removed guard stays green) and that
    nothing moved.
    """

    DRAFT = "plan-draft-readable-contract.md"

    @pytest.fixture
    def plan_dir(self, tmp_path):
        plan_dir = tmp_path / "plan"
        plan_dir.mkdir()
        return plan_dir

    @staticmethod
    def _assert_untouched(root: Path, *kept: Path) -> None:
        for path in kept:
            assert path.exists() or path.is_symlink(), f"{path} moved"
        # Anything plan-*.md that is not a draft is a rename result, whatever
        # the id form (plan-25.md, plan-SYN-42.md).
        created = [p for p in root.rglob("plan-*.md") if not is_draft_plan(p.name)]
        assert not created, f"a rename happened: {created}"

    def test_rename_success(self, plan_dir):
        src = plan_dir / "plan-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md"
        src.write_text("# Plan: Test")

        result = rename_plan_to_issue(src, 153, plan_dir=plan_dir)
        assert result == plan_dir / "plan-153.md"
        assert result.exists()
        assert not src.exists()

    def test_rename_slug_draft_success(self, plan_dir):
        src = plan_dir / self.DRAFT
        src.write_text("# Plan: Test")

        result = rename_plan_to_issue(src, 153, plan_dir=plan_dir)
        assert result == plan_dir / "plan-153.md"
        assert result.exists()
        assert not src.exists()

    def test_rename_target_exists_raises(self, plan_dir):
        src = plan_dir / "plan-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.md"
        src.write_text("# Plan: Test")
        (plan_dir / "plan-153.md").write_text("existing")

        with pytest.raises(FileExistsError):
            rename_plan_to_issue(src, 153, plan_dir=plan_dir)
        assert src.exists()
        assert (plan_dir / "plan-153.md").read_text() == "existing"

    def test_returns_resolved_absolute_path(self, tmp_path, plan_dir, monkeypatch):
        (plan_dir / self.DRAFT).write_text("# Plan: x")
        monkeypatch.chdir(tmp_path)

        result = rename_plan_to_issue(Path("plan") / self.DRAFT, 7, plan_dir=plan_dir)
        assert result.is_absolute()
        assert result == (plan_dir / "plan-7.md").resolve()

    def test_empty_path_does_not_rename_cwd(self, tmp_path, plan_dir, monkeypatch):
        # The defect itself: Path("") is ".", and "." was renamed to
        # ../plan-25.md — the whole directory, rc 0.
        root = tmp_path / "root"
        root.mkdir()
        monkeypatch.chdir(root)

        with pytest.raises(InvalidPlanFileError, match=r"reject \(exists\)"):
            rename_plan_to_issue(Path(""), 25, plan_dir=plan_dir)
        assert root.is_dir()
        assert not (tmp_path / "plan-25.md").exists()
        self._assert_untouched(tmp_path, root)

    def test_missing_file_rejected(self, tmp_path, plan_dir):
        with pytest.raises(InvalidPlanFileError, match=r"reject \(exists\)"):
            rename_plan_to_issue(plan_dir / self.DRAFT, 25, plan_dir=plan_dir)
        self._assert_untouched(tmp_path)

    def test_directory_with_draft_name_rejected(self, tmp_path, plan_dir):
        src = plan_dir / self.DRAFT
        src.mkdir()

        with pytest.raises(InvalidPlanFileError, match=r"reject \(exists\)"):
            rename_plan_to_issue(src, 25, plan_dir=plan_dir)
        assert src.is_dir()
        self._assert_untouched(tmp_path, src)

    @pytest.mark.parametrize("name", ["plan-100.md", "notes.md", "plan-draft-.md"])
    def test_non_draft_name_rejected(self, tmp_path, plan_dir, name):
        src = plan_dir / name
        src.write_text("x")

        with pytest.raises(InvalidPlanFileError, match=r"reject \(is_draft_plan\)"):
            rename_plan_to_issue(src, 25, plan_dir=plan_dir)
        assert src.read_text() == "x"
        assert not (plan_dir / "plan-25.md").exists()

    @pytest.mark.parametrize(
        "where",
        [
            "plan-x",  # sibling sharing the plan dir's name as a prefix
            "plan/sub",  # below the plan dir, not directly in it
            "plan/../out",  # climbs out
        ],
    )
    def test_draft_outside_plan_dir_rejected(self, tmp_path, plan_dir, where):
        (tmp_path / where).mkdir(parents=True, exist_ok=True)
        src = tmp_path / where / self.DRAFT
        src.write_text("x")

        with pytest.raises(InvalidPlanFileError, match=r"reject \(plan dir\)"):
            rename_plan_to_issue(src, 25, plan_dir=plan_dir)
        self._assert_untouched(tmp_path, src)

    def test_symlink_to_draft_in_same_dir_rejected(self, tmp_path, plan_dir):
        # Following the link would move plan-draft-b.md and leave a dangling a.
        real = plan_dir / "plan-draft-b.md"
        real.write_text("b")
        link = plan_dir / "plan-draft-a.md"
        link.symlink_to(real)

        with pytest.raises(InvalidPlanFileError, match=r"reject \(symlink\)"):
            rename_plan_to_issue(link, 25, plan_dir=plan_dir)
        assert link.is_symlink() and real.read_text() == "b"
        self._assert_untouched(tmp_path, link, real)

    def test_symlink_to_draft_outside_rejected(self, tmp_path, plan_dir):
        out = tmp_path / "out"
        out.mkdir()
        real = out / "plan-draft-b.md"
        real.write_text("b")
        link = plan_dir / self.DRAFT
        link.symlink_to(real)

        with pytest.raises(InvalidPlanFileError, match=r"reject \(symlink\)"):
            rename_plan_to_issue(link, 25, plan_dir=plan_dir)
        self._assert_untouched(tmp_path, link, real)

    def test_plan_dir_given_through_symlink_is_resolved(self, tmp_path, plan_dir):
        # macOS /tmp -> /private/tmp, or a linked .task/plan: the draft resolves
        # to the physical directory, so an unresolved plan_dir refuses it.
        alias = tmp_path / "alias"
        alias.symlink_to(plan_dir)
        (plan_dir / self.DRAFT).write_text("x")

        result = rename_plan_to_issue(alias / self.DRAFT, 25, plan_dir=alias)
        assert result == plan_dir / "plan-25.md"
        assert result.exists()

    def test_default_plan_dir_is_main_worktree(self, tmp_path, monkeypatch):
        # local imports main_worktree_root by name (and git caches it), so the
        # patch must land on harness_core.local — patching cli or git would
        # silently test the real repository root.
        from harness_core import local

        root = tmp_path / "main"
        plan_dir = root / ".task" / "plan"
        plan_dir.mkdir(parents=True)
        monkeypatch.setattr(local, "main_worktree_root", lambda: root)
        elsewhere = tmp_path / "cwd"
        (elsewhere / ".task" / "plan").mkdir(parents=True)
        monkeypatch.chdir(elsewhere)  # a CWD-relative default would look here

        inside = plan_dir / self.DRAFT
        inside.write_text("x")
        assert rename_plan_to_issue(inside, 25) == plan_dir / "plan-25.md"

        outside = elsewhere / ".task" / "plan" / self.DRAFT
        outside.write_text("x")
        with pytest.raises(InvalidPlanFileError, match=r"reject \(plan dir\)"):
            rename_plan_to_issue(outside, 26)
        assert outside.exists()

    def test_default_plan_dir_through_symlinked_root(self, tmp_path, monkeypatch):
        from harness_core import local

        real_root = tmp_path / "main"
        (real_root / ".task" / "plan").mkdir(parents=True)
        alias = tmp_path / "alias"
        alias.symlink_to(real_root)
        monkeypatch.setattr(local, "main_worktree_root", lambda: alias)

        draft = real_root / ".task" / "plan" / self.DRAFT
        draft.write_text("x")
        assert rename_plan_to_issue(draft, 25).exists()

    @pytest.mark.parametrize(
        "issue_id",
        ["", "../x", "#25", "0", "025", "-1", "25\n", "syn-42", "SYN-0", 0, -1, True],
    )
    def test_bad_issue_id_rejected(self, tmp_path, plan_dir, issue_id):
        src = plan_dir / self.DRAFT
        src.write_text("x")

        with pytest.raises(InvalidIssueIdError):
            rename_plan_to_issue(src, issue_id, plan_dir=plan_dir)
        assert sorted(p.name for p in plan_dir.iterdir()) == [self.DRAFT]
        self._assert_untouched(tmp_path, src)

    @pytest.mark.parametrize(
        ("issue_id", "name"),
        [(25, "plan-25.md"), ("25", "plan-25.md"), ("SYN-42", "plan-SYN-42.md")],
    )
    def test_issue_id_forms_accepted(self, plan_dir, issue_id, name):
        src = plan_dir / self.DRAFT
        src.write_text("x")

        assert rename_plan_to_issue(src, issue_id, plan_dir=plan_dir) == plan_dir / name

    def test_id_checked_before_source(self, tmp_path, plan_dir, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(InvalidIssueIdError):
            rename_plan_to_issue(Path(""), "../x", plan_dir=plan_dir)


class TestPlanFileForIssue:
    def test_exists(self, tmp_path):
        (tmp_path / "plan-42.md").write_text("# Plan: Test")
        result = plan_file_for_issue(42, tmp_path)
        assert result == tmp_path / "plan-42.md"

    def test_ticket_key(self, tmp_path):
        (tmp_path / "plan-SYN-42.md").write_text("# Plan: Test")
        assert plan_file_for_issue("SYN-42", tmp_path) == tmp_path / "plan-SYN-42.md"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            plan_file_for_issue(999, tmp_path)

    @pytest.mark.parametrize("issue_id", ["../x", "", "25\n"])
    def test_bad_issue_id_rejected(self, tmp_path, issue_id):
        # ../x must not reach the path: a plan-../x.md one level up would be found.
        (tmp_path / "plan-..").mkdir()
        (tmp_path / "plan-.." / "x.md").write_text("")
        with pytest.raises(InvalidIssueIdError):
            plan_file_for_issue(issue_id, tmp_path)


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


class TestAbsUnderMain:
    """The re-rooting `cli._abs_under_main` used to own privately.

    It moved here because a second caller appeared — the GitHub adapter reads
    `--body-file` the same way — and two copies of a path rule diverge.
    """

    def test_relative_path_reroots_at_the_main_worktree(self, tmp_path):
        # The file named lives only in the main checkout's gitignored .task/plan/.
        assert abs_under_main(Path("a/b.md"), root=tmp_path) == (tmp_path / "a" / "b.md")

    def test_absolute_path_passes_through(self, tmp_path):
        absolute = tmp_path / "elsewhere" / "b.md"
        assert abs_under_main(absolute, root=tmp_path / "main") == absolute

    def test_user_path_expands_and_is_treated_as_absolute(self, tmp_path, monkeypatch):
        # Without expansion `~/notes.md` is "relative" and would be re-rooted into
        # the worktree, producing a path that cannot exist.
        monkeypatch.setenv("HOME", str(tmp_path))
        result = abs_under_main(Path("~/notes.md"), root=tmp_path / "main")
        assert result == tmp_path / "notes.md"

    def test_expansion_can_be_turned_off(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = abs_under_main(Path("~/notes.md"), root=tmp_path / "main", expand_user=False)
        assert result == (tmp_path / "main" / "~" / "notes.md")

    def test_root_defaults_to_the_main_worktree_lookup(self, tmp_path, monkeypatch):
        from harness_core import local

        monkeypatch.setattr(local, "main_worktree_root", lambda: tmp_path)
        assert abs_under_main(Path("a.md")) == tmp_path / "a.md"
