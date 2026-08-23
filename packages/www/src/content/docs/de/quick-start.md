---
title: Schnellstart
description: Starten Sie einen containerisierten Dienst auf Ihrem Server in wenigen Minuten.
category: Guides
tags:
  - getting-started
  - containers
subcategory: setup
order: -1
language: de
sourceHash: "05e91da1e94dddfc"
sourceCommit: "a56b03aa5da8df74255a6bc9bc9463665c3499b6"
---

# Schnellstart

Stellen Sie eine verschlüsselte, isolierte Container-Umgebung auf Ihrem eigenen Server bereit. Keine Cloud-Konten oder SaaS-Abhängigkeiten. Alles läuft auf Hardware, die Sie kontrollieren.

---

## Einführung

### Schlüsselkonzepte

Ein Repo ist eine einzelne verschlüsselte Datei auf der Festplatte. Verschieben Sie es, sichern Sie es, forken Sie es. Es ist einfach eine Datei. Wenn es gemountet ist, wird es zu einem Ordner mit einem eigenen Docker-Daemon und Ihren App-Daten darin.

Stellen Sie sich ein Repo wie einen USB-Stick vor: Stecken Sie es in eine beliebige Maschine und die Apps und Daten werden eingehängt, bereit zur Ausführung. Wechseln Sie Maschinen oder Cloud-Anbieter ohne Neuaufbau. Plug & Run.

**Zwei Werkzeuge, zwei Rollen:**

- **rdc** = CLI auf Ihrem Laptop (TypeScript, global installiert)
- **renet** = Orchestrator auf dem Server (Go-Binary, verwaltet Daemons/Netzwerke/Isolation)
- RDC provisioniert renet automatisch während `config machine setup`. Keine manuelle Einrichtung auf dem Server erforderlich.

> [Architektur](/de/docs/architecture) erklärt das Sicherheitsmodell. [rdc vs renet](/de/docs/rdc-vs-renet) erklärt, welches Werkzeug wann verwendet wird.

### 1. CLI installieren

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Prüfen: Node, SSH-Schlüssel, renet, Docker
```

> Windows, Alpine, Arch: siehe [Installation](/de/docs/installation). Vollständige Systemanforderungen: [Anforderungen](/de/docs/requirements).

### 2. SSH-Schlüssel einrichten

rdc verbindet sich über SSH. Der Server muss Ihrem öffentlichen Schlüssel vertrauen, bevor rdc ihn erreichen kann.

```bash
# Schlüssel generieren (überspringen, falls bereits vorhanden)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Öffentlichen Schlüssel auf den Server kopieren (Passwort-Abfrage)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# rdc mitteilen, welcher Schlüssel verwendet werden soll
rdc config ssh set --key ~/.ssh/id_ed25519
```

Jeder rdc-Befehl authentifiziert sich nun mit diesem Schlüssel. Keine Passwörter.

### 3. Server hinzufügen

```bash
rdc machine add my-server --ip 192.168.1.100 --user admin
rdc machine setup my-server  # Provisioniert renet + erstellt Datenspeicher
```

**Was passiert:** SSH-Host-Schlüssel wird gescannt, renet-Binary hochgeladen, verschlüsselter Datenspeicher auf dem Server initialisiert. Bereit für Repos.

> Datenspeicher-Dimensionierung, Ceph RBD, Cloud-Anbieter: [Maschinen-Einrichtung](/de/docs/setup). SSH-Fehler: [Fehlerbehebung](/de/docs/troubleshooting).

### 4. Konfigurationsdatei

```bash
rdc config show                            # Menschenlesbare Zusammenfassung
cat ~/.config/rediacc/rediacc.json         # Rohes JSON: Maschinen, Repos, Speicher, SSH-Schlüssel
```

**Eine Datei = eine Umgebung.** Kopieren Sie sie auf einen anderen Laptop und Sie sind startklar.

---

## Mit einem Repo arbeiten

### 1. Repo erstellen

```bash
rdc repo create my-app -m my-server --size 2G  # 2 GB verschlüsseltes Repo erstellen
```

Erstellt das verschlüsselte Volume, mountet es und startet seinen Docker-Daemon. Das Repo wird in Ihrer Konfiguration registriert und ist einsatzbereit.

> Größe ändern, löschen, Validierung: [Repositories](/de/docs/repositories).

### 2. Template anwenden

```bash
rdc repo admin template list                                        # Eingebettete Templates anzeigen
rdc repo admin template apply my-app --template app-postgres  # docker-compose.yml + Rediaccfile bereitstellen
```

Templates liefern eine `docker-compose.yml`, ein `Rediaccfile` und unterstützende Dateien. Ohne ein Template (oder Ihre eigene Compose-Datei) gibt es nichts zu starten. Verwenden Sie das integrierte Template für Ihr erstes Repo. Es ist der schnellste Weg, den gesamten Workflow von Anfang bis Ende kennenzulernen.

### 3. Repo starten

```bash
rdc repo up my-app  # Rediaccfile up() ausführen
rdc repo list -m my-server                           # Alle Repos auf der Maschine anzeigen
rdc repo status my-app  # Mount-Status, Docker, Größe, Verschlüsselung
```

`repo up` mountet bei Bedarf automatisch. Keine zusätzlichen Flags erforderlich.

### 4. VS Code

```bash
rdc vscode connect my-app              # Öffnet VS Code SSH, landet in der Repo-Sandbox
```

Sie bearbeiten Dateien *innerhalb* des verschlüsselten Volumes. `docker ps` zeigt nur die Container dieses Repos. Speichern, compose up, iterieren.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Wo Sie es ausführen** | Ihr Laptop (CLI) | In der VS Code-Sandbox |
| **Was es tut** | SSH → Auto-Mount → Rediaccfile `up()` ausführen | Führt Rediaccfile `up()` direkt aus |
| **Anwendungsfall** | CI/CD, Automatisierung, Remote-Betrieb | Entwickler-Arbeitsschleife |
| **Isolation** | Orchestriert von außen | Bereits in der Sandbox |

**Demo-Ablauf:** `rdc repo admin template apply` → `rdc vscode connect my-app` → `docker-compose.yml` bearbeiten → `renet dev up` → App läuft → iterieren.

> Rediaccfile-Struktur: [Dienste](/de/docs/services). Wann welches Werkzeug verwenden: [rdc vs renet](/de/docs/rdc-vs-renet).

### 6. Isolationsmodell

- **Universeller Benutzer** (`rediacc`): Gleiche UID auf jeder Maschine. Verschieben Sie ein Repo auf einen anderen Server und Dateibesitz funktioniert einfach. Keine `chown`-Probleme.
- **Docker-Daemon pro Repo**: Jedes Repo erhält seinen eigenen isolierten Docker-Daemon. `docker ps` zeigt nur die Container DIESES Repos.
- **Landlock + OverlayFS-Sandbox**: Die VS Code-Shell ist dateisystembeschränkt. Sie können keine anderen Repos lesen. Schreibzugriffe auf `$HOME` sind pro Repo als Overlays isoliert.

> Wie Isolation funktioniert: [Architektur](/de/docs/architecture). Rediaccfile-Lebenszyklus: [Dienste](/de/docs/services).

### 7. Terminal, Sync & Tunnel

**Terminal:**
```bash
rdc term connect my-app                            # SSH in die Repo-Sandbox
rdc term connect my-app -c "curl localhost:3000"   # Befehl ausführen & beenden
rdc term connect my-server                                   # SSH zur Maschine (keine Sandbox)
```

**Dateisynchronisation (rsync über SSH):**
```bash
rdc repo sync upload my-app --local ./src                                   # Ein Verzeichnis hochladen
rdc repo sync upload my-app --local ./config.yml --remote conf              # Einzelne Datei hochladen
rdc repo sync download my-app --local ./backup                              # Verzeichnis herunterladen
rdc repo sync download my-app --remote-file conf/config.yml --local ./dl    # Einzelne Datei herunterladen
rdc repo sync download my-app --local ./backup --dry-run                    # Vorschau zuerst
```

**Tunnel (SSH-Portweiterleitung zum Container):**
```bash
rdc repo tunnel my-app -c app  # Port für den app-Container automatisch erkennen
rdc repo tunnel my-app -c db --port 5432  # Tunnel für Postgres
rdc repo tunnel my-app -c db --port 5432 --local 15432  # Benutzerdefinierter lokaler Port
```

Tunnel starten → `localhost:3000` im Browser öffnen → Live-App vom Remote-Server.

> Sync-, Terminal-, VS Code-Details: [Werkzeuge](/de/docs/tools).

---

## Fork & Backup

### 1. Grand & Fork von Repos

```bash
rdc repo fork my-app --tag experiment --up  # Sofortiger CoW-Klon + Start
rdc repo list -m my-server                                  # Zeigt: my-app (Grand) + my-app:experiment (Fork)
rdc repo delete my-app:experiment  # Fork löschen, Grand bleibt unberührt
```

**Sofortiger Klon ohne Kopieraufwand.** CoW (Copy-on-Write). Mikrosekunden, keine Daten kopiert. Blöcke werden geteilt, bis eine Seite schreibt.

**Anwendungsfälle:**
- **AI / ML:** Produktionsdatensatz forken, Experiment durchführen, verwerfen oder übernehmen
- **DevOps:** Fork → Migration testen → löschen wenn fehlgeschlagen, übernehmen wenn erfolgreich
- **Backup:** Fork = sofortiger Snapshot, extern sichern

> Fork-Lebenszyklus, maschinenübergreifende Forks: [Repositories](/de/docs/repositories).

### 2. Auf eine andere Maschine pushen

```bash
# Repo auf eine andere Maschine pushen
rdc repo push my-app --to backup-server

# Pushen und automatisch auf dem Ziel bereitstellen
rdc backup restore my-app --as my-app -m backup-server --up

# Pushen mit CRIU-Checkpoint (Live-Migration, Speicherzustand bleibt erhalten)
rdc repo push my-app --to new-server --checkpoint

# Auf eine neue Maschine pushen (automatische Provisionierung über Cloud-Anbieter)
rdc repo push my-app --to new-server --provision linode
```

### 3. Im Chunk-Store sichern

```bash
# Einen Snapshot zu einem bestimmten Zeitpunkt erstellen
rdc backup snapshot my-app

# Vorhandene Snapshots anzeigen
rdc backup manifests my-app

# Gespeicherte Bytes gegen Ihr Kontingent prüfen
rdc backup usage
```

Snapshots werden in den Chunk-Store hochgeladen, wofür ein Account-Server und ein lizenziertes Repository nötig sind. Es werden nur geänderte Daten gespeichert, sodass ein zweiter Snapshot desselben Repositorys nur die Differenz statt des gesamten Images kostet.

Das Pushen eines Repositorys in Cloud-Speicher mit `--to <storage>` ist eingestellt und wird jetzt zurückgewiesen. Um ein vor dieser Änderung geschriebenes Archiv zu lesen, funktioniert `rdc storage browse` weiterhin und benötigt `rclone` in Ihrem PATH.

### 4. Von Remote abrufen

```bash
# Repo von einer Cloud-Maschine auf Ihren lokalen Server abrufen
rdc repo pull my-app@my-local-server --from cloud-server

# Abrufen und sofort starten
rdc repo pull my-app@my-local-server --from cloud-server --up

# Stattdessen einen bestimmten Zeitpunkt aus dem Chunk-Store wiederherstellen
rdc backup restore my-app --at <snapshot> --as my-app --up
```

**Warum Pull?** Ihre lokale Maschine ist hinter NAT. Die Cloud kann nicht zu Ihnen pushen. Aber Sie können die Cloud erreichen. Pull bringt das Repo nach Hause.

**Kompletter Zyklus:** Auf Dev erstellen → in die Cloud pushen → auf Produktion pullen → `--up`. Ein Repo, jede Maschine, jede Cloud.

> Planung, automatisierte Backups, Wiederherstellung: [Backup & Wiederherstellung](/de/docs/backup-restore).

---

## Proxy & SSL

### 1. Infrastruktur-Konfiguration

```bash
rdc machine infra set my-server  # Konfigurieren: Basis-Domain, öffentliche IPs, Port-Bereiche
rdc machine infra show my-server  # Konfiguration überprüfen
rdc machine infra push my-server  # Proxy-Konfiguration auf Remote übertragen
```

**Wie Routing funktioniert:**
- Traefik erkennt Container automatisch über `rediacc.service_name`- und `rediacc.service_port`-Labels
- Routen: `{service}-{networkId}.{baseDomain}` → Container IP:Port
- SSL: Let's Encrypt über Cloudflare DNS-01-Challenge (automatische Verlängerung, Wildcard-Zertifikate)

### 2. Proxy-Template

```bash
rdc repo admin template apply infra --template proxy  # Proxy in ein Repo bereitstellen
rdc repo up infra  # Traefik starten
```

Traefik leitet nun externen Datenverkehr an alle Repos auf dieser Maschine weiter. Jeder Container erhält automatisch einen HTTPS-Endpunkt.

```bash
# Navigieren zu https://my-app.example.com → wird zum Container geroutet
# TCP/UDP-Weiterleitung für Datenbanken:
#   rediacc.tcp_ports=3306,5432 → automatisch zugewiesene externe Ports
```

> Routing-Regeln, DNS, TLS-Konfiguration: [Netzwerk](/de/docs/networking).

---

## Nächste Schritte

- **[Migrationsleitfaden](/de/docs/migration)** - Bestehende Projekte in Rediacc-Repositories überführen
- **[Monitoring](/de/docs/monitoring)** - Maschinen-Gesundheit, Container, Dienste, Diagnose
- **[CLI-Referenz](/de/docs/cli-application)** - Vollständige Befehlsreferenz
- **[Spickzettel](/de/docs/rdc-cheat-sheet)** - Schnelle Befehlsübersicht
- **[Fehlerbehebung](/de/docs/troubleshooting)** - Lösungen für häufige Probleme
- **[Rules of Rediacc](/de/docs/rules-of-rediacc)** - Rediaccfile Best Practices und Bereitstellungs-Checkliste
