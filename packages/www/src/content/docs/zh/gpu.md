---
title: "GPU"
description: "通过 CDI 设备授权让仓库使用 GPU：列出机器上的 GPU，按仓库授予和撤销设备，独占预留一张显卡，以及在 WSL 上使用。"
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: zh
sourceHash: "5a113ad69c52c63d"
---

# GPU

仓库只能通过**设备授权**使用 GPU。机器把自身的 GPU 发布为具名设备，由运维人员把仓库可以使用的名称授予它。没有授权的仓库得不到 GPU，[分叉](/zh/docs/repositories)即使其父仓库有授权，也是在没有授权的情况下启动。

名称遵循容器设备接口（CDI），这是 Docker 25 及更高版本用来描述设备以及容器使用该设备所需全部内容的标准。CDI 名称的形式为 `<vendor>/<class>=<device>`，例如 `nvidia.com/gpu=all`。

## 什么是 CDI 授权

每个仓库都在一个 API 网关之后运行自己的 Docker 守护进程，网关会拒绝一切把硬件接入容器的方式，因此无法通过 `docker run` 的参数使用 GPU。授权是唯一的入口。它为某个仓库记录一个精确的 CDI 名称，此后网关只放行指明该设备的容器请求。

- 授权从下一次 Docker 请求起生效，无需重启守护进程。
- 一项授权只指明一个设备。授予 `nvidia.com/gpu=all` 只放行 `nvidia.com/gpu=all`，不放行 `nvidia.com/gpu=0`。要给仓库单独一张卡，就授予这张卡的名称。
- 授权在写入时会对照机器上的设备规范进行检查，因此拼错的名称会被拒绝，而不会被记录。
- 授权属于它所授予的仓库。分叉和副本需要各自的授权。

## 设置机器

`rdc machine setup <machine>` 会检测机器上的 GPU，并把结果记录在 `/etc/rediacc/gpu/inventory.json`。存在 NVIDIA GPU 时，设置过程还会安装 NVIDIA Container Toolkit，并在 `/etc/cdi/nvidia.yaml` 生成 CDI 规范。没有 GPU 的机器同样会得到一个清单文件，其中的列表为空。

工具包的安装由 `renet setup` 的 `--install-nvidia-toolkit` 选项控制：

| 取值 | 行为 |
|---|---|
| `auto` | 存在 NVIDIA GPU 时安装工具包。这是默认值。 |
| `true` | 无论如何都安装工具包。 |
| `false` | 跳过工具包，也不生成 NVIDIA 规范。 |

由于只允许 `runc`，设置过程不会配置任何容器运行时。工具包仅用于生成规范，规范在每次设置时重新生成，以跟上驱动的变化。

有两类设备由 Rediacc 自身提供，它们只映射设备节点，因此不需要厂商的用户空间组件：

| 类型 | 设备 | 来源 |
|---|---|---|
| `rediacc.io/dri` | 每个渲染节点一个，例如 `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | 每张 AMD 卡的 `gpu<N>`，以及 `all` | `/dev/kfd` 加上该卡的渲染节点 |

NVIDIA 设备来自工具包的规范：`nvidia.com/gpu=all`，以及每张卡一个名称。AMD 计算需要容器镜像中带有 ROCm 用户空间，因为设置过程不安装 ROCm。

## 列出 GPU

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

表格列出每个 GPU 的名称、驱动版本和显存，平台（原生或 WSL），清单的存续时间，以及所有可以授予的 CDI 设备名称。`-o json` 按机器上的记录原样输出清单。当前有效的授权会从机器上实时读取。

## 授予与撤销

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` 是仓库名称，可以带上机器，例如 `gpu-a@wsl-gpu`。两条命令都可以用不同的 `--device` 值重复执行。授权之后，该仓库中的容器会带着设备启动：

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

同一个容器在没有授权的仓库中会被拒绝，报错信息会指出缺少的授权。

## 独占授权

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

独占授权把一个设备预留给单个仓库。如果另一个仓库已持有同名授权，它会被拒绝；独占授权存在期间，把该名称授予其他仓库也会被拒绝。检查在授予时进行，并处于覆盖机器上所有授权的锁之下。

独占授权是预留，而不是调度器。获得授权的同一个仓库中的两个容器仍然共用这张卡。

## 被拒绝的写法

通往 GPU 的其他途径无论有无授权都保持拒绝。CDI 形式可以替代其中每一种。

| 被拒绝 | 改用 |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| Compose 中的 `runtime: nvidia` | `devices: [nvidia.com/gpu=all]` |
| Compose 中的 `deploy.resources.reservations.devices` | `devices: [nvidia.com/gpu=all]` |
| Compose 中的 `gpus: all` | `devices: [nvidia.com/gpu=all]` |
| 原始的 `/dev/dri` 或 `/dev/kfd` 设备，或 `/dev` 下的 bind | `rediacc.io/dri=renderD128` 或 `rediacc.io/amd=gpu0` |
| 设备 cgroup 规则 | 针对该设备的 CDI 授权 |

使用已授权设备的 Compose 服务如下所示：

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

通过 `group_add` 添加 `video` 或 `render` 之类的组可以被接受，但不会授予任何东西，因为组并不能打开仓库未获授权的设备。

## WSL

在 WSL2 上，Windows 驱动通过 `/dev/dxg` 和 `/usr/lib/wsl/lib` 下的库提供 GPU。机器会把平台报告为 `wsl`，设置过程以 WSL 格式生成 NVIDIA 规范：

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

驱动位于 Windows 一侧，因此那里的驱动更新会在下一次运行 `rdc machine setup` 时被识别。授予、列出和撤销命令的用法与原生机器相同。

## 原生 NVIDIA

在原生 NVIDIA 机器上，工具包的 `nvidia-cdi-refresh` 服务会在安装、驱动变更和开机之后重新生成规范。设置过程把它指向 `/etc/cdi/nvidia.yaml`，这是仓库的 Docker 守护进程读取的唯一规范目录。`nvidia-persistenced` 运行时，它的套接字会对仓库守护进程可见，因为规范会把它挂载进容器。
