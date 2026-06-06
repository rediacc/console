---
title: Regeln von Rediacc
description: >-
  Wesentliche Regeln und Konventionen für die Entwicklung von Anwendungen auf
  der Rediacc-Plattform. Umfasst Rediaccfile, Compose, Netzwerk, Speicher, CRIU
  und Deployment.
category: Guides
order: 5
language: de
sourceHash: "74803e91ef07b03c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Regeln von Rediacc

Jedes Rediacc-Repository läuft in einer isolierten Umgebung mit eigenem Docker-Daemon, verschlüsseltem LUKS-Volume und dediziertem IP-Bereich. Diese Regeln stellen sicher, dass Ihre Anwendung innerhalb dieser Architektur korrekt funktioniert.

## Rediaccfile

- **Jedes Repository benötigt ein Rediaccfile**, ein Bash-Skript mit Lifecycle-Funktionen.
- **Lifecycle-Funktionen**: `up()`, `down()`. Optional: `info()`.
- `up()` startet Ihre Dienste. `down()` stoppt sie.
- `info()` liefert Statusinformationen (Container-Zustand, aktuelle Logs, Health).
- Rediaccfile wird von renet gesourced, es hat Zugriff auf Shell-Variablen, nicht nur auf Umgebungsvariablen.

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

- **Verwenden Sie `renet compose`, niemals `docker compose`**, renet injiziert Netzwerkisolation, Host-Networking, Loopback-IPs und Service-Labels.
- **Setzen Sie KEIN `network_mode`** in Ihrer Compose-Datei, renet erzwingt `network_mode: host` für alle Dienste. Jeder von Ihnen gesetzte Wert wird überschrieben.
- **Setzen Sie KEINE `rediacc.*`-Labels**, renet injiziert automatisch `rediacc.network_id`, `rediacc.service_ip` und `rediacc.service_name`.
- **`ports:`-Mappings werden ignoriert** im Host-Networking-Modus. Fügen Sie das Label `rediacc.service_port` für HTTP-Routing hinzu (Dienste ohne dieses Label erhalten keine HTTP-Routen). Verwenden Sie `rediacc.tcp_ports`/`rediacc.udp_ports`-Labels für TCP/UDP-Weiterleitung.
- **Restart-Richtlinien (`restart: always`, `on-failure` usw.) sind sicher zu verwenden**, renet entfernt sie automatisch für CRIU-Kompatibilität. Der Router-Watchdog stellt gestoppte Container automatisch wieder her, basierend auf der in `.rediacc.json` gespeicherten ursprünglichen Richtlinie.
- **Gefährliche Einstellungen sind standardmäßig blockiert**, `privileged: true`, `pid: host`, `ipc: host` und Bind-Mounts zu System-Pfaden werden abgelehnt. Verwenden Sie `renet compose --unsafe`, um dies auf eigenes Risiko zu überschreiben.

### Umgebungsvariablen innerhalb von Containern

Renet injiziert diese automatisch in jeden Container:

| Variable | Beschreibung |
|----------|--------------|
| `SERVICE_IP` | Die dedizierte Loopback-IP dieses Containers |
| `REDIACC_NETWORK_ID` | Netzwerkisolations-ID |

### Dienstnamen und Routing

- Der Compose-**Dienstname** wird zum Auto-Route-URL-Präfix.
- **Grand-Repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (z. B. `https://myapp.marketing.server-1.example.com`).
- **Fork-Repos**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (z. B. `https://myapp-fork-staging.marketing.server-1.example.com`). Der `-fork-`-Trenner verhindert URL-Kollisionen mit Grand-Repo-Dienstnamen. Die Fork-URL verwendet stets das vorhandene Wildcard-Zertifikat des Eltern-Repos, sodass kein neues Zertifikat benötigt wird.
- Für benutzerdefinierte Domains verwenden Sie Traefik-Labels (Hinweis: Benutzerdefinierte Domains sind NICHT fork-kompatibel, die Domain gehört zum Grand-Repo).

## Netzwerk

- **Jedes Repository erhält seinen eigenen Docker-Daemon** unter `/var/run/rediacc/docker-<networkId>.sock`.
- **Jeder Dienst erhält eine eindeutige Loopback-IP** innerhalb eines /26-Subnetzes (z.B. `127.0.24.192/26`).
- **Binden ist automatisch**: Dienste können an `0.0.0.0` oder `localhost` binden, der Kernel schreibt die Adresse transparent auf die dem Dienst zugewiesene Loopback-IP um. Explizites Binden an `${SERVICE_IP}` funktioniert weiterhin, ist aber nicht mehr erforderlich.
- **Health Checks können `localhost`** oder `${SERVICE_IP}` verwenden. Beispiel: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Cross-Repo-Verbindungen werden vom Kernel blockiert**: Der Kernel blockiert automatisch Verbindungen zu Loopback-IPs außerhalb des `/26`-Subnetzes des Repositorys. Ein Dienst in einem Repo kann keine Dienste in einem anderen Repo erreichen.
- **Inter-Service-Kommunikation**: Verwenden Sie **Dienstnamen** (z. B. `db`, `redis`), renet injiziert automatisch jeden Dienstnamen als Hostnamen, der auf die korrekte IP auflöst. Docker-DNS-Namen funktionieren im Host-Modus NICHT, aber Dienstnamen über `/etc/hosts` schon. Vermeiden Sie es, `${DB_IP}` oder Ähnliches in persistente Konfigurationsdateien (z. B. Verbindungszeichenfolgen in einer Datenbank) einzubetten, bei Forks wird die rohe IP mitgenommen und zeigt auf das falsche Repo. Dienstnamen werden immer korrekt pro Repo aufgelöst.
- **Portkonflikte sind unmöglich** zwischen Repositories, jedes hat seinen eigenen Docker-Daemon und IP-Bereich.
- **TCP/UDP-Portweiterleitung**: Fügen Sie Labels hinzu, um Nicht-HTTP-Ports freizugeben:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Speicher

- **Alle Docker-Daten werden im verschlüsselten Repo gespeichert**, Dockers `data-root` befindet sich unter `{mount}/.rediacc/docker/data` innerhalb des LUKS-Volumes. Named Volumes, Images und Container-Layer sind alle verschlüsselt, gesichert und werden automatisch geforkt.
- **Bind Mounts zu `${REDIACC_WORKING_DIR}/...` werden der Übersichtlichkeit halber empfohlen**, aber Named Volumes funktionieren ebenfalls sicher.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (empfohlen)
    - pgdata:/var/lib/postgresql/data      # named volume (ebenfalls sicher)
  ```
- Das LUKS-Volume wird unter `/mnt/rediacc/mounts/<guid>/` gemountet.
- BTRFS-Snapshots erfassen die gesamte LUKS-Backing-Datei, einschließlich aller bind-gemounteten Daten.
- Der Datenspeicher ist eine fest dimensionierte BTRFS-Pool-Datei auf der Systemfestplatte. Verwenden Sie `rdc machine query --name <name> --system`, um den effektiven freien Speicher zu sehen. Erweitern Sie mit `rdc datastore resize`.

## CRIU (Live-Migration)

- **Opt-in per Label**: Fügen Sie `rediacc.checkpoint=true` zu Containern hinzu, die Sie checkpointen möchten. Container ohne dieses Label (Datenbanken, Caches) starten frisch und erholen sich über eigene Mechanismen (WAL, LDF, AOF).
- **`repo down --checkpoint`** speichert den Prozesszustand vor dem Stoppen, beim nächsten `repo up` wird automatisch wiederhergestellt. **Dies ist der primäre Flow auf derselben Maschine**, verifiziert funktionsfähig.
- **`backup push --checkpoint`** erfasst den Arbeitsspeicher laufender Prozesse + Festplattenzustand für markierte Container und überträgt das Volume anschließend auf eine andere Maschine. Wiederherstellung auf der Zielmaschine über `repo up`.
- **`repo fork --checkpoint`** erfasst den Prozesszustand vor dem Forken und CoW-klont den Checkpoint zusammen mit dem Fork. ⚠️ Auf derselben Maschine schlägt das darauf folgende `repo up` auf dem Fork **derzeit fehl** mit `criu failed: type RESTORE errno 0`, solange das Eltern-Repository noch läuft. Upstream-CRIU-Bugs [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Verwenden Sie `repo down --checkpoint` für In-Place-Speichern/Wiederherstellen oder `backup push --checkpoint` für maschinenübergreifende Migration.
- **`repo up`** erkennt Checkpoint-Daten automatisch und stellt wieder her, wenn vorhanden. Verwenden Sie `--skip-checkpoint` für einen Neustart.
- **Abhängigkeitsbewusste Wiederherstellung**: Nutzt compose `depends_on`, um Datenbanken zuerst zu starten (auf healthy warten), dann CRIU-Wiederherstellung der App-Container.
- **TCP-Verbindungen werden nach der Wiederherstellung ungültig**, Anwendungen müssen `ECONNRESET` behandeln und sich neu verbinden. CRIU bewahrt aktive TCP-Verbindungszustände bei der Wiederherstellung in keinem unterstützten Flow.
- **Docker Experimental Mode** wird automatisch auf den pro-Repository-Daemons aktiviert.
- **CRIU wird installiert** während `rdc config machine setup`.
- **`/etc/criu/runc.conf`** wird standardmäßig mit `tcp-established` konfiguriert.
- **Container-Sicherheitseinstellungen werden automatisch für markierte Container injiziert**, `renet compose` fügt Folgendes zu Containern mit `rediacc.checkpoint=true` hinzu:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (Minimalsatz für CRIU auf Kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (CRIUs AppArmor-Unterstützung ist upstream noch nicht stabil)
  - `userns_mode: host` (CRIU benötigt Init-Namespace-Zugriff für `/proc/pid/map_files`)
- Container ohne Label laufen mit saubererem Sicherheitsprofil (keine zusätzlichen Capabilities).
- Das Standard-Seccomp-Profil von Docker wird beibehalten, CRIU verwendet `PTRACE_O_SUSPEND_SECCOMP` (Kernel 4.3+), um Filter während Checkpoint/Restore vorübergehend auszusetzen.
- **Setzen Sie CRIU-Capabilities NICHT manuell** in Ihrer Compose-Datei, renet übernimmt das basierend auf dem Label.
- Siehe die [Heartbeat-Vorlage](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) für eine CRIU-kompatible Referenzimplementierung.

### CRIU-kompatible Anwendungsmuster

- Behandeln Sie `ECONNRESET` bei allen persistenten Verbindungen (Datenbank-Pools, WebSockets, Message Queues).
- Verwenden Sie Connection-Pool-Bibliotheken, die automatische Neuverbindung unterstützen.
- Fügen Sie `process.on("uncaughtException")` als Sicherheitsnetz für veraltete Socket-Fehler von internen Bibliotheksobjekten hinzu.
- Restart-Richtlinien werden automatisch von renet verwaltet (für CRIU entfernt, Watchdog übernimmt die Wiederherstellung).
- Verlassen Sie sich nicht auf Docker-DNS, verwenden Sie Loopback-IPs für die Inter-Service-Kommunikation.

### Host-Sicherheitsrichtlinien nach Betriebssystem

Auf allen fünf offiziell unterstützten Server-Betriebssystemen (siehe [Anforderungen](/en/docs/requirements)) verwendet der pro-Repo-Docker-Daemon und die darin laufenden Container **Standard-Container-Labels**. `rdc config machine setup` installiert keine eigene SELinux-Richtlinie und kein eigenes AppArmor-Profil. Das ist beabsichtigt: Der Kompromiss besteht darin, dass Container-Prozesse unter der Standard-Label-Richtlinie des Host-Betriebssystems laufen, nicht unter einem Rediacc-spezifischen Isolierungsprofil. Wenn Ihr Threat-Modell obligatorische Zugriffskontrolle auf der Container-Ebene erfordert, konfigurieren Sie diese auf Host-Ebene vor dem Deployment.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor ist standardmäßig aktiviert. Container laufen unter dem Standard-Docker-Container-Profil. Die einzige Ausnahme ist CRIU (`apparmor=unconfined` für Container mit `rediacc.checkpoint=true`, wie oben beschrieben).
- **Fedora 43 / Oracle Linux 10**: SELinux läuft standardmäßig im Enforcing-Modus. Container erhalten den Standard-`container_t`-Kontext. Es ist keine zusätzliche Richtlinieninstallation erforderlich. Wenn ein Setup-Schritt mit AVC-Verweigerungen fehlschlägt, lesen Sie [Fehlerbehebung: SELinux-Verweigerungen](/en/docs/troubleshooting).
- **Debian 13**: AppArmor ist verfügbar, wird aber nicht standardmäßig auf allen Domains durchgesetzt. Container verwenden weiterhin das Docker-Container-Profil.

Fazit: `rdc` und `renet` erkennen das laufende Betriebssystem automatisch und liefern auf allen fünf unterstützten Distributionen dieselbe pro-Repo-Isolation. Kein betriebssystemspezifisches Sicherheitspositions-Flag erforderlich.

## Sicherheit

- **LUKS-Verschlüsselung** ist für Standard-Repositories obligatorisch. Jedes Repo hat seinen eigenen Verschlüsselungsschlüssel.
- **Anmeldeinformationen werden in der CLI-Konfiguration gespeichert** (`~/.config/rediacc/rediacc.json`). Der Verlust der Konfiguration bedeutet den Verlust des Zugangs zu verschlüsselten Volumes.
- **Committen Sie niemals Anmeldeinformationen** in die Versionskontrolle. Verwenden Sie `env_file` und generieren Sie Secrets in `up()`.
- **Repository-Isolation**: Docker-Daemon, Netzwerk und Speicher jedes Repos sind vollständig von anderen Repos auf derselben Maschine isoliert.
- **Agenten-Isolation**: KI-Agenten arbeiten standardmäßig im fork-only-Modus. Jedes Repo hat seinen eigenen SSH-Schlüssel mit serverseitiger Sandbox-Durchsetzung (`sandbox-gateway` ForceCommand). Alle Verbindungen werden mit Landlock LSM, OverlayFS Home-Overlay und repo-eigenem TMPDIR sandboxed. Dateisystemzugriff zwischen Repos wird durch den Kernel blockiert.
- **`sudo` ist innerhalb einer Repository-Sandbox bewusst deaktiviert.** Die Landlock-Dateisystemisolation erfordert `NoNewPrivs`, was jede Rechteerhöhung unterbindet, sodass `sudo` mit `no new privileges flag is set` fehlschlägt. Der Eigentümer-Benutzer des Repos besitzt bereits alle Berechtigungen, die für sämtliche Vorgänge innerhalb des Repo-Mounts und des Docker-Sockets erforderlich sind. Für echt privilegierte Operationen (Installation von Host-Paketen, Kernel-Tuning) führen Sie diese außerhalb der Sandbox aus oder über eine Rediaccfile-`up()`-Funktion, die vom Infrastruktur-Pfad ausgeführt wird.
- **Docker-Bridge-Networking ist auf pro-Repo-Daemons deaktiviert.** Die `daemon.json` (`FlavorRediacc`) jedes Repos enthält `"bridge": "none"` und `"iptables": false`, sodass ein einfaches `docker run <image>` einen Container nur mit Loopback-Interface und ohne ausgehende Konnektivität erzeugt. Dies ist kein Bug, sondern die Art und Weise, wie die Cross-Repo-Isolation durchgesetzt wird: Die eBPF-Kernel-Hooks, die verhindern, dass ein Repo die Loopback-IPs eines anderen Repos erreicht, greifen nur bei Containern, die im Host-Netzwerk-Namespace laufen. Verwenden Sie für Produktionsdienste `renet compose`, das automatisch `network_mode: host` injiziert. Für ad-hoc einmalige Container in einer Shell übergeben Sie `--network host` explizit. (Pro-Benutzer Hub-Daemons (`FlavorHub`, Entwicklungsumgebungen) sind die Ausnahme: Sie aktivieren `bridge="docker0"` und `iptables=true`, sodass Benutzer-Container normale ausgehende Netzwerkkonnektivität erhalten.)

## Deployment

- **`rdc repo up`** hängt das LUKS-Volume automatisch ein, falls es nicht eingehängt ist, und führt dann `up()` in allen Rediaccfiles aus.
- **`rdc repo down`** führt `down()` aus und stoppt den Docker-Daemon.
- **`rdc repo down --unmount`** schließt zusätzlich das LUKS-Volume (sperrt den verschlüsselten Speicher).
- **Forks** (`rdc repo fork`) erstellen einen CoW-Klon (Copy-on-Write) mit neuer GUID und networkId, in **konstanter Zeit, unabhängig von der Repo-Größe**. BTRFS-Reflink dupliziert die Image-Metadaten, nicht die Daten, sodass ein 100-GB-Repo in denselben wenigen Sekunden geforkt wird wie ein 1-GB-Repo. Der Fork teilt den Verschlüsselungsschlüssel des Elternteils.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) ersetzt die Daten des grand Repos durch die Daten eines Forks. Das grand Repo behält seine Identität (GUID, networkId, Domains, Autostart, Backup-Kette). Alte Produktionsdaten werden als Backup-Fork gesichert. Verwendung: Upgrade auf Fork testen, verifizieren, dann Takeover zur Produktion. Rückgängig machen mit `rdc repo takeover --name <backup-fork> -m <machine>`.
- **Proxy-Routen** werden ca. 3 Sekunden nach dem Deploy aktiv. Die Warnung „Proxy is not running" während `repo up` ist informativ in Ops/Dev-Umgebungen.
- **`rdc repo up` und `rdc repo fork --up` geben das URL-Muster** am Ende des Deploys für Dienste mit dem Label `rediacc.service_port` aus. Ersetzen Sie `{service}` durch Ihren freigegebenen Dienstnamen, um die exakte URL zu erhalten. Dienste ohne `rediacc.service_port` (Datenbanken, Worker) erhalten keine Routen und werden nicht angezeigt.

## Häufige Fehler

- `docker compose` statt `renet compose` verwenden, Container erhalten keine Netzwerkisolation.
- Restart-Richtlinien sind sicher, renet entfernt sie automatisch und der Watchdog übernimmt die Wiederherstellung.
- `privileged: true` verwenden, nicht nötig, renet injiziert stattdessen spezifische CRIU-Capabilities.
- Rohe IPs in persistenten Konfigurationsdateien hartkodieren - verwenden Sie Dienstnamen für Verbindungen, um die Fork-Isolation intakt zu halten.
- `rdc term connect -c` als Workaround für fehlgeschlagene Befehle verwenden, melden Sie stattdessen Bugs.
- `repo delete` führt eine vollständige Bereinigung durch, einschließlich Loopback-IPs und systemd-Units. Führen Sie `rdc machine prune --name <name>` aus, um Überreste aus alten Löschvorgängen zu bereinigen.
