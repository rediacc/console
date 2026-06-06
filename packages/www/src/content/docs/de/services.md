---
title: Dienste
description: >-
  Containerisierte Dienste mithilfe von Rediaccfiles, Dienst-Netzwerk und
  Autostart bereitstellen und verwalten.
category: Guides
order: 5
language: de
sourceHash: "88734af48d9648d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Dienste

Auf dieser Seite werden die Bereitstellung und Verwaltung containerisierter Dienste behandelt: Rediaccfiles, Dienst-Netzwerk, Starten/Stoppen, Massenoperationen und Autostart.

## Das Rediaccfile

Das **Rediaccfile** ist ein Bash-Skript, das definiert, wie Ihre Dienste gestartet und gestoppt werden. Es wird **sourced** (nicht als separater Prozess ausgeführt), daher teilen sich seine Funktionen denselben Shell-Kontext und haben Zugriff auf alle exportierten Umgebungsvariablen. Es muss `Rediaccfile` oder `rediaccfile` (Groß-/Kleinschreibung wird nicht unterschieden) heißen und muss im eingebundenen Dateisystem des Repositories platziert werden.

Rediaccfiles werden an zwei Orten gesucht:
1. Im **Stammverzeichnis** des Repository-Einbindungspfads
2. In **Unterverzeichnissen der ersten Ebene** des Einbindungspfads (nicht rekursiv)

Versteckte Verzeichnisse (Namen, die mit `.` beginnen) werden übersprungen.

### Lebenszyklus-Funktionen

Ein Rediaccfile enthält bis zu zwei Funktionen:

| Funktion | Ausführungszeitpunkt | Zweck | Fehlerverhalten |
|----------|---------------------|-------|-----------------|
| `up()` | Beim Starten | Dienste starten (z. B. `renet compose -- up -d`) | Fehler im Root-Rediaccfile sind **kritisch** (stoppt alles). Fehler in Unterverzeichnissen sind **nicht-kritisch** (werden protokolliert, es wird mit dem nächsten fortgefahren). |
| `down()` | Beim Stoppen | Dienste stoppen (z. B. `renet compose -- down`) | **Best-Effort** -- Fehler werden protokolliert, aber alle Rediaccfiles werden immer verarbeitet. |

Beide Funktionen sind optional. Wenn eine Funktion nicht definiert ist, wird sie stillschweigend übersprungen.

### Ausführungsreihenfolge

- **Starten (`up`):** Zuerst das Root-Rediaccfile, dann Unterverzeichnisse in **alphabetischer Reihenfolge** (A bis Z).
- **Stoppen (`down`):** Unterverzeichnisse in **umgekehrt alphabetischer Reihenfolge** (Z bis A), dann zuletzt das Root.

### Umgebungsvariablen

Wenn eine Rediaccfile-Funktion ausgeführt wird, stehen folgende Umgebungsvariablen zur Verfügung:

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Einbindungspfad des Repositories | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | Repository-GUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | Netzwerk-ID (Ganzzahl) | `2816` |
| `DOCKER_HOST` | Docker-Socket für den isolierten Daemon dieses Repositories | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | Loopback-IP für jeden in `.rediacc.json` definierten Dienst | `POSTGRES_IP=127.0.11.2` |

Die `{SERVICE}_IP`-Variablen werden automatisch aus den Slot-Zuordnungen in `.rediacc.json` generiert und werden vor der Ausführung Ihrer Rediaccfile-Funktionen exportiert. Die Namenskonvention wandelt den Dienstnamen in Großbuchstaben um, ersetzt Bindestriche durch Unterstriche und hängt `_IP` an. Beispiel: Ein Dienst namens `listmonk-app` mit Slot `0` wird zu `LISTMONK_APP_IP=127.0.11.2`.

> **Warnung: Verwenden Sie kein `sudo docker` in Rediaccfiles.** Der `sudo`-Befehl setzt Umgebungsvariablen zurück, wodurch `DOCKER_HOST` verloren geht und Docker-Befehle den System-Daemon statt des isolierten Repository-Daemons ansprechen. Dies bricht die Container-Isolation und kann Port-Konflikte verursachen. Rediacc blockiert die Ausführung, wenn es `sudo docker` ohne `-E` erkennt.
>
> Verwenden Sie `renet compose` in Ihren Rediaccfiles. Es übernimmt automatisch `DOCKER_HOST`, injiziert Netzwerk-Labels für die Routen-Erkennung und konfiguriert das Dienst-Netzwerk. Siehe [Netzwerk](/de/docs/networking) für Details, wie Dienste über den Reverse Proxy bereitgestellt werden. Wenn Sie Docker direkt aufrufen, verwenden Sie `docker` ohne `sudo`, da Rediaccfile-Funktionen bereits mit ausreichenden Rechten laufen. Wenn Sie sudo verwenden müssen, nutzen Sie `sudo -E docker`, um Umgebungsvariablen zu erhalten.
>
> `renet` ist das remote Low-Level-Tool. Für normale Benutzer-Workflows von Ihrer Workstation bevorzugen Sie `rdc`-Befehle wie `rdc repo up` und `rdc repo down`. Siehe [rdc vs renet](/de/docs/rdc-vs-renet).

### Beispiel

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

> **Wichtig:** Verwenden Sie immer `renet compose --` anstelle von `docker compose`. Der `renet compose`-Wrapper erzwingt Host-Networking, IP-Zuweisung und Service-Discovery-Labels, die von renet-proxy benötigt werden. CRIU-Checkpoint/Restore-Fähigkeiten werden zu Containern mit dem Label `rediacc.checkpoint=true` hinzugefügt. Die direkte Verwendung von `docker compose` wird durch die Rediaccfile-Validierung abgelehnt. Siehe [Netzwerk](/de/docs/networking) für Details.

### Multi-Service-Layout

Für Projekte mit mehreren unabhängigen Dienstgruppen verwenden Sie Unterverzeichnisse:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: gemeinsames Setup
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Datenbankdienste
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API-Server
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana usw.
    └── docker-compose.yml
```

Ausführungsreihenfolge für `up`: Root, dann `backend`, `database`, `monitoring` (A-Z).
Ausführungsreihenfolge für `down`: `monitoring`, `database`, `backend`, dann Root (Z-A).

## Dienst-Netzwerk (.rediacc.json)

Jedes Repository erhält ein /26-Subnetz (64 IPs) im `127.x.x.x`-Loopback-Bereich. Dienste binden sich an eindeutige Loopback-IPs, sodass sie auf denselben Ports ohne Konflikte laufen können.

### Die .rediacc.json-Datei

Ordnet Dienstnamen **Slot**-Nummern zu. Jeder Slot entspricht einer eindeutigen IP-Adresse innerhalb des Repository-Subnetzes.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Automatische Generierung aus Docker Compose

Sie müssen `.rediacc.json` nicht manuell erstellen. Wenn Sie `rdc repo up` ausführen, führt Rediacc automatisch folgende Schritte durch:

1. Durchsucht alle Verzeichnisse mit einem Rediaccfile nach Compose-Dateien (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` oder `compose.yaml`)
2. Extrahiert Dienstnamen aus dem `services:`-Abschnitt
3. Weist jedem neuen Dienst den nächsten verfügbaren Slot zu
4. Speichert das Ergebnis in `{repository}/.rediacc.json`

### IP-Berechnung

Die IP eines Dienstes wird aus der Netzwerk-ID des Repositories und dem Slot des Dienstes berechnet. Die Netzwerk-ID wird auf das zweite, dritte und vierte Oktett einer `127.x.y.z`-Loopback-Adresse aufgeteilt. Dienste starten bei Offset 2:

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Beispiel** für Netzwerk-ID `2816` (`0x0B00`), Basisadresse `127.0.11.0`:

| Dienst | Slot | IP-Adresse |
|--------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Jedes Repository unterstützt bis zu **61 Dienste** (Slots 0 bis 60).

### Verwendung von Dienst-IPs in Docker Compose

Da jedes Repository einen isolierten Docker-Daemon ausführt, konfiguriert `renet compose` automatisch `network_mode: host` für alle Dienste. Der Kernel schreibt `bind()`-Aufrufe transparent auf die zugewiesene Loopback-IP des Dienstes um, sodass Dienste an `0.0.0.0` oder `localhost` binden können ohne Konflikte. Für Verbindungen **zu anderen Diensten** verwenden Sie den **Dienstnamen**. renet injiziert jeden Dienstnamen als Hostname, der immer zur richtigen IP auflöst, auch in Forks:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Kein explizites listen_addresses nötig -- der Kernel schreibt bind auf die korrekte Loopback-IP um

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # Dienstnamen verwenden
      LISTEN_ADDR: 0.0.0.0:8080                                      # Kernel schreibt auf Dienst-IP um
```

> **Dienstnamen für Verbindungen:** Verwenden Sie den **Dienstnamen** (z. B. `postgres`, `redis`) um **zu anderen Diensten zu verbinden** -- renet mappt automatisch jeden Dienstnamen auf seine Loopback-IP via `/etc/hosts`. `${POSTGRES_IP}` in Verbindungsstrings einzubetten, die in Datenbanken oder Konfigurationsdateien gespeichert werden, bäckt die rohe IP ein, was Fork-Isolation bricht und ein **Validierungsfehler** ist. Die `${SERVICE_IP}`-Variablen sind weiterhin für explizite Nutzung verfügbar, aber das Binden wird automatisch vom Kernel übernommen.

> **Hinweis:** Fügen Sie `network_mode: host` nicht manuell hinzu, `renet compose` injiziert es automatisch. Restart-Richtlinien (z.B. `restart: always`) sind sicher zu verwenden, renet entfernt sie automatisch für CRIU-Kompatibilität und der Router-Watchdog übernimmt die Container-Wiederherstellung.

### Container-Wiederherstellung und Neustart-Richtlinie

renet und Docker sind absichtlich unterschiedlicher Meinung, wie Container-Neustarts zu behandeln sind. Dieses Verständnis ist wichtig bei der Fehlersuche, warum ein Container (nicht) zurückgekehrt ist.

**Übersetzung der Neustart-Richtlinie.** Wenn Sie `restart: always` (oder `unless-stopped` oder `on-failure`) in Ihrer Compose-Datei schreiben, **entfernt** renet diese beim Erstellen des tatsächlichen Compose-Deployments und ersetzt sie durch `restart: no`. Der ursprüngliche Wert wird in `.rediacc.json` des Repositories unter `services.<name>.restart_policy` gespeichert. Dies verhindert, dass Docker's daemon-seitiger Auto-Restart in CRIU-Checkpoint/Restore eingreift (ein daemon-gesteuerter Neustart würde aus einem veralteten Zustand vor dem Checkpoint fortgesetzt).

**Watchdog-Durchsetzung.** Der Router-Watchdog läuft periodisch auf jeder Maschine. Bei jedem Tick:

1. Liest er `.rediacc.json` für jedes Repository und findet Dienste mit einer wiederherstellbaren `restart_policy`.
2. Listet alle Container für den Daemon dieses Repositories auf, identifiziert gestoppte und startet sie gemäß der gespeicherten Richtlinie neu. Eine 30-sekündige Kulanzzeit verhindert Konflikte mit einem Operator, der gerade `docker stop` ausgeführt hat.
3. Dieselbe Schleife verarbeitet auch `/var/run/rediacc/cold-backup-<guid>.running.json` (siehe [Cold-Backup-Semantik](backup-restore.md#cold-backup-semantics)). Aufgelistete Container werden unabhängig von der gespeicherten Richtlinie neu gestartet, da das Sidecar bedeutet: "renet hat diese Container absichtlich gestoppt und schuldet dem Operator einen Neustart."

**Warum `on-failure` kaputt wirken kann.** Docker's `on-failure`-Richtlinie startet nur neu, wenn der Container mit einem Nicht-Null-Code beendet wird. Ein ordnungsgemäßes Stoppen (Exit 0) durch `docker stop` oder einen Daemon-Shutdown ist kein "Fehler" und löst keinen Neustart aus, weder durch Docker's native Logik noch durch den gespeicherten Richtlinienpfad des Watchdogs. Das Cold-Backup-Sidecar ist das Sicherheitsnetz: Jeder Container, den wir absichtlich gestoppt haben, wird unabhängig von seiner Richtlinie neu gestartet.

**Laufzeitzustand interpretieren:**

- `docker inspect <container>` → `RestartPolicy.Name`: wird für renet-verwaltete Container immer `no` sein. Verlassen Sie sich nicht darauf für die semantische Richtlinie.
- `.rediacc.json` im Repository-Mount-Root → `services.<name>.restart_policy`: die eigentliche Absicht.
- `docker ps --format '{{.Status}}'`: Laufzeitzustand.

**Abweichung beheben.** Wenn die in `.rediacc.json` gespeicherte Richtlinie eines Containers falsch ist (z. B. weil Sie Compose bearbeitet, den Container aber nie neu erstellt haben), führen Sie `rdc repo up --name <repo> -m <machine>` erneut aus. Der Container wird mit der aktualisierten gespeicherten Richtlinie neu erstellt.

> **Experimentell:** Die Cold-Backup-Sidecar-basierte Wiederherstellung und das Flag `--sync-certs` bei `rdc machine query` wurden in renet 0.9+ eingeführt. Ältere Versionen verlassen sich ausschließlich auf die gespeicherte `restart_policy` für Watchdog-Wiederherstellung, was `on-failure`-Container nach einem Cold-Backup hängen lassen kann.

> **Docker-Bridge-Networking ist für pro-Repo-Daemons deaktiviert.** Jeder pro-Repo-Daemon (`FlavorRediacc`) ist mit `"bridge": "none"` und `"iptables": false` konfiguriert. Ein einfaches `docker run <image>` innerhalb einer Repository-Shell startet zwar, aber der Container erhält lediglich ein Loopback-Interface und verfügt weder über DNS noch über ausgehende Konnektivität. Dies ist beabsichtigt, da die Loopback-Isolation zwischen Repos durch eBPF-cgroup-Hooks erzwungen wird, die ein Bridged-Container umgehen würde. Produktionsdienste sollten `renet compose` verwenden (das Host-Networking für Sie injiziert); für Ad-hoc-Debugging übergeben Sie `--network host` explizit: `docker run --rm --network host -it ubuntu bash`.
>
> Hub-Daemons pro Benutzer (`FlavorHub`, für Entwicklungsumgebungen) sind die Ausnahme: Sie setzen `bridge="docker0"`, `iptables=true` und `live-restore=true`, damit vom Benutzer gestartete Container normales Bridge-Networking und ausgehende Konnektivität erhalten.

> **Hinweis:** Fork-Repos erhalten Auto-Routen unter der Subdomain des Eltern-Repos: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Benutzerdefinierte Domains werden bei Forks übersprungen.

## Dienste starten

Repository einbinden und alle Dienste starten:

```bash
rdc repo up --name my-app -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--skip-router-restart` | Route-Server-Neustart nach der Operation überspringen |

Die Ausführungssequenz ist:
1. Das LUKS-verschlüsselte Repository einbinden (automatisch, wenn nicht eingebunden)
2. Den isolierten Docker-Daemon starten
3. `.rediacc.json` automatisch aus Compose-Dateien generieren
4. `up()` in allen Rediaccfiles ausführen (A-Z-Reihenfolge)

Nach der Bereitstellung zeigt die Ausgabe einen **PROXY ROUTES**-Abschnitt mit den tatsächlichen URLs für jeden Dienst. Dienste mit benutzerdefinierten Traefik-Labels (z.B. `traefik.http.routers.myapp.rule=Host(...)`) zeigen ihre benutzerdefinierten Domains als primäre URLs:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

Dienste ohne benutzerdefinierte Traefik-Labels zeigen nur die auto-generierte Route. Verwenden Sie diese URLs (nicht das generische Muster, das von der CLI gedruckt wird) für Browserzugriff, API-Aufrufe und Konfiguration zwischen Diensten.

## Dienste stoppen

```bash
rdc repo down --name my-app -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--unmount` | Das verschlüsselte Repository nach dem Stoppen aushängen. Falls dies nicht wirksam wird, verwenden Sie `rdc repo unmount` separat. |
| `--skip-router-restart` | Route-Server-Neustart nach der Operation überspringen |

Die Ausführungssequenz ist:
1. `down()` in allen Rediaccfiles ausführen (Z-A umgekehrte Reihenfolge, Best-Effort)
2. Den isolierten Docker-Daemon stoppen (wenn `--unmount`)
3. Das LUKS-verschlüsselte Volume aushängen und schließen (wenn `--unmount`)

## Massenoperationen

Alle Repositories auf einer Maschine gleichzeitig starten oder stoppen:

```bash
rdc repo up -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--include-forks` | Geforkte Repositories einschließen |
| `--mount-only` | Nur einbinden, keine Container starten |
| `--dry-run` | Anzeigen, was ausgeführt würde |
| `--parallel` | Operationen parallel ausführen |
| `--concurrency <n>` | Maximale parallele Operationen (Standard: 3) |
| `--skip-router-restart` | Route-Server-Neustart nach der Operation überspringen |

## Autostart beim Hochfahren

Standardmäßig müssen Repositories nach einem Server-Neustart manuell eingebunden und gestartet werden. **Autostart** konfiguriert Repositories so, dass sie beim Hochfahren des Servers automatisch eingebunden werden, Docker gestartet und das Rediaccfile `up()` ausgeführt wird.

### Funktionsweise

Wenn Sie Autostart für ein Repository aktivieren:

1. Wird eine 256 Byte große zufällige LUKS-Schlüsseldatei generiert und dem LUKS-Slot 1 des Repositories hinzugefügt (Slot 0 bleibt die Benutzer-Passphrase)
2. Die Schlüsseldatei wird unter `{datastore}/.credentials/keys/{guid}.key` mit `0600`-Berechtigungen (nur Root) gespeichert
3. Ein systemd-Dienst (`rediacc-autostart`) wird beim Hochfahren ausgeführt, um alle aktivierten Repositories einzubinden und deren Dienste zu starten

Beim Herunterfahren stoppt der Dienst ordnungsgemäß alle Dienste (Rediaccfile `down()`), stoppt Docker-Daemons und schließt LUKS-Volumes.

> **Sicherheitshinweis:** Das Aktivieren von Autostart speichert eine LUKS-Schlüsseldatei auf der Festplatte des Servers. Jeder mit Root-Zugriff auf den Server kann das Repository ohne Passphrase einbinden. Bewerten Sie dies basierend auf Ihrem Bedrohungsmodell.

### Aktivieren

```bash
rdc repo autostart enable --name my-app -m server-1
```

Sie werden nach der Repository-Passphrase gefragt.

### Alle aktivieren

```bash
rdc repo autostart enable -m server-1
```

### Deaktivieren

```bash
rdc repo autostart disable --name my-app -m server-1
```

Dies entfernt die Schlüsseldatei und löscht LUKS-Slot 1.

### Schlüsseldatei-Aktualisierung beim Deployment

Wenn Autostart aktiviert ist, validiert `rdc repo up` die LUKS-Slot-1-Schlüsseldatei.
Falls die auf der Festplatte gespeicherte Schlüsseldatei noch mit dem LUKS-Slot übereinstimmt, werden keine Änderungen vorgenommen.

Nach der Übertragung eines Repositories zwischen Maschinen via `repo push` / `repo pull`
stimmt die Schlüsseldatei auf der neuen Maschine nicht überein. In diesem Fall regeneriert `repo up` automatisch
die Schlüsseldatei und aktualisiert LUKS-Slot 1. Sie sehen folgende Log-Meldungen:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

Dies ist sicher, Slot 0 (Ihre Passphrase) wird nie geändert. Wenn Autostart nicht
aktiviert ist, wird die Prüfung stillschweigend übersprungen. Fehler sind nicht-kritisch und blockieren das Deployment nicht.

### Status anzeigen

```bash
rdc repo autostart list -m server-1
```

Informationen dazu, wie der periodische Reconciler Repositories wiederherstellt, die nach dem Start ausfallen, finden Sie unter [Autostart & Wiederherstellung](/de/docs/autostart-recovery).

## Vollständiges Beispiel

Dieses Beispiel stellt eine Webanwendung mit PostgreSQL, Redis und einem API-Server bereit.

### 1. Einrichten

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Einbinden und vorbereiten

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Anwendungsdateien erstellen

Erstellen Sie innerhalb des Repositories die folgenden Dateien:

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

### 4. Starten

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Autostart aktivieren

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Pro-Repo-Geheimnisse in Compose verwenden

Der Platzhalter `POSTGRES_PASSWORD: changeme` oben ist für ein Tutorial in Ordnung, aber echte Apps benötigen echte Anmeldedaten, und das Committen davon in die Compose-Datei (oder eine `.env`-Datei innerhalb des Repositories) bedeutet, dass Forks diese auch erben. Verwenden Sie für Deploy-Zeit-Anmeldedaten `rdc repo secret`. Werte liegen außerhalb des verschlüsselten Repository-Images, daher starten Forks mit einer leeren Secrets-Map.

Zwei Liefermodi funktionieren in Compose:

**`env`-Modus.** Interpoliert via `${REDIACC_SECRET_<KEY>}` in jedem `environment:`-Wert. Der renet-Wrapper übergibt den Wert zur Deploy-Zeit in die Container-Umgebung.

**`file`-Modus.** Der Wert landet in einer Host-seitigen tmpfs-Datei unter `/var/run/rediacc/secrets/<networkID>/<KEY>`, und Sie mounten ihn in den Container via Docker Compose's Standard `secrets:`-Block. Der Container liest `/run/secrets/<key>`. Bevorzugen Sie diesen Modus für alles Sensible. Werte erscheinen niemals in `docker inspect` oder `/proc/<pid>/environ`.

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

Seeden Sie die Werte mit `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` und dem Äquivalent für File-Modus. Siehe [Repositories § Geheimnisse](/de/docs/repositories#secrets) für die vollständige Anleitung und [Pro-Repo-Geheimnisse](/de/docs/rdc-cheat-sheet#per-repo-secrets) im Spickzettel für die Befehlsreferenz.

> **Cross-Repo-Pfade werden zur Validierungszeit abgelehnt.** Ein Compose-`secrets: file:` (oder `configs: file:`, oder `env_file:`), das auf das `/var/run/rediacc/secrets/<other-networkID>/`-Verzeichnis eines anderen Repositories zeigt, wird von dem renet-Wrapper vor docker compose mit Hard-Reject blockiert. `--unsafe` überschreibt es NICHT. Defense-in-depth: Der Landlock-Sandbox um die Rediaccfile-Shell bewältigt Lesen auf das secrets-Verzeichnis des aktuellen Netzwerks, sodass ein `cat /var/run/rediacc/secrets/<other>/X` aus Rediaccfile-Bash mit EACCES fehlschlägt, selbst wenn es den YAML-Validator umgeht. Sie müssen es nicht explizit aktivieren; dies ist standardmäßig für alle `repo up` aktiviert.
