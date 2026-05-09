---
title: 아키텍처
description: >-
  Rediacc의 작동 방식: 두 도구 아키텍처, 어댑터 감지, 보안 모델, 설정 구조.
category: Concepts
order: 0
language: ko
---

# 아키텍처

이 페이지에서는 Rediacc의 내부 작동 방식을 설명합니다. 두 도구 아키텍처, 어댑터 감지, 보안 모델, 설정 구조를 다룹니다.

## 전체 스택 개요

트래픽은 인터넷에서 역방향 프록시를 통해 격리된 Docker 데몬으로 흐르며, 각각 암호화된 스토리지를 사용합니다.

![전체 스택 아키텍처](/img/arch-full-stack.svg)

각 레포지토리는 자체 Docker 데몬, 루프백 IP 서브넷(/26 = 64 IP), LUKS 암호화 BTRFS 볼륨을 갖습니다. 라우트 서버는 모든 데몬에서 실행 중인 컨테이너를 발견하여 Traefik에 라우팅 설정을 제공합니다.

## 두 도구 아키텍처

Rediacc는 SSH를 통해 함께 작동하는 두 바이너리를 사용합니다.

![두 도구 아키텍처](/img/arch-two-tool.svg)

- **rdc**는 워크스테이션(macOS, Linux, 또는 Windows)에서 실행됩니다. 로컬 설정을 읽고, SSH로 원격 머신에 연결하고, renet 명령어를 호출합니다.
- **renet**은 원격 서버에서 루트 권한으로 실행됩니다. LUKS 암호화 디스크 이미지, 격리된 Docker 데몬, 서비스 오케스트레이션, 역방향 프록시 설정을 관리합니다.

로컬에서 입력하는 모든 명령어는 원격 머신에서 renet을 실행하는 SSH 호출로 변환됩니다. 서버에 수동으로 SSH 접속할 필요가 없습니다.

운영자 중심의 간단한 규칙은 [rdc vs renet](/en/docs/rdc-vs-renet)을 참조하세요. 테스트를 위해 로컬 VM 클러스터를 실행하려면 `rdc ops`를 사용할 수도 있습니다. [실험적 VM](/en/docs/experimental-vms)을 참조하세요.

## 설정

모든 CLI 상태는 `~/.config/rediacc/` 아래의 플랫 JSON 설정 파일에 저장됩니다.

### 로컬 어댑터 (기본값)

셀프호스팅 사용의 기본값입니다. 모든 상태는 워크스테이션의 설정 파일(예: `~/.config/rediacc/rediacc.json`)에 저장됩니다.

- 머신에 직접 SSH 연결
- 외부 서비스 불필요
- 단일 사용자, 단일 워크스테이션
- 기본 설정은 첫 CLI 사용 시 자동으로 생성됩니다. 명명된 설정은 `rdc config init --name <name>`으로 생성합니다.

### 클라우드 어댑터 (실험적)

설정에 `apiUrl`과 `token` 필드가 포함된 경우 자동으로 활성화됩니다. 상태 관리와 팀 협업을 위해 Rediacc API를 사용합니다.

- 클라우드 API에 상태 저장
- 역할 기반 접근 제어를 갖춘 다중 사용자 팀
- 시각적 관리를 위한 웹 콘솔
- `rdc auth login`으로 설정

> **참고:** 클라우드 어댑터 명령어는 실험적입니다. `REDIACC_EXPERIMENTAL=1`을 설정하여 활성화하세요.

두 어댑터 모두 동일한 CLI 명령어를 사용합니다. 어댑터는 상태가 저장되는 위치와 인증 방식에만 영향을 미칩니다.

## rediacc 사용자

`rdc config machine setup`을 실행하면 renet이 원격 서버에 `rediacc`라는 시스템 사용자를 생성합니다.

- **UID**: 7111
- **Shell**: `/sbin/nologin` (SSH로 직접 로그인 불가)
- **목적**: 레포지토리 파일을 소유하고 Rediaccfile 함수를 실행

`rediacc` 사용자는 SSH로 직접 접근할 수 없습니다. 대신 rdc가 설정한 SSH 사용자(예: `deploy`)로 연결하고, renet이 `sudo -u rediacc /bin/sh -c '...'`를 통해 레포지토리 작업을 실행합니다. 즉:

1. SSH 사용자에게 `sudo` 권한이 필요합니다.
2. 모든 레포지토리 데이터는 SSH 사용자가 아닌 `rediacc`가 소유합니다.
3. Rediaccfile 함수(`up()`, `down()`)는 `rediacc`로 실행됩니다.

이 분리는 어떤 SSH 사용자가 관리하든 레포지토리 데이터의 소유권이 일관되게 유지됨을 보장합니다.

## Docker 격리

각 레포지토리는 자체 격리된 Docker 데몬을 갖습니다. 레포지토리가 마운트되면 renet이 고유한 소켓을 가진 전용 `dockerd` 프로세스를 시작합니다.

![Docker 격리](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

예를 들어, 네트워크 ID `2816`을 가진 레포지토리는 다음을 사용합니다.
```
/var/run/rediacc/docker-2816.sock
```

즉:
- 서로 다른 레포지토리의 컨테이너는 서로를 볼 수 없습니다.
- 각 레포지토리는 자체 이미지 캐시, 네트워크, 볼륨을 갖습니다.
- 호스트 Docker 데몬(있는 경우)은 완전히 분리됩니다.

Rediaccfile 함수는 자동으로 올바른 소켓으로 `DOCKER_HOST`가 설정됩니다.

AI 에이전트가 `rdc term connect -r <repo>`를 통해 레포지토리에 진입할 때도 동일한 격리가 적용됩니다. 세션은 권한 없는 `rediacc` 사용자(UID 7111)로, 독립된 마운트 네임스페이스에서, 단일 레포 데몬 소켓으로 범위가 한정된 `DOCKER_HOST`로 실행됩니다. 포크 우선 워크플로우는 이 런타임 격리를 CoW 클론 기본 기능과 결합합니다. 에이전트는 태스크별 포크에서 작동하며, grand(프로덕션) 레포지토리에서는 작동하지 않습니다. 전체 샌드박스 모델, 재정의 의미론, 외부 서비스 자격 증명에 대한 개발자 책임 경계는 [AI 에이전트 안전성 및 가드레일](/en/docs/ai-agents-safety)을 참조하세요.

### 데몬 경로 레이아웃

Docker 데이터와 설정은 레포지토리 마운트 내부에 저장되어 각 데몬이 호스트 및 다른 레포지토리와 완전히 격리됩니다.

**레포별 레이아웃:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker 데이터 루트
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker 설정
```

**독립형 레이아웃** (레포 마운트에 연결되지 않은 데몬):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**공유 런타임 경로** (변경 없음):
```
/run/rediacc/docker-{N}.sock
```

이 통합 레이아웃은 데몬 경로가 호스트 파일시스템과 암호화 볼륨으로 분리되었을 때 발생했던 읽기 전용/읽기-쓰기 마운트 충돌을 제거합니다. 레포별 데몬과 독립형 데몬 모두 동일한 디렉토리 구조를 따르므로 툴링과 진단이 두 경우에서 동일하게 작동합니다.

## LUKS 암호화

레포지토리는 서버의 데이터스토어(기본값: `/mnt/rediacc`)에 저장된 LUKS 암호화 디스크 이미지입니다. 각 레포지토리는:

1. 무작위로 생성된 암호화 패스프레이즈("자격 증명")를 갖습니다.
2. 파일로 저장됩니다: `{datastore}/repos/{guid}.img`
3. 접근 시 `cryptsetup`을 통해 마운트됩니다.

자격 증명은 설정 파일에 저장되지만 서버에는 **절대** 저장되지 않습니다. 자격 증명 없이는 레포지토리 데이터를 읽을 수 없습니다. 자동 시작이 활성화된 경우 부팅 시 자동 마운트를 위해 보조 LUKS 키파일이 서버에 저장됩니다.

## 설정 구조

각 설정은 `~/.config/rediacc/`에 저장된 JSON 파일입니다. 기본 설정은 `rediacc.json`이고, 명명된 설정은 이름을 파일 이름으로 사용합니다(예: `production.json`). 필드는 목적별로 구분됩니다. `resources`는 배포를, `credentials`는 시크릿을, `account`는 클라우드 기본값을, `infra`는 TLS/DNS를, `encryption`은 필드별 저장 상태를 담습니다. 최상위 `schemaVersion: 2` 판별자는 하위 호환성을 보장합니다.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**주요 버킷:**

| 버킷 | 내용 |
|---|---|
| `schemaVersion` | 판별자 (현재 `2`). 로더는 알 수 없는 버전을 거부합니다. |
| `id` / `version` | 불변 UUID + 단조 증가 카운터. 원격 설정 저장소의 낙관적 잠금에 사용됩니다. |
| `defaults.*` | 비민감 런타임 기본값(`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | 인라인 SSH 키쌍 + `knownHosts`. 레거시 `ssh.privateKeyPath`를 대체합니다(더 이상 파일 경로 간접 참조 없음. 내용은 로드 시점에 해결되어 인라인으로 저장됩니다). |
| `credentials.cfDnsApiToken` | Cloudflare DNS-01 ACME 토큰. |
| `credentials.masterPasswordVerifier` | `encryption.mode === "master-password"`인 경우에만 존재합니다. |
| `resources.machines.*` | 머신별 SSH 연결 세부 정보. |
| `resources.storages.*` | rclone 호환 오프사이트 백업 자격 증명. |
| `resources.repositories.*` | 레포별 GUID + LUKS 자격 증명 + 샌드박스 격리 에이전트 접근을 위한 SSH 키. |
| `infra.acmeCertCache.*` | 캐시된 Traefik acme.json, gzip+base64, 도메인별 키. |
| `encryption.mode` | `"plaintext"` (기본값) 또는 `"master-password"`. |
| `encryption.encryptedFields` | 암호화된 경우 포인터별 AES-GCM 블롭 맵(`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). 세션당 한 번의 잠금 해제 프롬프트로 필드를 읽을 때 복호화됩니다. |
| `remote` | 설정이 암호화된 설정 저장소에 동기화된 경우에만 존재합니다. [암호화된 설정 저장소](/en/docs/config-storage)를 참조하세요. |

**`vim` 대신 CLI로 안전하게 편집하세요:**

```bash
# 포인터 주소 단일 필드 편집 (민감 경로는 지식 게이트 적용)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# 리댁션 JSONC 프로젝션을 통한 전체 편집기 (사람 전용)
rdc config edit

# 스크립트와 에이전트에게 안전한 읽기 전용 JSONC 덤프
rdc config edit --dump

# 감사 로그의 모든 변경, 거부, reveal 검사
rdc config audit log --since 24h
rdc config audit verify
```

> 이 파일에는 민감한 데이터(SSH 개인 키, LUKS 자격 증명, Cloudflare 토큰)가 포함되어 있습니다. `0600` 권한(소유자 읽기/쓰기 전용)으로 저장됩니다. 공유하거나 버전 관리에 커밋하지 마세요. `rdc` 명령어가 파일을 읽을 때 민감 필드는 [기본적으로 리댁션됩니다](/en/docs/ai-agents-safety). 평문은 대화형 사람 TTY에서 `--reveal`을 사용해야만 나타납니다.

### 봉투 v2와 서버 측 강제

설정이 [암호화된 설정 저장소](/en/docs/config-storage)에 동기화되면 CLI는 각 민감 필드를 필드별 HMAC 커밋으로 래핑하고 해당 커밋을 평문 봉투에 담습니다. 서버는 16진수 다이제스트만 봅니다. 값은 절대 보지 않지만 모든 쓰기에 지식 게이트를 적용할 수 있습니다.

- **전제 조건 확인**: `PUT /configs/<id>`에서 클라이언트는 변경하려는 경로에 대해 알고 있다고 주장하는 다이제스트를 제출합니다. 서버는 저장된 봉투의 커밋과 비교합니다. 불일치 시 `mismatchedPaths`와 함께 `409 precondition_failed`. 영지식: 서버는 평문을 볼 수 없습니다.
- **다운그레이드 방지**: 새 봉투는 이전 봉투가 커밋한 모든 민감 경로를 커밋해야 합니다. 에이전트는 향후 전제 조건을 우회하기 위해 커밋에서 경로를 제거할 수 없습니다.
- **봉투 버전 고정**: 서버는 `envelopeVersion: 2`가 없는 봉투를 `400 unsupported_envelope_version`으로 거부합니다. 이중 수락 창 없음.
- **필드별 저장 암호화** (CLI 측): `encryption.mode === "master-password"`인 경우 각 시크릿은 마스터 패스워드로 키가 지정된 개별 AES-GCM 블롭이 됩니다. 명령어가 실제로 시크릿을 건드리지 않는 한 읽기 시 프롬프트가 트리거되지 않습니다(따라서 `rdc machine list`는 프롬프트 없이 실행됩니다).

커밋 키(FCK)는 `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")`를 통해 설정별 솔트와 함께 클라이언트 측에서 CEK로부터 파생됩니다. `fckSalt`를 교체하면 모든 이전 커밋이 무효화되어 전체 재계산이 강제됩니다. CEK를 교체할 때 유용합니다.
