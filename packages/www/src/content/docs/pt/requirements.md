---
title: Requisitos
description: Requisitos de sistema e plataformas suportadas para executar o Rediacc na sua máquina.
category: Guides
order: 0
language: pt
---

# Requisitos

Antes de fazer deployments com o Rediacc, certifique-se de que o seu computador de trabalho e os servidores remotos cumprem os requisitos indicados a seguir.

## Computador de Trabalho (Plano de Controlo)

O CLI `rdc` corre no seu computador de trabalho e orquestra servidores remotos via SSH. Esta é a configuração recomendada.

| Plataforma | Versao Minima | Notas |
|------------|---------------|-------|
| macOS | 12 (Monterey)+ | Intel e Apple Silicon suportados |
| Linux (x86_64) | Qualquer distribuicao moderna | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Suporte nativo via instalador PowerShell |

**Requisitos adicionais:**
- Um par de chaves SSH (por exemplo, `~/.ssh/id_ed25519` ou `~/.ssh/id_rsa`)
- Acesso de rede aos servidores remotos na porta SSH (padrao: 22)

## Servidor Remoto (Plano de Dados)

O binario `renet` corre em servidores remotos com privilegios de root. Gere imagens de disco encriptadas, daemons Docker isolados e orquestracao de servicos.

Se nao tiver a certeza de qual binario usar, consulte [rdc vs renet](/pt/docs/rdc-vs-renet). Em resumo: use `rdc` para operacoes normais e `renet` diretamente apenas para tarefas avancadas do lado do servidor.

### Sistemas Operativos Suportados

Os servidores remotos executam o binario `renet` e alojam os daemons Docker encriptados por repositorio. As cinco distribuicoes seguintes sao testadas pela matriz Bridge Workers em CI em cada pull request e sao as unicas com suporte oficial:

| SO | Versao | Kernel Padrao | Notas |
|----|--------|---------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Recomendado. AppArmor ativado por padrao. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 tambem funciona (kernel 6.1 minimo). |
| Fedora | 43 | 6.12 | SELinux em modo enforcing por padrao. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor ativado por padrao. |
| Oracle Linux | 10 | UEK 7+ | Usa UEK, que mantem o modulo btrfs. SELinux em modo enforcing por padrao. Ver "Por que UEK?" abaixo. |

Todas as entradas sao `x86_64`. `arm64` e compilado mas nao testado continuamente para todos os SOs de servidor; abra uma issue se precisar numa distribuicao especifica. Outras distribuicoes Linux com systemd, suporte a Docker e cryptsetup podem funcionar, mas nao tem suporte oficial e podem falhar em actualizacoes sem aviso.

#### Por que UEK? (e por que Rocky 10 / RHEL 10 de serie nao tem suporte)

O backend de armazenamento encriptado do Rediacc requer o modulo de kernel `btrfs` em arvore. **O kernel de serie do RHEL 10 nao o inclui**: `modprobe btrfs` falha com "Module btrfs not found" e `dnf search btrfs` nao devolve nada. Rocky Linux 10 e AlmaLinux 10 herdam o mesmo kernel e, por isso, nao podem funcionar como servidores Rediacc.

O Oracle Linux 10 usa o **Unbreakable Enterprise Kernel (UEK)** por padrao, que mantem o btrfs integrado. E o unico alvo compativel com RHEL na lista suportada. Se necessitar de um servidor da familia RHEL, use Oracle Linux 10 com UEK. (A fonte de verdade para esta decisao esta em `.github/workflows/ct-tests.yml` como a matriz CI Bridge Workers.)

#### So para o computador de trabalho (alvos de instalacao do CLI)

O CLI `rdc` instala-se tambem sem problemas em Alpine 3.19+ (APK com a camada de compatibilidade `gcompat`, instalada automaticamente) e Arch Linux (rolling, via pacman). Estes sao apenas caminhos de instalacao do lado do cliente (consulte [Instalacao](/pt/docs/installation)) e nao tem suporte como alvos de servidor `renet`.

### Politicas de Seguranca por SO

O daemon Docker por repositorio e os proprios contendores do repositorio correm com **labels de contentor padrao** em todos os SOs suportados. `rdc config machine setup` nao instala politicas SELinux personalizadas nem perfis AppArmor. Comportamento por SO:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor esta ativado por padrao. O perfil docker-container padrao aplica-se; nao e necessaria configuracao adicional.
- **Fedora 43, Oracle Linux 10**: SELinux corre em modo enforcing. O daemon por repositorio atribui aos contentores o contexto `container_t` padrao. Nao e necessaria uma politica SELinux personalizada.
- **CRIU** (checkpoint/restore) e o unico caso que contorna o perfil AppArmor com `apparmor=unconfined`, uma vez que o suporte AppArmor do CRIU upstream ainda nao e estavel. Consulte as notas do CRIU em [Regras do Rediacc](/pt/docs/rules-of-rediacc).

Se um passo de configuracao falhar com negacoes AVC do SELinux ou rejeicoes do AppArmor, consulte [Resolucao de Problemas](/pt/docs/troubleshooting) -> Problemas de Configuracao Especificos da Distribuicao.

### Pre-requisitos do Servidor

- Uma conta de utilizador com privilegios `sudo` (sudo sem password recomendado)
- A sua chave publica SSH adicionada a `~/.ssh/authorized_keys`
- Pelo menos 20 GB de espaco em disco livre (mais consoante as suas cargas de trabalho)
- Acesso a Internet para obter imagens Docker (ou um registry privado)

### Instalado Automaticamente

O comando `rdc config machine setup` instala o seguinte no servidor remoto:

- **Docker** e **containerd** (runtime de contentores)
- **cryptsetup** (encriptacao de disco LUKS)
- Binario **renet** (carregado via SFTP)

Nao precisa de instalar estes componentes manualmente.

## Maquinas Virtuais Locais (Opcional)

Se pretender testar deployments localmente usando `rdc ops`, o seu computador de trabalho necessita de suporte a virtualizacao: KVM no Linux ou QEMU no macOS. Consulte o guia [VMs Experimentais](/pt/docs/experimental-vms) para passos de configuracao e detalhes de plataforma.
