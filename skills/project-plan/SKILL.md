---
name: project-plan
description: 작업 description을 받아 코드베이스를 분석하고 .task/plan/에 plan-draft-<slug>.md 파일을 생성, 에이전트 팀 리뷰까지 수행. Codex에서는 `$project-plan ...` 또는 "project-plan 스킬로 ..." 요청 시 실행.
---

# project-plan — Plan 작성

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- Codex에서 `$project-plan <작업 설명>` 또는 "project-plan 스킬로 <작업 설명>" 형태로 요청할 때
- 사용자가 새 기능·버그 수정·작업을 기술할 때
- "플랜", "계획", "설계", "구현하자", "추가하자" 키워드
- 코드베이스 분석 + 문서화가 필요한 모든 작업 착수 시점

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Instructions

**1. task description 확인**

1. `$ARGUMENTS` 가 있으면 task description으로 사용.
2. 없으면 최근 대화 메시지에서 추출.
3. 둘 다 없으면 사용자에게 요청.

**2. 코드베이스 분석**

task description에서 스코프를 파악하고 관련 파일·모듈을 탐색한다.
- Explore agent로 관련 소스 파일 분석
- 의존 관계, 인터페이스, 데이터 구조 파악
- 기존 패턴과 코딩 컨벤션 확인

**3. plan-draft-<slug>.md 생성**

파일명 규칙:
- **Draft (미등록, canonical)**: `plan-draft-<slug>.md`
- 슬러그는 task description에서 자동 생성 (3–5 단어, 영문 소문자, 하이픈)
- 예: "JWT 인증 Lambda 구현" → `plan-draft-jwt-auth-lambda.md`
- **슬러그 충돌**: 동일 슬러그 파일이 이미 존재하면 `-2`, `-3` suffix 추가
  - 예: `plan-draft-jwt-auth-lambda-2.md`
- 기존 harness 호환을 위해 `plan-<uuid>.md` draft도 `/issue`가 계속 인식하지만, 새 plan은 `plan-draft-<slug>.md`로 만든다.

```bash
mkdir -p .task/plan
grep -q "^\.task/plan/" .gitignore || echo ".task/plan/" >> .gitignore
SLUG="<task-description-을-3-5단어-영문-슬러그로-변환>"
PLAN_FILE=".task/plan/plan-draft-${SLUG}.md"
# 충돌 시 suffix 추가
N=2
while [ -f "$PLAN_FILE" ]; do
  PLAN_FILE=".task/plan/plan-draft-${SLUG}-${N}.md"
  N=$((N + 1))
done
```

파일 구조는 두 층으로 나눈다.

- **Human layer**: director가 첫 화면에서 의도, 현재 상태, 목표 상태, 제외 범위, 위험한 오해를 확인한다.
- **Agent layer**: 구현 agent가 파일, 계약, task별 완료 조건, 검증 방법을 따라 실행한다.

선두 frontmatter는 **선택** — 서브이슈일 때만 작성한다:

```markdown
---
base_branch: feat/issue-364-strategy-engine-lua   # PR 리뷰·머지 타겟. 생략/프로젝트 기본 base면 default
parent_issue: 364                                  # 선택 — 상위 user-story 이슈 번호
---
# Plan: <title>

## Intent Summary
<director가 첫 30줄 안에서 작업 의도를 확인할 수 있는 요약. 무엇을 바꾸고 왜 필요한지.>

## Current State
<현재 시스템/문서/워크플로우가 어떻게 동작하는지.>

## Target State
<작업 후 어떤 상태가 되어야 하는지.>

## Non-Goals
- <이번 작업에서 일부러 하지 않는 것>

## Drift Guards
- <agent가 위험하게 오해하기 쉬운 지점 또는 범위 이탈 금지사항>

## Requirements
- [ ] <requirement 1>
- [ ] <requirement 2>

## Definition of Done
- [ ] <검증 가능한 조건 — 구체적으로>

## Implementation Contract
<코드 수준 알고리즘은 쓰지 않되, 반드시 지킬 인터페이스/파일 경계/호환성 계약을 명시한다.>

## Task Cards

### Task 1: <name>

Intent:
<이 task가 전체 목표에 기여하는 방식>

Files / Modules:
- <path or module>

Implementation Contract:
- <반드시 지킬 동작/인터페이스/호환성>

Validation:
- <테스트 또는 수동 검증>

Drift Guard:
- <하면 안 되는 해석 또는 범위 이탈>

### Task 2: <small task name>

Intent:
<작은 작업은 Intent, Files / Modules, Validation만 작성해도 된다.>

Files / Modules:
- <path or module>

Validation:
- <검증 방법>

## Validation Plan
- <주요 자동 검증 명령>
- <필요한 수동 리뷰 체크>

## Scope
- Files to modify: <목록>
- Modules affected: <목록>
- Breaking changes: Yes / No

## References
<API 문서, 관련 이슈, 주의사항>
```

규칙:
- 첫 30줄 안에 `Intent Summary`, `Current State`, `Target State`, `Non-Goals`가 읽혀야 한다.
- 플랜은 ADR이 아니다. 아키텍처 결정의 장기 기록은 ADR에 남기고, plan은 작업 의도와 실행 계약을 공유한다.
- 코드 수준 알고리즘은 plan에 쓰지 않는다. 단, agent가 drift하지 않도록 파일/모듈 경계, 인터페이스, 호환성, 검증 계약은 plan에 명시한다.
- `Task Cards`는 압축된 체크리스트가 아니라 task별 실행 계약이다. 큰 작업은 모든 필드를 채우고, 작은 작업은 `Intent`, `Files / Modules`, `Validation`만 써도 된다.
- Definition of Done을 상세하게 — 이후 `$project-done` 에서 검증 기준이 된다.

**base branch 선언 (frontmatter):**
- 이 작업이 더 큰 user-story의 **서브이슈**이고, 프로젝트 기본 base에 직접 머지하지 않고 상위 이슈의 **통합 브랜치** 위로 머지된다면, 플랜 선두에 frontmatter로 선언한다:
  - `base_branch`: PR 리뷰·머지 타겟 브랜치(통합 브랜치명, 예 `feat/issue-364-strategy-engine-lua`).
  - `parent_issue`: 상위 user-story 이슈 번호(예 `364`).
- 이 선언이 `/start`·`/done`의 base **단일 출처**가 된다. `/issue`가 플랜 전체를 이슈 본문으로 올리므로 이슈 description에도 자동 포함되고, `/start`는 추론 없이 이 값을 **읽기만** 한다.
- **일반 작업**(프로젝트 기본 base에 바로 머지)은 frontmatter를 **생략**한다(또는 `base_branch: <프로젝트 기본 base>`). 생략 시 기존 동작과 동일하다.
- 통합 브랜치명을 모르면 상위 이슈 번호 `<P>`로 후보를 조회해 **사람이 확정**한다(런타임 추론이 아닌 plan 시점 제안):
  ```bash
  git branch -a --list "*feat/issue-<P>-*" "*feat/<P>-*"   # 로컬·원격 통합 브랜치 후보
  ```
  이미 등록된 서브이슈라면 `.claude/scripts/project.py get-parent <sub-issue>` 로 상위 이슈를 확인할 수 있다(없으면 `{"parent": null}`).

**짧은 샘플**

```markdown
# Plan: Retry Failed Webhook Delivery

## Intent Summary
Webhook delivery가 일시 실패할 때 운영자가 수동 재처리하지 않아도 되도록 짧은 retry 경로를 추가한다.

## Current State
현재 delivery 실패는 로그에 남지만 재시도 큐로 이어지지 않는다.

## Target State
일시 오류는 제한된 횟수로 재시도되고, 영구 실패는 기존 실패 기록 흐름을 유지한다.

## Non-Goals
- 외부 webhook provider 계약은 바꾸지 않는다.

## Drift Guards
- retry 추가가 중복 delivery 허용으로 해석되면 안 된다.

## Requirements
- [ ] 일시 오류만 retry 대상이다.

## Definition of Done
- [ ] retry 성공/실패 단위 테스트가 있다.

## Implementation Contract
기존 delivery result 타입과 실패 기록 포맷은 유지한다.

## Task Cards

### Task 1: Add retry decision helper

Intent:
Retry 대상 오류와 영구 실패를 한 곳에서 구분한다.

Files / Modules:
- `src/webhook/delivery.py`

Validation:
- `pytest tests/test_webhook_delivery.py`
```

**4. 에이전트 팀 리뷰**

설계자·구현자·테스트 엔지니어 역할의 에이전트 팀을 구성하여 플랜을 검토한다.

- **설계자**: 아키텍처 적합성, 기존 패턴과의 일관성, 확장성
- **구현자**: 구현 가능성, 누락된 엣지케이스, 기존 코드와의 충돌
- **테스트 엔지니어**: 테스트 가능성, DoD 검증 가능 여부, 누락된 테스트 시나리오

각 팀원은 상호 비판적으로 검토하고, 피드백을 취합하여 플랜을 수정·확정한다.

**5. Output**

- 생성된 파일 전체 경로 출력 (예: `.task/plan/plan-draft-jwt-auth-lambda.md`)
- 불확실한 부분 플래그
- 다음 단계: `$project-issue`
