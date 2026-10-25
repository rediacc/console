---
title: "GPU"
description: "Dar a um repo acesso a uma GPU por meio de uma concessão de dispositivo CDI: listar as GPUs da máquina, conceder e revogar dispositivos por repo, reservar uma placa com exclusividade e trabalhar no WSL."
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: pt
sourceHash: "1eeb1e646bd914d2"
sourceCommit: "80854ab96b06bee39cceae6b259e9efbc342f93a"
---

# GPUs

Um repo só alcança uma GPU por meio de uma **concessão de dispositivo**. A máquina publica as GPUs que tem como dispositivos nomeados, e um operador concede a um repo os nomes que ele pode usar. Um repo sem concessão não recebe GPU nenhuma, e um [fork](/pt/docs/repositories) começa sem concessão mesmo que o repo de origem tenha uma.

Os nomes seguem o Container Device Interface (CDI), o padrão que o Docker 25 e posteriores usa para descrever um dispositivo e tudo de que um contêiner precisa para usá-lo. Um nome CDI tem a forma `<vendor>/<class>=<device>`, por exemplo `nvidia.com/gpu=all`.

## O que é uma concessão CDI

Cada repo executa o próprio daemon do Docker atrás de um portão de API que recusa qualquer forma de ligar hardware a um contêiner, então uma GPU não é alcançada com opções do `docker run`. A concessão é a única porta. Ela registra um nome CDI exato para um repo, e o portão então admite uma requisição de contêiner que nomeie esse dispositivo e nenhum outro.

- As concessões valem a partir da próxima requisição ao Docker, sem reiniciar o daemon.
- Uma concessão nomeia exatamente um dispositivo. Conceder `nvidia.com/gpu=all` admite `nvidia.com/gpu=all` e não `nvidia.com/gpu=0`. Para dar a um repo uma única placa, concede-se o nome dessa placa.
- Ao ser gravada, a concessão é conferida com as especificações de dispositivos da máquina, de modo que um nome digitado errado é recusado em vez de registrado.
- Uma concessão pertence ao repo para o qual foi feita. Forks e cópias precisam da sua.

## Preparar a máquina

`rdc machine setup <machine>` detecta as GPUs da máquina e registra o resultado em `/etc/rediacc/gpu/inventory.json`. Quando há uma GPU NVIDIA, o setup também instala o NVIDIA Container Toolkit e gera a especificação CDI em `/etc/cdi/nvidia.yaml`. Uma máquina sem GPU ainda recebe um arquivo de inventário, com listas vazias.

A instalação do toolkit é controlada pela opção `--install-nvidia-toolkit` do `renet setup`:

| Valor | Comportamento |
|---|---|
| `auto` | O toolkit é instalado quando há uma GPU NVIDIA. É o padrão. |
| `true` | O toolkit é instalado em qualquer caso. |
| `false` | O toolkit é ignorado e nenhuma especificação NVIDIA é gerada. |

O setup não configura nenhum runtime de contêiner, porque só o `runc` é admitido. O toolkit serve apenas à especificação, regenerada a cada setup para acompanhar mudanças de driver.

Dois tipos de dispositivo vêm do próprio Rediacc e dispensam o espaço de usuário do fabricante, porque só mapeiam nós de dispositivo:

| Tipo | Dispositivos | Origem |
|---|---|---|
| `rediacc.io/dri` | Um por nó de renderização, como `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` para uma placa AMD e `all` | `/dev/kfd` mais o nó de renderização da placa |

Os dispositivos NVIDIA vêm da especificação do toolkit: `nvidia.com/gpu=all` e um nome por placa. A computação AMD precisa do espaço de usuário do ROCm na imagem do contêiner, pois o setup não instala o ROCm.

## Listar as GPUs

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

A tabela mostra cada GPU com nome, versão do driver e memória, a plataforma (nativa ou WSL), a idade do inventário e cada nome de dispositivo CDI que pode ser concedido. `-o json` imprime o inventário como está registrado na máquina. As concessões em vigor são lidas ao vivo da máquina.

## Conceder e revogar

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` é o nome de um repo, opcionalmente com a máquina, como `gpu-a@wsl-gpu`. Os dois comandos podem ser repetidos com valores diferentes de `--device`. Depois de uma concessão, um contêiner desse repo inicia com o dispositivo:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

O mesmo contêiner é recusado em um repo sem a concessão, e a mensagem nomeia a concessão ausente.

## Concessões exclusivas

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Uma concessão exclusiva reserva um dispositivo para um único repo. Ela é recusada quando outro repo detém o mesmo nome, e enquanto existir, qualquer concessão desse nome a outro repo é recusada. A verificação ocorre no momento da concessão, sob um bloqueio sobre todas as concessões da máquina.

Uma concessão exclusiva é uma reserva, não um escalonador. Dois contêineres do mesmo repo com a concessão continuam compartilhando a placa.

## Formas recusadas

Qualquer outro caminho até uma GPU continua recusado, com ou sem concessão. A forma CDI substitui cada um deles.

| Recusado | Usar no lugar |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` no Compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` no Compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` no Compose | `devices: [nvidia.com/gpu=all]` |
| Dispositivos `/dev/dri` ou `/dev/kfd` brutos, ou um bind sob `/dev` | `rediacc.io/dri=renderD128` ou `rediacc.io/amd=gpu0` |
| Regras de cgroup de dispositivos | Uma concessão CDI para o dispositivo |

Um serviço do Compose que usa um dispositivo concedido tem este aspecto:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Adicionar um grupo como `video` ou `render` com `group_add` é aceito, mas não concede nada, pois o grupo não dá acesso a um dispositivo que o repo não recebeu.

## WSL

No WSL2, o driver do Windows fornece a GPU por `/dev/dxg` e pelas bibliotecas em `/usr/lib/wsl/lib`. A máquina informa sua plataforma como `wsl`, e o setup gera a especificação NVIDIA no formato WSL:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

O driver fica no lado do Windows, então uma atualização lá é incorporada na próxima execução de `rdc machine setup`. Os comandos de conceder, listar e revogar funcionam como em uma máquina nativa.

## NVIDIA nativo

Em uma máquina NVIDIA nativa, o serviço `nvidia-cdi-refresh` do toolkit regenera a especificação após uma instalação, uma mudança de driver e uma inicialização. O setup o aponta para `/etc/cdi/nvidia.yaml`, o único diretório de especificações que o daemon do Docker de um repo lê. Quando o `nvidia-persistenced` está em execução, seu socket é tornado visível aos daemons dos repos, porque a especificação o monta nos contêineres.
