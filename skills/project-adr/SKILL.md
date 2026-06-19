---
name: project-adr
description: 아키텍처 결정 사항을 ADR 문서로 작성하고 이슈 코멘트에 경로를 게시한다. project-start 또는 project-done의 adr 플래그로 내부 호출되거나 독립 실행. Codex에서는 `$project-adr ...` 또는 "project-adr 스킬로 ..." 요청 시 실행.
---

# project-adr — Architecture Decision Record 작성

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- "ADR", "아키텍처 결정", "설계 문서" 키워드
- `$project-start <id> adr` 또는 `$project-done <id> adr` 의 내부 호출
- 중요 설계 선택을 기록해야 하는 시점

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

`adr_dir` 값을 ADR 저장 경로로 사용한다 (기본: `docs/adr`).

## Usage

```
$project-adr <issue-id>
```

독립 실행 또는 `$project-start` / `$project-done` 에서 내부 호출.

## Instructions

**1. ADR 내용 결정**

`.task/plan/plan-<issue-id>.md` 와 현재 브랜치 diff를 읽어 문서화할 아키텍처 결정을 파악한다.
결정 제목이 모호하면 사용자에게 확인한다.

**2. 파일명 결정**

ADR 컨벤션은 `<adr_dir>/README.md` 에 정의되어 있다.

- 위치: `<adr_dir>/` (`skill-config.yaml`의 `adr_dir` 값)
- 파일명: `YYYY-MM-DD-<slug>.md`
- 예: `2026-05-24-global-skills-config-layer.md`

**3. ADR 문서 작성**

```markdown
# ADR: <결정 제목>

**날짜**: YYYY-MM-DD
**상태**: 제안 | 수락 | 폐기 | 대체됨
**영향 범위**: `<변경 대상 파일/모듈>`
**키워드**: keyword1, keyword2

---

## 배경 (Context)
<문제 상황. 왜 결정이 필요한가?>

## 결정 (Decision)
<내린 결정. 능동적 문장으로.>

## 대안 검토 (Alternatives Considered)
| Option | Reason Rejected |
|--------|----------------|
| <대안> | <기각 사유> |

## 결과 (Consequences)
### 긍정적
- <이점>

### 부정적 / 트레이드오프
- <트레이드오프>

## 참조
- <관련 이슈, 문서 링크>
```

**3.5. 가독성·자급성 체크 (커밋 전 자가검증)**

초안을 커밋하기 전에 아래 기준으로 한 번 훑어 교정한다. 목표는 코드를 함께 펼치지 않아도 산문만으로 결정→근거→트레이드오프가 닫히는 문서다. 문서 언어가 한국어이면 명사 나열과 전보식(telegraphic — 절을 화살표·콜론 등으로 엮고 서술어를 생략하는 축약) 표현을 금지하고, 모든 항목을 주어와 서술어가 호응하는 완결문으로 쓴다.

- **식별자·약어 풀이**: 코드 식별자, 약어, 도메인 신조어가 처음 등장할 때 같은 문장 안에서 한 구절로 정의한다. 예를 들어 `PEL(Pending Entries List — 전달됐으나 ack 되지 않은 엔트리)`처럼 적는다. 정의를 뒤로 미루거나 외부 지식에 떠넘기지 않는다. 문서 언어와 코드 언어가 다를 때도 개념은 한 언어로 정의한 뒤 그 용어로 통일해 부른다.
- **코드 참조는 정의가 아니다**: `executor.rs:940` 같은 줄 참조는 산문 설명을 보강할 뿐이다. 그 식별자가 무엇을 왜 하는지는 산문이 먼저 말한다.
- **문장 분할**: 절이 셋을 넘게 이어지는 늘어진 문장(run-on — 주어가 한 번도 끊기지 않고 이어지는 문장)과, 화살표(→)·콜론·곱셈기호로 절을 엮은 전보식 항목은 완결문 여러 개로 나눈다.
- **한 개념 한 용어**: 같은 대상은 끝까지 한 용어로 부른다. 한국어와 영어를 겹쳐 같은 뜻을 두 번 적는 동어반복(예: `정방향 재유도(forward 재유도)`)을 쓰지 않는다.
- **코드블록은 본문이 풀이한다**: 코드, SQL, 의사코드 블록은 원문(영문) 그대로 두되, 직전 또는 직후 산문이 그 블록의 어느 부분이 논점인지 한 번 풀어 설명한다.
- **사실 충실도(fidelity)와 낡은 서술(stale) 교정**: 가독성 교정과 동시에 사실 충실도를 검증한다. 현재 diff·코드와 대조하여 낡아버린 서술과 잘못 인용한 코드 라인을 바로잡고, ADR 일련번호나 목록 순번이 중복되지 않았는지 확인한다.

마지막으로 코드를 한 번도 보지 않은 독자 관점에서 처음부터 끝까지 한 번 통독하여 걸림돌(미정의 식별자, 끊긴 인과, 주어-서술어 불일치)을 잡는다. 이 자가 통독은 언제나 거치고, 규모가 크거나 결정이 미묘하면 cold-reader 에이전트(코드를 본 적 없는 독자 역할의 에이전트)에게 같은 통독을 맡기고 별도 fidelity 에이전트(현재 코드와 사실을 대조하는 에이전트)에게 대조를 맡긴다. 이 교정의 결과도 전보식이 되지 않도록 완결문으로 남긴다.

**4. 이슈 코멘트 게시**

Markdown 백틱은 셸에서 명령 치환으로 해석될 수 있다. ADR 경로를 확정한 뒤 코멘트 본문 전체를 단일 quoted 인자로 전달한다.
Codex에서 GitHub API 호출이 네트워크/sandbox 오류로 실패하면 같은 명령을 `require_escalated`로 즉시 재실행한다.

```bash
ADR_PATH="<adr_dir>/YYYY-MM-DD-<slug>.md"
COMMENT="ADR recorded: \`${ADR_PATH}\`"

# GitHub (harness_enabled: true)
<harness_cli> add-comment <issue-id> "$COMMENT"
# GitHub (project.py fallback)
<project_py> add-comment <issue-id> "$COMMENT"
# GitHub (gh fallback)
gh issue comment <issue-id> --body "$COMMENT"
# Jira
jira issue comment add <ticket-id> "$COMMENT"
```

Codex `exec_command`에서 최종 경로를 직접 넣어 실행할 때는 아래처럼 single quote를 사용한다.

```bash
.claude/scripts/harness_cli.py add-comment 326 'ADR recorded: `docs/arch-decision-record/2026-06-07-blue-green-swap-orchestration.md`'
```

**5. ADR 파일 커밋**

ADR은 소스 트리에 포함되어 커밋된다.

```bash
git add "<ADR_PATH>"
git commit -m "docs(adr): <결정 제목>

Related to #<issue-id>"
```

**6. Output**

- ADR 파일 경로
- 이슈 코멘트 URL
- 독립 실행 시 다음 단계: `$project-start` 또는 `$project-done` 계속
