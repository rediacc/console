---
title: "Hub"
description: "Authentifizierte, benutzerspezifische Container-Umgebungen für jeden Nutzer mit automatischer Bereitstellung, Leerlaufüberwachung und Checkpoint/Restore."
category: "Guides"
order: 14
language: de
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Der Hub stellt benutzerspezifische Container-Umgebungen hinter OAuth-Authentifizierung bereit. Benutzer rufen eine einzelne URL auf, authentifizieren sich bei einem beliebigen OAuth2-Anbieter und werden transparent zu ihrem persönlichen Container weitergeleitet. Container werden bei Bedarf erstellt und automatisch verwaltet.

Alles wird über `docker-compose.yml`-Labels konfiguriert. Der Hub kennt den Inhalt der Container nicht und kümmert sich nicht darum -- er übernimmt Authentifizierung, Routing und Lebenszyklus. Repositories definieren das Verhalten.

## Funktionsweise

![Hub-Architektur](/img/hub-architecture.svg)

1. Ein Benutzer ruft `code.example.com` auf
2. Der Hub prüft das Session-Cookie. Fehlt es, wird der Benutzer zum konfigurierten OAuth2-Anbieter weitergeleitet (Nextcloud, Keycloak, GitHub usw.)
3. Nach der Authentifizierung identifiziert der Hub den Benutzer und sucht dessen Container
4. Existiert kein Container, wird bei Bedarf einer aus der konfigurierten Vorlage erstellt
5. Die Anfrage wird per Reverse-Proxy an den Container des Benutzers weitergeleitet
6. Der Hub bestimmt den Zielport anhand des Hostnamens (z. B. `code.` -> Port 8080, `term.` -> Port 7681)

Inaktive Container werden automatisch gestoppt oder per Checkpoint (CRIU) gesichert, um beim nächsten Login sofort wiederhergestellt zu werden.

## Schnellstart

Fügen Sie den Hub als Dienst in der `docker-compose.yml` Ihres Repositories hinzu:

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # Routen-Zuordnung: Subdomain-Präfix -> Port auf Benutzer-Containern
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Container-Vorlage
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Traefik-Routen (eine pro Subdomain)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Erstellen Sie `hub.env` mit den Zugangsdaten Ihres OAuth2-Anbieters:

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

Bereitstellen mit `rdc repo up`.

## Konfiguration

Die gesamte Hub-Konfiguration befindet sich in Compose-Labels des Hub-Dienstes selbst. Es gibt keine Konfigurationsdateien innerhalb der Hub-Binary.

### Routen-Zuordnung

Ordnen Sie Subdomain-Präfixe den Ports auf Benutzer-Containern zu. Der Hub liest diese Labels, um zu wissen, wohin jede Anfrage weitergeleitet werden soll.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Ordnet `{prefix}.{domain}` diesem Port auf dem Container des Benutzers zu | `rediacc.hub.route.code=8080` |

Sie können beliebig viele Routen definieren. Das Präfix wird mit dem ersten Segment des Hostnamens abgeglichen:

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Jede Route benötigt zudem einen passenden Traefik-Router, der auf den Hub-Port (7112) zeigt. Der Hub übernimmt das benutzerspezifische Routing intern.

### Container-Vorlage

Definieren Sie, wie Benutzer-Container aussehen sollen. Der Hub liest diese Labels und verwendet sie beim Erstellen eines neuen Containers für einen Benutzer.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.image` | Container-Image | Wert des `--container-image`-Flags |
| `rediacc.hub.command` | Startbefehl (bash -c kompatibel) | keiner |
| `rediacc.hub.user` | Container-Benutzer (Nicht-Root empfohlen) | `vscode` |
| `rediacc.hub.workspace` | Workspace-Einhängepunkt im Container | `/workspace` |
| `rediacc.hub.shm_size` | Shared-Memory-Größe in Bytes | `1073741824` (1 GB) |

Das `command`-Label unterstützt `${SERVICE_IP}`-Expansion, die beim Start durch die zugewiesene Loopback-IP des Containers ersetzt wird.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **Tipp:** Verwenden Sie `$$` für ein literales `$` in Compose-Labels, um eine vorzeitige Umgebungsvariablen-Expansion durch Docker Compose zu verhindern.

### Ressourcenlimits

Legen Sie Ressourcenlimits pro Benutzer fest, um zu verhindern, dass ein einzelner Benutzer alle Host-Ressourcen verbraucht.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | CPU-Limit (Kerne) | `2` |
| `rediacc.hub.limits.memory` | Speicherlimit | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### Lebenszyklus-Hooks

Führen Sie Befehle im Benutzer-Container zu bestimmten Lebenszyklus-Zeitpunkten aus.

| Label | Ausführungszeitpunkt | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Nach Erstellung des Containers (erster Login) | Repos klonen, Abhängigkeiten installieren |
| `rediacc.hub.hook.on_start` | Nach Start oder Wiederherstellung des Containers | Secrets einbinden, Tokens aktualisieren |
| `rediacc.hub.hook.on_idle` | Vor Stopp oder Checkpoint des Containers | Zustand speichern, Änderungen pushen |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### Checkpoint / Restore

Bei Aktivierung werden inaktive Container mittels CRIU als Checkpoint gesichert, anstatt gestoppt zu werden. Beim nächsten Login wird der Container innerhalb von Sekunden aus dem Checkpoint wiederhergestellt, wobei der exakte Zustand erhalten bleibt: geöffnete Dateien, laufende Prozesse, Terminal-Sitzungen.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | CRIU-Checkpoint für Benutzer-Container aktivieren | `false` |

Übergeben Sie zusätzlich `--checkpoint` beim Start des Hubs:

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...weitere Flags...
```

> **Hinweis:** Checkpoint/Restore erfordert, dass die CRIU-Binary auf dem Host verfügbar ist und der Container im Host-Netzwerkmodus läuft (Standard für Rediacc-Dienste).

### Zugriffskontrolle

Beschränken Sie, wer den Hub nutzen darf und wer Administratorrechte hat.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Kommagetrennte Gruppen, die den Hub nutzen dürfen | `developers,ops` |
| `rediacc.hub.admin_users` | Kommagetrennte Admin-Benutzernamen | `alice,bob` |

Admin-Benutzer können alle Container im Dashboard sehen und verwalten. Reguläre Benutzer sehen nur ihre eigenen.

### Ephemerer Modus

Standardmäßig sind Benutzer-Workspaces persistent (überleben Container-Neustarts). Der ephemere Modus bietet bei jedem Login eine saubere Umgebung -- nützlich für Demos, Schulungen oder CI.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` oder `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

Im ephemeren Modus verwendet der Workspace tmpfs (RAM-basiert) und der Container wird beim Stopp automatisch entfernt.

### Multi-Template-Unterstützung

Bieten Sie mehrere Umgebungstypen an. Benutzer können ihre Vorlage beim ersten Login wählen oder über das Dashboard wechseln.

```yaml
labels:
  # Standard-Vorlage
  - "rediacc.hub.template.default=fulldev"

  # Vollständige Entwicklungsumgebung
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # Leichtgewichtige Option
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## OAuth-Einrichtung

Der Hub funktioniert mit jedem Standard-OAuth2-Anbieter. Die Konfiguration erfolgt über Umgebungsvariablen, nicht über Compose-Labels (Secrets sollten nicht in Labels stehen).

| Variable | Beschreibung | Erforderlich |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 Client-ID | Ja |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 Client-Secret | Ja |
| `HUB_OAUTH_AUTHORIZE_URL` | Autorisierungs-Endpunkt des Anbieters | Ja |
| `HUB_OAUTH_TOKEN_URL` | Token-Endpunkt des Anbieters | Ja |
| `HUB_OAUTH_USERINFO_URL` | Benutzerinfo-Endpunkt des Anbieters | Ja |
| `HUB_OAUTH_USERINFO_PATH` | Punkt-Pfad zum Extrahieren des Benutzernamens aus der JSON-Antwort | Ja |
| `HUB_OAUTH_REDIRECT_URI` | Callback-URL überschreiben (automatisch berechnet wenn leer) | Nein |
| `HUB_OAUTH_SCOPES` | Zusätzliche Scopes (leerzeichengetrennt) | Nein |
| `HUB_SESSION_SECRET` | 32+ Byte Hex-String für Cookie-Signierung | Empfohlen |

### Anbieter-Beispiele

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

Der `HUB_OAUTH_USERINFO_PATH` ist ein punktgetrennter Pfad in die JSON-Antwort. Für verschachtelte Objekte wie Nextclouds `{"ocs":{"data":{"id":"alice"}}}` verwenden Sie `ocs.data.id`.

## Dashboard

Der Hub enthält ein Self-Service-Dashboard unter `/_hub/dashboard`. Es zeigt:

- Alle laufenden Umgebungen mit ihrem Status
- Service-Links (ein Klick zum Öffnen von Code, Terminal oder Desktop)
- Leerlauf-Timer und Ressourcenverbrauch
- Start/Stopp-Steuerung
- Admin-Benutzer können alle Container sehen und verwalten

Greifen Sie auf das Dashboard zu, indem Sie nach der Authentifizierung `https://code.example.com/_hub/dashboard` besuchen.

## Beispiele

### Entwicklungsumgebung (VS Code + Terminal + Desktop)

Eine vollständige Entwicklungsumgebung mit OpenVSCode Server, einem Web-Terminal (ttyd) und einem noVNC-Desktop:

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Jupyter-Notebook-Umgebung

Eine Data-Science-Umgebung mit JupyterLab:

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### Einfache Webanwendung

Eine Einzel-Service-Umgebung für ein Web-Framework:

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Verwandte Anleitungen

- [**Services**](/de/docs/services) -- Rediaccfile-Lebenszyklus, Compose-Muster
- [**Netzwerk**](/de/docs/networking) -- Docker-Labels, Traefik-Routing, TLS-Zertifikate
- [**Backup & Restore**](/de/docs/backup-restore) -- Workspace-Persistenz und Wiederherstellung
- [**Entwicklungsumgebungen**](/de/docs/development-environments) -- Produktionsklone für Entwicklungsumgebungen
