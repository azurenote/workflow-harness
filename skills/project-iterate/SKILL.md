---
name: project-iterate
description: project-plan → project-issue → project-start → project-done 4단계를 한 번에 실행하는 원스톱 워크플로. 각 Phase 사이 사용자 확인 포함. Codex에서는 `$project-iterate ...` 또는 "project-iterate 스킬로 ..." 요청 시 실행.
---

# project-iterate — 원스톱 워크플로

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- Codex에서 `$project-iterate <작업 설명>` 또는 "project-iterate 스킬로 <작업 설명>" 형태로 요청할 때
- "처음부터 끝까지", "원스톱", "iterate" 키워드
- 플랜 작성부터 PR까지 한 번에 진행하고 싶을 때

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Usage

```
$project-iterate <task description> [worktree] [adr]
```

- `<task description>`: 작업 설명 (필수)
- `[worktree]`: worktree 분기 모드
- `[adr]`: ADR 작성 포함 (start + done 양쪽에 전달)

## 재진입 (중단 후 이어서)

재진입은 반드시 `$project-iterate <id>` 형식으로 이슈 ID를 명시해야 한다.
- `<id>` 없이 호출하면 항상 Phase 1(Plan)부터 새로 시작한다.
- `<id>` 는 GitHub 이슈 번호 또는 Jira 티켓 ID.

각 Phase의 완료 여부는 다음 체크포인트로 판단한다:

| Phase | 완료 신호 | 체크 방법 |
|-------|----------|----------|
| Plan | 지원되는 draft plan 존재 | `$project-issue` Step 1과 같은 draft discovery 계약(`plan-draft-<lowercase-slug>.md` 또는 lowercase hex UUID `plan-<uuid>.md`) |
| Issue | `plan-<id>.md` 존재 | `ls .task/plan/plan-<id>.md 2>/dev/null` (정확한 경로, glob 아님) |
| Start | 이슈 ID 브랜치/워크트리 존재 | `git branch -a | grep <id>` 또는 `git worktree list` |
| Done | PR 존재 또는 이슈 상태 "In Review" | `gh pr list --head <branch-name>` |

완료된 Phase는 건너뛰고 다음 Phase부터 실행한다.

## Instructions

이 스킬은 4개 글로벌 스킬을 순차 호출한다.
각 단계의 상세 절차는 해당 스킬 문서(`~/.claude/skills/<name>/SKILL.md`)를 따른다.

---

### Phase 1: Plan

1. `$ARGUMENTS` 에서 task description 추출 (`worktree`, `adr` 키워드 제외).
2. `plan` 스킬 절차를 실행한다:
   - 코드베이스 분석
   - `plan-draft-<slug>.md` 생성
   - human layer(`Intent Summary`, `Current State`, `Target State`, `Non-Goals`, `Drift Guards`)와 agent layer(`Implementation Contract`, `Task Cards`, `Validation Plan`) 작성
   - **DoD를 상세하게 작성** — 이후 `$project-done` 검증 기준
   - 에이전트 팀 리뷰
3. **사용자 확인**: 플랜 요약을 보여주고 승인을 받는다.
   - Intent Summary와 base branch가 맞는지 먼저 확인한다.
   - 수정 요청 시 반영 후 재확인.
   - 승인 시 Phase 2로 진행.

---

### Phase 2: Issue

1. `issue` 스킬 절차를 실행한다:
   - `plan-draft-<slug>.md` 또는 기존 `plan-<uuid>.md` draft → 이슈 트래커 티켓 등록
   - draft plan → `plan-<id>.md` rename
2. 이슈 ID / 티켓 URL 출력 후 Phase 3로 자동 진행.

---

### Phase 3: Start + 구현

1. Phase 2에서 획득한 이슈 ID로 `start` 스킬 절차를 실행한다:
   - `worktree` 인자 전달 (해당 시)
   - `adr` 인자 전달 (해당 시) → 구현 전 ADR 작성
   - Intent Summary와 Drift Guards 숙지
   - Task Cards 체크리스트 출력 + 구현 착수
   - 에이전트 팀 코드 리뷰
2. **사용자 확인**: 구현 결과 요약 보여주고 승인을 받는다.
   - 수정 요청 시 반영 후 재확인.
   - 승인 시 Phase 4로 진행.

---

### Phase 4: Done

1. Phase 2에서 획득한 이슈 ID로 `done` 스킬 절차를 실행한다:
   - `adr` 인자 전달 (해당 시)
   - DoD 검증
   - impl-report 작성
   - 커밋 → Push → PR 생성 (또는 Jira 머지)
   - 이슈 상태 "In Review"
2. 최종 결과 출력 (커밋 해시, PR URL).

---

## 중단 보존 상태

| 중단 시점 | 보존 결과물 |
|-----------|------------|
| Phase 1 후 | `plan-draft-<slug>.md` 또는 기존 `plan-<uuid>.md` |
| Phase 2 후 | 이슈 티켓 + `plan-<id>.md` |
| Phase 3 후 | 위 + 구현 코드 (미커밋) |
| Phase 4 완료 | 위 + 커밋 + PR + 이슈 코멘트 |

중단 후 이어서 진행하려면 해당 스킬을 직접 호출한다:
- Phase 2부터: `$project-issue`
- Phase 3부터: `$project-start <id>`
- Phase 4부터: `$project-done <id>`
