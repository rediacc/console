---
title: "rdc repo diff"
description: "COW(Copy-on-Write) 포크된 두 저장소 간의 git 스타일 파일 수준 diff를 보여줍니다. 암호화된 이미지를 블록 수준에서 비교하므로 복호화가 필요 없습니다."
category: Reference
subcategory: advanced
order: 40
language: ko
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff`는 포크와 부모 저장소, 또는 COW 조상을 공유하는 모든 두 저장소 간에 변경된 파일을 보고합니다. `--name <fork>`를 사용하면 포크를 로컬 설정에 기록된 부모 저장소와 비교하거나, `--base <repo>`를 추가하면 임의의 관련 저장소와 비교할 수 있습니다. 여기서 `--base`는 기본(구) 측이고 `--name`은 대상(신) 측입니다. 이 명령은 읽기 전용이며 이미지를 복호화하지 않습니다. 원격 머신의 블록 수준에서 이미지를 비교하므로 비용은 저장소 크기가 아닌 변경된 블록 수를 따릅니다. 동일한 편집이 있는 1GB 저장소와 100GB 저장소는 동일한 시간이 소요됩니다. 전체 저장소가 변경된 경우 블록 수가 크기에 따라 확장되므로 비용도 마찬가지입니다.

## 사용 시기

포크를 반영하기 전에 `repo diff`를 사용합니다. AI 에이전트가 프로덕션 포크에서 실수로 실행되었고 변경사항을 병합하기 전에 정확히 어떤 파일이 변경되었는지 확인하고 싶을 때: `repo diff --name <fork> -m <machine>`으로 몇 초 만에 파일 목록을 얻을 수 있습니다. 재해 복구 후 복원된 포크를 원본 스냅샷과 비교하여 예상된 파일들이 모두 복구되었는지 확인하세요. 몇 주 동안 부모 저장소와 함께 실행 중인 장기간 포크의 경우, diff는 누적된 변경사항(설정 편집, 로그 증가, 스키마 마이그레이션)을 보여주므로 두 트리를 직접 마운트하고 확인할 필요가 없습니다.

관련 없는 저장소 간에는 사용하지 마세요. 두 측이 COW 조상을 공유해야 비교가 공유된 블록 히스토리에서 작동합니다. 또한 이것은 바이너리 diff 도구가 아닙니다. `--content`는 텍스트 파일에 대해서만 라인 수준의 출력을 제공하며, 바이너리는 `Binary files differ`로 보고됩니다.

## 명령 참조

### 개요

```bash
rdc repo diff --name <fork> -m <machine>            # fork를 부모 저장소와 비교
rdc repo diff --name <fork> --base <repo> -m <machine>   # 임의의 관련 저장소와 비교
```

### 옵션

| 옵션 | 설명 | 기본값 |
|--------|-------------|---------|
| `--name <name>` | 검사할 저장소(대상, 신 측). 필수. | 필수 |
| `--base <name>` | 비교할 저장소(기본, 구 측). `--name`의 부모로 기본값 설정. | `--name`의 부모 |
| (형식 플래그 없음) | 이름-상태 출력: 변경된 파일당 색상 `A`/`M`/`D`/`R` 문자 및 한 줄 요약. | 켜짐 |
| `--name-only` | 한 줄에 한 개의 변경된 경로, 상태 문자 없음. 파이프 친화적. | 꺼짐 |
| `--stat` | 파일당 변경 크기(바이트 및 블록 델타) 및 합계 바닥글. | 꺼짐 |
| `--content <path>` | 단일 파일의 통합 텍스트 diff. 텍스트만; 바이너리는 `Binary files differ` 보고. | 꺼짐 |
| `--json` | 에이전트 및 스크립트를 위한 구조화된 출력. | 꺼짐 |
| `--fast` | 컨텐츠-해시 확인 단계를 건너뛰고 블록 필터를 신뢰합니다. 더 빠르지만 Modified로 파일을 과다 보고할 수 있습니다. | 꺼짐 |
| `-m, --machine <name>` | 대상 머신. 필수. | 필수 |
| `--debug` | stderr의 상세한 진단. | 꺼짐 |
| `--skip-router-restart` | 라우터 재시작 단계 건너뜀. | 꺼짐 |

## 예제

### 부모에 대한 기본 이름-상태

`--name`만 사용하면 fork가 로컬 설정에 기록된 부모와 비교됩니다. 여기서 fork `test-1gb:fork1`은 하나의 수정된 파일을 가지고 있습니다:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### 명시적 기본에 대해 비교

`--base`를 사용하여 임의의 관련 저장소와 비교합니다. `--base`는 기본(구) 측이고 `--name`은 대상(신) 측입니다:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### `--stat`으로 변경 크기

`--stat`은 파일당 바이트 델타 및 블록 델타와 합계 바닥글을 추가합니다:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### 경로만, 도구로 파이프됨

`--name-only`는 상태 문자 없이 한 줄에 하나의 경로를 인쇄하므로 다른 명령에 공급할 수 있습니다:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### 한 파일의 라인 수준 diff

`--content`는 단일 텍스트 파일의 통합 diff를 생성합니다:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### jq로 JSON 필터링

`--json`은 stdout의 구조화된 봉투를 내보내므로 `jq`로 깔끔하게 파이프됩니다:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## 출력 형식

### 이름-상태(기본)

각 변경된 파일은 상태 문자와 경로를 표시합니다. `A`는 추가됨, `M`은 수정됨, `D`는 삭제됨, `R`은 이름 변경됨(이전 경로 표시)입니다. 요약 줄은 각 카테고리의 개수를 뒤따릅니다.

### `--name-only`

한 줄에 한 개의 경로, 상태 문자 없음, 요약 없음. 다운스트림 명령이 깔끔한 파일 목록을 원할 때 사용합니다.

### `--stat`

각 줄은 파일의 바이트 델타와 블록 델타를 나타냅니다. 바닥글은 전체 파일 개수와 터치된 총 바이트를 보고합니다. 이것은 단순히 어떤 파일이 변경되었는지가 아니라 변경의 무게가 어디에 있는지를 보여줍니다.

### `--content <path>`

표준 통합 diff(`---`/`+++` 헤더, `@@` 청크)로 한 텍스트 파일. 바이너리 파일은 `Binary files differ`를 보고하고 청크를 생성하지 않습니다.

### `--json`

전체 구조화된 결과. 데이터는 stdout으로 이동하고 진행 상황 및 진단은 stderr로 이동하므로 JSON은 진행 상황이 인쇄되는 동안에도 `jq` 또는 다른 파서로 깔끔하게 파이프됩니다.

## JSON 스키마

CLI는 renet 결과를 표준 봉투(`success`, `command`, `data`, `errors`, `warnings`, `metrics`)에 래핑합니다. diff 결과는 snake_case 필드가 있는 `data`에 있습니다:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

`entries[]`의 각 객체는 변경된 경로 하나를 설명합니다:

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | 추가됨, 수정됨, 삭제됨 또는 이름 변경됨. |
| `path` | string | 대상 측의 경로(삭제 시 기본 측). |
| `old_path` | string | 이전 경로. 이름 변경 시만 있습니다. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | 항목 종류. |
| `old_size` | number | 기본 측의 바이트 크기. |
| `size` | number | 대상 측의 바이트 크기. |
| `bytes_changed` | number | 다른 바이트, 전체 블록으로 반올림됨. |
| `blocks_changed` | number | 변경된 블록 수. |
| `inode` | number | 이름 변경 감지에 사용되는 inode 번호. |
| `content_changed` | boolean | 파일 컨텐츠(메타데이터만 아님)가 변경되었는지 여부. |
| `mode_changed` | boolean | 파일 모드가 변경되었는지 여부. 참일 때 `old_mode`/`new_mode` 제시. |
| `uid_changed` | boolean | 소유자가 변경되었는지 여부. 참일 때 `old_uid`/`new_uid` 제시. |
| `gid_changed` | boolean | 그룹이 변경되었는지 여부. 참일 때 `old_gid`/`new_gid` 제시. |
| `old_target` / `new_target` | string | 심볼릭 링크 대상. 변경된 심볼릭 링크에 대해 제시됨. |

봉투 필드 및 TTY가 아닌 환경에서 JSON을 내보내는 자동 감지 규칙은 [JSON Output Reference](/ko/docs/ai-agents-json-output)를 참조하세요.

## 작동 원리

저장소는 btrfs 풀의 LUKS2 이미지 파일이고 fork는 해당 이미지의 상수 시간 reflink입니다. `repo diff`는 FIEMAP을 통해 블록 수준에서 두 암호화 이미지를 비교하여 파일시스템 메타데이터만 읽고 아무것도 복호화하지 않습니다. 변경된 암호문 오프셋을 LUKS 데이터 오프셋으로 이동하여 ext4-장치 오프셋을 가져온 다음, 각 파일의 ext4 범위 맵을 통해 해당 오프셋을 파일 이름으로 다시 매핑합니다. 두 마운트의 최종 inode-identity 워크는 결과를 Added, Modified, Deleted 및 Renamed 항목으로 조정합니다. 작업이 변경된 블록 수로 제한되기 때문에 diff는 저장소 크기와 무관하며, 라이브 마운트를 제자리에서 재사용하기 때문에 실행 중인 저장소를 방해하지 않습니다. 전체 메커니즘은 [암호화된 디스크 이미지용 Git diff](/ko/blog/git-diff-for-encrypted-disk-images)에 설명되어 있습니다.

## 제한 사항

- **관련 fork만 가능합니다.** 양쪽이 COW 조상을 공유해야 합니다. 관련 없는 저장소 간에는 의미 있는 블록 수준 비교가 없습니다.
- **이름 변경 감지는 inode 기반입니다.** 파일은 동일한 inode가 새 경로에 나타날 때 이름 변경됨으로 보고됩니다. 삭제 후 재생성(새 inode)은 이름 변경이 아니라 Deleted 및 Added 항목으로 표시됩니다.
- **`--content`는 텍스트만 가능합니다.** 텍스트 파일에 대해 라인 수준 청크를 생성합니다. 바이너리는 `Binary files differ`로 보고합니다.
- **`--fast`는 Modified를 과다 보고할 수 있습니다.** 블록 필터를 신뢰하고 컨텐츠-해시 확인을 건너뛰므로 블록이 컨텐츠를 변경하지 않고 이동한 파일이 Modified로 표시될 수 있습니다.
- **범위-워크 시간은 크기가 아닌 단편화에 따라 확장됩니다.** 심하게 단편화된 파일시스템은 더 많은 범위를 매핑하여 변경의 바이트 양이 작아도 워크를 늘립니다.

## 참조

- [rdc repo fork](/ko/docs/repositories). 이 명령이 비교하는 COW fork를 생성합니다.
- [rdc repo status](/ko/docs/repositories). 단일 저장소의 현재 상태.
- [rdc repo cat](/ko/docs/repositories). 저장소에서 단일 파일 읽기.
