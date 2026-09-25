---
name: project-issue
description: Register `plan-draft-<slug>.md` or an existing `plan-<uuid>.md` draft as a ticket in the issue tracker, then rename it to `plan-<id>.md`.
---

# project-issue - Register Issue

## Trigger Conditions

Apply this skill in the following situations:
- The user invokes `project-issue`, or asks to use the project-issue skill to register an issue
- The user invokes `project-issue <plan-path>`, naming the draft file to register
- A `plan-draft-*.md` or `plan-<uuid>.md` draft exists and issue-registration intent is detected
- Keywords such as "register issue", "create ticket", "upload to GitHub", or "upload to Jira"

## Read Settings

Run the "Read Settings" procedure in `~/.claude/skills/SKILL-CONFIG.md` first.

That document holds the common contract only. This skill additionally reads:

- `~/.claude/skills/_shared/references/base-branch.md` — per-task base branch precedence
- `~/.claude/skills/_shared/references/github-issue-fields.md` — issue metadata contract. Written for `issue_tracker: github`; Step 4 and the Forgejo branch reuse its label rule, so forgejo reads it too.

Read nothing else from the reference set; the rest does not apply here.

## Output Language Guard

Issue bodies created by this skill must preserve the plan file exactly as written.
Because `project-plan` writes plan prose in Korean by default, do not translate or summarize the plan body into English during issue creation. Upload the Korean plan with `--body-file` as-is, including frontmatter.

## Usage

```
project-issue [<plan-path>]
```

- `[<plan-path>]`: the draft plan file to register. Optional.
  - **Omitted** — Step 1 discovers the draft exactly as it always has. Nothing about that path changes.
  - **Given** — Step 1 does not run discovery at all. It validates this path and uses it.

The argument exists for the case discovery cannot resolve on its own: two or more drafts present.
The harness path raises `MultiplePlanFilesError` outright; the harness-free path can still ask, but
only interactively. Naming the file settles it in one step, and settles it non-interactively.

## Instructions

**1. Detect Draft File**

When the call carried a `<plan-path>` argument, do not run discovery. Validate that path instead:

```bash
# The path is a single literal argument. Never interpolate it into a double-quoted
# shell assignment first: `PLAN_PATH="<plan-path>"` would run any `$(...)` or backtick
# the user typed, before python ever sees it.
DRAFT_PLAN="$(python -c '
import sys
from pathlib import Path
from harness_core.config import is_draft_plan
from harness_core.git import main_worktree_root
from harness_core.local import abs_under_main

path = abs_under_main(Path(sys.argv[1])).resolve()
plan_dir = (main_worktree_root() / ".task" / "plan").resolve()
if not path.is_file():
    sys.exit("reject (exists): no such file: %s" % path)
if not is_draft_plan(path.name):
    sys.exit("reject (is_draft_plan): not a draft plan name: %s" % path.name)
if path.parent != plan_dir:
    sys.exit("reject (plan dir): %s is not %s" % (path.parent, plan_dir))
print(path)
' '<plan-path>')"
```

- An explicit path is accepted only when it passes all three checks — the file exists, its name passes `is_draft_plan`, and its parent is the plan directory — and on any failure this skill reports which of the three failed and stops, never falling back to discovery.

The command exits non-zero and names the failed check, so a caller can branch on it. It prints the
**resolved** path and the rest of this skill uses that value — validating one path and then renaming
another is how a symlink lands Step 8's `mv` outside the plan directory.

`abs_under_main` and `main_worktree_root` are why the plan directory is not `Path(".task/plan")`:
`.task/plan/` is gitignored, so it exists only in the **main worktree**. Resolving against the CWD
rejects every valid path when this skill runs from a linked worktree (`harness_core/local.py`
records the same fix as plan-234).

Why each check is load-bearing:

- **Name check** — it is the only gate protecting Step 8's `mv`. Accept an arbitrary path here and Step 8 renames a file that was never a draft.
- **Plan-directory check** — the harness-free `mv` in Step 8 hardcodes `.task/plan/` as its destination, while the harness path renames next to the source file. A path outside the plan directory makes the same input land in two different places depending on `harness_enabled`.
- **Stopping** — falling back to discovery would hand back the very ambiguity the argument was given to settle.

Without the argument, discover the draft as before.

When `harness_enabled: true`:
```bash
<harness_cli> find-draft-plan
```

Otherwise (or when no harness exists):
```bash
python -c 'from pathlib import Path; from harness_core.config import is_draft_plan; print("\n".join(str(p) for p in sorted(Path(".task/plan").glob("plan-*.md")) if is_draft_plan(p.name)))'
```

The fallback also uses `harness_core.config.is_draft_plan` as the single contract. Valid draft file names are only `plan-draft-<lowercase-slug>.md` or lowercase hex UUID `plan-<uuid>.md`.

Handle the result:
- **No files**: tell the user to run `project-plan` first. Stop.
- **One file**: use that file.
- **Two or more files**: show the list and mtimes, then ask the user to choose.
  - If the user says "latest", automatically choose the file with the newest mtime.

**2. User Confirmation**

Show the file title, base branch, and first 30 body lines, then **always get confirmation**.
Do not create an issue without confirmation. This checkpoint is not just filename/title confirmation; it is a human-layer approval checkpoint. The user must review `Intent Summary`, `Current State`, `Target State`, `Non-Goals`, and `Drift Guards` and confirm that the work intent is correct.
The preview shows leading frontmatter as-is (`read_plan_preview`), so if the plan declares `base_branch`, explicitly name the merge target branch at confirmation time. If there is no frontmatter, show the project default base from `.claude/skill-config.yaml`.

```
file: <draft-plan-path>
title: <text after # Plan:>          # the real title, not '---', even with frontmatter (frontmatter-aware)
base branch: <frontmatter base_branch value, or "<project default base> (default)">
human preview: <full frontmatter + first 30 body lines>

Are the Intent Summary and base branch correct? Create an issue from this file? [yes/no]
```

> Plan frontmatter (`base_branch`/`parent_issue`) is propagated to the issue without any extra work: Step 6 uploads the entire plan file as the issue body with `--body-file`, and Step 8 renames without changing content, preserving frontmatter. Title inference (`--title`) and type/label inference use a frontmatter-aware parser, so the leading `---` block does not affect them.

**3. Infer Issue Type** (GitHub only)

Analyze the plan title and `Intent Summary` / `Current State` keywords:

| Condition | Type |
|------|------|
| `bug`, `fix`, `modify`, `bug`, `error` | `Bug` |
| `feat`, `add`, `improve`, `implement`, `introduce`, `feature` | `Feature` |
| otherwise | `Task` |

Bug keywords take priority. If the title is clear, skip body analysis.

The inferred name must be one the repository actually defines. The harness path validates it and refuses an unknown one before creating anything. On the gh path there is no `--json` field for it — `gh issue view --json` does not return the issue type — so read the repository's types with the `gh api graphql` query in the reference, or the repository's issue-type settings. Never guess: REST silently drops a `type` the token cannot set, so an unverified guess produces an untyped issue that reports as success.

**4. Infer Labels** (GitHub and Forgejo)

Analyze "Files to modify" in `Scope`, or "Files / Modules" in `Task Cards`:

| Condition | Labels |
|------|--------|
| `backend/`, `entity/`, or `migration/` path | `["BE"]` |
| `frontend/`, `.tsx`, `.ts`, or `.css` | `["FE"]` |
| both sides | `["BE", "FE"]` |
| unclear | `["BE"]` (default) |

- Never encode type, priority, or size as a label; labels carry area tags only.

That rule is the whole point of the metadata contract, and the reserved names are not a list to memorize — they are derived at runtime from the repository's issue types and the project's field options. See `~/.claude/skills/_shared/references/github-issue-fields.md`.

**5. Infer Priority / Size** (GitHub only)

These are project field values, decided **before** the issue is created so one call can apply them.

| Type | Priority |
|------|----------|
| Bug + critical/urgent | P0 |
| Bug | P1 |
| Feature | P1 |
| Task | P2 |

| Task count | File count | Size |
|---------|---------|------|
| 1-2 | 1-2 | XS |
| 2-3 | 2-4 | S |
| 3-5 | 3-6 | M |
| 5-8 | 5-10 | L |
| 8+ | 10+ | XL |

The names above are this project's option names as an example; use whatever the project's fields actually offer. A value the field does not have is rejected with the available options listed.

**6. Create Issue**

Branch by `issue_tracker` value:

### GitHub (`issue_tracker: github`)

One call. Type, labels, priority, size and the initial project status are applied together, so there is no second call to forget:

```bash
DRAFT_PLAN="<draft-plan-path>"
<harness_cli> create-issue \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN" \
  --type "<Type>" \
  --label "<area tag>" \
  --priority "<Priority option>" \
  --size "<Size option>"
```

Exit codes:

- **0** — created. The JSON on stdout carries `number`, `node_id`, `url`, `requested`, `observed` and `drift`.
- **2** — refused *before* creating anything. Nothing exists. Two kinds, and they need different responses: a **bad argument**, which you fix and run again; and an **environment refusal** — the project board could not be read, so a label cannot be told apart from a field value. Re-running an environment refusal changes nothing. Report it.
- **3** — the issue exists but its fields did not all apply.
- **4** — the create request failed and it is **not known** whether the issue exists. The server may have committed it before the connection dropped.

- On exit 3 the issue already exists: never re-run create-issue; run set-fields <number> instead.
- On exit 4 do not run create-issue again until you have searched the repository for the title: a blind re-run is how one plan becomes two issues.
- An environment refusal (2) or an unknown outcome (4) is **not** "the harness call failed": the judgement ran and answered. Do not drop to the bare `gh` fallback, which carries no reserved-label check at all.

Read `number` (ISSUE_NUMBER) and `node_id` (ISSUE_NODE_ID) from the output.

`add-backlog` is not part of this path. Call it on its own only after a deliberate `--no-project` creation, when the issue is later added to the board.

When `harness_enabled: false`:

```bash
DRAFT_PLAN="<draft-plan-path>"
gh issue create \
  --title "<plan title>" \
  --body-file "$DRAFT_PLAN" \
  --type "<Type>" \
  --label "<area tag>"
```

Then set the project fields on the created issue URL:

```bash
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.priority>" --value "<Priority option>"
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.size>" --value "<Size option>"
```

If the issue is not on the board yet, `gh project item-add <github_project.number> --owner <github_project.owner> --url <issue-url>` first. If these flags are unavailable (gh older than 2.97.0) or the token lacks the `project` scope, use the `gh api graphql` form in the reference. If that also fails, report the fields as **not applied** and continue — do not put the values in labels.

### Jira (`issue_tracker: jira`)

```bash
DRAFT_PLAN="<draft-plan-path>"
jira issue create \
  --project "<jira_project>" \
  --type "<Type>" \
  --summary "<plan title>" \
  --template "$DRAFT_PLAN" \
  --no-input \
  --raw
```

- **`jira issue create` has no `--description` flag.** Measured against the installed CLI (1.7.0): the body flags it accepts are `-b,--body` and `-T,--template`. Cobra aborts on an unknown flag, so a `--description` form does not degrade — it dies on the first call.
- **`--template` closes a second problem at the same time**: it hands over the file instead of expanding the plan body on a command line, and plan bodies are full of backticks and `$`.
- ★ **`-b/--body` wins over `--template`** (the CLI's own `EXAMPLES` say so). If someone later adds `-b` for convenience, the template is ignored **without a word** — the same silent precedence this skill guards against elsewhere.
- **Pass the type inferred in Step 3.** The keyword matching in that step reads the plan, not the tracker, so running it on this path is sound even though its heading says "GitHub only". What is *not* portable is the vocabulary it emits: `Bug` / `Feature` / `Task` are GitHub's names, and Jira issue types are defined per project — `Feature` is not one of Jira's defaults. Map the inferred name onto a type the target project actually defines, the same way the GitHub path requires a type the repository defines. Do not hardcode a type in this call, and do not send an unmapped one.
- **`--raw` returns the API response as JSON.** Read the issue key out of that response — for example `SYN-42`. Which field carries it is **not verified here** (see the limitation below), so do not write a field name into this document as though it were confirmed.
- **`--no-input` is the flag that keeps this call unattended, and it is required.** It suppresses the prompts for non-required fields, the description editor among them; drop it and `--template` alone still opens `$EDITOR` pre-filled with the file, which blocks an unattended run indefinitely. Both flags are load-bearing and neither substitutes for the other.

Then read the issue back before reporting anything about it, using the key from that response as `<TICKET_ID>` — the same name Step 8 consumes:

```bash
jira issue view "<TICKET_ID>" --raw
```

Compare the summary, type and project on the response with what was sent. This read-back stays **inside this section** — Step 7 is the GitHub path and is not generalized to cover other trackers.

> Limitation: this skillset's own repo has no Jira project. Both calls above were checked against the installed CLI's flag surface and this document's internal consistency, and neither has been executed against a live Jira. Anything reported from this path should carry that qualification rather than read as verified.

### Forgejo (`issue_tracker: forgejo`)

**이 CLI 에서 종료코드와 stdout 은 효과의 증거가 아니다 — 읽기 확인이 증거다.**

이 원칙에 매다는 조용한 실패가 둘이다. 서로 다른 사고지만 뿌리가 같아서, 따로 경고하는 대신 원칙을 먼저 세우고 사례로 내린다.

1. **빈 이슈 번호** — 생성 성공 출력의 번호가 양방향 격리 문자로 감싸여 있어, 순진한 파싱이 에러 없이 **빈 문자열**을 돌려준다.
2. **적용되지 않은 라벨** — 존재하지 않는 라벨은 종료코드 **0**, stderr **0 바이트**로 끝나고 경고는 stdout 으로만 나간다. 성공이 침묵하고 실패가 말하므로 `$?` 로도, "출력이 있었나" 로도 가를 수 없다 — 후자는 판정이 아예 뒤집힌다.

harness 분기는 없다. forgejo 어댑터가 존재하지 않으므로 `harness_enabled` 값과 **무관하게** `fj` 직접 호출이 유일한 경로다. 전역 옵션(`-H`, `-C`, `--style`)은 서브커맨드 **앞**에 온다. 버전 확인 명령(`fj version`)과 최소 버전은 `~/.claude/skills/dependencies.yaml` 이 선언한다 — 여기서 추측하지 않는다.

생성을 먼저 잡고, 번호는 그 출력에서 읽는다. 격리 제거가 그 추출의 한 단이다:

```bash
DRAFT_PLAN="<draft-plan-path>"
# Repo targeting: -r <forgejo_repo> as below, or -R <forgejo_remote> when the project
# declares a remote that actually exists locally. Both are accepted by create/search/edit.
TITLE="$(sed -n 's/^# Plan: //p' "$DRAFT_PLAN" | head -1)"
CREATED="$(fj -H <forgejo_host> issue create "$TITLE" --body-file "$DRAFT_PLAN" -r <forgejo_repo> --no-template)" || CREATE_FAILED=1
ISSUE_NUMBER="$(printf '%s\n' "$CREATED" \
  | python3 -c 'import sys; sys.stdout.write(sys.stdin.read().replace("\u2068", "").replace("\u2069", ""))' \
  | sed -n 's/^created issue #\([0-9][0-9]*\).*/\1/p')"
```

- 격리 제거(`\u2068`/`\u2069`)는 군더더기가 아니다. 파이프 한 단으로 두고 **추출보다 앞에** 둔다 — 뒤에 두면 추출이 영영 매치하지 않는다. 빼면 `#` 와 첫 숫자 사이에 격리 문자가 끼어 추출이 **에러 없이 빈 문자열**을 돌려주고, 그 빈 값이 8단계 `mv` 로 흘러들어 `plan-.md` 를 만든다. 실패가 조용하다는 것이 이 단계를 지켜야 하는 이유다.
- `--style minimal` 이 격리 문자를 없애줄 것이라고 기대하지 마라. 도움말의 "Always used in non-terminal contexts (i.e. pipes)" 가 그렇게 읽히지만, 파이프 출력에도 격리 문자는 **그대로 있다**.
- **제목을 명령문에 리터럴로 붙여넣지 마라.** 파일에서 읽어 `"$TITLE"` 로 넘긴다. 셸은 파라미터 확장 결과를 다시 훑지 않으므로 따옴표 씌운 변수는 백틱이 들어 있어도 안전하다 — 위험한 것은 **리터럴**이다. `project-plan` 제목은 파일·심볼을 백틱으로 부르는 것이 상례라 이건 예외가 아니라 기본이다. 작은따옴표로 감싸는 것도 해결이 아니다: 제목 안의 아포스트로피 하나가 따옴표를 닫고 뒤따르는 백틱을 실행시키며, 그때 `--body-file` 이 빈 값을 받아 `$EDITOR` 가 열린다.
- `--body-file` 은 선택이 아니다. `--body` 와 함께 빠지면 `$EDITOR` 가 열려 헤드리스에서 멈춘다. 한국어 플랜을 있는 그대로 올린다는 계약도 이 플래그가 지킨다.
- `--web` 은 브라우저를 여는 플래그다. 자동 경로에서 쓰지 않는다 — "웹에서 확인하려면" 같은 안내로도 넣지 않는다.
- `--no-template` 은 템플릿 선택 상호작용을 막는다. blank issue 를 막은 저장소에서는 이 형태가 실패하므로, 그때 `fj issue templates` 로 목록을 얻어 `--template <T>` 로 재시도한다. **이 재시도 경로는 미검증이다** — 실측한 저장소에 템플릿이 없어 겪지 못했다.

- **생성 실패와 파싱 실패를 한 덩어리로 다루지 마라.** `"$(a | b | c)"` 의 종료코드는 `c` 의 것이라, 파이프라인 하나로 합치면 `fj` 가 죽어도 종료코드 0 에 빈 번호가 나와 **파싱 실패와 구별되지 않는다**. 위처럼 생성을 먼저 잡아 `CREATE_FAILED` 로 갈라둔다.

두 경우의 복구가 다르다. 갈라두는 이유가 이것이다:

- `CREATE_FAILED` — 이슈는 **만들어지지 않았다**. 아래 웹 UI 마지막 단으로 간다. 여기서 검색으로 번호를 찾으려 하지 마라.
- 생성은 됐는데 `$ISSUE_NUMBER` 가 비었다 — 번호만 못 읽은 것이므로 방금 만든 제목으로 찾는다. 번호 없이 8단계로 넘어가지 않는다:

```bash
fj -H <forgejo_host> --style minimal issue search -r <forgejo_repo> "$TITLE"
```

`issue search` 는 기본이 `-s open` 인 자유 텍스트 검색이다. 제목이 비슷한 기존 열린 이슈가 있으면 **엉뚱한 번호가 잡힌다** — 생성 실패 경로에서 이걸 쓰면 안 되는 이유이고, 여기서도 잡힌 번호의 제목을 눈으로 대조한 뒤 쓴다. 이 출력 형식은 미검증이므로 create 용 파서를 돌리지 않는다.

라벨은 4단계에서 이미 추론한 area 태그를 재사용한다. `fj` 의 create 에는 라벨 플래그가 없으므로 생성 후 두 번째 호출로 적용한다 — GitHub 절이 한 번의 호출을 고집하는 것과 갈리는 이유는 도구 표면의 차이이지 절차 설계의 선택이 아니다:

```bash
fj -H <forgejo_host> issue edit "<forgejo_repo>#$ISSUE_NUMBER" labels -a "<area tag>"
```

- 4단계가 태그를 둘 추론하면(`["BE", "FE"]`) `-a` 를 태그마다 하나씩 준다. 쉼표로 묶은 `-a "BE,FE"` 는 **측정된 적 없고**, 틀렸다면 없는 라벨 취급을 받아 종료코드 0 으로 조용히 무시된다. 어느 쪽이든 판정은 아래 읽기 확인이다.

- 대상 저장소는 이슈를 `<forgejo_repo>#<N>` 형태로 주어 지정한다. `fj issue edit ... labels` 에는 `--repo` 가 **없고**, 거기서 `-r` 은 `--rm`(라벨 제거)이다. `create` 의 `-r`(`--repo`)과 같은 글자가 반대 의도를 갖는다 — 저장소 지정으로 잘못 쓰면 라벨이 조용히 지워진다.
- 라벨 적용은 아래 읽기 확인으로만 확증된다. 붙지 않았으면 그 라벨을 **미반영**으로 보고한다.
- Forgejo 의 area 태그는 **best-effort** 다. `fj` 에는 저장소 라벨을 열거할 수단이 없어(최상위 `label` 서브커맨드 자체가 없다) 무엇이 유효한지 볼 수 없다. 한 번 시도하고, 읽어서 확인하고, 안 붙었으면 미반영으로 보고한다 — 없는 라벨을 새로 만들어 채우지 않는다.

type·priority·size 는 `fj` 에 대응 플래그가 없다. 셋 다 **미반영**으로 보고하고 9단계 출력에 싣는다. 4단계가 세운 규칙이 여기에도 그대로 걸린다 — 이 셋을 area 태그에 실어 보내는 우회는 금지다. 근거는 `~/.claude/skills/SKILL-CONFIG.md` 의 폴백 원칙과 `~/.claude/skills/_shared/references/github-issue-fields.md` 이며, 여기에 복제하지 않고 가리킨다. 미반영은 오류 상태가 아니라 Forgejo 의 정상 결과다.

읽기 확인. 조회 형태는 `~/.claude/skills/SKILL-CONFIG.md` 의 기존 조회 계약을 그대로 재사용한다 — 새 형태를 발명하지 않는다:

```bash
# forgejo (read path - see "이슈 트래커" in SKILL-CONFIG.md)
fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#$ISSUE_NUMBER"
```

- 확인할 일은 둘이다: 이슈가 실재하는지, 그리고 라벨이 실제로 붙었는지. 위 원칙 때문에 라벨은 여기 말고 확인할 데가 없다.
- create 용 번호 파서를 이 확인에 재사용하지 않는다. view 는 번호가 제목 **뒤**에 오고 격리 문자가 중첩되거나 빈 채로 섞인다. 하나의 파서로 둘을 다루면 둘 다 부서진다 — 여기서는 번호를 다시 파싱하는 것이 목적이 아니므로 격리 문자에 관대하게 읽는다.
- 격리 제거를 라벨 줄에까지 확장하지 마라. 라벨은 자기 줄에 **평문**으로 찍힌다. 격리 제거는 감싸인 필드(번호·제목·작성자·상태)에만 쓰는 **국소 처리**이지 모든 `fj` 출력에 거는 일괄 처리가 아니다. 반대로 라벨이 평문인 것을 보고 "fj 출력에는 격리 문자가 없다" 고 일반화해서도 안 된다. 두 과잉 적용이 모두 틀렸다.
- 올바른 표면을 읽어라. `fj issue view <ID>` 는 기본이 `body` 라서 **코멘트를 보여주지 않는다**; 코멘트는 `fj issue view <ID> comments` 다. 이 절은 라벨만 확인하므로 기본 표면으로 충분하지만, 엉뚱한 표면을 읽으면 쓰기가 실패한 것과 똑같이 보인다.
- `fj issue edit <N> body` 에는 `--body-file` 이 없다 — 본문은 위치 인자뿐이라 **파일 기반 갱신 경로가 없다**. 플랜을 있는 그대로 올린다는 것은 생성 시점의 계약이고, 등록된 뒤 로컬 파일과 이슈 본문이 갈라지면 되돌리기가 비싸다. 처음 올리는 것이 정확해야 하는 이유가 하나 더 있는 셈이다.

`fj` 쓰기 경로가 실패했을 때의 마지막 단은 웹 UI 수동 등록이며, 그 규칙은 `~/.claude/skills/SKILL-CONFIG.md` 의 "이슈 트래커" 절이 갖는다 — 여기에 복제하지 않는다. 사람이 돌려준 번호만 있으면 8단계는 그대로 진행된다.

8단계 rename 은 GitHub 과 같은 `plan-<ISSUE_NUMBER>.md` 규칙을 쓴다. forgejo 도 정수 이슈 번호이므로 새 분기를 만들지 않는다.


**7. Read Back** (GitHub only)

Before reporting, read what is actually on the issue:

```bash
<harness_cli> get-issue <ISSUE_NUMBER>
# fallback (GitHub): gh issue view <ISSUE_NUMBER> --json number,title,url,labels
```

On the gh path, `gh issue view --json` does not return the issue type or the project fields; add `gh project item-list <github_project.number> --owner <github_project.owner> --format json` for the fields, or use the reference's GraphQL query for both at once.

A `create-issue` exit of 0 already includes this read in its `observed`; repeat it only on the gh path.

**8. Rename File**

After issue creation succeeds:

```bash
DRAFT_PLAN="<draft-plan-path>"
# GitHub
mv "$DRAFT_PLAN" .task/plan/plan-<ISSUE_NUMBER>.md

# Jira
mv "$DRAFT_PLAN" .task/plan/plan-<TICKET_ID>.md
# example: plan-SYN-42.md
```

Idempotency: if the destination file already exists, skip the rename.
If rename fails: keep the draft file and ask the user to enter the issue ID manually.

When a harness exists:
```bash
DRAFT_PLAN="<draft-plan-path>"
<harness_cli> rename-plan "$DRAFT_PLAN" <ISSUE_NUMBER>
```

**9. Output**

- issue number / URL, or Jira ticket ID
- issue title
- **observed** Type / Labels / Priority / Size — the values read back in Step 7, not the values inferred in Steps 3-5. Where they differ, report both and say which is which.
  - On forgejo the only observable one is Labels, and it is observable only through the read-back in the Forgejo section. Type, Priority and Size have no field to land in there, so report all three as 미반영 — that is the normal result, not a failure.
- anything reported as not applied, and the command that would apply it later
- file rename result: `<draft-plan-path>` -> `plan-<id>.md`
- next step: `project-start <issue-number>`
