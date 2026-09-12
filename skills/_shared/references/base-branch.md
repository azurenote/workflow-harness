<!-- Split out of skills/SKILL-CONFIG.md. Every skill used to read the whole
     config document at startup, including the parts that did not apply to it.
     Read this file only when the skill says it needs it. -->

# base branch 우선순위 (작업별)

PR 리뷰·머지 대상 base 는 **두 출처**가 있고, 좁은 범위가 우선한다:

1. **플랜 frontmatter `base_branch`** (작업별, 최우선) — 서브이슈가 상위 user-story 통합 브랜치 위로 머지될 때 `project-plan`·`cross-plan` 이 선언한다. `project-start`·`project-done` 은 `harness_cli get-base <id>` 로 읽어 **그대로 사용**(런타임 추론 없음). `/issue` 가 플랜 전체를 이슈 본문으로 올리므로 이슈 description 에도 자동 포함된다.
2. **`skill-config.yaml` `base_branch`** (프로젝트 기본) — 위 frontmatter 가 없을 때 적용. 값은 프로젝트마다 다르고, 공유 문서는 그 값을 알지 못한다.

즉 frontmatter 미선언 = 프로젝트 기본 base(기존 동작, 신규 프롬프트 없음). frontmatter 선언 = 그 통합 브랜치가 base 이며, default 가 아니므로 **서브-PR** 로 취급한다(`project-done` 이 `Closes #<id>` 대신 `Part of #<parent_issue>` 사용).
