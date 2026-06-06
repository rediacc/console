---
title: Requisitos
description: Requisitos de sistema e plataformas suportadas para executar o Rediacc.
category: Guides
order: 0
language: pt
sourceHash: "e84db3bb90270473"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Requisitos

A maior parte disto é configuração padrão de servidor Linux. Alguns detalhes são específicos de como o Rediacc funciona, portanto, verifique-os antes de começar.

## Computador de Trabalho (Plano de Controlo)

O CLI `rdc` é executado no seu computador de trabalho e orquestra servidores remotos via SSH.

| Plataforma | Versão Mínima | Notas |
|------------|---------------|-------|
| macOS | 12 (Monterey)+ | Intel e Apple Silicon suportados |
| Linux (x86_64) | Qualquer distribuição moderna | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Suporte nativo via instalador PowerShell |

**Requisitos adicionais:**
- Um par de chaves SSH (por exemplo, `~/.ssh/id_ed25519` ou `~/.ssh/id_rsa`)
- Acesso de rede aos servidores remotos na porta SSH (padrão: 22)

## Servidor Remoto (Plano de Dados)

O binário `renet` é executado em servidores remotos com privilégios de raiz. Gerencia imagens de disco encriptadas, daemons Docker isolados e orquestração de serviços.

Se não tiver a certeza de qual binário usar, consulte [rdc vs renet](/pt/docs/rdc-vs-renet). Em resumo: use `rdc` para operações normais e use `renet` diretamente apenas para tarefas avançadas do lado do servidor.

### Sistemas Operativos Suportados

Os servidores remotos executam o binário `renet` e alojam os daemons Docker encriptados por repositório. As cinco distribuições seguintes são exercidas pela matriz Bridge Workers em CI em cada pull request e são as únicas com suporte oficial:

| SO | Versão | Kernel Padrão | Notas |
|----|--------|---------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Recomendado. AppArmor ativado por padrão. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 também funciona (kernel 6.1 mínimo). |
| Fedora | 43 | 6.12 | SELinux em modo enforcing por padrão. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor ativado por padrão. |
| Oracle Linux | 10 | UEK 7+ | Usa UEK, que mantém o módulo btrfs. SELinux em modo enforcing por padrão. Consulte "Por que UEK?" abaixo. |

Todas as entradas são `x86_64`. `arm64` é compilado mas não continuamente testado para todos os SOs de servidor; abra uma issue se precisar dele numa distribuição específica. Outras distribuições Linux com systemd, suporte a Docker e cryptsetup podem funcionar, mas não têm suporte oficial e podem falhar em atualizações sem aviso.

#### Por que UEK? (e por que Rocky 10 / RHEL 10 de série não têm suporte)

O backend de armazenamento encriptado do Rediacc requer o módulo de kernel `btrfs` em árvore. **O kernel de série do RHEL 10 não o inclui**: `modprobe btrfs` falha com "Module btrfs not found" e `dnf search btrfs` não devolve nada. Rocky Linux 10 e AlmaLinux 10 herdam o mesmo kernel e, portanto, não podem funcionar como servidores Rediacc.

Oracle Linux 10 usa o **Unbreakable Enterprise Kernel (UEK)** por padrão, que mantém o btrfs integrado. É o único alvo compatível com RHEL na lista suportada. Se precisar de um servidor da família RHEL, use Oracle Linux 10 com UEK. (A fonte de verdade para esta decisão está em `.github/workflows/ct-tests.yml` como a matriz CI Bridge Workers.)

#### Apenas para o computador de trabalho (alvos de instalação do CLI)

O CLI `rdc` instala-se também sem problemas em Alpine 3.19+ (APK com a camada de compatibilidade `gcompat`, instalada automaticamente) e Arch Linux (rolling, via pacman). Estes são apenas caminhos de instalação do lado do cliente (consulte [Instalação](/pt/docs/installation)) e não têm suporte como alvos de servidor `renet`.

### Políticas de Segurança por SO

O daemon Docker por repositório e os próprios contentores do repositório correm com **labels de contentor padrão** em todos os SOs suportados. `rdc config machine setup` não instala políticas SELinux personalizadas nem perfis AppArmor. Comportamento por SO:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor está ativado por padrão. O perfil docker-container padrão aplica-se; não é necessária configuração adicional.
- **Fedora 43, Oracle Linux 10**: SELinux corre em modo enforcing. O daemon por repositório atribui aos contentores o contexto `container_t` padrão. Não é necessária uma política SELinux personalizada.
- **CRIU** (checkpoint/restore) é o único caso que contorna o perfil AppArmor com `apparmor=unconfined`, uma vez que o suporte AppArmor do CRIU upstream ainda não é estável. Consulte as notas do CRIU em [Regras do Rediacc](/pt/docs/rules-of-rediacc).

Se um passo de configuração falhar com negações AVC do SELinux ou rejeições do AppArmor, consulte [Resolução de Problemas](/pt/docs/troubleshooting) -> Problemas de Configuração Específicos da Distribuição.

### Pré-requisitos do Servidor

- Uma conta de utilizador com privilégios `sudo` (sudo sem palavra-passe recomendado)
- A sua chave pública SSH adicionada a `~/.ssh/authorized_keys`
- Pelo menos 20 GB de espaço em disco livre (mais consoante as suas cargas de trabalho)
- Acesso a Internet para obter imagens Docker (ou um registry privado)

### Instalado Automaticamente

O comando `rdc config machine setup` instala o seguinte no servidor remoto:

- **Docker** e **containerd** (runtime de contentores)
- **cryptsetup** (encriptação de disco LUKS)
- Binário **renet** (carregado via SFTP)

Não precisa de instalar estes componentes manualmente.

## Máquinas Virtuais Locais (Opcional)

Se pretender testar deployments localmente usando `rdc ops`, o seu computador de trabalho necessita de suporte a virtualização: KVM no Linux ou QEMU no macOS. Consulte o guia [VMs Experimentais](/pt/docs/experimental-vms) para passos de configuração e detalhes de plataforma.
