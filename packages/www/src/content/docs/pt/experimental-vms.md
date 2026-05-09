---
title: "VMs Experimentais"
description: "Provisione clusters de VMs locais para desenvolvimento e testes com rdc ops, sem necessidade de fornecedores externos de nuvem. Configuração rápida e isolada."
category: "Concepts"
order: 2
language: pt
---

# VMs Experimentais

Provisione clusters de VMs locais na sua estação de trabalho para desenvolvimento e testes -- sem necessidade de fornecedores de cloud externos.

## Requisitos

`rdc ops` requer o **adaptador local**. Não está disponível com o adaptador cloud.

```bash
rdc ops check
```

## Visão Geral

Os comandos `rdc ops` permitem criar e gerir clusters de VMs experimentais localmente. Esta é a mesma infraestrutura utilizada pelo pipeline CI para testes de integração, agora disponível para experimentação prática.

Casos de uso:
- Testar deployments Rediacc sem fornecedores externos de VM (Linode, Vultr, etc.)
- Desenvolver e depurar configurações de repositório localmente
- Aprender a plataforma num ambiente totalmente isolado
- Executar testes de integração na sua estação de trabalho

## Suporte de Plataforma

| Plataforma | Arquitetura | Backend | Estado |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Testado em CI |
| macOS | Intel | QEMU + HVF | Testado em CI |
| Linux | ARM64 | KVM (libvirt) | Suportado (não testado em CI) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Suportado (não testado em CI) |
| Windows | x86_64 / ARM64 | Hyper-V | Planeado |

**Linux (KVM)** utiliza libvirt para virtualização de hardware nativa com rede em bridge.

**macOS (QEMU)** utiliza QEMU com a Framework Hypervisor da Apple (HVF) para desempenho quase nativo, com rede em modo utilizador e reencaminhamento de portas SSH.

O suporte a **Windows (Hyper-V)** está planeado. Consulte a [issue #380](https://github.com/rediacc/console/issues/380) para detalhes. Requer Windows Pro/Enterprise.

## Pré-requisitos e Configuração

### Linux

```bash
# Instalar pré-requisitos automaticamente
rdc ops setup

# Ou manualmente:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Instalar pré-requisitos automaticamente
rdc ops setup

# Ou manualmente:
brew install qemu cdrtools
```

### Verificar Configuração

```bash
rdc ops check
```

Este comando executa verificações específicas da plataforma e reporta aprovação/falha para cada pré-requisito.

## Início Rápido

```bash
# 1. Verificar pré-requisitos
rdc ops check

# 2. Provisionar um cluster mínimo (bridge + 1 worker)
rdc ops up --basic

# 3. Verificar estado das VMs
rdc ops status

# 4. Aceder via SSH à VM bridge
rdc ops ssh --vm-id 1

# 4b. Ou executar um comando diretamente
rdc ops ssh --vm-id 1 -c hostname

# 5. Desligar
rdc ops down
```

## Composição do Cluster

Por defeito, `rdc ops up` provisiona:

| VM | ID | Função |
|----|-----|------|
| Bridge | 1 | Nó principal, executa o serviço bridge da Rediacc |
| Worker 1 | 11 | Nó worker para deployments de repositório |
| Worker 2 | 12 | Nó worker para deployments de repositório |

Use o flag `--basic` para provisionar apenas a bridge e o primeiro worker (IDs 1 e 11).

Use `--skip-orchestration` para provisionar VMs sem iniciar os serviços Rediacc, útil para testar a camada de VM em isolamento.

## Configuração

A VM bridge utiliza valores predefinidos menores do que as VMs worker:

| Função da VM | CPUs | RAM | Disco |
|---------|------|-----|------|
| Bridge | 1 | 1024 MB | 8 GB |
| Worker | 2 | 4096 MB | 16 GB |

As variáveis de ambiente substituem os recursos das VMs worker:

| Variável | Predefinição | Descrição |
|----------|---------|-------------|
| `VM_CPU` | 2 | Núcleos de CPU por VM worker |
| `VM_RAM` | 4096 | RAM em MB por VM worker |
| `VM_DSK` | 16 | Tamanho do disco em GB por VM worker |
| `VM_NET_BASE` | 192.168.111 | Base de rede (apenas KVM) |
| `RENET_DATA_DIR` | ~/.renet | Diretório de dados para discos e configuração de VM |

## Referência de Comandos

| Comando | Descrição |
|---------|-------------|
| `rdc ops setup` | Instalar pré-requisitos da plataforma (KVM ou QEMU) |
| `rdc ops check` | Verificar se os pré-requisitos estão instalados e a funcionar |
| `rdc ops up [options]` | Provisionar cluster de VMs |
| `rdc ops down` | Destruir todas as VMs e limpar |
| `rdc ops status` | Mostrar estado de todas as VMs |
| `rdc ops ssh --vm-id <id> [command...]` | Aceder via SSH a uma VM ou executar um comando nela |

### Opções de `rdc ops up`

| Opção | Descrição |
|--------|-------------|
| `--basic` | Cluster mínimo (bridge + 1 worker) |
| `--lite` | Ignorar provisionamento de VM (apenas chaves SSH) |
| `--force` | Forçar recriação de VMs existentes |
| `--parallel` | Provisionar VMs em paralelo |
| `--skip-orchestration` | Apenas VMs, sem serviços Rediacc |
| `--backend <kvm\|qemu>` | Substituir o backend detetado automaticamente |
| `--os <name>` | Imagem do SO (predefinição: ubuntu-24.04) |
| `--debug` | Saída detalhada |

## Diferenças de Plataforma

### Linux (KVM)
- Utiliza libvirt para gestão do ciclo de vida das VMs
- Rede em bridge, as VMs obtêm IPs numa rede virtual (192.168.111.x)
- SSH direto para os IPs das VMs
- Requer `/dev/kvm` e o serviço libvirtd

### macOS (QEMU + HVF)
- Utiliza processos QEMU geridos via ficheiros PID
- Rede em modo utilizador com reencaminhamento de portas SSH (localhost:222XX)
- SSH através de portas reencaminhadas, não IPs diretos
- ISOs cloud-init criados via `mkisofs`

## Resolução de Problemas

### Modo de depuração

Adicione `--debug` a qualquer comando para saída detalhada:

```bash
rdc ops up --basic --debug
```

### Problemas comuns

**KVM não disponível (Linux)**
- Verifique se `/dev/kvm` existe: `ls -la /dev/kvm`
- Ative a virtualização no BIOS/UEFI
- Carregue o módulo do kernel: `sudo modprobe kvm_intel` ou `sudo modprobe kvm_amd`

**libvirtd não está a executar (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU não encontrado (macOS)**
```bash
brew install qemu cdrtools
```

**As VMs não arrancam**
- Verifique o espaço em disco em `~/.renet/disks/`
- Execute `rdc ops check` para verificar todos os pré-requisitos
- Tente `rdc ops down` e depois `rdc ops up --force`
