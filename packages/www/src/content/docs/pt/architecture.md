---
title: Arquitetura
description: >-
  Como a Rediacc funciona: arquitetura de duas ferramentas, deteção de adaptador, modelo de segurança e
  estrutura de configuração.
category: Concepts
order: 0
language: pt
sourceHash: "83f6a9a2b0c8bae2"
sourceCommit: "5fab1177d6ceae5211c25cf8fa0176d67259d40e"
---

# Arquitetura

Assim: rdc na sua workstation, renet nos seus servidores, comunicando via SSH. Toda a arquitetura da Rediacc assenta nessa divisão. Esta página cobre como as duas ferramentas dividem responsabilidades, como a deteção do adaptador encaminha o estado, como o modelo de segurança se parece e como a configuração é estruturada.

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

Todo o estado reside num ficheiro de configuração na sua workstation (por exemplo, `~/.config/rediacc/rediacc.json`).

- Ligações SSH diretas às máquinas
- Sem serviços externos necessários
- A configuração predefinida é criada automaticamente no primeiro uso do CLI. As configurações nomeadas são criadas com `rdc config init --name <name>`
- Sincronização opcional de configuração encriptada guarda o mesmo ficheiro no arquivo de configuração, com âmbito por equipa

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

## Backends de Armazenamento

Um datastore é um pool de armazenamento por máquina que contém as imagens dos repositórios. Tem dois backends, escolhidos no momento do `datastore init`:

- **Local (predefinição)**: um sistema de ficheiros BTRFS assente num loop device no próprio disco da máquina. As imagens dos repositórios são ficheiros encriptados com LUKS dentro dele; o fork é um único `cp --reflink=always`. É o backend usado por todas as implementações de máquina única, e não precisa de nada além do disco do servidor.
- **Ceph RBD**: o datastore reside numa imagem RBD mapeada a partir de um cluster Ceph externo, com BTRFS simples por cima (sem LUKS nesta camada, já que os nós Ceph nunca abrem LUKS). O fork e a arquitetura multi-cliente só de leitura usam as primitivas nativas de copy-on-write do RBD (snapshot, protect, clone) e namespaces RADOS para isolamento por inquilino.

Ambos os backends apresentam o mesmo modelo de repositório a tudo o que está acima deles, pelo que os comandos `repo`, os backups e os forks funcionam de forma idêntica. A diferença está em onde vivem os bytes e em qual mecanismo de copy-on-write um fork usa (reflink BTRFS versus clone RBD). Consulte [Configuração da Máquina](/en/docs/setup) para saber como inicializar cada backend e [Referência do Servidor](/en/docs/server-reference) para os comandos de datastore ao nível do renet.

## Repositórios Kubernetes

Além dos repositórios Docker, uma máquina pode alojar **clusters**. A Rediacc mantém a mentalidade de repositório invertendo o modelo de objetos habitual: o cluster é o contentor, e um repositório Kubernetes é um namespace dentro dele.

- O estado do cluster (o diretório de dados do k3s por nó) vive em ficheiros de imagem copy-on-write suportados pelo datastore, um por nó, pelo que um cluster faz fork e migra como um conjunto de imagens.
- Um repositório Kubernetes é o namespace `<repo>` mais os seus volumes. Os volumes persistentes são unidades copy-on-write **separadas** (imagens RBD no Ceph, ou pequenos ficheiros de imagem do datastore através de um provisionador de PV local), nunca diretórios dentro de uma única imagem de cluster opaca. Essa separação é o que torna os forks por repositório independentemente copy-on-write.
- O `KUBECONFIG` é injetado como o análogo do `DOCKER_HOST`, e um wrapper `renet kube` aplica manifestos a partir de `up()` da mesma forma que o `renet compose` executa o Docker.

A clonagem e a relocalização de um cluster inteiro residem em `rdc cluster fork` e `rdc cluster migrate`. Esta é a capacidade diferenciadora: fazer fork ou mover um cluster em execução, incluindo os seus dados, para outra máquina ou centro de dados com um curto período de corte. Consulte o guia [Kubernetes](/en/docs/kubernetes) para o modelo completo, os comandos e os números de corte medidos.

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
