<!-- Split out of skills/SKILL-CONFIG.md. Every skill used to read the whole
     config document at startup, including the parts that did not apply to it.
     Read this file only when the skill says it needs it. -->

# release 설정 (project-release / project-release-doc)

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
