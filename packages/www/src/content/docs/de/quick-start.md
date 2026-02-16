---
title: "Schnellstart-Anleitung"
description: "Schritt-für-Schritt-Anleitung zur Bereitstellung verschlüsselter, isolierter Infrastruktur auf Ihren eigenen Servern mit Rediacc im lokalen Modus."
category: "Core Concepts"
order: 0
language: de
---

# Schnellstart-Anleitung

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

## Was Sie benötigen

Stellen Sie vor dem Start sicher, dass Sie Folgendes haben:

**Auf Ihrer Workstation:**
- macOS oder Linux mit einem SSH-Client
- Ein SSH-Schlüsselpaar (z. B. `~/.ssh/id_ed25519` oder `~/.ssh/id_rsa`)

**Auf dem entfernten Server:**
- Ubuntu 20.04+ oder Debian 11+ (andere Linux-Distributionen können funktionieren, sind aber nicht getestet)
- Ein Benutzerkonto mit `sudo`-Rechten
- Ihr öffentlicher SSH-Schlüssel in `~/.ssh/authorized_keys` hinterlegt
- Mindestens 20 GB freier Speicherplatz (mehr je nach Ihren Workloads)

## Schritt 1: rdc installieren

Installieren Sie die Rediacc-CLI auf Ihrer Workstation:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Dies lädt die `rdc`-Binary nach `$HOME/.local/bin/` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist. Überprüfen Sie die Installation:

```bash
rdc --help
```

> Führen Sie zum späteren Aktualisieren `rdc update` aus.

## Schritt 2: Einen lokalen Kontext erstellen

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

## Schritt 3: Eine Maschine hinzufügen

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

## Schritt 4: Die Maschine einrichten

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

## Schritt 5: Ein Repository erstellen

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

## Schritt 6: Das Rediaccfile

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

Die `{SERVICE}_IP`-Variablen werden automatisch aus `.rediacc.json` generiert (siehe Schritt 7). Die Namenskonvention wandelt den Dienstnamen in Großbuchstaben um, ersetzt Bindestriche durch Unterstriche und hängt `_IP` an. Zum Beispiel wird `listmonk-app` zu `LISTMONK_APP_IP`.

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

## Schritt 7: Dienst-Netzwerk (.rediacc.json)

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

## Schritt 8: Dienste starten

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

## Schritt 9: Dienste stoppen

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

## Autostart beim Hochfahren

Standardmäßig müssen Repositories nach einem Server-Neustart manuell eingebunden und gestartet werden. **Autostart** konfiguriert Repositories so, dass sie beim Hochfahren des Servers automatisch eingebunden werden, Docker gestartet und das Rediaccfile `up()` ausgeführt wird.

### Funktionsweise

Wenn Sie Autostart für ein Repository aktivieren:

1. Wird ein 256 Byte großer zufälliger LUKS-Schlüsseldatei generiert und dem LUKS-Slot 1 des Repositories hinzugefügt (Slot 0 bleibt die Benutzer-Passphrase).
2. Die Schlüsseldatei wird unter `{datastore}/.credentials/keys/{guid}.key` mit `0600`-Berechtigungen (nur Root) gespeichert.
3. Ein systemd-Dienst (`rediacc-autostart`) wird installiert, der beim Hochfahren alle aktivierten Repositories einbindet und deren Dienste startet.

Beim Herunterfahren oder Neustart des Systems stoppt der Dienst ordnungsgemäß alle Dienste (Rediaccfile `down()`), stoppt Docker-Daemons und schließt LUKS-Volumes.

> **Sicherheitshinweis:** Das Aktivieren von Autostart speichert eine LUKS-Schlüsseldatei auf der Festplatte des Servers. Jeder mit Root-Zugriff auf den Server kann das Repository ohne Passphrase einbinden. Dies ist ein Kompromiss zwischen Komfort (automatisches Hochfahren) und Sicherheit (manuelle Passphrase-Eingabe erforderlich). Bewerten Sie dies basierend auf Ihrem Bedrohungsmodell.

### Autostart aktivieren

```bash
rdc repo autostart enable my-app -m server-1
```

Sie werden nach der Repository-Passphrase gefragt. Diese wird benötigt, um das Hinzufügen der Schlüsseldatei zum LUKS-Volume zu autorisieren.

### Autostart für alle Repositories aktivieren

```bash
rdc repo autostart enable-all -m server-1
```

### Autostart deaktivieren

```bash
rdc repo autostart disable my-app -m server-1
```

Dies entfernt die Schlüsseldatei und löscht LUKS-Slot 1. Das Repository wird beim Hochfahren nicht mehr automatisch eingebunden.

### Autostart-Status anzeigen

```bash
rdc repo autostart list -m server-1
```

Zeigt an, welche Repositories Autostart aktiviert haben und ob der systemd-Dienst installiert ist.

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

## Die Kontext-Konfiguration verstehen

Die gesamte Kontext-Konfiguration wird in `~/.rediacc/config.json` gespeichert. Hier ist ein kommentiertes Beispiel, wie diese Datei nach Abschluss der obigen Schritte aussieht:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Wichtige Felder:**

| Feld | Beschreibung |
|------|-------------|
| `mode` | `"local"` für den lokalen Modus, `"s3"` für S3-gestützte Kontexte. |
| `apiUrl` | `"local://"` zeigt den lokalen Modus an (keine Remote-API). |
| `ssh.privateKeyPath` | Pfad zum privaten SSH-Schlüssel, der für alle Maschinenverbindungen verwendet wird. |
| `machines.<name>.knownHosts` | SSH-Host-Schlüssel von `ssh-keyscan`, zur Überprüfung der Serveridentität. |
| `repositories.<name>.repositoryGuid` | UUID, die das verschlüsselte Disk-Image auf dem Server identifiziert. |
| `repositories.<name>.credential` | LUKS-Verschlüsselungs-Passphrase. **Wird nicht auf dem Server gespeichert.** |
| `repositories.<name>.networkId` | Netzwerk-ID, die das IP-Subnetz bestimmt (2816 + n*64). Automatisch zugewiesen. |

> Diese Datei enthält sensible Daten (SSH-Schlüsselpfade, LUKS-Credentials). Sie wird mit `0600`-Berechtigungen gespeichert (nur Eigentümer lesen/schreiben). Teilen Sie sie nicht und committen Sie sie nicht in die Versionsverwaltung.

## Fehlerbehebung

### SSH-Verbindung schlägt fehl

- Überprüfen Sie, ob Sie sich manuell verbinden können: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Führen Sie `rdc context scan-keys server-1` aus, um Host-Schlüssel zu aktualisieren
- Überprüfen Sie, ob der SSH-Port übereinstimmt: `--port 22`

### Maschineneinrichtung schlägt fehl

- Stellen Sie sicher, dass der Benutzer sudo-Zugriff ohne Passwort hat, oder konfigurieren Sie `NOPASSWD` für die erforderlichen Befehle
- Überprüfen Sie den verfügbaren Speicherplatz auf dem Server
- Führen Sie mit `--debug` für ausführliche Ausgabe aus: `rdc context setup-machine server-1 --debug`

### Repository-Erstellung schlägt fehl

- Überprüfen Sie, ob die Einrichtung abgeschlossen wurde: Das Datastore-Verzeichnis muss existieren
- Überprüfen Sie den Speicherplatz auf dem Server
- Stellen Sie sicher, dass die renet-Binary installiert ist (führen Sie bei Bedarf die Einrichtung erneut aus)

### Dienste starten nicht

- Überprüfen Sie die Rediaccfile-Syntax: Es muss gültiges Bash sein
- Stellen Sie sicher, dass `docker compose`-Dateien `network_mode: host` verwenden
- Überprüfen Sie, ob Docker-Images erreichbar sind (erwägen Sie `docker compose pull` in `prep()`)
- Überprüfen Sie Container-Logs: Verbinden Sie sich per SSH mit dem Server und verwenden Sie `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Zugriff-verweigert-Fehler

- Repository-Operationen erfordern Root auf dem Server (renet wird über `sudo` ausgeführt)
- Überprüfen Sie, ob Ihr Benutzer in der `sudo`-Gruppe ist
- Überprüfen Sie, ob das Datastore-Verzeichnis die richtigen Berechtigungen hat

## Nächste Schritte

- **CLI-Referenz** -- Siehe die Seite [CLI-Anwendung](/de/docs/cli-application) für die vollständige Befehlsreferenz.
- **Backup und Wiederherstellung** -- Richten Sie externe Backups auf S3-kompatiblen Speicher für die Notfallwiederherstellung ein.
- **Reverse Proxy** -- Konfigurieren Sie Traefik für HTTPS mit automatischen Let's Encrypt-Zertifikaten.
- **CRIU Checkpoint/Restore** -- Erstellen Sie Checkpoints laufender Container für sofortige Migration oder Rollback.
