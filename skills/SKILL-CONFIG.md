# Skill Config 읽기 절차

모든 글로벌 워크플로우 스킬은 이 절차를 **서두에** 실행한다.

## 설정 읽기

`.claude/skill-config.yaml` 을 Read 도구로 읽는다.

파일이 없거나 키가 누락된 경우 아래 기본값을 사용한다:

| 키 | 기본값 | 설명 |
|----|--------|------|
| `issue_tracker` | `github` | `github`, `jira`, 또는 `forgejo` |
| `base_branch` | `main` | **프로젝트 기본** PR/머지 대상 브랜치. 각 프로젝트가 재정의(enseed-trader=`develop`, cosmos-forge=`main`). 작업별 override 는 플랜 frontmatter 가 우선 — 아래 "base branch 우선순위" 참조 |
| `adr_dir` | `docs/adr` | ADR 문서 저장 경로 |
| `harness_enabled` | `false` | `true`면 harness_cli.py 사용 |
| `harness_cli` | `.claude/scripts/harness_cli.py` | 프로젝트 **단일 진입점**. 코어 커맨드(`harness_core.cli`)와 이 프로젝트의 트래커 커맨드를 한 파서로 합쳐 노출한다. 모든 로컬/트래커 커맨드의 정본 주소 |
| `project_py` | `.claude/scripts/project.py` | **크로스 레포 호출자를 위한 하위호환 진입점**(예: `cross-plan` 이 다른 레포의 `project.py` 를 리터럴 경로로 호출). 같은 레포 안에서는 항상 `harness_cli` 를 쓴다 — `project.py` 는 in-repo fallback 계층이 아니다 |
| `github_repo` | (gh CLI 자동 감지) | `owner/repo` 형식 |
| `jira_project` | — | Jira 프로젝트 키 (예: `SYN`) |
| `forgejo_host` | — | Forgejo 인스턴스 호스트 (예: `forge.example.internal`) |
| `forgejo_remote` | — | Forgejo 를 가리키는 git remote 이름 (선택 — 없으면 `forgejo_host`/`forgejo_repo` 로 조회) |
| `forgejo_repo` | — | `owner/repo` 형식 |
| `review_profile` | `auto` | 리뷰 강도 기본값. `auto`, `full`, `docs-light` |
| `hooks` | (없음) | lifecycle 훅 맵 — 키: `post_start` · `pre_done` · `post_done` |
| `release` | (없음) | 릴리즈 준비 및 문서 생성 설정 맵 — 아래 "release 설정" 참조 |

## 분기 규칙

설정 읽기 후 이후 모든 단계에서 아래 규칙을 적용한다.

### 이슈 트래커

```
issue_tracker = github  → gh CLI (또는 harness_cli.py, harness_enabled=true 시)
issue_tracker = jira    → jira CLI (ankitpokhrel/jira-cli 필요)
issue_tracker = forgejo → fj CLI (forgejo-cli 필요) — 조회: fj -H <forgejo_host> issue view/search
```

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

## base branch 우선순위 (작업별)

PR 리뷰·머지 대상 base 는 **두 출처**가 있고, 좁은 범위가 우선한다:

1. **플랜 frontmatter `base_branch`** (작업별, 최우선) — 서브이슈가 상위 user-story 통합 브랜치 위로 머지될 때 `project-plan`·`cross-plan` 이 선언한다. `project-start`·`project-done` 은 `harness_cli get-base <id>` 로 읽어 **그대로 사용**(런타임 추론 없음). `/issue` 가 플랜 전체를 이슈 본문으로 올리므로 이슈 description 에도 자동 포함된다.
2. **`skill-config.yaml` `base_branch`** (프로젝트 기본) — 위 frontmatter 가 없을 때 적용. enseed-trader=`develop`, cosmos-forge=`main`.

즉 frontmatter 미선언 = 프로젝트 기본 base(기존 동작, 신규 프롬프트 없음). frontmatter 선언 = 그 통합 브랜치가 base 이며, default 가 아니므로 **서브-PR** 로 취급한다(`project-done` 이 `Closes #<id>` 대신 `Part of #<parent_issue>` 사용).

## release 설정 (project-release / project-release-doc)

`project-release`의 Cargo 릴리즈 준비와 `project-release-doc`의 릴리즈 문서 생성이 공유하는 설정이다. 문서 생성 키는 선택이며 `release` 블록이 없으면 일반 골격으로 degrade한다. 반면 버전/commit/tag를 변경하는 `project-release`는 `primary_component`, package mapping, path mapping이 완전하지 않으면 실행을 중단한다.

| 키 | 기본값 | 설명 |
|----|--------|------|
| `release.doc_dir` | `docs/release` | 릴리즈 문서 출력 경로. **git 추적 경로**여야 한다 — 문서는 생성 후 커밋된다 |
| `release.tag_format` | `{package}-v{version}` | 릴리즈 태그 패턴. 단일 패키지 프로젝트는 `v{version}` 으로 지정 |
| `release.primary_component` | (없음; mutation 중단) | 릴리즈 range를 정할 기준 component key. 프로젝트별 이름이며 공통 기본값은 없다 |
| `release.preflight_paths` | `[]` | SemVer/호환성 판정 전에 읽을 workspace manifest, API schema 등 파일 목록 |
| `release.preflight_commands` | `[]` | mutation 전에 실행할 프로젝트별 검증 명령. ignored build artifact는 허용하지만 tracked file이나 외부 시스템을 변경하면 안 된다 |
| `release.components.<name>.kind` | `backend` | `backend` 또는 `frontend`. `frontend` 는 backend↔frontend 호환성 확인 항목을 강제한다 |
| `release.components.<name>.paths` | (없음 = 전체) | 컴포넌트 소스 경로 목록. 모노레포에서 `git log <from>..<to> -- <paths>` 커밋 스코핑에 사용 |
| `release.components.<name>.cargo_package` | (없음; mutation 대상이면 중단) | `cargo metadata`의 package name과 정확히 일치하는 식별자 |
| `release.components.<name>.release_with` | `[]` | 이 component가 릴리즈될 때 함께 검토·릴리즈할 component key 목록. 포함 근거이지 동일 버전/동일 bump 강제가 아니다 |
| `release.components.<name>.migrations_globs` | `["**/migrations/**"]` | DB 마이그레이션 탐지 경로 |
| `release.components.<name>.config_globs` | `["config/**", ".env*", "docker/**", "deploy/**"]` | 설정 변경 탐지 경로. `**/*.toml` 같은 광역 패턴은 버전 범프 커밋 오탐을 만들므로 넣지 않는다 |
| `release.components.<name>.critical_globs` | (없음) | 고위험 경로 목록. 매칭 변경은 High 리스크로 판정된다 |
| `release.components.<name>.shared_globs` | (없음) | 컴포넌트 간 공유 코드 경로. 매칭 변경 발견 시 호환성 확인 항목을 강제한다 |
| `release.components.<name>.deploy_steps_template` | (없음) | 프로젝트 로컬 배포 절차 템플릿 경로. `{version}`, `{from_version}`, `{package}` 플레이스홀더 치환 |

`project-release` mutation의 필수 계약은 유효한 `primary_component`, 각 대상의 유일한 `cargo_package`, 비어 있지 않은 `paths`, 그리고 모든 placeholder를 해석할 수 있는 `tag_format`이다. component 참조 누락, 중복 package mapping, 순환 또는 존재하지 않는 `release_with`, 모호한 tag parsing은 안전한 기본값이 없으므로 확인 전에 중단한다. `doc_dir`, globs, template, preflight keys는 위 기본값으로 생략 가능하다.

glob 키들을 git pathspec 으로 사용할 때는 `:(glob)` 매직을 붙여 해석한다 — 붙이지 않으면 루트 레벨 `migrations/` 가 매칭되지 않는다 (`project-release-doc` Instruction 2 참조).

예시 (**예시일 뿐 기본값이 아니다** — 프로젝트 상수는 각 프로젝트의 `skill-config.yaml` 에만 둔다):

```yaml
release:
  doc_dir: docs/release
  tag_format: "{package}-v{version}"
  primary_component: service
  preflight_paths: [Cargo.toml, api/schema.json]
  preflight_commands: ["cargo test --workspace --no-run"]
  components:
    service:
      kind: backend
      cargo_package: service-core
      paths: [crates/service/, crates/shared/]
      release_with: [storage]
      migrations_globs: ["crates/service/migrations/**"]
      critical_globs: ["crates/service/src/protocol/**"]
      shared_globs: ["crates/shared/**"]
      deploy_steps_template: .claude/release/service-deploy-steps.md
    storage:
      kind: backend
      cargo_package: storage-adapter
      paths: [crates/storage/]
    console:
      kind: frontend
      cargo_package: admin-console
      paths: [crates/console/]
      deploy_steps_template: .claude/release/console-deploy-steps.md
```

단일 package 프로젝트도 같은 계약을 쓴다. 이 경우 `tag_format: "v{version}"`, 임의의 component key 하나, 그 key를 가리키는 `primary_component`, `cargo_package`, `paths: [.]`를 선언한다.

## 훅 실행

설정에 `hooks` 키가 있으면 lifecycle 포인트마다 커맨드를 실행한다.

### 포인트

| 포인트 | 스킬 · 위치 | 실패 처리 |
|--------|------------|-----------|
| `post_start` | `project-start` Step 6(구현 시작) 직전 | 경고 후 계속 |
| `pre_done` | `project-done` Step 3(ADR) 직전 — 모든 커밋 이전 | **중단** |
| `post_done` | `project-done` Step 9(이슈 코멘트) 직후 | 경고 후 계속 |

### 실행 규칙

- `hooks.<point>` 키 없음 · 값이 `~`(null) · 값이 `""` → 조용히 skip
- 단일 문자열: Bash에 그대로 전달
- YAML literal block (`|`): 전체를 단일 Bash 호출로 전달 (여러 줄이 하나의 shell 세션에서 실행됨)
- `pre_done` 실패 시: 훅 실패 출력을 사용자에게 보고하고 절차를 중단한다. 이후 Step은 실행하지 않는다.
- `post_start` / `post_done` 실패 시: 경고 출력 후 계속 진행한다.
- CWD: 프로젝트 루트 (워크트리 사용 시 워크트리 루트)

### YAML 예시

```yaml
hooks:
  pre_done: cargo dylint --all -- -p backend
  post_done: |
    echo "build ok"
    .claude/scripts/notify.sh
```

## 워크트리 경로 주의사항

`harness_cli.py` 와 `project.py` 는 워크트리 CWD에서 호출해도
`.task/plan/` 및 `.claude/state.json` 을 **메인 워크트리 기준**으로 자동 resolve한다.

단, `git add` / `git commit` / `git push` 는 **워크트리 CWD** 에서 실행해야
현재 브랜치에 붙는다. `cd` 를 반복하지 말 것.
