---
title: "Hub"
description: "Stellt authentifizierte Container-Umgebungen pro Benutzer bereit, mit benutzereigenem Docker-Daemon, Auswahl aus mehreren Vorlagen, CRIU-Prüfpunkt-Wiederherstellung, Prüfprotokollen und Garbage-Collection für Datenwurzeln."
category: "Guides"
order: 14
language: de
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Der Hub stellt benutzerspezifische Container-Umgebungen hinter OAuth-Authentifizierung bereit. Benutzer rufen eine einzelne URL auf, authentifizieren sich bei einem beliebigen OAuth2-Anbieter und werden transparent zu ihrem persönlichen Container weitergeleitet. Container werden bei Bedarf erstellt, jeder Benutzer erhält seinen eigenen isolierten Docker-Daemon, und Leerlauf-Sitzungen werden per CRIU-Checkpoint gesichert für sofortige Wiederherstellung.

Alles wird über `docker-compose.yml`-Labels konfiguriert. Der Hub selbst läuft als systemd-Host-Dienst, der durch den Befehl `renet hub install` aus der Compose-Datei Ihres Repositories materialisiert wird. Repositories definieren das Verhalten; der Hub übernimmt Authentifizierung, Routing, Lebenszyklus und benutzerspezifische Isolation.

## Funktionsweise

1. Ein Benutzer ruft `code.example.com` auf (oder `term.`, `desktop.`, oder ein anderes konfiguriertes Präfix).
2. Der Hub prüft das Session-Cookie. Fehlt es, wird der Benutzer zum konfigurierten OAuth2-Anbieter weitergeleitet (Nextcloud, Keycloak, GitHub usw.).
3. Nach der Authentifizierung identifiziert der Hub den Benutzer und sucht dessen Container.
4. Existiert kein Container, richtet der Hub einen dedizierten Docker-Daemon für diesen Benutzer auf dem Host ein und startet dann dessen Container.
5. Die Anfrage wird per Reverse-Proxy über das Loopback-Netzwerk an den Container des Benutzers weitergeleitet.
6. Inaktive Container werden per CRIU checkpointed; der benutzereigene Daemon wird gestoppt, um Speicher freizugeben. Beim nächsten Login startet der Daemon wieder und CRIU stellt den Container-Zustand in Sekunden wieder her.

## Schnellstart

Fügen Sie den Hub als Dienst in der `docker-compose.yml` Ihres Repositories hinzu. Der Dienst ist mit `install_as=systemd` markiert, sodass er als Host-Dienst und nicht als Docker-Container läuft (erforderlich für die benutzerspezifische Daemon-Verwaltung, die systemd nutzt).

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

      # Routen-Zuordnung: Subdomain-Präfix -> Port auf Benutzer-Containern
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Container-Vorlage
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik-Routen (File-Provider; rediacc-router liest diese Labels ebenfalls)
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

Erstellen Sie `hub/.env` mit den Zugangsdaten Ihres OAuth2-Anbieters:

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

Installieren Sie die systemd-Host-Unit (einmalig, erfordert root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Dies liest die `install_as=systemd`-Dienste und schreibt:

- `/etc/systemd/system/rediacc-hub.service` (die Unit)
- `/etc/rediacc/hub/hub.labels.yaml` (die Template-Labels)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (Traefik File-Provider-Routen)

Dann `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Zum Entfernen: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Install-Befehlsreferenz

| Befehl | Zweck |
|---------|---------|
| `sudo renet hub install <compose-file>` | `install_as=systemd`-Dienste aus der Compose-Datei in Host-Artefakte übersetzen und die Unit starten. |
| `sudo renet hub uninstall <compose-file>` | Alle Artefakte für die Dienste stoppen, deaktivieren und entfernen. Data-Roots unter `<workspace>/<user>-docker/` bleiben erhalten. |
| `sudo renet hub gc <workspace-dir>` | Verlassene benutzerspezifische Data-Roots bereinigen (Standard: älter als 30 Tage ohne aktiven Daemon). Flags: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | JSON-Status aller Container über die laufende Hub-API. |
| `renet hub stop <username>` | Den Container eines bestimmten Benutzers stoppen. |

## Konfiguration

Die gesamte Hub-Konfiguration befindet sich in Compose-Labels des Hub-Dienstes. Secrets (OAuth client_secret, session_secret) kommen in `hub/.env`, nicht in Labels.

### Routen-Zuordnung

Ordnen Sie Subdomain-Präfixe den Ports auf Benutzer-Containern zu. Der Hub liest diese Labels, um zu wissen, wohin jede Anfrage weitergeleitet werden soll.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Ordnet `{prefix}.{domain}` diesem Port auf dem Container des Benutzers zu | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Jede Route benötigt zudem einen passenden Traefik-Router, der auf den Hub-Port (7112) zeigt. Der Hub übernimmt das benutzerspezifische Routing intern anhand des Hostnamens.

### Container-Vorlage

Definieren Sie, wie Benutzer-Container aussehen sollen. Der Hub liest diese Labels und verwendet sie beim Erstellen eines neuen Containers.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.image` | Container-Image | Wert des `--container-image`-Flags |
| `rediacc.hub.command` | Startbefehl (bash -c kompatibel) | keiner |
| `rediacc.hub.user` | Container-Benutzer (Nicht-Root empfohlen) | `vscode` |
| `rediacc.hub.workspace` | Workspace-Einhängepunkt im Container | `/workspace` |
| `rediacc.hub.shm_size` | Shared-Memory-Größe in Bytes | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` für einen dedizierten dockerd pro Benutzer (dringend empfohlen) | `""` |

Das `command`-Label unterstützt `${SERVICE_IP}`- und `__SERVICE_IP__`-Expansion (letzteres vermeidet Compose-Vorexpansion) für die zugewiesene Loopback-IP des Containers.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Benutzerspezifischer Docker-Daemon

Wenn `rediacc.hub.docker=per-user` gesetzt ist, erhält jeder Benutzer eine dedizierte `dockerd`-Instanz auf dem Host, die als `/var/run/docker.sock` in dessen Container eingebunden wird. Dies ermöglicht:

- Vollständiges `docker ps`, `docker run`, `docker build` in der Benutzerumgebung ohne privilegierte Container oder Docker-in-Docker.
- Vollständige Isolation zwischen Benutzern (Benutzer A kann die Container oder Images von Benutzer B nicht sehen).
- Ein benutzerspezifisches BTRFS-Data-Root unter `<workspace-dir>/<user>-docker/.rediacc/docker/data`, das sitzungsübergreifend erhalten bleibt, sodass gecachte Images Leerlauf-Checkpoint-Zyklen überstehen.

Daemons werden in einem dedizierten Netzwerk-ID-Bereich ab 32768 zugewiesen. Eine `.networkid`-Markerdatei im Data-Root jedes Benutzers speichert die zugewiesene ID, damit wiederkehrende Benutzer denselben Daemon erhalten.

### Ressourcenlimits

Legen Sie Ressourcenlimits pro Benutzer fest, um zu verhindern, dass ein einzelner Benutzer alle Host-Ressourcen verbraucht. Limits gelten sowohl für den Container des Benutzers als auch für dessen benutzereigene dockerd-Instanz (via systemd `CPUQuota=` / `MemoryMax=`).

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd-CPUQuota-Wert | `200%` (2 Kerne) |
| `rediacc.hub.limits.memory` | systemd-MemoryMax-Wert | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemons werden im systemd-Slice `rediacc.slice` platziert, sodass Slice-Level-Limits vererbt werden.

### Multi-Template-Unterstützung

Bieten Sie mehrere Umgebungstypen an. Benutzer wählen eine Vorlage beim Login, indem sie `https://code.example.com/_hub/login?template=python` aufrufen (die Auswahl wird über den OAuth-Status übertragen). Ein Template-Wechsel bei späteren Logins baut den Container neu auf.

Definieren Sie Templates mit `rediacc.hub.templates.<name>.<field>`-Labels. Die flachen Labels `rediacc.hub.image` / `rediacc.hub.command` / usw. definieren weiterhin das implizite "Default"-Template für Benutzer, die keines auswählen.

```yaml
labels:
  # Das Standard-Template, wenn ?template=... fehlt.
  - "rediacc.hub.template=fulldev"

  # Eine umfangreiche VS Code + Desktop + Terminal-Umgebung.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Nur VS Code, leichtgewichtig.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python-spezifische Umgebung.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Lebenszyklus-Hooks

Führen Sie Befehle im Benutzer-Container zu Lebenszyklus-Zeitpunkten aus. Hooks laufen als Container-Benutzer (nicht root).

| Label | Ausführungszeitpunkt | Beispiel |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Nach Erstellung des Containers (erster Login) | Repos klonen, Abhängigkeiten installieren |
| `rediacc.hub.hook.checkpoint.pre_dump` | Vor CRIU-Checkpoint einer Leerlauf-Sitzung | Daemons stoppen, die nicht checkpointed werden können (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Nach CRIU-Restore | Die in pre_dump gestoppten Daemons neu starten |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restore

Wenn `--checkpoint` gesetzt ist, werden inaktive Benutzer-Container per CRIU checkpointed und ihr benutzereigener Daemon gestoppt, um Speicher freizugeben. Beim nächsten Login wird der Daemon neu gestartet und CRIU stellt den Container-Zustand von der Festplatte wieder her, wobei offene Dateien, laufende Prozesse und Terminal-Sitzungen erhalten bleiben. Die typische Wiederherstellungszeit beträgt wenige Sekunden unabhängig von der Arbeitslast.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | CRIU-Checkpoint für Benutzer-Container aktivieren | `false` |

Übergeben Sie `--checkpoint` und ein von null verschiedenes `--idle-timeout` (z. B. `30m`) im Hub-Befehl. Checkpoint-Verzeichnisse liegen unter `<workspace-dir>/<user>/.checkpoint/`.

Schlägt CRIU 3 Mal in Folge für einen Benutzer fehl, wird Checkpointing für diesen Benutzer deaktiviert und der Fallback wird Stopp-und-Neuerstellen.

### Ephemerer Modus

Standardmäßig sind Benutzer-Workspaces persistent (überleben Neustarts). Der ephemere Modus bietet bei jedem Login eine saubere Umgebung, nützlich für Demos, Schulungen oder CI.

| Label | Beschreibung | Standard |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` oder `ephemeral` | `persistent` |

Im ephemeren Modus verwendet der Workspace tmpfs (RAM-basiert) und der Container wird beim Stopp automatisch entfernt.

### Leerlauf-Timeout

| Flag | Beschreibung | Standard |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Container stoppen/checkpointen, die länger als angegeben inaktiv sind | `0` (deaktiviert) |

`0` lässt Container unbegrenzt laufen. Ein praktischer Wert ist `30m`: Inaktive Benutzer geben nach einer halben Stunde Speicher frei, und zurückkehrende Benutzer stellen via CRIU in Sekunden wieder her.

### Zugriffskontrolle

| Variable | Beschreibung |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Kommagetrennte Gruppen, die den Hub nutzen dürfen (wenn Ihr Anbieter Gruppen-Claims bereitstellt) |
| `HUB_ADMIN_USERS` | Kommagetrennte Admin-Benutzernamen. Admins sehen und steuern die Container anderer Benutzer im Dashboard. |

## Audit-Log

Jedes benutzerseitig ausgelöste Container-/Image-Ereignis (create, start, stop, destroy, kill, pull, push) am benutzereigenen Daemon wird als zeilengetrennter JSON-Eintrag an `/var/log/rediacc/hub/<user>.log` angehängt:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Einträge überleben CRIU-Checkpoint/Restore (der Audit-Stream wird bei der Wiederherstellung neu aktiviert). Verwenden Sie `logrotate`, um den Speicherplatz zu begrenzen; eine Beispielkonfiguration:

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

Der Hub enthält ein Self-Service-Dashboard unter `/_hub/dashboard`. Es zeigt:

- Alle laufenden Umgebungen mit ihrem Status
- Gewähltes Template
- Service-Links (ein Klick zum Öffnen von Code, Terminal, Desktop oder einer anderen Route)
- Leerlauf-Timer
- Benutzerspezifische Festplattennutzung, Anzahl laufender Container und Images
- Admins sehen alle Container; reguläre Benutzer nur ihre eigenen

Statistiken werden alle 30 Sekunden erfasst.

## Data-Root-Garbage-Collection

Benutzerspezifische Data-Roots akkumulieren sich auf lange laufenden Hosts. Planen Sie `renet hub gc`, um verlassene zu bereinigen. Ein systemd-Timer eignet sich gut:

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

`--dry-run` protokolliert Kandidaten ohne Löschung. Ein Data-Root ist berechtigt, wenn seine `.networkid`-Markerdatei älter als `--max-age` ist UND der gespeicherte Daemon nicht mehr auf dem Host konfiguriert ist.

## OAuth-Einrichtung

Der Hub funktioniert mit jedem Standard-OAuth2-Anbieter. Die Konfiguration erfolgt über Umgebungsvariablen.

| Variable | Beschreibung | Erforderlich |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2-Client-ID | Ja |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2-Client-Secret | Ja |
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

## Beispiele

### Entwicklungsumgebung (VS Code + Terminal + Desktop)

Eine vollständige Entwicklungsumgebung mit OpenVSCode Server, einem Web-Terminal (ttyd) und einem noVNC-Desktop. Benutzer erhalten darin ihren eigenen Docker-Daemon.

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
      # ... Traefik-Router für jedes Präfix ...
```

### Jupyter-Notebook-Umgebung

Eine Data-Science-Umgebung mit JupyterLab:

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

### Einfache Webanwendung (Ephemer)

Eine Einzel-Service-Umgebung, die bei jedem Login neu startet:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Verwandte Anleitungen

- [**Services**](/de/docs/services) -- Rediaccfile-Lebenszyklus, Compose-Muster
- [**Netzwerk**](/de/docs/networking) -- Docker-Labels, Traefik-Routing, TLS-Zertifikate
- [**Backup & Restore**](/de/docs/backup-restore) -- Workspace-Persistenz und Wiederherstellung
- [**Entwicklungsumgebungen**](/de/docs/development-environments) -- Produktionsklone für Entwicklungsumgebungen
