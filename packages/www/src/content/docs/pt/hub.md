---
sourceHash: "6fa16a1c73af497e"
title: "Hub"
description: "Forneça ambientes contentorizados autenticados por utilizador com daemons Docker por utilizador, seleção de múltiplos modelos, checkpoint/restauro CRIU, registos de auditoria e recolha de lixo do data-root."
category: "Guides"
order: 14
language: pt
---

# Hub

O Hub fornece ambientes contentorizados por utilizador protegidos por autenticação OAuth. Os utilizadores visitam um único URL, autenticam-se com qualquer fornecedor OAuth2 e são encaminhados de forma transparente para o seu contentor pessoal. Os contentores são criados a pedido, cada utilizador tem o seu próprio daemon Docker isolado, e as sessões inativas são guardadas via CRIU checkpoint para retoma instantânea.

Tudo é configurado através de etiquetas do `docker-compose.yml`. O próprio Hub executa como um serviço systemd do anfitrião materializado pelo comando `renet hub install` a partir do ficheiro compose do seu repositório. Os repositórios definem o comportamento; o Hub trata da autenticação, encaminhamento, ciclo de vida e isolamento por utilizador.

## Como Funciona

1. Um utilizador visita `code.example.com` (ou `term.`, `desktop.`, ou qualquer outro prefixo configurado).
2. O Hub verifica se existe um cookie de sessão. Se não existir, o utilizador é redirecionado para o fornecedor OAuth2 configurado (Nextcloud, Keycloak, GitHub, etc.).
3. Após autenticação, o Hub identifica o utilizador e procura o seu contentor.
4. Se não existir contentor, o Hub provisiona um daemon Docker dedicado para esse utilizador no anfitrião e depois cria o contentor.
5. O pedido é encaminhado de forma reversa para o contentor do utilizador através da rede de loopback.
6. Os contentores inativos são guardados via CRIU checkpoint; o daemon por utilizador é parado para libertar memória. No próximo login, o daemon reinicia e o CRIU restaura o estado do contentor em segundos.

## Início Rápido

Adicione o Hub como serviço no `docker-compose.yml` do seu repositório. O serviço é marcado como `install_as=systemd` para que execute como serviço do anfitrião em vez de contentor Docker (necessário para a gestão de daemons por utilizador, que usa systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Mapeamento de rotas: prefixo de subdomínio -> porta nos contentores do utilizador
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Modelo de contentor
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Rotas Traefik (file-provider; rediacc-router também lê estas etiquetas)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Crie `hub/.env` com as credenciais do seu fornecedor OAuth2:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Instale a unidade systemd do anfitrião (uma única vez, requer root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Este comando lê os serviços `install_as=systemd` e escreve:

- `/etc/systemd/system/rediacc-hub.service` (a unidade)
- `/etc/rediacc/hub/hub.labels.yaml` (as etiquetas do modelo)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (rotas de file-provider Traefik)

Depois `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Para remover: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Referência do Comando de Instalação

| Comando | Finalidade |
|---------|---------|
| `sudo renet hub install <compose-file>` | Traduz os serviços `install_as=systemd` do ficheiro compose em artefactos do anfitrião e inicia a unidade. |
| `sudo renet hub uninstall <compose-file>` | Para, desativa e remove todos os artefactos dos serviços. Os data-roots em `<workspace>/<user>-docker/` são preservados. |
| `sudo renet hub gc <workspace-dir>` | Elimina data-roots por utilizador abandonados (predefinição: mais antigos de 30 dias sem daemon ativo). Flags: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | Estado JSON de todos os contentores via API do Hub em execução. |
| `renet hub stop <username>` | Para o contentor de um utilizador específico. |

## Configuração

Toda a configuração do Hub reside nas etiquetas compose do serviço Hub. Os segredos (client_secret OAuth, session_secret) vão em `hub/.env`, não nas etiquetas.

### Mapeamento de Rotas

Mapeie prefixos de subdomínio para portas nos contentores do utilizador. O Hub lê estas etiquetas para saber onde encaminhar cada pedido.

| Etiqueta | Descrição | Exemplo |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Mapeia `{prefix}.{domain}` para esta porta no contentor do utilizador | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Cada rota também precisa de um router Traefik correspondente apontando para a porta do Hub (7112). O Hub trata do encaminhamento por utilizador internamente com base no hostname.

### Modelo de Contentor

Defina como são os contentores dos utilizadores. O Hub lê estas etiquetas e usa-as ao criar um novo contentor.

| Etiqueta | Descrição | Predefinição |
|-------|-------------|---------|
| `rediacc.hub.image` | Imagem do contentor | Valor do flag `--container-image` |
| `rediacc.hub.command` | Comando de arranque (compatível com bash -c) | nenhum |
| `rediacc.hub.user` | Utilizador do contentor (recomendado não-root) | `vscode` |
| `rediacc.hub.workspace` | Ponto de montagem do workspace dentro do contentor | `/workspace` |
| `rediacc.hub.shm_size` | Tamanho da memória partilhada em bytes | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` para provisionar um dockerd dedicado por utilizador (fortemente recomendado) | `""` |

A etiqueta `command` suporta expansão de `${SERVICE_IP}` e `__SERVICE_IP__` (este último evita a pré-expansão do compose) para o IP de loopback atribuído ao contentor.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Daemon Docker por Utilizador

Quando `rediacc.hub.docker=per-user` está definido, cada utilizador obtém uma instância `dockerd` dedicada no anfitrião, montada como `/var/run/docker.sock` dentro do seu contentor. Isto fornece:

- `docker ps`, `docker run`, `docker build` completos dentro do ambiente do utilizador sem contentores privilegiados nem Docker-in-Docker.
- Isolamento completo entre utilizadores (o utilizador A não consegue ver os contentores ou imagens do utilizador B).
- Um data-root BTRFS por utilizador em `<workspace-dir>/<user>-docker/.rediacc/docker/data`, preservado entre sessões para que as imagens em cache sobrevivam aos ciclos de checkpoint inativo.

Os daemons são alocados num intervalo de ID de rede dedicado a partir de 32768. Um ficheiro marcador `.networkid` no data-root de cada utilizador regista o ID atribuído para que os utilizadores recorrentes obtenham o mesmo daemon.

### Limites de Recursos

Defina limites de recursos por utilizador para impedir que um único utilizador consuma todos os recursos do anfitrião. Os limites aplicam-se tanto ao contentor do utilizador como à sua instância dockerd por utilizador (via `CPUQuota=` / `MemoryMax=` do systemd).

| Etiqueta | Descrição | Exemplo |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Valor CPUQuota do systemd | `200%` (2 núcleos) |
| `rediacc.hub.limits.memory` | Valor MemoryMax do systemd | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Os daemons são colocados na slice systemd `rediacc.slice` para que os limites ao nível da slice sejam herdados.

### Suporte a Múltiplos Modelos

Ofereça múltiplos tipos de ambiente. Os utilizadores escolhem um modelo no login visitando `https://code.example.com/_hub/login?template=python` (a seleção percorre o estado OAuth). Mudar de modelo em logins subsequentes reconstrói o contentor.

Defina modelos com etiquetas `rediacc.hub.templates.<name>.<field>`. As etiquetas planas `rediacc.hub.image` / `rediacc.hub.command` / etc. continuam a definir o modelo implícito "predefinido" para utilizadores que não escolhem nenhum.

```yaml
labels:
  # O modelo predefinido quando ?template=... é omitido.
  - "rediacc.hub.template=fulldev"

  # Um ambiente rico VS Code + desktop + terminal.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # VS Code leve apenas.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Ambiente específico para Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Hooks de Ciclo de Vida

Execute comandos dentro do contentor do utilizador em pontos do ciclo de vida. Os hooks executam como o utilizador do contentor (não root).

| Etiqueta | Quando executa | Exemplo |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Após o contentor ser criado (primeiro login) | Clonar repositórios, instalar dependências |
| `rediacc.hub.hook.checkpoint.pre_dump` | Antes do checkpoint CRIU de uma sessão inativa | Parar daemons que não podem ser checkpointed (servidor X, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Após restauro CRIU | Reiniciar os daemons parados no pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restauro

Quando `--checkpoint` está definido, os contentores de utilizadores inativos são guardados via CRIU checkpoint e o seu daemon por utilizador é parado para libertar memória. No próximo login, o daemon é reiniciado e o CRIU restaura o estado do contentor a partir do disco, preservando ficheiros abertos, processos em execução e sessões de terminal. O tempo típico de retoma é de alguns segundos independentemente da carga de trabalho.

| Etiqueta | Descrição | Predefinição |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Ativar checkpoint CRIU para contentores de utilizadores | `false` |

Passe `--checkpoint` e um `--idle-timeout` diferente de zero (p. ex. `30m`) no comando Hub. Os diretórios de checkpoint ficam em `<workspace-dir>/<user>/.checkpoint/`.

Se o CRIU falhar 3 vezes seguidas para um utilizador, o checkpointing é desativado para esse utilizador e o fallback passa a ser parar-e-recriar.

### Modo Efémero

Por defeito, os workspaces dos utilizadores são persistentes (sobrevivem ao reinício). O modo efémero fornece um ambiente limpo em cada login, útil para demos, formação ou CI.

| Etiqueta | Descrição | Predefinição |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` ou `ephemeral` | `persistent` |

No modo efémero, o workspace é tmpfs (suportado por RAM) e o contentor é removido automaticamente ao parar.

### Timeout de Inatividade

| Flag | Descrição | Predefinição |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Parar/guardar checkpoint de contentores inativos por mais tempo do que este valor | `0` (desativado) |

`0` mantém os contentores em execução indefinidamente. Um valor prático é `30m`: os utilizadores inativos libertam memória após meia hora, e os utilizadores recorrentes retomam em segundos via CRIU.

### Controlo de Acesso

| Variável | Descrição |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Grupos separados por vírgula com permissão para usar o Hub (quando o seu fornecedor expõe claims de grupo) |
| `HUB_ADMIN_USERS` | Nomes de utilizador de administradores separados por vírgula. Os administradores veem e controlam os contentores de outros utilizadores no dashboard. |

## Registo de Auditoria

Cada evento de contentor/imagem iniciado pelo utilizador (create, start, stop, destroy, kill, pull, push) no daemon por utilizador é adicionado como um registo JSON delimitado por linha em `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

As entradas sobrevivem ao checkpoint/restauro CRIU (o fluxo de auditoria é rearmado no restauro). Use `logrotate` para limitar o uso de disco; uma configuração de exemplo:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Dashboard

O Hub inclui um dashboard self-service em `/_hub/dashboard`. Mostra:

- Todos os ambientes em execução com o seu estado
- Modelo selecionado
- Links de serviço (um clique para abrir código, terminal, desktop ou qualquer outra rota)
- Temporizadores de inatividade
- Uso de disco por utilizador, contagem de contentores em execução e contagem de imagens
- Os administradores veem todos os contentores; os utilizadores normais veem apenas os seus

As estatísticas são amostradas a cada 30 segundos.

## Recolha de Lixo do Data-Root

Os data-roots por utilizador acumulam-se em anfitriões de longa duração. Agende `renet hub gc` para eliminar os abandonados. Um temporizador systemd funciona bem:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` regista candidatos sem eliminar. Um data-root é elegível quando o seu marcador `.networkid` é mais antigo do que `--max-age` E o daemon registado já não está configurado no anfitrião.

## Configuração OAuth

O Hub funciona com qualquer fornecedor OAuth2 padrão. A configuração é feita via variáveis de ambiente.

| Variável | Descrição | Obrigatório |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID do cliente OAuth2 | Sim |
| `HUB_OAUTH_CLIENT_SECRET` | Segredo do cliente OAuth2 | Sim |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint de autorização do fornecedor | Sim |
| `HUB_OAUTH_TOKEN_URL` | Endpoint de token do fornecedor | Sim |
| `HUB_OAUTH_USERINFO_URL` | Endpoint de informação do utilizador do fornecedor | Sim |
| `HUB_OAUTH_USERINFO_PATH` | Caminho de pontos para extrair o nome de utilizador da resposta JSON | Sim |
| `HUB_OAUTH_REDIRECT_URI` | Substituir URL de callback (calculado automaticamente se vazio) | Não |
| `HUB_OAUTH_SCOPES` | Âmbitos adicionais (separados por espaço) | Não |
| `HUB_SESSION_SECRET` | String hexadecimal de 32+ bytes para assinatura de cookies | Recomendado |

### Exemplos de Fornecedores

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` é um caminho separado por pontos na resposta JSON. Para objetos aninhados como `{"ocs":{"data":{"id":"alice"}}}` do Nextcloud, use `ocs.data.id`.

## Exemplos

### Ambiente de Desenvolvimento (VS Code + Terminal + Desktop)

Um ambiente de desenvolvimento completo com OpenVSCode Server, um terminal web (ttyd) e um desktop noVNC. Os utilizadores têm o seu próprio daemon Docker dentro.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Routers Traefik para cada prefixo ...
```

### Ambiente Jupyter Notebook

Um ambiente de ciência de dados com JupyterLab:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Aplicação Web Simples (Efémera)

Um ambiente de serviço único que começa do zero em cada login:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guias Relacionados

- [**Serviços**](/pt/docs/services) -- Ciclo de vida do Rediaccfile, padrões de compose
- [**Rede**](/pt/docs/networking) -- Etiquetas Docker, encaminhamento Traefik, certificados TLS
- [**Backup e Restauro**](/pt/docs/backup-restore) -- Persistência e recuperação do workspace
- [**Ambientes de Desenvolvimento**](/pt/docs/development-environments) -- Clonagem de produção para ambientes de desenvolvimento
