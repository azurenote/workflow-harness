# Codex host notes

Codex is still a consumer of this skillset. These instructions were **moved here,
not deleted** — they used to sit in each `SKILL.md`, where the Claude Code path
had to read the Codex rules first and then apply a diff against them. The skill
bodies now describe one host-neutral procedure; everything Codex-specific lives
in this file.

Read this file when running these skills under Codex. Under any other host, the
skill body is complete on its own and this file does not apply.

## Invocation

Codex invokes a skill with a `$`-prefixed name:

```
$project-plan <task description>
$project-issue [<plan-path>]
$project-start <issue-id> [worktree] [adr]
$project-done <issue-id> [adr]
$project-adr <issue-id>
$project-clean
$project-iterate <task description> [worktree] [adr]
$project-release
$project-release-doc <package> [<from>..<to>]
$project-harness-init <target-project-root>
$project-harness-update <target-project-root>
```

The skill bodies write these names without the `$`, because the prefix is Codex
call syntax rather than part of the skill's identity. A request such as "use the
project-start skill" triggers the same skill.

## Escalation on sandbox/network failure

When a tracker or git API command (`harness_cli.py`, `project.py`, `gh`, `fj`,
`jira`) fails because of a network or sandbox error, immediately rerun the same
command with `require_escalated`.

This mechanism is Codex-only. Other hosts have no equivalent: there, a failed
call is retried through the documented fallback path, and if it still fails the
agent reports it to the user and stops rather than escalating.

## Subagents

Where a skill says to dispatch independent subagents — one per review role —
Codex uses `multi_agent_v1.spawn_agent`.

Two rules hold regardless of host, and are repeated here because the failure they
prevent is common:

- Never run `codex`, `claude`, or any other LLM CLI **through the shell** to
  create a reviewer. That path repeatedly fails on sandbox permissions and is not
  a fallback.
- If no subagent mechanism is available, or policy disallows it, do not stop. The
  main agent performs each role directly, as separate passes. That is the last
  entry of the execution chain and it always applies.

## `exec_command` quoting

Markdown backticks in a comment body are shell command substitution. When
embedding a finished path directly in an `exec_command` call, wrap the whole body
in single quotes:

```bash
.claude/scripts/harness_cli.py add-comment 326 'ADR recorded: `docs/adr/2026-06-07-blue-green-swap.md`'
```

Passing such a body unquoted, or inside double quotes without escaping, lets the
shell execute the backticked text.
