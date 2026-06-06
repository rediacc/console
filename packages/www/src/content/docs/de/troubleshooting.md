---
title: "Fehlerbehebung"
description: "Lösungen für häufig auftretende SSH-, Setup-, Repository-, Service- und Docker-Probleme."
category: "Guides"
order: 10
language: de
sourceHash: "17dc03eb0589d606"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Fehlerbehebung

Häufig auftretende Probleme und deren Lösungen. Bei Unsicherheit können Sie mit `rdc doctor` eine vollständige Diagnose ausführen.

## SSH-Verbindung fehlgeschlagen

- Überprüfen Sie, ob Sie sich manuell verbinden können: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Führen Sie `rdc config machine scan-keys -m server-1` aus, um die Host-Schlüssel zu aktualisieren
- Überprüfen Sie, dass der SSH-Port übereinstimmt: `--port 22`
- Testen Sie mit einem einfachen Befehl: `rdc term connect -m server-1 -c "hostname"`

## Host-Schlüssel stimmt nicht überein

Falls ein Server neu installiert wurde oder sich seine SSH-Schlüssel geändert haben, sehen Sie die Fehlermeldung "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

Dies ruft neue Host-Schlüssel ab und aktualisiert Ihre Konfiguration.

## Machine-Setup fehlgeschlagen

- Stellen Sie sicher, dass der SSH-Benutzer sudo-Zugriff ohne Passwort hat oder konfigurieren Sie `NOPASSWD` für die erforderlichen Befehle
- Überprüfen Sie den verfügbaren Speicherplatz auf dem Server
- Führen Sie mit `--debug` aus, um ausführliche Ausgaben zu erhalten: `rdc config machine setup --name server-1 --debug`

## Distributionsspezifische Setup-Probleme

Die fünf offiziell unterstützten Server-Betriebssysteme (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) werden mit unterschiedlichen Sicherheitsrichtlinien und Paketmanagern ausgeliefert. Die meisten Setups funktionieren "einfach so"; die folgenden Fälle behandeln diejenigen, die es nicht tun.

### SELinux-Ablehnungen (Fedora 43, Oracle Linux 10)

Beide führen SELinux im Modus "enforcing" aus. rdc setup installiert keine benutzerdefinierte SELinux-Richtlinie; der pro-Repository Docker-Daemon läuft unter dem Standard-Kontext `container_t`. Falls Setup mit AVC-Ablehnungen fehlschlägt, überprüfen Sie das Audit-Log und identifizieren Sie die Domain:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Or:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Falls eine Ablehnung auf das renet-Binary oder einen bestimmten Dateipfad verweist, ist die Lösung fast immer, ein Relabel durchzuführen (`restorecon -v /path`), anstatt SELinux zu deaktivieren. Als temporäre Lösung während der Untersuchung können Sie `sudo setenforce 0` verwenden, um das System in den Modus "permissive" zu versetzen. Aktivieren Sie es wieder mit `sudo setenforce 1`, sobald Sie bestätigt haben, dass das Relabel wirksam ist.

### AppArmor-Ablehnungen (Ubuntu 24.04, openSUSE Leap 16.0)

Beide führen AppArmor standardmäßig aus; der pro-Repository Docker-Daemon nutzt das Standardcontainer-Profil. Falls ein Container in einem Repository blockiert wird:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU ist der bekannte Fall, der AppArmor trifft. renet setzt automatisch `security_opt: apparmor=unconfined` auf Containern, die mit `rediacc.checkpoint=true` gekennzeichnet sind. Sie sollten AppArmor-Profile für nichts anderes selbst konfigurieren müssen. Siehe die CRIU-Notizen in [Rediacc-Regeln](/en/docs/rules-of-rediacc).

### Fehlersignaturen des Paketmanagers

| OS | Paketmanager | Typischer Fehler | Lösung |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare-Edge-Cache hinter Origin. Wiederholen Sie `apt-get update` nach ~15s; die Integritätsprüfung wird beim nächsten Abruf durchgeführt. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Die zwischengespeicherten RPM-Repository-Metadaten auf der Festplatte sind veraltet. Führen Sie `sudo dnf clean all && sudo dnf makecache` aus. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Führen Sie `sudo zypper refresh rediacc` einmal aus; nachfolgende Installationen sollten erfolgreich sein. |

### btrfs-Modul fehlt (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Falls `rdc config machine setup` oder `renet system check-btrfs` fehlschlägt mit:

```
Module btrfs not found
```

...läuft der Server mit dem Standard-Kernel von RHEL 10, der ohne das integrierte btrfs-Modul ausgeliefert wird. Dies ist kein Rediacc-Bug; RHEL 10 hat btrfs absichtlich entfernt. Die Lösung besteht darin, stattdessen **Oracle Linux 10** auszuführen. Oracle 10 verwendet standardmäßig den Unbreakable Enterprise Kernel (UEK), der btrfs beibehält. Siehe [Anforderungen → Warum UEK?](/en/docs/requirements) für die vollständige Geschichte.

## Repository-Erstellung fehlgeschlagen

- Überprüfen Sie, dass das Setup abgeschlossen wurde: Das Datastore-Verzeichnis muss vorhanden sein
- Überprüfen Sie den Speicherplatz auf dem Server
- Stellen Sie sicher, dass das renet-Binary installiert ist (Setup bei Bedarf erneut ausführen)

## Services können nicht gestartet werden

- Überprüfen Sie die Rediaccfile-Syntax: Sie muss gültiges Bash sein
- Stellen Sie sicher, dass Ihre Rediaccfile `renet compose --` verwendet (nicht `docker compose`)
- Überprüfen Sie, dass Docker-Images zugänglich sind (erwägen Sie `renet compose -- pull` in `up()`)
- Überprüfen Sie Container-Logs mit dem Docker-Socket des Repository:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Oder zeigen Sie alle Container an:

```bash
rdc machine containers --name server-1
```

## Fehler "Berechtigung verweigert"

- Repository-Operationen erfordern Root auf dem Server (renet läuft über `sudo`)
- Überprüfen Sie, dass Ihr SSH-Benutzer in der `sudo`-Gruppe ist
- Überprüfen Sie, dass das Datastore-Verzeichnis die richtigen Berechtigungen hat

## Docker-Socket-Probleme

Jedes Repository hat seinen eigenen Docker-Daemon. Beim manuellen Ausführen von Docker-Befehlen müssen Sie den richtigen Socket angeben:

```bash
# Using rdc term (auto-configured):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Or manually with the socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Ersetzen Sie `2816` durch die Netzwerk-ID Ihres Repository (zu finden in `rediacc.json` oder `rdc repo status`).

## `docker run` hat kein Netz, `apt update` fehlgeschlagen, `curl` hängt

In einer Repository-Shell gibt Ihnen das Ausführen eines Containers ohne `--network host` einen isolierten Container mit nur einer Loopback-Schnittstelle, ohne DNS und ohne ausgehende Konnektivität. Befehle wie `apt update`, `pip install`, `curl https://...` oder ein beliebiger Netzwerk-Abruf schlägt sofort mit DNS-Fehlern fehl.

Dies ist beabsichtigt. Rediacs Netzwerk-Modell ist **Host-Netzwerk für jeden Service**, erzwungen durch `renet compose`. Eine Standard-Docker-Bridge mit NAT würde die Isolation auf Kernel-Ebene umgehen, die verhindert, dass ein Repository die Services eines anderen Repository erreicht, daher ist der pro-Repository Docker-Daemon (`FlavorRediacc`) mit `"bridge": "none"` und `"iptables": false` konfiguriert. Es gibt keine routbare Bridge, an die ein einfacher `docker run`-Container angehängt werden könnte. (Pro-Benutzer Hub-Daemons (`FlavorHub`), die in Entwicklungsumgebungen verwendet werden, sind die Ausnahme: Sie aktivieren Bridge und iptables, damit von Benutzern ausgeführte Container ausgehende Netzwerkkonnektivität haben.)

**Um Netzwerkzugriff in einem Ad-hoc-Container zu erhalten, verwenden Sie Host-Netzwerk:**

```bash
# Inside a repository shell (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Now apt update, curl, pip install all work.
```

**Verwenden Sie für Production-Services eine Rediaccfile mit `renet compose`** anstelle von rohem `docker run`. `renet compose` injiziert automatisch `network_mode: host`, Service-IP-Labels und Traefik-Routing-Labels. Siehe [Services](/en/docs/services) für Details.

## VS Code: Berechtigung verweigert für Sandbox-Dateien

Beim Verbinden mit `rdc vscode connect -m <machine> -r <repo>` nach einer vorherigen VS-Code-Sitzung erzeugten ältere renet-Versionen Fehler wie `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied`. Die Ursache: gemischtes Dateieigentum im Sandbox-Verzeichnis, wo sowohl Ihr SSH-Benutzer als auch der interne `rediacc`-Benutzer Dateien geschrieben hatten.

Moderne Versionen von renet beheben dies durch:

- Erstellen des pro-Repository Sandbox-Arbeitsbereichs (`/mnt/rediacc/.interim/sandbox/<repo>/`) mit Gruppe `rediacc` und dem Set-Group-ID-Bit (Modus `2775`), sodass jede darunter geschriebene Datei die richtige Gruppe erbt.
- Anwendung von umask `002` in der Sandbox-Laufzeit, damit neue Dateien mit Gruppenschreibzugriff erstellt werden (`0664`/`0775`).
- Normalisierung eines bestehenden `.vscode-server/`-Teilbaums beim Start, sodass veraltete Dateien von vor der Behebung automatisch repariert werden.

Falls Sie immer noch Berechtigungsfehler sehen, starten Sie den Docker-Daemon des Repository einmal mit `sudo systemctl restart rediacc-docker-<network-id>` aus einer Shell auf der Maschine neu, damit die Normalisierung durchgeführt wird, und versuchen Sie dann `rdc vscode connect` erneut.

## Daemon kann nach einem renet-Upgrade nicht gestartet werden

Vor jedem Start schreibt `renet daemon start-foreground` `daemon.json` und `containerd.toml` im Konfigurationsverzeichnis des Repository aus den aktuellen Vorlagen neu, sodass ein Repository, dessen Konfiguration von einer älteren renet-Version generiert wurde, automatisch das neue Format übernimmt. Sie müssen keinen Migrationsbefehl ausführen und müssen die Systemd-Einheit nicht manuell neu generieren. Starten Sie einfach den Service neu:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Falls die Einheit immer noch fehlschlägt, überprüfen Sie das Journal auf einen bestimmten Fehler:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Container auf dem falschen Docker-Daemon erstellt

Falls Ihre Container auf dem Docker-Daemon des Host-Systems statt auf dem isolierten Daemon des Repository angezeigt werden, ist die häufigste Ursache die Verwendung von `sudo docker` in einer Rediaccfile.

`sudo` setzt Umgebungsvariablen zurück, also geht `DOCKER_HOST` verloren und Docker wechselt zum System-Socket (`/var/run/docker.sock`). Rediacc blockiert dies automatisch, aber falls Sie darauf stoßen:

- **Verwenden Sie `docker` direkt**, Rediaccfile-Funktionen werden bereits mit ausreichenden Berechtigungen ausgeführt
- Falls Sie sudo verwenden müssen, verwenden Sie `sudo -E docker`, um Umgebungsvariablen zu bewahren
- Überprüfen Sie Ihre Rediaccfile auf `sudo docker`-Befehle und entfernen Sie das `sudo`

## Terminal funktioniert nicht

Falls `rdc term` das Öffnen eines Terminal-Fensters fehlschlägt:

- Verwenden Sie den Inline-Modus mit `-c`, um Befehle direkt auszuführen:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Erzwingen Sie ein externes Terminal mit `--external`, falls der Inline-Modus Probleme hat
- Stellen Sie unter Linux sicher, dass Sie `gnome-terminal`, `xterm` oder ein anderes Terminal-Emulator installiert haben

## Diagnose ausführen

```bash
rdc doctor
```

Dies überprüft Ihre Umgebung, renet-Installation, Konfiguration und Authentifizierungsstatus. Jede Überprüfung meldet OK, Warnung oder Fehler mit einer kurzen Erklärung.
