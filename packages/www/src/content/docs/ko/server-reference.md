---
title: "서버 레퍼런스"
description: "원격 서버의 디렉터리 구조, renet 명령, systemd 서비스 및 워크플로."
category: "Concepts"
order: 3
language: ko
sourceHash: "4fb53bb4cb1512f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 서버 레퍼런스

Rediacc 서버에 SSH로 접속하면 다음을 접하게 됩니다: 디렉터리 구조, `renet` 명령, systemd 서비스, 그리고 필요한 워크플로입니다.

대부분의 사용자는 워크스테이션에서 `rdc`를 통해 서버를 관리하므로 이 페이지가 필요하지 않습니다. 이 페이지는 고급 디버깅이나 서버에서 직접 작업해야 할 때를 위해 작성되었습니다.

고수준 아키텍처는 [아키텍처](/en/docs/architecture)를 참조하고, `rdc`와 `renet`의 차이점은 [rdc vs renet](/en/docs/rdc-vs-renet)을 참조하십시오.

## 디렉터리 구조

```
/mnt/rediacc/                          # 메인 데이터스토어
├── repositories/                      # 암호화된 디스크 이미지 (LUKS)
│   └── {uuid}                         # 각각 루프 장치 이미지
├── mounts/                            # 복호화된 저장소 마운트 포인트
│   └── {uuid}/
│       ├── .rediacc.json              # 서비스 → IP 슬롯 매핑
│       ├── .rediacc/docker/           # Docker 데몬 데이터 (이미지, 컨테이너)
│       └── {service-name}/            # 서비스 디렉터리
│           ├── docker-compose.yml     # Compose 정의
│           ├── Rediaccfile            # 라이프사이클 훅 (bash)
│           └── data/                  # 영구 데이터
├── immovable/                         # 읽기 전용 공유 콘텐츠
├── .credentials/                      # 암호화된 시크릿
└── .backup-*/                         # BTRFS 스냅샷

/opt/rediacc/proxy/                    # Traefik 리버스 프록시
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME 인증서
└── traefik/dynamic/                   # 동적 라우트 파일

/run/rediacc/docker-{id}.sock          # 네트워크별 Docker 소켓
/var/lib/rediacc/router/               # 라우터 상태 (포트 할당)
```

## renet 명령

`renet`은 서버 측 바이너리입니다. 모든 명령에는 루트 권한(`sudo`)이 필요합니다.

### 저장소 라이프사이클

```bash
# 모든 저장소 목록
renet repository list

# 저장소 세부 정보 표시
renet repository status --name {uuid}

# 저장소 시작 (마운트 + Rediaccfile up 실행)
renet repository up --name {uuid} --network-id {id} --password-stdin

# 저장소 중지 (Rediaccfile down 실행)
renet repository down --name {uuid} --network-id {id}

# 새 저장소 생성
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (BTRFS reflink을 사용한 즉각적인 복사)
renet repository fork --source {uuid} --target {new-uuid}

# 실행 중인 저장소 확장 (다운타임 없음)
renet repository expand --name {uuid} --size 4G

# 저장소 및 모든 데이터 삭제
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

특정 저장소의 Docker 데몬에 대해 compose 명령 실행:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

docker 명령 직접 실행:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Docker 소켓을 직접 사용할 수도 있습니다:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> compose는 항상 `docker-compose.yml`이 있는 디렉터리에서 실행하십시오. 그렇지 않으면 Docker가 파일을 찾지 못합니다.

### 파일시스템 샌드박스

```bash
# Landlock 지원 확인
renet sandbox-exec --detect

# Landlock 샌드박스 내에서 명령 실행 (내부적으로 사용)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec`는 Landlock LSM 파일시스템 제한을 적용한 후 지정된 명령을 exec합니다. 모든 저장소 수준 연결에 대해 `sandbox-gateway`(SSH ForceCommand 핸들러)에 의해 자동으로 호출됩니다.

### 사용자별 Hub (개발 환경)

Hub는 각 사용자에게 개발 환경을 위한 전용 Docker 데몬을 제공하며, 저장소별 `FlavorRediacc` 데몬과 독립적으로 운영됩니다.

```bash
# 사용자별 Hub systemd 유닛 설치 / 제거
sudo renet hub install
sudo renet hub uninstall

# 유휴 상태의 사용자별 Hub 데몬 가비지 컬렉션
sudo renet hub gc
```

데몬은 `--flavor`로 선택되는 두 가지 플레이버 중 하나로 실행됩니다:

```bash
# 저장소 격리 데몬 (bridge=none, iptables=false) — 기본값
sudo renet daemon start-foreground --flavor=rediacc ...

# 사용자별 Hub 데몬 (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

`hub` 플레이버는 일반 브리지 네트워킹을 활성화하여 사용자가 실행하는 컨테이너에 외부 연결성을 제공하고, `rediacc` 플레이버는 저장소 간 루프백 격리를 강제합니다. Hub 감사 로그는 `/var/log/rediacc/hub/<user>.log`에 기록됩니다.

**플래그:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: Landlock 경로 규칙
- `--home-overlay`: 저장소별 쓰기 격리를 위해 홈 디렉터리에 OverlayFS 마운트
- `--sandbox-dir`: 저장소별 워크스페이스 (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: 작업 디렉터리 설정 및 저장소 환경을 위한 `.envrc` 로드
- `--run-as`: 설정 후 대상 사용자로 권한 강등
- `--reset-home`: 새로 시작하기 위해 저장소별 홈 오버레이 초기화

**`sandbox-gateway`**는 `authorized_keys`의 `command=`를 통해 설정된 SSH ForceCommand 핸들러입니다. 각 저장소의 SSH 키는 저장소 이름이 내장된 게이트웨이를 트리거하며, 클라이언트가 위조할 수 없습니다. 게이트웨이는 sandbox-exec 인수를 구성하고 sudo를 통해 exec합니다.

### 프록시 및 라우팅

```bash
renet proxy status          # Traefik + 라우터 상태 확인
renet proxy routes          # 구성된 모든 경로 표시
renet proxy refresh         # 실행 중인 컨테이너에서 경로 새로 고침
renet proxy up / down       # Traefik 시작/중지
renet proxy logs            # 프록시 로그 보기
```

경로는 컨테이너 레이블에서 자동으로 검색됩니다. Traefik 레이블 구성 방법은 [네트워킹](/en/docs/networking)을 참조하십시오.

### 시스템 상태

```bash
renet ps                    # 전체 시스템 상태
renet list all              # 전체: 시스템, 컨테이너, 저장소
renet list containers       # 모든 Docker 데몬의 모든 컨테이너
renet list repositories     # 저장소 상태 및 디스크 사용량
renet list system           # CPU, 메모리, 디스크, 네트워크
renet ips --network-id {id} # 네트워크의 IP 할당
```

### 데몬 관리

각 저장소는 자체 Docker 데몬을 실행합니다. 개별적으로 관리할 수 있습니다:

```bash
renet daemon status --network-id {id}    # Docker 데몬 상태
renet daemon start  --network-id {id}    # 데몬 시작
renet daemon stop   --network-id {id}    # 데몬 중지
renet daemon logs   --network-id {id}    # 데몬 로그
```

### 백업 및 복원

다른 머신이나 클라우드 스토리지로 백업 푸시:

```bash
# 원격 머신으로 푸시 (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# 클라우드 스토리지로 푸시 (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# 원격에서 풀
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# 원격 백업 목록
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> 대부분의 사용자는 `rdc repo push/pull`을 사용해야 합니다. `rdc` 명령은 자격 증명과 머신 확인을 자동으로 처리합니다.

### 체크포인팅 (CRIU)

체크포인트는 실행 중인 컨테이너의 상태를 저장하여 나중에 복원할 수 있게 합니다:

```bash
renet checkpoint create    --network-id {id}   # 실행 중인 컨테이너 상태 저장
renet checkpoint restore   --network-id {id}   # 체크포인트에서 복원
renet checkpoint validate  --network-id {id}   # 체크포인트 무결성 확인
```

### 유지보수

```bash
renet prune --dry-run       # 고아 네트워크 및 IP 미리보기
renet prune                 # 고아 리소스 정리
renet datastore status      # BTRFS 데이터스토어 상태
renet datastore validate    # 파일시스템 무결성 확인
renet datastore expand      # 온라인으로 데이터스토어 확장
```

## Systemd 서비스

각 저장소는 다음 systemd 유닛을 생성합니다:

| 유닛 | 목적 |
|------|------|
| `rediacc-docker-{id}.service` | 격리된 Docker 데몬 |
| `rediacc-docker-{id}.socket` | Docker API 소켓 활성화 |
| `rediacc-loopback-{id}.service` | 루프백 IP 별칭 설정 |

모든 저장소에서 공유되는 전역 서비스:

| 유닛 | 목적 |
|------|------|
| `rediacc-router.service` | 경로 검색 (포트 7111) |
| `rediacc-autostart.service` | 부팅 시 저장소 마운트 |
| `rediacc-autostart-reconcile.service` | 주기적 자동 시작 조정자 (아래 타이머에 의해 실행) |
| `rediacc-autostart-reconcile.timer` | 부팅 후 중단된 자동 시작 저장소를 복구하기 위해 약 3분마다 `renet repository reconcile` 실행 |

## 일반 워크플로

### 새 서비스 배포

1. 암호화된 저장소 생성:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. 마운트 후 `docker-compose.yml`, `Rediaccfile`, `.rediacc.json` 파일을 추가합니다.
3. 시작:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### 실행 중인 컨테이너 접근

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### 컨테이너를 실행하는 Docker 소켓 찾기

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### 설정 변경 후 서비스 재생성

```bash
sudo renet compose -- up -d
```

`docker-compose.yml`이 있는 디렉터리에서 실행하십시오. 변경된 컨테이너는 자동으로 재생성됩니다.

### 모든 데몬의 모든 컨테이너 확인

```bash
renet list containers
```

## 팁

- `renet compose`, `renet repository`, `renet docker` 명령에는 항상 `sudo`를 사용하십시오. LUKS 및 Docker 작업에 루트 권한이 필요합니다.
- `renet compose` 및 `renet docker`에 인수를 전달하기 전에 `--` 구분자가 필요합니다.
- compose는 `docker-compose.yml`이 있는 디렉터리에서 실행하십시오.
- `.rediacc.json` 슬롯 할당은 안정적입니다. 배포 후에는 변경하지 마십시오.
- `/run/rediacc/docker-{id}.sock` 경로를 사용하십시오 (systemd가 레거시 `/var/run/` 경로를 변경할 수 있습니다).
- 주기적으로 `renet prune --dry-run`을 실행하여 고아 리소스를 찾으십시오.
- BTRFS 스냅샷(`renet backup`)은 빠르고 비용이 저렴합니다. 위험한 변경 전에 사용하십시오.
- 저장소는 LUKS 암호화됩니다. 패스워드를 잃으면 데이터를 잃습니다.
