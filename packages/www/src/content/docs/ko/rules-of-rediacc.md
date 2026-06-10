---
title: "Rediacc 규칙"
description: "Rediacc 플랫폼에서 애플리케이션을 구축하기 위한 필수 규칙과 규약. Rediaccfile, compose, 네트워킹, 스토리지, CRIU 및 배포를 다룹니다."
category: "Guides"
order: 5
language: ko
sourceHash: "4b6899adea7f0712"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Rediacc 규칙

모든 Rediacc 저장소는 자체 Docker 데몬, 암호화된 LUKS 볼륨, 전용 IP 범위를 갖춘 격리된 환경에서 실행됩니다. 이 규칙들은 애플리케이션이 이 아키텍처 내에서 올바르게 작동하도록 보장합니다.

## Rediaccfile

- **모든 저장소에는 Rediaccfile이 필요합니다.** Rediaccfile은 라이프사이클 함수를 포함하는 bash 스크립트입니다.
- **라이프사이클 함수**: `up()`, `down()`. 선택 사항: `info()`.
- `up()`은 서비스를 시작하고, `down()`은 서비스를 중지합니다.
- `info()`는 상태 정보(컨테이너 상태, 최근 로그, 헬스)를 제공합니다.
- Rediaccfile은 renet에 의해 소싱되므로 환경 변수뿐만 아니라 셸 변수에도 접근할 수 있습니다.

### Rediaccfile에서 사용 가능한 환경 변수

| 변수 | 예시 | 설명 |
|------|------|------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | 마운트된 저장소의 루트 경로 |
| `REDIACC_NETWORK_ID` | `6336` | 네트워크 격리 식별자 |
| `REDIACC_REPOSITORY` | `abc123-...` | 저장소 GUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | 서비스별 루프백 IP (서비스 이름 대문자) |

### 최소 Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **`renet compose`를 사용하고, `docker compose`는 절대 사용하지 마십시오.** renet은 네트워크 격리, 호스트 네트워킹, 루프백 IP, 서비스 레이블을 주입합니다.
- **compose 파일에 `network_mode`를 설정하지 마십시오.** renet이 모든 서비스에 `network_mode: host`를 강제합니다. 설정한 값은 덮어써집니다.
- **`rediacc.*` 레이블을 설정하지 마십시오.** renet이 `rediacc.network_id`, `rediacc.service_ip`, `rediacc.service_name`을 자동으로 주입합니다.
- **`ports:` 매핑은 호스트 네트워킹 모드에서 무시됩니다.** HTTP 라우팅을 위해 `rediacc.service_port` 레이블을 추가하십시오 (이 레이블이 없는 서비스는 HTTP 경로를 받지 못합니다). TCP/UDP 포워딩에는 `rediacc.tcp_ports`/`rediacc.udp_ports` 레이블을 사용하십시오.
- **재시작 정책(`restart: always`, `on-failure` 등)은 안전하게 사용할 수 있습니다.** renet이 CRIU 호환성을 위해 자동으로 제거합니다. 라우터 watchdog은 `.rediacc.json`에 저장된 원래 정책을 기반으로 중지된 컨테이너를 자동으로 복구합니다.
- **위험한 설정은 기본적으로 차단됩니다.** `privileged: true`, `pid: host`, `ipc: host`, 시스템 경로에 대한 호스트 바인드 마운트는 거부됩니다. 직접 책임 하에 재정의하려면 `renet compose --unsafe`를 사용하십시오.

### 컨테이너 내부 환경 변수

Renet이 모든 컨테이너에 자동으로 주입합니다.

| 변수 | 설명 |
|------|------|
| `SERVICE_IP` | 이 컨테이너의 전용 루프백 IP |
| `REDIACC_NETWORK_ID` | 네트워크 격리 ID |

### 서비스 이름 및 라우팅

- compose **서비스 이름**이 자동 경로 URL 접두사가 됩니다.
- **Grand 저장소**: `https://{service}.{repo}.{machine}.{baseDomain}` (예: `https://myapp.marketing.server-1.example.com`).
- **Fork 저장소**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (예: `https://myapp-fork-staging.marketing.server-1.example.com`). `-fork-` 구분자는 grand 저장소 서비스 이름과의 URL 충돌을 방지합니다. fork URL은 항상 부모 저장소의 기존 와일드카드 인증서를 사용하므로 새 인증서가 필요하지 않습니다.
- 사용자 정의 도메인에는 Traefik 레이블을 사용하십시오 (단, 사용자 정의 도메인은 fork에 적합하지 않습니다. 도메인은 grand 저장소에 속합니다).

## 네트워킹

- **각 저장소는 `/var/run/rediacc/docker-<networkId>.sock`에 자체 Docker 데몬을 갖습니다.**
- **각 서비스는 /26 서브넷 내에서 고유한 루프백 IP를 받습니다** (예: `127.0.24.192/26`).
- **바인딩은 자동입니다.** 서비스는 `0.0.0.0` 또는 `localhost`에 바인딩할 수 있으며, 커널이 주소를 서비스에 할당된 루프백 IP로 투명하게 재작성합니다. 명시적인 `${SERVICE_IP}` 바인딩은 여전히 작동하지만 더 이상 필수가 아닙니다.
- **헬스 체크는 `localhost` 또는 `${SERVICE_IP}`를 사용할 수 있습니다.** 예: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **저장소 간 연결은 커널에 의해 차단됩니다.** 커널은 저장소의 `/26` 서브넷 외부의 루프백 IP에 대한 연결을 자동으로 차단합니다. 한 저장소의 서비스는 다른 저장소의 서비스에 접근할 수 없습니다.
- **서비스 간 통신**: **서비스 이름**을 사용하십시오 (예: `db`, `redis`). renet은 모든 서비스 이름을 올바른 IP로 확인되는 호스트명으로 자동 주입합니다. Docker DNS 이름은 호스트 모드에서 작동하지 않지만, `/etc/hosts`를 통한 서비스 이름은 작동합니다. 영구 설정 파일(예: 데이터베이스에 저장된 연결 문자열)에 `${DB_IP}` 같은 원시 IP를 포함하는 것을 피하십시오. fork 시 해당 IP가 유지되어 잘못된 저장소를 가리킵니다. 서비스 이름은 항상 저장소별로 올바르게 확인됩니다.
- **저장소 간 포트 충돌은 불가능합니다.** 각 저장소는 자체 Docker 데몬과 IP 범위를 갖습니다.
- **TCP/UDP 포트 포워딩**: 비HTTP 포트를 노출하려면 레이블을 추가하십시오.
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## 스토리지

- **모든 Docker 데이터는 암호화된 저장소 내에 저장됩니다.** Docker의 `data-root`는 LUKS 볼륨 내 `{mount}/.rediacc/docker/data`에 있습니다. 명명된 볼륨, 이미지, 컨테이너 레이어는 모두 암호화되고, 백업되며, 자동으로 fork됩니다.
- **`${REDIACC_WORKING_DIR}/...`에 대한 바인드 마운트가 명확성을 위해 권장됩니다.** 명명된 볼륨도 안전하게 작동합니다.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # 바인드 마운트 (권장)
    - pgdata:/var/lib/postgresql/data      # 명명된 볼륨 (안전)
  ```
- LUKS 볼륨은 `/mnt/rediacc/mounts/<guid>/`에 마운트됩니다.
- BTRFS 스냅샷은 모든 바인드 마운트된 데이터를 포함한 전체 LUKS 백업 파일을 캡처합니다.
- 데이터스토어는 시스템 디스크의 고정 크기 BTRFS 풀 파일입니다. `rdc machine query --name <name> --system`으로 유효 여유 공간을 확인하십시오. `rdc datastore resize`로 확장하십시오.

## CRIU (라이브 마이그레이션)

- **레이블로 활성화**: 체크포인트하려는 컨테이너에 `rediacc.checkpoint=true`를 추가하십시오. 이 레이블이 없는 컨테이너(데이터베이스, 캐시)는 새로 시작하여 자체 메커니즘(WAL, LDF, AOF)으로 복구합니다.
- **`repo down --checkpoint`**는 중지 전에 프로세스 상태를 저장하며, 다음 `repo up` 시 자동으로 복원합니다. **이것이 동일 머신에서의 기본 흐름**으로, 작동이 검증되었습니다.
- **`backup push --checkpoint`**는 레이블이 있는 컨테이너의 실행 중인 프로세스 메모리와 디스크 상태를 캡처한 후 볼륨을 다른 머신으로 전송합니다. 대상 머신에서 `repo up`으로 복원합니다.
- **`repo fork --checkpoint`**는 실행 중인 부모에서 프로세스 상태를 캡처하고 체크포인트를 포크와 함께 CoW 복제합니다. 포크의 `repo up`은 부모가 같은 머신에서 계속 실행되는 동안 프로세스를 복원합니다. 부모의 루프백 주소를 참조하는 복원된 프로세스(바인딩된 소켓, 메모리의 서비스 IP)는 포크 자신의 주소로 투명하게 리디렉션되므로, 항상 포크의 데이터 사본과 통신하며 부모의 데이터에는 절대 접근하지 않습니다.
- **`repo up`**은 체크포인트 데이터를 자동 감지하고 발견 시 복원합니다. 강제로 새로 시작하려면 `--skip-checkpoint`를 사용하십시오.
- **의존성 인식 복원**: compose `depends_on`을 사용하여 먼저 데이터베이스를 시작(정상 상태까지 대기)한 후 앱 컨테이너를 CRIU 복원합니다.
- **복원 후 TCP 연결이 오래되므로** 앱은 `ECONNRESET`을 처리하고 재연결해야 합니다. CRIU는 지원되는 어떤 흐름에서도 복원 후 활성 TCP 연결 상태를 보존하지 않습니다.
- **Docker 실험 모드**는 저장소별 데몬에서 자동으로 활성화됩니다.
- **CRIU는** `rdc config machine setup` 중에 **설치됩니다.**
- **`/etc/criu/runc.conf`**는 기본적으로 `tcp-established`로 구성됩니다.
- **레이블이 있는 컨테이너에 대해 컨테이너 보안 설정이 자동으로 주입됩니다.** `renet compose`는 `rediacc.checkpoint=true`인 컨테이너에 다음을 추가합니다.
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (커널 5.9 이상에서 CRIU를 위한 최소 집합)
  - `security_opt`: `apparmor=unconfined` (CRIU의 AppArmor 지원이 업스트림에서 아직 안정적이지 않음)
  - `userns_mode: host` (CRIU는 `/proc/pid/map_files`를 위해 init 네임스페이스 접근이 필요)
- 레이블이 없는 컨테이너는 더 깔끔한 보안 자세로 실행됩니다 (추가 권한 없음).
- Docker의 기본 seccomp 프로파일이 유지되며, CRIU는 체크포인트/복원 중 필터를 일시적으로 중단하기 위해 `PTRACE_O_SUSPEND_SECCOMP`(커널 4.3 이상)를 사용합니다.
- **compose 파일에 CRIU 권한을 수동으로 설정하지 마십시오.** renet이 레이블에 따라 처리합니다.
- CRIU 호환 참조 구현은 [heartbeat 템플릿](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat)을 참조하십시오.

### CRIU 호환 애플리케이션 패턴

- 모든 영구 연결(데이터베이스 풀, 웹소켓, 메시지 큐)에서 `ECONNRESET`을 처리하십시오.
- 자동 재연결을 지원하는 연결 풀 라이브러리를 사용하십시오.
- 내부 라이브러리 객체의 오래된 소켓 오류를 위해 `process.on("uncaughtException")` 안전망을 추가하십시오.
- 재시작 정책은 renet에 의해 자동으로 관리됩니다 (CRIU를 위해 제거되며, watchdog이 복구를 처리합니다).
- Docker DNS에 의존하지 마십시오. 서비스 간 통신에는 루프백 IP를 사용하십시오.

### OS별 호스트 보안 정책

공식 지원되는 5개 서버 OS([요구 사항](/en/docs/requirements) 참조) 전체에서, 저장소별 docker 데몬과 그것이 실행하는 컨테이너는 **기본 컨테이너 레이블**을 사용합니다. `rdc config machine setup`은 사용자 정의 SELinux 정책이나 AppArmor 프로파일을 설치하지 않습니다.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor가 기본적으로 활성화됩니다. 컨테이너는 기본 docker-container 프로파일에서 실행됩니다. 유일한 예외는 CRIU입니다 (`rediacc.checkpoint=true` 컨테이너에 대해 `apparmor=unconfined`, 위 참조).
- **Fedora 43 / Oracle Linux 10**: SELinux가 기본적으로 enforcing 모드로 실행됩니다. 컨테이너는 표준 `container_t` 컨텍스트를 받습니다. 추가 정책 설치가 필요하지 않습니다. 설정 단계에서 AVC 거부가 발생하면 [문제 해결 → SELinux 거부](/en/docs/troubleshooting)를 참조하십시오.
- **Debian 13**: AppArmor를 사용할 수 있지만 기본적으로 모든 도메인에서 enforcing되지는 않습니다. 컨테이너는 여전히 docker-container 프로파일을 사용합니다.

OS별 보안 자세 플래그가 필요하지 않습니다. `rdc`와 `renet`은 실행 중인 항목을 감지하고 5개 배포판 모두에서 동일한 저장소별 격리를 제공합니다.

## 보안

- **LUKS 암호화**는 표준 저장소에 필수입니다. 각 저장소는 자체 암호화 키를 갖습니다.
- **자격 증명은 CLI 설정에 저장됩니다** (`~/.config/rediacc/rediacc.json`). 설정을 잃으면 암호화된 볼륨에 대한 접근을 잃습니다.
- **버전 관리에 자격 증명을 커밋하지 마십시오.** `env_file`을 사용하고 `up()`에서 시크릿을 생성하십시오.
- **저장소 격리**: 각 저장소의 Docker 데몬, 네트워크, 스토리지는 동일 머신의 다른 저장소와 완전히 격리됩니다.
- **에이전트 격리**: AI 에이전트는 기본적으로 fork 전용 모드로 작동합니다. 각 저장소는 서버 측 샌드박스 적용(`sandbox-gateway` ForceCommand)이 있는 자체 SSH 키를 갖습니다. 모든 연결은 Landlock LSM, OverlayFS 홈 오버레이, 저장소별 TMPDIR로 샌드박스화됩니다. 저장소 간 파일시스템 접근은 커널에 의해 차단됩니다.
- **`sudo`는 저장소 샌드박스 내에서 설계상 비활성화됩니다.** Landlock 파일시스템 격리는 `NoNewPrivs`가 필요하며, 이는 모든 권한 상승을 방지합니다. 따라서 `sudo`는 `no new privileges flag is set`으로 실패합니다. 저장소 소유자 사용자는 이미 저장소의 마운트와 Docker 소켓 내의 모든 것에 필요한 권한을 갖고 있습니다. 진정한 권한 작업(호스트 패키지 설치, 커널 튜닝)은 샌드박스 외부에서 또는 인프라 경로에 의해 실행되는 Rediaccfile `up()` 함수에서 수행하십시오.
- **Docker 브리지 네트워킹은 저장소별 데몬에서 비활성화됩니다.** 각 저장소의 `daemon.json`(`FlavorRediacc`)에는 `"bridge": "none"`과 `"iptables": false`가 있어, 일반 `docker run <image>`는 루프백 인터페이스만 있고 아웃바운드 연결이 없는 컨테이너를 생성합니다. 이것은 버그가 아니라 저장소 간 격리가 적용되는 방식입니다. 한 저장소가 다른 저장소의 루프백 IP에 도달하는 것을 차단하는 커널 수준 eBPF 훅은 호스트 네트워크 네임스페이스에 있는 컨테이너에만 적용됩니다. 프로덕션 서비스에는 `renet compose`를 사용하십시오 (`network_mode: host`를 자동으로 주입). 셸에서 임시 컨테이너를 사용하려면 `--network host`를 명시적으로 전달하십시오. (사용자별 Hub 데몬(`FlavorHub`, 개발 환경)은 예외로, `bridge="docker0"`과 `iptables=true`를 활성화하여 사용자가 실행하는 컨테이너가 정상적인 아웃바운드 네트워크 연결을 사용할 수 있습니다.)

## 배포

- **`rdc repo up`**은 LUKS 볼륨이 마운트되지 않은 경우 자동으로 마운트한 후, 모든 Rediaccfile에서 `up()`을 실행합니다.
- **`rdc repo down`**은 `down()`을 실행하고 Docker 데몬을 중지합니다.
- **`rdc repo down --unmount`**는 LUKS 볼륨도 닫습니다 (암호화된 스토리지를 잠금).
- **Fork** (`rdc repo fork`)는 **저장소 크기에 관계없이 일정한 시간에** 새 GUID와 networkId를 가진 CoW(copy-on-write) 클론을 생성합니다. BTRFS reflink는 데이터가 아닌 이미지 메타데이터를 복제하므로 100 GB 저장소도 1 GB 저장소와 동일한 몇 초 안에 fork됩니다. fork는 부모의 암호화 키를 공유합니다.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`)는 grand 저장소의 데이터를 fork의 데이터로 교체합니다. grand는 자신의 정체성(GUID, networkId, 도메인, autostart, 백업 체인)을 유지합니다. 기존 프로덕션 데이터는 백업 fork로 보존됩니다. 사용 방법: fork에서 업그레이드 테스트, 검증, 프로덕션으로 takeover. `rdc repo takeover --name <backup-fork> -m <machine>`으로 되돌릴 수 있습니다.
- **프록시 경로**는 배포 후 활성화되는 데 약 3초가 걸립니다. `repo up` 중 "Proxy is not running" 경고는 ops/dev 환경에서 정보용입니다.
- **`rdc repo up` 및 `rdc repo fork --up`은 배포 끝에 `rediacc.service_port`로 레이블된 서비스의 URL 패턴을 출력합니다.** `{service}`를 노출된 서비스 이름으로 교체하여 정확한 URL을 얻으십시오. `rediacc.service_port`가 없는 서비스(데이터베이스, 워커)는 경로를 받지 않으며 표시되지 않습니다.

## 일반적인 실수

- `renet compose` 대신 `docker compose` 사용: 컨테이너가 네트워크 격리를 받지 못합니다.
- 재시작 정책은 안전합니다. renet이 자동으로 제거하고 watchdog이 복구를 처리합니다.
- `privileged: true` 사용: 필요하지 않습니다. renet이 대신 특정 CRIU 권한을 주입합니다.
- 영구 설정 파일에 원시 IP 하드코딩: fork 격리를 유지하기 위해 연결에 서비스 이름을 사용하십시오.
- 실패한 명령의 해결 방법으로 `rdc term connect -c` 사용: 대신 버그를 보고하십시오.
- `repo delete`는 루프백 IP와 systemd 유닛을 포함한 전체 정리를 수행합니다. 이전 삭제의 잔재를 정리하려면 `rdc machine prune --name <name>`을 실행하십시오.
