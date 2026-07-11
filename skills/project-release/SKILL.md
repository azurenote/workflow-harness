---
name: project-release
description: Prepare a Cargo release by analyzing changes from the latest primary-component tag, proposing per-package SemVer bumps, then creating one release commit and annotated package tags after explicit confirmation. Never publishes or pushes. In Codex, run this for `$project-release` or requests such as "use the project-release skill".
---

# project-release - Prepare a Cargo Release

## Trigger Conditions

Apply this skill when Codex receives `$project-release`, or when the user asks to prepare versions, a release commit, and tags for a Cargo workspace. Requests for release notes, deployment plans, or release documents belong to `$project-release-doc`.

## Migration Notice

`$project-release` now mutates local manifests and creates a local release commit and tags. The former document-only workflow moved to `$project-release-doc`. Never silently interpret an old `$project-release` invocation as document generation. If intent is ambiguous, explain the rename and confirm which workflow the user wants.

Recommended order:

1. Run `$project-release` to prepare versions, one commit, and package tags.
2. Run `$project-release-doc` to generate the Korean release/deployment document from those release points.

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first, then read the `release` block. Release mutation requires:

- `release.primary_component`
- `release.tag_format`, containing `{package}` and `{version}` for multi-package workspaces, or `{version}` for a single package
- at least one `release.components.<name>.cargo_package`
- each releasable component's `paths`

Also apply optional `release.components.<name>.release_with`, `release.preflight_paths`, and `release.preflight_commands`. Missing optional keys use the documented safe defaults; missing or ambiguous required keys stop mutation and produce a configuration error.

## Usage

```text
$project-release
```

The skill proposes a range and package plan from configuration. It does not accept an unchecked bump level as authority; every package target is shown for explicit confirmation.

## Output Language Guard

Write the range proposal, SemVer reasoning, confirmation table, failure report, and final report in Korean. Preserve commands, package names, refs, paths, and tags exactly.

## External-effect Guard

- Never run `cargo publish`, `cargo release publish`, `git push`, or any deployment command.
- Pass cargo-release options that prevent publish, push, commit, and tag during version mutation. Git alone creates the single release commit; tag creation happens only after that commit exists.
- Do not modify the repository before the user confirms the complete package plan.
- Never recover with `git reset --hard`, `git clean`, tag deletion, or other destructive commands. On partial failure, stop and report the exact dirty files, commit SHA, and tags that exist.

## Instructions

**1. Preflight the branch and repository**

Before analysis, require all of the following:

```bash
git branch --show-current
git status --porcelain
git fetch --no-tags origin <base_branch>
git merge-base --is-ancestor "origin/<base_branch>" HEAD
cargo metadata --format-version 1 --no-deps
cargo release --version
```

- The current branch must be the configured project `base_branch` (not merely based on it).
- The working tree must be clean.
- `HEAD` must contain `origin/<base_branch>` so a stale local base cannot be released.
- Resolve every configured `cargo_package` to exactly one `cargo metadata` package and record its `manifest_path` and current version.
- Run configured `preflight_commands`. Ignored build artifacts are acceptable, but a command that mutates tracked files or any external system is unsafe and must not run. Inspect every `preflight_paths` file needed for compatibility judgment.

Do not use `git fetch --tags`: historical local tags may intentionally or accidentally differ from the remote, and a broad tag update then blocks an otherwise valid release with `would clobber existing tag`. Base freshness and release-tag discovery are separate checks.

Any violation stops before mutation. Base fetch failure, detached HEAD, missing cargo-release, missing package, duplicate mapping, or an unsafe preflight command is a blocking error.

**2. Resolve the primary range**

Expand `tag_format` for the `primary_component`. Build a version-sorted union of matching local and remote tag names without changing local tags, then select the newest unambiguous tag whose peeled target is reachable from `HEAD`:

```bash
git tag --list "<primary-pattern>" --sort=-version:refname
git ls-remote --tags --refs --sort=-version:refname origin "<primary-pattern>"
# Only when a candidate has no usable local ref:
git fetch --no-tags origin "refs/tags/<candidate-tag>"
REMOTE_TAG_SHA=$(git rev-parse 'FETCH_HEAD^{}')
git merge-base --is-ancestor "<resolved-candidate-sha>" HEAD
```

Resolve each candidate as follows:

- Local and remote refs both exist and peel to the same SHA: use that SHA.
- Local-only ref: use its peeled SHA and warn that the previous release tag has not been pushed. Local-only tags are valid because this skill intentionally never pushes.
- Remote-only ref: explicitly fetch that one ref without a destination, peel `FETCH_HEAD`, and use the fetched SHA. The fetch may write `FETCH_HEAD` and downloaded objects but must not create or overwrite `refs/tags/<candidate-tag>`.
- Local and remote refs have the same name but peel to different SHAs: if it is the newest reachable candidate, stop for explicit resolution. Never guess which history is authoritative and never rewrite or delete either tag. Older conflicting names that fall below an already selected newer unambiguous tag are warnings, not blockers.

Check union candidates in version order and skip unreachable targets. This preserves an unpushed tag created by a prior `$project-release` run while avoiding the broad-fetch `would clobber existing tag` failure.

The proposed human-readable range is `<latest-reachable-primary-tag>..HEAD`, but all `git log` and `git diff` commands use the resolved immutable `<FROM_SHA>..HEAD`. Resolve `HEAD` to its full SHA for the confirmation screen and show the tag name, source (`local`, `remote`, or `both`), and peeled SHA. Do not choose an unreachable tag even if its version is higher.

If the remote lookup or an explicit remote-only candidate fetch fails, stop before mutation. Only when neither namespace has a matching tag may the workflow mark this as a first release and propose the repository root commit as the lower bound. If matching tags exist but none is reachable, stop and report the candidates instead of silently treating the repository as a first release. If tags do not match configured package/version parsing, or the latest version is a prerelease, stop and ask the user to resolve the ambiguity; do not guess stable/prerelease policy.

**3. Investigate changes and propose SemVer levels**

For the full range and for every configured component path, inspect commit subjects, names, stats, and relevant full diffs:

```bash
git log --oneline --no-merges <from_sha>..HEAD
git diff --name-status <from_sha>..HEAD -- <paths...>
git diff <from_sha>..HEAD -- <paths...>
```

Classify each component as `major`, `minor`, `patch`, or `skip` with concrete commit/path evidence:

- `major`: public compatibility break, schema/serialization break, or required incompatible consumer change
- `minor`: backward-compatible public feature or additive schema/API capability
- `patch`: backward-compatible bug, security, performance, or internal behavior correction
- `skip`: no direct change and no configured coupling/dependency reason to release

Conventional Commit prefixes are supporting evidence only. File counts and diff size never determine the level. Mark uncertain classifications as `미확정`; they cannot execute until the user explicitly selects a level.

Apply `release_with` coupling after direct classification. A coupled package may be included without direct changes, but its reason must name the triggering package and policy. Independent packages retain their own level. Do not force all versions or levels to match the primary component.

**4. Compute and confirm the immutable release plan**

Compute each next version from its own current version. Before any write, show one Korean confirmation screen containing:

- primary component, resolved `<from>..<HEAD-SHA>` range, base branch, and change summary
- package/component, manifest path, current version, proposed `major|minor|patch|skip`, next version, evidence/reason, and planned tag
- expected mutation allowlist: selected manifests and `Cargo.lock`
- explicit statements that exactly one commit and local annotated tags will be created, while publish and push will not occur

Ask the user to confirm or edit every target. Recompute versions and tags after edits. No confirmation means no mutation.

**5. Dry-run every level group**

Group confirmed packages by level and run `cargo release version` in dry-run mode for each group using explicit `--package` arguments and guards equivalent to `--no-publish`, `--no-push`, `--no-commit`, and `--no-tag`. Use the installed cargo-release version's documented flags; inspect `cargo release version --help` rather than guessing when flags differ.

Dry-run all groups before executing any group. A dry-run that proposes a package, version, tag, manifest, or dependency update outside the confirmed plan stops the workflow and returns to confirmation.

**6. Execute version changes without commit, tag, publish, or push**

Run the same validated level groups with `cargo release version --execute`, retaining the no-publish/no-push/no-commit/no-tag guards. Mixed levels are separate **version-only** invocations; never run `cargo release <level> --execute` in a way that commits each group.

After all groups, regenerate or update `Cargo.lock` using the workspace's normal Cargo command if cargo-release did not do so. Then verify:

- every selected manifest has exactly the confirmed version;
- dependency version propagation matches the confirmed package plan;
- changed files are exactly the allowlisted manifests and `Cargo.lock`;
- no tag or commit was created during version execution.

Unexpected packages or files stop before commit/tag. Report the dirty state and request a revised plan; do not automatically revert it.

**7. Create exactly one release commit**

Stage only the verified allowlist and create one commit with Git:

```bash
git add -- <confirmed manifests...> Cargo.lock
git diff --cached --check
git commit -m "chore(release): prepare package releases"
```

Record `RELEASE_SHA=$(git rev-parse HEAD)` and verify the commit's changed-file list equals the allowlist. `git commit` is invoked exactly once. cargo-release does not own commit creation for a mixed-level release.

**8. Create and verify annotated tags**

Before creating any tag, verify every planned tag is absent locally and from the fetched remote tag namespace. For each selected package, inspect `cargo release tag --help`, then run its dry-run and execute forms with the explicit package and configured tag name. Disable push and publish in both configuration and command flags. The cargo-release tag step must create an annotated tag at the current `RELEASE_SHA`; if the installed version cannot express the confirmed tag exactly, stop and report the incompatibility instead of silently switching tools.

Verify each peeled tag target:

```bash
test "$(git rev-parse '<tag>^{}')" = "$RELEASE_SHA"
```

Do not push tags. If any tag creation or verification fails, stop immediately and report which tags exist and which remain. Do not delete already-created tags automatically. `git tag -a` may be shown only as a manual recovery choice after stopping; it is not the normal automated path.

**9. Failure and edge-case handling**

- No changed or coupled packages: report `변경 없음` and exit without commit/tag.
- Existing target tag: stop before mutation when discovered in preflight; if discovered later, stop and report state.
- First release: require explicit confirmation of the root-commit range and initial version targets.
- Prerelease or non-SemVer current version/tag: stop for explicit policy input.
- Any command failure: never continue to later mutation phases and never publish, push, deploy, or destructively roll back.

**10. Output**

Report in Korean:

- resolved range and evidence summary
- each package's old/new version and bump reason
- release commit SHA and the fact that exactly one commit was created
- every annotated tag and verified target SHA
- explicit `publish: 수행하지 않음`, `push: 수행하지 않음`
- dirty files, created commit/tags, and manual recovery choices when partially failed
- next step: run `$project-release-doc` to create the release/deployment document

## Mixed-level Example

This is a contract sample, not a project default:

```text
range: backend-v1.0.2..864b825
backend: 1.0.2 -> 1.1.0 (minor)
domain: 1.0.2 -> 1.1.0 (minor)
entity: 1.0.2 -> 1.1.0 (minor)
migration: 1.0.2 -> 1.1.0 (minor)
auth-lambda: 1.0.1 -> 1.0.2 (patch)
commit_count: 1
publish: false
push: false
```
