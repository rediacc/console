---
title: "rdc vs renet"
description: "Quando usar o rdc e quando usar o renet. Introdução à configuração de cada ferramenta."
category: "Concepts"
order: 1
language: pt
sourceHash: "026a183f8a5f9dd4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# rdc vs renet

O Rediacc tem dois binários. Veja quando usar cada um.

| | rdc | renet |
|---|-----|-------|
| **Executa em** | A sua estação de trabalho | O servidor remoto |
| **Liga-se via** | SSH | Executa localmente com root |
| **Usado por** | Todos | Apenas depuração avançada |
| **Instalar** | Instala-o o utilizador | `rdc` provisiona-o automaticamente |

> Para o trabalho do dia a dia, use `rdc`. Raramente precisará de `renet` diretamente.

## Como Trabalham em Conjunto

Na sua estação de trabalho executa o `rdc`. Ele abre uma ligação SSH ao servidor e executa o comando `renet` correspondente lá por si. Um comando, um sítio para o executar:

1. Lê a sua config local (`~/.config/rediacc/rediacc.json`)
2. Liga-se ao servidor via SSH
3. Atualiza o binário `renet` se necessário
4. Executa a operação `renet` correspondente no servidor
5. Devolve o resultado ao seu terminal

## Use `rdc` para o Trabalho Normal

Todas as tarefas comuns passam pelo `rdc` na sua estação de trabalho:

```bash
# Configurar um novo servidor
rdc config machine setup --name server-1

# Criar e iniciar um repositório
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# Parar um repositório
rdc repo down --name my-app -m server-1

# Verificar a saúde da máquina
rdc machine health --name server-1
```

Consulte o [Início Rápido](/pt/docs/quick-start) para um percurso completo.

## Use `renet` para Depuração no Lado do Servidor

Só precisa de `renet` diretamente quando faz SSH para um servidor para:

- Depuração de emergência quando o `rdc` não consegue ligar
- Verificar internos do sistema não disponíveis através do `rdc`
- Operações de recuperação de baixo nível

Todos os comandos `renet` precisam de privilégios de root (`sudo`). Consulte a [Referência do Servidor](/pt/docs/server-reference) para a lista completa de comandos `renet`.

## Experimental: `rdc ops` (VMs Locais)

`rdc ops` encapsula `renet ops` para gerir clusters de VM locais na sua estação de trabalho:

```bash
rdc ops setup              # Instalar pré-requisitos (KVM ou QEMU)
rdc ops up --basic         # Iniciar um cluster mínimo
rdc ops status             # Verificar estado das VMs
rdc ops ssh --vm-id 1  # SSH para a VM de ponte
rdc ops ssh --vm-id 1 -c hostname  # Executar um comando na VM de ponte
rdc ops down               # Destruir o cluster
```

> Requer o adaptador local. Não disponível com o adaptador de nuvem.

Estes comandos executam o `renet` localmente (não via SSH). Consulte [VMs Experimentais](/pt/docs/experimental-vms) para documentação completa.

## Nota sobre o Rediaccfile

Vai ver `renet compose -- ...` dentro de um `Rediaccfile`. Não se preocupe. As funções do Rediaccfile são executadas no servidor, onde o `renet` já está instalado.

A partir da sua estação de trabalho, inicie e pare cargas de trabalho com `rdc repo up` e `rdc repo down`.
