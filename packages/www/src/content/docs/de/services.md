---
title: Dienste
description: >-
  Überblick über containerisierte Dienste mit Rediaccfiles, Dienst-Netzwerk und
  Autostart bereitstellen und verwalten.
category: Guides
order: 5
language: de
sourceHash: c4048b13799a7767
---

# Dienste

Wenn Sie unsicher sind, welches Tool Sie verwenden sollen, lesen Sie [rdc vs renet](/de/docs/rdc-vs-renet).

Diese Seite behandelt die Bereitstellung und Verwaltung containerisierter Dienste: Rediaccfiles, Dienst-Netzwerk, Starten/Stoppen, Massenoperationen und Autostart.

## Das Rediaccfile

Das **Rediaccfile** ist ein Bash-Skript, das definiert, wie Ihre Dienste vorbereitet, gestartet und gestoppt werden. Es muss `Rediaccfile` oder `rediaccfile` (Groß-/Kleinschreibung wird nicht unterschieden) heißen und im eingebundenen Dateisystem des Repositories platziert werden.

Rediaccfiles werden an zwei Orten gesucht:
1. Im **Stammverzeichnis** des Repository-Einbindungspfads
2. In **Unterverzeichnissen der ersten Ebene** des Einbindungspfads (nicht rekursiv)

Versteckte Verzeichnisse (Namen, die mit `.` beginnen) werden übersprungen.

### Lebenszyklus-Funktionen

Ein Rediaccfile enthält bis zu drei Funktionen:

| Funktion | Ausführungszeitpunkt | Zweck | Fehlerverhalten |
|----------|---------------------|-------|-----------------|
| `prep()` | Vor `up()` | Abhängigkeiten installieren, Images pullen, Migrationen ausführen | **Fail-Fast** -- wenn eine `prep()` fehlschlägt, wird der gesamte Prozess sofort gestoppt. |
| `up()` | Nach Abschluss aller `prep()` | Dienste starten (z. B. `docker compose up -d`) | Fehler im Root-Rediaccfile sind **kritisch** (stoppt alles). Fehler in Unterverzeichnissen sind **nicht-kritisch** (werden protokolliert, es wird mit dem nächsten fortgefahren). |
| `down()` | Beim Stoppen | Dienste stoppen (z. B. `docker compose down`) | **Best-Effort** -- Fehler werden protokolliert, aber alle Rediaccfiles werden immer verarbeitet. |

Alle drei Funktionen sind optional. Wenn eine Funktion nicht definiert ist, wird sie stillschweigend übersprungen.

### Ausführungsreihenfolge

- **Starten (`up`):** Zuerst das Root-Rediaccfile, dann Unterverzeichnisse in **alphabetischer Reihenfolge** (A bis Z).
- **Stoppen (`down`):** Unterverzeichnisse in **umgekehrt alphabetischer Reihenfolge** (Z bis A), dann zuletzt das Root.

### Umgebungsvariablen

Wenn eine Rediaccfile-Funktion ausgeführt wird, stehen folgende Umgebungsvariablen zur Verfügung:

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Einbindungspfad des Repositories | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | Repository-GUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | Netzwerk-ID (Ganzzahl) | `2816` |
| `DOCKER_HOST` | Docker-Socket für den isolierten Daemon dieses Repositories | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | Loopback-IP für jeden in `.rediacc.json` definierten Dienst | `POSTGRES_IP=127.0.11.2` |

Die `{SERVICE}_IP`-Variablen werden automatisch aus `.rediacc.json` generiert. Die Namenskonvention wandelt den Dienstnamen in Großbuchstaben um, ersetzt Bindestriche durch Unterstriche und hängt `_IP` an. Zum Beispiel wird `listmonk-app` zu `LISTMONK_APP_IP`.

> **Warnung: Verwenden Sie kein `sudo docker` in Rediaccfiles.** Der `sudo`-Befehl setzt Umgebungsvariablen zurück, wodurch `DOCKER_HOST` verloren geht und Docker-Befehle den System-Daemon statt des isolierten Repository-Daemons ansprechen. Dies bricht die Container-Isolation und kann Port-Konflikte verursachen. Rediacc blockiert die Ausführung, wenn es `sudo docker` ohne `-E` erkennt.
>
> Verwenden Sie `renet compose` in Ihren Rediaccfiles -- es übernimmt automatisch `DOCKER_HOST`, injiziert Netzwerk-Labels für die Routen-Erkennung und konfiguriert das Dienst-Netzwerk. Siehe [Netzwerk](/de/docs/networking) für Details, wie Dienste über den Reverse Proxy bereitgestellt werden. Wenn Sie Docker direkt aufrufen, verwenden Sie `docker` ohne `sudo` -- Rediaccfile-Funktionen laufen bereits mit ausreichenden Rechten. Wenn Sie sudo verwenden müssen, nutzen Sie `sudo -E docker`, um Umgebungsvariablen zu erhalten.

### Beispiel

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` funktioniert ebenfalls, da `DOCKER_HOST` automatisch gesetzt wird, aber `renet compose` wird bevorzugt, weil es zusätzlich `rediacc.*`-Labels injiziert, die für die Reverse-Proxy-Routen-Erkennung benötigt werden. Siehe [Netzwerk](/de/docs/networking) für Details.

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

Die IP eines Dienstes wird aus der Netzwerk-ID des Repositories und dem Slot des Dienstes berechnet. Die Netzwerk-ID wird auf das zweite, dritte und vierte Oktett einer `127.x.y.z`-Loopback-Adresse aufgeteilt. Jeder Dienst erhält einen Offset von `slot + 2` (Offsets 0 und 1 sind reserviert).

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

Da jedes Repository einen isolierten Docker-Daemon ausführt, verwenden Dienste `network_mode: host` und binden sich an ihre zugewiesenen Loopback-IPs:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## Dienste starten

Repository einbinden und alle Dienste starten:

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Beschreibung |
|--------|-------------|
| `--mount` | Repository zuerst einbinden, falls noch nicht eingebunden |
| `--prep-only` | Nur die `prep()`-Funktionen ausführen, `up()` überspringen |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Die Ausführungssequenz ist:
1. Das LUKS-verschlüsselte Repository einbinden (wenn `--mount`)
2. Den isolierten Docker-Daemon starten
3. `.rediacc.json` automatisch aus Compose-Dateien generieren
4. `prep()` in allen Rediaccfiles ausführen (A-Z-Reihenfolge, Fail-Fast)
5. `up()` in allen Rediaccfiles ausführen (A-Z-Reihenfolge)

## Dienste stoppen

```bash
rdc repo down my-app -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--unmount` | Das verschlüsselte Repository nach dem Stoppen aushängen |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Die Ausführungssequenz ist:
1. `down()` in allen Rediaccfiles ausführen (Z-A umgekehrte Reihenfolge, Best-Effort)
2. Den isolierten Docker-Daemon stoppen (wenn `--unmount`)
3. Das LUKS-verschlüsselte Volume aushängen und schließen (wenn `--unmount`)

## Massenoperationen

Alle Repositories auf einer Maschine gleichzeitig starten oder stoppen:

```bash
rdc repo up-all -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--include-forks` | Geforkte Repositories einschließen |
| `--mount-only` | Nur einbinden, keine Container starten |
| `--dry-run` | Anzeigen, was ausgeführt würde |
| `--parallel` | Operationen parallel ausführen |
| `--concurrency <n>` | Maximale parallele Operationen (Standard: 3) |
| `--skip-router-restart` | Skip restarting the route server after the operation |

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
rdc repo autostart enable my-app -m server-1
```

Sie werden nach der Repository-Passphrase gefragt.

### Alle aktivieren

```bash
rdc repo autostart enable-all -m server-1
```

### Deaktivieren

```bash
rdc repo autostart disable my-app -m server-1
```

Dies entfernt die Schlüsseldatei und löscht LUKS-Slot 1.

### Status anzeigen

```bash
rdc repo autostart list -m server-1
```

## Vollständiges Beispiel

Dieses Beispiel stellt eine Webanwendung mit PostgreSQL, Redis und einem API-Server bereit.

### 1. Einrichten

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Einbinden und vorbereiten

```bash
rdc repo mount webapp -m prod-1
```

### 3. Anwendungsdateien erstellen

Erstellen Sie innerhalb des Repositories die folgenden Dateien:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up webapp -m prod-1
```

### 5. Autostart aktivieren

```bash
rdc repo autostart enable webapp -m prod-1
```
