---
title: "Nach der Installation"
description: "Autostart-Konfiguration, Kontextstruktur und Fehlerbehebung für Rediacc."
category: "Guides"
order: 3
language: de
---

# Nach der Installation

Nachdem Sie die [Schritt-für-Schritt-Anleitung](/de/docs/guide) abgeschlossen haben, behandelt diese Seite die Autostart-Konfiguration, das Verständnis der Kontext-Konfigurationsdatei und die Behebung häufiger Probleme.

## Autostart beim Hochfahren

Standardmäßig müssen Repositories nach einem Server-Neustart manuell eingebunden und gestartet werden. **Autostart** konfiguriert Repositories so, dass sie beim Hochfahren des Servers automatisch eingebunden werden, Docker gestartet und das Rediaccfile `up()` ausgeführt wird.

### Funktionsweise

Wenn Sie Autostart für ein Repository aktivieren:

1. Wird eine 256 Byte große zufällige LUKS-Schlüsseldatei generiert und dem LUKS-Slot 1 des Repositories hinzugefügt (Slot 0 bleibt die Benutzer-Passphrase).
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

## Die Kontext-Konfiguration verstehen

Die gesamte Kontext-Konfiguration wird in `~/.rediacc/config.json` gespeichert. Hier ist ein kommentiertes Beispiel, wie diese Datei nach Abschluss der Anleitung aussieht:

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

### Diagnose ausführen

Verwenden Sie den integrierten Doctor-Befehl zur Diagnose von Problemen:

```bash
rdc doctor
```

Dieser prüft Ihre Umgebung, die renet-Installation, die Kontext-Konfiguration und den Authentifizierungsstatus.
