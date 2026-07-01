"""Project-local harness scaffold and update support."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from string import Template
from typing import Iterable, Sequence

from .preflight import (
    PreflightResult,
    check_preflight,
    preflight_to_dict,
)


TEMPLATE_VERSION = "2"


@dataclass(frozen=True)
class FilePlan:
    """Planned operation for one target file."""

    path: str
    action: str
    reason: str
    backup_path: str | None = None


@dataclass(frozen=True)
class ScaffoldResult:
    """Dry-run or apply result for a scaffold operation."""

    mode: str
    target_root: str
    dry_run: bool
    preflight: PreflightResult
    files: tuple[FilePlan, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.preflight.ok and not self.errors

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(w for w in self.warnings if w.startswith("error:"))

    def by_action(self, action: str) -> list[str]:
        return [file.path for file in self.files if file.action == action]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "target_root": self.target_root,
            "dry_run": self.dry_run,
            "preflight": preflight_to_dict(self.preflight),
            "created": self.by_action("create"),
            "updated": self.by_action("update"),
            "unchanged": self.by_action("unchanged"),
            "skipped": self.by_action("skip"),
            "backed_up": [
                file.backup_path
                for file in self.files
                if file.backup_path and file.action == "update"
            ],
            "warnings": list(self.warnings),
            "files": [
                {
                    "path": file.path,
                    "action": file.action,
                    "reason": file.reason,
                    "backup_path": file.backup_path,
                }
                for file in self.files
            ],
        }


@dataclass(frozen=True)
class RenderContext:
    """Project-specific values used while rendering canonical templates."""

    project_name: str
    base_branch: str = "main"
    issue_tracker: str = "forgejo"
    forgejo_remote: str = "lab"
    forgejo_repo: str = ""


@dataclass(frozen=True)
class TemplateEntry:
    rel_path: str
    template_path: str
    preserve_existing: bool = False


CANONICAL_ENTRIES = (
    TemplateEntry(".claude/skill-config.yaml", "skill-config.yaml.tmpl", True),
    TemplateEntry(".claude/scripts/project.py", "project.py.tmpl", True),
    TemplateEntry(".claude/scripts/harness_cli.py", "harness_cli.py.tmpl"),
    TemplateEntry(".claude/scripts/harness/__init__.py", "harness/__init__.py.tmpl"),
    TemplateEntry(".claude/scripts/harness/config.py", "harness/config.py.tmpl"),
    TemplateEntry(".claude/scripts/harness/.manifest.json", "manifest.json.tmpl"),
    TemplateEntry(
        ".claude/scripts/.harness-backup/.gitignore",
        "backup.gitignore.tmpl",
    ),
)


def plan_init(
    target_root: Path | str,
    *,
    context: RenderContext | None = None,
    apply: bool = False,
    preflight: PreflightResult | None = None,
    backup_id: str | None = None,
) -> ScaffoldResult:
    """Plan or apply initial local harness creation."""

    root = Path(target_root).resolve()
    ctx = context or _default_context(root)
    harness_exists = (root / ".claude/scripts/harness_cli.py").exists() or (
        root / ".claude/scripts/harness"
    ).exists()
    warnings = []
    if harness_exists:
        warnings.append("error: local harness already exists; use update instead")
    return _plan(
        root,
        mode="init",
        context=ctx,
        apply=apply,
        preflight=preflight,
        backup_id=backup_id,
        warnings=warnings,
    )


def plan_update(
    target_root: Path | str,
    *,
    context: RenderContext | None = None,
    apply: bool = False,
    preflight: PreflightResult | None = None,
    backup_id: str | None = None,
) -> ScaffoldResult:
    """Plan or apply canonical local harness updates."""

    root = Path(target_root).resolve()
    return _plan(
        root,
        mode="update",
        context=context or _default_context(root),
        apply=apply,
        preflight=preflight,
        backup_id=backup_id,
        warnings=[],
    )


def _plan(
    root: Path,
    *,
    mode: str,
    context: RenderContext,
    apply: bool,
    preflight: PreflightResult | None,
    backup_id: str | None,
    warnings: list[str],
) -> ScaffoldResult:
    preflight_result = preflight or check_preflight(_harness_project_root())
    if not preflight_result.ok:
        warnings.extend(f"error: {failure}" for failure in preflight_result.failures())
        return ScaffoldResult(
            mode=mode,
            target_root=str(root),
            dry_run=not apply,
            preflight=preflight_result,
            files=(),
            warnings=tuple(warnings),
        )
    if any(warning.startswith("error:") for warning in warnings):
        return ScaffoldResult(
            mode=mode,
            target_root=str(root),
            dry_run=not apply,
            preflight=preflight_result,
            files=(),
            warnings=tuple(warnings),
        )

    rendered = {
        entry.rel_path: _render_template(entry.template_path, context)
        for entry in CANONICAL_ENTRIES
    }
    backup_name = backup_id or _backup_id()
    files = tuple(
        _file_plan(root, entry, rendered[entry.rel_path], backup_name)
        for entry in CANONICAL_ENTRIES
    )
    if apply:
        _apply(root, files, rendered)
    return ScaffoldResult(
        mode=mode,
        target_root=str(root),
        dry_run=not apply,
        preflight=preflight_result,
        files=files,
        warnings=tuple(warnings),
    )


def _file_plan(
    root: Path,
    entry: TemplateEntry,
    desired: str,
    backup_id: str,
) -> FilePlan:
    path = root / entry.rel_path
    if not path.exists():
        return FilePlan(entry.rel_path, "create", "missing canonical file")
    if path.read_text() == desired:
        return FilePlan(entry.rel_path, "unchanged", "already canonical")
    if entry.preserve_existing:
        return FilePlan(entry.rel_path, "skip", "project-specific file preserved")
    backup = root / ".claude/scripts/.harness-backup" / backup_id / entry.rel_path
    return FilePlan(
        entry.rel_path,
        "update",
        "content differs from canonical template",
        str(backup.relative_to(root)),
    )


def _apply(root: Path, files: Iterable[FilePlan], rendered: dict[str, str]) -> None:
    for file in files:
        target = root / file.path
        if file.action == "skip" or file.action == "unchanged":
            continue
        if file.action == "update" and file.backup_path:
            backup = root / file.backup_path
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(target.read_text())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered[file.path])
        if target.name.endswith(".py"):
            target.chmod(0o755 if target.name in {"harness_cli.py", "project.py"} else 0o644)


def _render_template(template_path: str, context: RenderContext) -> str:
    data = {
        "PROJECT_NAME": context.project_name,
        "BASE_BRANCH": context.base_branch,
        "ISSUE_TRACKER": context.issue_tracker,
        "FORGEJO_REMOTE": context.forgejo_remote,
        "FORGEJO_REPO": context.forgejo_repo,
        "TEMPLATE_VERSION": TEMPLATE_VERSION,
    }
    text = (
        resources.files("harness_core.templates")
        .joinpath(template_path)
        .read_text()
    )
    return Template(text).safe_substitute(data)


def _default_context(root: Path) -> RenderContext:
    repo = ""
    remote = "lab"
    config = _read_flat_yaml(root / ".claude/skill-config.yaml")
    return RenderContext(
        project_name=root.name,
        base_branch=config.get("base_branch", "main"),
        issue_tracker=config.get("issue_tracker", "forgejo"),
        forgejo_remote=config.get("forgejo_remote", remote),
        forgejo_repo=config.get("forgejo_repo", repo),
    )


def _harness_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_flat_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _backup_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness-scaffold")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("init", "update"):
        sub = subparsers.add_parser(mode)
        sub.add_argument("--target", default=".")
        sub.add_argument("--apply", action="store_true")
        sub.add_argument("--project-name")
        sub.add_argument("--base-branch")
        sub.add_argument("--issue-tracker")
        sub.add_argument("--forgejo-remote")
        sub.add_argument("--forgejo-repo")
    args = parser.parse_args(argv)
    context = _context_from_args(args)
    fn = plan_init if args.mode == "init" else plan_update
    result = fn(args.target, context=context, apply=args.apply)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _context_from_args(args: argparse.Namespace) -> RenderContext:
    root = Path(args.target).resolve()
    defaults = _default_context(root)
    return RenderContext(
        project_name=args.project_name or defaults.project_name,
        base_branch=args.base_branch or defaults.base_branch,
        issue_tracker=args.issue_tracker or defaults.issue_tracker,
        forgejo_remote=args.forgejo_remote or defaults.forgejo_remote,
        forgejo_repo=args.forgejo_repo or defaults.forgejo_repo,
    )


def main_init() -> int:
    import sys

    return main(["init", *sys.argv[1:]])


def main_update() -> int:
    import sys

    return main(["update", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
