---
name: project-harness-init
description: 새 프로젝트에 workflow-harness local wrapper를 설치한다. Python/uv/git preflight와 dry-run 확인을 거친 뒤 project-local `.claude/scripts/` harness를 생성한다. Codex에서는 `$project-harness-init ...` 또는 "project-harness-init 스킬로 ..." 요청 시 실행.
---

# project-harness-init — local harness 초기 설치

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- `$project-harness-init <target-project-root>` 또는 "harness init", "local harness 설치", "새 프로젝트에 workflow-harness 붙이기" 요청
- 새 repo에 `.claude/scripts/harness_cli.py`, `.claude/scripts/harness/`, `.claude/skill-config.yaml` scaffold가 필요할 때

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Instructions

**1. 대상 확인**

대상 project root를 확인한다. 인자가 없으면 현재 작업 의도에서 추출하고, 불명확하면 사용자에게 묻는다.

확인할 값:
- target root 절대 경로
- `base_branch` (기본: 설정의 `base_branch`)
- `issue_tracker` 및 repo/remote 값
- 기존 `.claude/scripts/harness_cli.py` 또는 `.claude/scripts/harness/` 존재 여부

기존 local harness가 있으면 init으로 덮어쓰지 않는다. `$project-harness-update`를 안내하거나 사용자가 명시적으로 overwrite를 요청할 때만 별도 작업으로 다룬다.

**2. preflight**

write 전 반드시 Python core preflight를 실행한다. 이 단계가 실패하면 target project에는 아무 파일도 쓰지 않는다.

```bash
python -m harness_core.scaffold init --target "<target-root>"
```

또는 console script가 설치되어 있으면:

```bash
harness-init --target "<target-root>"
```

preflight는 최소 다음을 확인해야 한다:
- 현재 Python 버전이 workflow-harness `pyproject.toml`의 `requires-python`을 만족한다.
- `uv --version`이 성공한다.
- `git --version`이 성공한다.

실패 시 현재 버전, 필요한 버전, 누락 도구, 권장 조치를 보고하고 중단한다. 자동 설치는 하지 않는다.

**3. dry-run 확인**

dry-run 출력에서 다음을 확인한다:
- `created`: 새로 만들 파일
- `updated`: init에서는 없어야 정상
- `skipped`: 보존된 project-specific 파일
- `warnings`: preflight 또는 existing harness 경고

사용자에게 target root와 생성 예정 파일을 보여주고 확인을 받는다.

**4. apply**

사용자가 승인하면 apply를 실행한다.

```bash
python -m harness_core.scaffold init \
  --target "<target-root>" \
  --base-branch "<base-branch>" \
  --issue-tracker "<forgejo|github|jira>" \
  --forgejo-remote "<remote-name>" \
  --forgejo-repo "<owner/repo>" \
  --apply
```

또는:

```bash
harness-init --target "<target-root>" --apply
```

**5. smoke 검증**

생성된 local CLI가 import 가능한지 확인한다.

```bash
python "<target-root>/.claude/scripts/harness_cli.py" --help
```

필요하면 target repo에서 `uv sync` 후 같은 smoke를 다시 실행한다.

**6. Output**

- target root
- preflight 결과(Python required/current, uv/git status)
- 생성 파일 목록
- 보존/skip 파일 목록
- smoke 결과
- 다음 단계: target repo에서 `$project-plan` 또는 기존 workflow 시작

## Drift Guards

- user scope skills 설치(`~/.codex/skills` 또는 `~/.claude/skills`)와 project-local harness init을 섞지 않는다.
- Python/uv/git preflight 실패 상태에서 target project에 파일을 만들지 않는다.
- GitHub Projects/Forgejo/Jira 세부 ID를 자동 추론하지 않는다. 필요한 값은 placeholder 또는 사용자 입력으로 남긴다.
