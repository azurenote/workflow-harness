---
name: project-harness-update
description: 기존 프로젝트의 workflow-harness local wrapper를 최신 canonical wrapper로 동기화한다. dry-run/diff와 backup 경로를 먼저 보여주고, project-specific 설정은 보존한다. Codex에서는 `$project-harness-update ...` 또는 "project-harness-update 스킬로 ..." 요청 시 실행.
---

# project-harness-update — local harness 갱신

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- `$project-harness-update <target-project-root>` 또는 "harness update", "local harness 동기화", "wrapper 갱신" 요청
- `harness_core` public contract나 canonical wrapper 템플릿이 바뀐 뒤 기존 프로젝트를 맞춰야 할 때

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Instructions

**1. 대상 확인**

대상 project root를 확인한다. 인자가 없으면 현재 repo를 대상으로 한다.

확인할 값:
- target root 절대 경로
- 기존 `.claude/skill-config.yaml`
- 기존 `.claude/scripts/project.py`
- 기존 `.claude/scripts/harness_cli.py`
- 기존 `.claude/scripts/harness/`

**2. preflight + dry-run**

write 전 반드시 dry-run을 실행한다.

```bash
python -m harness_core.scaffold update --target "<target-root>"
```

또는 console script가 설치되어 있으면:

```bash
harness-update --target "<target-root>"
```

preflight는 Python 최소 버전, `uv`, `git`을 확인한다. 실패하면 아무 파일도 쓰지 않고 중단한다.

dry-run 출력에서 다음을 확인한다:
- `created`: 누락되어 새로 만들 canonical 파일
- `updated`: canonical template과 달라 교체할 파일
- `unchanged`: 이미 canonical인 파일
- `skipped`: project-specific이라 보존할 파일
- `backed_up`: apply 시 backup될 경로
- `warnings`: conflict 또는 preflight 경고

**3. 보존 경계 확인**

다음 파일은 project-specific 값이 있으므로 기본적으로 보존한다:
- `.claude/skill-config.yaml`
- `.claude/scripts/project.py`
- hooks, tracker-specific constants, repo/remote 설정
- `.claude/scripts/harness/` 아래 local-only/custom 파일

canonical wrapper 파일은 manifest/template version 또는 content 비교로 갱신한다. manifest가 없는 legacy wrapper도 content mismatch로 update 대상이 될 수 있다.

**4. apply**

사용자가 dry-run을 승인하면 apply한다.

```bash
python -m harness_core.scaffold update --target "<target-root>" --apply
```

또는:

```bash
harness-update --target "<target-root>" --apply
```

update 대상 파일이 기존에 있으면 target repo 내부 `.claude/scripts/.harness-backup/<timestamp>/` 아래에 먼저 백업한다.

**5. smoke 검증**

```bash
python "<target-root>/.claude/scripts/harness_cli.py" --help
```

실패하면 변경 파일과 backup 경로를 보고한다. 자동 rollback은 하지 말고 사용자가 확인할 수 있게 둔다.

**6. Output**

- target root
- preflight 결과
- created/updated/unchanged/skipped/backed_up 목록
- smoke 결과
- 보존된 project-specific 파일 목록

## Drift Guards

- 여러 sibling 프로젝트를 자동 탐색해 일괄 write하지 않는다. 다중 target은 명시 인자와 target별 확인이 있을 때만 허용한다.
- `.claude/skill-config.yaml`과 `.claude/scripts/project.py`를 canonical template으로 무조건 덮어쓰지 않는다.
- 복잡한 merge/backup 판단을 shell snippet으로 구현하지 않는다. `harness_core.scaffold` 결과를 source of truth로 삼는다.
