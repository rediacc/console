---
title: "Git 방식의 브랜칭"
description: "copy-on-write 포크를 git 커밋처럼 다루세요: 포크를 변경 불가능한 커밋으로 고정하고, 브랜치를 명명하고, 커밋을 쓰기 가능한 포크로 체크아웃하고, 이력을 탐색하고, 라이브 리포지터리를 변경하지 않고 병합합니다."
category: Reference
subcategory: advanced
order: 41
language: ko
sourceHash: "6ca18986dfd6e237"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Git 방식의 브랜칭

Rediacc 리포지터리는 copy-on-write 포크 위에 구축된 git 방식의 버전 관리를 지원합니다. 각 변경 불가능한 포크는 **커밋**입니다. 마운트를 거부하는 바이트 안정적이고 고정된 이미지입니다. 브랜치는 커밋을 가리키는 명명된 참조입니다. `rdc repo checkout`은 커밋을 reflink 복제하여 쓰기 가능한 작업 포크로 만들고, `rdc repo merge`는 라이브 리포지터리를 직접 변경하지 않고 두 이력 라인을 결합합니다.

이 모델은 두 개의 저장소로 구성됩니다. **머신이 객체 저장소**입니다. 커밋은 데이터스토어에 있는 변경 불가능한 포크 이미지입니다. **CLI config가 참조 저장소**입니다. 브랜치 이름, 현재 `HEAD`, 참조 로그는 머신이 아닌 로컬 config에 있습니다. 이것은 git이 `.git/objects`와 `.git/refs` 사이에서 사용하는 것과 동일한 분리입니다.

## 사용 시기

포크가 이름을 얻을 만큼 중요해졌을 때 브랜칭을 사용하세요. AI 에이전트가 프로덕션 포크에서 실행되어 결과가 좋아 보이고, 나중에 돌아오거나 프로모션할 수 있는 고정된 명명 체크포인트가 필요할 때: `rdc repo commit`으로 고정하고 `rdc repo branch`로 명명하세요. 위험한 마이그레이션 전에 작업 포크를 커밋하면 절대 변경되지 않는 정확한 롤백 지점을 확보할 수 있습니다(변경 불가능한 커밋은 마운트를 거부하므로 아무것도 쓸 수 없습니다). 두 체크포인트를 비교하려면 `rdc repo diff`가 copy-on-write 조상을 공유하기 때문에 어떤 두 커밋 사이에서도 작동합니다. 검토된 작업 라인을 대상 포크로 다시 가져오려면 `rdc repo merge`가 reflink 복제본에서 결과를 빌드하고 원자적으로 교체하므로 실행 중인 대상이 병합 중에 손상되지 않습니다.

`rdc repo fork`의 대체제로 사용하지 마세요. 일회용 복사본만 필요한 경우에는 일반 포크가 임시 테스트 격리의 올바른 단위입니다. 커밋은 상태를 보관하거나 명명하거나 배포할 가치가 있을 때 유용합니다.

## 커밋과 포크의 관계

리포지터리는 btrfs 풀에 있는 하나의 LUKS 이미지 파일입니다. 포크는 해당 이미지의 constant-time reflink이므로 1 GB 리포지터리와 100 GB 리포지터리를 포크하는 데 드는 비용이 같습니다. **커밋**은 변경 불가능으로 표시된 포크입니다. renet은 마운트를 거부하여 이미지를 영원히 바이트 안정 상태로 유지합니다. 이 바이트 안정성이 커밋을 신뢰할 수 있는 롤백 지점과 교차 머신 델타 푸시의 결정론적 기반으로 만듭니다.

`rdc repo commit`은 커밋 메시지, 작성자, 타임스탬프, 부모 커밋을 **볼륨 내부에** 기록하므로(이미지를 푸시할 때 메타데이터가 함께 이동) 볼륨 외부에도 미러링하여(`rdc repo log`가 잠금 해제 없이 이력을 탐색할 수 있도록) 저장합니다. 커밋한 작업 포크는 git이 커밋 후 작업 트리를 그대로 두는 것처럼 변경 없이 그대로 유지됩니다.

## 명령어

### rdc repo commit

마운트된 작업 포크를 새 변경 불가능한 커밋으로 고정합니다.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--name <name>` | 커밋할 작업 포크. 마운트되어 있어야 합니다. 필수. | 필수 |
| `--message <msg>` | 커밋 메시지. 필수. | 필수 |
| `--author <author>` | 커밋 메타데이터에 기록되는 커밋 작성자. | 미설정 |
| `-m, --machine <name>` | 대상 머신. 필수. | 필수 |
| `--debug` | stderr에 자세한 진단 출력. | 꺼짐 |

새 커밋은 `immutable: true`로 로컬 config에 등록되고, 작업 포크의 `headCommit`이 해당 커밋을 가리키도록 업데이트됩니다. 변경 불가능한 리포지터리를 커밋하는 것은 거부됩니다. 먼저 쓰기 가능한 포크로 체크아웃하세요.

### rdc repo branch

작업 포크의 현재 커밋을 가리키는 명명된 브랜치 참조를 생성합니다.

```bash
rdc repo branch --branch <name> --name <fork>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--branch <branch>` | 새 브랜치의 이름. 필수. | 필수 |
| `--name <name>` | 브랜치가 가리킬 현재 커밋을 가진 작업 포크. 필수. | 필수 |

이것은 config 전용 작업입니다. 머신에서는 아무 작업도 수행되지 않습니다. 브랜치 참조는 이름을 작업 포크의 `headCommit`에 매핑하므로, 포크에 먼저 커밋이 하나 이상 있어야 합니다.

### rdc repo checkout

변경 불가능한 커밋(또는 브랜치 팁)을 새 쓰기 가능한 작업 포크로 reflink 복제합니다.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--ref <commit\|branch>` | 체크아웃할 커밋 GUID, 또는 `--from`이 주어졌을 때 브랜치 이름. 필수. | 필수 |
| `--tag <name>` | 새 쓰기 가능한 작업 포크의 이름. 필수. | 필수 |
| `-m, --machine <name>` | 대상 머신. 필수. | 필수 |
| `--from <workingFork>` | 이 작업 포크의 브랜치 세트에서 `--ref`를 브랜치 이름으로 해석. | 직접 커밋 |
| `--debug` | stderr에 자세한 진단 출력. | 꺼짐 |
| `--skip-router-restart` | 라우터 재시작 단계를 건너뜀. | 꺼짐 |

체크아웃은 포크 reflink 경로를 재사용하므로 리포지터리 크기에 상관없이 거의 즉각적이고 constant-time입니다. 새 작업 포크의 `headCommit`은 체크아웃된 커밋으로 설정됩니다.

### rdc repo log

작업 포크 또는 커밋에서 도달 가능한 커밋 이력을 탐색합니다.

```bash
rdc repo log --name <fork> -m <machine>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--name <name>` | 이력 탐색을 시작할 작업 포크 또는 커밋. 필수. | 필수 |
| `-m, --machine <name>` | 대상 머신. 필수. | 필수 |
| `--json` | 커밋 이력을 JSON으로 출력. | 꺼짐 |
| `--debug` | stderr에 자세한 진단 출력. | 꺼짐 |

`log`는 `rdc repo commit`이 기록한 부모 체인을 탐색하며, 볼륨 외부 상태 미러를 읽으므로 커밋이 잠금 해제되거나 마운트되지 않습니다. 읽기 전용입니다.

### rdc repo merge

라이브 대상을 직접 변경하지 않고 소스 커밋 또는 포크를 대상 작업 포크에 병합합니다.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--name <name>` | 병합 대상 작업 포크. 필수. | 필수 |
| `--from <source>` | 병합 소스 커밋 또는 포크. 필수. | 필수 |
| `-m, --machine <name>` | 대상 머신. 필수. | 필수 |
| `--force` | 마운트되었거나 실행 중인 대상을 먼저 종료한 후 병합. 라이브 마운트는 절대 변경하지 않음. | 꺼짐 |
| `--resolve <ours\|theirs>` | 파일 수준 3방향 병합: 소스의 파일별 변경 사항을 대상에 적용하여, 양쪽에서 변경된 파일에 대해 소스 버전을 유지(`ours`)하거나 채택(`theirs`). 전체 이미지 take-theirs를 위해서는 생략. | 꺼짐 |
| `--base <guid>` | 3방향 병합의 공통 조상 커밋(`--resolve`와 함께 사용). 기본값은 소스 커밋의 부모 또는 대상의 현재 커밋. | 자동 |
| `--debug` | stderr에 자세한 진단 출력. | 꺼짐 |

결과는 reflink 복제본에서 빌드되고 충돌 안전 마커 뒤에 원자적으로 교체되므로 중단된 병합이 발생해도 원래 대상이 그대로 유지됩니다. 마운트되었거나 실행 중인 대상은 `--force`가 없으면 거부되며, `--force`는 교체 전에 대상을 깔끔하게 종료합니다.

`--resolve` 없이는 병합이 전체 이미지 take-theirs입니다(대상이 소스가 됨). `--resolve`를 사용하면 소스 커밋의 기록된 부모에 대한 파일 수준 3방향 병합입니다. 한쪽에서만 변경된 파일은 그쪽에서 가져오고, 양쪽에서 변경된 파일은 플래그에 따라 해결됩니다. 충돌 경로가 보고됩니다.

### rdc repo gc

머신에서 브랜치나 HEAD가 도달하지 않는 변경 불가능한 커밋 객체를 가비지 수집합니다.

```bash
rdc repo gc -m <machine>            # 드라이런 미리보기 (기본값)
rdc repo gc --apply -m <machine>    # 도달 불가능한 커밋 삭제
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-m, --machine <name>` | 수집할 머신. 필수. | 필수 |
| `--apply` | 도달 불가능한 커밋을 실제로 삭제 (그렇지 않으면 드라이런 미리보기). | 꺼짐 |
| `--debug` | stderr에 자세한 진단 출력. | 꺼짐 |

도달 가능성은 로컬 config(참조 저장소)에서 계산됩니다. 각 브랜치 팁과 HEAD를 부모 체인 아래로 따라가 도달 가능한 커밋 세트가 결정됩니다. 해당 세트 외부의 머신에 있는 변경 불가능한 커밋은 도달 불가능합니다. 마운트된 객체나 작업 포크는 절대 수집되지 않습니다.

### rdc repo fsck

머신에 있는 객체에 대해 config 참조를 검증합니다.

```bash
rdc repo fsck -m <machine>
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-m, --machine <name>` | 확인할 머신. 필수. | 필수 |

끊어진 참조(머신에 객체가 없는 GUID를 가리키는 브랜치 팁 또는 HEAD)와 고아 커밋(머신에 있지만 어떤 참조도 도달하지 않는 변경 불가능한 커밋)을 보고합니다. 읽기 전용입니다. `rdc repo gc --apply`로 고아를 회수하세요.

### 변경 불가능한 포크

`rdc repo fork --immutable`은 별도의 `commit` 단계 없이 생성 시 새 포크를 읽기 전용으로 표시하여 커밋 동등한 기반을 만듭니다.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

변경 불가능한 포크는 마운트를 거부하여 이미지를 영원히 바이트 안정 상태로 유지합니다. 이것은 베이스가 양쪽 끝에서 동일해야 하는 교차 머신 델타 푸시의 고정된 기반으로 유용합니다. 변경하려면 쓰기 가능한 복사본으로 체크아웃하거나 다시 포크하세요.

## 예시

### 작업 포크 커밋

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### 명시적 작성자로 커밋

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### 현재 커밋에 브랜치 이름 지정

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### 커밋을 새 쓰기 가능한 포크로 체크아웃

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### 이름으로 브랜치 팁 체크아웃

`--from`을 사용하면 `--ref` 값이 주어진 작업 포크의 브랜치 이름으로 해석됩니다:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### 이력 탐색

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### JSON으로 이력 보기

`--json`은 구조화된 탐색을 출력하며, 최신 항목이 먼저 나옵니다:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### 두 커밋 비교

`rdc repo diff`는 copy-on-write 조상을 공유하기 때문에 어떤 두 커밋 사이에서도 작동합니다. 커밋 하나를 체크아웃한 다음 다른 커밋과 비교하세요:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

전체 diff 참조는 [rdc repo diff](/ko/docs/repo-diff)를 참조하세요.

### 검토된 라인 병합

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### 실행 중인 대상에 병합

마운트되었거나 실행 중인 대상은 `--force`가 없으면 거부되며, `--force`는 먼저 종료합니다:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### 파일 수준 3방향 병합

동일한 커밋에서 체크아웃된 두 포크(`feature`와 `hotfix`)가 각각 일부 파일을 변경했습니다. `--resolve theirs`는 소스(`hotfix`)를 대상(`feature`)에 적용합니다. 한쪽에서만 변경된 파일은 그쪽에서 가져오고, 양쪽에서 변경된 파일은 소스로 해결됩니다. 베이스는 공유 조상에서 자동으로 감지됩니다(`--base`로 지정할 수도 있음):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml`은 양쪽에서 변경되어 소스로 해결되었습니다. `hotfix`만 추가한 파일은 적용되고, `feature`만 변경한 파일은 유지됩니다. 충돌 경로가 보고되므로 검토할 수 있습니다.

### 직접 변경 불가능한 기반 생성

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## 델타 푸시 및 풀

변경 불가능하고 바이트 안정적인 이미지는 **블록 수준 델타 전송**의 기반이기도 합니다. 두 머신에 동일한 변경 불가능한 기반이 있으면, 푸시 또는 풀이 전체 암호화 이미지를 스캔하는 대신 해당 기반에 대해 변경된 블록만 계산하여 이동할 수 있습니다. 몇 개의 변경된 블록이 있는 1 GB 리포지터리는 메가바이트 단위로 전송됩니다.

일반적으로 베이스를 직접 전달하지 않아도 됩니다. 전체 푸시 후 CLI는 푸시된 이미지를 양쪽 머신에 변경 불가능한 기반으로 유지하고 기록하므로, 해당 리포지터리의 **다음** 푸시는 플래그 없이도 이미 대상에 포크가 있더라도 자동으로 델타만 전송합니다. (기존 포크의 *전체* 재푸시는 여전히 `--force`가 필요합니다. 검증된 델타를 적용하는 것이 아니라 전체 이미지를 교체하는 것이기 때문입니다.) 특정 베이스를 고정하려면 `--delta-base <guid>`를 전달하고, 변경된 블록을 감지하는 방법을 제어하려면 `--strategy <auto|physical|shared>`를 사용하세요(`auto`가 거의 모든 경우에 올바릅니다).

```bash
# 첫 번째 푸시는 전체 전송입니다. 양쪽 끝에 재사용 가능한 기반을 유지합니다.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# 로컬 변경 후 다음 푸시는 플래그 없이 변경된 블록만 전송합니다.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# 명시적 베이스 지정 (양쪽 머신에 있는 변경 불가능한 커밋).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# 델타는 역방향으로도 작동합니다. 머신 소스에서 변경된 블록만 풀.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# 기존 로컬 리포지터리를 --force로 재풀 (덮어쓰기).
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

델타 전송은 머신 간(FIEMAP 기반이 있는 원격)에만 적용됩니다. 클라우드 객체 스토리지로의 푸시는 항상 전체 이미지를 전송합니다. 베이스는 양쪽 끝에서 바이트 동일해야 하며, 이것이 바로 변경 불가능한 커밋 또는 `--immutable` 포크가 보장하는 것입니다.

## JSON 스키마

`rdc repo log --json`은 renet 결과를 표준 봉투로 감쌉니다. 탐색된 이력은 `entries`에 있으며 최신 항목이 먼저 나옵니다:

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 탐색이 완료되었는지 여부. |
| `start` | string | 탐색을 시작한 GUID. |
| `entries` | array | 커밋당 하나의 객체, 최신 항목이 먼저. |
| `entries[].guid` | string | 커밋 GUID. |
| `entries[].message` | string | 커밋 메시지. 비어 있으면 생략. |
| `entries[].author` | string | 커밋 작성자. 비어 있으면 생략. |
| `entries[].parent` | string | 부모 커밋 GUID. 루트에서는 생략. |
| `entries[].committed_at` | string | RFC 3339 커밋 타임스탬프. 미설정 시 생략. |
| `entries[].immutable` | boolean | 커밋이 읽기 전용으로 표시되었는지 여부 (실제 커밋의 경우 항상 true). |

봉투 필드와 비TTY 환경에서 JSON을 출력하는 자동 감지 규칙은 [JSON 출력 참조](/ko/docs/ai-agents-json-output)를 참조하세요.

## 제한 사항

- **참조는 로컬입니다.** 브랜치 이름, `HEAD`, 참조 로그는 머신이 아닌 CLI config에 있습니다. 커밋을 다른 머신으로 푸시하면 커밋 객체와 볼륨 내 메타데이터가 전송되지만, 브랜치 참조는 config 측 개념입니다.
- **커밋은 마운트를 거부합니다.** 이것이 바로 그 목적입니다. 변경 불가능성이 커밋을 바이트 안정적으로 만드는 것입니다. 커밋을 실행하거나 편집하려면 먼저 쓰기 가능한 작업 포크로 체크아웃하세요.
- **병합 해결은 파일 수준이며 줄 수준이 아닙니다.** 전체 이미지 take-theirs(`--resolve` 없음)와 파일 수준 3방향(`--resolve ours|theirs`) 모두 지원됩니다. 3방향 병합은 플래그에 따라 파일 전체 단위로 충돌을 해결합니다. 파일 내 줄 수준 헝크나 병합 마커는 생성하지 않습니다.
- **이력은 부모 체인입니다.** `rdc repo log`는 커밋 시 기록된 단일 `parent` 링크를 탐색합니다. 쿼리된 머신에 메타데이터가 없는 커밋에 도달하면 중지됩니다.

## 참조

- [rdc repo diff](/ko/docs/repo-diff). 관련된 두 커밋 또는 포크 사이의 파일 수준 비교.
- [리포지터리](/ko/docs/repositories). 리포지터리 생성, 포크, 마운트, 운영.
