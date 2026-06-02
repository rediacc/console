---
title: "문제 해결"
description: "일반적인 SSH, 설정, 저장소, 서비스, Docker 문제에 대한 해결책."
category: "Guides"
order: 10
language: ko
sourceHash: "7cfabe7bbf3914c3"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 문제 해결

일반적인 문제와 해결 방법입니다. 확실하지 않을 때는 `rdc doctor`로 시작하여 전체 진단 검사를 실행하세요.

## SSH 연결 실패

- 수동으로 연결 가능한지 확인하세요: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- `rdc config machine scan-keys -m server-1`을 실행하여 호스트 키를 새로 고치세요
- SSH 포트가 일치하는지 확인하세요: `--port 22`
- 간단한 명령으로 테스트하세요: `rdc term connect -m server-1 -c "hostname"`

## 호스트 키 불일치

서버가 재설치되거나 SSH 키가 변경되면 "host key verification failed" 오류가 표시됩니다:

```bash
rdc config machine scan-keys -m server-1
```

이 명령은 새로운 호스트 키를 가져와 설정을 업데이트합니다.

## 머신 설정 실패

- SSH 사용자에게 비밀번호 없는 sudo 접근 권한이 있는지, 또는 필요한 명령에 대해 `NOPASSWD`가 구성되어 있는지 확인하세요
- 서버의 디스크 여유 공간을 확인하세요
- 자세한 출력을 위해 `--debug`와 함께 실행하세요: `rdc config machine setup --name server-1 --debug`

## 배포판별 설정 문제

공식 지원 서버 OS 5종(Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10)은 서로 다른 보안 정책과 패키지 관리자를 사용합니다. 대부분의 설정은 "바로 작동"하지만, 아래 경우들은 그렇지 않은 경우를 다룹니다.

### SELinux 거부 (Fedora 43, Oracle Linux 10)

두 OS 모두 강제 모드에서 SELinux를 실행합니다. rdc 설정은 사용자 정의 SELinux 정책을 설치하지 않으며, 저장소별 docker 데몬은 표준 `container_t` 컨텍스트에서 실행됩니다. AVC 거부와 함께 설정이 실패하면 감사 로그를 확인하고 도메인을 식별하세요:

```bash
sudo ausearch -m AVC -ts recent | head -40
# 또는:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

거부가 renet 바이너리나 특정 파일 경로를 가리키면, SELinux를 비활성화하는 것보다 레이블 재지정(`restorecon -v /path`)이 거의 항상 올바른 해결책입니다. 조사하는 동안 임시 해결책으로 `sudo setenforce 0`을 사용하면 시스템이 허용 모드로 전환됩니다. 레이블 재지정이 유지됨을 확인한 후 `sudo setenforce 1`로 다시 활성화하세요.

### AppArmor 거부 (Ubuntu 24.04, openSUSE Leap 16.0)

두 OS 모두 기본적으로 AppArmor를 실행하며, 저장소별 docker 데몬은 기본 컨테이너 프로필을 사용합니다. 저장소 내 컨테이너가 차단되는 경우:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU는 AppArmor에 걸리는 알려진 경우입니다. Renet은 `rediacc.checkpoint=true`로 레이블된 컨테이너에 자동으로 `security_opt: apparmor=unconfined`를 설정합니다. 그 외의 경우에는 AppArmor 프로필을 직접 구성할 필요가 없습니다. [Rediacc 규칙](/ko/docs/rules-of-rediacc)의 CRIU 참고 사항을 확인하세요.

### 패키지 관리자 오류 특징

| OS | 패키지 관리자 | 일반적인 오류 | 해결책 |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare 엣지 캐시가 원본 뒤에 있습니다. ~15초 후 `apt-get update`를 재시도하면 다음 폴링에서 무결성 검사가 통과됩니다. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | 디스크에 캐시된 RPM 저장소 메타데이터가 오래되었습니다. `sudo dnf clean all && sudo dnf makecache`를 실행하세요. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | `sudo zypper refresh rediacc`를 한 번 실행하면 이후 설치가 성공합니다. |

### btrfs 모듈 누락 (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

`rdc config machine setup` 또는 `renet system check-btrfs`가 다음과 같이 실패하는 경우:

```
Module btrfs not found
```

...서버가 in-tree btrfs 모듈 없이 출시된 RHEL 10 기본 커널을 실행하고 있습니다. 이것은 Rediacc 버그가 아닙니다. RHEL 10은 의도적으로 btrfs를 제외했습니다. 수정 방법은 **Oracle Linux 10을 대신 사용**하는 것입니다. Oracle 10은 btrfs를 유지하는 Unbreakable Enterprise Kernel(UEK)을 기본으로 사용합니다. 전체 내용은 [요구 사항 - UEK를 사용하는 이유?](/ko/docs/requirements)를 참조하세요.

## 저장소 생성 실패

- 설정이 완료되었는지 확인하세요: 데이터스토어 디렉터리가 존재해야 합니다
- 서버의 디스크 여유 공간을 확인하세요
- renet 바이너리가 설치되어 있는지 확인하세요 (필요한 경우 설정을 다시 실행하세요)

## 서비스 시작 실패

- Rediaccfile 구문을 확인하세요: 유효한 Bash여야 합니다
- Rediaccfile이 `renet compose --`를 사용하는지 확인하세요 (`docker compose` 아님)
- Docker 이미지에 접근 가능한지 확인하세요 (`up()`에서 `renet compose -- pull`을 고려하세요)
- 저장소의 Docker 소켓을 사용하여 컨테이너 로그를 확인하세요:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

또는 모든 컨테이너를 확인하세요:

```bash
rdc machine containers --name server-1
```

## 권한 거부 오류

- 저장소 작업은 서버에서 루트 권한이 필요합니다 (renet은 `sudo`를 통해 실행됩니다)
- SSH 사용자가 `sudo` 그룹에 있는지 확인하세요
- 데이터스토어 디렉터리의 권한이 올바른지 확인하세요

## Docker 소켓 문제

각 저장소에는 자체 Docker 데몬이 있습니다. Docker 명령을 수동으로 실행할 때는 올바른 소켓을 지정해야 합니다:

```bash
# rdc term 사용 (자동 구성됨):
rdc term connect -m server-1 -r my-app -c "docker ps"

# 또는 소켓으로 수동 지정:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816`을 저장소의 네트워크 ID로 교체하세요 (`rediacc.json` 또는 `rdc repo status`에서 확인 가능).

## `docker run`에 네트워크 없음, `apt update` 실패, `curl` 응답 없음

저장소 셸에서 `--network host` 없이 컨테이너를 실행하면 루프백 인터페이스만 있고 DNS와 외부 연결이 없는 격리된 컨테이너가 생성됩니다. `apt update`, `pip install`, `curl https://...` 또는 모든 네트워크 요청이 DNS 오류로 즉시 실패합니다.

이것은 의도적인 동작입니다. Rediacc의 네트워킹 모델은 `renet compose`에 의해 강제되는 **모든 서비스에 대한 호스트 네트워킹**입니다. NAT가 있는 기본 Docker 브리지는 하나의 저장소가 다른 저장소의 서비스에 접근하는 것을 막는 커널 레벨 루프백 격리를 우회하므로, 저장소별 Docker 데몬(`FlavorRediacc`)은 `"bridge": "none"` 및 `"iptables": false`로 구성됩니다. 일반 `docker run` 컨테이너가 연결할 수 있는 라우팅 가능한 브리지가 없습니다. (개발 환경에서 사용되는 사용자별 Hub 데몬(`FlavorHub`)은 예외로, 브리지와 iptables를 활성화하여 사용자 컨테이너가 외부 네트워크에 연결할 수 있도록 합니다.)

**임시 컨테이너에서 네트워크 접근을 위해서는 호스트 네트워킹을 사용하세요:**

```bash
# 저장소 셸 내부 (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# 이제 apt update, curl, pip install이 모두 작동합니다.
```

**프로덕션 서비스에는 원시 `docker run` 대신 `renet compose`와 함께 Rediaccfile을 사용하세요.** `renet compose`는 `network_mode: host`, 서비스 IP 레이블, Traefik 라우팅 레이블을 자동으로 주입합니다. 자세한 내용은 [서비스](/ko/docs/services)를 참조하세요.

## 샌드박스 파일에 대한 VS Code 권한 거부

이전 VS Code 세션 이후 `rdc vscode connect -m <machine> -r <repo>`로 연결할 때, 이전 버전의 renet은 `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` 같은 오류를 발생시켰습니다. 원인은 샌드박스 디렉터리 내의 파일 소유권 혼재로, SSH 사용자와 내부 `rediacc` 사용자가 모두 파일을 작성했기 때문입니다.

최신 버전의 renet은 다음으로 이 문제를 해결합니다:

- 저장소별 샌드박스 워크스페이스(`/mnt/rediacc/.interim/sandbox/<repo>/`)를 `rediacc` 그룹과 set-group-ID 비트(모드 `2775`)로 생성하여 하위에 작성되는 모든 파일이 올바른 그룹을 상속합니다.
- 샌드박스 런타임 내부에 umask `002`를 적용하여 새 파일이 그룹 쓰기 가능(`0664`/`0775`)으로 생성됩니다.
- 시작 시 기존 `.vscode-server/` 서브트리를 정규화하여 수정 전의 오래된 파일이 자동으로 수정됩니다.

권한 오류가 계속 발생하면, 머신의 셸에서 `sudo systemctl restart rediacc-docker-<network-id>`로 저장소의 Docker 데몬을 한 번 재시작하여 정규화 패스가 실행되도록 한 다음 `rdc vscode connect`를 다시 시도하세요.

## renet 업그레이드 후 데몬 시작 실패

시작할 때마다 `renet daemon start-foreground`는 현재 템플릿에서 저장소의 구성 디렉터리에 있는 `daemon.json` 및 `containerd.toml`을 다시 작성하므로, 이전 renet 버전으로 생성된 구성을 가진 저장소는 자동으로 새 형식을 적용합니다. 마이그레이션 명령을 실행하거나 systemd 유닛을 수동으로 재생성할 필요가 없습니다. 서비스만 재시작하면 됩니다:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

유닛이 여전히 실패하는 경우 저널에서 특정 오류를 확인하세요:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## 잘못된 Docker 데몬에 생성된 컨테이너

컨테이너가 저장소의 격리된 데몬 대신 호스트 시스템의 Docker 데몬에 나타나는 경우, 가장 일반적인 원인은 Rediaccfile에서 `sudo docker`를 사용하는 것입니다.

`sudo`는 환경 변수를 초기화하므로 `DOCKER_HOST`가 손실되고 Docker가 시스템 소켓(`/var/run/docker.sock`)으로 기본 설정됩니다. Rediacc은 이를 자동으로 차단하지만, 이 문제가 발생하면:

- **`docker`를 직접 사용하세요**, Rediaccfile 함수는 이미 충분한 권한으로 실행됩니다
- sudo를 반드시 사용해야 한다면 `sudo -E docker`를 사용하여 환경 변수를 유지하세요
- Rediaccfile에서 `sudo docker` 명령을 찾아 `sudo`를 제거하세요

## 터미널이 작동하지 않음

`rdc term`이 터미널 창을 열지 못하는 경우:

- `-c`와 함께 인라인 모드를 사용하여 명령을 직접 실행하세요:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- 인라인 모드에 문제가 있으면 `--external`로 외부 터미널을 강제 사용하세요
- Linux에서는 `gnome-terminal`, `xterm` 또는 다른 터미널 에뮬레이터가 설치되어 있는지 확인하세요

## 진단 실행

```bash
rdc doctor
```

환경, renet 설치, 설정, 인증 상태를 확인합니다. 각 검사는 간단한 설명과 함께 OK, Warning, 또는 Error를 보고합니다.
