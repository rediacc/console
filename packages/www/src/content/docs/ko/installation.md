---
title: "설치"
description: "Linux, macOS, 또는 Windows에 Rediacc CLI를 설치합니다."
category: "Guides"
order: 1
language: ko
---

# 설치

워크스테이션에 `rdc` CLI를 설치합니다. 수동으로 설치해야 하는 도구는 이것뿐입니다. 나머지는 원격 머신을 설정할 때 자동으로 처리됩니다.

## 빠른 설치

### Linux 및 macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

이 명령은 `rdc` 바이너리를 `$HOME/.local/bin/`에 다운로드합니다. 이 디렉토리가 PATH에 있는지 확인하십시오.

```bash
export PATH="$HOME/.local/bin:$PATH"
```

영구적으로 적용하려면 이 줄을 셸 프로파일(`~/.bashrc`, `~/.zshrc` 등)에 추가하십시오.

### Windows

PowerShell에서 실행하십시오.

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

이 명령은 `rdc.exe`를 `%LOCALAPPDATA%\rediacc\bin\`에 다운로드합니다. 필요한 경우 설치 프로그램이 PATH에 추가할지 여부를 묻습니다.

## 패키지 매니저

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL 호환)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux, Rocky Linux 모두 동일한 DNF 절차를 사용합니다. `dnf`가 있는 모든 RHEL 호환 배포판에서 위 리포지토리를 사용할 수 있습니다. 참고: **Oracle Linux 10은 Rediacc 서버 대상으로 공식 지원되는 유일한 RHEL 계열 배포판입니다**([요구 사항](/ko/docs/requirements) 참조). Rocky/Alma 10은 renet 데이터 플레인에 필요한 btrfs 커널 모듈이 없지만, `rdc` CLI는 정상적으로 설치됩니다.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

openSUSE Leap 16.0 이상에서 테스트되었습니다.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

참고: `gcompat` 패키지(glibc 호환성 레이어)는 의존성으로 자동 설치됩니다.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

### npm (Node.js)

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz
```

Node.js 22 이상이 필요합니다. 특정 버전을 설치하려면:

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-0.8.5.tgz
```

## Docker

CLI를 컨테이너로 가져와 실행합니다.

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

편의를 위해 별칭을 만드십시오.

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

사용 가능한 Docker 태그:

| 태그 | 설명 |
|-----|-------------|
| `:stable` | 최신 안정 릴리스 (권장) |
| `:edge` | 최신 edge 릴리스 |
| `:0.8.4` | 고정된 버전 (변경 불가) |
| `:latest` | `:stable`의 별칭 |

## 설치 확인

```bash
rdc --version
```

## 업데이트

최신 버전으로 업데이트:

```bash
rdc update
```

설치 없이 업데이트 확인:

```bash
rdc update --check-only
```

현재 업데이트 상태 보기:

```bash
rdc update --status
```

이전 버전으로 롤백:

```bash
rdc update --rollback
```

## 릴리스 채널

Rediacc는 채널 기반 릴리스 시스템을 사용합니다. 채널은 CLI 업데이트, 패키지 매니저 설치, Docker 풀에서 수신하는 버전을 결정합니다.

| 채널 | 설명 | 업데이트 시점 |
|---------|-------------|--------------|
| `stable` | 7일 소크 후 edge에서 승격된 프로덕션 | 주간 소크 승격 |
| `edge` | 지속적으로 배포되는 프로덕션 | main 브랜치 병합마다 |
| `pr-N` | PR 프리뷰 빌드 | 풀 리퀘스트마다 자동 |

### 채널 전환

```bash
rdc update --channel edge      # edge 채널로 전환
rdc update --channel stable    # stable 채널로 복귀
```

edge 채널에서 직접 설치:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

패키지 매니저의 경우 리포지토리 URL에서 `stable`을 `edge`로 교체하십시오.

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### 채널 작동 방식

채널은 모든 전달 방법에 균일하게 적용됩니다.

- **설치 스크립트**: `REDIACC_CHANNEL` 환경 변수로 채널 선택
- **패키지 리포지토리**: `releases.rediacc.com/{format}/{channel}/`
- **Docker 태그**: `ghcr.io/rediacc/elite/cli:{channel}`
- **CLI 업데이트**: `rdc update`는 설치 시 구성된 채널을 확인합니다.

### PR 프리뷰 자동 설정

PR 프리뷰 배포(예: `pr-420.rediacc.workers.dev`)에서 설치하면 채널과 계정 서버가 자동으로 구성됩니다.

- CLI 바이너리는 `pr-420` 채널에서 다운로드됩니다.
- `rdc update`는 업데이트를 위해 `pr-420` 채널을 확인합니다.
- 모든 계정/구독 명령이 PR 프리뷰 서버에 연결됩니다.
- 프리뷰 사이트의 Docker 명령에 `cli:pr-420`이 표시됩니다.

수동 설정이 필요 없습니다. 설치 스크립트가 URL에서 배포 컨텍스트를 자동으로 감지합니다.

## 원격 바이너리 업데이트

원격 머신에 대해 명령을 실행하면 CLI가 자동으로 일치하는 `renet` 바이너리를 프로비저닝합니다. 바이너리가 업데이트되면 라우트 서버(`rediacc-router`)가 자동으로 재시작되어 새 버전을 인식합니다.

재시작은 투명하게 이루어지며 **다운타임이 없습니다**.

- 라우트 서버는 약 1~2초 안에 재시작됩니다.
- 그 동안 Traefik은 마지막으로 알려진 라우팅 설정을 사용하여 트래픽을 계속 제공합니다. 어떤 라우트도 삭제되지 않습니다.
- Traefik은 다음 폴링 사이클(5초 이내)에 새 설정을 인식합니다.
- **기존 클라이언트 연결(HTTP, TCP, UDP)은 영향을 받지 않습니다.** 라우트 서버는 설정 공급자로, 데이터 경로에 있지 않습니다. Traefik이 모든 트래픽을 직접 처리합니다.
- 애플리케이션 컨테이너는 건드리지 않습니다. 시스템 수준의 라우트 서버 프로세스만 재시작됩니다.

자동 재시작을 건너뛰려면 모든 명령에 `--skip-router-restart`를 전달하거나 `RDC_SKIP_ROUTER_RESTART=1` 환경 변수를 설정하십시오.
