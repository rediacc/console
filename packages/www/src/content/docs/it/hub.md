---
title: "Hub"
description: "Fornisci ambienti containerizzati per utente con daemon Docker per utente, selezione multi-template, checkpoint/restore CRIU, log di audit e garbage collection dei data-root. È più sicuro degli ambienti condivisi tradizionali."
category: "Guides"
order: 14
language: it
---

# Hub

L'Hub fornisce ambienti containerizzati per utente protetti dall'autenticazione OAuth. Gli utenti visitano un singolo URL, si autenticano con qualsiasi provider OAuth2 e vengono instradati in modo trasparente al loro container personale. I container vengono avviati su richiesta, ogni utente ha il proprio daemon Docker isolato e le sessioni inattive vengono salvate tramite checkpoint CRIU per una ripresa istantanea.

Tutto è configurato tramite label in `docker-compose.yml`. L'Hub stesso viene eseguito come servizio systemd sull'host, generato dal comando `renet hub install` dal file compose del tuo repository. I repository definiscono il comportamento; l'Hub gestisce autenticazione, routing, ciclo di vita e isolamento per utente.

## Come Funziona

1. Un utente visita `code.example.com` (o `term.`, `desktop.`, o qualsiasi altro prefisso configurato).
2. L'Hub verifica la presenza di un cookie di sessione. Se assente, l'utente viene reindirizzato al provider OAuth2 configurato (Nextcloud, Keycloak, GitHub, ecc.).
3. Dopo l'autenticazione, l'Hub identifica l'utente e cerca il suo container.
4. Se non esiste alcun container, l'Hub provisiona un daemon Docker dedicato per quell'utente sull'host, quindi avvia il suo container.
5. La richiesta viene inoltrata tramite reverse proxy al container dell'utente sulla rete loopback.
6. I container inattivi vengono salvati tramite checkpoint CRIU; il daemon per utente viene fermato per liberare memoria. Al prossimo accesso il daemon torna attivo e CRIU ripristina lo stato del container in pochi secondi.

## Avvio Rapido

Aggiungi l'Hub come servizio nel `docker-compose.yml` del tuo repository. Il servizio è contrassegnato con `install_as=systemd` in modo da essere eseguito come servizio sull'host piuttosto che come container Docker (richiesto per la gestione del daemon per utente, che usa systemd).

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

      # Mappatura route: prefisso sottodominio -> porta sui container utente
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Template container
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Route Traefik (file-provider; rediacc-router legge anche queste label)
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

Crea `hub/.env` con le credenziali del tuo provider OAuth2:

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

Installa l'unità systemd sull'host (una tantum, richiede root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Questo legge i servizi con `install_as=systemd` e scrive:

- `/etc/systemd/system/rediacc-hub.service` (l'unità)
- `/etc/rediacc/hub/hub.labels.yaml` (le label del template)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (le route del file-provider Traefik)

Poi `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Per rimuovere: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Riferimento Comandi di Installazione

| Comando | Scopo |
|---------|---------|
| `sudo renet hub install <compose-file>` | Traduce i servizi `install_as=systemd` dal file compose in artefatti sull'host e avvia l'unità. |
| `sudo renet hub uninstall <compose-file>` | Ferma, disabilita e rimuove tutti gli artefatti per i servizi. I data-root sotto `<workspace>/<user>-docker/` vengono preservati. |
| `sudo renet hub gc <workspace-dir>` | Elimina i data-root per utente abbandonati (predefinito: più vecchi di 30 giorni senza daemon attivo). Flag: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | Stato JSON di tutti i container tramite l'API dell'Hub in esecuzione. |
| `renet hub stop <username>` | Ferma il container di un utente specifico. |

## Configurazione

Tutta la configurazione dell'Hub si trova nelle label compose sul servizio Hub. I segreti (OAuth client_secret, session_secret) vanno in `hub/.env`, non nelle label.

### Mappatura Route

Mappa i prefissi dei sottodomini alle porte sui container utente. L'Hub legge queste label per sapere dove instradare ogni richiesta.

| Label | Descrizione | Esempio |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Mappa `{prefix}.{domain}` a questa porta sul container dell'utente | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Ogni route richiede anche un router Traefik corrispondente che punta alla porta dell'Hub (7112). L'Hub gestisce il routing per utente internamente in base all'hostname.

### Template Container

Definisci come appaiono i container utente. L'Hub legge queste label e le utilizza quando avvia un nuovo container.

| Label | Descrizione | Predefinito |
|-------|-------------|---------|
| `rediacc.hub.image` | Immagine container | Valore del flag `--container-image` |
| `rediacc.hub.command` | Comando di avvio (compatibile con bash -c) | nessuno |
| `rediacc.hub.user` | Utente container (non-root raccomandato) | `vscode` |
| `rediacc.hub.workspace` | Punto di mount del workspace nel container | `/workspace` |
| `rediacc.hub.shm_size` | Dimensione della memoria condivisa in byte | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` per provisiona un dockerd dedicato per utente (fortemente raccomandato) | `""` |

La label `command` supporta l'espansione di `${SERVICE_IP}` e `__SERVICE_IP__` (quest'ultimo evita la pre-espansione di compose) per l'IP loopback assegnato al container.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Daemon Docker per Utente

Quando è impostato `rediacc.hub.docker=per-user`, ogni utente ottiene un'istanza `dockerd` dedicata sull'host, montata come `/var/run/docker.sock` nel suo container. Questo fornisce:

- `docker ps`, `docker run`, `docker build` completi nell'ambiente utente senza container privilegiati o Docker-in-Docker.
- Isolamento completo tra utenti (l'utente A non può vedere i container o le immagini dell'utente B).
- Un data-root BTRFS per utente in `<workspace-dir>/<user>-docker/.rediacc/docker/data`, preservato tra le sessioni in modo che le immagini memorizzate nella cache sopravvivano ai cicli di checkpoint-inattività.

I daemon vengono allocati in un intervallo di ID di rete dedicato a partire da 32768. Un file marker `.networkid` nel data-root di ogni utente registra l'ID assegnato in modo che gli utenti di ritorno riprendano lo stesso daemon.

### Limiti delle Risorse

Imposta limiti di risorse per utente per evitare che un singolo utente consumi tutte le risorse dell'host. I limiti si applicano sia al container dell'utente che alla sua istanza dockerd per utente (tramite systemd `CPUQuota=` / `MemoryMax=`).

| Label | Descrizione | Esempio |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Valore systemd CPUQuota | `200%` (2 core) |
| `rediacc.hub.limits.memory` | Valore systemd MemoryMax | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

I daemon vengono collocati nella slice systemd `rediacc.slice` in modo che i limiti a livello di slice vengano ereditati.

### Supporto Multi-Template

Offri più tipi di ambiente. Gli utenti scelgono un template al login visitando `https://code.example.com/_hub/login?template=python` (la selezione passa attraverso lo stato OAuth). Cambiare template ai login successivi ricostruisce il container.

Definisci i template con label `rediacc.hub.templates.<name>.<field>`. Le label flat `rediacc.hub.image` / `rediacc.hub.command` / ecc. continuano a definire il template "default" implicito per gli utenti che non ne scelgono uno.

```yaml
labels:
  # Il template predefinito quando ?template=... è omesso.
  - "rediacc.hub.template=fulldev"

  # Un ambiente ricco VS Code + desktop + terminale.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Un VS Code leggero.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Ambiente specifico per Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Hook del Ciclo di Vita

Esegui comandi nel container utente nei punti del ciclo di vita. Gli hook vengono eseguiti come utente del container (non root).

| Label | Quando viene eseguito | Esempio |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Dopo la creazione del container (primo login) | Clona repository, installa dipendenze |
| `rediacc.hub.hook.checkpoint.pre_dump` | Prima del checkpoint CRIU di una sessione inattiva | Ferma i daemon che non possono essere salvati con checkpoint (server X, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Dopo il restore CRIU | Riavvia i daemon fermati in pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restore

Quando è impostato `--checkpoint`, i container utente inattivi vengono salvati tramite checkpoint CRIU e il loro daemon per utente viene fermato per liberare memoria. Al prossimo login il daemon viene riavviato e CRIU ripristina lo stato del container dal disco, preservando i file aperti, i processi in esecuzione e le sessioni terminale. Il tempo di ripresa tipico è di pochi secondi indipendentemente dal carico di lavoro.

| Label | Descrizione | Predefinito |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Abilita il checkpoint CRIU per i container utente | `false` |

Passa `--checkpoint` e un `--idle-timeout` non zero (es. `30m`) nel comando Hub. Le directory di checkpoint si trovano in `<workspace-dir>/<user>/.checkpoint/`.

Se CRIU fallisce 3 volte di fila per un utente, il checkpointing viene disabilitato per quell'utente e il fallback diventa stop-and-recreate.

### Modalità Effimera

Per impostazione predefinita, i workspace utente sono persistenti (sopravvivono al riavvio). La modalità effimera fornisce un ambiente pulito a ogni login, utile per demo, formazione o CI.

| Label | Descrizione | Predefinito |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` o `ephemeral` | `persistent` |

In modalità effimera il workspace è tmpfs (supportato dalla RAM) e il container viene rimosso automaticamente all'arresto.

### Timeout di Inattività

| Flag | Descrizione | Predefinito |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Ferma/salva con checkpoint i container inattivi da più di questo tempo | `0` (disabilitato) |

`0` mantiene i container in esecuzione per sempre. Un valore pratico è `30m`: gli utenti inattivi liberano memoria dopo mezz'ora, e gli utenti di ritorno riprendono in pochi secondi tramite CRIU.

### Controllo degli Accessi

| Variabile | Descrizione |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Gruppi separati da virgola autorizzati a utilizzare l'Hub (quando il provider espone le informazioni sui gruppi) |
| `HUB_ADMIN_USERS` | Nomi utente admin separati da virgola. Gli admin vedono e controllano i container di tutti gli utenti nella dashboard. |

## Log di Audit

Ogni evento container/immagine avviato dall'utente (create, start, stop, destroy, kill, pull, push) sul daemon per utente viene aggiunto come record JSON delimitato da newline in `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Le voci sopravvivono al checkpoint/restore CRIU (il flusso di audit viene riarmato al restore). Usa `logrotate` per limitare l'utilizzo del disco; una configurazione di esempio:

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

L'Hub include una dashboard self-service su `/_hub/dashboard`. Mostra:

- Tutti gli ambienti in esecuzione con il loro stato
- Template selezionato
- Link ai servizi (un clic per aprire il codice, il terminale, il desktop o qualsiasi altra route)
- Timer di inattività
- Utilizzo del disco per utente, numero di container in esecuzione e numero di immagini
- Gli admin vedono tutti i container; gli utenti normali vedono solo i propri

Le statistiche vengono campionate ogni 30 secondi.

## Garbage Collection dei Data-Root

I data-root per utente si accumulano sugli host a lungo termine. Pianifica `renet hub gc` per eliminare quelli abbandonati. Un timer systemd funziona bene:

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

`--dry-run` registra i candidati senza eliminarli. Un data-root è eleggibile quando il suo marker `.networkid` è più vecchio di `--max-age` E il daemon registrato non è più configurato sull'host.

## Configurazione OAuth

L'Hub funziona con qualsiasi provider OAuth2 standard. La configurazione avviene tramite variabili d'ambiente.

| Variabile | Descrizione | Richiesta |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID client OAuth2 | Sì |
| `HUB_OAUTH_CLIENT_SECRET` | Segreto client OAuth2 | Sì |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint di autorizzazione del provider | Sì |
| `HUB_OAUTH_TOKEN_URL` | Endpoint token del provider | Sì |
| `HUB_OAUTH_USERINFO_URL` | Endpoint userinfo del provider | Sì |
| `HUB_OAUTH_USERINFO_PATH` | Percorso con punti per estrarre il nome utente dalla risposta JSON | Sì |
| `HUB_OAUTH_REDIRECT_URI` | Sovrascrive l'URL di callback (calcolato automaticamente se vuoto) | No |
| `HUB_OAUTH_SCOPES` | Scope aggiuntivi (separati da spazio) | No |
| `HUB_SESSION_SECRET` | Stringa esadecimale di 32+ byte per la firma dei cookie | Raccomandato |

### Esempi di Provider

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

`HUB_OAUTH_USERINFO_PATH` è un percorso separato da punti nella risposta JSON. Per gli oggetti annidati come `{"ocs":{"data":{"id":"alice"}}}` di Nextcloud, usa `ocs.data.id`.

## Esempi

### Ambiente di Sviluppo (VS Code + Terminale + Desktop)

Un ambiente di sviluppo completo con OpenVSCode Server, un terminale web (ttyd) e un desktop noVNC. Gli utenti hanno il proprio daemon Docker all'interno.

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
      # ... Router Traefik per ogni prefisso ...
```

### Ambiente Jupyter Notebook

Un ambiente di data science con JupyterLab:

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

### Semplice Applicazione Web (Effimera)

Un ambiente a singolo servizio che parte da zero a ogni login:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guide Correlate

- [**Servizi**](/en/docs/services) -- Ciclo di vita del Rediaccfile, pattern compose
- [**Networking**](/en/docs/networking) -- Label Docker, routing Traefik, certificati TLS
- [**Backup e Ripristino**](/en/docs/backup-restore) -- Persistenza e recupero dei workspace
- [**Ambienti di Sviluppo**](/en/docs/development-environments) -- Clonazione della produzione per gli ambienti di sviluppo
