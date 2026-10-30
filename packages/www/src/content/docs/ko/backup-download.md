---
title: "백업 다운로드"
description: "저장소의 암호화된 이미지를 로컬 디렉터리나 외장 드라이브에 복사하고, 이후 실행에서는 제자리에서 갱신합니다. 머신 없이 백업 스토어에서 곧바로 다시 구성할 수도 있습니다."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: ko
sourceHash: "c52e6a0471befc30"
---

# 백업 다운로드

`rdc backup download`는 저장소의 암호화된 이미지 사본을 로컬 디렉터리나 외장 드라이브에 보관합니다. 사본은 머신에 있는 것과 같은 암호문이므로 전송 중에는 아무것도 복호화되지 않습니다. 이미지를 여는 자격 증명은 구성에 남아 있으므로, 안전하게 보관하려면 [config storage](/ko/docs/config-storage) 등록이 적합합니다. 자격 증명이 없으면 이미지를 열 수 없습니다.

소스는 두 가지입니다. 기본값은 실행 중인 머신입니다. 다른 하나는 백업 스토어이며 `--store`로 선택합니다.

## 머신에서 다운로드

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to`에는 이미 존재하고 쓰기 가능한 디렉터리를 지정합니다. 디렉터리는 만들어지지 않으므로 드라이브를 먼저 마운트해야 합니다. 이미지는 `<machine>/<name>.<tag>.img`에 저장되고, 옆에 `.state.json` 파일이 생깁니다.

실행할 때마다 저장소의 새 스냅샷을 찍어 전송이 진행되는 동안에만 유지하고, 차이를 rsync로 보낸 뒤 결과물의 sha256을 머신의 스냅샷과 비교합니다.

| 플래그 | 효과 |
|------|--------|
| `--all -m <machine>` | 머신에 배치된 모든 grand 저장소를 복사 |
| `--include-forks` | `--all`과 함께 사용하면 포크도 복사 |
| `--bwlimit <rate>` | 네트워크 대역폭 제한(예: `100Mbps`, `12.5M`) |
| `--checkpoint` | 스냅샷 전에 저장소를 체크포인트하고 동결(핫 백업) |
| `--retries <n>` | 네트워크 장애 후 실행 내 재시도 횟수(기본값 3) |
| `--skip-verify` | sha256 비교를 건너뜀. rsync 자체 체크섬은 계속 실행됨 |
| `--skip-space-check` | 대상에 여유 공간이 부족할 수 있어도 거부하지 않고 경고만 표시 |

### 사본 갱신

두 번째 실행부터는 기존 이미지를 rsync 델타로 제자리에서 갱신합니다. 매주 실행해도 바뀐 부분만 전송되며, 대상에는 이미지 두 개가 아니라 한 개 분량의 공간만 있으면 됩니다. 실행을 시작하기 전에 여유 공간을 이미지 크기와 비교하며, `--skip-space-check`를 쓰면 거부가 경고로 바뀝니다.

### 중단된 실행과 재개

상태 파일에는 `status`가 기록됩니다. 첫 바이트를 쓰기 전부터 실행이 검증될 때까지는 `incomplete`이며, `incomplete` 이미지는 사용할 수 없습니다. Ctrl-C, 연결 끊김, 프로세스 강제 종료가 일어나면 이 상태로 남습니다. 같은 명령을 다시 실행하면 이어서 진행하며 차이만 전송됩니다. 상태가 `complete`가 되면 명령은 종료 코드 0으로 끝납니다.

### 요구 사항

전송에는 이 컴퓨터에 rsync 3.1.3 이상이 필요하며 SFTP 대체 경로는 없습니다. Linux 배포판에는 기본으로 포함되어 있습니다. macOS에서는 `brew install rsync`가 전송을 실행하지 못하는 기본 탑재 openrsync를 대체합니다. Windows에서는 rsync 패키지를 포함해 MSYS2를 설치하거나 데스크톱 앱을 사용합니다.

### 외장 드라이브

무엇이 들어가는지는 대상의 파일 시스템이 결정합니다.

- **FAT32**는 4 GiB를 넘는 파일을 담을 수 없으며, 명령은 실행을 거부합니다.
- 스파스 파일을 지원하지 않는 **exFAT**는 이미지를 겉보기 전체 크기로 저장하므로, 여유 공간 확인도 그 크기를 기준으로 계산합니다.
- 대상에 대해 로컬에서 찍은 **카피 온 라이트 스냅샷**(btrfs, ZFS, APFS)은 이미지의 이전 버전을 보존합니다. 그러면 제자리 갱신마다 기존 블록에 더해 변경된 블록만큼의 공간이 듭니다.

## 백업 스토어에서 다운로드

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store`는 머신을 거치지 않고 청크 스토어에서 곧바로 이미지를 다시 구성합니다. `REDIACC_TOKEN`의 토큰에는 `backup:read`와 `backup:restore` 스코프가 필요합니다. CLI 로그인에는 `backup:restore`가 포함되지 않으므로, 토큰은 포털의 API Tokens 페이지에서 만듭니다. 토큰은 팀에 속해야 하고, 현재 조직의 소유자 또는 관리자가 만든 것이어야 합니다.

`--store`는 저장소 이름을 정확히 하나만 받습니다. `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify`, `--skip-space-check`는 함께 쓸 수 없습니다. 스토어 가져오기에는 자체 재개 기능이 있고 모든 청크를 검증하기 때문입니다.

이미지는 `<dir>/<name>.<tag>.img`에 기록됩니다. 가져오기가 중단되면 일부만 받은 사본이 남고, 같은 명령으로 거기서부터 이어서 받습니다.

### `--at`으로 스냅샷 선택

기본적으로 가장 최근 스냅샷을 가져옵니다. `--at <time|snapshot>`으로 다른 스냅샷을 고를 수 있으며, ISO 8601 형식의 시각이나 스냅샷 ID를 지정합니다. `--store`와 함께 쓸 때만 적용됩니다.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Linux가 아닌 플랫폼에서는 가져온 이미지가 암호화된 상태여서 로컬에서 열 수 없습니다. `rdc backup upload`로 Linux 머신에 보냅니다.

## 사본을 다시 업로드

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload`는 다운로드한 이미지를 머신에 보내 새 저장소로 등록합니다. 전송은 중단 후에도 이어서 진행되며, 머신은 이미지를 배치하기 전에 sha256과 LUKS 헤더를 확인합니다. 자격 증명은 이미지 옆의 상태 파일에서 가져옵니다. 이 파일을 잃어버린 경우에는 `--from-repo <name>`으로 자격 증명을 제공할 저장소를 지정합니다.

| 플래그 | 효과 |
|------|--------|
| `--as <name>` | 새 저장소의 이름(기본값: 이미지의 이름) |
| `--datastore <name>` | 이름이 지정된 데이터스토어에 이미지를 배치 |
| `--from-repo <name>` | 상태 파일을 쓸 수 없을 때 자격 증명과 계보 정보를 제공 |
| `--bwlimit <rate>`, `--retries <n>` | 다운로드와 동일 |
| `--up` | 등록이 끝나면 저장소를 시작 |
| `--skip-verify` | 다운로드 때 기록된 sha256과의 비교를 건너뜀 |

## 오래된 전송 스냅샷

강제로 종료된 전송은 머신에 스냅샷을 남길 수 있습니다. `rdc machine status`는 풀 요약에서 오래된 전송 스냅샷의 개수를 보여 주고, `rdc machine prune <machine> --dry-run`은 그 목록을 보여 줍니다. `rdc machine prune <machine>`을 실행하면 삭제됩니다.

청크 스토리지로의 스냅샷은 [백업 및 복원](/ko/docs/backup-restore)을 참고하세요.
