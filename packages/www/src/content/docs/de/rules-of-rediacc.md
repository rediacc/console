---
title: "Regeln von Rediacc"
description: "Wesentliche Regeln und Konventionen für die Entwicklung von Anwendungen auf der Rediacc-Plattform. Umfasst Rediaccfile, Compose, Netzwerk, Speicher, CRIU und Deployment."
category: "Guides"
order: 5
language: de
sourceHash: "c276f24c681da0ef"
---

# Regeln von Rediacc

Jedes Rediacc-Repository läuft in einer isolierten Umgebung mit eigenem Docker-Daemon, verschlüsseltem LUKS-Volume und dediziertem IP-Bereich. Diese Regeln stellen sicher, dass Ihre Anwendung innerhalb dieser Architektur korrekt funktioniert.

## Rediaccfile

- **Jedes Repository benötigt ein Rediaccfile** — ein Bash-Skript mit Lifecycle-Funktionen.
- **Lifecycle-Funktionen**: `up()`, `down()`. Optional: `info()`.
- `up()` startet Ihre Dienste. `down()` stoppt sie.
- `info()` liefert Statusinformationen (Container-Zustand, aktuelle Logs, Health).
- Rediaccfile wird von renet gesourced — es hat Zugriff auf Shell-Variablen, nicht nur auf Umgebungsvariablen.

### Verfügbare Umgebungsvariablen im Rediaccfile

| Variable | Beispiel | Beschreibung |
|----------|----------|--------------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | Wurzelpfad des gemounteten Repos |
| `REPOSITORY_NETWORK_ID` | `6336` | Netzwerkisolations-Kennung |
| `REPOSITORY_NAME` | `abc123-...` | Repository-GUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | Loopback-IP pro Dienst (Dienstname in Großbuchstaben) |

### Minimales Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Verwenden Sie `renet compose`, niemals `docker compose`** — renet injiziert Netzwerkisolation, Host-Networking, Loopback-IPs und Service-Labels.
- **Setzen Sie KEIN `network_mode`** in Ihrer Compose-Datei — renet erzwingt `network_mode: host` für alle Dienste. Jeder von Ihnen gesetzte Wert wird überschrieben.
- **Setzen Sie KEINE `rediacc.*`-Labels** — renet injiziert automatisch `rediacc.network_id`, `rediacc.service_ip` und `rediacc.service_name`.
- **`ports:`-Mappings werden ignoriert** im Host-Networking-Modus. Verwenden Sie das Label `rediacc.service_port` für Proxy-Routing zu Nicht-80-Ports.
- **Verwenden Sie NICHT `restart: always` oder `restart: unless-stopped`** — diese kollidieren mit CRIU Checkpoint/Restore. Verwenden Sie `restart: on-failure` oder lassen Sie es weg.
- **Verwenden Sie KEINE Docker Named Volumes** — diese befinden sich außerhalb des verschlüsselten Repos und werden nicht in Backups oder Forks einbezogen.

### Umgebungsvariablen innerhalb von Containern

Renet injiziert diese automatisch in jeden Container:

| Variable | Beschreibung |
|----------|--------------|
| `SERVICE_IP` | Die dedizierte Loopback-IP dieses Containers |
| `REPOSITORY_NETWORK_ID` | Netzwerkisolations-ID |

### Dienstnamen und Routing

- Der **Dienstname** in der Compose-Datei wird zum URL-Präfix der automatischen Route.
- Beispiel: Dienst `myapp` mit networkId 6336 und Basisdomain `example.com` wird zu `https://myapp-6336.example.com`.
- Für benutzerdefinierte Domains verwenden Sie Traefik-Labels (beachten Sie: benutzerdefinierte Domains sind NICHT fork-freundlich).

## Netzwerk

- **Jedes Repository erhält seinen eigenen Docker-Daemon** unter `/var/run/rediacc/docker-<networkId>.sock`.
- **Jeder Dienst erhält eine eindeutige Loopback-IP** innerhalb eines /26-Subnetzes (z.B. `127.0.24.192/26`).
- **Binden Sie an `SERVICE_IP`**, nicht an `0.0.0.0` — Host-Networking bedeutet, dass `0.0.0.0` mit anderen Repos kollidieren würde.
- **Inter-Service-Kommunikation**: Verwenden Sie Loopback-IPs oder die Umgebungsvariable `SERVICE_IP`. Docker-DNS-Namen funktionieren im Host-Modus NICHT.
- **Portkonflikte sind unmöglich** zwischen Repositories — jedes hat seinen eigenen Docker-Daemon und IP-Bereich.
- **TCP/UDP-Portweiterleitung**: Fügen Sie Labels hinzu, um Nicht-HTTP-Ports freizugeben:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Speicher

- **Alle persistenten Daten müssen `${REPOSITORY_PATH}/...` Bind Mounts verwenden.**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Docker Named Volumes befinden sich außerhalb des LUKS-Repos — sie sind **nicht verschlüsselt**, **nicht gesichert** und **nicht in Forks enthalten**.
- Das LUKS-Volume wird unter `/mnt/rediacc/mounts/<guid>/` gemountet.
- BTRFS-Snapshots erfassen die gesamte LUKS-Backing-Datei, einschließlich aller bind-gemounteten Daten.

## CRIU (Live-Migration)

- **`backup push --checkpoint`** erfasst den Arbeitsspeicher laufender Prozesse + Festplattenzustand.
- **`repo up --mount --checkpoint`** stellt Container aus dem Checkpoint wieder her (kein Neustart).
- **TCP-Verbindungen werden nach der Wiederherstellung ungültig** — Anwendungen müssen `ECONNRESET` behandeln und sich neu verbinden.
- **Docker Experimental Mode** wird automatisch auf den pro-Repository-Daemons aktiviert.
- **CRIU wird installiert** während `rdc config setup-machine`.
- **`/etc/criu/runc.conf`** wird mit `tcp-established` für TCP-Verbindungserhaltung konfiguriert.
- **Container-Sicherheitseinstellungen werden automatisch von renet injiziert** — `renet compose` fügt automatisch Folgendes zu jedem Container für CRIU-Kompatibilität hinzu:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (Minimalsatz für CRIU auf Kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (CRIUs AppArmor-Unterstützung ist upstream noch nicht stabil)
  - `userns_mode: host` (CRIU benötigt Init-Namespace-Zugriff für `/proc/pid/map_files`)
- Das Standard-Seccomp-Profil von Docker wird beibehalten — CRIU verwendet `PTRACE_O_SUSPEND_SECCOMP` (Kernel 4.3+), um Filter während Checkpoint/Restore vorübergehend auszusetzen.
- **Setzen Sie diese NICHT manuell** in Ihrer Compose-Datei — renet übernimmt das. Eigenhändiges Setzen riskiert Duplikate oder Konflikte.
- Siehe die [Heartbeat-Vorlage](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) für eine CRIU-kompatible Referenzimplementierung.

### CRIU-kompatible Anwendungsmuster

- Behandeln Sie `ECONNRESET` bei allen persistenten Verbindungen (Datenbank-Pools, WebSockets, Message Queues).
- Verwenden Sie Connection-Pool-Bibliotheken, die automatische Neuverbindung unterstützen.
- Fügen Sie `process.on("uncaughtException")` als Sicherheitsnetz für veraltete Socket-Fehler von internen Bibliotheksobjekten hinzu.
- Vermeiden Sie `restart: always` — es stört die CRIU-Wiederherstellung.
- Verlassen Sie sich nicht auf Docker-DNS — verwenden Sie Loopback-IPs für die Inter-Service-Kommunikation.

## Sicherheit

- **LUKS-Verschlüsselung** ist für Standard-Repositories obligatorisch. Jedes Repo hat seinen eigenen Verschlüsselungsschlüssel.
- **Anmeldeinformationen werden in der CLI-Konfiguration gespeichert** (`~/.config/rediacc/rediacc.json`). Der Verlust der Konfiguration bedeutet den Verlust des Zugangs zu verschlüsselten Volumes.
- **Committen Sie niemals Anmeldeinformationen** in die Versionskontrolle. Verwenden Sie `env_file` und generieren Sie Secrets in `up()`.
- **Repository-Isolation**: Docker-Daemon, Netzwerk und Speicher jedes Repos sind vollständig von anderen Repos auf derselben Maschine isoliert.
- **Agenten-Isolation**: KI-Agenten arbeiten standardmäßig im fork-only-Modus. Sie können nur Fork-Repositories ändern, nicht grand (ursprüngliche) Repositories. Befehle, die über `term_exec` oder `rdc term` mit Repository-Kontext ausgeführt werden, werden mit Landlock LSM auf Kernel-Ebene sandboxed und verhindern dateisystemweiten Zugriff zwischen Repositories.

## Deployment

- **`rdc repo up`** führt `up()` in allen Rediaccfiles aus.
- **`rdc repo up --mount`** öffnet zuerst das LUKS-Volume und führt dann den Lifecycle aus. Erforderlich nach `backup push` auf eine neue Maschine.
- **`rdc repo down`** führt `down()` aus und stoppt den Docker-Daemon.
- **`rdc repo down --unmount`** schließt zusätzlich das LUKS-Volume (sperrt den verschlüsselten Speicher).
- **Forks** (`rdc repo fork`) erstellen einen CoW-Klon (Copy-on-Write) mit neuer GUID und networkId. Der Fork teilt den Verschlüsselungsschlüssel des Elternteils.
- **Proxy-Routen** werden ca. 3 Sekunden nach dem Deploy aktiv. Die Warnung „Proxy is not running" während `repo up` ist informativ in Ops/Dev-Umgebungen.

## Häufige Fehler

- `docker compose` statt `renet compose` verwenden — Container erhalten keine Netzwerkisolation.
- `restart: always` verwenden — verhindert CRIU-Wiederherstellung und stört `repo down`.
- Docker Named Volumes verwenden — Daten sind nicht verschlüsselt, nicht gesichert, nicht geforkt.
- An `0.0.0.0` binden — verursacht Portkonflikte zwischen Repos im Host-Networking-Modus.
- IPs hardcoden — verwenden Sie die Umgebungsvariable `SERVICE_IP`; IPs werden dynamisch pro networkId zugewiesen.
- `--mount` beim ersten Deploy nach `backup push` vergessen — das LUKS-Volume muss explizit geöffnet werden.
- `rdc term -c` als Workaround für fehlgeschlagene Befehle verwenden — melden Sie stattdessen Bugs.
