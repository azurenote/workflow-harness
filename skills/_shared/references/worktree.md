<!-- Split out of skills/SKILL-CONFIG.md. Every skill used to read the whole
     config document at startup, including the parts that did not apply to it.
     Read this file only when the skill says it needs it. -->

# 워크트리 경로 주의사항

`.task/plan/` 과 `.claude/state.json` 은 gitignore 되어 **main checkout 에만** 있다.
`harness_cli.py` 와 `project.py` 는 워크트리 CWD 에서 호출해도 이 둘을 main checkout 기준으로
resolve 한다(`harness_core.git.main_worktree_root()`). 단, main work tree 가 없는 레이아웃에서는
추측하지 않고 `MainWorktreeUnresolvedError` 로 멈춘다(아래 표). `create-worktree` 도 같은 기준이다 —
상대 경로를 main checkout 아래로 풀고 main checkout 에서 분기하므로, 링크드 워크트리 CWD 에서 불러도
워크트리가 그 안에 중첩되거나 그 feature 에서 갈라지지 않는다.

단, `git add` / `git commit` / `git push` 는 **워크트리 CWD** 에서 실행해야
현재 브랜치에 붙는다. `cd` 를 반복하지 말 것.

## main checkout 해석 정본

main checkout 경로가 필요한 셸 단계(harness 가 없을 때의 fallback 포함)는 아래 블록을 **문자 그대로** 복사해 쓴다. 변수명만 `MAIN_CHECKOUT`
또는 `REPORT_ROOT` 로 바꿀 수 있다. 이 파일이 원본이고, 스킬의 사본이 이 블록과 같은지는
`tests/test_skill_docs.py` 가 검사한다. 스킬이 실행 중에 이 파일을 읽는 것은 아니다.

```bash
FIRST_WORKTREE="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
MAIN_CHECKOUT="$([ -n "$FIRST_WORKTREE" ] && git -C "$FIRST_WORKTREE" rev-parse --show-toplevel 2>/dev/null || :)"
[ -n "$MAIN_CHECKOUT" ] && [ -d "$MAIN_CHECKOUT" ] || {
  echo "could not resolve the main checkout"; exit 1; }
```

규칙: `git worktree list --porcelain` 의 첫 항목을 얻고, **그 항목의 작업 트리를 git 에게 다시 묻는다**
(`git -C <첫 항목> rev-parse --show-toplevel`). 답이 없으면 멈춘다. `main_worktree_root()` 도 같은 규칙이다.

- 첫 항목을 그대로 쓰지 않는다. submodule 에서는 `.git/modules/<name>`, separate-git-dir 에서는 git dir 이 첫 항목으로 나온다.
- `--git-common-dir` 의 부모로 만들지 않는다. submodule·separate-git-dir·bare 에서 **존재하는 엉뚱한 디렉터리**가 된다.
- CWD 의 `--show-toplevel`·`$PWD` 로 만들지 않는다. 링크드 워크트리 자신이 나온다.
- `[ -n "$FIRST_WORKTREE" ] &&` 를 빼지 않는다. `git -C ""` 는 CWD 에 머물러 링크드 워크트리를 답한다.
- `|| :` 를 빼지 않는다. 대입문의 종료코드는 치환의 종료코드라서, 이게 없으면 `sh -e` 가 아래 메시지 전에 셸을 죽인다.

| 레이아웃 | 답 |
|----------|----|
| 일반 clone | main checkout |
| 링크드 워크트리 | main checkout |
| submodule | submodule checkout |
| submodule 의 링크드 워크트리 | submodule checkout |
| separate-git-dir | 멈춤 |
| bare | 멈춤 |
| bare 의 링크드 워크트리 | 멈춤 |

git dir 이름이 다른 디렉터리의 `.git` 인 separate-git-dir(`--separate-git-dir=/x/other/.git`)는 git 이 그 부모를 작업 트리로 보고하므로 이 규칙이 가려내지 못한다 — 드문 배치라 검사하지 않는다. 그 밖의 separate-git-dir 는 링크드 워크트리에서 main work tree 를 알아낼 방법이 없다(git dir 이 작업 트리를
가리키지 않는다). 그래서 main 에서 부르든 링크드에서 부르든 똑같이 멈춘다. 저장소 밖에서는 셸 블록이 멈추고,
`main_worktree_root()` 는 CWD 로 폴백한다.
