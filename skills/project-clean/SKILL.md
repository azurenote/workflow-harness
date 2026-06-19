---
name: project-clean
description: PR 머지 후 gone 브랜치와 연결된 워크트리를 일괄 정리한다. Codex에서는 `$project-clean` 또는 "project-clean 스킬로 ..." 요청 시 실행.
---

# project-clean — 브랜치 및 워크트리 정리

## 트리거 조건

다음 상황에서 이 스킬을 적용한다:
- `$project-clean` 또는 "브랜치 정리", "워크트리 정리", "gone 브랜치", "clean" 키워드
- PR 머지 후 정리 작업 요청 시

## 설정 읽기

`~/.claude/skills/SKILL-CONFIG.md` 의 "설정 읽기" 절차를 먼저 실행한다.

## Instructions

`harness_enabled: true`:
```bash
<harness_cli> clean-up
```

스크립트 동작:
1. `git fetch --prune` — 리모트 트래킹 ref 정리
2. gone 브랜치(`git branch -vv`) + 머지된 브랜치(`git branch --merged <base_branch>`) 수집
3. **선언 base 보호**: `.task/plan/plan-<id>.md` frontmatter 의 `base_branch` 로 선언된 통합 브랜치는 stale(gone/merged) 여도 삭제 대상에서 제외(로컬 스캔, 네트워크 無). 서브-PR 이 open 인 동안 통합 브랜치가 자동 삭제되는 데이터 손실 방지.
4. stale 브랜치에 연결된 워크트리 `git worktree remove --force` 로 먼저 제거
5. 브랜치 삭제 — 머지 확인 브랜치 `-d`, gone 전용 브랜치 `-D`
6. JSON 결과: `removed_worktrees`, `deleted_branches`, **`protected_branches`**(보호된 선언 base 목록), `warnings`. `protected_branches` 를 사용자에게 보고해 어떤 통합 브랜치가 보존됐는지 보이게 한다.

`harness_enabled: false`:
> ⚠️ fallback 경로는 **선언 base 보호를 적용하지 않는다.** 아래 명령을 그대로 쓰면 다른 서브이슈가 base 로 삼는 통합 브랜치까지 삭제할 수 있다. 삭제 전 보호 집합을 직접 수집해 제외하라:
```bash
git fetch --prune

# (선) 보호할 선언 base 수집 — plan-*.md frontmatter 의 base_branch (네트워크 無)
PROTECT=$(grep -hERo '^base_branch:[[:space:]]*\S+' .task/plan/plan-*.md 2>/dev/null \
  | sed -E 's/^base_branch:[[:space:]]*//' | sort -u)

# gone 브랜치 목록 (보호 집합 제외)
git branch -vv | grep '\[origin/.*: gone\]' | awk '{print $1}' \
  | grep -vxF "$PROTECT" 2>/dev/null

# 워크트리 목록
git worktree list

# 수동으로 gone 브랜치 제거 — 보호 집합·기본 base(develop/main)는 제외
git worktree remove --force ".claude/worktrees/<name>" 2>/dev/null || true
git branch -D <gone-branch>   # PROTECT 에 없고 develop/main 이 아닐 때만
```
