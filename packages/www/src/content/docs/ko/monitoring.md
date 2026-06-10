---
title: "모니터링"
description: "머신 상태, 컨테이너, 서비스, 저장소를 모니터링하고 진단을 실행합니다."
category: "Guides"
order: 9
language: ko
sourceHash: "436c1c20b0ce8e35"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 모니터링

Rediacc는 머신 상태, 실행 중인 컨테이너, 서비스, 저장소 상태 및 시스템 진단을 검사하는 내장 모니터링 명령을 제공합니다.

## 머신 상태

머신에 대한 전체 상태 보고서를 가져옵니다.

```bash
rdc machine health --name server-1
```

다음을 보고합니다.
- **시스템**: 가동 시간, 디스크 사용량, 데이터스토어 사용량
- **컨테이너**: 실행 중, 정상, 비정상 수
- **스토리지**: SMART 상태
- **문제**: 식별된 문제

머신 가독성 출력을 위해 `--output json`을 사용하십시오.

## 컨테이너 목록

머신의 모든 저장소에서 실행 중인 컨테이너를 봅니다.

```bash
rdc machine containers --name server-1
```

| 열 | 설명 |
|--------|-------------|
| 이름 | 컨테이너 이름 |
| 상태 | 가동 시간 또는 종료 이유 |
| 상태값 | 실행 중, 종료됨 등 |
| 상태 확인 | 정상, 비정상, 없음 |
| CPU | CPU 사용률 |
| 메모리 | 메모리 사용량 / 제한 |
| 저장소 | 컨테이너를 소유하는 저장소 |

옵션:
- `--health-check`, 컨테이너에 대한 활성 상태 확인 수행
- `--output json`, 머신 가독성 JSON 출력

JSON 출력에는 전체 컨테이너 세부 정보(`labels`, `port_mappings`, `image`, `id`)와 `repository`(해석된 이름), `repository_guid`(원본 GUID), `domain` 및 `autoRoute`가 포함됩니다.

## 서비스 목록

머신에서 Rediacc와 관련된 systemd 서비스를 봅니다.

```bash
rdc machine services --name server-1
```

| 열 | 설명 |
|--------|-------------|
| 이름 | 서비스 이름 |
| 상태 | 활성, 비활성, 실패 |
| 하위 상태 | 실행 중, 종료됨 등 |
| 재시작 | 재시작 횟수 |
| 메모리 | 서비스 메모리 사용량 |
| 저장소 | 연결된 저장소 |

옵션:
- `--stability-check`, 불안정한 서비스 표시(실패, 3회 이상 재시작, 자동 재시작)
- `--output json`, 머신 가독성 JSON 출력

JSON 출력에는 `repository`(해석된 이름) 및 `repository_guid`(원본 GUID)가 포함된 전체 서비스 세부 정보가 포함됩니다.

## 저장소 목록

상세한 통계와 함께 머신의 저장소를 봅니다.

```bash
rdc machine repos --name server-1
```

| 열 | 설명 |
|--------|-------------|
| 이름 | 저장소 이름 |
| 크기 | 디스크 이미지 크기 |
| 마운트 | 마운트됨 또는 마운트 해제됨 |
| Docker | Docker 데몬 실행 중 또는 중지됨 |
| 컨테이너 | 컨테이너 수 |
| 디스크 사용량 | 저장소 내 실제 디스크 사용량 |
| 수정됨 | 마지막 수정 시간 |

옵션:
- `--search <text>`, 이름 또는 마운트 경로로 필터링
- `--output json`, 머신 가독성 JSON 출력

JSON 출력에는 `name`(해석된 이름)과 `guid`(원본 GUID)가 포함되며, 각 저장소의 `containers`(`domain`, `autoRoute`, `repository`/`repository_guid` 포함) 및 `services` 배열이 중첩됩니다.

## 스토리지 상태

머신의 모든 저장소에서 BTRFS 단편화 및 reflink 공유를 검사합니다.

```bash
rdc machine query --name server-1 --storage-health
```

| 열 | 설명 |
|--------|-------------|
| Quota | 리포지터리의 최대 크기(성장 상한. 생성 시 또는 resize/자동 확장으로 설정) |
| Allocated | 스파스 이미지가 현재 풀에서 실제로 점유하는 크기 |
| Unique | 이 리포지터리만 소유하는 실제 고유 데이터 |
| Shared | BTRFS reflink을 통해 리포지터리 간에 재사용되는 데이터 블록(무료 복사) |
| Reclaimable | [`repo trim`](/ko/docs/repositories#공간-회수-trim)으로 풀에 반환할 수 있는 할당 대 사용 격차. 마운트되지 않은 리포지터리는 `-`로 표시 |
| Discards | 암호화된 볼륨이 discard를 통과시키는지 여부(최신 버전으로 마운트된 리포지터리는 `on`) |
| Divergence | 공유되지 않고 이 리포지터리에만 고유한 이미지 비율(높을수록 삭제 시 더 많은 공간 회수 가능) |
| Frag | copy-on-write 이미지의 GB당 익스텐트 수(정보 제공용) |

Quota와 Allocated는 의도적으로 다른 숫자입니다. 20 GB 쿼터에 6 GB 데이터를 저장하는 리포지터리는 실제로 할당한 만큼만 풀에 비용을 발생시킵니다. 따라서 풀은 물리적 용량보다 더 많은 총 쿼터를 약속할 수 있으며, Reclaimable 열은 각 리포지터리 할당 중 더 이상 사용되지 않아 trim으로 회수할 수 있는 양을 보여줍니다.

테이블 아래에 풀 요약이 데이터스토어 채움 수준과 백업 스냅샷이 고정하고 있는 공간을 보고합니다.

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

백업이 실행되는 동안 해당 스냅샷은 라이브 리포지터리와 공유하는 모든 블록을 계속 참조하므로, 해당 백업 사이클이 완료되어 스냅샷이 삭제될 때까지 삭제와 trim으로 확보되는 풀 공간이 줄어듭니다. 중단된 백업의 오래된 스냅샷은 스토리지 관리자가 몇 분 내에 자동으로 제거합니다.

요약은 BTRFS reflink으로 인한 총 절감액을 보여줍니다.

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **가상 크기**는 모든 저장소 이미지 크기의 합입니다. 이것은 저장소가 보이는 모습이지만 reflink을 통해 공유된 블록을 이중으로 계산합니다.
- **고유 데이터**는 하나의 저장소에만 존재하는 저장소 데이터가 소비하는 실제 스토리지입니다. 이것이 저장소를 삭제하면 해제되는 용량입니다.
- **공유**는 BTRFS reflink을 통해 저장소 간에 재사용되는 데이터입니다. 저장소를 포크하면 reflink 복사본이 생성되어 어느 한쪽이 새 데이터를 쓸 때까지 블록을 공유하며, 그 시점에서 블록이 분기됩니다.
- **효율**은 reflink을 통해 재사용되는 데이터의 비율입니다. 높을수록 좋습니다. 동일한 부모에서 많은 포크가 있는 머신은 거의 100% 효율을 보입니다.

단편화(Frag) 열은 정보 제공용입니다. 애플리케이션이 내부에서 읽는 파일이 아닌 copy-on-write 이미지 파일의 익스텐트를 세므로, 일반적인 무작위 쓰기 워크로드(데이터베이스, 컨테이너 레이어)에서는 높게 표시되며 SSD 기반 스토리지의 읽기 성능을 예측하지 않습니다. Rediacc는 의도적으로 조각 모음 명령을 제공하지 않습니다. `btrfs filesystem defragment`는 reflink으로 연결된 포크와 스냅샷의 공유를 해제하는데, 거의 가득 찬 풀에서는 벤치마크상 측정 가능한 읽기 이득 없이 사용량을 극적으로 부풀릴 수 있습니다. 전체 측정 결과와 근거는 [단편화 수치가 무섭게 보입니다. 실제 비용을 직접 측정해봤습니다.](/ko/blog/i-benchmarked-btrfs-fragmentation)를 참조하세요.

스캔은 병렬로 실행되며 저장소의 수와 크기에 따라 5~15초가 걸립니다. `--storage-health`가 지정되지 않은 경우 쿼리 출력 후 한 줄의 힌트가 알림으로 표시됩니다.

## BTRFS 스크럽

Rediacc는 모든 머신에서 주간 BTRFS 스크럽을 자동으로 예약합니다. 스크럽은 데이터스토어의 모든 데이터 블록을 읽고, 체크섬을 검증하며, 손상을 보고합니다. 이는 조용한 데이터 손상(비트 부식)이 백업 및 포크로 전파되기 전에 감지합니다.

스크럽은 최대 1시간의 무작위 지연과 함께 매주 일요일 02:00 현지 시간(머신 시간대)에 실행됩니다. 실행 중인 서비스에 방해가 되지 않도록 최저 I/O 우선순위(`ionice idle`, `nice 19`)로 실행됩니다. SSD 기반 머신에서 데이터스토어 100GB당 약 8분이 소요됩니다.

스크럽 타이머는 renet 업그레이드 후 첫 번째 데몬 시작 시 자동으로 설치됩니다. 향후 renet 버전에서 스크럽 정책이 변경되면 다음 데몬 시작 시 사용자 조치 없이 자동으로 업데이트됩니다.

### 스크럽 상태

마지막 스크럽 결과는 BTRFS 볼륨 외부(`/var/lib/rediacc/scrub-last-result.json`)에 저장되므로 볼륨에 문제가 있어도 읽을 수 있습니다. `rdc machine query --system` 출력에는 `scrub_status` 필드가 포함됩니다.

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| 상태 | 의미 |
|--------|---------|
| `ok` | 마지막 스크럽이 오류 없이 완료됨 |
| `never_run` | 스크럽이 아직 실행되지 않음(타이머가 방금 설치됨) |
| `overdue` | 마지막 스크럽이 14일 이상 전 |
| `errors_found` | 스크럽이 체크섬 불일치를 발견함(`total_errors` 및 `uncorrectable` 수 확인) |
| `failed` | 스크럽 프로세스가 0이 아닌 코드로 종료됨 |

`uncorrectable`이 0보다 크면 영향을 받은 블록을 자동으로 복구할 수 없습니다(단일 디스크 BTRFS에는 중복 복사본이 없음). 가장 최근 백업에서 영향을 받은 저장소를 복원하십시오.

### 수동 스크럽

즉시 스크럽을 실행하려면(예: 전원 장애 또는 디스크 마이그레이션 후):

```bash
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

결과는 동일한 JSON 파일에 저장되며 다음 `rdc machine query --system`에서 즉시 확인할 수 있습니다.

## 볼트 상태

배포 정보를 포함한 머신의 완전한 개요를 가져옵니다.

```bash
rdc machine vault-status --name server-1
```

다음을 제공합니다.
- 호스트명 및 가동 시간
- 메모리, 디스크 및 데이터스토어 사용량
- 총 저장소 수, 마운트된 수, Docker 실행 수
- 저장소별 상세 정보

머신 가독성 출력을 위해 `--output json`을 사용하십시오.

## 연결 테스트

> **클라우드 어댑터 전용.** 로컬 어댑터에서는 `rdc term connect -m server-1 -c "hostname"`을 사용하여 연결을 확인하십시오.

머신에 대한 SSH 연결을 확인합니다.

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

보고 내용:
- 연결 상태(성공/실패)
- 사용된 인증 방법
- SSH 키 구성
- 공개 키 배포 상태
- known hosts 항목

옵션:
- `--port <number>`, SSH 포트(기본값: 22)
- `--save -m server-1`, 검증된 호스트 키를 머신 구성에 저장

## 진단(doctor)

Rediacc 환경의 전체 진단 검사를 실행합니다.

```bash
rdc doctor
```

| 카테고리 | 확인 항목 |
|----------|--------|
| **환경** | Node.js 버전, CLI 버전, SEA 모드, Go 설치, Docker 가용성 |
| **Renet** | 바이너리 위치, 버전, CRIU, rsync, SEA 내장 자산 |
| **구성** | 활성 구성, 어댑터, 머신, SSH 키 |
| **가상화** | 시스템이 로컬 가상 머신을 실행할 수 있는지 확인(`rdc ops`) |

각 확인 항목은 **OK**, **경고** 또는 **오류**를 보고합니다. 문제를 해결할 때 첫 번째 단계로 사용하십시오.

종료 코드: `0` = 모두 통과, `1` = 경고, `2` = 오류.

## 서비스 준비 상태 확인

`repo up` 중에 renet은 각 HTTP 서비스가 연결을 수락할 때까지 대기한 후 준비 완료를 선언합니다. 이 대기는 헬스체크를 인식합니다:

- Docker가 **healthy**로 보고하는 컨테이너는 즉시 신뢰됩니다. TCP 프로브를 수행하지 않습니다.
- 헬스체크의 `start_period` 중인 컨테이너는 경고가 아닌 정보성 메시지만 기록됩니다. 프록시는 바인딩될 때까지 재시도를 계속합니다.
- 실행 중인 컨테이너가 없는 Compose 서비스(예: 비활성 프로파일 뒤에 있는 서비스)는 건너뜁니다.
- 그 외 모든 서비스는 최대 15초 동안 TCP로 프로브됩니다(`REDIACC_READINESS_TIMEOUT`을 초 단위로 설정해 변경 가능).

부팅이 느린 서비스에 [Docker 헬스체크](https://docs.docker.com/reference/dockerfile/#healthcheck)를 정의하면 renet에 권위 있는 준비 신호를 제공하여 배포 출력에서 프로브 노이즈를 제거할 수 있습니다.
