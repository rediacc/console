---
title: "Migrationsleitfaden"
description: "Bestehende Projekte in verschlüsselte Rediacc-Repositories migrieren."
category: "Guides"
order: 11
language: de
sourceHash: "5064d721c8cf32ff"
---

# Migrationsleitfaden

Migrieren Sie ein bestehendes Projekt — Dateien, Docker-Dienste, Datenbanken — von einem herkömmlichen Server oder einer lokalen Entwicklungsumgebung in ein verschlüsseltes Rediacc-Repository.

## Voraussetzungen

- `rdc` CLI installiert ([Installation](/de/docs/installation))
- Eine Maschine hinzugefügt und provisioniert ([Einrichtung](/de/docs/setup))
- Ausreichend Speicherplatz auf dem Server für Ihr Projekt (prüfen Sie mit `rdc machine status`)

## Schritt 1: Repository erstellen

Erstellen Sie ein verschlüsseltes Repository mit ausreichender Größe für Ihr Projekt. Planen Sie zusätzlichen Speicherplatz für Docker-Images und Container-Daten ein.

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **Tipp:** Sie können die Größe später mit `rdc repo resize` ändern, aber das Repository muss dafür zuerst ausgehängt werden. Es ist einfacher, gleich mit genügend Speicherplatz zu beginnen.

## Schritt 2: Dateien hochladen

Verwenden Sie `rdc sync upload`, um Ihre Projektdateien in das Repository zu übertragen.

```bash
# Vorschau der Übertragung (keine Änderungen)
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Dateien hochladen
rdc sync upload -m server-1 -r my-project --local ./my-project
```

Das Repository muss vor dem Hochladen eingehängt sein. Falls es noch nicht eingehängt ist:

```bash
rdc repo mount my-project -m server-1
```

Für nachfolgende Synchronisierungen, bei denen das Remote-Verzeichnis exakt Ihrem lokalen Verzeichnis entsprechen soll:

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> Das `--mirror`-Flag löscht Dateien auf dem Remote-Server, die lokal nicht existieren. Verwenden Sie zuerst `--dry-run` zur Überprüfung.

## Schritt 3: Dateieigentümerschaft korrigieren

Hochgeladene Dateien haben die UID Ihres lokalen Benutzers (z. B. 1000). Rediacc verwendet einen universellen Benutzer (UID 7111), damit VS Code, Terminal-Sitzungen und andere Werkzeuge einheitlichen Zugriff haben. Führen Sie den Eigentümerschaftsbefehl aus:

```bash
rdc repo ownership my-project -m server-1
```

### Docker-bewusste Ausnahmen

Wenn Docker-Container laufen (oder gelaufen sind), erkennt der Eigentümerschaftsbefehl automatisch deren beschreibbare Datenverzeichnisse und **überspringt sie**. Dies verhindert, dass Container beschädigt werden, die ihre eigenen Dateien mit anderen UIDs verwalten (z. B. MariaDB verwendet UID 999, Nextcloud verwendet UID 33).

Der Befehl gibt einen Bericht aus:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Wann ausführen

- **Nach dem Hochladen von Dateien** — um Ihre lokale UID zu 7111 zu konvertieren
- **Nach dem Starten von Containern** — wenn Docker-Volume-Verzeichnisse automatisch ausgeschlossen werden sollen. Wenn Container noch nicht gestartet wurden, gibt es keine Volumes zum Ausschließen, und alle Verzeichnisse werden geändert (was in Ordnung ist — die Container erstellen ihre Daten beim ersten Start neu)

### Erzwungener Modus

Um die Docker-Volume-Erkennung zu überspringen und alles zu ändern, einschließlich Container-Datenverzeichnissen:

```bash
rdc repo ownership my-project -m server-1 --force
```

> **Warnung:** Dies kann laufende Container beschädigen. Stoppen Sie sie vorher mit `rdc repo down`, falls nötig.

### Benutzerdefinierte UID

Um eine andere UID als die Standard-UID 7111 festzulegen:

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## Schritt 4: Rediaccfile einrichten

Erstellen Sie ein `Rediaccfile` im Stammverzeichnis Ihres Projekts. Dieses Bash-Skript definiert, wie Ihre Dienste vorbereitet, gestartet und gestoppt werden.

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

Die drei Lebenszyklus-Funktionen:

| Funktion | Zweck | Fehlerverhalten |
|----------|-------|-----------------|
| `prep()` | Images herunterladen, Migrationen ausführen, Abhängigkeiten installieren | Sofortiger Abbruch: jeder Fehler stoppt alles |
| `up()` | Dienste starten | Root-Fehler ist kritisch; Fehler in Unterverzeichnissen werden protokolliert und fortgesetzt |
| `down()` | Dienste stoppen | Best-Effort: versucht immer alles |

> **Wichtig:** Verwenden Sie `docker` direkt in Ihrem Rediaccfile — niemals `sudo docker`. Der Befehl `sudo` setzt Umgebungsvariablen zurück, wodurch `DOCKER_HOST` verloren geht und Container auf dem System-Docker-Daemon statt auf dem isolierten Daemon des Repositorys erstellt werden. Rediaccfile-Funktionen laufen bereits mit ausreichenden Berechtigungen. Siehe [Dienste](/de/docs/services#environment-variables) für Details.

Siehe [Dienste](/de/docs/services) für vollständige Details zu Rediaccfiles, Multi-Service-Layouts und Ausführungsreihenfolge.

## Schritt 5: Dienst-Netzwerk konfigurieren

Rediacc betreibt einen isolierten Docker-Daemon pro Repository. Dienste verwenden `network_mode: host` und binden an einzigartige Loopback-IPs, damit sie Standardports ohne Konflikte zwischen Repositories verwenden können.

### docker-compose.yml anpassen

**Vorher (traditionell):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Nachher (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

Wichtige Änderungen:

1. **`network_mode: host` hinzufügen** zu jedem Dienst
2. **`ports:`-Zuordnungen entfernen** (nicht nötig bei Host-Netzwerk)
3. **Dienste an `${SERVICE_IP}`-Umgebungsvariablen binden** (werden automatisch von Rediacc injiziert)
4. **Andere Dienste über ihre IP referenzieren** statt über Docker-DNS-Namen (z. B. `${POSTGRES_IP}` statt `postgres`)

Die `{SERVICE}_IP`-Variablen werden automatisch aus den Dienstnamen Ihrer Compose-Datei generiert. Die Namenskonvention: Großbuchstaben, Bindestriche durch Unterstriche ersetzen, Suffix `_IP`. Zum Beispiel wird `listmonk-app` zu `LISTMONK_APP_IP`.

Siehe [Dienst-Netzwerk](/de/docs/services#service-networking-rediaccjson) für Details zur IP-Zuweisung und `.rediacc.json`.

## Schritt 6: Dienste starten

Hängen Sie das Repository ein (falls noch nicht geschehen) und starten Sie alle Dienste:

```bash
rdc repo up my-project -m server-1 --mount
```

Dies wird:
1. Das verschlüsselte Repository einhängen
2. Den isolierten Docker-Daemon starten
3. `.rediacc.json` automatisch mit Dienst-IP-Zuweisungen generieren
4. `prep()` aus allen Rediaccfiles ausführen
5. `up()` aus allen Rediaccfiles ausführen

Überprüfen Sie, ob Ihre Container laufen:

```bash
rdc machine containers server-1
```

## Schritt 7: Autostart aktivieren (Optional)

Standardmäßig müssen Repositories nach einem Server-Neustart manuell eingehängt und gestartet werden. Aktivieren Sie den Autostart, damit Ihre Dienste automatisch starten:

```bash
rdc repo autostart enable my-project -m server-1
```

Sie werden nach der Repository-Passphrase gefragt.

> **Sicherheitshinweis:** Autostart speichert eine LUKS-Schlüsseldatei auf dem Server. Jeder mit Root-Zugriff kann das Repository ohne Passphrase einhängen. Siehe [Autostart](/de/docs/services#autostart-on-boot) für Details.

## Häufige Migrationsszenarien

### WordPress / PHP mit Datenbank

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress-Dateien (UID 33 zur Laufzeit)
├── database/data/          # MariaDB-Daten (UID 999 zur Laufzeit)
└── wp-content/uploads/     # Benutzer-Uploads
```

1. Laden Sie Ihre Projektdateien hoch
2. Starten Sie zuerst die Dienste (`rdc repo up`), damit Container ihre Datenverzeichnisse erstellen
3. Führen Sie die Eigentümerschaftskorrektur aus — MariaDB- und App-Datenverzeichnisse werden automatisch ausgeschlossen

### Node.js / Python mit Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Anwendungsquellcode
├── node_modules/           # Abhängigkeiten
└── redis-data/             # Redis-Persistenz (UID 999 zur Laufzeit)
```

1. Laden Sie Ihr Projekt hoch (erwägen Sie, `node_modules` auszuschließen und in `prep()` zu pullen)
2. Führen Sie die Eigentümerschaftskorrektur aus, nachdem Container gestartet wurden

### Benutzerdefiniertes Docker-Projekt

Für jedes Projekt mit Docker-Diensten:

1. Projektdateien hochladen
2. `docker-compose.yml` anpassen (siehe Schritt 5)
3. Ein `Rediaccfile` mit Lebenszyklus-Funktionen erstellen
4. Eigentümerschaftskorrektur ausführen
5. Dienste starten

## Fehlerbehebung

### Zugriff verweigert nach dem Hochladen

Die Dateien haben noch Ihre lokale UID. Führen Sie den Eigentümerschaftsbefehl aus:

```bash
rdc repo ownership my-project -m server-1
```

### Container startet nicht

Überprüfen Sie, ob Dienste an ihre zugewiesene IP binden, nicht an `0.0.0.0` oder `localhost`:

```bash
# Zugewiesene IPs überprüfen
rdc term server-1 my-project -c "cat .rediacc.json"

# Container-Logs überprüfen
rdc term server-1 my-project -c "docker logs <container-name>"
```

### Port-Konflikte zwischen Repositories

Jedes Repository erhält einzigartige Loopback-IPs. Wenn Port-Konflikte auftreten, überprüfen Sie, ob Ihre `docker-compose.yml` `${SERVICE_IP}` für die Bindung verwendet, statt `0.0.0.0`. Dienste, die an `0.0.0.0` gebunden sind, hören auf allen Schnittstellen und kollidieren mit anderen Repositories.

### Eigentümerschaftskorrektur beschädigt Container

Wenn Sie `rdc repo ownership --force` ausgeführt haben und ein Container nicht mehr funktioniert, wurden die Datendateien des Containers geändert. Stoppen Sie den Container, löschen Sie sein Datenverzeichnis und starten Sie ihn neu — der Container erstellt es neu:

```bash
rdc repo down my-project -m server-1
# Datenverzeichnis des Containers löschen (z. B. database/data)
rdc repo up my-project -m server-1
```
