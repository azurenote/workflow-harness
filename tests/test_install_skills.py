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
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-skills.sh"

# The script itself runs awk, grep, ln and date, so a test PATH may only ever be
# *prepended* to — drop the system directories and the script breaks for reasons
# that have nothing to do with what is being tested.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

ROW = re.compile(r"^  (ok|MISSING|unknown) +(\S+)", re.MULTILINE)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway copy of the script + skills tree, safe to mutate."""
    dst = tmp_path / "repo"
    dst.mkdir()
    shutil.copy(SCRIPT, dst / "install-skills.sh")
    shutil.copytree(ROOT / "skills", dst / "skills")
    return dst


def run(repo: Path, tmp_path: Path, *, plugin_db: Path | None, env=None, path_prefix: Path | None = None):
    """Run the script. `path_prefix` goes in front of the system PATH.

    Which CLIs a machine happens to have is not a fact a test may depend on —
    a GitHub runner has /usr/bin/gh, this laptop does not. Tests that care
    about presence put their own stub on PATH and assert against that.
    """
    environ = {
        "PATH": f"{path_prefix}:{BASE_PATH}" if path_prefix else BASE_PATH,
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


def mutate(repo: Path, old: str, new: str) -> None:
    """Rewrite one unique span of the manifest copy.

    A `sed` that misses its pattern is a no-op, and a no-op mutation leaves the
    suite green while the assertion below reads as proof. Requiring exactly one
    occurrence turns a missed mutation into a failure at the point of mutating.
    """
    manifest = repo / "skills" / "dependencies.yaml"
    text = manifest.read_text(encoding="utf-8")
    count = text.count(old)
    assert count == 1, f"mutation anchor {old!r} occurs {count} times, expected exactly 1"
    manifest.write_text(text.replace(old, new, 1), encoding="utf-8")


def mutate_field(repo: Path, tool_id: str, field: str, new_value: str) -> None:
    """Rewrite one field inside one tool's record.

    Anchoring on a literal value couples a test to whatever that value happens
    to be: two tools sharing a `min_version` makes the anchor ambiguous, and a
    legitimate version bump makes it vanish. Both surface as "mutation anchor
    occurs 0 times" in a test that has nothing to do with the edit.
    """
    manifest = repo / "skills" / "dependencies.yaml"
    lines = manifest.read_text(encoding="utf-8").split("\n")
    start = next(
        (i for i, l in enumerate(lines) if re.match(rf"^\s*- id:\s*{re.escape(tool_id)}\s*$", l)),
        None,
    )
    assert start is not None, f"no record for {tool_id!r} in the manifest"
    for i in range(start + 1, len(lines)):
        if re.match(r"^\s*- id:", lines[i]):
            break
        m = re.match(rf"^(\s*){re.escape(field)}:", lines[i])
        if m:
            lines[i] = f"{m.group(1)}{field}: {new_value}"
            manifest.write_text("\n".join(lines), encoding="utf-8")
            return
    raise AssertionError(f"{tool_id} has no `{field}` field to mutate")


def stub(bin_dir: Path, name: str, marker: Path) -> Path:
    """An executable file on PATH that records having been run.

    Presence is a PATH lookup, not an execution — the marker is how the test
    tells those two apart.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / name
    exe.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    exe.chmod(0o755)
    return bin_dir


def declared_ids(repo: Path) -> list[str]:
    manifest = (repo / "skills" / "dependencies.yaml").read_text(encoding="utf-8")
    return re.findall(r"^\s*- id:\s*(.+?)\s*$", manifest, re.MULTILINE)


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


def test_an_env_id_subscript_cannot_execute_code(repo, tmp_path):
    """`${!id}` is not inert, and the old payloads did not prove it was.

    Bash evaluates a `name[subscript]` subscript arithmetically, and arithmetic
    evaluation performs command substitution. `X:-$(touch f)` and `X$(touch f)`
    both miss that path, so two tests certified a property the code lacked:
    with the subscript form, the real script created the file and still exited
    0 with a normal-looking report.
    """
    marker = tmp_path / "subscript-injected"
    mutate(repo, "  - id: ENABLE_LSP_TOOL\n", f"  - id: x[$(touch {marker})]\n")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "an env-presence id reached arithmetic evaluation and ran"
    assert "id is not usable" in result.stdout, "the unusable id was not reported"


def test_an_on_path_id_with_a_slash_is_not_a_cwd_lookup(repo, tmp_path):
    """`type -P bin/ls` is a path test against the invoker's cwd.

    Left alone, a row's verdict depends on where the script was run from — the
    same cwd dependence the group-member glob fix removed.
    """
    mutate(repo, "  - id: git\n", "  - id: bin/ls\n")

    result = subprocess.run(
        ["bash", str(repo / "install-skills.sh")],
        capture_output=True, text=True, cwd="/", timeout=60,
        env={"PATH": BASE_PATH, "HOME": str(tmp_path / "home"),
             "CLAUDE_SKILLS_DIR": str(tmp_path / "skills-dst"),
             "CLAUDE_PLUGIN_DB": str(write_db(tmp_path))},
    )

    assert result.returncode == 0, result.stderr
    assert "ok       bin/ls" not in result.stdout
    assert "id is not usable" in result.stdout


def test_an_empty_member_list_is_reported_not_a_bash_error(repo, tmp_path):
    """On bash 3.2 an empty array under `set -u` kills the subshell; the caller
    saw "" and the row degraded to `unknown` while still being counted."""
    manifest = repo / "skills" / "dependencies.yaml"
    text = manifest.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("    members:"))
    manifest.write_text(text.replace(line, "    members:"), encoding="utf-8")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "unbound variable" not in result.stderr
    assert "id is not usable" in result.stdout


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
    # Derived, not counted by hand: how many tools are MISSING depends on what
    # this machine has installed, but every declared tool gets exactly one row.
    assert [m.group(2) for m in ROW.finditer(result.stdout)] == declared_ids(repo)


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


# --------------------------------------------------------------------------
# CLI presence: a PATH lookup, and nothing more than a PATH lookup.
# --------------------------------------------------------------------------


def test_a_cli_missing_from_path_is_reported_and_exit_is_still_zero(repo, tmp_path):
    """Renaming the tool, not un-installing it, is what makes this deterministic."""
    mutate(repo, "  - id: uv\n", "  - id: no-such-tool-xyzzy\n")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "MISSING  no-such-tool-xyzzy (required)" in result.stdout
    assert "install: https://docs.astral.sh/uv/" in result.stdout
    assert "min version: 0.7.8 (declared here; this script does not check it)" in result.stdout


def test_a_cli_on_path_is_reported_ok(repo, tmp_path):
    """And the executable on PATH is found, not run."""
    marker = tmp_path / "stub-ran"
    mutate(repo, "  - id: uv\n", "  - id: no-such-tool-xyzzy\n")
    bin_dir = stub(tmp_path / "bin", "no-such-tool-xyzzy", marker)

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path), path_prefix=bin_dir)

    assert result.returncode == 0, result.stderr
    assert "ok       no-such-tool-xyzzy (required)" in result.stdout
    assert "MISSING  no-such-tool-xyzzy" not in result.stdout
    assert not marker.exists(), "presence resolution executed the tool"


def test_an_on_path_id_cannot_execute_code(repo, tmp_path):
    """The `env`-presence branch once went through `eval`. The new branch must
    not reintroduce that on a different field."""
    marker = tmp_path / "injected"
    mutate(repo, "  - id: git\n", f"  - id: X$(touch {marker})\n")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "an on_path id reached a shell"


def test_a_declared_version_probe_is_never_executed(repo, tmp_path):
    """`version_probe` is declared for the agent, never for this script.

    The script does not read the field at all, so the value has no route into
    a shell — this pins that, and would catch an awk anchor added for it later.
    """
    marker = tmp_path / "probed"
    mutate_field(repo, "git", "version_probe", f"touch {marker}")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "the script executed a declared version probe"
    assert str(marker) not in result.stdout, "the script read version_probe"


def test_a_declared_min_version_is_reported_not_enforced(repo, tmp_path):
    """A floor above the installed build changes nothing. That is the contract.

    If someone later adds a version comparison here, the stubbed tool below
    flips from ok to MISSING and this test says so.
    """
    marker = tmp_path / "stub-ran"
    # Present on PATH, floor raised far above anything installable.
    mutate_field(repo, "uv", "min_version", '"99.0.0"')
    bin_dir = stub(tmp_path / "bin", "uv", marker)
    # Absent by construction (renamed, not un-installed), floor raised too.
    mutate_field(repo, "fj", "min_version", '"98.0.0"')
    mutate(repo, "  - id: fj\n", "  - id: no-such-tool-xyzzy\n")

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path), path_prefix=bin_dir)

    assert result.returncode == 0, result.stderr
    # Present, with a floor it cannot possibly meet -> still ok.
    assert "ok       uv (required)" in result.stdout
    assert "MISSING  uv" not in result.stdout
    assert not marker.exists()
    # Absent -> the declared floor is shown, and labelled as unchecked.
    assert "MISSING  no-such-tool-xyzzy (optional)" in result.stdout
    assert "min version: 98.0.0 (declared here; this script does not check it)" in result.stdout


def test_a_cli_row_appears_for_every_declared_cli(repo, tmp_path):
    """The report covers the manifest; nothing drops out silently."""
    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))

    assert [m.group(2) for m in ROW.finditer(result.stdout)] == declared_ids(repo)
    assert "unrecognized presence check" not in result.stdout


# --------------------------------------------------------------------------
# Local only: is the declared probe the command that actually works?
#
# The whole point of declaring `version_probe` is that it cannot be inferred.
# Nothing but running it proves the declared one is right, and that can only
# happen where the tool is installed — so this is skipped on CI rather than
# made into an assertion about what a runner has.
# --------------------------------------------------------------------------


@pytest.mark.skipif(bool(os.environ.get("CI")), reason="needs the real CLIs installed")
def test_declared_version_probe_actually_runs():
    import yaml

    tools = yaml.safe_load((ROOT / "skills" / "dependencies.yaml").read_text(encoding="utf-8"))["tools"]
    clis = [t for t in tools if t["kind"] == "cli"]
    assert clis

    checked = []
    for tool in clis:
        argv = shlex.split(tool["version_probe"])
        # The boundary: a manifest edit must not be able to smuggle an
        # arbitrary command into the test runner. The probe may only invoke
        # the tool it belongs to.
        assert argv[0] == tool["id"], (
            f"{tool['id']} declares a version_probe that runs {argv[0]!r}"
        )
        if shutil.which(argv[0]) is None:
            continue
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, (
            f"`{tool['version_probe']}` exited {proc.returncode}: {proc.stderr.strip()!r}. "
            "The declared probe is wrong for the installed tool — which is how an "
            "installed tool gets reported as missing."
        )
        assert proc.stdout.strip(), f"`{tool['version_probe']}` printed nothing"
        checked.append(tool["id"])

    if not checked:
        pytest.skip("none of the declared CLIs are installed here")


def test_the_shell_reader_and_the_yaml_parser_agree_on_every_value(repo, tmp_path):
    """Two parsers read this file; only one of them was ever checked.

    The awk reader is hand-rolled and scalar-only. Nothing compared what it
    *prints* against `yaml.safe_load`, so a `minv` left unreset between records
    printed python3's floor on a Claude-plugin row, and a value containing `"`
    printed a raw YAML escape — both with the suite green.
    """
    import yaml

    result = run(repo, tmp_path, plugin_db=write_db(tmp_path))
    tools = {
        t["id"]: t
        for t in yaml.safe_load(
            (repo / "skills" / "dependencies.yaml").read_text(encoding="utf-8")
        )["tools"]
    }

    printed: dict[str, dict[str, str]] = {}
    current = None
    for line in result.stdout.splitlines():
        row = ROW.match(line)
        if row:
            current = row.group(2)
            printed[current] = {}
            floor = re.search(r"declared floor (\S+), not checked here", line)
            if floor:
                printed[current]["floor"] = floor.group(1)
            continue
        field = re.match(r"^ +(degrade|install|min version): (.*)$", line)
        if field and current:
            key = "floor" if field.group(1) == "min version" else field.group(1)
            value = field.group(2)
            if key == "floor":
                value = value.split(" (declared here")[0]
            printed[current][key] = value

    assert printed, "the script printed no rows"

    for tool_id, fields in printed.items():
        tool = tools[tool_id]
        if "degrade" in fields:
            assert fields["degrade"] == tool["degrades"], (
                f"{tool_id}: the shell reader printed a `degrades` the YAML parser disagrees with"
            )
        if "install" in fields:
            assert fields["install"] == tool["install"], (
                f"{tool_id}: the shell reader printed an `install` the YAML parser disagrees with"
            )
        # A floor printed for a tool that declares none means the reader leaked
        # another record's value across the row boundary.
        assert fields.get("floor") == tool.get("min_version"), (
            f"{tool_id}: printed floor {fields.get('floor')!r} but the manifest declares "
            f"{tool.get('min_version')!r}"
        )
