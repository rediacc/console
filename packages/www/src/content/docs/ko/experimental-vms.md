---
title: "실험적 VM"
description: "rdc ops를 사용하여 개발 및 테스트를 위한 로컬 VM 클러스터를 프로비저닝합니다."
category: "Concepts"
order: 2
language: ko
---

# 실험적 VM

외부 클라우드 공급자 없이 워크스테이션에서 개발 및 테스트를 위한 로컬 VM 클러스터를 프로비저닝합니다.

## 요구 사항

`rdc ops`는 **로컬 어댑터**가 필요합니다. 클라우드 어댑터에서는 사용할 수 없습니다.

```bash
rdc ops check
```

## 개요

`rdc ops` 명령을 사용하면 로컬에서 실험적 VM 클러스터를 생성하고 관리할 수 있습니다. 이는 CI 파이프라인의 통합 테스트에 사용하는 것과 동일한 인프라로, 이제 직접 실험할 수 있습니다.

사용 사례:
- 외부 VM 공급자(Linode, Vultr 등) 없이 Rediacc 배포 테스트
- 로컬에서 리포지토리 설정 개발 및 디버그
- 완전히 격리된 환경에서 플랫폼 학습
- 워크스테이션에서 통합 테스트 실행

## 플랫폼 지원

| 플랫폼 | 아키텍처 | 백엔드 | 상태 |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | CI에서 테스트됨 |
| macOS | Intel | QEMU + HVF | CI에서 테스트됨 |
| Linux | ARM64 | KVM (libvirt) | 지원됨 (CI 미테스트) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | 지원됨 (CI 미테스트) |
| Windows | x86_64 / ARM64 | Hyper-V | 계획 중 |

**Linux (KVM)**은 브리지 네트워킹을 통한 네이티브 하드웨어 가상화에 libvirt를 사용합니다.

**macOS (QEMU)**는 Apple의 Hypervisor Framework(HVF)를 활용하는 QEMU를 사용하여 네이티브에 가까운 성능을 제공하며, 사용자 모드 네트워킹과 SSH 포트 포워딩을 지원합니다.

**Windows (Hyper-V)** 지원은 계획 중입니다. 자세한 내용은 [이슈 #380](https://github.com/rediacc/console/issues/380)을 참조하십시오. Windows Pro/Enterprise가 필요합니다.

## 사전 조건 및 설정

### Linux

```bash
# 사전 조건 자동 설치
rdc ops setup

# 또는 수동으로:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# 사전 조건 자동 설치
rdc ops setup

# 또는 수동으로:
brew install qemu cdrtools
```

### 설정 확인

```bash
rdc ops check
```

플랫폼별 검사를 실행하고 각 사전 조건에 대해 통과/실패를 보고합니다.

## 빠른 시작

```bash
# 1. 사전 조건 확인
rdc ops check

# 2. 최소 클러스터 프로비저닝 (브리지 + 워커 1개)
rdc ops up --basic

# 3. VM 상태 확인
rdc ops status

# 4. 브리지 VM에 SSH 접속
rdc ops ssh --vm-id 1

# 4b. 또는 명령 직접 실행
rdc ops ssh --vm-id 1 -c hostname

# 5. 종료
rdc ops down
```

## 클러스터 구성

기본적으로 `rdc ops up`은 다음을 프로비저닝합니다.

| VM | ID | 역할 |
|----|-----|------|
| 브리지 | 1 | 기본 노드, Rediacc 브리지 서비스 실행 |
| 워커 1 | 11 | 리포지토리 배포를 위한 워커 노드 |
| 워커 2 | 12 | 리포지토리 배포를 위한 워커 노드 |

`--basic` 플래그를 사용하면 브리지와 첫 번째 워커(ID 1과 11)만 프로비저닝합니다.

`--skip-orchestration`을 사용하면 Rediacc 서비스를 시작하지 않고 VM만 프로비저닝합니다. VM 레이어를 독립적으로 테스트할 때 유용합니다.

## 설정

브리지 VM은 워커 VM보다 작은 기본값을 사용합니다.

| VM 역할 | CPU | RAM | 디스크 |
|---------|------|-----|------|
| 브리지 | 1 | 1024 MB | 8 GB |
| 워커 | 2 | 4096 MB | 16 GB |

환경 변수로 워커 VM 리소스를 재정의할 수 있습니다.

| 변수 | 기본값 | 설명 |
|----------|---------|-------------|
| `VM_CPU` | 2 | 워커 VM당 CPU 코어 수 |
| `VM_RAM` | 4096 | 워커 VM당 RAM (MB) |
| `VM_DSK` | 16 | 워커 VM당 디스크 크기 (GB) |
| `VM_NET_BASE` | 192.168.111 | 네트워크 베이스 (KVM 전용) |
| `RENET_DATA_DIR` | ~/.renet | VM 디스크 및 설정의 데이터 디렉토리 |

## 명령 참조

| 명령 | 설명 |
|---------|-------------|
| `rdc ops setup` | 플랫폼 사전 조건 설치 (KVM 또는 QEMU) |
| `rdc ops check` | 사전 조건 설치 및 작동 여부 확인 |
| `rdc ops up [options]` | VM 클러스터 프로비저닝 |
| `rdc ops down` | 모든 VM 삭제 및 정리 |
| `rdc ops status` | 모든 VM의 상태 표시 |
| `rdc ops ssh --vm-id <id> [command...]` | VM에 SSH 접속하거나 명령 실행 |

### `rdc ops up` 옵션

| 옵션 | 설명 |
|--------|-------------|
| `--basic` | 최소 클러스터 (브리지 + 워커 1개) |
| `--lite` | VM 프로비저닝 건너뜀 (SSH 키만) |
| `--force` | 기존 VM 강제 재생성 |
| `--parallel` | VM 병렬 프로비저닝 |
| `--skip-orchestration` | VM만, Rediacc 서비스 없음 |
| `--backend <kvm\|qemu>` | 자동 감지된 백엔드 재정의 |
| `--os <name>` | OS 이미지 (기본값: ubuntu-24.04) |
| `--debug` | 상세 출력 |

## 플랫폼별 차이점

### Linux (KVM)
- VM 수명 주기 관리에 libvirt 사용
- 브리지 네트워킹, VM이 가상 네트워크(192.168.111.x)에서 IP 획득
- VM IP로 직접 SSH 접속
- `/dev/kvm` 및 libvirtd 서비스 필요

### macOS (QEMU + HVF)
- PID 파일로 관리되는 QEMU 프로세스 사용
- SSH 포트 포워딩을 통한 사용자 모드 네트워킹(localhost:222XX)
- 직접 IP가 아닌 포워딩된 포트를 통한 SSH
- `mkisofs`를 통해 생성된 Cloud-init ISO

## 문제 해결

### 디버그 모드

자세한 출력을 위해 모든 명령에 `--debug`를 추가하십시오.

```bash
rdc ops up --basic --debug
```

### 일반적인 문제

**KVM을 사용할 수 없음 (Linux)**
- `/dev/kvm` 존재 여부 확인: `ls -la /dev/kvm`
- BIOS/UEFI에서 가상화 활성화
- 커널 모듈 로드: `sudo modprobe kvm_intel` 또는 `sudo modprobe kvm_amd`

**libvirtd가 실행 중이 아님 (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU를 찾을 수 없음 (macOS)**
```bash
brew install qemu cdrtools
```

**VM이 시작되지 않음**
- `~/.renet/disks/`의 디스크 공간 확인
- `rdc ops check`를 실행하여 모든 사전 조건 확인
- `rdc ops down` 후 `rdc ops up --force` 시도
