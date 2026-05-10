---
title: 시스템 요구 사항
description: Rediacc 실행을 위한 시스템 요구 사항 및 지원 플랫폼.
category: Guides
order: 0
language: ko
---

# 시스템 요구 사항

Rediacc로 배포하기 전에 워크스테이션과 원격 서버가 아래 요구 사항을 충족하는지 확인하십시오.

## 워크스테이션 (컨트롤 플레인)

`rdc` CLI는 워크스테이션에서 실행되며, SSH를 통해 원격 서버를 오케스트레이션합니다.

| 플랫폼 | 최소 버전 | 비고 |
|--------|----------|------|
| macOS | 12 (Monterey) 이상 | Intel 및 Apple Silicon 지원 |
| Linux (x86_64) | 최신 배포판 | glibc 2.31 이상 (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10 이상 | PowerShell 설치 프로그램을 통한 네이티브 지원 |

**추가 요구 사항:**
- SSH 키 쌍 (예: `~/.ssh/id_ed25519` 또는 `~/.ssh/id_rsa`)
- SSH 포트(기본값: 22)로 원격 서버에 대한 네트워크 접근

## 원격 서버 (데이터 플레인)

`renet` 바이너리는 원격 서버에서 루트 권한으로 실행됩니다. 암호화된 디스크 이미지, 격리된 Docker 데몬, 서비스 오케스트레이션을 관리합니다.

어떤 바이너리를 사용해야 할지 모를 경우 [rdc vs renet](/en/docs/rdc-vs-renet)을 참조하십시오. 간단히 말하면, 일반적인 작업에는 `rdc`를 사용하고, 고급 원격 작업에만 직접 `renet`을 사용하십시오.

### 지원 운영 체제

원격 서버는 `renet` 바이너리를 실행하고, 암호화된 저장소별 Docker 데몬을 호스팅합니다. 다음 5개 배포판은 모든 풀 리퀘스트에서 CI의 Bridge Workers 매트릭스에 의해 검증되며, 공식적으로 지원되는 유일한 배포판입니다.

| OS | 버전 | 기본 커널 | 비고 |
|----|------|----------|------|
| Ubuntu | 24.04 LTS | 6.8 | 권장. AppArmor 기본 활성화. |
| Debian | 13 (Trixie) | 6.12 | Debian 12도 지원 (커널 6.1 이상 필요). |
| Fedora | 43 | 6.12 | SELinux enforcing 기본 설정. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor 기본 활성화. |
| Oracle Linux | 10 | UEK 7+ | UEK 사용으로 btrfs 모듈 유지. SELinux enforcing 기본 설정. 아래 "UEK를 사용하는 이유" 참조. |

모든 행은 `x86_64`입니다. `arm64`는 빌드되지만 모든 서버 OS에 대해 지속적으로 테스트되지는 않습니다. 특정 배포판에서 필요하다면 이슈를 제출하십시오. systemd, Docker 지원, cryptsetup이 있는 다른 Linux 배포판은 작동할 수 있지만 공식 지원되지 않으며, 업그레이드 시 예고 없이 작동이 중단될 수 있습니다.

#### UEK를 사용하는 이유 (그리고 Rocky 10 / 기본 RHEL 10이 지원되지 않는 이유)

Rediacc의 암호화 스토리지 백엔드는 인트리 `btrfs` 커널 모듈이 필요합니다. **RHEL 10의 기본 커널에는 이 모듈이 포함되어 있지 않습니다.** `modprobe btrfs`는 "Module btrfs not found"로 실패하고 `dnf search btrfs`는 아무것도 반환하지 않습니다. Rocky Linux 10과 AlmaLinux 10은 동일한 커널을 상속하므로 Rediacc 서버로 실행할 수 없습니다.

Oracle Linux 10은 기본적으로 **Unbreakable Enterprise Kernel(UEK)**을 사용하며, btrfs가 내장되어 있습니다. 이것이 지원 목록에서 유일한 RHEL 호환 대상입니다. RHEL 계열 서버를 반드시 실행해야 한다면 UEK가 포함된 Oracle Linux 10을 사용하십시오. (이 결정의 근거는 `.github/workflows/ct-tests.yml`의 CI Bridge Workers 매트릭스에 있습니다.)

#### 워크스테이션 전용 (CLI 설치 대상)

`rdc` CLI는 Alpine 3.19 이상(APK와 `gcompat` 호환 레이어, 자동 설치됨) 및 Arch Linux(rolling, pacman을 통해)에서도 정상적으로 설치됩니다. 이는 클라이언트 측 설치 경로 전용입니다([설치](/en/docs/installation) 참조). `renet` 서버 대상으로는 지원되지 않습니다.

### OS별 보안 정책

저장소별 Docker 데몬과 저장소 컨테이너 자체는 모든 지원 OS에서 **기본 컨테이너 레이블**로 실행됩니다. `rdc config machine setup`은 사용자 정의 SELinux 정책이나 AppArmor 프로파일을 설치하지 않습니다. OS별 동작:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor가 기본적으로 활성화됩니다. 기본 docker-container 프로파일이 적용되며, 추가 설정이 필요하지 않습니다.
- **Fedora 43, Oracle Linux 10**: SELinux가 enforcing 모드로 실행됩니다. 저장소별 데몬은 컨테이너에 표준 `container_t` 컨텍스트를 레이블링합니다. 사용자 정의 SELinux 정책은 필요하지 않습니다.
- **CRIU**(체크포인트/복원)는 AppArmor 프로파일을 `apparmor=unconfined`로 우회하는 유일한 경우입니다. 업스트림 CRIU의 AppArmor 지원이 아직 안정적이지 않기 때문입니다. [Rediacc 규칙](/en/docs/rules-of-rediacc)의 CRIU 노트를 참조하십시오.

설정 단계에서 SELinux AVC 거부 또는 AppArmor 거부가 발생하면 [문제 해결](/en/docs/troubleshooting) → 배포판별 설정 문제를 참조하십시오.

### 서버 사전 요구 사항

- `sudo` 권한이 있는 사용자 계정 (패스워드 없는 sudo 권장)
- `~/.ssh/authorized_keys`에 추가된 SSH 공개 키
- 최소 20 GB의 여유 디스크 공간 (워크로드에 따라 더 필요할 수 있음)
- Docker 이미지 pull을 위한 인터넷 접근 (또는 프라이빗 레지스트리)

### 자동으로 설치되는 항목

`rdc config machine setup` 명령은 원격 서버에 다음을 설치합니다.

- **Docker** 및 **containerd** (컨테이너 런타임)
- **cryptsetup** (LUKS 디스크 암호화)
- **renet** 바이너리 (SFTP를 통해 업로드)

이들을 수동으로 설치할 필요가 없습니다.

## 로컬 가상 머신 (선택 사항)

`rdc ops`를 사용하여 로컬에서 배포를 테스트하려면 워크스테이션에 가상화 지원이 필요합니다. Linux의 경우 KVM, macOS의 경우 QEMU가 필요합니다. 설정 단계와 플랫폼 세부 정보는 [실험적 VM](/en/docs/experimental-vms) 가이드를 참조하십시오.
