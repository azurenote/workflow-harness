---
name: project-done
description: DoD 검증 → impl-report 작성 → 커밋 → PR 생성(GitHub) 또는 브랜치 머지(Jira) → 이슈 상태 갱신까지 완료 처리를 일괄 수행. Codex에서는 `$project-done ...` 또는 "project-done 스킬로 ..." 요청 시 실행.
---

# project-done — 작업 완료

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- Codex에서 `$project-done <issue-id>` 또는 "project-done 스킬로 <issue-id> 완료" 형태로 요청할 때
- "완료", "커밋", "PR", "닫기", "머지" + 이슈 번호 조합
- 구현이 끝났고 DoD 검증을 요청할 때

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Usage

```
$project-done <issue-id> [adr]
```

- `<issue-id>`: GitHub 이슈 번호 또는 Jira 티켓 ID
  - 생략 시 대화 컨텍스트 또는 현재 브랜치명에서 추론
- `[adr]`: 커밋 전 ADR 작성

## 워크트리 주의사항

`harness_cli.py` / `project.py` 는 워크트리 CWD에서 호출해도 `.task/plan/` 과
`.claude/state.json` 을 메인 워크트리 기준으로 자동 resolve한다.

`git add` / `git commit` / `git push` 는 **워크트리 CWD** 에서 실행해야 현재 브랜치에 붙는다.

## Instructions

**1. 플랜 파일 확인**

```bash
<harness_cli> plan-file <issue-id>   # fallback: ls .task/plan/plan-<issue-id>.md
```

파일 없으면 중단 후 사용자에게 안내.

**1-B. base branch 판독 (frontmatter)**

```bash
<harness_cli> get-base <issue-id>   # {"base_branch": <branch|null>, "parent_issue": <num|null>}
```

여기서 **"프로젝트 기본 base"** = "설정 읽기"에서 읽은 `skill-config.yaml` 의 `base_branch`(enseed-trader=`develop`, cosmos-forge=`main`). 리터럴 `develop` 으로 비교하지 말 것 — 이 스킬은 여러 프로젝트가 공유한다.

- `base_branch` 가 non-null 이고 **프로젝트 기본 base 와 다르면** → **서브-PR**(통합 브랜치 타겟). `<base_branch>`·`<parent_issue>` 를 이후 단계(impl-report diff·PR base·종료 트레일러)에서 사용한다.
- `null` 이거나 프로젝트 기본 base 와 같으면 → `<base_branch>` = 프로젝트 기본 base, 서브-PR 아님. 기존 동작.
- harness 없을 때 fallback: 플랜 파일 `.task/plan/plan-<issue-id>.md` 선두 frontmatter 의 `base_branch:`/`parent_issue:` 를 직접 확인(없으면 프로젝트 기본 base).

**1-C. Review Profile 판독**

플랜의 `## Review Profile` 섹션을 읽는다. 없으면 `~/.claude/skills/SKILL-CONFIG.md`의 `review_profile` 기본값을 사용한다.

- `project-done`은 리뷰를 새 의미로 재해석하지 않고, `project-start`에서 수행한 profile/mode/근거/수행 방식을 impl-report에 기록한다.
- 수행 기록이 없으면 `not reported`로 명시하고, DoD 검증 중 필요한 추가 리뷰를 수행했는지 별도로 적는다.
- 코드 영향 변경에 `docs-light`가 기록되어 있으면 안전 규칙 위반으로 보고하고 `full` 리뷰 보완 여부를 확인한다.

**2. Definition of Done 검증**

`.task/plan/plan-<issue-id>.md` 의 DoD 항목을 하나씩 확인한다.
- 충족: ✅ 확인
- 미충족: 목록을 나열하고 진행 여부를 사용자에게 묻는다

**2-H. `pre_done` 훅 (있을 때만)**

`.claude/skill-config.yaml`의 `hooks.pre_done` 값이 있으면 Bash로 실행한다.
**실패 시 훅 실패 출력을 사용자에게 보고하고 절차를 중단한다. 이후 Step은 실행하지 않는다.**
(`SKILL-CONFIG.md` "훅 실행" 참조)

**3. ADR (조건부)**

`adr` 인자가 있으면 `$project-adr <issue-id>` 를 먼저 실행한다.
ADR 커밋이 완료된 후 4단계로 진행한다.

**4. impl-report 작성**

`.task/plan/impl-report-<issue-id>.md` 생성:

```markdown
# Implementation Report: <title>

## Issue
#<id> — <title>
<서브-PR이면 이 줄 추가: "Part of #<parent_issue>">

## Branch
`<branch-name>` → base `<base_branch>`

## Summary
<구현 내용 2–4문장>

## Changed Files
<git diff --name-only "<diff_base>" 출력>

## Definition of Done
- [x] <condition>

## Review
- Review Profile: `<auto | full | docs-light | not reported>`
- Resolved Mode: `<full | docs-light | not reported>`
- Reason: `<선택 또는 승격 근거>`
- Execution: `<subagents | main-agent fallback | docs-light | not reported>`
- Findings / Fixes: `<반영한 리뷰 지적사항, 없으면 None>`

## Known Limitations / Follow-up
<없으면 "None">

## Tests
<실행한 테스트와 결과>
```

> `<diff_base>` 결정: 로컬에 `<base_branch>` ref 가 있으면 그대로, 없으면 `origin/<base_branch>`(필요 시 `git fetch origin <base_branch>` 선행). **부재 ref 로 `git diff` 하면 exit 128 로 깨지므로** 반드시 존재하는 ref 를 사용한다. base 가 프로젝트 기본 base 면 `origin/<기본 base>`(예 enseed=`origin/develop`)가 안전하다.

**5. 소스 변경 커밋**

`.task/plan/` 은 `.gitignore` 대상 — 절대 스테이징하지 않는다.

```bash
grep -q "^\.task/plan/" .gitignore || echo ".task/plan/" >> .gitignore

git add -A
git restore --staged ".task/plan/" 2>/dev/null || true

git commit -m "feat(<scope>): <title>

- <change 1>

<trailer>"
```

`<trailer>` 결정 (1-B 의 서브-PR 판정 기준):
- base == 프로젝트 기본 base → `Closes #<issue-id>` (머지 시 이슈 자동 종료).
- base 가 통합 브랜치(**서브-PR**) → `Part of #<parent_issue>` (`Closes` **생략** — 비-default 머지에서 `Closes` 는 발동하지 않으므로 잘못된 자동 종료를 만들지 않는다).

**6. 브랜치 Push**

```bash
<harness_cli> push-branch "<branch-name>"   # fallback: git push -u origin "<branch-name>"
```

**7. PR / 브랜치 처리**

### GitHub (`issue_tracker: github`)

`--base` 는 항상 1-B 에서 읽은 `<base_branch>` 를 **명시 전달**한다(하드코딩 develop 제거 — 세 계층이 한 출처에 동의).

```bash
# default-base PR: --closes 로 머지 시 이슈 자동 종료
<harness_cli> create-pr \
  --title "<이슈 제목>" \
  --body-file ".task/plan/impl-report-<id>.md" \
  --head "<branch-name>" \
  --base "<base_branch>" \
  --closes <id>
# fallback: gh pr create --title "<이슈 제목>" --body-file ".task/plan/impl-report-<id>.md" --base "<base_branch>"
```

```bash
# 서브-PR (base ≠ default): --closes 생략. impl-report 에 "Part of #<parent_issue>" 만 남긴다.
# 서브이슈는 In Review 로 유지되고, 통합 브랜치가 develop 에 머지될 때(통합 PR 의 Closes 목록
# 또는 수동) 종료된다.
<harness_cli> create-pr \
  --title "<이슈 제목>" \
  --body-file ".task/plan/impl-report-<id>.md" \
  --head "<branch-name>" \
  --base "<base_branch>"
# fallback: gh pr create --title "<이슈 제목>" --body-file ".task/plan/impl-report-<id>.md" --base "<base_branch>"
```

PR URL 획득.

### Jira (`issue_tracker: jira`)

```bash
git checkout <base_branch> && git merge --no-ff "<branch-name>" && git push origin <base_branch>
```

**8. 프로젝트 상태 → In Review**

```bash
<harness_cli> set-review <issue-id>
# fallback(GitHub): gh issue edit <issue-id> --add-label "in-review"
# fallback(Jira):   jira issue move <ticket-id> "In Review"
```

**9. 이슈 코멘트 등록**

```bash
<harness_cli> add-comment <id> "Implementation complete. PR: <PR_URL>"
# fallback(GitHub): gh issue comment <id> --body "Implementation complete. PR: <PR_URL>"
# fallback(Jira):   jira issue comment add <ticket-id> "Implementation complete. Branch: <branch-name>"
```

**9-H. `post_done` 훅 (있을 때만)**

`.claude/skill-config.yaml`의 `hooks.post_done` 값이 있으면 Bash로 실행한다.
실패해도 경고만 출력하고 계속 진행한다. (`SKILL-CONFIG.md` "훅 실행" 참조)

**default-base PR** 은 `Closes #<id>` 키워드로 머지 시 이슈가 자동 종료되므로 `gh issue close` 를 호출하지 않는다.
**서브-PR(base ≠ default)** 은 `Closes` 가 발동하지 않으므로 이슈는 In Review 로 남고, 통합 브랜치가 develop 에 머지될 때 종료된다 — 자동 종료를 가정하지 않는다.

**10. 임시 파일 정리**

```bash
<project_py> clean-temp <issue-id>
```

**11. Output**

- 커밋 해시
- PR URL (GitHub) 또는 머지 커밋 해시 (Jira)
- 머지 후: `$project-clean` 실행하여 브랜치/워크트리 정리
