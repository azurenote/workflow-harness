"""Behavioural tests for install-skills.sh.

The script grew ~110 lines of bash that parse a YAML manifest with awk and read
a JSON plugin database with grep. The first attempt to guard that was a set of
greps over the script's *source*, which a review proved vacuous: deleting the
whole feature, or adding `eval "$inst"` so the script ran installs, both left
the suite green.

So run the thing. The repo already does this for git (tests/test_git.py drives
a real binary through subprocess), and the script is parameterized for exactly
this via CLAUDE_SKILLS_DIR and CLAUDE_PLUGIN_DB.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-skills.sh"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway copy of the script + skills tree, safe to mutate."""
    dst = tmp_path / "repo"
    dst.mkdir()
    shutil.copy(SCRIPT, dst / "install-skills.sh")
    shutil.copytree(ROOT / "skills", dst / "skills")
    return dst


def run(repo: Path, tmp_path: Path, *, plugin_db: Path | None, env=None):
    environ = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp_path / "home"),
        "CLAUDE_SKILLS_DIR": str(tmp_path / "skills-dst"),
    }
    if plugin_db is not None:
        environ["CLAUDE_PLUGIN_DB"] = str(plugin_db)
    environ.update(env or {})
    return subprocess.run(
        ["bash", str(repo / "install-skills.sh")],
        capture_output=True, text=True, env=environ, timeout=60,
    )


def write_db(tmp_path: Path, *plugin_ids: str) -> Path:
    db = tmp_path / "installed_plugins.json"
    db.write_text(json.dumps({"version": 2, "plugins": {p: [] for p in plugin_ids}}), encoding="utf-8")
    return db


# --------------------------------------------------------------------------
# The report is a report: it installs nothing and never gates.
# --------------------------------------------------------------------------


def test_missing_tools_are_reported_and_exit_is_still_zero(repo, tmp_path):
    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "MISSING  code-review@claude-plugins-official (required)" in result.stdout
    # Every missing row carries what it costs and how to fix it.
    assert "degrade:" in result.stdout
    assert "install: claude plugin install code-review@claude-plugins-official" in result.stdout
    assert "missing — skills fall back" in result.stdout


def test_linking_still_happens_when_every_tool_is_missing(repo, tmp_path):
    run(repo, tmp_path, plugin_db=write_db(tmp_path))

    dst = tmp_path / "skills-dst"
    linked = sorted(p.name for p in dst.iterdir())
    assert "project-start" in linked and "SKILL-CONFIG.md" in linked
    # The reference tree and the manifest are addressed as ~/.claude/skills/...
    # by the skills, so they have to be linked too.
    assert "_shared" in linked and "dependencies.yaml" in linked
    assert len(linked) == len(list((repo / "skills").iterdir()))


def test_no_plugin_database_is_a_skip_not_a_finding(repo, tmp_path):
    result = run(repo, tmp_path, plugin_db=tmp_path / "nope.json")

    assert result.returncode == 0, result.stderr
    assert "prerequisites: skipped" in result.stdout
    # A host without the plugin system (Codex, CI) must not be told it is broken.
    assert "MISSING" not in result.stdout


def test_present_tools_are_reported_ok(repo, tmp_path):
    db = write_db(tmp_path, "code-review@claude-plugins-official")
    result = run(repo, tmp_path, plugin_db=db)

    assert "ok       code-review@claude-plugins-official (required)" in result.stdout
    assert "MISSING  code-review@claude-plugins-official" not in result.stdout


def test_the_script_never_executes_an_install_command(repo, tmp_path):
    """`install:` is printed for a human, never run.

    Proven by making the install command observable: if anything executes it,
    the marker file appears.
    """
    marker = tmp_path / "executed"
    manifest = repo / "skills" / "dependencies.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "    install: claude plugin install code-review@claude-plugins-official",
            f"    install: touch {marker}",
        ),
        encoding="utf-8",
    )

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0
    assert f"install: touch {marker}" in result.stdout
    assert not marker.exists(), "the script executed a command from the manifest"


# --------------------------------------------------------------------------
# The manifest is data, not code.
# --------------------------------------------------------------------------


def test_a_manifest_id_cannot_execute_code(repo, tmp_path):
    """An `env`-presence id once went through `eval`.

    `skills/dependencies.yaml` looks inert, and everyone who pulls this repo
    runs ./install-skills.sh. A value in it must never reach a shell.
    """
    marker = tmp_path / "injected"
    manifest = repo / "skills" / "dependencies.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "  - id: ENABLE_LSP_TOOL", f"  - id: X:-$(touch {marker})"
        ),
        encoding="utf-8",
    )

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0
    assert not marker.exists(), "a manifest value was executed"


def test_a_group_member_is_not_glob_expanded(repo, tmp_path):
    """`for m in $memb` let `*@mk` match filenames in the invoker's cwd."""
    manifest = repo / "skills" / "dependencies.yaml"
    text = manifest.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("    members:"))
    manifest.write_text(text.replace(line, '    members: "*@claude-plugins-official"'), encoding="utf-8")
    (repo / "pyright-lsp@claude-plugins-official").touch()

    db = write_db(tmp_path, "pyright-lsp@claude-plugins-official")
    result = subprocess.run(
        ["bash", str(repo / "install-skills.sh")],
        capture_output=True, text=True, cwd=repo, timeout=60,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
             "CLAUDE_SKILLS_DIR": str(tmp_path / "skills-dst"),
             "CLAUDE_PLUGIN_DB": str(db)},
    )

    assert "MISSING  language-lsp@claude-plugins-official" in result.stdout


def test_a_plugin_id_is_matched_exactly_not_as_a_prefix(repo, tmp_path):
    db = write_db(tmp_path, "code-review@claude-plugins-official-fork")
    result = run(repo, tmp_path, plugin_db=db)

    assert "MISSING  code-review@claude-plugins-official (required)" in result.stdout


# --------------------------------------------------------------------------
# A reader that produced nothing must not look like "nothing is missing".
# --------------------------------------------------------------------------


def test_a_partially_read_manifest_is_reported_loudly(repo, tmp_path):
    """A block scalar aborts the awk reader mid-file.

    Without the count check the script prints a short, clean report and exits
    0 — indistinguishable from a healthy run.
    """
    manifest = repo / "skills" / "dependencies.yaml"
    text = manifest.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("    degrades:") and "역할별" in l)
    manifest.write_text(text.replace(line, "    degrades: >\n      역할별 전문 리뷰어를 못 쓴다."), encoding="utf-8")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))
    combined = result.stdout + result.stderr

    assert "block scalar" in combined
    assert "ERROR: manifest declares" in combined
    assert "The report above is incomplete" in combined


def test_reindenting_the_manifest_does_not_empty_the_report(repo, tmp_path):
    """Indentation is not part of the contract; the row count is."""
    manifest = repo / "skills" / "dependencies.yaml"
    reindented = "\n".join(
        ("  " + l) if (l.startswith("  - ") or (l.startswith("    ") and not l.lstrip().startswith("#"))) else l
        for l in manifest.read_text(encoding="utf-8").split("\n")
    )
    manifest.write_text(reindented, encoding="utf-8")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert "ERROR: manifest declares" not in result.stdout
    assert result.stdout.count("MISSING") == 5


def test_an_unrecognized_presence_check_is_counted_not_swallowed(repo, tmp_path):
    """A typo'd presence on a required tool used to print one line and vanish
    from the totals, taking its install hint with it."""
    manifest = repo / "skills" / "dependencies.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "    presence: installed_plugins\n    install: claude plugin install code-review",
            "    presence: installed_plugin\n    install: claude plugin install code-review",
            1,
        ),
        encoding="utf-8",
    )

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert 'unrecognized presence check "installed_plugin"' in result.stdout
    assert "with an unrecognized presence check" in result.stdout


def test_a_trailing_comment_is_not_part_of_the_value(repo, tmp_path):
    manifest = repo / "skills" / "dependencies.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "    requirement: required", "    requirement: required   # 주석", 1
        ),
        encoding="utf-8",
    )

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert "MISSING  code-review@claude-plugins-official (required)" in result.stdout
    assert "# 주석" not in result.stdout
