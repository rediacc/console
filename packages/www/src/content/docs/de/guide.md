---
title: "Schritt-für-Schritt-Anleitung"
description: "Stellen Sie verschlüsselte, isolierte Infrastruktur auf Ihren eigenen Servern mit Rediacc im lokalen Modus bereit."
category: "Getting Started"
order: 2
language: de
---

# Schritt-für-Schritt-Anleitung

Diese Anleitung führt Sie durch die Bereitstellung verschlüsselter, isolierter Infrastruktur auf Ihren eigenen Servern mit Rediacc im **lokalen Modus**. Am Ende werden Sie ein voll funktionsfähiges Repository haben, das containerisierte Dienste auf einem entfernten Rechner ausführt -- alles von Ihrer Workstation aus verwaltet.

Lokaler Modus bedeutet, dass alles auf Infrastruktur läuft, die Sie kontrollieren. Keine Cloud-Konten, keine SaaS-Abhängigkeiten. Ihre Workstation orchestriert entfernte Server über SSH, und der gesamte Zustand wird lokal auf Ihrem Rechner und auf den Servern selbst gespeichert.

## Architekturübersicht

Rediacc verwendet eine Zwei-Tool-Architektur:

```
Ihre Workstation                    Entfernter Server
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** läuft auf Ihrer Workstation (macOS oder Linux). Es liest Ihre lokale Konfiguration, verbindet sich über SSH mit entfernten Rechnern und ruft renet-Befehle auf.
- **renet** läuft auf dem entfernten Server mit Root-Rechten. Es verwaltet LUKS-verschlüsselte Disk-Images, isolierte Docker-Daemons, Service-Orchestrierung und Reverse-Proxy-Konfiguration.

Jeder Befehl, den Sie lokal eingeben, wird in einen SSH-Aufruf übersetzt, der renet auf dem entfernten Rechner ausführt. Sie müssen sich nie manuell per SSH auf den Servern anmelden.

## Schritt 1: Einen lokalen Kontext erstellen

Ein **Kontext** ist eine benannte Konfiguration, die Ihre SSH-Zugangsdaten, Maschinendefinitionen und Repository-Zuordnungen speichert. Betrachten Sie ihn als Projekt-Arbeitsbereich.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `--ssh-key <path>` | Ja | Pfad zu Ihrem privaten SSH-Schlüssel. Die Tilde (`~`) wird automatisch expandiert. |
| `--renet-path <path>` | Nein | Benutzerdefinierter Pfad zur renet-Binary auf entfernten Rechnern. Standardmäßig der Standard-Installationspfad. |

Dies erstellt einen lokalen Kontext namens `my-infra` und speichert ihn in `~/.rediacc/config.json`.

> Sie können mehrere Kontexte haben (z. B. `production`, `staging`, `dev`). Wechseln Sie zwischen ihnen mit dem `--context`-Flag bei jedem Befehl.

## Schritt 2: Eine Maschine hinzufügen

Registrieren Sie Ihren entfernten Server als Maschine im Kontext:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--ip <address>` | Ja | - | IP-Adresse oder Hostname des entfernten Servers. |
| `--user <username>` | Ja | - | SSH-Benutzername auf dem entfernten Server. |
| `--port <port>` | Nein | `22` | SSH-Port. |
| `--datastore <path>` | Nein | `/mnt/rediacc` | Pfad auf dem Server, an dem Rediacc verschlüsselte Repositories speichert. |

Nach dem Hinzufügen der Maschine führt rdc automatisch `ssh-keyscan` aus, um die Host-Schlüssel des Servers abzurufen. Sie können dies auch manuell ausführen:

```bash
rdc context scan-keys server-1
```

Um alle registrierten Maschinen anzuzeigen:

```bash
rdc context machines
```

## Schritt 3: Die Maschine einrichten

Provisionieren Sie den entfernten Server mit allen erforderlichen Abhängigkeiten:

```bash
rdc context setup-machine server-1
```

Dieser Befehl:
1. Lädt die renet-Binary per SFTP auf den Server hoch
2. Installiert Docker, containerd und cryptsetup (falls nicht vorhanden)
3. Erstellt das Datastore-Verzeichnis und bereitet es für verschlüsselte Repositories vor

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--datastore <path>` | Nein | `/mnt/rediacc` | Datastore-Verzeichnis auf dem Server. |
| `--datastore-size <size>` | Nein | `95%` | Anteil des verfügbaren Speichers, der für den Datastore reserviert wird. |
| `--debug` | Nein | `false` | Aktiviert ausführliche Ausgabe zur Fehlerbehebung. |

> Die Einrichtung muss nur einmal pro Maschine ausgeführt werden. Eine erneute Ausführung ist bei Bedarf sicher möglich.

## Schritt 4: Ein Repository erstellen

Ein **Repository** ist ein LUKS-verschlüsseltes Disk-Image auf dem entfernten Server. Nach dem Einbinden bietet es:
- Ein isoliertes Dateisystem für Ihre Anwendungsdaten
- Einen dedizierten Docker-Daemon (getrennt vom Docker des Hosts)
- Einzigartige Loopback-IPs für jeden Dienst innerhalb eines /26-Subnetzes

Erstellen Sie ein Repository:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `-m, --machine <name>` | Ja | Zielmaschine, auf der das Repository erstellt wird. |
| `--size <size>` | Ja | Größe des verschlüsselten Disk-Images (z. B. `5G`, `10G`, `50G`). |

Die Ausgabe zeigt drei automatisch generierte Werte:

- **Repository-GUID** -- Eine UUID, die das verschlüsselte Disk-Image auf dem Server identifiziert.
- **Credential** -- Eine zufällige Passphrase zum Ver- und Entschlüsseln des LUKS-Volumes.
- **Netzwerk-ID** -- Eine Ganzzahl (beginnend bei 2816, um 64 inkrementiert), die das IP-Subnetz für die Dienste dieses Repositories bestimmt.

> **Bewahren Sie das Credential sicher auf.** Es ist der Verschlüsselungsschlüssel für Ihr Repository. Bei Verlust können die Daten nicht wiederhergestellt werden. Das Credential wird in Ihrer lokalen `config.json` gespeichert, jedoch nicht auf dem Server.

## Schritt 5: Das Rediaccfile

Das **Rediaccfile** ist ein Bash-Skript, das definiert, wie Ihre Dienste vorbereitet, gestartet und gestoppt werden. Es ist der zentrale Mechanismus für die Verwaltung des Dienst-Lebenszyklus.

### Was ist ein Rediaccfile?

Ein Rediaccfile ist ein einfaches Bash-Skript, das bis zu drei Funktionen enthält: `prep()`, `up()` und `down()`. Es muss `Rediaccfile` oder `rediaccfile` (Groß-/Kleinschreibung wird nicht unterschieden) heißen und im eingebundenen Dateisystem des Repositories platziert werden.

Rediaccfiles werden an zwei Orten gesucht:
1. Im **Stammverzeichnis** des Repository-Einbindungspfads
2. In **Unterverzeichnissen der ersten Ebene** des Einbindungspfads (nicht rekursiv)

Versteckte Verzeichnisse (Namen, die mit `.` beginnen) werden übersprungen.

### Lebenszyklus-Funktionen

| Funktion | Ausführungszeitpunkt | Zweck | Fehlerverhalten |
|----------|---------------------|-------|-----------------|
| `prep()` | Vor `up()` | Abhängigkeiten installieren, Images pullen, Migrationen ausführen | **Fail-Fast** -- wenn eine `prep()` fehlschlägt, wird der gesamte Prozess sofort gestoppt. |
| `up()` | Nach Abschluss aller `prep()` | Dienste starten (z. B. `docker compose up -d`) | Fehler im Root-Rediaccfile sind **kritisch** (stoppt alles). Fehler in Unterverzeichnissen sind **nicht-kritisch** (werden protokolliert, es wird mit dem nächsten fortgefahren). |
| `down()` | Beim Stoppen | Dienste stoppen (z. B. `docker compose down`) | **Best-Effort** -- Fehler werden protokolliert, aber alle Rediaccfiles werden immer verarbeitet. |

Alle drei Funktionen sind optional. Wenn eine Funktion in einem Rediaccfile nicht definiert ist, wird sie stillschweigend übersprungen.

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

Die `{SERVICE}_IP`-Variablen werden automatisch aus `.rediacc.json` generiert (siehe Schritt 6). Die Namenskonvention wandelt den Dienstnamen in Großbuchstaben um, ersetzt Bindestriche durch Unterstriche und hängt `_IP` an. Zum Beispiel wird `listmonk-app` zu `LISTMONK_APP_IP`.

### Beispiel-Rediaccfile

Ein einfaches Rediaccfile für eine Webanwendung:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### Multi-Service-Beispiel

Für Projekte mit mehreren unabhängigen Dienstgruppen verwenden Sie Unterverzeichnisse:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: gemeinsames Setup (z. B. Docker-Netzwerke erstellen)
├── docker-compose.yml       # Root-Compose-Datei
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

## Schritt 6: Dienst-Netzwerk (.rediacc.json)

Jedes Repository erhält ein /26-Subnetz (64 IPs) im `127.x.x.x`-Loopback-Bereich. Dienste binden sich an eindeutige Loopback-IPs, sodass sie auf denselben Ports ohne Konflikte laufen können. Zum Beispiel können zwei PostgreSQL-Instanzen beide auf Port 5432 lauschen, jeweils auf einer anderen IP.

### Die .rediacc.json-Datei

Die `.rediacc.json`-Datei ordnet Dienstnamen **Slot**-Nummern zu. Jeder Slot entspricht einer eindeutigen IP-Adresse innerhalb des Repository-Subnetzes.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Dienste werden in alphabetischer Reihenfolge geschrieben.

### Automatische Generierung aus Docker Compose

Sie müssen `.rediacc.json` nicht manuell erstellen. Wenn Sie `rdc repo up` ausführen, führt Rediacc automatisch folgende Schritte durch:

1. Durchsucht alle Verzeichnisse mit einem Rediaccfile nach Compose-Dateien (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` oder `compose.yaml`).
2. Extrahiert Dienstnamen aus dem `services:`-Abschnitt jeder Compose-Datei.
3. Weist jedem neuen Dienst den nächsten verfügbaren Slot zu.
4. Speichert das Ergebnis in `{repository}/.rediacc.json`.

### IP-Berechnung

Die IP eines Dienstes wird aus der Netzwerk-ID des Repositories und dem Slot des Dienstes berechnet. Die Netzwerk-ID wird auf das zweite, dritte und vierte Oktett einer `127.x.y.z`-Loopback-Adresse aufgeteilt. Jeder Dienst erhält einen Offset von `slot + 2` zur Netzwerk-ID (Offsets 0 und 1 sind für die Netzwerkadresse und das Gateway reserviert).

Zum Beispiel ist bei Netzwerk-ID `2816` (`0x0B00`) die Basisadresse `127.0.11.0` und Dienste beginnen bei `127.0.11.2`.

**Beispiel** für Netzwerk-ID `2816`:

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

Die Variablen `${POSTGRES_IP}` und `${API_IP}` werden automatisch aus `.rediacc.json` exportiert, wenn das Rediaccfile ausgeführt wird.

## Schritt 7: Dienste starten

Binden Sie das Repository ein und starten Sie alle Dienste:

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `-m, --machine <name>` | Ja | Zielmaschine. |
| `--mount` | Nein | Repository zuerst einbinden, falls noch nicht eingebunden. Ohne dieses Flag muss das Repository bereits eingebunden sein. |
| `--prep-only` | Nein | Nur die `prep()`-Funktionen ausführen, `up()` überspringen. Nützlich zum Vorziehen von Images oder zum Ausführen von Migrationen. |

Die Ausführungssequenz ist:

1. Das LUKS-verschlüsselte Repository einbinden (wenn `--mount` angegeben ist)
2. Den isolierten Docker-Daemon für dieses Repository starten
3. `.rediacc.json` automatisch aus Compose-Dateien generieren
4. `prep()` in allen Rediaccfiles ausführen (A-Z-Reihenfolge, Fail-Fast)
5. `up()` in allen Rediaccfiles ausführen (A-Z-Reihenfolge)

## Schritt 8: Dienste stoppen

Alle Dienste in einem Repository stoppen:

```bash
rdc repo down my-app -m server-1
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `-m, --machine <name>` | Ja | Zielmaschine. |
| `--unmount` | Nein | Das verschlüsselte Repository nach dem Stoppen der Dienste aushängen. Dies stoppt auch den isolierten Docker-Daemon und schließt das LUKS-Volume. |

Die Ausführungssequenz ist:

1. `down()` in allen Rediaccfiles ausführen (Z-A umgekehrte Reihenfolge, Best-Effort)
2. Den isolierten Docker-Daemon stoppen (wenn `--unmount`)
3. Das LUKS-verschlüsselte Volume aushängen und schließen (wenn `--unmount`)

## Weitere häufige Operationen

### Einbinden und Aushängen (ohne Dienste zu starten)

```bash
rdc repo mount my-app -m server-1     # Entschlüsseln und einbinden
rdc repo unmount my-app -m server-1   # Aushängen und wieder verschlüsseln
```

### Repository-Status prüfen

```bash
rdc repo status my-app -m server-1
```

### Alle Repositories auflisten

```bash
rdc repo list -m server-1
```

### Repository-Größe ändern

```bash
rdc repo resize my-app -m server-1 --size 20G    # Auf exakte Größe setzen
rdc repo expand my-app -m server-1 --size 5G      # 5G zur aktuellen Größe hinzufügen
```

### Repository löschen

```bash
rdc repo delete my-app -m server-1
```

> Dies zerstört dauerhaft das verschlüsselte Disk-Image und alle darin enthaltenen Daten.

### Repository forken

Eine Kopie eines vorhandenen Repositories in seinem aktuellen Zustand erstellen:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Dies erstellt eine neue verschlüsselte Kopie mit eigener GUID und Netzwerk-ID. Der Fork teilt sich das gleiche LUKS-Credential wie das übergeordnete Repository.

### Repository validieren

Die Dateisystemintegrität eines Repositories prüfen:

```bash
rdc repo validate my-app -m server-1
```

## Vollständiges Beispiel: Bereitstellung einer Webanwendung

Dieses End-to-End-Beispiel stellt eine Webanwendung mit PostgreSQL, Redis und einem API-Server bereit.

### 1. Umgebung einrichten

```bash
# rdc installieren
curl -fsSL https://get.rediacc.com | sh

# Einen lokalen Kontext erstellen
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Ihren Server registrieren
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Den Server provisionieren
rdc context setup-machine prod-1

# Ein verschlüsseltes Repository erstellen (10 GB)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Repository einbinden und vorbereiten

```bash
rdc repo mount webapp -m prod-1
```

Verbinden Sie sich per SSH mit dem Server und erstellen Sie die Anwendungsdateien im eingebundenen Repository. Der Einbindungspfad wird in der Ausgabe angezeigt (typischerweise `/mnt/rediacc/repos/{guid}`).

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
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
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
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. Alles starten

```bash
rdc repo up webapp -m prod-1
```

Dies wird:
1. `.rediacc.json` automatisch mit Slots für `api`, `postgres` und `redis` generieren
2. `prep()` ausführen, um Verzeichnisse zu erstellen und Images zu pullen
3. `up()` ausführen, um alle Container zu starten

### 5. Autostart aktivieren

```bash
rdc repo autostart enable webapp -m prod-1
```

Nach einem Server-Neustart wird das Repository automatisch eingebunden und alle Dienste gestartet.
