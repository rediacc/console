---
title: "Regeln von Rediacc"
description: "Wesentliche Regeln und Konventionen für die Entwicklung von Anwendungen auf der Rediacc-Plattform. Umfasst Rediaccfile, Compose, Netzwerk, Speicher, CRIU und Deployment."
category: "Guides"
order: 5
language: de
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
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
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Wurzelpfad des gemounteten Repos |
| `REDIACC_NETWORK_ID` | `6336` | Netzwerkisolations-Kennung |
| `REDIACC_REPOSITORY` | `abc123-...` | Repository-GUID |
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
- **Restart-Richtlinien (`restart: always`, `on-failure` usw.) sind sicher zu verwenden** — renet entfernt sie automatisch für CRIU-Kompatibilität. Der Router-Watchdog stellt gestoppte Container automatisch wieder her, basierend auf der in `.rediacc.json` gespeicherten ursprünglichen Richtlinie.
- **Gefährliche Einstellungen sind standardmäßig blockiert** — `privileged: true`, `pid: host`, `ipc: host` und Bind-Mounts zu System-Pfaden werden abgelehnt. Verwenden Sie `renet compose --unsafe`, um dies auf eigenes Risiko zu überschreiben.

### Umgebungsvariablen innerhalb von Containern

Renet injiziert diese automatisch in jeden Container:

| Variable | Beschreibung |
|----------|--------------|
| `SERVICE_IP` | Die dedizierte Loopback-IP dieses Containers |
| `REDIACC_NETWORK_ID` | Netzwerkisolations-ID |

### Dienstnamen und Routing

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-{tag}.{machine}.{baseDomain}` — uses the machine wildcard cert to avoid Let's Encrypt rate limits.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly — the domain belongs to the grand repo).

## Netzwerk

- **Jedes Repository erhält seinen eigenen Docker-Daemon** unter `/var/run/rediacc/docker-<networkId>.sock`.
- **Jeder Dienst erhält eine eindeutige Loopback-IP** innerhalb eines /26-Subnetzes (z.B. `127.0.24.192/26`).
- **Binden Sie an `SERVICE_IP`** — jeder Dienst erhält eine eindeutige Loopback-IP.
- **Health Checks müssen `${SERVICE_IP}` verwenden**, nicht `localhost`. Beispiel: `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **Inter-Service-Kommunikation**: Verwenden Sie Loopback-IPs oder die Umgebungsvariable `SERVICE_IP`. Docker-DNS-Namen funktionieren im Host-Modus NICHT.
- **Portkonflikte sind unmöglich** zwischen Repositories — jedes hat seinen eigenen Docker-Daemon und IP-Bereich.
- **TCP/UDP-Portweiterleitung**: Fügen Sie Labels hinzu, um Nicht-HTTP-Ports freizugeben:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Speicher

- **Alle Docker-Daten werden im verschlüsselten Repo gespeichert** — Dockers `data-root` befindet sich unter `{mount}/.rediacc/docker/data` innerhalb des LUKS-Volumes. Named Volumes, Images und Container-Layer sind alle verschlüsselt, gesichert und werden automatisch geforkt.
- **Bind Mounts zu `${REDIACC_WORKING_DIR}/...` werden der Übersichtlichkeit halber empfohlen**, aber Named Volumes funktionieren ebenfalls sicher.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (empfohlen)
    - pgdata:/var/lib/postgresql/data      # named volume (ebenfalls sicher)
  ```
- Das LUKS-Volume wird unter `/mnt/rediacc/mounts/<guid>/` gemountet.
- BTRFS-Snapshots erfassen die gesamte LUKS-Backing-Datei, einschließlich aller bind-gemounteten Daten.
- Der Datenspeicher ist eine fest dimensionierte BTRFS-Pool-Datei auf der Systemfestplatte. Verwenden Sie `rdc machine query <name> --system`, um den effektiven freien Speicher zu sehen. Erweitern Sie mit `rdc datastore resize`.

## CRIU (Live-Migration)

- **`backup push --checkpoint`** erfasst den Arbeitsspeicher laufender Prozesse + Festplattenzustand.
- **`repo up --mount --checkpoint`** stellt Container aus dem Checkpoint wieder her (kein Neustart).
- **TCP-Verbindungen werden nach der Wiederherstellung ungültig** — Anwendungen müssen `ECONNRESET` behandeln und sich neu verbinden.
- **Docker Experimental Mode** wird automatisch auf den pro-Repository-Daemons aktiviert.
- **CRIU wird installiert** während `rdc config machine setup`.
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
- Restart-Richtlinien werden automatisch von renet verwaltet (für CRIU entfernt, Watchdog übernimmt die Wiederherstellung).
- Verlassen Sie sich nicht auf Docker-DNS — verwenden Sie Loopback-IPs für die Inter-Service-Kommunikation.

## Sicherheit

- **LUKS-Verschlüsselung** ist für Standard-Repositories obligatorisch. Jedes Repo hat seinen eigenen Verschlüsselungsschlüssel.
- **Anmeldeinformationen werden in der CLI-Konfiguration gespeichert** (`~/.config/rediacc/rediacc.json`). Der Verlust der Konfiguration bedeutet den Verlust des Zugangs zu verschlüsselten Volumes.
- **Committen Sie niemals Anmeldeinformationen** in die Versionskontrolle. Verwenden Sie `env_file` und generieren Sie Secrets in `up()`.
- **Repository-Isolation**: Docker-Daemon, Netzwerk und Speicher jedes Repos sind vollständig von anderen Repos auf derselben Maschine isoliert.
- **Agenten-Isolation**: KI-Agenten arbeiten standardmäßig im fork-only-Modus. Jedes Repo hat seinen eigenen SSH-Schlüssel mit serverseitiger Sandbox-Durchsetzung (`sandbox-gateway` ForceCommand). Alle Verbindungen werden mit Landlock LSM, OverlayFS Home-Overlay und repo-eigenem TMPDIR sandboxed. Dateisystemzugriff zwischen Repos wird durch den Kernel blockiert.

## Deployment

- **`rdc repo up`** führt `up()` in allen Rediaccfiles aus.
- **`rdc repo up --mount`** öffnet zuerst das LUKS-Volume und führt dann den Lifecycle aus. Erforderlich nach `backup push` auf eine neue Maschine.
- **`rdc repo down`** führt `down()` aus und stoppt den Docker-Daemon.
- **`rdc repo down --unmount`** schließt zusätzlich das LUKS-Volume (sperrt den verschlüsselten Speicher).
- **Forks** (`rdc repo fork`) erstellen einen CoW-Klon (Copy-on-Write) mit neuer GUID und networkId. Der Fork teilt den Verschlüsselungsschlüssel des Elternteils.
- **Takeover** (`rdc repo takeover <fork> -m <machine>`) ersetzt die Daten des grand Repos durch die Daten eines Forks. Das grand Repo behält seine Identität (GUID, networkId, Domains, Autostart, Backup-Kette). Alte Produktionsdaten werden als Backup-Fork gesichert. Verwendung: Upgrade auf Fork testen, verifizieren, dann Takeover zur Produktion. Rückgängig machen mit `rdc repo takeover <backup-fork> -m <machine>`.
- **Proxy-Routen** werden ca. 3 Sekunden nach dem Deploy aktiv. Die Warnung „Proxy is not running" während `repo up` ist informativ in Ops/Dev-Umgebungen.

## Häufige Fehler

- `docker compose` statt `renet compose` verwenden — Container erhalten keine Netzwerkisolation.
- Restart-Richtlinien sind sicher — renet entfernt sie automatisch und der Watchdog übernimmt die Wiederherstellung.
- `privileged: true` verwenden — nicht nötig, renet injiziert stattdessen spezifische CRIU-Capabilities.
- Nicht an `SERVICE_IP` binden — verursacht Portkonflikte zwischen Repos.
- IPs hardcoden — verwenden Sie die Umgebungsvariable `SERVICE_IP`; IPs werden dynamisch pro networkId zugewiesen.
- `--mount` beim ersten Deploy nach `backup push` vergessen — das LUKS-Volume muss explizit geöffnet werden.
- `rdc term -c` als Workaround für fehlgeschlagene Befehle verwenden — melden Sie stattdessen Bugs.
- `repo delete` führt eine vollständige Bereinigung durch, einschließlich Loopback-IPs und systemd-Units. Führen Sie `rdc machine prune <name>` aus, um Überreste aus alten Löschvorgängen zu bereinigen.
