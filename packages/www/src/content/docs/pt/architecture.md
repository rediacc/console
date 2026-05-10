---
title: Arquitetura
description: >-
  Como a Rediacc funciona: arquitetura de duas ferramentas, deteção de adaptador, modelo de segurança e
  estrutura de configuração.
category: Concepts
order: 0
language: pt
---

# Arquitetura

Esta página explica como a Rediacc funciona internamente: a arquitetura de duas ferramentas, a deteção de adaptador, o modelo de segurança e a estrutura de configuração.

## Visão Geral da Stack Completa

O tráfego flui da internet através de um reverse proxy, para daemons Docker isolados, cada um suportado por armazenamento encriptado:

![Full Stack Architecture](/img/arch-full-stack.svg)

Cada repositório tem o seu próprio daemon Docker, sub-rede IP de loopback (/26 = 64 IPs) e volume BTRFS encriptado com LUKS. O servidor de rotas descobre os contentores em execução em todos os daemons e fornece a configuração de encaminhamento ao Traefik.

## Arquitetura de Duas Ferramentas

A Rediacc usa dois binários que funcionam em conjunto via SSH:

![Two-Tool Architecture](/img/arch-two-tool.svg)

- **rdc** corre na sua workstation (macOS, Linux ou Windows). Lê a sua configuração local, liga-se a máquinas remotas via SSH e invoca comandos renet.
- **renet** corre no servidor remoto com privilégios de root. Gere imagens de disco encriptadas com LUKS, daemons Docker isolados, orquestração de serviços e configuração do reverse proxy.

Cada comando que escreve localmente traduz-se numa chamada SSH que executa o renet na máquina remota. Nunca precisa de fazer SSH para os servidores manualmente.

Para uma regra prática orientada ao operador, consulte [rdc vs renet](/en/docs/rdc-vs-renet). Também pode usar `rdc ops` para executar um cluster de VM local para testes; consulte [VMs Experimentais](/en/docs/experimental-vms).

## Configuração

Todo o estado do CLI é armazenado em ficheiros de configuração JSON planos em `~/.config/rediacc/`.

### Adaptador Local (Predefinição)

A predefinição para uso self-hosted. Todo o estado reside num ficheiro de configuração na sua workstation (por exemplo, `~/.config/rediacc/rediacc.json`).

- Ligações SSH diretas às máquinas
- Sem serviços externos necessários
- Utilizador único, workstation única
- A configuração predefinida é criada automaticamente no primeiro uso do CLI. As configurações nomeadas são criadas com `rdc config init --name <name>`

### Adaptador Cloud (Experimental)

Ativado automaticamente quando uma configuração contém os campos `apiUrl` e `token`. Usa a API da Rediacc para gestão de estado e colaboração em equipa.

- Estado armazenado na API cloud
- Equipas multi-utilizador com controlo de acesso baseado em funções
- Consola web para gestão visual
- Configurado com `rdc auth login`

> **Nota:** Os comandos do adaptador cloud são experimentais. Ative-os definindo `REDIACC_EXPERIMENTAL=1`.

Ambos os adaptadores usam os mesmos comandos CLI. O adaptador apenas afeta onde o estado é armazenado e como a autenticação funciona.

## O Utilizador rediacc

Quando executa `rdc config machine setup`, o renet cria um utilizador de sistema chamado `rediacc` no servidor remoto:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (não pode iniciar sessão via SSH)
- **Finalidade**: Detém os ficheiros do repositório e executa as funções do Rediaccfile

O utilizador `rediacc` não pode ser acedido via SSH diretamente. Em vez disso, o rdc liga-se como o utilizador SSH que configurou (por exemplo, `deploy`), e o renet executa operações de repositório via `sudo -u rediacc /bin/sh -c '...'`. Isto significa:

1. O seu utilizador SSH precisa de privilégios `sudo`
2. Todos os dados do repositório pertencem ao `rediacc`, não ao seu utilizador SSH
3. As funções do Rediaccfile (`up()`, `down()`) correm como `rediacc`

Esta separação garante que os dados do repositório têm propriedade consistente, independentemente do utilizador SSH que os gere.

## Isolamento Docker

Cada repositório tem o seu próprio daemon Docker isolado. Quando um repositório é montado, o renet inicia um processo `dockerd` dedicado com um socket único:

![Docker Isolation](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Por exemplo, um repositório com o ID de rede `2816` usa:
```
/var/run/rediacc/docker-2816.sock
```

Isto significa:
- Os contentores de repositórios diferentes não se conseguem ver
- Cada repositório tem a sua própria cache de imagens, redes e volumes
- O daemon Docker do host (se existir) é completamente separado

As funções do Rediaccfile têm automaticamente `DOCKER_HOST` definido para o socket correto.

Quando um agente de IA entra num repositório via `rdc term connect -r <repo>`, o mesmo isolamento se aplica: a sessão corre como o utilizador `rediacc` sem privilégios (UID 7111), num namespace de mount distinto, com `DOCKER_HOST` limitado ao socket do daemon desse único repositório. O fluxo fork-first combina este isolamento de execução com uma primitiva de clone CoW: o agente opera num fork por tarefa, nunca em repositórios grand (produção). Consulte [Segurança e Controlos para Agentes de IA](/en/docs/ai-agents-safety) para o modelo completo de sandbox, a semântica dos overrides e a fronteira de responsabilidade do programador para credenciais de serviços externos.

### Layout do Caminho do Daemon

Os dados e a configuração do Docker são armazenados dentro do mount do repositório, mantendo cada daemon completamente isolado do host e dos outros repositórios.

**Layout por repositório:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Raiz de dados Docker
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Configuração Docker
```

**Layout standalone** (daemons não ligados a um mount de repositório):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Caminho de runtime partilhado** (inalterado):
```
/run/rediacc/docker-{N}.sock
```

Este layout unificado elimina colisões de mount só de leitura/leitura-escrita que ocorriam quando os caminhos dos daemons estavam divididos entre o sistema de ficheiros do host e o volume encriptado. Tanto os daemons por repositório como os standalone seguem a mesma estrutura de diretórios, pelo que as ferramentas e os diagnósticos funcionam de forma idêntica em ambos os casos.

## Encriptação LUKS

Os repositórios são imagens de disco encriptadas com LUKS armazenadas no datastore do servidor (predefinição: `/mnt/rediacc`). Cada repositório:

1. Tem uma passphrase de encriptação gerada aleatoriamente (a "credencial")
2. É armazenado como um ficheiro: `{datastore}/repos/{guid}.img`
3. É montado via `cryptsetup` quando acedido

A credencial é armazenada no seu ficheiro de configuração mas **nunca** no servidor. Sem a credencial, os dados do repositório não podem ser lidos. Quando o autostart está ativado, um keyfile LUKS secundário é armazenado no servidor para permitir a montagem automática no arranque.

## Estrutura de Configuração

Cada configuração é um ficheiro JSON armazenado em `~/.config/rediacc/`. A configuração predefinida é `rediacc.json`; as configurações nomeadas usam o nome como nome de ficheiro (por exemplo, `production.json`). Os campos são agrupados por finalidade: `resources` contém implementações, `credentials` contém segredos, `account` contém predefinições cloud, `infra` contém TLS/DNS, e `encryption` contém o estado em repouso por campo. O discriminador de nível superior `schemaVersion: 2` ancora a compatibilidade futura.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Grupos principais:**

| Grupo | Conteúdo |
|---|---|
| `schemaVersion` | Discriminador (atualmente `2`). Os loaders rejeitam versões desconhecidas. |
| `id` / `version` | UUID imutável + contador monótono; usado para locking otimista no armazenamento de configuração remoto. |
| `defaults.*` | Predefinições de runtime não sensíveis (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Par de chaves SSH inline + `knownHosts`. Substitui o legado `ssh.privateKeyPath` (sem mais indireção por caminho de ficheiro; o conteúdo é resolvido no carregamento e armazenado inline). |
| `credentials.cfDnsApiToken` | Token ACME DNS-01 do Cloudflare. |
| `credentials.masterPasswordVerifier` | Presente apenas quando `encryption.mode === "master-password"`. |
| `resources.machines.*` | Detalhes de ligação SSH por máquina. |
| `resources.storages.*` | Credenciais de backup off-site compatíveis com rclone. |
| `resources.repositories.*` | GUID por repositório + credencial LUKS + chave SSH para acesso de agente isolado em sandbox. |
| `infra.acmeCertCache.*` | acme.json do Traefik em cache, gzip+base64, indexado por domínio. |
| `encryption.mode` | `"plaintext"` (predefinição) ou `"master-password"`. |
| `encryption.encryptedFields` | Quando encriptado, um mapa de blobs AES-GCM por pointer (`/resources/repositories/webapp/credential` para `{ciphertext, nonce, tag}`). Uma única solicitação de desbloqueio por sessão desencripta à medida que os campos são lidos. |
| `remote` | Presente apenas quando a configuração está sincronizada com o armazenamento de configuração encriptado; consulte [Armazenamento de configuração encriptado](/en/docs/config-storage). |

**Edite com segurança através do CLI, não com `vim`:**

```bash
# Edições de campo único por pointer (com knowledge-gate para caminhos sensíveis)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Editor completo com projeção JSONC redatada (apenas para humanos)
rdc config edit

# Dump JSONC só de leitura, seguro para scripts e agentes
rdc config edit --dump

# Inspecionar cada mutação + recusa + revelação no registo de auditoria
rdc config audit log --since 24h
rdc config audit verify
```

> Este ficheiro contém dados sensíveis (chaves privadas SSH, credenciais LUKS, tokens Cloudflare). É armazenado com permissões `0600` (leitura/escrita apenas pelo proprietário). Não o partilhe nem o adicione ao controlo de versão. Quando qualquer comando `rdc` o lê, os campos sensíveis são [redatados por omissão](/en/docs/ai-agents-safety): o texto simples apenas aparece com `--reveal` num TTY humano interativo.

### Envelope v2 e aplicação do lado do servidor

Quando a configuração está sincronizada com o [armazenamento de configuração encriptado](/en/docs/config-storage), o CLI envolve cada campo sensível num compromisso HMAC por campo e transporta esses compromissos no envelope em texto simples. O servidor vê apenas digests hexadecimais: nunca os valores: mas pode aplicar knowledge-gates em cada escrita:

- **Verificação de pré-condição**: em `PUT /configs/<id>`, o cliente submete os digests que afirma conhecer para os caminhos que pretende mutar. O servidor compara com os compromissos do envelope armazenado. Incompatibilidade: `409 precondition_failed` com `mismatchedPaths`. Zero-knowledge: o servidor nunca vê texto simples.
- **Anti-downgrade**: o novo envelope deve comprometer cada caminho sensível que o envelope anterior comprometeu. Um agente não pode remover um caminho dos compromissos para contornar uma pré-condição futura.
- **Fixação da versão do envelope**: o servidor rejeita envelopes sem `envelopeVersion: 2` com `400 unsupported_envelope_version`. Sem janela de dupla aceitação.
- **Encriptação em repouso por campo** (lado do CLI): quando `encryption.mode === "master-password"`, cada segredo torna-se um blob AES-GCM individual cifrado pela password mestra. As leituras não desencadeiam uma solicitação a menos que o comando toque realmente num segredo (pelo que `rdc machine list` permanece sem solicitação).

A chave de compromisso (FCK) é derivada do lado do cliente a partir da CEK via `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` com um salt por configuração. A rotação de `fckSalt` invalida todos os compromissos anteriores, forçando um recálculo completo: útil ao rodar a CEK.
