# Handoff: trader#477 이 남긴 코어 후속 과제 2건

**날짜**: 2026-08-31
**출처**: enseed-trading-dev/trader#477 (harness CLI 단일 진입점 통합) 의 3관점 적대적 리뷰
**관련 코어 커밋**: `6df6bf4` (코어 파서 도입), `45ecd96` (`clean_up_bases` 주입)
**상태**: 미착수 — 이 저장소에서 처리해야 할 항목

trader#477 을 구현하며 설계자·구현자·테스트 엔지니어 관점의 리뷰를 돌렸고, 그중 **코어가
고쳐야 하는** 두 건이 나왔다. trader 쪽에서는 우회했거나 경계를 문서화만 했으므로, 근본
수정은 여기에 남는다.

---

## 1. `clean_up_stale_branches` 가 프로젝트 base 브랜치를 삭제한다 (데이터 손실)

**심각도**: 높음 — 되돌릴 수 없는 브랜치 삭제
**위치**: `src/harness_core/git.py:198` vs `src/harness_core/git.py:209`

### 증상

base 보호를 두 곳에서 **서로 다른 출처**로 판정한다.

```python
# git.py:198 — gone 브랜치는 bases 전체를 올바르게 제외한다
gone_branches -= set(bases)

# git.py:202-209 — merged 브랜치는 하드코딩된 두 이름만 제외한다
for base in bases:
    merged_result = _run_git("branch", "--merged", base)
    for line in merged_result.stdout.splitlines():
        stripped = line.strip().lstrip("*+ ")
        if stripped and stripped not in ("develop", "main"):   # ← bases 를 안 본다
            merged_branches.add(stripped)
```

base 는 자기 자신에 항상 merged 이므로, `bases` 에 `develop`·`main` 이 아닌 이름이 들어오면
그 브랜치가 `merged_branches` 에 들어가고 → `stale` 이 되고 → `git branch -d` 대상이 된다.

`bases=["develop","main"]` (기본값) 에서는 두 출처가 우연히 일치해 무증상이다. 그래서
지금까지 드러나지 않았다.

### 재현 (실측)

임시 저장소, base 가 `master` 인 프로젝트. 개발자는 피처 브랜치에 있다(`/clean` 을 돌리는
정상 상태).

```python
git init -b master; commit; git remote add origin <self>
git checkout -b feat/work; commit          # HEAD 가 master 가 아니어야 -d 가 성공한다

clean_up_stale_branches(bases=["develop","main","master"], plan_dir=...)
```

결과:

```
bases passed    : ['develop', 'main', 'master']
deleted_branches: ['master']
warnings        : []
master still exists: False
```

`bases` 에 **명시적으로 넘긴** 브랜치가 삭제됐고, `protected_branches` 는 비어 있으며
경고도 없다. HEAD 가 `master` 위에 있으면 git 이 현재 브랜치 삭제를 거부해 우연히 살아남는다
— 즉 개발자가 어디에 서 있느냐가 데이터 손실 여부를 가른다.

### 왜 지금 시급해졌나

`45ecd96` 이 `build_core_parser(clean_up_bases=...)` 주입점을 만들었고, scaffold 템플릿이
`sorted({BASE_BRANCH, "develop", "main"})` 을 넘기도록 바뀌었다. 즉 **이제 모든 신규 프로젝트가
자기 base 를 실제로 주입한다.** base 가 `develop`/`main` 인 프로젝트는 무해하지만, 그렇지
않은 프로젝트는 이 경로를 곧바로 밟는다. 결함 자체는 선행하지만 도달 가능성이 올라갔다.

### 처방

`git.py:209` 의 하드코딩을 `bases` 로 바꾼다.

```python
if stripped and stripped not in set(bases):
```

같은 함수 안에서 base 판정 출처가 하나여야 한다는 것이 요점이다. 두 출처가 존재하는 한
같은 형태의 결함이 다시 난다.

### 가드 (변이로 확인할 것)

- `bases=["develop","main","master"]` + HEAD 가 피처 브랜치 → `master` 가 `deleted_branches`
  에 없고 실제로 살아 있을 것
- 하드코딩을 되돌리면 그 테스트가 FAIL 할 것 (통과 사실만으로는 가드의 증거가 아니다)
- 기존 기본값 경로(`bases=None`)의 동작이 변하지 않을 것

---

## 2. 글로벌 스킬 문서의 **프로젝트 명령** 호출을 아무도 검증하지 않는다

**심각도**: 중간 — 침묵 회귀를 허용하는 커버리지 구멍
**위치**: `tests/test_cli_surface.py:82-83`

### 증상

이 저장소의 문서 스캔은 코어 명령만 검사하고, 나머지는 프로젝트에 위임한다.

```python
if command not in CORE_COMMANDS:
    continue  # project surface — asserted by the project's golden test
```

그런데 프로젝트(trader)의 대응 테스트는 **repo 안의 문서만** 열 수 있다. 글로벌 스킬은
`~/.claude/skills/project-*/SKILL.md` → 이 저장소의 `skills/` 이고, trader 의 CI 에서는
접근할 수 없는 경로다.

결과적으로 위임이 양쪽에서 닫히지 않는다:

- 여기: "프로젝트 명령은 프로젝트가 검사한다"
- trader: "글로벌 스킬은 repo 밖이라 못 연다"

`skills/project-done/SKILL.md` 의 `<harness_cli> create-pr --title … --closes …` 같은 호출은
**어느 쪽 게이트도 통과하지 않는다.** trader#477 에서 손으로 대조했을 때 17개 명령·미해석 0
이었지만, 그것은 그 시점의 사실이지 유지되는 계약이 아니다.

### 처방 (택일)

- **A. 검증 명령을 코어에 넣는다.** `harness_cli validate-docs <path>` 를 코어 명령으로
  추가하고, 프로젝트 CI 가 자기 파서로 임의 디렉터리를 검사하게 한다. 프로젝트가 글로벌
  스킬 사본을 가진 경우(설치 스크립트가 심링크한다) 그 경로를 넘기면 된다.
- **B. 프로젝트 명령 인벤토리를 선언으로 받는다.** 이 저장소가 스킬 문서를 스캔하되,
  코어가 모르는 명령은 "프로젝트가 선언한 목록" 과 대조한다. 목록은 각 프로젝트가
  `skill-config.yaml` 에 적는다.

A 가 단순하고, 검증 주체가 실제 파서를 가진 쪽이라는 점에서 축이 맞다. B 는 목록이 또 하나의
갈라질 수 있는 사본이 된다.

어느 쪽이든 **`continue` 로 위임하고 끝내지 않는 것**이 핵심이다. 위임은 받는 쪽이 실제로
할 수 있을 때만 위임이다.

---

## 참조

- trader#477 impl-report — `남은 갭` 절
- trader ADR `2026-08-31-harness-cli-single-entrypoint-dependency-inversion.md`
  (의존 역전 결정과 트레이드오프)
- `src/harness_core/git.py` — `clean_up_stale_branches`
- `tests/test_cli_surface.py` — 코어 문서 스캔
