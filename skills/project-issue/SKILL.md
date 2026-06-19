---
name: project-issue
description: plan-draft-*.md 파일을 이슈 트래커(GitHub/Jira)에 티켓으로 등록하고, plan-draft-<slug>.md를 plan-<id>.md로 rename한다. Codex에서는 `$project-issue` 또는 "project-issue 스킬로 ..." 요청 시 실행.
---

# project-issue — 이슈 등록

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- Codex에서 `$project-issue` 또는 "project-issue 스킬로 이슈 등록" 형태로 요청할 때
- `plan-draft-*.md` 파일이 존재하고 이슈 등록 의도가 감지될 때
- "이슈 등록", "티켓 생성", "깃허브에 올려", "jira에 올려" 키워드

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Instructions

**1. Draft 파일 탐지**

`harness_enabled: true` 인 경우:
```bash
<harness_cli> find-draft-plan
```

그 외 (또는 harness 없는 경우):
```bash
ls .task/plan/plan-draft-*.md 2>/dev/null
```

결과 처리:
- **파일 없음**: `$project-plan` 먼저 실행하라고 안내. 중단.
- **1개**: 해당 파일 사용.
- **2개 이상**: 목록과 mtime을 보여주고 사용자에게 선택 요청.
  - 사용자가 "최근 것"이라고 하면 mtime 가장 최신 파일 자동 선택.

**2. 사용자 확인**

파일 제목과 첫 30줄을 보여준 후 **반드시 확인**을 받는다.
확인 없이 이슈를 생성하지 않는다. 미리보기에는 선두 frontmatter가 그대로 노출되므로(`read_plan_preview`), 플랜이 `base_branch`를 선언했다면 **머지 타겟 브랜치를 확인 시점에 사람에게 명시**한다.

```
파일: .task/plan/plan-draft-<slug>.md
제목: <# Plan: 이후 텍스트>          # frontmatter가 있어도 '---' 가 아닌 실제 제목 (frontmatter-aware)
base branch: <frontmatter base_branch 값 — 없으면 "develop (default)">
미리보기: <첫 30줄 (frontmatter 포함)>

이 파일로 이슈를 생성합니까? [yes/no]
```

> 플랜 frontmatter(`base_branch`/`parent_issue`)는 **별도 작업 없이** 이슈에 전파된다 — Step 5의 `--body-file` 이 플랜 파일 전체를 이슈 본문으로 올리고, Step 7의 rename 은 내용을 바꾸지 않아 frontmatter 가 보존된다. 제목 추정(`--title`)·type/label 추정은 frontmatter-aware 파서를 쓰므로 선두 `---` 블록에 영향받지 않는다.

**3. 이슈 타입 판단** (GitHub 전용)

플랜 제목과 Background 키워드 분석:

| 조건 | Type |
|------|------|
| `bug`, `fix`, `수정`, `버그`, `오류` | `Bug` |
| `feat`, `추가`, `개선`, `구현`, `도입`, `기능` | `Feature` |
| 그 외 | `Task` |

Bug 키워드 우선. 제목에서 명확하면 Background 생략.

**4. 레이블 판단** (GitHub 전용)

Scope의 "Files to modify" 분석:

| 조건 | Labels |
|------|--------|
| `backend/`, `entity/`, `migration/` 경로 | `["BE"]` |
| `frontend/`, `.tsx`, `.ts`, `.css` | `["FE"]` |
| 양쪽 모두 | `["BE", "FE"]` |
| 판단 불가 | `["BE"]` (기본값) |

**5. 이슈 생성**

`issue_tracker` 값에 따라 분기:

### GitHub (`issue_tracker: github`)

`harness_enabled: true` 인 경우:
```bash
<project_py> create-issue \
  --title "<플랜 제목>" \
  --body-file ".task/plan/plan-draft-<slug>.md" \
  --type "<Bug|Feature|Task>" \
  --label "<BE|FE>"
```

`harness_enabled: false` 인 경우:
```bash
gh issue create \
  --title "<플랜 제목>" \
  --body-file ".task/plan/plan-draft-<slug>.md"
```

출력에서 `number` (ISSUE_NUMBER), `node_id` (ISSUE_NODE_ID) 획득.

### Jira (`issue_tracker: jira`)

```bash
jira issue create \
  --project "<jira_project>" \
  --summary "<플랜 제목>" \
  --description "$(cat .task/plan/plan-draft-<slug>.md)" \
  --type Task
```

출력에서 티켓 ID (예: `SYN-42`) 획득.

**6. Priority / Size 추정** (GitHub 전용)

| Type | Priority |
|------|----------|
| Bug + critical/urgent | P0 |
| Bug | P1 |
| Feature | P1 |
| Task | P2 |

| Task 수 | 파일 수 | Size |
|---------|---------|------|
| 1–2 | 1–2 | XS |
| 2–3 | 2–4 | S |
| 3–5 | 3–6 | M |
| 5–8 | 5–10 | L |
| 8+ | 10+ | XL |

```bash
<project_py> add-backlog "<ISSUE_NODE_ID>" --priority <P0|P1|P2> --size <XS|S|M|L|XL>
```

**7. 파일 Rename**

이슈 등록 성공 후:

```bash
# GitHub
mv .task/plan/plan-draft-<slug>.md .task/plan/plan-<ISSUE_NUMBER>.md

# Jira
mv .task/plan/plan-draft-<slug>.md .task/plan/plan-<TICKET_ID>.md
# 예: plan-SYN-42.md
```

멱등 처리: 대상 파일이 이미 존재하면 rename 건너뜀.
rename 실패 시: draft 파일 유지하고 사용자에게 이슈 ID 수동 입력 요청.

harness 있는 경우:
```bash
<harness_cli> rename-plan ".task/plan/plan-draft-<slug>.md" <ISSUE_NUMBER>
```

**8. Output**

- 이슈 번호 / URL (또는 Jira 티켓 ID)
- 이슈 제목
- 감지된 Type / Labels / Priority / Size (판단 근거 포함)
- 파일 rename 결과: `plan-draft-<slug>.md` → `plan-<id>.md`
- 다음 단계: `$project-start <issue-number>`
