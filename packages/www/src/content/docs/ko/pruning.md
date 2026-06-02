---
title: "정리(Pruning)"
description: "고아 백업, 오래된 스냅샷, 리포지터리 이미지, 로컬 config 잔여물을 제거하여 디스크 공간을 확보하고 상태를 일관되게 유지합니다."
category: "Guides"
order: 12
language: ko
sourceHash: "98bb2d50d75a1d3d"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 정리(Pruning)

정리는 더 이상 실제 리소스에 해당하지 않는 상태를 스캔하여 제거합니다. 세 가지 명령이 세 가지 범위를 다룹니다.

| 명령 | 정리하는 항목 | 진실의 원천 위치 |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | 클라우드 스토리지의 고아 백업 | 로컬 CLI config (마운트 안전성을 위해 실행기 머신과 교차 확인) |
| `rdc machine prune --name <machine>` | 머신 내 데이터스토어 아티팩트 (항상 실행); 고아 또는 알 수 없는 리포지터리 이미지 (옵트인) | 로컬 CLI config + 머신의 `.interim/state` 미러 |
| `rdc config prune` | 로컬 config 잔여물 (인증서 캐시, 만료된 아카이브, 끊어진 상호 참조) | 로컬 CLI config만 |

세 가지는 독립적입니다. 다른 것 없이 어느 하나만 실행할 수 있습니다. 아래 [안전 모델](#안전-모델)에 설명된 공통 안전 모델을 공유합니다.

## 마운트 안전성 프리플라이트

`storage prune`과 `machine prune --prune-unknown`은 모두 삭제 전에 **마운트 안전성 프리플라이트**를 실행합니다: 실행기 머신에서 현재 마운트되거나 실행 중인 리포지터리를 쿼리하고, 삭제 후보와 교차하여 **머신에서 여전히 실행 중인 후보는 삭제를 거부합니다**. 마운트된 리포지터리의 오프머신 백업을 삭제하거나 실행 중인 리포지터리 이미지를 삭제하는 것은 실제 데이터 손실의 위험이 있습니다. 프리플라이트는 이것이 실수로 발생하는 것을 불가능하게 합니다.

재정의하려면(드문 경우; 실제 상태가 잘못되었다는 것을 확실히 아는 경우에만), `--force-delete-mounted`를 전달합니다. 이것은 `--force`(아카이브 유예 기간을 제어함)와 별개의 플래그이므로 두 이스케이프 해치가 구별됩니다.

## Storage Prune

스토리지 공급자를 스캔하고 GUID가 더 이상 로컬 config 파일에 나타나지 않는 백업을 삭제합니다.

```bash
# 미리 보기만 - 삭제될 항목 표시
rdc storage prune --name my-s3 -m server-1 --dry-run

# 실제로 고아 백업 삭제 (기본 동작)
rdc storage prune --name my-s3 -m server-1

# 유예 기간 재정의 (기본값 7일)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# 마운트 안전성 검사 재정의 (주의해서 사용)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine`은 rclone 호출이 노트북이 아닌 실행기 머신에서 실행되기 때문에 필요합니다. 클라이언트는 rclone을 로컬에 설치할 필요가 없습니다. 스토리지 자격 증명은 여전히 로컬 config에서 가져오며, 머신은 단지 rclone 실행기입니다.

### 확인 항목

1. 명명된 스토리지에서 모든 백업 GUID를 나열합니다 (`hot/` 및 `cold/` 하위 디렉터리 모두. [백업 및 복원](/ko/docs/backup-restore#scheduled-backups) 참조).
2. 디스크의 모든 config 파일(`~/.config/rediacc/*.json`)을 스캔합니다.
3. GUID가 어떤 config의 리포지터리 섹션에도 참조되지 않으면 백업은 **고아**입니다.
4. 유예 기간 내에 최근 아카이브된 리포지터리는 활성 config에서 제거되더라도 **보호됩니다**.
5. 마운트 안전성 프리플라이트: `--machine`에 현재 마운트된 GUID는 건너뛰고 보고되며, 절대 삭제되지 않습니다.

### 성능

삭제는 스토리지 하위 경로별로 일괄 처리됩니다: 제거되는 GUID 수에 관계없이 `hot/` 또는 `cold/` 디렉터리당 하나의 rclone 호출. 11개의 고아 백로그가 ~50초의 SSH 오버헤드에서 하위 경로당 단일 라운드 트립으로 축소됩니다.

## Machine Prune

세 단계로 머신 내 리소스를 정리합니다. 1단계는 항상 실행되며, 2단계와 3단계는 옵트인 방식으로 함께 사용할 수 있습니다.

### 1단계: 데이터스토어 정리 (항상 실행)

리포지터리가 삭제되거나 머신 수준 리팩터링이 명명 규칙을 폐기할 때 남을 수 있는 모든 종류의 리소스를 제거합니다. 각 범주는 독립적으로 스캔되고, 정리는 단일 멱등성 패스이므로 prune을 반복적으로 실행해도 안전하며 깨끗한 데이터스토어로 수렴됩니다.

| 범주 | 제거하는 항목 |
|---------|-----------------|
| 빈 마운트 디렉터리 | 지원하는 리포지터리 이미지가 없는 `mounts/<guid>/` 디렉터리 |
| 고아 immovable 디렉터리 | 지원하는 리포지터리 이미지가 없는 `immovable/<guid>/` 디렉터리 |
| 오래된 잠금 파일 | 삭제된 리포지터리에 대한 `repositories/.lock-<guid>` |
| 오래된 백업 스냅샷 | 종료된 백업 실행에 남겨진 `.snapshot-*` 및 `.backup-*` |
| 고아 VS Code 샌드박스 디렉터리 | 머신에서 더 이상 활성화되지 않은 리포지터리의 `.interim/sandbox/<name>` |
| 고아 iptables 체인 | 삭제된 네트워크에 대한 `REDIACC_WILDCARD_<N>` 및 `DOCKER_ISOLATED_NET_<N>` 체인 |
| 고아 authorized_keys 항목 | `--guid`가 더 이상 활성 마운트 디렉터리와 일치하지 않는 `sandbox-gateway <repo> --guid <uuid>` 줄 |

authorized_keys 스캔은 `/home/*/.ssh/authorized_keys`와 `/root/.ssh/authorized_keys`를 살펴봅니다. 항목은 `--guid` 태그가 실제 마운트 디렉터리 GUID에 매핑되는 경우에만 유지되므로, 현재 머신에 배포된 리포지터리는 이름이 디스크 어디에 나타나는지에 관계없이 항상 보존됩니다. renet이 `--guid` 태그 추가를 시작하기 전에 작성된 레거시 항목은 유효성을 검사할 수 없으며 항상 고아로 보고됩니다.

```bash
# 드라이런, 제거될 항목을 표시합니다 (변경 사항 적용 없음)
rdc machine prune --name server-1 --dry-run

# 정리 실행
rdc machine prune --name server-1
```

> **연쇄 정리.** 일부 범주는 이전 범주에 의존합니다. 예를 들어, 빈 마운트 디렉터리를 삭제하면 지원 마운트가 방금 사라진 추가 샌드박스 고아가 노출될 수 있습니다. `rdc machine prune`을 두 번째 실행하면 연쇄가 포착되고 정리가 완료됩니다. 아무것도 남지 않으면 최종 드라이런은 `No orphaned resources found. Datastore is clean.`으로 끝납니다.

### 2단계: `--orphaned-repos` (대략적)

`--orphaned-repos`를 사용하면, CLI는 **어떤** 로컬 config 파일에도 나타나지 않는 머신의 리포지터리 이미지도 삭제합니다.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

이것은 **대략적**입니다. 다른 도구나 다른 운영자의 CLI 체크아웃에서 관리하는 합법적인 포크를 포함하여 로컬 config에 없는 모든 것을 삭제합니다. renet `.interim/state` 미러가 리포지터리를 포크로 올바르게 식별하지만 로컬 config가 그것을 본 적이 없다면, 이 단계는 여전히 그것을 제거합니다. 보수적으로 처리하려면 3단계(`--prune-unknown`)를 선호합니다.

### 3단계: `--prune-unknown` (정밀)

`--prune-unknown`을 사용하면, CLI는 **두 가지** 신호가 모두 분류에 실패한 리포지터리만 삭제합니다: 어떤 로컬 config에도 없고 **그리고** 머신의 `.interim/state` 미러에 포크로 표시된 항목이 없는 것 ([리포지터리. `Type` 열](/ko/docs/repositories#type-column-and-the-state-mirror) 참조).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

실제로 `--prune-unknown`은 일상적인 정리에 필요한 것이며, `--orphaned-repos`는 로컬 config가 머신의 모든 리포지터리의 완전하고 권위 있는 목록임을 확신할 때만 올바릅니다. 미러 이전 레거시 고아와 실수로 config 항목이 삭제된 리포지터리 모두 "알 수 없는" 버킷에 속합니다. 이것들은 진정으로 불확실하며, 정밀 플래그는 운영자에게 이를 명시적으로 인정하도록 요청합니다.

마운트 안전성 프리플라이트는 이 단계에서도 실행됩니다: `--machine`에 현재 마운트된 리포지터리는 `--force-delete-mounted`를 전달하지 않는 한 보고되고 건너뜁니다.

```bash
# 결합: 정밀 포크 인식 경로를 사용한 전체 머신 정리
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

`~/.config/rediacc/<config>.json`의 **로컬 config 파일 내부** 오래된 잔여물을 스캔합니다. 순수 로컬. SSH 없음, renet 호출 없음. 세 가지 버킷이 정리됩니다.

1. 앵커(GUID, 리포지터리 이름, 또는 머신 이름)가 더 이상 활성 config에 없는 **ACME 인증서 캐시 항목**. 인증서 와일드카드는 어디로도 라우팅할 수 없으므로 데드 웨이트입니다.
2. `resources.deletedRepositories[]`의 **만료된 아카이브된 리포지터리**. `deletedAt`이 `defaults.pruneGraceDays` (기본값 7일)보다 오래된 항목. 유예 기간 내 항목은 (남은 일수와 함께) 보고되고 유지됩니다.
3. config 버킷 간 **끊어진 상호 참조**:
   - 더 이상 존재하지 않는 전략을 명명하는 `resources.machines.<m>.backupStrategies[]` 항목.
   - 더 이상 존재하지 않는 리포지터리를 명명하는 `resources.backupStrategies.<s>.exclude[]` 및 `include[]` 항목.
   - 대상 스토리지가 없는 스토리지 목적지. 경고로 표시되며, 자동 제거되지 않습니다 (자동 제거는 전략 의미를 변경할 것임).

```bash
# 미리 보기만
rdc config prune --dry-run

# 적용 (기본 동작)
rdc config prune

# 하나의 버킷으로 제한
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# 유예에 관계없이 모든 아카이브된 리포지터리 삭제
rdc config prune --purge-archived

# 이번 호출에 대한 아카이브 유예 기간 재정의
rdc config prune --grace-days 30
```

### 건드리지 않는 항목

- 활성 리소스 (머신, 스토리지, 리포지터리, 백업 전략, 클라우드 공급자).
- 자격 증명, 계정 블록, 암호화 블록, 기본값.
- 스토리지 `vaultContent` (만료된 OneDrive `access_token` 포함. refresh_token은 여전히 새 토큰을 발급합니다; pruning하면 재인증이 필요합니다).
- `knownHosts` 항목 (자동 갱신 경로는 `rdc config machine scan-keys`).
- 압축된 인증서 blob 배열 (`infra.acmeCertCache.<base>.data[]`)은 정리된 인증서 목록에서 자동으로 재구성됩니다; 여전히 유지된 이름을 다루는 체인은 잃지 않습니다.

### 작업 예시

4개의 고아 GUID 와일드카드와 2개의 오래된 머신 이름 와일드카드가 있는 머신의 실제 실행 출력:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

앵커가 실제 머신, 리포지터리 또는 GUID인 인증서 이름은 그대로 유지되며, 단일 레이블 `<service>.<base>` 또는 루트 `*.<base>` 와일드카드도 마찬가지입니다.

## 마이그레이션: 상태 미러 백필

`--prune-unknown`과 `rdc repo list -m`의 `Type` 열을 지원하는 `.interim/state/<guid>/.rediacc.json` 미러는 다음 경우에 작성됩니다.

- **포크 시** (`rdc repo fork`). 포크가 마운트되기 전이라도 즉시.
- **모든 상태 저장 시** (`rdc repo mount` 및 리포지터리 상태를 업데이트하는 모든 작업). 미러 코드가 배포되기 전에 생성된 리포지터리의 경우.

**미러가 존재하기 전에 생성되었고 업그레이드 이후 다시 마운트되지 않은** 리포지터리에는 미러 파일이 없습니다. 일부는 합법적인 포크임에도 불구하고 `rdc repo list -m`에서 `unknown`으로 표시됩니다. 레거시 고아에 대한 이 문제를 해결하려면, 머신에서 일회성 백필을 실행합니다.

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

백필은 현재 마운트된 리포지터리에 대해 실제 인볼륨 상태를 미러에 복사하고 `--mark-as-fork` 아래에 나열한 GUID에 대해 합성 포크 표시 미러를 작성합니다. 백필 후, 예약된 백업은 나열된 포크 업로드를 중지합니다 (업로드 파이프라인은 `is_fork: true`에 대한 미러를 확인함).

## 안전 모델

정리는 다중 config 설정에서 기본적으로 안전하게 설계되어 있습니다.

### 다중 config 인식

`storage prune`과 `machine prune --orphaned-repos`는 활성 config만이 아니라 `~/.config/rediacc/`의 **모든** config 파일을 스캔합니다. `production.json`에서 참조된 리포지터리는 `staging.json`에 없더라도 삭제되지 않습니다. 이를 통해 config가 다른 환경으로 범위가 지정되었을 때 우발적인 삭제를 방지합니다.

### 유예 기간

`--archive-config`로 config에서 리포지터리를 제거하면, 자격 증명 항목이 `deletedAt` 타임스탬프와 함께 `resources.deletedRepositories[]`로 이동됩니다. prune 명령은 최근 아카이브된 리포지터리가 삭제로부터 보호되는 유예 기간(기본값 7일)을 존중합니다. 이를 통해 실수로 제거된 리포지터리를 복원할 시간(`rdc config repository restore-archived --name <guid>`)을 제공합니다. 유예 기간이 만료되면 `storage prune`, `machine prune`, `config prune`이 모두 항목을 자동으로 제거합니다.

### 마운트 안전성 프리플라이트

위에서 설명되었습니다. `storage prune`과 `machine prune --prune-unknown`은 실행기 머신에서 현재 마운트되거나 실행 중인 리포지터리를 삭제하기를 거부합니다. `--force-delete-mounted`로만 재정의합니다.

### 기본적으로 적용; 미리 보기는 `--dry-run`

세 가지 prune 명령 모두 기본적으로 변경 사항을 **적용합니다**. 작성 없이 미리 보기를 위해 `--dry-run`을 전달합니다. 이것은 동사와 일치합니다: "prune"은 자체적으로 파괴적이며, 드라이런 플래그는 명시적인 옵트아웃입니다.

## 구성

### `pruneGraceDays`

매번 `--grace-days`를 전달할 필요가 없도록 config 파일에 사용자 정의 기본 유예 기간을 설정합니다.

```bash
# 활성 config에서 유예 기간을 14일로 설정
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

`--grace-days` CLI 플래그는 제공될 때 이 값을 재정의합니다.

### 우선순위

1. `--grace-days <N>` 플래그 (최고 우선순위)
2. config 파일의 `pruneGraceDays`
3. 기본 제공 기본값: 7일

## 모범 사례

- **프로덕션에서 먼저 드라이런을 실행합니다.** 특히 프로덕션 스토리지에서 파괴적인 prune을 실행하기 전에 항상 미리 봅니다.
- **여러 config를 최신 상태로 유지합니다.** 스토리지 및 머신 prune은 config 디렉터리의 모든 config를 확인합니다. config 파일이 오래되었거나 삭제되면 해당 리포지터리는 보호를 잃습니다. config 파일을 정확하게 유지합니다.
- **`--orphaned-repos` 대신 `--prune-unknown`을 선호합니다.** 정밀 플래그는 renet 미러를 존중합니다; 대략적인 플래그는 다른 도구가 생성한 포크를 기꺼이 삭제합니다.
- **프로덕션에는 넉넉한 유예 기간을 사용합니다.** 기본 7일 유예 기간은 대부분의 워크플로에 적합합니다. 유지 관리 기간이 드문 프로덕션 환경의 경우 14일 또는 30일을 고려합니다.
- **백업 실행 후 스토리지 prune을 예약합니다.** `storage prune`을 백업 일정과 함께 사용하여 수동 개입 없이 스토리지 비용을 관리합니다.
- **머신 prune을 백업 일정과 결합합니다.** 백업 일정을 배포한 후(`rdc machine backup schedule`), 오래된 스냅샷과 고아 데이터스토어 아티팩트를 정리하기 위해 주기적인 머신 prune을 추가합니다.
- **`config prune`을 주기적으로 실행합니다.** 로컬 config 팽창(특히 인증서 캐시)은 조용히 누적됩니다; 분기별 `config prune --dry-run`으로 충분히 확인할 수 있습니다.
- **`--force` 또는 `--force-delete-mounted` 사용 전에 감사합니다.** 두 플래그 모두 안전 검사를 우회합니다. 다른 config가 해당 리포지터리를 참조하지 않는다고 확신할 때만 `--force`를 사용합니다; 머신의 실제 상태가 잘못되었다고 확신할 때만 `--force-delete-mounted`를 사용합니다.
