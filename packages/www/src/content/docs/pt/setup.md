---
title: "Configuração da Máquina"
description: "Crie uma configuração, adicione máquinas, provisione servidores e configure a infraestrutura."
category: "Guides"
order: 3
language: pt
sourceHash: "6e0b338423280f98"
sourceCommit: "5fab1177d6ceae5211c25cf8fa0176d67259d40e"
---

# Configuração da Máquina

Quatro passos colocam a sua primeira máquina em funcionamento: criar uma configuração, registar um servidor, provisioná-lo e, opcionalmente, configurar a infraestrutura para tráfego público.

## Passo 1: Criar uma Configuração

Uma **configuração** é um ficheiro de configuração nomeado que armazena as suas credenciais SSH, definições de máquinas e mapeamentos de repositórios. Pense nela como um espaço de trabalho de projeto.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
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
rdc machine add server-1 --ip 203.0.113.50 --user deploy
```

| Opção | Obrigatória | Padrão | Descrição |
|-------|-------------|--------|-----------|
| `--ip <address>` | Sim | - | Endereço IP ou hostname do servidor remoto |
| `--user <username>` | Sim | - | Nome de utilizador SSH no servidor remoto |
| `--port <port>` | Não | `22` | Porta SSH |
| `--datastore <path>` | Não | `/mnt/rediacc` | Caminho no servidor onde o Rediacc armazena os repositórios encriptados |

Após adicionar a máquina, o rdc executa automaticamente `ssh-keyscan` para obter as chaves de host do servidor. Também pode fazer isto manualmente:

```bash
rdc machine scan-keys server-1
```

Para ver todas as máquinas registadas:

```bash
rdc machine list
```

## Passo 3: Configurar a Máquina

Provisione o servidor remoto com todas as dependências necessárias:

```bash
rdc machine setup server-1
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

## Backends de Datastore

O datastore é o pool de armazenamento por máquina que contém as imagens de repositório encriptadas. O `machine setup` cria um datastore **local** por predefinição: um sistema de ficheiros BTRFS assente num loop device no próprio disco do servidor, dimensionado por `--datastore-size` (predefinição `95%` do disco disponível). É o backend certo para quase todas as implementações de máquina única e não precisa de nada além do servidor.

### Dimensionamento do datastore

`--datastore-size` aceita uma percentagem (`95%`) ou um tamanho absoluto (`50G`, `1T`). O datastore pode ser aumentado online mais tarde:

```bash
rdc datastore resize ds-server-1 --size 200G
```

Os repositórios dentro do datastore são dimensionados de forma independente no momento do `repo create` e podem ser expandidos enquanto estão em execução, pelo que não precisa de sobredimensionar o datastore antecipadamente.

### Backend Ceph RBD

Para armazenamento partilhado, de escalonamento horizontal, ou de suporte ao Kubernetes, inicialize o datastore num cluster Ceph externo. O datastore passa então a residir numa imagem RBD (BTRFS por cima, sem camada de LUKS por imagem), e os forks usam clones copy-on-write do RBD em vez de reflinks BTRFS.

```bash
# 1. Registar a referência Ceph da máquina (pool + imagem RBD, não secreta)

# 2. Inicializar o datastore no backend Ceph
rdc datastore create ds-server-1 -m server-1 --backend ceph --pool rbd --image datastore-server1 --size 100G
```

Os keyrings do Ceph permanecem nas máquinas; o ficheiro de configuração guarda apenas as referências não secretas de pool e imagem. O Ceph é também a camada de armazenamento que os clusters Kubernetes consomem através do ceph-csi. Consulte o guia [Kubernetes](/en/docs/kubernetes) para clusters e volumes persistentes, e [Arquitetura](/en/docs/architecture) para saber como os dois backends se comparam.

## Gestão de Chaves de Host

Se a chave de host SSH de um servidor mudar (por exemplo, após reinstalação), atualize as chaves armazenadas:

```bash
rdc machine scan-keys server-1
```

Isto atualiza o campo `knownHosts` na sua configuração para essa máquina.

## Testar Conectividade SSH

Após adicionar uma máquina, verifique se é alcançável:

```bash
rdc term connect server-1 -c "hostname"
```

Isto abre uma conexão SSH e executa o comando. Se funcionar, a sua configuração SSH está correta.

Para diagnósticos mais detalhados, execute:

```bash
rdc doctor
```

> **Dica**: Para verificar a conectividade SSH, execute `rdc term connect <machine> -c "hostname"` ou use `ssh` diretamente.

## Configuração de Infraestrutura

Para máquinas que precisam de servir tráfego publicamente, configure as definições de infraestrutura:

### Definir Infraestrutura

```bash
rdc machine infra set server-1 \
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
rdc machine infra show server-1
```

### Enviar para o Servidor

Gerar e fazer deploy da configuração do proxy reverso Traefik para o servidor:

```bash
rdc machine infra push server-1
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
rdc machine provider add my-linode \
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
rdc machine provision prod-2 --provider my-linode
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
rdc machine deprovision prod-2
```

Destrói a VM via OpenTofu e remove-a da sua configuração. Requer confirmação a menos que `--force` seja usado. Só funciona para máquinas criadas com `machine provision`.

### Listar Fornecedores

```bash
rdc machine provider list
```

## Definir Predefinições

Defina valores predefinidos para não ter de os especificar em cada comando:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Máquina padrão
rdc config set team my-team                   # Equipe padrão para o armazenamento de configuração
```

Após definir uma máquina padrão, pode omitir `-m server-1` dos comandos:

```bash
rdc repo create my-app -m my-server --size 10G
```

## Múltiplas Configurações

Gira múltiplos ambientes com configurações nomeadas:

```bash
# Criar configurações separadas
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

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
