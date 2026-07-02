---
title: "Configuração da Máquina"
description: "Crie uma configuração, adicione máquinas, provisione servidores e configure a infraestrutura."
category: "Guides"
order: 3
language: pt
sourceHash: "19a208e453f7d742"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Configuração da Máquina

Quatro passos colocam a sua primeira máquina em funcionamento: criar uma configuração, registar um servidor, provisioná-lo e, opcionalmente, configurar a infraestrutura para tráfego público.

## Passo 1: Criar uma Configuração

Uma **configuração** é um ficheiro de configuração nomeado que armazena as suas credenciais SSH, definições de máquinas e mapeamentos de repositórios. Pense nela como um espaço de trabalho de projeto.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opção | Obrigatória | Descrição |
|-------|-------------|-----------|
| `--ssh-key <path>` | Sim | Caminho para a sua chave SSH privada. O til (`~`) é expandido automaticamente. |
| `--renet-path <path>` | Não | Caminho personalizado para o binário renet nas máquinas remotas. Por padrão, usa a localização de instalação padrão. |

Isto cria uma configuração chamada `my-infra` e armazena-a em `~/.config/rediacc/my-infra.json`. A configuração padrão (quando nenhum nome é fornecido) é armazenada como `~/.config/rediacc/rediacc.json`.

> Pode ter múltiplas configurações (por exemplo, `production`, `staging`, `dev`). Alterne entre elas com a flag `--config` em qualquer comando.

## Passo 2: Adicionar uma Máquina

Registe o seu servidor remoto como máquina na configuração:

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Opção | Obrigatória | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `--ip <address>` | Sim | - | Endereço IP ou hostname do servidor remoto |
| `--user <username>` | Sim | - | Nome de utilizador SSH no servidor remoto |
| `--port <port>` | Não | `22` | Porta SSH |
| `--datastore <path>` | Não | `/mnt/rediacc` | Caminho no servidor onde o Rediacc armazena os repositórios encriptados |

Após adicionar a máquina, o rdc executa automaticamente `ssh-keyscan` para obter as chaves de host do servidor. Também pode fazer isto manualmente:

```bash
rdc config machine scan-keys -m server-1
```

Para ver todas as máquinas registadas:

```bash
rdc config machine list
```

## Passo 3: Configurar a Máquina

Provisione o servidor remoto com todas as dependências necessárias:

```bash
rdc config machine setup --name server-1
```

Este comando:
1. Carrega o binário renet para o servidor via SFTP
2. Instala Docker, containerd e cryptsetup (se não estiverem presentes)
3. Cria o utilizador de sistema `rediacc` (UID 7111)
4. Cria o diretório do datastore e prepara-o para repositórios encriptados

| Opção | Obrigatória | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `--datastore <path>` | Não | `/mnt/rediacc` | Diretório do datastore no servidor |
| `--datastore-size <size>` | Não | `95%` | Quanto do disco disponível alocar para o datastore |
| `--debug` | Não | `false` | Ativar saída detalhada para resolução de problemas |

> A configuração só precisa de ser executada uma vez por máquina. É seguro voltar a executar se necessário.

## Gestão de Chaves de Host

Se a chave de host SSH de um servidor mudar (por exemplo, após reinstalação), atualize as chaves armazenadas:

```bash
rdc config machine scan-keys -m server-1
```

Isto atualiza o campo `knownHosts` na sua configuração para essa máquina.

## Testar Conectividade SSH

Após adicionar uma máquina, verifique se é alcançável:

```bash
rdc term connect -m server-1 -c "hostname"
```

Isto abre uma conexão SSH e executa o comando. Se funcionar, a sua configuração SSH está correta.

Para diagnósticos mais detalhados, execute:

```bash
rdc doctor
```

> **Dica**: Para verificar a conectividade SSH, execute `rdc term connect -m <machine> -c "hostname"` ou use `ssh` diretamente.

## Configuração de Infraestrutura

Para máquinas que precisam de servir tráfego publicamente, configure as definições de infraestrutura:

### Definir Infraestrutura

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opção | Âmbito | Descrição |
|-------|--------|-----------|
| `--public-ipv4 <ip>` | Máquina | Endereço IPv4 público; os entrypoints do proxy só são criados para famílias de endereços configuradas |
| `--public-ipv6 <ip>` | Máquina | Endereço IPv6 público; os entrypoints do proxy só são criados para famílias de endereços configuradas |
| `--base-domain <domain>` | Máquina | Domínio base para aplicações (por exemplo, `example.com`) |
| `--cert-email <email>` | Configuração | Email para certificados TLS Let's Encrypt (partilhado entre máquinas) |
| `--cf-dns-token <token>` | Configuração | Token da API DNS Cloudflare para desafios ACME DNS-01 (partilhado entre máquinas) |
| `--tcp-ports <ports>` | Máquina | Portas TCP adicionais separadas por vírgula para reencaminhar (por exemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Máquina | Portas UDP adicionais separadas por vírgula para reencaminhar (por exemplo, `53`) |

As opções com âmbito de máquina são armazenadas por máquina. As opções com âmbito de configuração (`--cert-email`, `--cf-dns-token`) são partilhadas entre todas as máquinas da configuração. Defina-as uma vez e aplicam-se em todo o lado.

### Ver Infraestrutura

```bash
rdc config infra show -m server-1
```

### Enviar para o Servidor

Gerar e fazer deploy da configuração do proxy reverso Traefik para o servidor:

```bash
rdc config infra push -m server-1
```

Este comando:
1. Faz deploy do binário renet para a máquina remota
2. Configura o proxy reverso Traefik, o router e os serviços systemd
3. Cria registos DNS Cloudflare para o subdomínio da máquina (`server-1.example.com` e `*.server-1.example.com`) se `--cf-dns-token` estiver definido

O passo DNS é automático e idempotente: cria registos em falta, atualiza registos com IPs alterados e ignora registos que já estão corretos. Se nenhum token Cloudflare estiver configurado, o DNS é ignorado com um aviso. Os registos DNS wildcard por repositório (para rotas automáticas) são criados automaticamente quando executa `rdc repo up`.

## Provisionamento na Nuvem

Em vez de criar VMs manualmente, pode configurar um fornecedor de nuvem e deixar o `rdc` provisionar máquinas automaticamente usando [OpenTofu](https://opentofu.org/).

### Pré-requisitos

Instale o OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Certifique-se de que a sua configuração SSH tem uma chave registada com `rdc`:

```bash
# Lê o ficheiro de chave e incorpora o conteúdo em /credentials/ssh.
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

| Opção | Obrigatória | Descrição |
|-------|-------------|-----------|
| `--provider <source>` | Sim* | Fonte de fornecedor conhecida (por exemplo, `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Sim* | Fonte de fornecedor OpenTofu personalizada (para fornecedores desconhecidos) |
| `--token <token>` | Sim | Token de API do fornecedor de nuvem |
| `--region <region>` | Não | Região padrão para novas máquinas |
| `--type <type>` | Não | Tipo/tamanho de instância padrão |
| `--image <image>` | Não | Imagem SO padrão |
| `--ssh-user <user>` | Não | Nome de utilizador SSH (padrão: `root`) |

\* É necessário `--provider` ou `--source`. Use `--provider` para fornecedores conhecidos (predefinições incorporadas). Use `--source` com flags adicionais `--resource`, `--ipv4-output`, `--ssh-key-attr` para fornecedores personalizados.

### Provisionar uma Máquina

```bash
rdc machine provision --name prod-2 --provider my-linode
```

Este único comando:
1. Cria uma VM no fornecedor de nuvem via OpenTofu
2. Aguarda conectividade SSH
3. Regista a máquina na sua configuração
4. Instala renet e todas as dependências
5. Configura o proxy Traefik e DNS Cloudflare (detecta automaticamente o domínio base a partir de máquinas irmãs, ou passe `--base-domain` explicitamente)

| Opção | Descrição |
|-------|-----------|
| `--provider <name>` | Nome do fornecedor de nuvem (de `add-provider`) |
| `--region <region>` | Substituir a região padrão do fornecedor |
| `--type <type>` | Substituir o tipo de instância padrão |
| `--image <image>` | Substituir a imagem SO padrão |
| `--base-domain <domain>` | Domínio base para infraestrutura. Detectado automaticamente a partir de máquinas irmãs se não for especificado |
| `--no-infra` | Ignorar completamente a configuração de infraestrutura (proxy + DNS) |
| `--debug` | Mostrar saída detalhada do provisionamento |

### Desprovisionar uma Máquina

```bash
rdc machine deprovision --name prod-2
```

Destrói a VM via OpenTofu e remove-a da sua configuração. Requer confirmação a menos que `--force` seja usado. Só funciona para máquinas criadas com `machine provision`.

### Listar Fornecedores

```bash
rdc config provider list
```

## Definir Predefinições

Defina valores predefinidos para não ter de os especificar em cada comando:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Máquina padrão
rdc config set --key team --value my-team                   # Equipe padrão para o armazenamento de configuração
```

Após definir uma máquina padrão, pode omitir `-m server-1` dos comandos:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Múltiplas Configurações

Gira múltiplos ambientes com configurações nomeadas:

```bash
# Criar configurações separadas
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# Usar uma configuração específica
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Ver todas as configurações:

```bash
rdc config list
```

Mostrar os detalhes da configuração atual:

```bash
rdc config show
```
