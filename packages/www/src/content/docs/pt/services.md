---
title: Serviços
description: >-
  Faça deploy e gerencie serviços em contêineres usando Rediaccfiles, networking de
  serviços e autostart.
category: Guides
order: 5
language: pt
sourceHash: "011bc5d87114f105"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Serviços

Esta página cobre como fazer deploy e gerenciar serviços em contêineres: Rediaccfiles, networking de serviços, iniciar/parar, operações em massa e autostart.

## O Rediaccfile

O **Rediaccfile** é um script Bash que define como seus serviços são iniciados e parados. Ele é **carregado** (sourced, não executado como um processo separado), portanto suas funções compartilham o mesmo contexto de shell e têm acesso a todas as variáveis de ambiente exportadas. Deve ser nomeado `Rediaccfile` ou `rediaccfile` (sem distinção de maiúsculas/minúsculas) e colocado dentro do sistema de arquivos montado do repositório.

Os Rediaccfiles são descobertos em dois locais:
1. A **raiz** do caminho de montagem do repositório
2. **Subdiretórios de primeiro nível** do caminho de montagem (não recursivo)

Diretórios ocultos (nomes começando com `.`) são ignorados.

### Funções de Ciclo de Vida

Um Rediaccfile contém até duas funções:

| Função | Quando é executada | Propósito | Comportamento em erro |
|--------|-------------------|-----------|----------------------|
| `up()` | Ao iniciar | Iniciar serviços (por exemplo, `renet compose -- up -d`) | Falha na raiz é **crítica** (para tudo). Falhas em subdiretórios são **não críticas** (registadas, continua) |
| `down()` | Ao parar | Parar serviços (por exemplo, `renet compose -- down`) | **Melhor esforço** - falhas são registadas mas todos os Rediaccfiles são sempre tentados |

Ambas as funções são opcionais. Se uma função não estiver definida, é silenciosamente ignorada.

### Ordem de Execução

- **Ao iniciar (`up`):** Rediaccfile da raiz primeiro, depois subdiretórios em **ordem alfabética** (A a Z).
- **Ao parar (`down`):** Subdiretórios em **ordem alfabética inversa** (Z a A), depois raiz por último.

### Variáveis de Ambiente

Quando uma função Rediaccfile é executada, as seguintes variáveis de ambiente estão disponíveis:

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `REDIACC_WORKING_DIR` | Caminho de montagem do repositório | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID do repositório | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID de rede (inteiro) | `2816` |
| `DOCKER_HOST` | Socket Docker para o daemon isolado deste repositório | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada serviço definido em `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

As variáveis `{SERVICE}_IP` são geradas automaticamente a partir dos mapeamentos de slots em `.rediacc.json` e exportadas antes de suas funções Rediaccfile serem executadas. A convenção de nomenclatura converte o nome do serviço para maiúsculas com hífens substituídos por sublinhados e depois acrescenta `_IP`. Por exemplo, um serviço chamado `listmonk-app` com slot `0` torna-se `LISTMONK_APP_IP=127.0.11.2`.

> **Aviso: Não use `sudo docker` nos Rediaccfiles.** O comando `sudo` reinicia as variáveis de ambiente, o que significa que `DOCKER_HOST` é perdido e os comandos Docker passarão a ter como alvo o daemon do sistema em vez do daemon isolado do repositório. Isto quebra o isolamento de contêineres e pode causar conflitos de portas. O Rediacc bloqueará a execução se detectar `sudo docker` sem `-E`.
>
> Use `renet compose` em seus Rediaccfiles; trata automaticamente de `DOCKER_HOST`, injeta labels de networking para descoberta de rotas e configura o networking de serviços. Consulte [Networking](/pt/docs/networking) para detalhes sobre como os serviços são expostos via proxy reverso. Se chamar Docker diretamente, use `docker` sem `sudo`; as funções Rediaccfile já executam com privilégios suficientes. Se deve mesmo usar sudo, use `sudo -E docker` para preservar as variáveis de ambiente.
>
> `renet` é a ferramenta remota de baixo nível. Para fluxos de trabalho normais a partir de sua estação de trabalho, prefira os comandos `rdc` como `rdc repo up` e `rdc repo down`. Consulte [rdc vs renet](/pt/docs/rdc-vs-renet).

### Exemplo

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Importante:** Use sempre `renet compose --` em vez de `docker compose`. O wrapper `renet compose` aplica host networking, alocação de IPs e labels de descoberta de serviços necessários pelo renet-proxy. Capacidades de checkpoint/restore do CRIU são adicionadas a contêineres com o label `rediacc.checkpoint=true`. O uso direto de `docker compose` é rejeitado pela validação do Rediaccfile. Consulte [Networking](/pt/docs/networking) para detalhes.

### Labels de Capacidade

Por padrão, os contêineres executam com um conjunto mínimo de capacidades Linux. Um serviço opta por capacidades adicionais adicionando um label ao seu `docker-compose.yml`:

| Label | Concede | Para usar em |
|-------|---------|--------------|
| `rediacc.checkpoint=true` | `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` | Checkpoint/restore CRIU (migração ao vivo, guardar e retomar) |
| `rediacc.wireguard=true` | `NET_ADMIN` mais o dispositivo `/dev/net/tun` | Executar um cliente WireGuard dentro do contêiner |

```yaml
services:
  vpn:
    image: alpine
    labels:
      - "rediacc.wireguard=true"
```

`rediacc.wireguard` permite que um serviço estabeleça um túnel WireGuard, por exemplo para encaminhar um único processo por um endpoint remoto. Como todos os serviços executam com host networking, confine o túnel a um network namespace dentro do contêiner para não alterar o roteamento do host. Opções privilegiadas mais amplas como `privileged: true`, `pid: host` e `ipc: host` continuam rejeitadas pela validação independentemente dos labels.

### Disposição Multi-Serviço

Para projetos com múltiplos grupos de serviços independentes, use subdiretórios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raiz: configuração compartilhada
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Serviços de banco de dados
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # Servidor API
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

Ordem de execução para `up`: raiz, depois `backend`, `database`, `monitoring` (A-Z).
Ordem de execução para `down`: `monitoring`, `database`, `backend`, depois raiz (Z-A).

## Networking de Serviços (.rediacc.json)

Cada repositório obtém uma subnet /26 (64 IPs) no intervalo de loopback `127.x.x.x`. Os serviços vinculam-se a IPs de loopback únicos para poderem executar nas mesmas portas sem conflitos.

### O Arquivo .rediacc.json

Mapeia nomes de serviços para números de **slot**. Cada slot corresponde a um endereço IP único dentro da subnet do repositório.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Geração Automática a partir do Docker Compose

Você não precisa criar `.rediacc.json` manualmente. Quando executa `rdc repo up`, o Rediacc automaticamente:

1. Analisa todos os diretórios que contêm um Rediaccfile em busca de arquivos compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` ou `compose.yaml`)
2. Extrai nomes de serviços da seção `services:`
3. Atribui o próximo slot disponível a novos serviços
4. Guarda o resultado em `{repository}/.rediacc.json`

### Cálculo de IP

O IP para um serviço é calculado a partir do ID de rede do repositório e do slot do serviço. O ID de rede é distribuído pelo segundo, terceiro e quarto octetos de um endereço de loopback `127.x.y.z`. Os serviços começam no offset 2:

| Offset | Endereço | Propósito |
|--------|----------|-----------|
| .0 | `127.0.11.0` | Endereço de rede (reservado) |
| .1 | `127.0.11.1` | Gateway (reservado) |
| .2 a .62 | `127.0.11.2` a `127.0.11.62` | Serviços (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reservado) |

**Exemplo** para o ID de rede `2816` (`0x0B00`), endereço base `127.0.11.0`:

| Serviço | Slot | Endereço IP |
|---------|------|-------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Cada repositório suporta até **61 serviços** (slots 0 a 60).

### Usar IPs de Serviço no Docker Compose

Como cada repositório executa um daemon Docker isolado, `renet compose` configura automaticamente `network_mode: host` para todos os serviços. O kernel reescreve transparentemente as chamadas `bind()` para o IP de loopback atribuído ao serviço, portanto os serviços podem vincular-se a `0.0.0.0` ou `localhost` sem conflitos. Para conexões **a outros serviços**, use o **nome do serviço**. O renet injeta cada nome de serviço como hostname que sempre resolve para o IP correto, mesmo em forks:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Não é necessário listen_addresses explícito - o kernel reescreve o bind para o IP de loopback correto

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # use o nome do serviço
      LISTEN_ADDR: 0.0.0.0:8080                                      # o kernel reescreve para o IP do serviço
```

> **Nomes de serviço para conexões:** Use o **nome do serviço** (por exemplo, `postgres`, `redis`) para **conectar a** outros serviços; o renet mapeia automaticamente cada nome de serviço para seu IP de loopback via `/etc/hosts`. Incorporar `${POSTGRES_IP}` em strings de conexão armazenadas dentro de bancos de dados ou arquivos de configuração vai fixar o IP bruto, o que quebra o isolamento de fork e é um **erro de validação**. As variáveis `${SERVICE_IP}` ainda estão disponíveis para uso explícito, mas a vinculação é tratada automaticamente pelo kernel.

> **Nota:** Não adicione `network_mode: host` manualmente; `renet compose` injeta-o automaticamente. As políticas de reinício (por exemplo, `restart: always`) são seguras de usar; o renet remove-as automaticamente para compatibilidade com CRIU e o watchdog do router cuida da recuperação dos contêineres.

### Recuperação de Contêineres e Política de Reinício

O renet e o Docker discordam, propositadamente, sobre como tratar reinícios de contêineres. Compreender essa divisão é importante ao depurar por que um contêiner voltou ou não.

**Tradução da política de reinício.** Quando escreve `restart: always` (ou `unless-stopped`, ou `on-failure`) em seu arquivo compose, o renet **remove-o** ao sintetizar o deployment de compose real e o substitui por `restart: no`. O valor original é guardado em `.rediacc.json` do repositório em `services.<name>.restart_policy`. Isto impede que o reinício automático no nível do daemon do Docker interfira com o checkpoint/restore do CRIU (um reinício conduzido pelo daemon recomeçaria a partir de um estado pré-checkpoint desatualizado).

**Aplicação pelo watchdog.** O watchdog do router executa periodicamente em cada máquina. Em cada ciclo:

1. Lê `.rediacc.json` para cada repositório e encontra serviços com `restart_policy` recuperável.
2. Lista todos os contêineres do daemon desse repositório, identifica os parados e reinicia-os de acordo com a política guardada. Um período de graça de 30 segundos evita conflito com um operador que acabou de executar `docker stop`.
3. O mesmo ciclo também processa `/var/run/rediacc/cold-backup-<guid>.running.json` (consulte [Semântica de Cold Backup](backup-restore.md#cold-backup-semantics)). Os contêineres listados são reiniciados independentemente da política guardada, pois o sidecar significa "o renet parou esses propositadamente e deve ao operador um reinício."

**Por que `on-failure` pode parecer quebrado.** A política `on-failure` do Docker apenas reinicia quando o contêiner sai com um código não zero. Uma parada graciosa (exit 0) por `docker stop` ou um shutdown do daemon não é uma "falha" e NÃO aciona um reinício, nem pela lógica nativa do Docker nem pelo caminho de política guardada do watchdog. O sidecar de cold backup é a rede de segurança: qualquer contêiner que paramos propositadamente é reiniciado independentemente de sua política.

**Como interpretar o estado em tempo de execução:**

- `docker inspect <container>` -> `RestartPolicy.Name`: será sempre `no` para contêineres geridos pelo renet. Não confie nisso para a política semântica.
- `.rediacc.json` na raiz do repositório montado -> `services.<name>.restart_policy`: a intenção real.
- `docker ps --format '{{.Status}}'`: estado em tempo de execução.

**Como corrigir uma divergência.** Se a política guardada de um contêiner em `.rediacc.json` estiver errada (por exemplo, porque editou o compose mas nunca recriou o contêiner), execute novamente `rdc repo up --name <repo> -m <machine>`. O contêiner é recriado com a política atualizada registada.

> **Experimental:** A recuperação baseada em sidecar de cold backup e o flag `--sync-certs` em `rdc machine query` foram lançados no renet 0.9+. Versões anteriores dependem apenas de `restart_policy` guardado para recuperação pelo watchdog, o que pode deixar contêineres `on-failure` parados após um cold backup.

> **O bridge networking do Docker está desativado para daemons por repositório.** Cada daemon por repositório (`FlavorRediacc`) é configurado com `"bridge": "none"` e `"iptables": false`. Um simples `docker run <image>` dentro de um shell de repositório ainda será iniciado, mas o contêiner obtém apenas uma interface de loopback e não tem DNS nem conectividade de saída. Isto é por design, uma vez que o isolamento de loopback entre repositórios é aplicado por hooks cgroup eBPF que um contêiner com bridge contornaria. Os serviços de produção devem usar `renet compose` (que injeta host networking automaticamente); para depuração ad-hoc, passe `--network host` explicitamente: `docker run --rm --network host -it ubuntu bash`.
>
> Os daemons Hub por usuário (`FlavorHub`, usados em ambientes de desenvolvimento) são a exceção: definem `bridge="docker0"`, `iptables=true` e `live-restore=true` para que contêineres executados pelo usuário tenham bridge networking normal e conectividade de saída.

> **Nota:** Os repositórios fork obtêm rotas automáticas sob o subdomínio do pai: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Os domínios personalizados são ignorados para forks.

## Iniciando Serviços

Montar o repositório e iniciar todos os serviços:

```bash
rdc repo up --name my-app -m server-1
```

| Opção | Descrição |
|-------|-----------|
| `--detach` | Retorna assim que os contêineres estiverem iniciados; as verificações de saúde continuam em segundo plano |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

A sequência de execução é:
1. Montar o repositório encriptado com LUKS (monta automaticamente se não estiver montado)
2. Iniciar o daemon Docker isolado
3. Gerar automaticamente `.rediacc.json` a partir dos arquivos compose
4. Executar `up()` em todos os Rediaccfiles (ordem A-Z)

Após o deployment, a saída mostra uma seção **PROXY ROUTES** com os URLs reais de cada serviço. Os serviços com labels Traefik personalizadas (por exemplo, `traefik.http.routers.myapp.rule=Host(...)`) mostram seus domínios personalizados como URLs primários:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

Os serviços sem labels Traefik personalizadas mostram apenas a rota gerada automaticamente. Use estes URLs (não o padrão genérico mostrado pelo CLI) para acesso via browser, chamadas API e configuração entre serviços.

### Inicialização em Modo Detached

Com `--detach`, o comando retorna assim que os contêineres estiverem iniciados, sem aguardar a conclusão das verificações de saúde. A inicialização termina em segundo plano: o proxy tenta reconectar-se aos serviços de upstream até que cada um esteja vinculado, e as rotas se recuperam sozinhas. Acompanhe o progresso com `rdc machine query --containers --name <machine>`. Ideal para forks descartáveis e scripts em loop onde os serviços não precisam estar prontos antes da próxima etapa.

### Verificação de Prontidão

Após `up()`, o renet sonda cada serviço HTTP até que ele aceite conexões TCP, evitando que a primeira requisição do browser receba um erro 502 do proxy. Serviços cujos contêineres definem um health check do Docker são tratados diretamente: um contêiner saudável pula a sonda, e um ainda dentro do `start_period` registra uma nota informativa em vez de um aviso. A sonda desiste após 15 segundos (substitua com a variável de ambiente `REDIACC_READINESS_TIMEOUT`, em segundos, na máquina); inicializações em modo detached a ignoram completamente.

## Parando Serviços

```bash
rdc repo down --name my-app -m server-1
```

| Opção | Descrição |
|-------|-----------|
| `--unmount` | Desmontar o repositório encriptado após parar. Se isto não tiver efeito, use `rdc repo unmount` separadamente. |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

A sequência de execução é:
1. Executar `down()` em todos os Rediaccfiles (ordem inversa Z-A, melhor esforço)
2. Parar o daemon Docker isolado (se `--unmount`)
3. Desmontar e fechar o volume encriptado LUKS (se `--unmount`)

## Operações em Massa

Iniciar ou parar todos os repositórios em uma máquina de uma vez:

```bash
rdc repo up -m server-1
```

| Opção | Descrição |
|-------|-----------|
| `--include-forks` | Incluir repositórios com fork |
| `--mount-only` | Apenas montar, sem iniciar contêineres |
| `--dry-run` | Mostrar o que seria feito |
| `--parallel` | Executar operações em paralelo |
| `--concurrency <n>` | Número máximo de operações concorrentes (padrão: 3) |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Autostart no Arranque

Por padrão, os repositórios devem ser montados e iniciados manualmente após um reinício do servidor. O **Autostart** configura os repositórios para montarem automaticamente, iniciarem o Docker e executarem `up()` do Rediaccfile quando o servidor arranca.

### Como Funciona

Quando ativa o autostart para um repositório:

1. Um arquivo de chave LUKS aleatório de 256 bytes é gerado e adicionado ao slot 1 do LUKS do repositório (o slot 0 permanece a frase-passe do usuário)
2. O arquivo de chave é guardado em `{datastore}/.credentials/keys/{guid}.key` com permissões `0600` (apenas root)
3. Um serviço systemd (`rediacc-autostart`) executa no arranque para montar todos os repositórios ativos e iniciar seus serviços

No shutdown, o serviço para graciosamente todos os serviços (`down()` do Rediaccfile), para os daemons Docker e fecha os volumes LUKS.

> **Nota de segurança:** Ativar o autostart guarda um arquivo de chave LUKS no disco do servidor. Qualquer pessoa com acesso root ao servidor pode montar o repositório sem a frase-passe. Avalie isto com base em seu modelo de ameaça.

### Ativar

```bash
rdc repo autostart enable --name my-app -m server-1
```

Será solicitada a frase-passe do repositório.

### Ativar Todos

```bash
rdc repo autostart enable -m server-1
```

### Desativar

```bash
rdc repo autostart disable --name my-app -m server-1
```

Isto remove o arquivo de chave e elimina o slot 1 do LUKS.

### Atualização do Arquivo de Chave no Deploy

Quando o autostart está ativo, `rdc repo up` valida o arquivo de chave do slot 1 do LUKS.
Se o arquivo de chave no disco ainda corresponder ao slot LUKS, nenhuma alteração é feita.

Após transferir um repositório entre máquinas via `repo push` / `repo pull`,
o arquivo de chave na nova máquina não corresponderá. Neste caso, `repo up` automaticamente
regenera o arquivo de chave e atualiza o slot 1 do LUKS. Você verá mensagens de log:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

Isto é seguro; o slot 0 (sua frase-passe) nunca é modificado. Se o autostart não estiver
ativo, a verificação é silenciosamente ignorada. As falhas não são fatais e não bloqueiam
o deployment.

### Listar Estado

```bash
rdc repo autostart list -m server-1
```

Para mais detalhes sobre como o reconciliador periódico recupera repositórios que ficam inativos após o arranque, consulte [Autostart e Recuperação](/pt/docs/autostart-recovery).

## Exemplo Completo

Faz o deploy de uma aplicação web com PostgreSQL, Redis e um servidor API.

### 1. Configurar

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Montar e Preparar

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Criar os Arquivos da Aplicação

Dentro do repositório, crie:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Iniciar

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Ativar Autostart

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Usar segredos por repositório no compose

O marcador `POSTGRES_PASSWORD: changeme` acima é adequado para um tutorial, mas aplicações reais precisam de credenciais reais, e colocá-las no arquivo compose (ou em um arquivo `.env` dentro do repositório) significa que um fork também as herda. Para credenciais no momento do deployment, use `rdc repo secret`. Os valores vivem fora da imagem do repositório encriptado, portanto forks começam com um mapa de segredos vazio.

Dois modos de entrega funcionam no compose:

**Modo `env`**. Interpole via `${REDIACC_SECRET_<KEY>}` em qualquer valor `environment:`. O wrapper renet passa o valor para o ambiente do contêiner no momento do deployment.

**Modo `file`**. O valor fica em um arquivo tmpfs do lado do host em `/var/run/rediacc/secrets/<networkID>/<KEY>`, e você o monta no contêiner via o bloco `secrets:` padrão do Docker compose. O contêiner lê `/run/secrets/<key>`. Prefira este modo para qualquer coisa sensível. Os valores nunca aparecem em `docker inspect` ou `/proc/<pid>/environ`.

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Insira os valores com `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` e o equivalente em modo file. Consulte [Repositórios - Segredos](/pt/docs/repositories#secrets) para o guia completo e [Segredos por repositório](/pt/docs/rdc-cheat-sheet#per-repo-secrets) na cheat sheet para a referência de comandos.

> **Os caminhos entre repositórios são rejeitados no momento da validação.** Um `secrets: file:` do compose (ou `configs: file:`, ou `env_file:`) que aponte para o diretório `/var/run/rediacc/secrets/<other-networkID>/` de outro repositório é rejeitado pelo wrapper renet antes do docker compose ser executado. `--unsafe` NÃO substitui este comportamento. Defesa em profundidade: a sandbox Landlock em torno do shell do Rediaccfile limita as leituras ao diretório de segredos da rede atual, portanto um `cat /var/run/rediacc/secrets/<other>/X` a partir do bash do Rediaccfile falha com EACCES mesmo que contorne o validador YAML. Você não precisa ativar isto; está ativo por padrão em cada `repo up`.
