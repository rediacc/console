---
title: "GPU"
description: "CDI 장치 권한으로 리포지토리에 GPU 접근을 부여하는 방법입니다. 머신의 GPU 목록 확인, 리포지토리별 장치 부여와 회수, 카드 단독 예약, WSL 사용을 다룹니다."
category: "Guides"
tags:
  - gpu
  - containers
subcategory: workloads
order: 7
language: ko
sourceHash: "5a113ad69c52c63d"
---

# GPU

리포지토리는 **장치 권한**을 통해서만 GPU에 접근합니다. 머신은 가진 GPU를 이름 붙은 장치로 공개하고, 운영자는 리포지토리가 쓸 수 있는 이름을 부여합니다. 권한이 없는 리포지토리는 GPU를 받지 못하며, [포크](/ko/docs/repositories)는 부모에게 권한이 있어도 권한 없이 시작합니다.

이름은 Container Device Interface(CDI)를 따릅니다. CDI는 Docker 25 이상이 장치와, 컨테이너가 그 장치를 쓰는 데 필요한 모든 것을 기술하는 표준입니다. CDI 이름은 `<vendor>/<class>=<device>` 형식이며, 예를 들면 `nvidia.com/gpu=all`입니다.

## CDI 권한이란

각 리포지토리는 컨테이너에 하드웨어를 연결하는 모든 방법을 거부하는 API 게이트 뒤에서 자체 Docker 데몬을 실행합니다. 따라서 `docker run` 플래그로는 GPU에 접근할 수 없습니다. 권한이 유일한 통로입니다. 권한은 한 리포지토리에 대해 정확한 CDI 이름을 기록하고, 게이트는 그 장치만 지정하는 컨테이너 요청을 허용합니다.

- 권한은 다음 Docker 요청부터 적용되며 데몬을 재시작할 필요가 없습니다.
- 권한은 정확히 하나의 장치를 지정합니다. `nvidia.com/gpu=all`을 부여하면 `nvidia.com/gpu=all`만 허용되고 `nvidia.com/gpu=0`은 허용되지 않습니다. 리포지토리에 카드 한 장만 주려면 그 카드의 이름을 부여합니다.
- 권한은 기록할 때 머신의 장치 사양과 대조되므로, 철자가 틀린 이름은 기록되지 않고 거부됩니다.
- 권한은 부여받은 리포지토리에 속합니다. 포크와 복사본에는 각자의 권한이 필요합니다.

## 머신 설정

`rdc machine setup <machine>`은 머신의 GPU를 감지하고 결과를 `/etc/rediacc/gpu/inventory.json`에 기록합니다. NVIDIA GPU가 있으면 설정이 NVIDIA Container Toolkit도 설치하고 CDI 사양을 `/etc/cdi/nvidia.yaml`에 생성합니다. GPU가 없는 머신도 빈 목록이 담긴 인벤토리 파일을 받습니다.

툴킷 설치는 `renet setup`의 `--install-nvidia-toolkit` 옵션으로 제어합니다.

| 값 | 동작 |
|---|---|
| `auto` | NVIDIA GPU가 있으면 툴킷을 설치합니다. 기본값입니다. |
| `true` | 항상 툴킷을 설치합니다. |
| `false` | 툴킷을 건너뛰고 NVIDIA 사양을 생성하지 않습니다. |

허용되는 것은 `runc`뿐이므로 설정은 컨테이너 런타임을 구성하지 않습니다. 툴킷은 사양을 만드는 데만 쓰이며, 사양은 드라이버 변경을 따라가도록 설정 때마다 다시 생성됩니다.

두 종류의 장치는 Rediacc 자체에서 제공하며, 장치 노드만 매핑하므로 벤더의 사용자 공간 구성 요소가 필요 없습니다.

| 종류 | 장치 | 출처 |
|---|---|---|
| `rediacc.io/dri` | 렌더 노드마다 하나, 예: `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | AMD 카드 한 장당 `gpu<N>`과 `all` | `/dev/kfd`와 해당 카드의 렌더 노드 |

NVIDIA 장치는 툴킷의 사양에서 나옵니다. `nvidia.com/gpu=all`과 카드마다 하나의 이름입니다. AMD 컴퓨팅에는 컨테이너 이미지 안의 ROCm 사용자 공간이 필요합니다. 설정은 ROCm을 설치하지 않습니다.

## GPU 목록 보기

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

표에는 각 GPU의 이름, 드라이버 버전, 메모리, 플랫폼(네이티브 또는 WSL), 인벤토리의 경과 시간, 부여할 수 있는 모든 CDI 장치 이름이 나옵니다. `-o json`은 머신에 기록된 그대로 인벤토리를 출력합니다. 현재 유효한 권한은 머신에서 실시간으로 읽습니다.

## 부여와 회수

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>`는 `gpu-a@wsl-gpu`처럼 머신을 붙일 수 있는 리포지토리 이름입니다. 두 명령 모두 다른 `--device` 값으로 반복할 수 있습니다. 권한을 부여한 뒤에는 해당 리포지토리의 컨테이너가 장치와 함께 시작됩니다.

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

권한이 없는 리포지토리에서는 같은 컨테이너가 거부되며, 메시지에 빠진 권한이 표시됩니다.

## 단독 권한

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

단독 권한은 장치를 한 리포지토리 전용으로 예약합니다. 다른 리포지토리가 같은 이름을 갖고 있으면 거부되고, 단독 권한이 유지되는 동안에는 그 이름을 다른 리포지토리에 부여하는 것도 거부됩니다. 이 확인은 부여 시점에 머신의 모든 권한에 걸린 잠금 아래에서 수행됩니다.

단독 권한은 예약일 뿐 스케줄러가 아닙니다. 권한을 받은 같은 리포지토리의 컨테이너 두 개는 여전히 카드를 공유합니다.

## 거부되는 표기

GPU에 접근하는 다른 모든 경로는 권한이 있든 없든 거부된 상태로 유지됩니다. CDI 형식이 각각을 대신합니다.

| 거부됨 | 대신 사용 |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| Compose의 `runtime: nvidia` | `devices: [nvidia.com/gpu=all]` |
| Compose의 `deploy.resources.reservations.devices` | `devices: [nvidia.com/gpu=all]` |
| Compose의 `gpus: all` | `devices: [nvidia.com/gpu=all]` |
| 원시 `/dev/dri` 또는 `/dev/kfd` 장치, 혹은 `/dev` 아래의 bind | `rediacc.io/dri=renderD128` 또는 `rediacc.io/amd=gpu0` |
| 장치 cgroup 규칙 | 해당 장치에 대한 CDI 권한 |

부여된 장치를 사용하는 Compose 서비스는 다음과 같습니다.

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

`group_add`로 `video`나 `render` 같은 그룹을 추가하는 것은 허용되지만 아무것도 부여하지 않습니다. 그룹은 리포지토리가 받지 않은 장치에 대한 접근을 열어 주지 않기 때문입니다.

## WSL

WSL2에서는 Windows 드라이버가 `/dev/dxg`와 `/usr/lib/wsl/lib` 아래의 라이브러리를 통해 GPU를 제공합니다. 머신은 플랫폼을 `wsl`로 보고하며, 설정은 NVIDIA 사양을 WSL 형식으로 생성합니다.

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

드라이버는 Windows 쪽에 있으므로, 거기서 한 업데이트는 다음 `rdc machine setup` 실행 때 반영됩니다. 부여, 목록 보기, 회수 명령은 네이티브 머신과 똑같이 동작합니다.

## 네이티브 NVIDIA

네이티브 NVIDIA 머신에서는 툴킷의 `nvidia-cdi-refresh` 서비스가 설치, 드라이버 변경, 부팅 후에 사양을 다시 생성합니다. 설정은 이 서비스가 리포지토리의 Docker 데몬이 읽는 유일한 사양 디렉터리인 `/etc/cdi/nvidia.yaml`을 가리키게 합니다. `nvidia-persistenced`가 실행 중이면, 사양이 그 소켓을 컨테이너에 마운트하므로 소켓이 리포지토리 데몬에 보이도록 만듭니다.
