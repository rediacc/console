---
title: "백업 및 복원"
description: "암호화된 레포지토리를 rclone 호환 스토리지에 백업하고, 모든 머신에서 복원하고, 명명된 백업 전략 및 systemd 타이머로 자동화합니다."
category: "Guides"
order: 7
language: ko
sourceHash: "6ed9a5b950de8ddb"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 백업 및 복원

Rediacc는 암호화된 레포지토리를 외부 스토리지 제공자에 백업하고 동일하거나 다른 머신에서 복원할 수 있습니다. 백업은 암호화되어 있으며, 복원 시 레포지토리의 LUKS 자격 증명이 필요합니다.

## 스토리지 설정

백업을 푸시하기 전에 스토리지 제공자를 등록하세요. Rediacc는 rclone 호환 스토리지라면 S3, B2, Google Drive 등 무엇이든 지원합니다.

### rclone에서 가져오기

이미 rclone 원격이 설정되어 있는 경우:

```bash
rdc config storage import --file rclone.conf
```

이 명령어는 rclone 설정 파일에서 현재 설정으로 스토리지 설정을 가져옵니다. 지원 형식: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob, Swift.

### 스토리지 목록 보기

```bash
rdc config storage list
```

## 백업 푸시

레포지토리 백업을 외부 스토리지에 푸시합니다.

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

푸시는 쓰기 전에 항상 대상 레포지토리가 마운트되어 있는지 확인합니다. 마운트되지 않은 경우 작업이 중단됩니다.

| 옵션 | 설명 |
|--------|-------------|
| `--to <storage>` | 대상 스토리지 위치 |
| `--to-machine <machine>` | 머신 간 백업을 위한 대상 머신 |
| `--dest <filename>` | 사용자 지정 대상 파일 이름 |
| `--checkpoint` | 푸시 전 CRIU 체크포인트 생성 (`rediacc.checkpoint=true` 레이블이 있는 컨테이너용). `repo up` 시 대상이 자동 복원 |
| `--force` | 기존 백업 덮어쓰기 |
| `--bwlimit <limit>` | rsync 전송 대역폭 제한 (예: `10M`, `500K`) |
| `--tag <tag>` | 백업에 태그 지정 |
| `-w, --watch` | 작업 진행 상황 모니터링 |
| `--debug` | 상세 출력 활성화 |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

## 백업 풀 / 복원

외부 스토리지에서 레포지토리 백업을 풀합니다.

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

풀은 쓰기 전에 항상 대상 레포지토리가 마운트되어 있는지 확인합니다. 마운트되지 않은 경우 작업이 중단됩니다.

| 옵션 | 설명 |
|--------|-------------|
| `--from <storage>` | 소스 스토리지 위치 |
| `--from-machine <machine>` | 머신 간 복원을 위한 소스 머신 |
| `--force` | 기존 로컬 백업 덮어쓰기 |
| `--bwlimit <limit>` | rsync 전송 대역폭 제한 (예: `10M`, `500K`) |
| `-w, --watch` | 작업 진행 상황 모니터링 |
| `--debug` | 상세 출력 활성화 |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

## 백업 목록 보기

스토리지 위치에서 사용 가능한 백업을 확인합니다.

```bash
rdc repo backup list --from my-storage -m server-1
```

출력은 [예약 백업 폴더](#scheduled-backups)(`hot/`과 `cold/`) 모두를 병합한 통합 테이블로, 모든 백업을 한 번에 볼 수 있습니다.

| 열 | 의미 |
|---|---|
| `Mode` | `hot` 또는 `cold`. 이 항목이 속한 예약 백업 폴더 |
| `Name` | 로컬 설정에서 확인된 레포지토리 이름 (설정에 없는 레포는 GUID로 대체) |
| `GUID` | 디스크상 레포지토리 GUID |
| `Size` | 백업 파일의 사람이 읽을 수 있는 크기 |
| `Modified` | 스토리지 백엔드의 UTC 타임스탬프 |

단일 모드를 조회하려면 `--path`를 전달하세요.

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

### 스토리지 레이아웃

예약 백업은 스토리지의 설정된 폴더 내 모드별 하위 폴더에 저장되므로, 동일한 스토리지가 시간별 및 주별 스트림을 섞지 않고 깔끔하게 호스팅합니다.

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

레포는 `hot/`과 `cold/` 모두에 나타날 수 있습니다(시간별 일정이 스냅샷을 찍고, 주별 일정이 다시 스냅샷을 찍음). 병합된 목록은 두 행 모두를 표시하여 어떤 스트림이 어떤 레포를 커버하는지 명확히 합니다.

## 일괄 동기화

모든 레포지토리를 한 번에 푸시하거나 풀합니다.

### 모든 레포를 스토리지에 푸시

```bash
rdc repo push --to my-storage -m server-1
```

### 스토리지에서 모두 풀

```bash
rdc repo pull --from my-storage -m server-1
```

| 옵션 | 설명 |
|--------|-------------|
| `--to <storage>` | 대상 스토리지 (푸시 방향) |
| `--from <storage>` | 소스 스토리지 (풀 방향) |
| `--repo <name>` | 특정 레포지토리만 동기화 (반복 사용 가능) |
| `--override` | 기존 백업 덮어쓰기 |
| `--debug` | 상세 출력 활성화 |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

## 예약 백업

Rediacc는 명명된 백업 전략을 사용합니다. 각 전략은 일정, 백업 모드, 선택적 대역폭 제한, 파일 필터를 정의합니다. 머신은 이름으로 전략을 참조하여 실행할 백업을 결정합니다.

### 백업 모드

| 모드 | 동작 | 다운타임 |
|------|----------|----------|
| `hot` | 서비스 실행 중 BTRFS 스냅샷 생성 (충돌 일관성) | 없음 |
| `cold` | 서비스 중지, 스냅샷 생성, 서비스 재시작, 스냅샷 업로드 (애플리케이션 일관성) | 레포별 중지+시작 창, 레포 간 병렬 처리. 아래 "콜드 백업 다운타임 추정"을 참조하세요. |

충돌 일관성 스냅샷을 허용하는 서비스에는 `hot`을 사용하세요. 보장된 일관성이 필요하고 짧은 재시작을 허용할 수 있는 경우 `cold`를 사용하세요.

### 콜드 백업 의미론

콜드 백업은 포함된 레포당 세 단계로 실행됩니다: **중지 → 스냅샷 → 시작**. 보장이 끝나는 지점을 이해하면 운영자가 부분 실패를 일찍 발견할 수 있습니다.

**콜드 백업이 보장하는 것:**

- 스냅샷 전에 포함된 각 레포의 실행 중인 모든 컨테이너는 Rediaccfile `down()` 훅을 통해 정상적으로 중지되고 레포별 Docker 데몬이 정지됩니다. 따라서 스냅샷은 단순한 충돌 일관성이 아닌 애플리케이션 일관성을 갖습니다.
- 스냅샷 전에 실행 중이던 컨테이너 ID 세트는 `/var/run/rediacc/cold-backup-<guid>.running.json`의 사이드카에 지속됩니다. 이것이 "완료 시 다시 실행되어야 할 것"의 진실 소스입니다.
- 스냅샷 후 레포의 Rediaccfile `up()` 훅이 호출되어 전체 compose 스택을 복원합니다.
- `/var/run/rediacc/cold-backup-<guid>.status.json`의 실행별 상태 사이드카는 각 시도의 단계, 결과, 오류를 기록합니다.

**콜드 백업이 보장하지 않는 것:**

- `up()`은 최선 노력입니다. 콜드 백업의 제어 범위 밖의 이유로 실패할 수 있습니다(`depends_on: service_healthy` 조건 대기 중, compose 파일 구문 오류, 이미지 풀 중 일시적 네트워크 실패). 실패 시 콜드 백업은 오류 수준에서 오류를 로그하고, 상태 사이드카를 기록하고, 다음 레포로 이동합니다.
- `up()`이 실패하면 **직접 재시작 폴백**이 작동합니다. 실행 사이드카를 읽고 기록된 각 컨테이너 ID를 직접 Docker API를 통해 재시작합니다(compose 없이). compose 흐름에 문제가 있어도 서비스가 복구되지만, Rediaccfile 훅은 다시 실행되지 않습니다.
- 일부 컨테이너 ID에 대해 폴백도 실패하는 경우(예: Docker 데몬 자체가 다운됨), 사이드카가 **그대로 유지**되어 라우터 왓치독이 각 틱마다 재시도할 수 있습니다.

**왓치독 복구:** 모든 틱마다 왓치독은 실행 사이드카를 확인합니다. 현재 중지된 컨테이너 ID가 나열된 경우 컨테이너의 저장된 `restart_policy`에 관계없이 재시작됩니다. 즉, `restart: on-failure`가 설정된 서비스(Docker가 깨끗한 중지 후 재시작하지 않을)도 콜드 백업 후 복구됩니다. 나열된 모든 컨테이너가 실행 중이 되면 사이드카가 삭제됩니다.

**운영자가 실패를 감지하는 방법:**

- `rdc machine query --name <machine> --containers`는 실행 상태를 표시합니다. 예상 세트와 비교하세요.
- 머신의 `/var/run/rediacc/cold-backup-<guid>.status.json`. `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`으로 검사하세요. 오래된 `startedAt`과 함께 `success: false`는 마지막 백업이 깔끔하게 완료되지 않았음을 의미합니다.
- renet 백업 실행 로그(`journalctl -u renet-*` 또는 직접 `rdc machine backup schedule` 호출)는 `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` 형식의 최종 요약 줄을 출력합니다. 비어 있지 않은 `failed_repos`가 grep 대상입니다.

### 콜드 백업 다운타임 추정

각 레포는 자체 `down()` + `up()` 창 동안만 다운됩니다. 워밍된 호스트에서 일반적으로:

| 레포 형태 | 일반적인 중지+시작 |
|------------|--------------------|
| 소형 (컨테이너 1-2개, DB 없음) | 5-15 s |
| 중형 (웹 앱 + 캐시) | 20-45 s |
| 대형 (DB + 큐 + 메일) | 60-120 s |

스냅샷 단계(`btrfs subvolume snapshot -r`)는 레포 크기에 관계없이 O(1)입니다: 0.1-1 s. 레포는 다른 레포의 스냅샷을 위해 계속 다운 상태에 있지 않습니다. 업로더는 모든 레포가 이미 복구된 후 읽기 전용 스냅샷에 대해 실행됩니다.

**전체 실행의 벽시계 시간**은 동시에 재시작하는 레포 수에 따라 결정됩니다. Renet은 호스트로부터 이를 도출합니다.

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

예시:

| 호스트 | 레포 | 동시성 | 벽시계 재시작 |
|------|-------|-------------|--------------------|
| 4 CPU VM | 5 레포, 평균 30 s | 2 | ~75 s |
| 16 CPU 서버 | 10 레포, 평균 40 s | 8 | ~80 s |
| 64 CPU 플릿 노드 | 50 레포, 평균 40 s | 8 | ~4 min |

**환경변수로 재정의:** 백업 서비스의 환경에 `REDIACC_COLD_BACKUP_CONCURRENCY=N`을 설정하여(systemd 드롭인이 일반적) 특정 값을 고정할 수 있습니다. `=1`은 엄격한 직렬 재시작을 강제하며, 한 레포의 `up()` 훅에서 크래시 루프를 디버깅할 때 유용합니다.

지연 민감한 레포(공개 웹 앱, 메일)를 실행하는 경우 다운타임은 전체 실행 시간이 아닌 자체 중지+시작(일반적으로 30-90 s)으로 제한됩니다. 레포는 발견된 순서대로 동시성 슬롯에 예약됩니다. 우선순위 큐는 없습니다. 더 세밀한 예약이 필요하면 대형 레포를 자체 `--exclude` 스코프 전략으로 분리하세요.

### 장기 실행 백업과 일정 겹침

자체 일정 간격보다 오래 걸리는 콜드 백업(예: 적당한 링크에서 500 GB 레포의 첫 시드는 24시간 이상 걸릴 수 있으며, 이 동안 야간 타이머가 다시 실행됨)은 두 번째 실행을 큐에 넣거나 시작하지 않습니다. systemd `Type=oneshot` 유닛은 단일 인스턴스입니다. 타이머가 실행되고 서비스가 이미 `activating` 상태인 경우 systemd는 시작을 기존 작업으로 병합합니다. 새 프로세스가 시작되지 않고, 나중에 실행을 위한 큐도 없습니다.

구체적으로, 월요일 03:00 UTC에 시작하여 목요일 정오에 완료되는 실행의 경우:

| 날 | 03:00 UTC 실행 | 결과 |
|------|---------------|--------|
| 월요일 | 첫 번째 실행 | 실행 시작 |
| 화요일 | 두 번째 실행 | 자동 삭제 (이전 실행이 여전히 활성) |
| 수요일 | 세 번째 실행 | 자동 삭제 (이전 실행이 여전히 활성) |
| 목요일 | 낮에 실행 종료 | 보충 없음; 다음 실행은 금요일 03:00 UTC |

타이머의 `Persistent=true` 지시어는 이러한 실행을 살리지 **않습니다**. `Persistent=true`는 타이머 자체가 비활성화되었기 때문에(시스템 꺼짐, 타이머 비활성화) 누락된 실행을 재생합니다. 서비스가 바빠서 삭제된 실행은 사라집니다.

이 기본값은 의도적입니다. 동일한 데이터스토어에 대해 두 콜드 백업을 병렬로 실행하면 BTRFS 스냅샷 경로, rclone 원격, `/var/run/rediacc/cold-backup-<guid>.status.json`의 레포별 사이드카에서 경합이 발생합니다. 장기 실행 인스턴스 뒤에서 직렬화하는 것이 안전한 결과입니다.

**모니터링 함의.** 중단된 백업(예: 네트워크 블랙홀에서 rclone이 멈춤)은 모든 후속 타이머 실행을 자동으로 삭제합니다. 스케줄러는 경보를 발생시키지 않습니다. `systemctl show <unit> -p ActiveEnterTimestamp`를 모니터링하세요. 서비스가 예상 실행 시간보다 오래(예: 야간 타이머에서 48시간 이상) `activating` 상태이면 조사하세요.

**예약된 모든 실행이 실행되어야 한다면** 타이머를 `OnCalendar=<cron>`에서 `OnUnitInactiveSec=<interval>`로 전환하세요. 이는 고정 벽시계 일정이 아닌 이전 실행 완료 후 N시간 후에 실행되므로 장기 실행이 삭제를 발생시키지 않습니다. 다음 실행을 나중으로 미룰 뿐입니다. 트레이드오프는 일정 드리프트입니다. 03:00 야간이 "마지막 종료 후 24시간"이 됩니다.

### 전략 정의

표준 기본값은 두 전략 분할입니다. 모든 레포를 캡처하는 빠른 시간별 hot 스트림과 애플리케이션 일관성 스냅샷을 찍는 느린 주별 cold 스트림입니다. 두 전략은 서로 다른 스토리지 하위 폴더(`hot/`과 `cold/`)에 쓰므로 백업이 절대 섞이지 않습니다.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

cold 전략의 `--exclude` 필터는 주별 유지 관리 창에 맞지 않는 매우 큰 레포를 위한 권장 탈출구입니다. 시간별 hot 전략이 여전히 이들을 커버합니다. cold는 단순히 건너뜁니다. `--exclude`의 레포지토리 이름은 로컬 설정 레포 이름과 일치합니다(`:tag` 없음).

| 옵션 | 설명 |
|--------|-------------|
| `--name <name>` | 전략 이름 (머신 바인딩에 사용) |
| `--destination <storage>` | 업로드할 스토리지 제공자 |
| `--cron <expression>` | Cron 표현식 (예: `"0 2 * * *"`는 매일 오전 2시) |
| `--mode <hot\|cold>` | 백업 모드 |
| `--bwlimit <limit>` | 업로드 대역폭 제한 (예: `10M`) |
| `--include <pattern>` | 포함 필터 (반복 사용 가능) |
| `--exclude <pattern>` | 제외 필터 (반복 사용 가능) |
| `--enable` / `--disable` | 전략 활성화 또는 비활성화 |

### 전략 보기

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### 전략 삭제

```bash
rdc config backup-strategy remove --name weekly-cold
```

### 머신에 전략 바인딩

설정에서 머신에 하나 이상의 전략 이름을 바인딩합니다.

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **바인딩은 로컬 구성 전용입니다.** 전략을 정의하고 머신에 바인딩해도 머신은 변경되지 않습니다. systemd 타이머를 배포하려면 `rdc machine backup schedule -m <machine>`을 실행하세요([머신에 일정 배포](#머신에-일정-배포) 참조). 전략이나 바인딩을 변경한 후에는 다시 실행해야 합니다.

## 핫 vs 콜드 선택 및 레포지토리별 필터링

### 핫 vs 콜드 한눈에 보기

| | 핫 | 콜드 |
|---|-----|------|
| **일관성** | 충돌 일관성 (실행 중 BTRFS 스냅샷) | 애플리케이션 일관성 (중지 → 스냅샷 → 시작) |
| **다운타임** | 없음 | 레포별 중지+시작 창 (일반적으로 5-120 s) |
| **적합한 빈도** | 높은 빈도 (예: 매시간) | 낮은 빈도 (예: 매일 또는 매주) |
| **일반적인 용도** | 자주 찍는 안전망 | 예약된 보장 일관성 백업 |

**핫**은 고빈도 실행의 올바른 기본값입니다. 스냅샷을 찍는 동안 서비스가 계속 실행되므로 백업 창이 사용자를 방해하지 않습니다. 스냅샷은 충돌 일관성을 갖습니다. 즉, 비정상 종료 후 얻을 수 있는 것과 동일합니다. 대부분의 최신 데이터베이스와 메시지 큐에서는 이것으로 충분합니다.

**콜드**는 보장된 애플리케이션 일관성 스냅샷이 필요하고 짧은 레포별 재시작을 허용할 수 있을 때 적합합니다. 스냅샷 전에 서비스가 중지되고 업로드가 시작되기 전에 재시작되므로, 느리거나 실패한 업로드가 다운타임 창을 연장하지 않습니다. 전체 보장 모델에 대해서는 [콜드 백업 의미론](#콜드-백업-의미론)을 참조하세요.

### 전략별 레포지토리 필터링

각 전략에 `--include` 및 `--exclude` 필터를 적용할 수 있습니다. `--exclude` 패턴과 일치하는 레포지토리 이름은 해당 전략에서 건너뜁니다. `--include`는 해당 이름으로만 실행을 제한합니다. 필터는 로컬 설정 레포지토리 이름(`:tag` 없음)과 일치합니다.

```bash
# 핫 전략: 매시간 모든 것 백업
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# 콜드 전략: 매주 모든 것 백업, 큰 파생 데이터셋 제외
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### 고빈도 핫 전략에서 레포지토리를 제외해야 하는 경우

다음 상황에서 고빈도 실행에서 레포지토리를 제외하세요:

- 레포가 크고 이미 볼륨에 있는 소스 데이터에서 **완전히 재생성 가능**해서, 매시간 백업이 의미 있는 복구 가치 없이 상당한 대역폭을 낭비하는 경우.
- 백업 실행이 사용 가능한 업로드 속도에서 자체 일정 간격을 초과하는 경우.

**예시.** `analytics-demo` 레포지토리에는 동일한 볼륨에 저장된 원시 CSV 덤프 파일에서 완전히 재구축할 수 있는 약 114 GB의 파생된 Postgres 테이블이 포함되어 있습니다. 6 MB/s 업로드 제한에서 해당 레포의 단일 핫 백업은 5시간 이상 걸립니다. 매시간 실행하면 다음 실행이 발생할 때 여전히 진행 중이어서 모든 후속 실행이 자동으로 삭제됩니다([장기 실행 백업과 일정 겹침](#장기-실행-백업과-일정-겹침) 참조). `hourly-hot`에서 제외하고 `weekly-cold`에 유지하면 전혀 백업되지 않는 대신 주 1회 백업됩니다.

> **데이터가 순수하게 재생성 가능한 경우**, 그것을 전혀 백업할 필요가 있는지 고려하세요. 대안으로 원시 소스 입력(이 예에서는 CSV 덤프)만 백업하고 파생 사본을 완전히 건너뛸 수 있습니다. 소스 입력의 주간 콜드 백업은 훨씬 작고 복구에 완전히 충분합니다.

두 전략에서 모두 제외되지 않은 레포는 `hot/`과 `cold/` 스토리지 서브폴더 모두에 나타납니다. 병합된 `rdc repo backup list` 출력은 두 행을 모두 표시하여 어떤 스트림이 어떤 레포를 커버하는지 확인할 수 있습니다.

## 백업 작업

### 머신에 일정 배포

바인딩된 전략을 systemd 타이머로 머신에 푸시합니다.

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

배포는 상태 조정자입니다. 머신의 현재 유닛 파일과 systemd 상태를 읽고, 설정이 생성할 내용과 비교하여(파일당 SHA-256), 실제로 변경된 유닛만 건드립니다. 설정 변경 없이 다시 실행하면 아무 작업도 없습니다. 쓰기 없음, `daemon-reload` 없음, 타이머 변경 없음.

`--dry-run`은 머신을 건드리지 않고 각 전략의 계획(`created`, `updated (service, timer, env)`, `unchanged`, `removed`)을 출력합니다. `--debug`와 결합하면 생성된 유닛 본문도 출력합니다. rclone 토큰은 리댁션됩니다.

업데이트하거나 제거하려는 전략에 대해 현재 백업이 실행 중이면 배포가 빠르게 실패하며 취소하거나 `--force`를 전달하라는 힌트가 표시됩니다. `--force`를 사용하면 실행 중인 호출은 인메모리 유닛을 유지하고 새 설정이 다음 타이머 틱에 적용됩니다. 따라서 실행 중인 백업이 절대 종료되지 않습니다.

`--reset-failed`는 선택 사항입니다. 전달 시 성공적인 배포 후 건드린 서비스의 systemd 실패 상태를 지웁니다. 이전 실패 신호가 경보에 계속 표시되도록 기본적으로 비활성화되어 있습니다.

### 지금 바로 백업 실행

타이머를 기다리지 않고 즉시 백업을 트리거합니다. 타이머가 배포되지 않은 경우에도 `systemd-run`을 사용한 임시 실행으로 작동합니다.

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### 백업 상태 보기

백업 타이머의 현재 상태와 최근 작업 결과를 표시합니다.

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### 실행 중인 백업 취소

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## 레포지토리 마이그레이션

한 머신에서 다른 머신으로 레포지토리를 이동합니다.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| 옵션 | 설명 |
|--------|-------------|
| `--name <repo>` | 마이그레이션할 레포지토리 |
| `--from <machine>` | 소스 머신 |
| `--to <machine>` | 대상 머신 |
| `--provision` | 전송 전 대상에 레포지토리 프로비저닝 |
| `--checkpoint` | 마이그레이션 전 CRIU 체크포인트 생성 |
| `--skip-dns` | 마이그레이션 후 DNS 레코드 업데이트 건너뜀 |
| `--bwlimit <limit>` | 전송 대역폭 제한 (예: `50M`) |

마이그레이션은 rsync를 통해 암호화된 레포지토리 데이터를 전송합니다. 소스 레포지토리는 명시적으로 삭제할 때까지 그대로 유지됩니다.

## 스토리지 탐색

스토리지 위치의 내용을 탐색합니다.

```bash
rdc storage browse --name my-storage
```

## 모범 사례

- 중요 데이터의 애플리케이션 일관성 스냅샷을 위해 일일 콜드 백업을 예약하세요.
- 다운타임이 없는 고빈도 스냅샷에는 hot 백업을 사용하세요.
- 백업 무결성을 주기적으로 복원 테스트로 검증하세요.
- 중요 데이터에는 여러 스토리지 제공자를 사용하세요 (예: S3 + B2).
- 자격 증명을 안전하게 보관하세요. 백업은 암호화되지만 복원에는 LUKS 자격 증명이 필요합니다.
