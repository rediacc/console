---
title: "Configuração da Máquina"
description: "Crie uma configuração, adicione máquinas, provisione servidores e configure a infraestrutura."
category: "Guides"
order: 3
language: pt
sourceHash: "2456daa4289ffb8c"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Configuracao da Maquina

Esta pagina guia-o atraves da configuracao da sua primeira maquina: criar uma configuracao, registar um servidor, provisioná-lo e, opcionalmente, configurar a infraestrutura para acesso publico.

## Passo 1: Criar uma Configuracao

Uma **configuracao** e um ficheiro de configuracao nomeado que guarda as suas credenciais SSH, definicoes de maquinas e mapeamentos de repositorios. Pense nela como um espaco de trabalho de projecto.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opcao | Obrigatoria | Descricao |
|-------|-------------|-----------|
| `--ssh-key <path>` | Sim | Caminho para a sua chave SSH privada. O til (`~`) e expandido automaticamente. |
| `--renet-path <path>` | Nao | Caminho personalizado para o binario renet nas maquinas remotas. Por padrao, usa a localizacao de instalacao padrao. |

Isto cria uma configuracao chamada `my-infra` e guarda-a em `~/.config/rediacc/my-infra.json`. A configuracao padrao (quando nenhum nome e fornecido) e guardada como `~/.config/rediacc/rediacc.json`.

> Pode ter multiplas configuracoes (por exemplo, `production`, `staging`, `dev`). Alterne entre elas com a flag `--config` em qualquer comando.

## Passo 2: Adicionar uma Maquina

Registe o seu servidor remoto como maquina na configuracao:

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Opcao | Obrigatoria | Padrao | Descricao |
|-------|-------------|--------|-----------|
| `--ip <address>` | Sim | - | Endereco IP ou hostname do servidor remoto |
| `--user <username>` | Sim | - | Nome de utilizador SSH no servidor remoto |
| `--port <port>` | Nao | `22` | Porta SSH |
| `--datastore <path>` | Nao | `/mnt/rediacc` | Caminho no servidor onde o Rediacc guarda os repositorios encriptados |

Apos adicionar a maquina, o rdc executa automaticamente `ssh-keyscan` para obter as chaves de host do servidor. Tambem pode fazer isto manualmente:

```bash
rdc config machine scan-keys -m server-1
```

Para ver todas as maquinas registadas:

```bash
rdc config machine list
```

## Passo 3: Configurar a Maquina

Provisione o servidor remoto com todas as dependencias necessarias:

```bash
rdc config machine setup --name server-1
```

Este comando:
1. Carrega o binario renet para o servidor via SFTP
2. Instala Docker, containerd e cryptsetup (se nao estiverem presentes)
3. Cria o utilizador de sistema `rediacc` (UID 7111)
4. Cria o diretorio do datastore e prepara-o para repositorios encriptados

| Opcao | Obrigatoria | Padrao | Descricao |
|-------|-------------|--------|-----------|
| `--datastore <path>` | Nao | `/mnt/rediacc` | Diretorio do datastore no servidor |
| `--datastore-size <size>` | Nao | `95%` | Quanto do disco disponivel alocar para o datastore |
| `--debug` | Nao | `false` | Activar saida detalhada para resolucao de problemas |

> A configuracao so precisa de ser executada uma vez por maquina. E seguro voltar a executar se necessario.

## Gestao de Chaves de Host

Se a chave de host SSH de um servidor mudar (por exemplo, apos reinstalacao), actualize as chaves guardadas:

```bash
rdc config machine scan-keys -m server-1
```

Isto actualiza o campo `knownHosts` na sua configuracao para essa maquina.

## Testar Conectividade SSH

Apos adicionar uma maquina, verifique se e alcancavel:

```bash
rdc term connect -m server-1 -c "hostname"
```

Isto abre uma conexao SSH para a maquina e executa o comando. Se tiver sucesso, a sua configuracao SSH esta correcta.

Para diagnosticos mais detalhados, execute:

```bash
rdc doctor
```

> **Apenas adaptador cloud**: O comando `rdc machine test-connection` fornece diagnosticos SSH detalhados, mas requer o adaptador cloud. Para o adaptador local, use `rdc term` ou `ssh` directamente.

## Configuracao de Infraestrutura

Para maquinas que precisam de servir trafico publicamente, configure as definicoes de infraestrutura:

### Definir Infraestrutura

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opcao | Ambito | Descricao |
|-------|--------|-----------|
| `--public-ipv4 <ip>` | Maquina | Endereco IPv4 publico; os entrypoints do proxy so sao criados para familias de enderecos configuradas |
| `--public-ipv6 <ip>` | Maquina | Endereco IPv6 publico; os entrypoints do proxy so sao criados para familias de enderecos configuradas |
| `--base-domain <domain>` | Maquina | Dominio base para aplicacoes (por exemplo, `example.com`) |
| `--cert-email <email>` | Configuracao | Email para certificados TLS Let's Encrypt (partilhado entre maquinas) |
| `--cf-dns-token <token>` | Configuracao | Token da API DNS Cloudflare para desafios ACME DNS-01 (partilhado entre maquinas) |
| `--tcp-ports <ports>` | Maquina | Portas TCP adicionais separadas por virgula para reencaminhar (por exemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Maquina | Portas UDP adicionais separadas por virgula para reencaminhar (por exemplo, `53`) |

As opcoes com ambito de maquina sao guardadas por maquina. As opcoes com ambito de configuracao (`--cert-email`, `--cf-dns-token`) sao partilhadas entre todas as maquinas da configuracao. Defina-as uma vez e aplicam-se em todo o lado.

### Ver Infraestrutura

```bash
rdc config infra show -m server-1
```

### Enviar para o Servidor

Gerar e fazer deploy da configuracao do proxy reverso Traefik para o servidor:

```bash
rdc config infra push -m server-1
```

Este comando:
1. Faz deploy do binario renet para a maquina remota
2. Configura o proxy reverso Traefik, o router e os servicos systemd
3. Cria registos DNS Cloudflare para o subdominio da maquina (`server-1.example.com` e `*.server-1.example.com`) se `--cf-dns-token` estiver definido

O passo DNS e automatico e idempotente: cria registos em falta, actualiza registos com IPs alterados e ignora registos que ja estao correctos. Se nenhum token Cloudflare estiver configurado, o DNS e ignorado com um aviso. Os registos DNS wildcard por repositorio (para rotas automaticas) sao criados automaticamente quando executa `rdc repo up`.

## Provisionamento na Nuvem

Em vez de criar VMs manualmente, pode configurar um fornecedor de nuvem e deixar o `rdc` provisionar maquinas automaticamente usando [OpenTofu](https://opentofu.org/).

### Pre-requisitos

Instale o OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Certifique-se de que a sua configuracao SSH tem uma chave registada com `rdc`:

```bash
# Le o ficheiro de chave e incorpora o conteudo em /credentials/ssh.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Adicionar um Fornecedor de Nuvem

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Opcao | Obrigatoria | Descricao |
|-------|-------------|-----------|
| `--provider <source>` | Sim* | Fonte de fornecedor conhecida (por exemplo, `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Sim* | Fonte de fornecedor OpenTofu personalizada (para fornecedores desconhecidos) |
| `--token <token>` | Sim | Token de API do fornecedor de nuvem |
| `--region <region>` | Nao | Regiao padrao para novas maquinas |
| `--type <type>` | Nao | Tipo/tamanho de instancia padrao |
| `--image <image>` | Nao | Imagem SO padrao |
| `--ssh-user <user>` | Nao | Nome de utilizador SSH (padrao: `root`) |

\* E necessario `--provider` ou `--source`. Use `--provider` para fornecedores conhecidos (predefinicoes incorporadas). Use `--source` com flags adicionais `--resource`, `--ipv4-output`, `--ssh-key-attr` para fornecedores personalizados.

### Provisionar uma Maquina

```bash
rdc machine provision --name prod-2 --provider my-linode
```

Este unico comando:
1. Cria uma VM no fornecedor de nuvem via OpenTofu
2. Aguarda conectividade SSH
3. Regista a maquina na sua configuracao
4. Instala renet e todas as dependencias
5. Configura o proxy Traefik e DNS Cloudflare (detecta automaticamente o dominio base a partir de maquinas irmas, ou passe `--base-domain` explicitamente)

| Opcao | Descricao |
|-------|-----------|
| `--provider <name>` | Nome do fornecedor de nuvem (de `add-provider`) |
| `--region <region>` | Substituir a regiao padrao do fornecedor |
| `--type <type>` | Substituir o tipo de instancia padrao |
| `--image <image>` | Substituir a imagem SO padrao |
| `--base-domain <domain>` | Dominio base para infraestrutura. Detectado automaticamente a partir de maquinas irmas se nao for especificado |
| `--no-infra` | Ignorar completamente a configuracao de infraestrutura (proxy + DNS) |
| `--debug` | Mostrar saida detalhada do provisionamento |

### Desprovisionar uma Maquina

```bash
rdc machine deprovision --name prod-2
```

Destroi a VM via OpenTofu e remove-a da sua configuracao. Requer confirmacao a menos que `--force` seja usado. So funciona para maquinas criadas com `machine provision`.

### Listar Fornecedores

```bash
rdc config provider list
```

## Definir Predefinicoes

Defina valores predefinidos para nao ter de os especificar em cada comando:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Maquina padrao
rdc config set --key team --value my-team                   # Equipa padrao (adaptador cloud, experimental)
```

Apos definir uma maquina padrao, pode omitir `-m server-1` dos comandos:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Multiplas Configuracoes

Gira multiplos ambientes com configuracoes nomeadas:

```bash
# Criar configuracoes separadas
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# Usar uma configuracao especifica
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Ver todas as configuracoes:

```bash
rdc config list
```

Mostrar os detalhes da configuracao actual:

```bash
rdc config show
```
