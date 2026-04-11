---
title: "Fehlerbehebung"
description: "Lösungen für häufige Probleme mit SSH, Einrichtung, Repositories, Services und Docker."
category: "Guides"
order: 10
language: de
sourceHash: "756725b9a8fb168f"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# Fehlerbehebung

Häufige Probleme und ihre Lösungen. Im Zweifelsfall starten Sie mit `rdc doctor`, um eine umfassende Diagnoseprüfung durchzuführen.

## SSH-Verbindung schlägt fehl

- Überprüfen Sie, ob Sie sich manuell verbinden können: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Führen Sie `rdc config machine scan-keys server-1` aus, um die Host-Schlüssel zu aktualisieren
- Stellen Sie sicher, dass der SSH-Port übereinstimmt: `--port 22`
- Testen Sie mit einem einfachen Befehl: `rdc term connect -m server-1 -c "hostname"`

## Host-Schlüssel stimmt nicht überein

Wenn ein Server neu installiert wurde oder seine SSH-Schlüssel geändert wurden, sehen Sie "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

Dieser Befehl ruft frische Host-Schlüssel ab und aktualisiert Ihre Konfiguration.

## Maschineneinrichtung schlägt fehl

- Stellen Sie sicher, dass der SSH-Benutzer sudo-Zugriff ohne Passwort hat, oder konfigurieren Sie `NOPASSWD` für die erforderlichen Befehle
- Überprüfen Sie den verfügbaren Speicherplatz auf dem Server
- Führen Sie den Befehl mit `--debug` für ausführliche Ausgabe aus: `rdc config machine setup server-1 --debug`

## Repository-Erstellung schlägt fehl

- Überprüfen Sie, ob die Einrichtung abgeschlossen wurde: Das Datastore-Verzeichnis muss existieren
- Überprüfen Sie den Speicherplatz auf dem Server
- Stellen Sie sicher, dass die renet-Binary installiert ist (führen Sie die Einrichtung bei Bedarf erneut aus)

## Services starten nicht

- Überprüfen Sie die Rediaccfile-Syntax: Es muss gültiges Bash sein
- Stellen Sie sicher, dass Ihr Rediaccfile `renet compose --` verwendet (nicht `docker compose`)
- Überprüfen Sie, ob Docker-Images erreichbar sind (erwägen Sie `renet compose -- pull` in `up()`)
- Überprüfen Sie die Container-Logs über den Docker-Socket des Repositories:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Oder alle Container anzeigen:

```bash
rdc machine containers server-1
```

## Zugriff-verweigert-Fehler

- Repository-Operationen erfordern Root-Rechte auf dem Server (renet läuft über `sudo`)
- Überprüfen Sie, ob Ihr SSH-Benutzer in der `sudo`-Gruppe ist
- Stellen Sie sicher, dass das Datastore-Verzeichnis die richtigen Berechtigungen hat

## Docker-Socket-Probleme

Jedes Repository hat seinen eigenen Docker-Daemon. Wenn Sie Docker-Befehle manuell ausführen, müssen Sie den korrekten Socket angeben:

```bash
# Mit rdc term (automatisch konfiguriert):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Oder manuell mit dem Socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Ersetzen Sie `2816` durch die Netzwerk-ID Ihres Repositories (zu finden in `rediacc.json` oder `rdc repo status`).

## `docker run` hat kein Netzwerk, `apt update` schlägt fehl, `curl` hängt

Innerhalb einer Repository-Shell erhalten Sie, wenn Sie einen Container ohne `--network host` starten, einen isolierten Container, der nur über ein Loopback-Interface verfügt, kein DNS und keine ausgehende Konnektivität hat. Befehle wie `apt update`, `pip install`, `curl https://...` oder jeder Netzwerk-Abruf schlagen sofort mit DNS-Fehlern fehl.

Dies ist beabsichtigt. Rediaccs Netzwerkmodell ist **Host-Networking für jeden Dienst**, durchgesetzt von `renet compose`. Eine standardmäßige Docker-Bridge mit NAT würde die Loopback-Isolation auf Kernel-Ebene umgehen, die verhindert, dass ein Repo die Dienste eines anderen Repos erreicht, weshalb der pro-Repo-Docker-Daemon mit `"bridge": "none"` und `"iptables": false` konfiguriert ist. Es gibt keine routebare Bridge, an die sich ein einfacher `docker run`-Container anhängen könnte.

**Um in einem Ad-hoc-Container Netzwerkzugriff zu erhalten, verwenden Sie Host-Networking:**

```bash
# Inside a repository shell (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Now apt update, curl, pip install all work.
```

**Verwenden Sie für Produktionsdienste ein Rediaccfile mit `renet compose`** anstelle von reinem `docker run`. `renet compose` injiziert automatisch `network_mode: host`, Dienst-IP-Labels und Traefik-Routing-Labels. Siehe [Dienste](/de/docs/services) für Details.

## VS Code Permission Denied bei Sandbox-Dateien

Beim Verbinden mit `rdc vscode connect -m <machine> -r <repo>` sind Ihnen nach einer vorherigen VS-Code-Sitzung möglicherweise Fehler wie `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` begegnet. Dies wurde durch gemischte Dateibesitzverhältnisse innerhalb des Sandbox-Verzeichnisses verursacht, das Dateien enthielt, die sowohl von Ihrem SSH-Benutzer als auch vom internen `rediacc`-Benutzer geschrieben wurden.

Moderne Versionen von renet beheben dies wie folgt:

- Der pro-Repo-Sandbox-Workspace (`/mnt/rediacc/.interim/sandbox/<repo>/`) wird mit der Gruppe `rediacc` und gesetztem Set-Group-ID-Bit (Modus `2775`) angelegt, sodass jede darunter geschriebene Datei die korrekte Gruppe erbt.
- Innerhalb der Sandbox-Laufzeit wird umask `002` angewandt, sodass neue Dateien gruppen-schreibbar (`0664`/`0775`) erstellt werden.
- Beim Start wird ein vorhandener `.vscode-server/`-Unterbaum normalisiert, sodass veraltete Dateien aus der Zeit vor dem Fix automatisch repariert werden.

Falls weiterhin Berechtigungsfehler auftreten, starten Sie den Docker-Daemon des Repos einmal mit `sudo systemctl restart rediacc-docker-<network-id>` aus einer Shell auf der Maschine neu, damit der Normalisierungsdurchlauf erfolgt, und versuchen Sie dann erneut `rdc vscode connect`.

## Daemon startet nach einem renet-Upgrade nicht

Vor jedem Start schreibt `renet daemon start-foreground` `daemon.json` und `containerd.toml` im Konfigurationsverzeichnis des Repositories anhand der aktuellen Vorlagen neu, sodass ein Repository, dessen Konfiguration von einer älteren renet-Version erzeugt wurde, das neue Format automatisch übernimmt. Sie müssen keinen Migrationsbefehl ausführen und die systemd-Unit nicht manuell neu generieren. Starten Sie einfach den Dienst neu:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Falls die Unit weiterhin fehlschlägt, prüfen Sie das Journal auf einen konkreten Fehler:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Container auf falschem Docker-Daemon erstellt

Wenn Ihre Container auf dem Docker-Daemon des Host-Systems statt auf dem isolierten Daemon des Repositories erscheinen, ist die häufigste Ursache die Verwendung von `sudo docker` innerhalb eines Rediaccfiles.

`sudo` setzt Umgebungsvariablen zurück, sodass `DOCKER_HOST` verloren geht und Docker auf den System-Socket (`/var/run/docker.sock`) zurückfällt. Rediacc blockiert dies automatisch, aber falls Sie darauf stoßen:

- **Verwenden Sie `docker` direkt**, Rediaccfile-Funktionen laufen bereits mit ausreichenden Rechten
- Falls Sie sudo verwenden müssen, nutzen Sie `sudo -E docker`, um Umgebungsvariablen beizubehalten
- Überprüfen Sie Ihr Rediaccfile auf `sudo docker`-Befehle und entfernen Sie das `sudo`

## Terminal funktioniert nicht

Wenn `rdc term` kein Terminal-Fenster öffnen kann:

- Verwenden Sie den Inline-Modus mit `-c`, um Befehle direkt auszuführen:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Erzwingen Sie ein externes Terminal mit `--external`, wenn der Inline-Modus Probleme bereitet
- Unter Linux stellen Sie sicher, dass `gnome-terminal`, `xterm` oder ein anderer Terminal-Emulator installiert ist

## Diagnose ausführen

```bash
rdc doctor
```

Dieser Befehl überprüft Ihre Umgebung, renet-Installation, Konfiguration und Authentifizierungsstatus. Jede Prüfung meldet OK, Warning oder Error mit einer kurzen Erklärung.
