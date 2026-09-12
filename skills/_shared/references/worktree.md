<!-- Split out of skills/SKILL-CONFIG.md. Every skill used to read the whole
     config document at startup, including the parts that did not apply to it.
     Read this file only when the skill says it needs it. -->

# 워크트리 경로 주의사항

`harness_cli.py` 와 `project.py` 는 워크트리 CWD에서 호출해도
`.task/plan/` 및 `.claude/state.json` 을 **메인 워크트리 기준**으로 자동 resolve한다.

단, `git add` / `git commit` / `git push` 는 **워크트리 CWD** 에서 실행해야
현재 브랜치에 붙는다. `cd` 를 반복하지 말 것.
