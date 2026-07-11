# workflow-harness

Claude Code 워크플로우 자동화(plan → issue → start → done → clean)의 **공유 코어와 글로벌 스킬**을 버전 관리하는 저장소.

여러 프로젝트(enseed-trader, cosmos-forge 등)가 동일한 워크플로우 패턴을 쓰되 프로젝트별 상수만 다르다. 그 공통분모를 여기에 모아 한 곳에서 추적·리뷰·롤백한다.

## 2-layer 아키텍처

1. **`harness_core`** (이 repo, `src/harness_core/`) — 제네릭 파이썬 패키지. git/io/state/local/config/preflight/scaffold 모듈. 프로젝트 상수를 모른다(경로·base 브랜치 등은 호출측이 주입). `pip install -e .` 로 설치.
2. **per-project harness** — 각 프로젝트의 `.claude/scripts/harness/`. `harness_core`를 프로젝트 기본값(PLAN_DIR, STATE_FILE, BASE_BRANCH 등)으로 감싸는 얇은 래퍼. `harness-init`/`harness-update`가 canonical wrapper를 생성·갱신한다.
3. **글로벌 스킬** (이 repo, `skills/`) — `harness_core`/`project.py`를 구동하는 오케스트레이션 레이어. 아래 참조.

## skills/

워크플로우 글로벌 스킬의 **정본(source of truth)**. Claude Code 는 `~/.claude/skills/` 에서 스킬을 읽으므로, `install-skills.sh` 가 이 repo 의 각 스킬을 그곳에 심링크한다. 스킬을 고친다 = 이 repo 의 파일을 고친다 → git 으로 추적되고, 스크립트 재실행으로 재배포된다.

| 스킬 | 역할 |
|------|------|
| `project-plan` | 플랜 문서 작성(frontmatter 선언 포함) |
| `project-issue` | 플랜을 이슈 트래커에 등록 |
| `project-start` | 브랜치/워크트리 생성 + 이슈 In Progress + 구현 시작 |
| `project-done` | PR 생성 + 리뷰 상태 전환 |
| `project-adr` | ADR 문서 작성 |
| `project-clean` | stale 브랜치/워크트리 정리 |
| `project-release` | Cargo 변경을 조사해 패키지별 SemVer를 제안하고, 확인 후 단일 release commit과 로컬 annotated tag 생성(publish/push 금지) |
| `project-release-doc` | 두 릴리즈 지점을 비교해 변경·리스크·배포 체크리스트를 담은 한국어 릴리즈 문서 생성(배포 실행 금지) |
| `project-iterate` | 리뷰 피드백 반영 반복 |
| `project-harness-init` | 새 프로젝트에 local harness scaffold 생성 |
| `project-harness-update` | 기존 프로젝트 local harness를 canonical wrapper로 갱신 |
| `SKILL-CONFIG.md` | 스킬 공통 설정/규약 |

> 무관 스킬(`code-efficiency`/`fix-build`/`gemini-export` 등 일반 유틸리티)은 이 repo 범위 밖이며 `~/.claude/skills/` 에 그대로 둔다 — `install-skills.sh` 는 `skills/` 에 있는 항목만 심링크한다.

### 릴리즈 흐름 및 migration notice

`$project-release`는 이제 문서 생성이 아니라 로컬 release mutation을 뜻한다. 패키지별 버전 변경을 확인받아 정확히 하나의 commit과 같은 commit을 가리키는 package tag들을 만들며, publish와 push는 하지 않는다. 기존 문서 전용 호출은 `$project-release-doc <package> [<from>..<to>]`으로 이름이 바뀌었다.

권장 순서는 `$project-release`로 버전·commit·tag를 준비한 다음 `$project-release-doc`으로 릴리즈/배포 문서를 만드는 것이다. 후자는 문서와 그 commit 외에는 저장소나 배포 환경을 변경하지 않는다.

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
