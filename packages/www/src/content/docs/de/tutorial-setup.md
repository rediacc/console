---
title: "Maschineneinrichtung"
description: "Erstellen Sie ein Konfigurationsprofil, registrieren Sie eine Remote-Maschine, überprüfen Sie die SSH-Konnektivität und konfigurieren Sie Infrastruktureinstellungen."
category: "Tutorials"
order: 2
language: de
sourceHash: "c85a5f51a95e07bb"
---

# So richten Sie eine Maschine mit Rediacc ein

Jede Rediacc-Bereitstellung beginnt mit einem Konfigurationsprofil und einer registrierten Maschine. In diesem Tutorial erstellen Sie eine Konfiguration, registrieren einen Remote-Server, überprüfen die SSH-Konnektivität, führen Umgebungsdiagnosen durch und konfigurieren die Infrastrukturnetzwerke. Am Ende ist Ihre Maschine bereit für Repository-Bereitstellungen.

## Voraussetzungen

- Die `rdc` CLI ist installiert
- Ein Remote-Server (oder lokale VM), der über SSH erreichbar ist
- Ein privater SSH-Schlüssel, der sich beim Server authentifizieren kann

## Interaktive Aufzeichnung

![Tutorial: Maschineneinrichtung und Konfiguration](/assets/tutorials/setup-tutorial.cast)

### Schritt 1: Neue Konfiguration erstellen

Ein Konfigurationsprofil speichert Maschinendefinitionen, SSH-Anmeldedaten und Infrastruktureinstellungen. Erstellen Sie eines für diese Umgebung.

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Dies erstellt eine benannte Konfigurationsdatei unter `~/.config/rediacc/tutorial-demo.json`.

### Schritt 2: Konfigurationen anzeigen

Überprüfen Sie, ob das neue Profil in der Konfigurationsliste erscheint.

```bash
rdc config list
```

Listet alle verfügbaren Konfigurationen mit ihrem Adaptertyp (lokal oder Cloud) und der Maschinenanzahl auf.

### Schritt 3: Maschine hinzufügen

Registrieren Sie eine Maschine mit ihrer IP-Adresse und dem SSH-Benutzer. Die CLI ruft automatisch die Host-Schlüssel des Servers über `ssh-keyscan` ab und speichert sie.

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### Schritt 4: Maschinen anzeigen

Bestätigen Sie, dass die Maschine korrekt registriert wurde.

```bash
rdc config machines --config tutorial-demo
```

Zeigt alle Maschinen in der aktuellen Konfiguration mit ihren Verbindungsdetails an.

### Schritt 5: Standardmaschine festlegen

Das Festlegen einer Standardmaschine vermeidet die Wiederholung von `-m bridge-vm` bei jedem Befehl.

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### Schritt 6: Konnektivität testen

Bevor Sie etwas bereitstellen, überprüfen Sie, ob die Maschine über SSH erreichbar ist.

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Beide Befehle werden auf der Remote-Maschine ausgeführt und liefern sofort ein Ergebnis zurück. Wenn einer fehlschlägt, überprüfen Sie, ob Ihr SSH-Schlüssel korrekt ist und der Server erreichbar ist.

### Schritt 7: Diagnose ausführen

```bash
rdc doctor
```

Überprüft Ihre lokale Umgebung: CLI-Version, Docker, renet-Binary, Konfigurationsstatus, SSH-Schlüssel und Virtualisierungsvoraussetzungen. Jede Prüfung meldet **OK**, **Warning** oder **Error**.

### Schritt 8: Infrastruktur konfigurieren

Für öffentlich zugängliche Dienste benötigt die Maschine eine Netzwerkkonfiguration — ihre externe IP, eine Basisdomain und eine Zertifikats-E-Mail für TLS.

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Überprüfen Sie die Konfiguration:

```bash
rdc config show-infra bridge-vm
```

Stellen Sie die generierte Traefik-Proxy-Konfiguration mit `rdc config push-infra bridge-vm` auf dem Server bereit.

## Fehlerbehebung

**"SSH key not found" oder "Permission denied (publickey)"**
Überprüfen Sie, ob der an `config init` übergebene Schlüsselpfad existiert und mit den `authorized_keys` des Servers übereinstimmt. Prüfen Sie die Berechtigungen: Die private Schlüsseldatei muss `600` sein (`chmod 600 ~/.ssh/id_ed25519`).

**"Connection refused" bei SSH-Befehlen**
Bestätigen Sie, dass der Server läuft und die IP korrekt ist. Prüfen Sie, ob Port 22 offen ist: `nc -zv <ip> 22`. Bei einem nicht standardmäßigen Port übergeben Sie `--port` beim Hinzufügen der Maschine.

**"Host key verification failed"**
Der gespeicherte Host-Schlüssel stimmt nicht mit dem aktuellen Schlüssel des Servers überein. Dies passiert nach einem Server-Neuaufbau oder einer IP-Neuzuweisung. Führen Sie `rdc config scan-keys <machine>` aus, um den Schlüssel zu aktualisieren.

## Nächste Schritte

Sie haben ein Konfigurationsprofil erstellt, eine Maschine registriert, die Konnektivität überprüft und die Infrastrukturnetzwerke konfiguriert. Zum Bereitstellen von Anwendungen:

- [Maschineneinrichtung](/de/docs/setup) — vollständige Referenz für alle Konfigurations- und Einrichtungsbefehle
- [Tutorial: Repository-Lebenszyklus](/de/docs/tutorial-repos) — Repositories erstellen, bereitstellen und verwalten
- [Schnellstart](/de/docs/quick-start) — eine containerisierte Anwendung Ende-zu-Ende bereitstellen
