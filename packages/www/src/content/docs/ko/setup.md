---
title: "머신 설정"
description: "구성 생성, 머신 추가, 서버 프로비저닝, 인프라 구성."
category: "Guides"
order: 3
language: ko
sourceHash: "b3c8c42db1b8d99b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 머신 설정

첫 번째 머신을 실행하기까지 네 가지 단계가 필요합니다. 구성을 생성하고, 서버를 등록하고, 프로비저닝한 후, 선택적으로 공개 트래픽을 위한 인프라를 설정합니다.

## 1단계: 설정 생성

**설정**은 SSH 자격 증명, 머신 정의, 저장소 매핑을 저장하는 이름이 있는 구성 파일입니다. 프로젝트 워크스페이스로 생각하면 됩니다.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--ssh-key <path>` | 예 | SSH 개인 키 경로. 틸드(`~`)는 자동으로 확장됩니다. |
| `--renet-path <path>` | 아니오 | 원격 머신의 renet 바이너리 사용자 정의 경로. 기본 설치 위치가 기본값입니다. |

이렇게 하면 `my-infra`라는 설정이 생성되고 `~/.config/rediacc/my-infra.json`에 저장됩니다. 이름이 없을 때의 기본 설정은 `~/.config/rediacc/rediacc.json`으로 저장됩니다.

> 여러 설정을 가질 수 있습니다(예: `production`, `staging`, `dev`). 어떤 명령에서든 `--config` 플래그로 전환하십시오.

## 2단계: 머신 추가

원격 서버를 설정에 머신으로 등록합니다.

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| 옵션 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--ip <address>` | 예 | - | 원격 서버의 IP 주소 또는 호스트명 |
| `--user <username>` | 예 | - | 원격 서버의 SSH 사용자명 |
| `--port <port>` | 아니오 | `22` | SSH 포트 |
| `--datastore <path>` | 아니오 | `/mnt/rediacc` | Rediacc가 암호화된 저장소를 저장하는 서버 경로 |

머신을 추가한 후 rdc는 서버의 호스트 키를 가져오기 위해 자동으로 `ssh-keyscan`을 실행합니다. 수동으로 실행할 수도 있습니다.

```bash
rdc config machine scan-keys -m server-1
```

등록된 모든 머신을 보려면:

```bash
rdc config machine list
```

## 3단계: 머신 설정

필요한 모든 의존성으로 원격 서버를 프로비저닝합니다.

```bash
rdc config machine setup --name server-1
```

이 명령은:
1. SFTP를 통해 renet 바이너리를 서버에 업로드
2. Docker, containerd, cryptsetup 설치 (설치되지 않은 경우)
3. `rediacc` 시스템 사용자 생성 (UID 7111)
4. 데이터스토어 디렉터리 생성 및 암호화된 저장소를 위한 준비

| 옵션 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--datastore <path>` | 아니오 | `/mnt/rediacc` | 서버의 데이터스토어 디렉터리 |
| `--datastore-size <size>` | 아니오 | `95%` | 데이터스토어에 할당할 가용 디스크 비율 |
| `--debug` | 아니오 | `false` | 문제 해결을 위한 상세 출력 활성화 |

> 설정은 머신당 한 번만 실행해야 합니다. 필요한 경우 다시 실행해도 안전합니다.

## 호스트 키 관리

서버의 SSH 호스트 키가 변경된 경우(예: 재설치 후) 저장된 키를 새로 고침하십시오.

```bash
rdc config machine scan-keys -m server-1
```

이렇게 하면 해당 머신의 설정에서 `knownHosts` 필드가 업데이트됩니다.

## SSH 연결 테스트

머신을 추가한 후 접근 가능한지 확인합니다.

```bash
rdc term connect -m server-1 -c "hostname"
```

이렇게 하면 SSH 연결을 열고 명령을 실행합니다. 성공하면 SSH 구성이 올바른 것입니다.

더 자세한 진단을 위해 다음을 실행하십시오.

```bash
rdc doctor
```

> **클라우드 어댑터 전용**: `rdc machine test-connection` 명령은 자세한 SSH 진단을 제공하지만 클라우드 어댑터가 필요합니다. 로컬 어댑터의 경우 `rdc term` 또는 `ssh`를 직접 사용하십시오.

## 인프라 구성

공개적으로 트래픽을 제공해야 하는 머신의 경우 인프라 설정을 구성하십시오.

### 인프라 설정

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| 옵션 | 범위 | 설명 |
|------|------|------|
| `--public-ipv4 <ip>` | 머신 | 공개 IPv4 주소. 구성된 주소 패밀리에 대해서만 프록시 진입점 생성 |
| `--public-ipv6 <ip>` | 머신 | 공개 IPv6 주소. 구성된 주소 패밀리에 대해서만 프록시 진입점 생성 |
| `--base-domain <domain>` | 머신 | 애플리케이션의 기본 도메인(예: `example.com`) |
| `--cert-email <email>` | 설정 | Let's Encrypt TLS 인증서용 이메일(머신 간 공유) |
| `--cf-dns-token <token>` | 설정 | ACME DNS-01 챌린지용 Cloudflare DNS API 토큰(머신 간 공유) |
| `--tcp-ports <ports>` | 머신 | 추가로 포워딩할 TCP 포트 쉼표 구분 목록(예: `25,143,465,587,993`) |
| `--udp-ports <ports>` | 머신 | 추가로 포워딩할 UDP 포트 쉼표 구분 목록(예: `53`) |

머신 범위 옵션은 머신별로 저장됩니다. 설정 범위 옵션(`--cert-email`, `--cf-dns-token`)은 설정의 모든 머신에서 공유됩니다. 한 번 설정하면 모든 곳에 적용됩니다.

### 인프라 보기

```bash
rdc config infra show -m server-1
```

### 서버에 푸시

Traefik 리버스 프록시 구성을 생성하여 서버에 배포합니다.

```bash
rdc config infra push -m server-1
```

이 명령은:
1. 원격 머신에 renet 바이너리 배포
2. Traefik 리버스 프록시, 라우터, systemd 서비스 구성
3. `--cf-dns-token`이 설정된 경우 머신 서브도메인(`server-1.example.com` 및 `*.server-1.example.com`)에 대한 Cloudflare DNS 레코드 생성

DNS 단계는 자동이며 멱등성이 있습니다. 누락된 레코드를 생성하고, 변경된 IP로 레코드를 업데이트하며, 이미 올바른 레코드는 건너뜁니다. Cloudflare 토큰이 구성되지 않은 경우 DNS는 경고와 함께 건너뜁니다. 저장소별 와일드카드 DNS 레코드(자동 경로용)는 `rdc repo up`을 실행할 때 자동으로 생성됩니다.

## 클라우드 프로비저닝

VM을 수동으로 생성하는 대신 클라우드 공급자를 구성하고 [OpenTofu](https://opentofu.org/)를 사용하여 `rdc`가 자동으로 머신을 프로비저닝하도록 할 수 있습니다.

### 사전 요구 사항

OpenTofu 설치: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

SSH 설정에 `rdc`에 등록된 키가 있는지 확인하십시오.

```bash
# 키 파일을 읽어 /credentials/ssh 아래에 콘텐츠를 인라인으로 추가합니다.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### 클라우드 공급자 추가

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--provider <source>` | 예* | 알려진 공급자 소스(예: `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | 예* | 사용자 정의 OpenTofu 공급자 소스(알 수 없는 공급자용) |
| `--token <token>` | 예 | 클라우드 공급자 API 토큰 |
| `--region <region>` | 아니오 | 새 머신의 기본 리전 |
| `--type <type>` | 아니오 | 기본 인스턴스 타입/크기 |
| `--image <image>` | 아니오 | 기본 OS 이미지 |
| `--ssh-user <user>` | 아니오 | SSH 사용자명(기본값: `root`) |

\* `--provider` 또는 `--source` 중 하나가 필수입니다. 알려진 공급자(기본값 내장)에는 `--provider`를 사용하십시오. 사용자 정의 공급자에는 추가 `--resource`, `--ipv4-output`, `--ssh-key-attr` 플래그와 함께 `--source`를 사용하십시오.

### 머신 프로비저닝

```bash
rdc machine provision --name prod-2 --provider my-linode
```

이 단일 명령은:
1. OpenTofu를 통해 클라우드 공급자에 VM 생성
2. SSH 연결 대기
3. 설정에 머신 등록
4. renet 및 모든 의존성 설치
5. Traefik 프록시 및 Cloudflare DNS 구성(형제 머신에서 기본 도메인 자동 감지 또는 `--base-domain`으로 명시적 지정)

| 옵션 | 설명 |
|------|------|
| `--provider <name>` | 클라우드 공급자 이름(`add-provider`에서) |
| `--region <region>` | 공급자의 기본 리전 재정의 |
| `--type <type>` | 기본 인스턴스 타입 재정의 |
| `--image <image>` | 기본 OS 이미지 재정의 |
| `--base-domain <domain>` | 인프라의 기본 도메인. 지정하지 않으면 형제 머신에서 자동 감지 |
| `--no-infra` | 인프라 구성(프록시 + DNS) 완전히 건너뜀 |
| `--debug` | 상세한 프로비저닝 출력 표시 |

### 머신 프로비저닝 해제

```bash
rdc machine deprovision --name prod-2
```

OpenTofu를 통해 VM을 삭제하고 설정에서 제거합니다. `--force`를 사용하지 않으면 확인이 필요합니다. `machine provision`으로 생성된 머신에만 작동합니다.

### 공급자 목록

```bash
rdc config provider list
```

## 기본값 설정

모든 명령에서 지정할 필요가 없도록 기본값을 설정합니다.

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # 기본 머신
rdc config set --key team --value my-team                   # 기본 팀(클라우드 어댑터, 실험적)
```

기본 머신을 설정한 후 명령에서 `-m server-1`을 생략할 수 있습니다.

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## 다중 설정

명명된 설정으로 여러 환경을 관리합니다.

```bash
# 별도의 설정 생성
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# 특정 설정 사용
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

모든 설정 보기:

```bash
rdc config list
```

현재 설정 세부 정보 표시:

```bash
rdc config show
```
