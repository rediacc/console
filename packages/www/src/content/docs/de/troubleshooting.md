---
title: "Fehlerbehebung"
description: "Lösungen für häufige Probleme mit SSH, Einrichtung, Repositories, Services und Docker."
category: "Guides"
order: 10
language: de
---

# Fehlerbehebung

Häufige Probleme und ihre Lösungen. Im Zweifelsfall starten Sie mit `rdc doctor`, um eine umfassende Diagnoseprüfung durchzuführen.

## SSH-Verbindung schlägt fehl

- Überprüfen Sie, ob Sie sich manuell verbinden können: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Führen Sie `rdc context scan-keys server-1` aus, um die Host-Schlüssel zu aktualisieren
- Stellen Sie sicher, dass der SSH-Port übereinstimmt: `--port 22`
- Testen Sie die Konnektivität: `rdc machine test-connection --ip 203.0.113.50 --user deploy`

## Host-Schlüssel stimmt nicht überein

Wenn ein Server neu installiert wurde oder seine SSH-Schlüssel geändert wurden, sehen Sie "host key verification failed":

```bash
rdc context scan-keys server-1
```

Dieser Befehl ruft frische Host-Schlüssel ab und aktualisiert Ihre Konfiguration.

## Maschineneinrichtung schlägt fehl

- Stellen Sie sicher, dass der SSH-Benutzer sudo-Zugriff ohne Passwort hat, oder konfigurieren Sie `NOPASSWD` für die erforderlichen Befehle
- Überprüfen Sie den verfügbaren Speicherplatz auf dem Server
- Führen Sie den Befehl mit `--debug` für ausführliche Ausgabe aus: `rdc context setup-machine server-1 --debug`

## Repository-Erstellung schlägt fehl

- Überprüfen Sie, ob die Einrichtung abgeschlossen wurde: Das Datastore-Verzeichnis muss existieren
- Überprüfen Sie den Speicherplatz auf dem Server
- Stellen Sie sicher, dass die renet-Binary installiert ist (führen Sie die Einrichtung bei Bedarf erneut aus)

## Services starten nicht

- Überprüfen Sie die Rediaccfile-Syntax: Es muss gültiges Bash sein
- Stellen Sie sicher, dass `docker compose`-Dateien `network_mode: host` verwenden
- Überprüfen Sie, ob Docker-Images erreichbar sind (erwägen Sie `docker compose pull` in `prep()`)
- Überprüfen Sie die Container-Logs über den Docker-Socket des Repositories:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
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
rdc term server-1 my-app -c "docker ps"

# Oder manuell mit dem Socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Ersetzen Sie `2816` durch die Netzwerk-ID Ihres Repositories (zu finden in `config.json` oder `rdc repo status`).

## Container auf falschem Docker-Daemon erstellt

Wenn Ihre Container auf dem Docker-Daemon des Host-Systems statt auf dem isolierten Daemon des Repositories erscheinen, ist die häufigste Ursache die Verwendung von `sudo docker` innerhalb eines Rediaccfiles.

`sudo` setzt Umgebungsvariablen zurück, sodass `DOCKER_HOST` verloren geht und Docker auf den System-Socket (`/var/run/docker.sock`) zurückfällt. Rediacc blockiert dies automatisch, aber falls Sie darauf stoßen:

- **Verwenden Sie `docker` direkt** — Rediaccfile-Funktionen laufen bereits mit ausreichenden Rechten
- Falls Sie sudo verwenden müssen, nutzen Sie `sudo -E docker`, um Umgebungsvariablen beizubehalten
- Überprüfen Sie Ihr Rediaccfile auf `sudo docker`-Befehle und entfernen Sie das `sudo`

## Terminal funktioniert nicht

Wenn `rdc term` kein Terminal-Fenster öffnen kann:

- Verwenden Sie den Inline-Modus mit `-c`, um Befehle direkt auszuführen:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- Erzwingen Sie ein externes Terminal mit `--external`, wenn der Inline-Modus Probleme bereitet
- Unter Linux stellen Sie sicher, dass `gnome-terminal`, `xterm` oder ein anderer Terminal-Emulator installiert ist

## Diagnose ausführen

```bash
rdc doctor
```

Dieser Befehl überprüft Ihre Umgebung, renet-Installation, Kontextkonfiguration und Authentifizierungsstatus. Jede Prüfung meldet OK, Warning oder Error mit einer kurzen Erklärung.
