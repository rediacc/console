---
title: 서비스
description: >-
  Rediaccfile, 서비스 네트워킹, autostart를 사용하여 컨테이너화된 서비스를 배포하고 관리하십시오.
category: Guides
order: 5
language: ko
sourceHash: "181ba0512ff98f9c"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 서비스

이 페이지에서는 컨테이너화된 서비스 배포 및 관리를 다룹니다. Rediaccfile, 서비스 네트워킹, 시작/중지, 일괄 작업, autostart가 포함됩니다.

## Rediaccfile

**Rediaccfile**은 서비스의 시작 및 중지 방법을 정의하는 Bash 스크립트입니다. 별도의 프로세스로 실행되는 것이 아니라 **소싱**되므로, 함수는 동일한 셸 컨텍스트를 공유하고 내보낸 모든 환경 변수에 접근할 수 있습니다. 이름은 `Rediaccfile` 또는 `rediaccfile`(대소문자 구분 없음)이어야 하며, 저장소의 마운트된 파일시스템 내에 배치해야 합니다.

Rediaccfile은 두 위치에서 검색됩니다.
1. 저장소 마운트 경로의 **루트**
2. 마운트 경로의 **첫 번째 레벨 하위 디렉터리** (재귀 없음)

숨겨진 디렉터리(`.`으로 시작하는 이름)는 건너뜁니다.

### 라이프사이클 함수

Rediaccfile에는 최대 두 개의 함수가 포함됩니다.

| 함수 | 실행 시점 | 목적 | 오류 동작 |
|------|---------|------|---------|
| `up()` | 시작 시 | 서비스 시작 (예: `renet compose -- up -d`) | 루트 실패는 **치명적** (모든 것 중지). 하위 디렉터리 실패는 **비치명적** (로그 후 계속) |
| `down()` | 중지 시 | 서비스 중지 (예: `renet compose -- down`) | **최선 노력** -- 실패가 로그되지만 모든 Rediaccfile이 항상 시도됨 |

두 함수 모두 선택 사항입니다. 함수가 정의되지 않으면 자동으로 건너뜁니다.

### 실행 순서

- **시작(`up`):** 루트 Rediaccfile 먼저, 그 다음 **알파벳 순서**(A에서 Z)로 하위 디렉터리.
- **중지(`down`):** **역 알파벳 순서**(Z에서 A)로 하위 디렉터리, 마지막으로 루트.

### 환경 변수

Rediaccfile 함수가 실행될 때 다음 환경 변수를 사용할 수 있습니다.

| 변수 | 설명 | 예시 |
|------|------|------|
| `REDIACC_WORKING_DIR` | 저장소의 마운트 경로 | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | 저장소 GUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | 네트워크 ID (정수) | `2816` |
| `DOCKER_HOST` | 이 저장소의 격리된 데몬을 위한 Docker 소켓 | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json`에 정의된 각 서비스의 루프백 IP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP` 변수는 `.rediacc.json`의 슬롯 매핑에서 자동 생성되고 Rediaccfile 함수가 실행되기 전에 내보내집니다. 명명 규칙은 서비스 이름을 대문자로 변환하고 하이픈을 밑줄로 교체한 후 `_IP`를 추가합니다. 예를 들어, 슬롯 `0`의 `listmonk-app`이라는 서비스는 `LISTMONK_APP_IP=127.0.11.2`가 됩니다.

> **경고: Rediaccfile에서 `sudo docker`를 사용하지 마십시오.** `sudo` 명령은 환경 변수를 초기화하므로 `DOCKER_HOST`가 손실되고 Docker 명령이 저장소의 격리된 데몬 대신 시스템 데몬을 대상으로 합니다. 이는 컨테이너 격리를 깨고 포트 충돌을 일으킬 수 있습니다. Rediacc는 `-E` 없이 `sudo docker`를 감지하면 실행을 차단합니다.
>
> Rediaccfile에서 `renet compose`를 사용하십시오. 이는 `DOCKER_HOST`를 자동으로 처리하고, 경로 검색을 위한 네트워킹 레이블을 주입하며, 서비스 네트워킹을 구성합니다. 서비스가 리버스 프록시를 통해 노출되는 방법은 [네트워킹](/en/docs/networking)을 참조하십시오. Docker를 직접 호출하는 경우 `sudo` 없이 `docker`를 사용하십시오. Rediaccfile 함수는 이미 충분한 권한으로 실행됩니다. sudo를 사용해야 한다면 `sudo -E docker`를 사용하여 환경 변수를 보존하십시오.
>
> `renet`은 원격 저수준 도구입니다. 워크스테이션에서의 일반 사용자 워크플로에는 `rdc repo up` 및 `rdc repo down` 같은 `rdc` 명령을 선호하십시오. [rdc vs renet](/en/docs/rdc-vs-renet)을 참조하십시오.

### 예시

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **중요:** `docker compose` 대신 항상 `renet compose --`를 사용하십시오. `renet compose` 래퍼는 renet-proxy에서 필요한 호스트 네트워킹, IP 할당, 서비스 검색 레이블을 적용합니다. CRIU 체크포인트/복원 기능은 `rediacc.checkpoint=true` 레이블이 있는 컨테이너에 추가됩니다. 직접 `docker compose` 사용은 Rediaccfile 유효성 검사에서 거부됩니다. 자세한 내용은 [네트워킹](/en/docs/networking)을 참조하십시오.

### 다중 서비스 레이아웃

여러 독립적인 서비스 그룹을 가진 프로젝트에는 하위 디렉터리를 사용하십시오.

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # 루트: 공유 설정
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # 데이터베이스 서비스
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API 서버
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana 등
    └── docker-compose.yml
```

`up` 실행 순서: 루트, 그 다음 `backend`, `database`, `monitoring` (A-Z).
`down` 실행 순서: `monitoring`, `database`, `backend`, 그 다음 루트 (Z-A).

## 서비스 네트워킹 (.rediacc.json)

각 저장소는 `127.x.x.x` 루프백 범위에서 /26 서브넷(64개 IP)을 받습니다. 서비스는 고유한 루프백 IP에 바인딩되어 충돌 없이 동일한 포트에서 실행할 수 있습니다.

### .rediacc.json 파일

서비스 이름을 **슬롯** 번호에 매핑합니다. 각 슬롯은 저장소 서브넷 내의 고유한 IP 주소에 해당합니다.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Docker Compose에서 자동 생성

`.rediacc.json`을 수동으로 생성할 필요가 없습니다. `rdc repo up`을 실행하면 Rediacc가 자동으로:

1. Rediaccfile을 포함하는 모든 디렉터리에서 compose 파일(`docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, 또는 `compose.yaml`)을 스캔
2. `services:` 섹션에서 서비스 이름 추출
3. 새 서비스에 다음 사용 가능한 슬롯 할당
4. 결과를 `{repository}/.rediacc.json`에 저장

### IP 계산

서비스의 IP는 저장소의 네트워크 ID와 서비스 슬롯에서 계산됩니다. 네트워크 ID는 `127.x.y.z` 루프백 주소의 두 번째, 세 번째, 네 번째 옥텟에 분배됩니다. 서비스는 오프셋 2에서 시작합니다.

| 오프셋 | 주소 | 목적 |
|--------|------|------|
| .0 | `127.0.11.0` | 네트워크 주소 (예약) |
| .1 | `127.0.11.1` | 게이트웨이 (예약) |
| .2 ~ .62 | `127.0.11.2` ~ `127.0.11.62` | 서비스 (`slot + 2`) |
| .63 | `127.0.11.63` | 브로드캐스트 (예약) |

네트워크 ID `2816` (`0x0B00`), 기본 주소 `127.0.11.0`의 **예시**:

| 서비스 | 슬롯 | IP 주소 |
|--------|------|---------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

각 저장소는 최대 **61개 서비스**(슬롯 0~60)를 지원합니다.

### Docker Compose에서 서비스 IP 사용

각 저장소는 격리된 Docker 데몬을 실행하므로, `renet compose`는 모든 서비스에 `network_mode: host`를 자동으로 구성합니다. 커널은 `bind()` 호출을 서비스에 할당된 루프백 IP로 투명하게 재작성하므로, 서비스는 충돌 없이 `0.0.0.0` 또는 `localhost`에 바인딩할 수 있습니다. **다른 서비스에 대한 연결**에는 **서비스 이름**을 사용하십시오. renet은 모든 서비스 이름을 fork에서도 항상 올바른 IP로 확인되는 호스트명으로 주입합니다.

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # 명시적인 listen_addresses 불필요 - 커널이 바인딩을 올바른 루프백 IP로 재작성

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # 서비스 이름 사용
      LISTEN_ADDR: 0.0.0.0:8080                                      # 커널이 서비스 IP로 재작성
```

> **연결에 서비스 이름 사용:** 다른 서비스에 **연결하려면** **서비스 이름**(예: `postgres`, `redis`)을 사용하십시오. renet이 모든 서비스 이름을 `/etc/hosts`를 통해 루프백 IP로 자동 매핑합니다. 데이터베이스나 설정 파일에 저장된 연결 문자열에 `${POSTGRES_IP}`를 포함하면 원시 IP가 고정되어 fork 격리가 깨지며 **유효성 검사 오류**가 됩니다. `${SERVICE_IP}` 변수는 명시적 사용을 위해 여전히 사용 가능하지만, 바인딩은 커널에 의해 자동으로 처리됩니다.

> **참고:** `network_mode: host`를 수동으로 추가하지 마십시오. `renet compose`가 자동으로 주입합니다. 재시작 정책(예: `restart: always`)은 안전하게 사용할 수 있습니다. renet이 CRIU 호환성을 위해 자동으로 제거하고 라우터 watchdog이 컨테이너 복구를 처리합니다.

### 컨테이너 복구 및 재시작 정책

renet과 Docker는 의도적으로 컨테이너 재시작 처리 방식이 다릅니다. 컨테이너가 복구되지 않은 이유를 디버깅할 때 이 차이를 이해하는 것이 중요합니다.

**재시작 정책 변환.** compose 파일에 `restart: always`(또는 `unless-stopped`, `on-failure`)를 작성하면, renet이 실제 compose 배포를 합성할 때 이를 **제거**하고 `restart: no`로 교체합니다. 원래 값은 `services.<name>.restart_policy` 아래 저장소의 `.rediacc.json`에 저장됩니다. 이는 Docker의 데몬 수준 자동 재시작이 CRIU 체크포인트/복원을 방해하는 것을 방지합니다 (데몬 구동 재시작은 오래된 체크포인트 이전 상태에서 재개됩니다).

**Watchdog 적용.** 라우터 watchdog은 모든 머신에서 주기적으로 실행됩니다. 매 틱마다:

1. 각 저장소의 `.rediacc.json`을 읽어 복구 가능한 `restart_policy`가 있는 서비스를 찾습니다.
2. 해당 저장소 데몬의 모든 컨테이너를 나열하고, 중지된 것을 식별하여 저장된 정책에 따라 재시작합니다. 30초 유예 기간으로 방금 `docker stop`을 실행한 운영자와의 충돌을 방지합니다.
3. 동일한 루프가 `/var/run/rediacc/cold-backup-<guid>.running.json`도 처리합니다([Cold Backup 시맨틱](backup-restore.md#cold-backup-semantics) 참조). 나열된 컨테이너는 저장된 정책에 관계없이 재시작됩니다. 사이드카는 "renet이 의도적으로 이것들을 중지했으며 운영자에게 재시작을 빚지고 있다"는 것을 의미하기 때문입니다.

**`on-failure`가 작동하지 않는 것처럼 보이는 이유.** Docker의 `on-failure` 정책은 컨테이너가 0이 아닌 코드로 종료될 때만 재시작합니다. `docker stop`이나 데몬 종료로 인한 정상 종료(exit 0)는 "실패"가 아니며 Docker의 기본 로직이나 watchdog의 저장된 정책 경로에 의해 재시작이 트리거되지 않습니다. cold-backup 사이드카가 안전망입니다. 의도적으로 중지한 컨테이너는 정책에 관계없이 재시작됩니다.

**런타임 상태 해석 방법:**

- `docker inspect <container>` → `RestartPolicy.Name`: renet 관리 컨테이너에 대해 항상 `no`입니다. 시맨틱 정책을 위해 이에 의존하지 마십시오.
- 저장소 마운트 루트의 `.rediacc.json` → `services.<name>.restart_policy`: 실제 의도.
- `docker ps --format '{{.Status}}'`: 런타임 상태.

**드리프트 수정 방법.** 컨테이너의 `.rediacc.json` 저장된 정책이 잘못된 경우(예: compose를 편집했지만 컨테이너를 재생성하지 않은 경우), `rdc repo up --name <repo> -m <machine>`을 다시 실행하십시오. 컨테이너가 업데이트된 정책으로 재생성됩니다.

> **실험적:** Cold-backup 사이드카 기반 복구와 `rdc machine query`의 `--sync-certs` 플래그는 renet 0.9+에 포함됩니다. 이전 버전은 watchdog 복구를 위해 저장된 `restart_policy`에만 의존하며, cold backup 후 `on-failure` 컨테이너가 중단될 수 있습니다.

> **Docker 브리지 네트워킹은 저장소별 데몬에서 비활성화됩니다.** 각 저장소별 데몬(`FlavorRediacc`)은 `"bridge": "none"`과 `"iptables": false`로 구성됩니다. 저장소 셸 내에서 일반 `docker run <image>`는 여전히 실행되지만, 컨테이너는 루프백 인터페이스만 받고 DNS나 아웃바운드 연결이 없습니다. 이는 설계상의 것입니다. 저장소 간 루프백 격리는 브리지 컨테이너가 우회할 수 있는 eBPF cgroup 훅에 의해 적용되기 때문입니다. 프로덕션 서비스는 `renet compose`를 사용해야 합니다 (호스트 네트워킹 자동 주입). 임시 디버깅에는 `--network host`를 명시적으로 전달하십시오: `docker run --rm --network host -it ubuntu bash`.
>
> 사용자별 Hub 데몬(`FlavorHub`, 개발 환경에서 사용)은 예외입니다. 이들은 `bridge="docker0"`, `iptables=true`, `live-restore=true`를 설정하여 사용자가 실행한 컨테이너가 일반 브리지 네트워킹과 아웃바운드 연결을 사용할 수 있도록 합니다.

> **참고:** Fork 저장소는 부모 서브도메인 아래에 자동 경로를 받습니다: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. 사용자 정의 도메인은 fork에 대해 건너뜁니다.

## 서비스 시작

저장소를 마운트하고 모든 서비스를 시작합니다.

```bash
rdc repo up --name my-app -m server-1
```

| 옵션 | 설명 |
|------|------|
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

실행 순서:
1. LUKS 암호화 저장소 마운트 (마운트되지 않은 경우 자동 마운트)
2. 격리된 Docker 데몬 시작
3. compose 파일에서 `.rediacc.json` 자동 생성
4. 모든 Rediaccfile에서 `up()` 실행 (A-Z 순서)

배포 후 출력에 각 서비스의 실제 URL이 포함된 **PROXY ROUTES** 섹션이 표시됩니다. 사용자 정의 Traefik 레이블(예: `traefik.http.routers.myapp.rule=Host(...)`)이 있는 서비스는 사용자 정의 도메인을 기본 URL로 표시합니다.

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

사용자 정의 Traefik 레이블이 없는 서비스는 자동 생성된 경로만 표시합니다. 브라우저 접근, API 호출, 서비스 간 설정에 이 URL(CLI가 출력하는 일반 패턴이 아님)을 사용하십시오.

## 서비스 중지

```bash
rdc repo down --name my-app -m server-1
```

| 옵션 | 설명 |
|------|------|
| `--unmount` | 중지 후 암호화된 저장소 언마운트. 이것이 적용되지 않으면 `rdc repo unmount`를 별도로 사용하십시오. |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

실행 순서:
1. 모든 Rediaccfile에서 `down()` 실행 (Z-A 역순, 최선 노력)
2. 격리된 Docker 데몬 중지 (`--unmount` 시)
3. LUKS 암호화 볼륨 언마운트 및 닫기 (`--unmount` 시)

## 일괄 작업

한 번에 머신의 모든 저장소를 시작하거나 중지합니다.

```bash
rdc repo up -m server-1
```

| 옵션 | 설명 |
|------|------|
| `--include-forks` | Fork된 저장소 포함 |
| `--mount-only` | 마운트만, 컨테이너 시작 안 함 |
| `--dry-run` | 수행될 작업 미리보기 |
| `--parallel` | 병렬로 작업 실행 |
| `--concurrency <n>` | 최대 동시 작업 수 (기본값: 3) |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

## 부팅 시 Autostart

기본적으로 저장소는 서버 재부팅 후 수동으로 마운트하고 시작해야 합니다. **Autostart**는 저장소가 서버 부팅 시 자동으로 마운트되고, Docker를 시작하고, Rediaccfile `up()`을 실행하도록 구성합니다.

### 작동 방식

저장소에 대해 autostart를 활성화하면:

1. 256바이트 무작위 LUKS 키파일이 생성되어 저장소의 LUKS 슬롯 1에 추가됩니다 (슬롯 0은 사용자 패스프레이즈로 유지)
2. 키파일은 `{datastore}/.credentials/keys/{guid}.key`에 `0600` 권한(루트 전용)으로 저장됩니다.
3. systemd 서비스(`rediacc-autostart`)가 부팅 시 실행되어 활성화된 모든 저장소를 마운트하고 서비스를 시작합니다.

종료 시 서비스는 모든 서비스(Rediaccfile `down()`)를 정상적으로 중지하고, Docker 데몬을 중지하며, LUKS 볼륨을 닫습니다.

> **보안 참고:** Autostart를 활성화하면 서버 디스크에 LUKS 키파일이 저장됩니다. 서버에 루트 접근 권한이 있는 누구나 패스프레이즈 없이 저장소를 마운트할 수 있습니다. 위협 모델에 따라 평가하십시오.

### 활성화

```bash
rdc repo autostart enable --name my-app -m server-1
```

저장소 패스프레이즈를 입력하라는 메시지가 표시됩니다.

### 모두 활성화

```bash
rdc repo autostart enable -m server-1
```

### 비활성화

```bash
rdc repo autostart disable --name my-app -m server-1
```

키파일이 제거되고 LUKS 슬롯 1이 삭제됩니다.

### 배포 시 키파일 새로 고침

Autostart가 활성화된 경우 `rdc repo up`은 LUKS 슬롯 1 키파일을 검증합니다.
디스크상의 키파일이 LUKS 슬롯과 일치하면 변경 사항이 없습니다.

`repo push` / `repo pull`로 저장소를 머신 간에 전송한 후,
새 머신의 키파일이 일치하지 않습니다. 이 경우 `repo up`이 자동으로
키파일을 재생성하고 LUKS 슬롯 1을 업데이트합니다. 다음과 같은 로그 메시지가 표시됩니다.

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

이것은 안전합니다. 슬롯 0(패스프레이즈)은 절대 수정되지 않습니다. Autostart가
활성화되지 않은 경우 확인은 자동으로 건너뜁니다. 실패는 치명적이지 않으며 배포를 차단하지 않습니다.

### 상태 목록

```bash
rdc repo autostart list -m server-1
```

부팅 후 중단된 레포지토리를 주기적 조정자가 복구하는 방법에 대한 자세한 내용은 [자동 시작 및 복구](/ko/docs/autostart-recovery)를 참조하세요.

## 완전한 예시

PostgreSQL, Redis, API 서버를 갖춘 웹 애플리케이션을 배포합니다.

### 1. 설정

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. 마운트 및 준비

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. 애플리케이션 파일 생성

저장소 내에서 다음을 생성하십시오.

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. 시작

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Autostart 활성화

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## compose에서 저장소별 시크릿 사용

위의 `POSTGRES_PASSWORD: changeme` 플레이스홀더는 튜토리얼에는 괜찮지만, 실제 앱에는 실제 자격 증명이 필요합니다. compose 파일(또는 저장소 내 `.env` 파일)에 커밋하면 fork도 이를 상속합니다. 배포 시 자격 증명에는 `rdc repo secret`을 사용하십시오. 값은 암호화된 저장소 이미지 외부에 저장되므로 fork는 빈 시크릿 맵으로 시작합니다.

두 가지 전달 모드가 compose에서 작동합니다.

**`env` 모드.** `environment:` 값에서 `${REDIACC_SECRET_<KEY>}`를 통해 보간합니다. renet 래퍼가 배포 시 컨테이너 환경에 값을 전달합니다.

**`file` 모드.** 값이 `/var/run/rediacc/secrets/<networkID>/<KEY>`의 호스트 측 tmpfs 파일에 저장되며, Docker compose의 표준 `secrets:` 블록을 통해 컨테이너에 마운트합니다. 컨테이너는 `/run/secrets/<key>`를 읽습니다. 민감한 것에는 이 모드를 선호하십시오. 값은 `docker inspect`나 `/proc/<pid>/environ`에 나타나지 않습니다.

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

`rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""`로 값을 설정하십시오. 전체 방법은 [저장소 § 시크릿](/en/docs/repositories#secrets)을 참조하고, 명령 참조는 치트 시트의 [저장소별 시크릿](/en/docs/rdc-cheat-sheet#per-repo-secrets)을 참조하십시오.

> **교차 저장소 경로는 유효성 검사 시 거부됩니다.** 다른 저장소의 `/var/run/rediacc/secrets/<other-networkID>/` 디렉터리를 가리키는 compose `secrets: file:`(또는 `configs: file:`, `env_file:`)은 docker compose가 실행되기 전에 renet 래퍼에 의해 강경히 거부됩니다. `--unsafe`는 이를 재정의하지 않습니다. 심층 방어: Rediaccfile 셸 주변의 Landlock 샌드박스는 읽기를 현재 네트워크의 시크릿 디렉터리로 범위를 제한하므로, Rediaccfile bash에서 `cat /var/run/rediacc/secrets/<other>/X`는 YAML 유효성 검사기를 우회하더라도 EACCES로 실패합니다. 별도로 활성화할 필요가 없습니다. 모든 `repo up`에 기본적으로 적용됩니다.
