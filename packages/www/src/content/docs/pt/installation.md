---
title: "Instalação"
description: "Instale a CLI Rediacc em Linux, macOS ou Windows."
category: "Guides"
order: 1
language: pt
---

# Instalação

Instale a CLI `rdc` na sua estação de trabalho. Esta é a única ferramenta que precisa de instalar manualmente -- todo o resto é tratado automaticamente quando configura máquinas remotas.

## Instalação Rápida

### Linux e macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Este comando transfere o binário `rdc` para `$HOME/.local/bin/`. Certifique-se de que este diretório está no seu PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Adicione esta linha ao perfil da sua shell (`~/.bashrc`, `~/.zshrc`, etc.) para torná-la permanente.

### Windows

Execute no PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Este comando transfere `rdc.exe` para `%LOCALAPPDATA%\rediacc\bin\`. O instalador irá solicitar que o adicione ao PATH se necessário.

## Gestores de Pacotes

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / compatível com RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux e Rocky Linux utilizam todos o mesmo fluxo DNF; qualquer distribuição compatível com RHEL que tenha `dnf` pode utilizar o repositório acima. Nota: **Oracle Linux 10 é a única distribuição da família RHEL oficialmente suportada como destino de servidor Rediacc** (consulte [Requisitos](/pt/docs/requirements)). Rocky/Alma 10 não têm o módulo de kernel btrfs necessário pelo plano de dados renet, embora a CLI `rdc` instale neles sem problemas.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Testado em openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Nota: O pacote `gcompat` (camada de compatibilidade glibc) é instalado automaticamente como dependência.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

### npm (Node.js)

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz
```

Requer Node.js 22 ou superior. Para instalar uma versão específica:

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-0.8.5.tgz
```

## Docker

Transfira e execute a CLI como contentor:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Crie um alias para conveniência:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Tags Docker disponíveis:

| Tag | Descrição |
|-----|-------------|
| `:stable` | Última versão estável (recomendada) |
| `:edge` | Última versão edge |
| `:0.8.4` | Versão fixada (imutável) |
| `:latest` | Alias para `:stable` |

## Verificar a Instalação

```bash
rdc --version
```

## Atualização

Atualize para a versão mais recente:

```bash
rdc update
```

Verifique se há atualizações sem instalar:

```bash
rdc update --check-only
```

Veja o estado atual da atualização:

```bash
rdc update --status
```

Reverta para a versão anterior:

```bash
rdc update --rollback
```

## Canais de Lançamento

A Rediacc utiliza um sistema de lançamento baseado em canais. O canal determina a versão que recebe para atualizações da CLI, instalações por gestor de pacotes e pulls Docker.

| Canal | Descrição | Quando atualizado |
|---------|-------------|--------------|
| `stable` | Produção, promovido do edge após 7 dias de espera | Promoção semanal |
| `edge` | Produção continuamente deployada | Em cada merge para main |
| `pr-N` | Builds de pré-visualização de PR | Automaticamente por pull request |

### Mudar de canal

```bash
rdc update --channel edge      # Mudar para o canal edge
rdc update --channel stable    # Voltar para o canal stable
```

Instale diretamente a partir do canal edge:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Para gestores de pacotes, substitua `stable` por `edge` no URL do repositório:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Como funcionam os canais

O canal aplica-se uniformemente em todos os métodos de entrega:

- **Scripts de instalação**: a variável de ambiente `REDIACC_CHANNEL` seleciona o canal
- **Repositórios de pacotes**: `releases.rediacc.com/{format}/{channel}/`
- **Tags Docker**: `ghcr.io/rediacc/elite/cli:{channel}`
- **Atualizações da CLI**: `rdc update` verifica o canal configurado durante a instalação

### Autoconfiguração de pré-visualização de PR

Quando instala a partir de um deployment de pré-visualização de PR (p. ex., `pr-420.rediacc.workers.dev`), o canal e o servidor de conta são autoconfigurados:

- O binário da CLI é transferido do canal `pr-420`
- `rdc update` verifica o canal `pr-420` para atualizações
- Todos os comandos de conta/subscrição ligam ao servidor de pré-visualização do PR
- Os comandos Docker no site de pré-visualização mostram `cli:pr-420`

Não é necessária configuração manual. O script de instalação deteta o contexto do deployment a partir do URL.

## Atualizações de Binário Remoto

Quando executa comandos contra uma máquina remota, a CLI provisiona automaticamente o binário `renet` correspondente. Se o binário for atualizado, o servidor de rotas (`rediacc-router`) é reiniciado automaticamente para que utilize a nova versão.

O reinício é transparente e não causa **nenhuma indisponibilidade**:

- O servidor de rotas reinicia em aproximadamente 1 a 2 segundos.
- Durante esse período, o Traefik continua a servir tráfego usando a sua última configuração de encaminhamento conhecida. Nenhuma rota é perdida.
- O Traefik capta a nova configuração no seu próximo ciclo de sondagem (dentro de 5 segundos).
- **As ligações de cliente existentes (HTTP, TCP, UDP) não são afetadas.** O servidor de rotas é um fornecedor de configuração -- não está no caminho de dados. O Traefik trata de todo o tráfego diretamente.
- Os seus contentores de aplicação não são tocados -- apenas o processo do servidor de rotas ao nível do sistema é reiniciado.

Para ignorar o reinício automático, passe `--skip-router-restart` a qualquer comando ou defina a variável de ambiente `RDC_SKIP_ROUTER_RESTART=1`.
