---
title: "GPUs"
description: "Give a repo access to a GPU through a CDI device grant: list the machine's GPUs, grant and revoke devices per repo, reserve a card exclusively, and run on WSL."
category: "Guides"
tags:
  - gpu
  - containers
subcategory: workloads
order: 7
language: en
---

# GPUs

A repo reaches a GPU only through a **device grant**. The machine publishes the GPUs it has as named devices, and an operator grants a repo the names it may use. A repo with no grant gets no GPU, and a [fork](/en/docs/repositories) starts with no grant even when its parent has one.

The names follow the Container Device Interface (CDI), the standard that Docker 25 and later uses to describe a device and everything a container needs to use it. A CDI name has the form `<vendor>/<class>=<device>`, for example `nvidia.com/gpu=all`.

## What a CDI grant is

Each repo runs its own Docker daemon behind an API gate that refuses every way of attaching hardware to a container, so a GPU cannot be reached by passing flags to `docker run`. A grant is the one door. It records an exact CDI name for one repo, and the gate then admits a container request that names that device and nothing else.

- Grants take effect on the next Docker request, with no daemon restart.
- A grant names exactly one device. Granting `nvidia.com/gpu=all` admits `nvidia.com/gpu=all` and not `nvidia.com/gpu=0`. To give a repo a single card, grant that card's name.
- A grant is checked against the device specs on the machine when it is written, so a misspelled name is refused instead of recorded.
- A grant belongs to the repo it was made for. Forks and copies need their own grant.

## Set up the machine

`rdc machine setup <machine>` detects the GPUs on the machine and records the result in `/etc/rediacc/gpu/inventory.json`. When an NVIDIA GPU is present, setup also installs the NVIDIA Container Toolkit and generates the CDI spec at `/etc/cdi/nvidia.yaml`. A machine with no GPU still gets an inventory file, with empty lists.

The toolkit install is controlled by the `renet setup` option `--install-nvidia-toolkit`:

| Value | Behavior |
|---|---|
| `auto` | Install the toolkit when an NVIDIA GPU is present. This is the default. |
| `true` | Install the toolkit regardless. |
| `false` | Skip the toolkit, and generate no NVIDIA spec. |

Setup configures no container runtime, because only `runc` is admitted. The toolkit is used for the spec alone, and the spec is regenerated on every setup so that it follows driver changes.

Two device kinds come from Rediacc itself and need no vendor userspace, because they map device nodes only:

| Kind | Devices | Source |
|---|---|---|
| `rediacc.io/dri` | One per render node, such as `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` for one AMD card and `all` | `/dev/kfd` plus the card's render node |

NVIDIA devices come from the toolkit's spec: `nvidia.com/gpu=all` and one name per card. AMD compute needs the ROCm userspace inside the container image, since setup installs no ROCm.

## List the GPUs

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

The table shows each GPU with its name, driver version and memory, the platform (native or WSL), the age of the inventory, and every CDI device name that can be granted. `-o json` prints the inventory as recorded on the machine. The grants currently held are read live from the machine.

## Grant and revoke

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` is a repo name, optionally with a machine, such as `gpu-a@wsl-gpu`. Both commands can be repeated with different `--device` values. After a grant, a container in that repo starts with the device:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

The same container in a repo without the grant is refused, and the message names the missing grant.

## Exclusive grants

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

An exclusive grant reserves a device for one repo. It is refused when another repo holds the same name, and while it stands, any other repo's grant of that name is refused. The check runs when the grant is made, under a lock over all grants on the machine.

An exclusive grant is a reservation, not a scheduler. Two containers in the one granted repo still share the card.

## Spellings that are refused

Every other way of reaching a GPU stays refused, granted or not. The CDI form replaces each one.

| Refused | Use instead |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` in compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` in compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` in compose | `devices: [nvidia.com/gpu=all]` |
| Raw `/dev/dri` or `/dev/kfd` devices, or a bind under `/dev` | `rediacc.io/dri=renderD128` or `rediacc.io/amd=gpu0` |
| Device cgroup rules | A CDI grant for the device |

A compose service that uses a granted device looks like this:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Adding a group such as `video` or `render` with `group_add` is accepted but grants nothing, since the group gives no access to a device the repo was not granted.

## WSL

On WSL2 the Windows driver provides the GPU through `/dev/dxg` and the libraries under `/usr/lib/wsl/lib`. The machine reports its platform as `wsl`, and setup generates the NVIDIA spec in WSL mode:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

The driver lives on the Windows side, so a driver update there is picked up the next time `rdc machine setup` runs. The grant, list and revoke commands work the same as on a native machine.

## Native NVIDIA

On a native NVIDIA machine the toolkit's `nvidia-cdi-refresh` service regenerates the spec after an install, a driver change and a boot. Setup points it at `/etc/cdi/nvidia.yaml`, the only spec directory a repo's Docker daemon reads. When `nvidia-persistenced` is running, its socket is made visible to the repo daemons, because the spec mounts it into containers.
