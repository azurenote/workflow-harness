# Skill Config 읽기 절차

모든 글로벌 워크플로우 스킬은 이 절차를 **서두에** 실행한다.

## 설정 읽기

`.claude/skill-config.yaml` 을 읽는다.

파일이 없거나 키가 누락된 경우 아래 기본값을 사용한다:

| 키 | 기본값 | 설명 |
|----|--------|------|
| `issue_tracker` | `github` | `github`, `jira`, 또는 `forgejo` |
| `base_branch` | `main` | **프로젝트 기본** PR/머지 대상 브랜치. 각 프로젝트가 자기 값으로 재정의한다 — 공유 문서에 특정 프로젝트의 값을 적지 않는다. 작업별 override 는 플랜 frontmatter 가 우선 — 아래 "base branch 우선순위" 참조 |
| `adr_dir` | `docs/adr` | ADR 문서 저장 경로 |
| `harness_enabled` | `false` | `true`면 harness_cli.py 사용 |
| `harness_cli` | `.claude/scripts/harness_cli.py` | 프로젝트 **단일 진입점**. 코어 커맨드(`harness_core.cli`)와 이 프로젝트의 트래커 커맨드를 한 파서로 합쳐 노출한다. 모든 로컬/트래커 커맨드의 정본 주소 |
| `project_py` | `.claude/scripts/project.py` | **크로스 레포 호출자를 위한 하위호환 진입점**(예: `cross-plan` 이 다른 레포의 `project.py` 를 리터럴 경로로 호출). 같은 레포 안에서는 항상 `harness_cli` 를 쓴다 — `project.py` 는 in-repo fallback 계층이 아니다 |
| `github_repo` | (gh CLI 자동 감지) | `owner/repo` 형식 |
| `github_project` | (없음) | GitHub 이슈 메타데이터 계약의 프로젝트(Projects V2) 좌표 — `owner`·`number`·`status_names`·`field_names`. 없으면 프로젝트 필드 경로를 쓸 수 없고 "미반영" 으로 degrade 한다. 아래 "GitHub 이슈 메타데이터" 참조 |
| `jira_project` | — | Jira 프로젝트 키 (예: `SYN`) |
| `forgejo_host` | — | Forgejo 인스턴스 호스트 (예: `forge.example.internal`) |
| `forgejo_remote` | — | Forgejo 를 가리키는 git remote 이름 (선택 — 없으면 `forgejo_host`/`forgejo_repo` 로 조회) |
| `forgejo_repo` | — | `owner/repo` 형식 |
| `review_profile` | `auto` | 리뷰 강도 기본값. `auto`, `full`, `docs-light` |
| `review_guidelines` | (없음) | 리뷰 단계가 각 역할에게 읽힐 **프로젝트 근거 문서 경로**. 없으면 역할 기본값으로 degrade — 아래 "리뷰 가이드라인 주입" 참조 |
| `hooks` | (없음) | lifecycle 훅 맵 — 키: `post_start` · `pre_done` · `post_done` |
| `release` | (없음) | 릴리즈 준비 및 문서 생성 설정 맵 — 아래 "release 설정" 참조 |

## 호스트별 참조

스킬 본문은 **호스트 중립**으로 하나의 절차만 서술한다. 특정 호스트에서만 쓰는 메커니즘과
호출 문법은 참조 파일에 있다.

| 호스트 | 참조 |
|--------|------|
| Codex | `~/.claude/skills/_shared/references/codex.md` — 호출 문법, 샌드박스 실패 시 승격, 서브에이전트 API, 셸 인용 |
| 그 외 | 스킬 본문만으로 완결된다. 별도 참조 없음 |

옮긴 것이지 지운 것이 아니다. 예전에는 Codex 규칙이 본문에 먼저 오고 다른 호스트가 그에 대한
**차분**을 읽어야 했다 — 한 경로를 위해 두 벌을 읽는 구조였다.

## 분기 규칙

설정 읽기 후 이후 모든 단계에서 아래 규칙을 적용한다.

### 이슈 트래커

```
issue_tracker = github  → gh CLI (또는 harness_cli.py, harness_enabled=true 시)
issue_tracker = jira    → jira CLI (ankitpokhrel/jira-cli 필요)
issue_tracker = forgejo → fj CLI (forgejo-cli 필요) — 조회: fj -H <forgejo_host> issue view/search
```

위 CLI 들의 최소 버전과 **버전 확인 명령**은 `~/.claude/skills/dependencies.yaml` 에 선언돼 있다. 확인 명령을 추측하지 말 것 — `--version` 이 모든 도구에 통하지는 않고, 추측하면 설치된 도구를 미설치로 오판한다.

`forgejo` 는 현재 **조회(read) 경로만** 계약이다. 이슈 제목·상태 조회는
`fj -H <forgejo_host> --style minimal issue view "<forgejo_repo>#<N>"` 을 사용하고,
로컬에 `forgejo_remote` 리모트가 실제로 존재하면 `fj issue view -R <forgejo_remote> <N>` 형태의 remote 기반 조회로 대체할 수 있다.
조회가 실패하면(네트워크·인증·CLI 부재) 그 항목을 "미확인" 으로 표기한 뒤 절차를 계속한다 — 조회 실패로 스킬을 중단하지 않는다.
이슈 생성·상태 전환처럼 쓰기가 필요한 단계에서 CLI/API 가 실패하면 웹 UI 수동 처리를 안내하고, 수동 결과(이슈 번호 등)를 받아 이후 단계를 진행한다.

### harness 사용 여부

```
harness_enabled = true  → harness_cli 경로의 스크립트 우선 사용, 실패 시 gh CLI fallback
harness_enabled = false → gh CLI / jira CLI 직접 사용
```

`harness_cli` 는 코어 커맨드와 프로젝트 트래커 커맨드(`get-issue`·`create-pr`·
`add-comment`·`clean-temp` 등)를 모두 노출하는 **단일 진입점**이다. 따라서 fallback
사슬은 `harness_cli → gh` 하나뿐이며 **중간에 `project.py` 계층은 없다**. `project.py`
는 같은 레포 안에서 harness_cli 를 우회하는 fallback 이 아니라, `cross-plan` 처럼 **다른
레포의 스크립트를 리터럴 경로로 호출**하는 크로스 레포 진입점으로만 남는다.

**폴백은 경로를 바꾸는 것이지 모델을 바꾸는 것이 아니다.** `issue_tracker: github` 에서
harness 를 못 쓰고 gh 로 내려가도 type·priority·size·status 가 적히는 자리는 같다 —
라벨로 우회하지 않는다. 계약과 gh 폴백 명령은 `_shared/references/github-issue-fields.md`
에 있다.

## Review Profile 공통 정책

모든 글로벌 워크플로우 스킬은 리뷰 강도를 같은 의미로 해석한다.

우선순위:

1. 플랜 본문 `## Review Profile` 섹션의 값
2. `.claude/skill-config.yaml` 의 `review_profile`
3. 기본값 `auto`

지원 값:

| Profile | 의미 |
|---------|------|
| `auto` | 작업 범위와 변경 파일을 보고 `full` 또는 `docs-light`를 선택한다. 불확실하면 `full` |
| `full` | 기존 설계자·구현자·테스트 엔지니어 관점의 적대적 리뷰 |
| `docs-light` | 문서 전용 작업에 쓰는 단일 문서 리뷰 패스 |

### `auto` 판정

`docs-light`는 범위와 변경 파일이 문서 전용일 때만 선택한다.

- Markdown/MDX 문서
- `docs/`, `wiki/`, `content/`, `handbook/`, `manual/` 같은 문서 경로
- 문서가 참조하는 이미지, 다이어그램, 예제 데이터처럼 실행되지 않는 정적 자산

다음 항목이 하나라도 포함되면 `full`을 선택한다.

- 실행 코드, 스크립트, 라이브러리 소스
- 테스트 코드 또는 fixture
- build 설정, CI workflow, package metadata, dependency lockfile
- runtime config, infrastructure, deployment manifest
- 생성물이더라도 실행·배포·런타임 동작에 관여하는 artifact
- Markdown이라도 동작을 정의하는 문서 — 에이전트/스킬 지침(`skills/**/SKILL.md` 등), 프롬프트 템플릿, agent 정의처럼 읽히는 즉시 실행 동작을 바꾸는 파일
- 문서 전용인지 확신할 수 없는 변경

예시:

- `docs/**/*.md`, `content/**/*.mdx`, 문서 이미지 파일만 변경 → `docs-light`
- `src/**`, `tests/**`, `.github/**`, `pyproject.toml`, `package.json`, lockfile, runtime config 변경 포함 → `full`
- `skills/**/SKILL.md`처럼 에이전트 동작을 정의하는 문서 변경 → `full` (확장자가 `.md`여도 docs-light 아님)

### Override 안전 규칙

- 명시값 `full`은 그대로 `full`로 처리한다.
- 명시값 `docs-light`라도 코드·테스트·빌드·CI·의존성·런타임 설정 변경이 섞이면 `full`로 승격한다.
- `auto` 또는 override 승격 결과와 판단 근거를 최종 보고나 impl-report에 남긴다.

### `docs-light` 리뷰 체크리스트

`docs-light`는 리뷰 생략이 아니다. 최소 한 번의 문서 리뷰 패스로 아래를 확인한다.

- 독자가 문서만 읽고 의도와 절차를 이해할 수 있는가?
- 링크, 경로, 명령, 파일명이 현재 repo와 일치하는가?
- 문서 변경이 코드 동작 변경을 암시하지 않는가?
- LLM wiki/docs-as-code 구조의 index, frontmatter, tag, sidebar 계약을 깨지 않는가?

## 참조 파일

모든 스킬이 이 문서 전체를 읽던 구조를 끊었다. 아래는 **필요한 스킬만** 읽는다.
자기가 쓰지 않는 키의 지시는 읽지 않는다 — 토큰 절감이 목적이 아니라, 무관한 지시가
절차 판단에 섞이지 않게 하는 것이 목적이다.

| 참조 | 내용 | 읽는 스킬 |
|------|------|-----------|
| `_shared/references/review-guidelines.md` | `review_guidelines` 스키마와 해석 규칙 | project-start · project-plan · project-done |
| `_shared/references/base-branch.md` | 작업별 base branch 우선순위 | project-start · project-done · project-plan · project-issue · project-clean · project-harness-init |
| `_shared/references/release.md` | `release` 블록 전체 | project-release · project-release-doc |
| `_shared/references/hooks.md` | lifecycle 훅 포인트와 실패 정책 | project-start · project-done |
| `_shared/references/worktree.md` | 워크트리 CWD 주의사항 | project-start · project-done · project-clean |
| `_shared/references/github-issue-fields.md` | GitHub 이슈 메타데이터 계약과 `github_project` 스키마 | project-issue · project-start · project-done |
| `_shared/references/codex.md` | Codex 호스트 메커니즘 | Codex 에서 실행할 때만 |

경로는 `~/.claude/skills/` 기준이다.
