---
title: "GPU"
description: "Dar a un repo acceso a una GPU mediante una concesión de dispositivo CDI: listar las GPU de la máquina, conceder y revocar dispositivos por repo, reservar una tarjeta en exclusiva y trabajar en WSL."
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: es
sourceHash: "1eeb1e646bd914d2"
sourceCommit: "80854ab96b06bee39cceae6b259e9efbc342f93a"
---

# GPU

Un repo solo llega a una GPU mediante una **concesión de dispositivo**. La máquina publica las GPU que tiene como dispositivos con nombre, y un operador concede a un repo los nombres que puede usar. Un repo sin concesión no recibe ninguna GPU, y un [fork](/es/docs/repositories) empieza sin concesión aunque su repo de origen la tenga.

Los nombres siguen el Container Device Interface (CDI), el estándar con el que Docker 25 y posteriores describe un dispositivo y todo lo que un contenedor necesita para usarlo. Un nombre CDI tiene la forma `<vendor>/<class>=<device>`, por ejemplo `nvidia.com/gpu=all`.

## Qué es una concesión CDI

Cada repo ejecuta su propio demonio de Docker detrás de una puerta de API que rechaza cualquier forma de conectar hardware a un contenedor, de modo que una GPU no se alcanza con opciones de `docker run`. La concesión es la única puerta. Registra un nombre CDI exacto para un repo, y la puerta admite entonces una petición de contenedor que nombre ese dispositivo y ninguno más.

- Las concesiones surten efecto en la siguiente petición a Docker, sin reiniciar el demonio.
- Una concesión nombra exactamente un dispositivo. Conceder `nvidia.com/gpu=all` admite `nvidia.com/gpu=all` y no `nvidia.com/gpu=0`. Para dar a un repo una sola tarjeta, se concede el nombre de esa tarjeta.
- Al escribirse, una concesión se comprueba contra las especificaciones de dispositivos de la máquina, así que un nombre mal escrito se rechaza en lugar de registrarse.
- Una concesión pertenece al repo para el que se hizo. Los forks y las copias necesitan la suya.

## Preparar la máquina

`rdc machine setup <machine>` detecta las GPU de la máquina y guarda el resultado en `/etc/rediacc/gpu/inventory.json`. Cuando hay una GPU NVIDIA, el setup instala además el NVIDIA Container Toolkit y genera la especificación CDI en `/etc/cdi/nvidia.yaml`. Una máquina sin GPU recibe igualmente un archivo de inventario con listas vacías.

La instalación del toolkit se controla con la opción `--install-nvidia-toolkit` de `renet setup`:

| Valor | Comportamiento |
|---|---|
| `auto` | Se instala el toolkit cuando hay una GPU NVIDIA. Es el valor por defecto. |
| `true` | Se instala el toolkit en cualquier caso. |
| `false` | Se omite el toolkit y no se genera ninguna especificación NVIDIA. |

El setup no configura ningún runtime de contenedores, porque solo se admite `runc`. El toolkit sirve únicamente para la especificación, que se regenera en cada setup para seguir los cambios de controlador.

Dos tipos de dispositivo proceden del propio Rediacc y no necesitan espacio de usuario del fabricante, porque solo mapean nodos de dispositivo:

| Tipo | Dispositivos | Origen |
|---|---|---|
| `rediacc.io/dri` | Uno por nodo de renderizado, como `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` para una tarjeta AMD y `all` | `/dev/kfd` más el nodo de renderizado de la tarjeta |

Los dispositivos NVIDIA proceden de la especificación del toolkit: `nvidia.com/gpu=all` y un nombre por tarjeta. El cómputo AMD necesita el espacio de usuario de ROCm en la imagen del contenedor, porque el setup no instala ROCm.

## Listar las GPU

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

La tabla muestra cada GPU con su nombre, versión del controlador y memoria, la plataforma (nativa o WSL), la antigüedad del inventario y cada nombre de dispositivo CDI que se puede conceder. `-o json` imprime el inventario tal como está registrado en la máquina. Las concesiones vigentes se leen en directo desde la máquina.

## Conceder y revocar

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` es el nombre de un repo, con una máquina opcional, como `gpu-a@wsl-gpu`. Ambos comandos se pueden repetir con distintos valores de `--device`. Tras una concesión, un contenedor de ese repo arranca con el dispositivo:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

El mismo contenedor se rechaza en un repo sin la concesión, y el mensaje nombra la concesión que falta.

## Concesiones exclusivas

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Una concesión exclusiva reserva un dispositivo para un solo repo. Se rechaza cuando otro repo tiene el mismo nombre, y mientras exista, se rechaza cualquier concesión de ese nombre a otro repo. La comprobación se hace al conceder, bajo un bloqueo sobre todas las concesiones de la máquina.

Una concesión exclusiva es una reserva, no un planificador. Dos contenedores del mismo repo con la concesión siguen compartiendo la tarjeta.

## Formas rechazadas

Cualquier otra vía hacia una GPU sigue rechazada, con o sin concesión. La forma CDI sustituye a cada una.

| Rechazado | Usar en su lugar |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` en Compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` en Compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` en Compose | `devices: [nvidia.com/gpu=all]` |
| Dispositivos `/dev/dri` o `/dev/kfd` en bruto, o un bind bajo `/dev` | `rediacc.io/dri=renderD128` o `rediacc.io/amd=gpu0` |
| Reglas de cgroup de dispositivos | Una concesión CDI para el dispositivo |

Un servicio de Compose que usa un dispositivo concedido tiene este aspecto:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Añadir un grupo como `video` o `render` con `group_add` se acepta, pero no concede nada, porque el grupo no da acceso a un dispositivo que el repo no recibió.

## WSL

En WSL2, el controlador de Windows ofrece la GPU mediante `/dev/dxg` y las bibliotecas de `/usr/lib/wsl/lib`. La máquina informa su plataforma como `wsl`, y el setup genera la especificación NVIDIA en formato WSL:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

El controlador está en el lado de Windows, así que una actualización allí se recoge la próxima vez que se ejecute `rdc machine setup`. Los comandos de conceder, listar y revocar funcionan igual que en una máquina nativa.

## NVIDIA nativo

En una máquina NVIDIA nativa, el servicio `nvidia-cdi-refresh` del toolkit regenera la especificación tras una instalación, un cambio de controlador y un arranque. El setup lo apunta a `/etc/cdi/nvidia.yaml`, el único directorio de especificaciones que lee el demonio de Docker de un repo. Si `nvidia-persistenced` está en marcha, su socket se hace visible a los demonios de los repos, porque la especificación lo monta en los contenedores.
