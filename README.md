# workflow-harness

Claude Code 워크플로우 자동화(plan → issue → start → done → clean)의 **공유 코어와 글로벌 스킬**을 버전 관리하는 저장소.

여러 프로젝트가 동일한 워크플로우 패턴을 쓰되 프로젝트별 상수만 다르다. 그 공통분모를 여기에 모아 한 곳에서 추적·리뷰·롤백한다.

소비 프로젝트의 이름·경로·브랜치 같은 상수는 이 저장소에 두지 않는다. 각 프로젝트의 `.claude/skill-config.yaml` 이 자기 값을 선언하고, 스킬은 그걸 읽을 뿐 무엇인지 알지 못한다.

## 2-layer 아키텍처

1. **`harness_core`** (이 repo, `src/harness_core/`) — 제네릭 파이썬 패키지. git/io/state/local/config/preflight/scaffold 모듈. 프로젝트 상수를 모른다(경로·base 브랜치 등은 호출측이 주입). `pip install -e .` 로 설치.
   - `trackers/github` 는 **opt-in 어댑터**다. 코어 커맨드 8개와 달리 `build_core_parser()` 가 등록하지 않고, 프로젝트 `project.py` 가 `register_github_commands(sub, ...)` 로 직접 가져간다. owner·repo·프로젝트 번호·필드/옵션 이름은 전부 **인자로 주입**되고, 예약 라벨 목록은 리포의 issue type 이름과 프로젝트 필드 옵션 이름에서 런타임에 도출된다 — 어댑터 소스에 특정 프로젝트의 값이 등장하지 않는다. 계약은 `skills/_shared/references/github-issue-fields.md`.
   - 두 템플릿의 갱신 규칙이 다르다. `project.py` 는 `preserve_existing` 이라 위 예시는 **새 프로젝트에만** 닿고, 기존 프로젝트는 자기 `project.py` 에 등록을 직접 넣는다. 반면 `harness/config.py` 는 관리 대상이므로 `harness-update` 가 **기존 프로젝트에서도 덮어쓴다** — `github_project()` 는 그 경로로 전달된다.
2. **per-project harness** — 각 프로젝트의 `.claude/scripts/harness/`. `harness_core`를 프로젝트 기본값(PLAN_DIR, STATE_FILE, BASE_BRANCH 등)으로 감싸는 얇은 래퍼. `harness-init`/`harness-update`가 canonical wrapper를 생성·갱신한다.
3. **글로벌 스킬** (이 repo, `skills/`) — `harness_core`/`project.py`를 구동하는 오케스트레이션 레이어. 아래 참조.

## skills/

워크플로우 글로벌 스킬의 **정본(source of truth)**. Claude Code 는 `~/.claude/skills/` 에서 스킬을 읽으므로, `install-skills.sh` 가 이 repo 의 각 스킬을 그곳에 심링크한다. 스킬을 고친다 = 이 repo 의 파일을 고친다 → git 으로 추적되고, 스크립트 재실행으로 재배포된다.

| 스킬 | 역할 |
|------|------|
| `project-plan` | 플랜 문서 작성(frontmatter 선언 포함) |
| `project-issue` | 플랜을 이슈 트래커에 등록. GitHub 은 단일 `create-issue` 호출로 type·label·priority·size·초기 Status 를 함께 적용한다. `--issue <id>` 면 새 티켓 없이 기존 이슈에 연결한다 |
| `project-start` | 브랜치/워크트리 생성 + 이슈 In Progress + 구현 시작. 로컬 `plan-<id>.md` 가 없으면 브랜치를 만들기 전에 멈춘다 |
| `project-done` | PR 생성 + 리뷰 상태 전환 |
| `project-adr` | ADR 문서 작성 |
| `project-clean` | stale 브랜치/워크트리 정리 |
| `project-release` | Cargo 변경을 조사해 패키지별 SemVer를 제안하고, 확인 후 단일 release commit과 로컬 annotated tag 생성(publish/push 금지) |
| `project-release-doc` | 두 릴리즈 지점을 비교해 변경·리스크·배포 체크리스트를 담은 한국어 릴리즈 문서 생성(배포 실행 금지) |
| `project-iterate` | plan → issue → start → done 을 한 번에 실행(단계 사이 사용자 확인). `project-iterate <id>` 는 기존 이슈에서 출발하며, 플랜이 없으면 이슈 본문으로 쓰고 연결 모드로 붙인다 |
| `project-harness-init` | 새 프로젝트에 local harness scaffold 생성 |
| `project-harness-update` | 기존 프로젝트 local harness를 canonical wrapper로 갱신 |
| `SKILL-CONFIG.md` | 스킬 공통 설정/규약 |

> 무관 스킬(`code-efficiency`/`fix-build`/`gemini-export` 등 일반 유틸리티)은 이 repo 범위 밖이며 `~/.claude/skills/` 에 그대로 둔다 — `install-skills.sh` 는 `skills/` 에 있는 항목만 심링크한다.

### 전제 도구

이 스킬셋은 아래 도구를 전제한다. 정본은 `skills/dependencies.yaml` 이고 **이 표는 거기서 파생된다** — 표만 고치면 `tests/test_skill_docs.py` 의 일치 단언이 깨진다.

| 도구 | 필수 | 설치 | 없으면 | 최소 버전 |
|------|------|------|--------|-----------|
| `code-review@claude-plugins-official` | required | `claude plugin install code-review@claude-plugins-official` | 리뷰가 사슬 첫 칸을 잃는다. 역할별 독립 서브에이전트로, 그마저 없으면 메인 에이전트가 역할별로 직접 수행하는 데까지 내려가며 리뷰 자체는 중단되지 않는다. | - |
| `pr-review-toolkit@claude-plugins-official` | optional | `claude plugin install pr-review-toolkit@claude-plugins-official` | 역할별 전문 리뷰어(침묵 실패·타입 설계·테스트 커버리지)를 못 쓴다. 선언된 역할 또는 기본 3역할 리뷰로 수행한다. | - |
| `security-guidance@claude-plugins-official` | optional | `claude plugin install security-guidance@claude-plugins-official` | 보안은 implementer 역할의 기본 focus 안에서만 다뤄진다. 이 스킬셋은 별도 보안 패스를 지휘하지 않으므로, 있으면 사용자가 직접 돌릴 수 있다는 뜻이다. | - |
| `ENABLE_LSP_TOOL` | optional | `export ENABLE_LSP_TOOL=1` | 중복 탐색이 구조 기반에서 텍스트 기반으로 내려간다. Grep/Glob 만으로 수행하고, 구조적 중복을 놓쳤을 수 있음을 플랜에 남긴다. | - |
| `language-lsp@claude-plugins-official` | optional | `claude plugin install rust-analyzer-lsp@claude-plugins-official` | `ENABLE_LSP_TOOL` 이 켜져 있어도 해당 언어의 심볼 질의가 되지 않는다. 텍스트 기반 탐색으로 내려간다. | - |
| `git` | required | `https://git-scm.com` | 폴백이 없다. 브랜치·워크트리·커밋·머지 판정이 전부 이 도구 위에 있어 없으면 워크플로우 스킬 자체가 성립하지 않는다. | 2.23.0 |
| `gh` | optional | `https://cli.github.com/` | `issue_tracker: github` 인 프로젝트에서는 사실상 required 다. 없으면 이슈 조회·생성, PR 생성, 프로젝트 필드 반영이 모두 막히고 스킬은 웹 UI 수동 처리를 안내한 뒤 사용자가 준 결과로 이어간다. | 2.97.0 |
| `fj` | optional | `https://codeberg.org/forgejo-contrib/forgejo-cli` | `issue_tracker: forgejo` 인 프로젝트에서는 사실상 required 다. 조회가 막히면 그 항목을 미확인으로 표기하고 절차를 계속하며, 쓰기가 필요한 단계는 웹 UI 수동 처리로 내려간다. | 0.6.0 |
| `jira` | optional | `https://github.com/ankitpokhrel/jira-cli` | `issue_tracker: jira` 인 프로젝트에서는 사실상 required 다. 없으면 티켓 조회·상태 전환·코멘트가 막히고 스킬은 웹 UI 수동 처리를 안내한 뒤 사용자가 준 결과로 이어간다. | 1.7.0 |
| `uv` | required | `https://docs.astral.sh/uv/` | harness 부트스트랩 스킬(project-harness-init·project-harness-update)에 폴백이 없다. preflight 가 게이트로 요구하므로 없으면 scaffold 가 파일을 하나도 쓰지 않고 멈춘다. 이미 설치된 프로젝트의 일상 워크플로우 스킬은 영향받지 않는다. | 0.7.8 |
| `python3` | required | `https://www.python.org/` | 폴백이 없다. harness_cli.py 가 프로젝트의 단일 진입점이고, harness_enabled 인 프로젝트의 모든 로컬·트래커 커맨드가 이 인터프리터 위에서 돈다. | 3.11.0 |

`required` 는 **문서화된 기본 경로가 그 도구를 쓴다**는 뜻이지 워크플로우 게이트가 아니다. 다만 폴백이 있는지, 없으면 무엇이 무너지는지는 `없으면` 열이 말한다 — `git`·`python3` 처럼 폴백이 아예 없는 도구도 있다. 이 스킬셋은 이 **플러그인**이 하나도 없는 호스트(Codex, CI)에서도 돌아야 하고, 거기서 폴백은 부수적 경로가 아니라 1급 경로다.

트래커 CLI(`gh`·`fj`·`jira`)가 `optional` 인 것은 조건부라는 뜻이다. 해당 `issue_tracker` 를 쓰는 프로젝트에서는 사실상 required 이고, 그 조건은 `없으면` 열의 첫 문장에 있다.

`최소 버전` 열은 매니페스트의 `min_version` 에서 파생된다. CLI 가 아닌 항목은 `-` 다. 이 값은 **선언될 뿐 `./install-skills.sh` 가 비교하지 않는다**. 버전 확인 명령은 도구마다 달라 추론할 수 없으므로 매니페스트가 `version_probe` 로 따로 선언한다 — 명령 자체는 거기서 보고, 여기에 옮겨 적지 않는다.

전제의 축은 둘이고 섞으면 안 된다.

- **presence** — 이 머신에 설치되어 있는가. `./install-skills.sh` 가 링크 후 보고하는 유일한 축이다. 설치하지 않고, 누락이 있어도 **exit 0** 이다.
- **probe** — 지금 실행 중인 주체가 실제로 쓸 수 있는가. 같은 머신이라도 호스트(터미널 Claude Code / Desktop / Codex / CI)에 따라 갈리며 설치 스크립트는 이걸 답할 수 없다. 도구별 관찰 방법은 매니페스트의 `probe` 에 있다.

presence 가 초록이어도 probe 가 통과한다는 뜻이 아니다. 스킬은 도구가 **없을 때**뿐 아니라 **쓸 수 없을 때**도 degrade 경로로 내려간다.

### 릴리즈 흐름 및 migration notice

`project-release`는 이제 문서 생성이 아니라 로컬 release mutation을 뜻한다. 패키지별 버전 변경을 확인받아 정확히 하나의 commit과 같은 commit을 가리키는 package tag들을 만들며, publish와 push는 하지 않는다. 기존 문서 전용 호출은 `project-release-doc <package> [<from>..<to>]`으로 이름이 바뀌었다.

권장 순서는 `project-release`로 버전·commit·tag를 준비한 다음 `project-release-doc`으로 릴리즈/배포 문서를 만드는 것이다. 후자는 문서와 그 commit 외에는 저장소나 배포 환경을 변경하지 않는다.

### 설치 / 재배포

```bash
./install-skills.sh
```

멱등(idempotent)·안전:

- 올바른 심링크가 이미 있으면 no-op
- 다른 곳을 가리키는 심링크면 재지정
- 실제 파일/디렉터리가 자리에 있으면 `<name>.bak.<timestamp>` 로 백업 후 교체

커스텀 대상 디렉터리(테스트 등)는 `CLAUDE_SKILLS_DIR` 로 override:

```bash
CLAUDE_SKILLS_DIR=/tmp/skills ./install-skills.sh
```

## 개발

```bash
uv sync                       # 의존성
.venv/bin/python -m pytest tests/ -v
```

### local harness scaffold

```bash
.venv/bin/python -m harness_core.scaffold init --target /path/to/project
.venv/bin/python -m harness_core.scaffold init --target /path/to/project --apply

.venv/bin/python -m harness_core.scaffold update --target /path/to/project
.venv/bin/python -m harness_core.scaffold update --target /path/to/project --apply
```

설치된 console script를 사용할 수 있는 환경에서는 `harness-init`과 `harness-update`가 같은 동작을 수행한다. 두 명령은 write 전에 Python 최소 버전과 `uv`/`git` preflight를 수행하고, 실패 시 대상 프로젝트를 변경하지 않는다.
