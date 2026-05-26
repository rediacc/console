---
title: Serviços
description: >-
  Faça deploy e gira serviços em contentores usando Rediaccfiles, networking de
  serviços e autostart.
category: Guides
order: 5
language: pt
sourceHash: "ee2c8fc465b846e4"
sourceCommit: "a3b80f4e653e80766813a8c1d7ef563f00904147"
---

# Servicos

Esta pagina cobre como fazer deploy e gerir servicos em contentores: Rediaccfiles, networking de servicos, iniciar/parar, operacoes em massa e autostart.

## O Rediaccfile

O **Rediaccfile** e um script Bash que define como os seus servicos sao iniciados e parados. E **carregado** (sourced, nao executado como processo separado), pelo que as suas funcoes partilham o mesmo contexto de shell e tem acesso a todas as variaveis de ambiente exportadas. Deve chamar-se `Rediaccfile` ou `rediaccfile` (sem distincao de maiusculas/minusculas) e ser colocado dentro do sistema de ficheiros montado do repositorio.

Os Rediaccfiles sao descobertos em duas localizacoes:
1. A **raiz** do caminho de montagem do repositorio
2. **Subdiretorios de primeiro nivel** do caminho de montagem (nao recursivo)

Os diretorios ocultos (nomes que comecam por `.`) sao ignorados.

### Funcoes de Ciclo de Vida

Um Rediaccfile contem ate duas funcoes:

| Funcao | Quando e executada | Proposito | Comportamento em caso de erro |
|--------|-------------------|-----------|-------------------------------|
| `up()` | Ao iniciar | Iniciar servicos (por exemplo, `renet compose -- up -d`) | Falha na raiz e **critica** (para tudo). Falhas em subdiretorios sao **nao criticas** (registadas, continua) |
| `down()` | Ao parar | Parar servicos (por exemplo, `renet compose -- down`) | **Melhor esforco** -- as falhas sao registadas mas todos os Rediaccfiles sao sempre tentados |

Ambas as funcoes sao opcionais. Se uma funcao nao estiver definida, e silenciosamente ignorada.

### Ordem de Execucao

- **Ao iniciar (`up`):** Rediaccfile da raiz primeiro, depois subdiretorios por **ordem alfabetica** (A a Z).
- **Ao parar (`down`):** Subdiretorios por **ordem alfabetica inversa** (Z a A), depois a raiz por ultimo.

### Variaveis de Ambiente

Quando uma funcao Rediaccfile e executada, as seguintes variaveis de ambiente estao disponiveis:

| Variavel | Descricao | Exemplo |
|----------|-----------|---------|
| `REDIACC_WORKING_DIR` | Caminho de montagem do repositorio | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID do repositorio | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID de rede (inteiro) | `2816` |
| `DOCKER_HOST` | Socket Docker para o daemon isolado deste repositorio | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada servico definido em `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

As variaveis `{SERVICE}_IP` sao geradas automaticamente a partir dos mapeamentos de slots em `.rediacc.json` e exportadas antes das suas funcoes Rediaccfile serem executadas. A convencao de nomenclatura converte o nome do servico para maiusculas com hifens substituidos por sublinhados e depois acrescenta `_IP`. Por exemplo, um servico chamado `listmonk-app` com slot `0` torna-se `LISTMONK_APP_IP=127.0.11.2`.

> **Aviso: Nao use `sudo docker` nos Rediaccfiles.** O comando `sudo` reinicia as variaveis de ambiente, o que significa que `DOCKER_HOST` e perdido e os comandos Docker passarao a ter como alvo o daemon do sistema em vez do daemon isolado do repositorio. Isto quebra o isolamento de contentores e pode causar conflitos de portas. O Rediacc bloqueara a execucao se detectar `sudo docker` sem `-E`.
>
> Use `renet compose` nos seus Rediaccfiles; trata automaticamente de `DOCKER_HOST`, injeta labels de networking para descoberta de rotas e configura o networking de servicos. Consulte [Networking](/pt/docs/networking) para detalhes sobre como os servicos sao expostos via proxy reverso. Se chamar Docker directamente, use `docker` sem `sudo`; as funcoes Rediaccfile ja correm com privilegios suficientes. Se tiver mesmo de usar sudo, use `sudo -E docker` para preservar as variaveis de ambiente.
>
> `renet` e a ferramenta remota de baixo nivel. Para fluxos de trabalho normais a partir do seu computador de trabalho, prefira os comandos `rdc`, como `rdc repo up` e `rdc repo down`. Consulte [rdc vs renet](/pt/docs/rdc-vs-renet).

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

> **Importante:** Use sempre `renet compose --` em vez de `docker compose`. O wrapper `renet compose` aplica host networking, alocacao de IPs e labels de descoberta de servicos necessarios pelo renet-proxy. As capacidades de checkpoint/restore do CRIU sao adicionadas a contentores com a label `rediacc.checkpoint=true`. O uso directo de `docker compose` e rejeitado pela validacao do Rediaccfile. Consulte [Networking](/pt/docs/networking) para detalhes.

### Disposicao Multi-Servico

Para projectos com multiplos grupos de servicos independentes, use subdiretorios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raiz: configuracao partilhada
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Servicos de base de dados
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # Servidor API
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

Ordem de execucao para `up`: raiz, depois `backend`, `database`, `monitoring` (A-Z).
Ordem de execucao para `down`: `monitoring`, `database`, `backend`, depois a raiz (Z-A).

## Networking de Servicos (.rediacc.json)

Cada repositorio obtem uma subnet /26 (64 IPs) no intervalo de loopback `127.x.x.x`. Os servicos fazem bind a IPs de loopback unicos para poderem correr nas mesmas portas sem conflitos.

### O Ficheiro .rediacc.json

Mapeia nomes de servicos para numeros de **slot**. Cada slot corresponde a um endereco IP unico dentro da subnet do repositorio.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Geracao Automatica a partir do Docker Compose

Nao precisa de criar `.rediacc.json` manualmente. Quando executa `rdc repo up`, o Rediacc automaticamente:

1. Analisa todos os diretorios que contem um Rediaccfile em busca de ficheiros compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` ou `compose.yaml`)
2. Extrai nomes de servicos da seccao `services:`
3. Atribui o proximo slot disponivel a novos servicos
4. Guarda o resultado em `{repository}/.rediacc.json`

### Calculo de IP

O IP para um servico e calculado a partir do ID de rede do repositorio e do slot do servico. O ID de rede e distribuido pelo segundo, terceiro e quarto octetos de um endereco de loopback `127.x.y.z`. Os servicos comecam no offset 2:

| Offset | Endereco | Proposito |
|--------|----------|-----------|
| .0 | `127.0.11.0` | Endereco de rede (reservado) |
| .1 | `127.0.11.1` | Gateway (reservado) |
| .2 a .62 | `127.0.11.2` a `127.0.11.62` | Servicos (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reservado) |

**Exemplo** para o ID de rede `2816` (`0x0B00`), endereco base `127.0.11.0`:

| Servico | Slot | Endereco IP |
|---------|------|-------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Cada repositorio suporta ate **61 servicos** (slots 0 a 60).

### Usar IPs de Servico no Docker Compose

Como cada repositorio executa um daemon Docker isolado, `renet compose` configura automaticamente `network_mode: host` para todos os servicos. O kernel reescreve transparentemente as chamadas `bind()` para o IP de loopback atribuido ao servico, pelo que os servicos podem fazer bind a `0.0.0.0` ou `localhost` sem conflitos. Para conexoes **a outros servicos**, use o **nome do servico**; o renet injeta cada nome de servico como hostname que resolve sempre para o IP correcto, mesmo em forks:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Nao e necessario listen_addresses explicito - o kernel reescreve o bind para o IP de loopback correcto

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # use o nome do servico
      LISTEN_ADDR: 0.0.0.0:8080                                      # o kernel reescreve para o IP do servico
```

> **Nomes de servico para conexoes:** Use o **nome do servico** (por exemplo, `postgres`, `redis`) para **conectar a** outros servicos; o renet mapeia automaticamente cada nome de servico para o seu IP de loopback via `/etc/hosts`. Incorporar `${POSTGRES_IP}` em strings de conexao guardadas dentro de bases de dados ou ficheiros de configuracao vai fixar o IP bruto, o que quebra o isolamento de fork e e um **erro de validacao**. As variaveis `${SERVICE_IP}` estao ainda disponiveis para uso explicito, mas o binding e tratado automaticamente pelo kernel.

> **Nota:** Nao adicione `network_mode: host` manualmente; `renet compose` injeta-o automaticamente. As politicas de reinicio (por exemplo, `restart: always`) sao seguras de usar; o renet remove-as automaticamente para compatibilidade com CRIU e o watchdog do router trata da recuperacao dos contentores.

### Recuperacao de Contentores e Politica de Reinicio

O renet e o Docker discordam, propositadamente, sobre como tratar os reinicios de contentores. Compreender esta divisao e importante quando se depura porque um contentor voltou ou nao ao estado anterior.

**Traducao da politica de reinicio.** Quando escreve `restart: always` (ou `unless-stopped`, ou `on-failure`) no seu ficheiro compose, o renet **remove-o** ao sintetizar o deployment de compose real e substitui-o por `restart: no`. O valor original e guardado em `.rediacc.json` do repositorio em `services.<name>.restart_policy`. Isto impede que o reinicio automatico ao nivel do daemon do Docker interfira com o checkpoint/restore do CRIU (um reinicio conduzido pelo daemon recomearia a partir de um estado pre-checkpoint desactualizado).

**Aplicacao pelo watchdog.** O watchdog do router corre periodicamente em cada maquina. Em cada ciclo:

1. Le `.rediacc.json` para cada repositorio e encontra servicos com `restart_policy` recuperavel.
2. Lista todos os contentores do daemon desse repositorio, identifica os parados e reinicia-os de acordo com a politica guardada. Um periodo de graca de 30 segundos evita conflito com um operador que acabou de executar `docker stop`.
3. O mesmo ciclo tambem processa `/var/run/rediacc/cold-backup-<guid>.running.json` (consulte [Semantica de Cold Backup](backup-restore.md#cold-backup-semantics)). Os contentores listados sao reiniciados independentemente da politica guardada, pois o sidecar significa "o renet parou estes propositadamente e deve ao operador um reinicio."

**Por que `on-failure` pode parecer nao funcionar.** A politica `on-failure` do Docker so reinicia quando o contentor sai com um codigo nao zero. Uma paragem graceful (exit 0) por `docker stop` ou um shutdown do daemon nao e uma "falha" e NAO aciona um reinicio, nem pela logica nativa do Docker nem pelo caminho de politica guardada do watchdog. O sidecar de cold backup e a rede de seguranca: qualquer contentor que paramos propositadamente e reiniciado independentemente da sua politica.

**Como interpretar o estado em tempo de execucao:**

- `docker inspect <container>` -> `RestartPolicy.Name`: sera sempre `no` para contentores geridos pelo renet. Nao confie nisto para a politica semantica.
- `.rediacc.json` na raiz do repositorio montado -> `services.<name>.restart_policy`: a intencao real.
- `docker ps --format '{{.Status}}'`: estado em tempo de execucao.

**Como corrigir um desvio.** Se a politica guardada de um contentor em `.rediacc.json` estiver errada (por exemplo, porque editou o compose mas nunca recriou o contentor), execute novamente `rdc repo up --name <repo> -m <machine>`. O contentor e recriado com a politica actualizada registada.

> **Experimental:** A recuperacao baseada em sidecar de cold backup e a flag `--sync-certs` em `rdc machine query` foram lancadas no renet 0.9+. Versoes anteriores dependem apenas de `restart_policy` guardado para recuperacao pelo watchdog, o que pode deixar contentores `on-failure` parados apos um cold backup.

> **O bridge networking do Docker esta desactivado para daemons por repositorio.** Cada daemon por repositorio (`FlavorRediacc`) e configurado com `"bridge": "none"` e `"iptables": false`. Um simples `docker run <image>` dentro de uma shell de repositorio ainda sera lancado, mas o contentor obtem apenas uma interface de loopback e nao tem DNS nem conectividade de saida. Isto e por design, uma vez que o isolamento de loopback entre repositorios e aplicado por hooks cgroup eBPF que um contentor com bridge contornaria. Os servicos de producao devem usar `renet compose` (que injeta host networking automaticamente); para depuracao ad-hoc, passe `--network host` explicitamente: `docker run --rm --network host -it ubuntu bash`.
>
> Os daemons Hub por utilizador (`FlavorHub`, usados em ambientes de desenvolvimento) sao a excecao: definem `bridge="docker0"`, `iptables=true` e `live-restore=true` para que os contentores executados pelo utilizador tenham bridge networking normal e conectividade de saida.

> **Nota:** Os repositorios fork obtem rotas automaticas sob o subdominio do pai: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Os dominios personalizados sao ignorados para forks.

## Iniciar Servicos

Montar o repositorio e iniciar todos os servicos:

```bash
rdc repo up --name my-app -m server-1
```

| Opcao | Descricao |
|-------|-----------|
| `--skip-router-restart` | Ignorar o reinicio do servidor de rotas apos a operacao |

A sequencia de execucao e:
1. Montar o repositorio encriptado com LUKS (monta automaticamente se nao estiver montado)
2. Iniciar o daemon Docker isolado
3. Gerar automaticamente `.rediacc.json` a partir dos ficheiros compose
4. Executar `up()` em todos os Rediaccfiles (ordem A-Z)

Apos o deployment, o resultado mostra uma seccao **PROXY ROUTES** com os URLs reais de cada servico. Os servicos com labels Traefik personalizadas (por exemplo, `traefik.http.routers.myapp.rule=Host(...)`) mostram os seus dominios personalizados como URLs primarios:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

Os servicos sem labels Traefik personalizadas mostram apenas a rota gerada automaticamente. Use estes URLs (nao o padrao generico mostrado pelo CLI) para acesso via browser, chamadas API e configuracao entre servicos.

## Parar Servicos

```bash
rdc repo down --name my-app -m server-1
```

| Opcao | Descricao |
|-------|-----------|
| `--unmount` | Desmontar o repositorio encriptado apos parar. Se isto nao tiver efeito, use `rdc repo unmount` separadamente. |
| `--skip-router-restart` | Ignorar o reinicio do servidor de rotas apos a operacao |

A sequencia de execucao e:
1. Executar `down()` em todos os Rediaccfiles (ordem inversa Z-A, melhor esforco)
2. Parar o daemon Docker isolado (se `--unmount`)
3. Desmontar e fechar o volume encriptado LUKS (se `--unmount`)

## Operacoes em Massa

Iniciar ou parar todos os repositorios numa maquina de uma vez:

```bash
rdc repo up -m server-1
```

| Opcao | Descricao |
|-------|-----------|
| `--include-forks` | Incluir repositorios com fork |
| `--mount-only` | Apenas montar, sem iniciar contentores |
| `--dry-run` | Mostrar o que seria feito |
| `--parallel` | Executar operacoes em paralelo |
| `--concurrency <n>` | Numero maximo de operacoes concorrentes (padrao: 3) |
| `--skip-router-restart` | Ignorar o reinicio do servidor de rotas apos a operacao |

## Autostart no Arranque

Por padrao, os repositorios devem ser montados e iniciados manualmente apos um reinicio do servidor. O **Autostart** configura os repositorios para montarem automaticamente, iniciarem o Docker e executarem `up()` do Rediaccfile quando o servidor arranca.

### Como Funciona

Quando activa o autostart para um repositorio:

1. E gerado um keyfile LUKS aleatorio de 256 bytes e adicionado ao slot 1 do LUKS do repositorio (o slot 0 permanece a frase-passe do utilizador)
2. O keyfile e guardado em `{datastore}/.credentials/keys/{guid}.key` com permissoes `0600` (apenas root)
3. Um servico systemd (`rediacc-autostart`) corre no arranque para montar todos os repositorios activos e iniciar os seus servicos

No shutdown, o servico para graciosamente todos os servicos (`down()` do Rediaccfile), para os daemons Docker e fecha os volumes LUKS.

> **Nota de seguranca:** Activar o autostart guarda um keyfile LUKS no disco do servidor. Qualquer pessoa com acesso root ao servidor pode montar o repositorio sem a frase-passe. Avalie isto com base no seu modelo de ameaca.

### Activar

```bash
rdc repo autostart enable --name my-app -m server-1
```

Sera solicitada a frase-passe do repositorio.

### Activar Todos

```bash
rdc repo autostart enable -m server-1
```

### Desactivar

```bash
rdc repo autostart disable --name my-app -m server-1
```

Isto remove o keyfile e elimina o slot 1 do LUKS.

### Actualizacao do Keyfile no Deploy

Quando o autostart esta activo, `rdc repo up` valida o keyfile do slot 1 do LUKS.
Se o keyfile no disco ainda corresponder ao slot LUKS, nao sao feitas alteracoes.

Apos transferir um repositorio entre maquinas via `repo push` / `repo pull`,
o keyfile na nova maquina nao correspondra. Neste caso, `repo up` regenera automaticamente
o keyfile e actualiza o slot 1 do LUKS. Vera mensagens de log:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

Isto e seguro; o slot 0 (a sua frase-passe) nunca e modificado. Se o autostart nao estiver
activo, a verificacao e silenciosamente ignorada. As falhas nao sao fatais e nao bloqueiam
o deployment.

### Listar Estado

```bash
rdc repo autostart list -m server-1
```

Para mais detalhes sobre como o reconciliador periódico recupera repositórios que ficam inactivos após o arranque, consulte [Autostart e Recuperação](/pt/docs/autostart-recovery).

## Exemplo Completo

Faz o deploy de uma aplicacao web com PostgreSQL, Redis e um servidor API.

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

### 3. Criar os Ficheiros da Aplicacao

Dentro do repositorio, crie:

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

### 5. Activar Autostart

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Usar segredos por repositorio no compose

O marcador `POSTGRES_PASSWORD: changeme` acima e adequado para um tutorial, mas as aplicacoes reais precisam de credenciais reais, e colocá-las no ficheiro compose (ou num ficheiro `.env` dentro do repositorio) significa que um fork tambem as herda. Para credenciais no momento do deployment, use `rdc repo secret`. Os valores vivem fora da imagem do repositorio encriptado, pelo que os forks comecam com um mapa de segredos vazio.

Dois modos de entrega funcionam no compose:

**Modo `env`**. Interpole via `${REDIACC_SECRET_<KEY>}` em qualquer valor `environment:`. O wrapper renet passa o valor para o ambiente do contentor no momento do deployment.

**Modo `file`**. O valor fica num ficheiro tmpfs do lado do host em `/var/run/rediacc/secrets/<networkID>/<KEY>`, e monta-o no contentor via o bloco `secrets:` padrao do Docker compose. O contentor le `/run/secrets/<key>`. Prefira este modo para qualquer coisa sensivel. Os valores nunca aparecem em `docker inspect` ou `/proc/<pid>/environ`.

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

Insira os valores com `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` e o equivalente em modo file. Consulte [Repositorios - Segredos](/pt/docs/repositories#secrets) para o guia completo e [Segredos por repositorio](/pt/docs/rdc-cheat-sheet#per-repo-secrets) na cheat sheet para a referencia de comandos.

> **Os caminhos entre repositorios sao rejeitados no momento da validacao.** Um `secrets: file:` do compose (ou `configs: file:`, ou `env_file:`) que aponte para o diretorio `/var/run/rediacc/secrets/<other-networkID>/` de outro repositorio e rejeitado pelo wrapper renet antes do docker compose ser executado. `--unsafe` NAO substitui este comportamento. Defesa em profundidade: a sandbox Landlock em torno da shell do Rediaccfile limita as leituras ao diretorio de segredos da rede actual, pelo que um `cat /var/run/rediacc/secrets/<other>/X` a partir do bash do Rediaccfile falha com EACCES mesmo que contorne o validador YAML. Nao precisa de activar isto; esta activo por padrao em cada `repo up`.
