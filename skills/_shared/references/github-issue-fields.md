<!-- Referenced from skills/SKILL-CONFIG.md. 이 문서는 SKILL-CONFIG.md 에서 갈라져
     나온 것이 아니라 새로 쓴 계약이다. project-issue · project-start · project-done
     세 스킬이 이 경로를 읽는다. 그 스킬이 말할 때만 읽는다. -->

# GitHub 이슈 메타데이터 계약 (`issue_tracker: github`)

같은 정보가 issue type · 라벨 · 프로젝트 필드 세 곳에 따로 적히는 드리프트를 막는 계약이다.
규칙의 **정본은 이 문서 하나**이고, 세 스킬은 이 경로를 가리킬 뿐 규칙을 복제하지 않는다.

이 계약은 `issue_tracker: github` 에만 적용된다. Jira · Forgejo 는 자기 필드 모델을 따른다.

## ① 데이터 모델

한 정보는 한 자리에만 적는다.

| 정보 | 정본 자리 | 쓰는 방법 |
|------|-----------|-----------|
| type | GitHub **issue type** | `gh issue create --type`, `gh issue edit --type` |
| priority | **프로젝트 단일 선택 필드** (`field_names.priority`) | 프로젝트 필드 쓰기 |
| size | **프로젝트 단일 선택 필드** (`field_names.size`) | 프로젝트 필드 쓰기 |
| status | **프로젝트 Status 필드** (`status_names.*`) | 프로젝트 필드 쓰기 |
| 영역 태그 | **라벨** | `gh issue create --label` |

라벨은 영역 태그만 싣는다. type · priority · size · status 를 라벨로 적지 않는다.
`in-progress` · `in-review` 같은 워크플로우 상태 라벨도 이 규칙에 걸린다 — 상태는 Status 필드다.

## ② 예약 라벨의 도출 규칙

예약 라벨 목록을 이 문서에도, 스킬에도, 코어 소스에도 **적지 않는다**. 목록은 런타임에 도출한다.

> 예약 라벨 = 리포의 issue type 이름 ∪ `field_names.priority` 필드의 옵션 이름 ∪
> `field_names.size` 필드의 옵션 이름 (대소문자 무시)

리포가 issue type 을 쓰지 않으면 그쪽 집합은 빈 집합으로 degrade 한다. 프로젝트가 옵션 이름을
바꾸면 예약 목록도 따라 바뀐다 — 이것이 목록을 적지 않는 이유다.

검사 결과는 **거부**다. `--label <priority 옵션 이름>` 을 조용히 `--priority` 로 바꾸지 않는다.
호출측이 무엇을 의도했는지는 호출측만 안다.

## ③ 관측 우선 (read-back)

이슈를 만든 뒤 **실제로 무엇이 붙었는지 다시 읽어서** 보고한다. 추론값을 보고하지 않는다.
요청과 관측이 다르면 차이를 그대로 적는다 — 자동화 봇·리포 기본 라벨·프로젝트 자동화가
요청하지 않은 값을 넣을 수 있고, 그것을 감추면 드리프트가 다음 세션에 그대로 넘어간다.

읽기-되돌림이 선택이 아닌 결정적인 이유가 하나 더 있다. GitHub REST 는 이슈 생성·수정에서
**push 권한이 없는 토큰의 `type` 을 오류 없이 조용히 버린다**(API 스펙 원문: *"The type is
silently dropped otherwise"*). 즉 성공 응답을 받고도 type 이 안 붙어 있을 수 있고, 그 사실은
다시 읽어야만 보인다.

## ④ `github_project` 설정 스키마

```yaml
github_repo: <owner>/<repo>
github_project:
  owner: <login>                 # 조직 또는 사용자. organization → user 순으로 조회한다
  number: <int>                  # 프로젝트(Projects V2) 번호
  status_names:                  # Status 필드의 옵션 이름 — 프로젝트마다 다르다
    backlog: <name>
    in_progress: <name>
    in_review: <name>
  field_names:                   # 단일 선택 필드의 이름. 생략 시 "Priority" / "Size" / "Status"
    priority: <name>
    size: <name>
    status: <name>               # 선택 — Status 필드 이름을 바꾼 프로젝트만
```

값은 전부 **프로젝트 상수**이며 각 프로젝트의 `.claude/skill-config.yaml` 에만 둔다.
이 문서와 스킬 본문에는 `<owner>` · `<github_project.number>` 같은 플레이스홀더만 쓴다.

`github_project` 블록이 없으면 프로젝트 필드 경로는 쓸 수 없다 — 그 경우 필드는 "미반영"(⑦)으로
보고하고 절차는 계속한다. type 과 라벨은 블록 없이도 쓸 수 있다.

## ⑤ gh CLI 폴백 명령

`harness_enabled: false` 이거나 harness 호출이 실패했을 때 쓰는 경로다. 폴백에서도 모델은 같다.

**"실패" 는 호출이 성립하지 않은 경우다.** `create-issue` 가 `REFUSED` 의 환경 거부나 `UNKNOWN` 으로
끝난 것은 판정이 **수행된** 결과이지 호출의 실패가 아니다(뜻은 `~/.claude/skills/_shared/references/exit-codes.md`
의 `create-issue` 행). 이 폴백에는 예약 라벨 판정이 아예 없으므로, 그 두 결과를 실패로 읽고 내려오면
정본이 막아 세운 라벨이 그대로 통과한다. 그 경우는 폴백하지 말고 보고하고 멈춘다.

### 생성

```bash
gh issue create \
  --title "<plan title>" \
  --body-file "<draft-plan-path>" \
  --type "<type name>" \
  --label "<area tag>"
```

`--type` 은 리포에 issue type 이 설정돼 있을 때만 쓴다. 없으면 생략하고 그 사실을 보고한다.

### 프로젝트 필드 (priority · size)

```bash
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.priority>" --value "<option name>"
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field "<field_names.size>" --value "<option name>"
```

항목이 아직 프로젝트에 없으면 먼저 추가한다:

```bash
gh project item-add <github_project.number> --owner <github_project.owner> --url <issue-url>
```

### Status 전환

```bash
gh project item-edit <github_project.number> --owner <github_project.owner> \
  --url <issue-url> --field Status --value "<status_names.in_progress>"
```

`status_names.backlog` · `status_names.in_review` 도 같은 형태다. `Status` 는 GitHub Projects 가
모든 프로젝트에 만들어 주는 기본 필드 이름이라 여기에 리터럴로 적는다 — 옵션 이름은 프로젝트
상수이고, 필드 이름을 바꾼 프로젝트는 `field_names.status` 로 주입한다.

### 조회

```bash
gh issue view <issue-id> --json number,title,url,labels
gh project item-list <github_project.number> --owner <github_project.owner> --format json
```

`gh issue view --json` 은 issue type 을 돌려주지 않는다. type 까지 한 번에 읽으려면 ⑧ 의
GraphQL 형태를 쓴다.

## ⑥ 전제

- **gh 최소 버전 2.97.0 (2026-07-31)**. `gh project item-edit` 의 이름 기반 `--field` / `--value`
  해석이 이 릴리즈에서 들어왔다(cli/cli#13807). 그 이전 gh 는 필드·옵션을 **ID 로만** 받으므로
  ⑧ 로 내려간다.
- `gh project` 계열은 토큰에 `project` 스코프가 필요하다. 확인과 부여:

  ```bash
  gh auth status
  gh auth refresh --scopes project
  ```

- 플래그 존재 확인은 실행 전에 `gh project item-edit --help` 로 한다. 이 저장소는 문서에 적힌
  플래그를 `tests/fixtures/gh_flags.yaml` 과 대조하지만, 그 픽스처는 생성 시점의 gh 를 기록한
  고정 목록이지 실행 호스트의 gh 가 아니다.

## ⑦ 폴백도 실패할 때

`project` 스코프가 없거나, gh 가 낮거나, `github_project` 블록이 없어서 필드를 쓸 수 없으면
**"미반영"을 보고하고 절차를 계속한다.** 필드를 못 썼다고 이슈 등록·브랜치 생성·PR 을 세우지
않는다. 보고에는 무엇이 반영되지 않았는지와 나중에 고칠 명령을 적는다.

라벨로 우회하지 않는다 — 그것이 이 계약이 막으려는 바로 그 드리프트다.

## ⑧ 이름 기반 플래그가 없는 gh

필드·옵션 ID 를 셸에서 **조회해서** 쓴다. 조회한 ID 를 그 자리에서 쓰는 것은 하드코딩이 아니다 —
금지되는 것은 ID 를 문서·소스·설정에 **적어 두는** 것이다.

```bash
gh project field-list <github_project.number> --owner <github_project.owner> --format json
```

출력에서 필드 ID 와 단일 선택 옵션 ID 를 고른 뒤:

```bash
gh api graphql -f query='
  mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project, itemId:$item, fieldId:$field,
      value:{singleSelectOptionId:$option}
    }){ projectV2Item { id } }
  }' -f project=<project-node-id> -f item=<item-id> -f field=<field-id> -f option=<option-id>
```

이슈 메타를 type 까지 한 번에 읽는 질의도 같은 경로다 — `issueType`, `labels`,
`projectItems.fieldValues` 를 한 질의로 읽는다.
