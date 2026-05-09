---
title: "Hub"
description: "사용자별 Docker 데몬, 다중 템플릿 선택, CRIU 체크포인트/복원, 감사 로그, 데이터 루트 가비지 컬렉션을 갖춘 인증된 사용자별 컨테이너 환경을 제공합니다."
category: "Guides"
order: 14
language: ko
---

# Hub

Hub는 OAuth 인증 뒤에서 사용자별 컨테이너 환경을 제공합니다. 사용자는 단일 URL을 방문하여 OAuth2 공급자로 인증하면 자신의 개인 컨테이너로 투명하게 라우팅됩니다. 컨테이너는 온디맨드로 생성되며, 각 사용자는 자신만의 격리된 Docker 데몬을 갖고, 유휴 세션은 즉각적인 재개를 위해 CRIU로 체크포인트됩니다.

모든 설정은 `docker-compose.yml` 레이블을 통해 이루어집니다. Hub 자체는 리포지토리의 컴포즈 파일에서 `renet hub install` 명령으로 생성된 호스트 systemd 서비스로 실행됩니다. 리포지토리가 동작을 정의하고, Hub는 인증, 라우팅, 수명 주기 및 사용자별 격리를 처리합니다.

## 작동 방식

1. 사용자가 `code.example.com`(또는 `term.`, `desktop.`, 또는 다른 구성된 접두사)을 방문합니다.
2. Hub가 세션 쿠키를 확인합니다. 없으면 사용자를 구성된 OAuth2 공급자(Nextcloud, Keycloak, GitHub 등)로 리다이렉트합니다.
3. 인증 후, Hub가 사용자를 식별하고 해당 컨테이너를 조회합니다.
4. 컨테이너가 없으면 Hub가 호스트에 해당 사용자를 위한 전용 Docker 데몬을 프로비저닝한 다음 컨테이너를 생성합니다.
5. 요청이 루프백 네트워크를 통해 사용자의 컨테이너로 역방향 프록시됩니다.
6. 유휴 컨테이너는 CRIU로 체크포인트되며, 사용자별 데몬은 메모리를 확보하기 위해 중지됩니다. 다음 로그인 시 데몬이 재시작되고 CRIU가 컨테이너 상태를 몇 초 만에 복원합니다.

## 빠른 시작

리포지토리의 `docker-compose.yml`에 Hub를 서비스로 추가합니다. 서비스는 `install_as=systemd`로 표시되어 Docker 컨테이너가 아닌 호스트 서비스로 실행됩니다(systemd를 사용하는 사용자별 데몬 관리에 필요).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # 라우트 매핑: 서브도메인 접두사 -> 사용자 컨테이너 포트
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # 컨테이너 템플릿
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik 라우트 (파일 공급자; rediacc-router도 이 레이블을 읽음)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

OAuth2 공급자 자격 증명으로 `hub/.env`를 생성합니다.

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

호스트 systemd 유닛을 설치합니다(최초 1회, root 권한 필요).

```bash
sudo renet hub install /path/to/docker-compose.yml
```

이 명령은 `install_as=systemd` 서비스를 읽어 다음 파일을 작성합니다.

- `/etc/systemd/system/rediacc-hub.service` (유닛)
- `/etc/rediacc/hub/hub.labels.yaml` (템플릿 레이블)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (Traefik 파일 공급자 라우트)

이후 `systemctl daemon-reload && systemctl enable --now rediacc-hub`를 실행합니다. 제거하려면: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## 설치 명령 참조

| 명령 | 목적 |
|---------|---------|
| `sudo renet hub install <compose-file>` | 컴포즈 파일의 `install_as=systemd` 서비스를 호스트 아티팩트로 변환하고 유닛을 시작합니다. |
| `sudo renet hub uninstall <compose-file>` | 서비스의 모든 아티팩트를 중지, 비활성화 및 제거합니다. `<workspace>/<user>-docker/` 아래의 데이터 루트는 보존됩니다. |
| `sudo renet hub gc <workspace-dir>` | 방치된 사용자별 데이터 루트를 정리합니다(기본값: 활성 데몬 없이 30일 이상 된 항목). 플래그: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | 실행 중인 Hub API를 통해 모든 컨테이너의 JSON 상태를 표시합니다. |
| `renet hub stop <username>` | 특정 사용자의 컨테이너를 중지합니다. |

## 설정

모든 Hub 설정은 Hub 서비스의 컴포즈 레이블에 있습니다. 시크릿(OAuth client_secret, session_secret)은 레이블이 아닌 `hub/.env`에 저장합니다.

### 라우트 매핑

서브도메인 접두사를 사용자 컨테이너의 포트에 매핑합니다. Hub는 이 레이블을 읽어 각 요청을 어디로 프록시할지 파악합니다.

| 레이블 | 설명 | 예시 |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | `{prefix}.{domain}`을 사용자 컨테이너의 이 포트로 매핑 | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

각 라우트에는 Hub의 포트(7112)를 가리키는 매칭 Traefik 라우터도 필요합니다. Hub는 호스트명을 기반으로 내부적으로 사용자별 라우팅을 처리합니다.

### 컨테이너 템플릿

사용자 컨테이너의 모양을 정의합니다. Hub는 이 레이블을 읽어 새 컨테이너를 생성할 때 사용합니다.

| 레이블 | 설명 | 기본값 |
|-------|-------------|---------|
| `rediacc.hub.image` | 컨테이너 이미지 | `--container-image` 플래그 값 |
| `rediacc.hub.command` | 시작 명령 (bash -c 호환) | 없음 |
| `rediacc.hub.user` | 컨테이너 사용자 (비루트 권장) | `vscode` |
| `rediacc.hub.workspace` | 컨테이너 내부 워크스페이스 마운트 포인트 | `/workspace` |
| `rediacc.hub.shm_size` | 공유 메모리 크기 (바이트) | `1073741824` (1 GB) |
| `rediacc.hub.docker` | 사용자별 전용 dockerd를 프로비저닝하려면 `per-user` 설정 (강력 권장) | `""` |

`command` 레이블은 컨테이너에 할당된 루프백 IP에 대해 `${SERVICE_IP}` 및 `__SERVICE_IP__` 확장을 지원합니다(후자는 컴포즈 사전 확장을 피하기 위함).

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### 사용자별 Docker 데몬

`rediacc.hub.docker=per-user`가 설정되면, 각 사용자는 호스트에 전용 `dockerd` 인스턴스를 갖게 되며, 이는 컨테이너 내부에 `/var/run/docker.sock`으로 바인드 마운트됩니다. 이를 통해:

- 특권 컨테이너나 Docker-in-Docker 없이 사용자 환경 내에서 완전한 `docker ps`, `docker run`, `docker build` 사용이 가능합니다.
- 사용자 간 완전한 격리(사용자 A는 사용자 B의 컨테이너나 이미지를 볼 수 없음).
- `<workspace-dir>/<user>-docker/.rediacc/docker/data`에 사용자별 BTRFS 데이터 루트가 세션에 걸쳐 보존되어 캐시된 이미지가 유휴 체크포인트 사이클에서도 살아남습니다.

데몬은 32768부터 시작하는 전용 네트워크 ID 범위에 할당됩니다. 각 사용자의 데이터 루트에 있는 `.networkid` 마커 파일이 할당된 ID를 기록하여 복귀한 사용자가 동일한 데몬을 사용할 수 있습니다.

### 리소스 제한

단일 사용자가 모든 호스트 리소스를 소비하지 않도록 사용자별 리소스 제한을 설정합니다. 제한은 사용자의 컨테이너와 사용자별 dockerd 인스턴스 모두에 적용됩니다(systemd `CPUQuota=` / `MemoryMax=` 경유).

| 레이블 | 설명 | 예시 |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota 값 | `200%` (2코어) |
| `rediacc.hub.limits.memory` | systemd MemoryMax 값 | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

데몬은 슬라이스 수준 제한을 상속받도록 `rediacc.slice` systemd 슬라이스에 배치됩니다.

### 다중 템플릿 지원

여러 환경 유형을 제공합니다. 사용자는 로그인 시 `https://code.example.com/_hub/login?template=python`을 방문하여 템플릿을 선택합니다(선택은 OAuth 상태를 통해 전달됩니다). 이후 로그인 시 템플릿을 바꾸면 컨테이너가 재구성됩니다.

`rediacc.hub.templates.<name>.<field>` 레이블로 템플릿을 정의합니다. 기존의 `rediacc.hub.image` / `rediacc.hub.command` 등 레이블은 선택하지 않은 사용자를 위한 암묵적 "기본" 템플릿을 계속 정의합니다.

```yaml
labels:
  # ?template=...이 생략된 경우의 기본 템플릿.
  - "rediacc.hub.template=fulldev"

  # VS Code + 데스크톱 + 터미널이 포함된 풍부한 환경.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # 경량 VS Code 전용.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python 특화 환경.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### 수명 주기 훅

수명 주기 시점에 사용자 컨테이너 내부에서 명령을 실행합니다. 훅은 컨테이너 사용자(루트 아님)로 실행됩니다.

| 레이블 | 실행 시점 | 예시 |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | 컨테이너 생성 후 (첫 로그인) | 리포지토리 클론, 의존성 설치 |
| `rediacc.hub.hook.checkpoint.pre_dump` | 유휴 세션의 CRIU 체크포인트 전 | 체크포인트할 수 없는 데몬 중지 (X 서버, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | CRIU 복원 후 | pre_dump에서 중지한 데몬 재시작 |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### 체크포인트 / 복원

`--checkpoint`가 설정되면, 유휴 사용자 컨테이너는 CRIU로 체크포인트되고 사용자별 데몬은 메모리를 확보하기 위해 중지됩니다. 다음 로그인 시 데몬이 재시작되고 CRIU가 디스크에서 컨테이너 상태를 복원하며, 열린 파일, 실행 중인 프로세스, 터미널 세션이 보존됩니다. 일반적인 재개 시간은 워크로드에 관계없이 몇 초입니다.

| 레이블 | 설명 | 기본값 |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | 사용자 컨테이너에 대한 CRIU 체크포인트 활성화 | `false` |

Hub 명령에 `--checkpoint`와 0이 아닌 `--idle-timeout`(예: `30m`)을 전달합니다. 체크포인트 디렉토리는 `<workspace-dir>/<user>/.checkpoint/`에 저장됩니다.

특정 사용자에 대해 CRIU가 연속으로 3번 실패하면 해당 사용자의 체크포인트가 비활성화되고 중지 후 재생성 방식으로 대체됩니다.

### 임시 모드

기본적으로 사용자 워크스페이스는 영구적(재시작 후에도 유지)입니다. 임시 모드는 로그인마다 깨끗한 환경을 제공하며, 데모, 교육, CI에 유용합니다.

| 레이블 | 설명 | 기본값 |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` 또는 `ephemeral` | `persistent` |

임시 모드에서는 워크스페이스가 tmpfs(RAM 기반)이고 컨테이너는 중지 시 자동으로 삭제됩니다.

### 유휴 타임아웃

| 플래그 | 설명 | 기본값 |
|------|-------------|---------|
| `--idle-timeout=<dur>` | 이 시간보다 오래 유휴 상태인 컨테이너를 중지/체크포인트 | `0` (비활성화) |

`0`은 컨테이너를 영원히 실행 상태로 유지합니다. 실용적인 값은 `30m`입니다. 유휴 사용자는 30분 후 메모리를 해제하고, 복귀한 사용자는 CRIU를 통해 몇 초 만에 재개됩니다.

### 접근 제어

| 변수 | 설명 |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Hub 사용이 허용된 그룹의 쉼표로 구분된 목록 (공급자가 그룹 클레임을 제공하는 경우) |
| `HUB_ADMIN_USERS` | 쉼표로 구분된 관리자 사용자 이름. 관리자는 대시보드에서 다른 사용자의 컨테이너를 보고 제어할 수 있습니다. |

## 감사 로그

사용자별 데몬에서 발생하는 모든 사용자 시작 컨테이너/이미지 이벤트(create, start, stop, destroy, kill, pull, push)가 `/var/log/rediacc/hub/<user>.log`에 줄 구분 JSON 레코드로 추가됩니다.

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

항목은 CRIU 체크포인트/복원에서도 살아남습니다(복원 후 감사 스트림이 재연결됩니다). 디스크 사용량을 제한하려면 `logrotate`를 사용하십시오. 샘플 설정:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## 대시보드

Hub에는 `/_hub/dashboard`에 셀프서비스 대시보드가 포함되어 있습니다. 다음 정보를 표시합니다.

- 상태와 함께 모든 실행 중인 환경
- 선택된 템플릿
- 서비스 링크 (코드, 터미널, 데스크톱 또는 다른 라우트를 한 번에 열기)
- 유휴 타이머
- 사용자별 디스크 사용량, 실행 중인 컨테이너 수, 이미지 수
- 관리자는 모든 컨테이너를 보고, 일반 사용자는 자신의 것만 봅니다.

통계는 30초마다 샘플링됩니다.

## 데이터 루트 가비지 컬렉션

사용자별 데이터 루트는 장기간 실행되는 호스트에서 누적됩니다. `renet hub gc`를 예약하여 방치된 것들을 정리하십시오. systemd 타이머가 효과적입니다.

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run`은 삭제하지 않고 후보를 로그에 기록합니다. `.networkid` 마커가 `--max-age`보다 오래되었고 기록된 데몬이 더 이상 호스트에 구성되지 않은 경우 데이터 루트가 대상이 됩니다.

## OAuth 설정

Hub는 모든 표준 OAuth2 공급자와 함께 작동합니다. 환경 변수를 통해 설정합니다.

| 변수 | 설명 | 필수 여부 |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 클라이언트 ID | 예 |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 클라이언트 시크릿 | 예 |
| `HUB_OAUTH_AUTHORIZE_URL` | 공급자의 authorize 엔드포인트 | 예 |
| `HUB_OAUTH_TOKEN_URL` | 공급자의 token 엔드포인트 | 예 |
| `HUB_OAUTH_USERINFO_URL` | 공급자의 userinfo 엔드포인트 | 예 |
| `HUB_OAUTH_USERINFO_PATH` | JSON 응답에서 사용자명을 추출하는 점 경로 | 예 |
| `HUB_OAUTH_REDIRECT_URI` | 콜백 URL 재정의 (비어있으면 자동 계산) | 아니요 |
| `HUB_OAUTH_SCOPES` | 추가 스코프 (공백으로 구분) | 아니요 |
| `HUB_SESSION_SECRET` | 쿠키 서명을 위한 32바이트 이상의 16진수 문자열 | 권장 |

### 공급자 예시

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH`는 JSON 응답 내의 점으로 구분된 경로입니다. Nextcloud의 `{"ocs":{"data":{"id":"alice"}}}`와 같은 중첩 객체에는 `ocs.data.id`를 사용합니다.

## 예시

### 개발 환경 (VS Code + 터미널 + 데스크톱)

OpenVSCode Server, 웹 터미널(ttyd), noVNC 데스크톱이 포함된 완전한 개발 환경입니다. 사용자는 내부에 자신만의 Docker 데몬을 갖습니다.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... 각 접두사에 대한 Traefik 라우터 ...
```

### Jupyter Notebook 환경

JupyterLab이 포함된 데이터 과학 환경:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### 간단한 웹 애플리케이션 (임시)

로그인마다 새로 시작하는 단일 서비스 환경:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## 관련 가이드

- [**서비스**](/ko/docs/services) -- Rediaccfile 수명 주기, 컴포즈 패턴
- [**네트워킹**](/ko/docs/networking) -- Docker 레이블, Traefik 라우팅, TLS 인증서
- [**백업 및 복원**](/ko/docs/backup-restore) -- 워크스페이스 지속성 및 복구
- [**개발 환경**](/ko/docs/development-environments) -- 개발 환경을 위한 프로덕션 클로닝
