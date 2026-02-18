---
title: "Maschineneinrichtung"
description: "Kontext erstellen, Maschinen hinzufügen, Server provisionieren und Infrastruktur konfigurieren."
category: "Guides"
order: 3
language: de
---

# Maschineneinrichtung

Diese Seite führt Sie durch die Einrichtung Ihrer ersten Maschine: einen Kontext erstellen, einen Server registrieren, ihn provisionieren und optional die Infrastruktur für öffentlichen Zugriff konfigurieren.

## Schritt 1: Einen lokalen Kontext erstellen

Ein **Kontext** ist eine benannte Konfiguration, die Ihre SSH-Zugangsdaten, Maschinendefinitionen und Repository-Zuordnungen speichert. Betrachten Sie ihn als Projekt-Arbeitsbereich.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `--ssh-key <path>` | Ja | Pfad zu Ihrem privaten SSH-Schlüssel. Die Tilde (`~`) wird automatisch expandiert. |
| `--renet-path <path>` | Nein | Benutzerdefinierter Pfad zur renet-Binary auf entfernten Rechnern. Standardmäßig der Standard-Installationspfad. |

Dies erstellt einen lokalen Kontext namens `my-infra` und speichert ihn in `~/.rediacc/config.json`.

> Sie können mehrere Kontexte haben (z. B. `production`, `staging`, `dev`). Wechseln Sie zwischen ihnen mit dem `--context`-Flag bei jedem Befehl.

## Schritt 2: Eine Maschine hinzufügen

Registrieren Sie Ihren entfernten Server als Maschine im Kontext:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--ip <address>` | Ja | - | IP-Adresse oder Hostname des entfernten Servers. |
| `--user <username>` | Ja | - | SSH-Benutzername auf dem entfernten Server. |
| `--port <port>` | Nein | `22` | SSH-Port. |
| `--datastore <path>` | Nein | `/mnt/rediacc` | Pfad auf dem Server, an dem Rediacc verschlüsselte Repositories speichert. |

Nach dem Hinzufügen der Maschine führt rdc automatisch `ssh-keyscan` aus, um die Host-Schlüssel des Servers abzurufen. Sie können dies auch manuell ausführen:

```bash
rdc context scan-keys server-1
```

Um alle registrierten Maschinen anzuzeigen:

```bash
rdc context machines
```

## Schritt 3: Die Maschine einrichten

Provisionieren Sie den entfernten Server mit allen erforderlichen Abhängigkeiten:

```bash
rdc context setup-machine server-1
```

Dieser Befehl:
1. Lädt die renet-Binary per SFTP auf den Server hoch
2. Installiert Docker, containerd und cryptsetup (falls nicht vorhanden)
3. Erstellt den `rediacc`-Systembenutzer (UID 7111)
4. Erstellt das Datastore-Verzeichnis und bereitet es für verschlüsselte Repositories vor

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--datastore <path>` | Nein | `/mnt/rediacc` | Datastore-Verzeichnis auf dem Server. |
| `--datastore-size <size>` | Nein | `95%` | Anteil des verfügbaren Speichers, der für den Datastore reserviert wird. |
| `--debug` | Nein | `false` | Aktiviert ausführliche Ausgabe zur Fehlerbehebung. |

> Die Einrichtung muss nur einmal pro Maschine ausgeführt werden. Eine erneute Ausführung ist bei Bedarf sicher möglich.

## Host-Schlüssel-Verwaltung

Wenn sich der SSH-Host-Schlüssel eines Servers ändert (z. B. nach einer Neuinstallation), aktualisieren Sie die gespeicherten Schlüssel:

```bash
rdc context scan-keys server-1
```

Dies aktualisiert das `knownHosts`-Feld in Ihrer Konfiguration für diese Maschine.

## SSH-Konnektivität testen

Überprüfen Sie, ob Ihre Maschine erreichbar ist, bevor Sie fortfahren:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Dies testet die SSH-Verbindung und meldet:
- Verbindungsstatus
- Verwendete Authentifizierungsmethode
- SSH-Schlüssel-Konfiguration
- Known-Hosts-Eintrag

Sie können den verifizierten Host-Schlüssel mit `--save -m server-1` in Ihrer Maschinenkonfiguration speichern.

## Infrastruktur-Konfiguration

Für Maschinen, die Traffic öffentlich bereitstellen müssen, konfigurieren Sie die Infrastruktureinstellungen:

### Infrastruktur festlegen

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Beschreibung |
|--------|-------------|
| `--public-ipv4 <ip>` | Öffentliche IPv4-Adresse für externen Zugriff |
| `--public-ipv6 <ip>` | Öffentliche IPv6-Adresse für externen Zugriff |
| `--base-domain <domain>` | Basis-Domain für Anwendungen (z. B. `example.com`) |
| `--cert-email <email>` | E-Mail für Let's Encrypt TLS-Zertifikate |
| `--cf-dns-token <token>` | Cloudflare DNS API-Token für ACME DNS-01-Challenges |
| `--tcp-ports <ports>` | Kommagetrennte zusätzliche TCP-Ports zur Weiterleitung (z. B. `25,143,465,587,993`) |
| `--udp-ports <ports>` | Kommagetrennte zusätzliche UDP-Ports zur Weiterleitung (z. B. `53`) |

### Infrastruktur anzeigen

```bash
rdc context show-infra server-1
```

### Auf den Server übertragen

Generieren und verteilen Sie die Traefik-Reverse-Proxy-Konfiguration auf den Server:

```bash
rdc context push-infra server-1
```

Dies überträgt die Proxy-Konfiguration basierend auf Ihren Infrastruktureinstellungen. Traefik übernimmt die TLS-Terminierung, das Routing und die Portweiterleitung.

## Standardwerte festlegen

Legen Sie Standardwerte fest, damit Sie sie nicht bei jedem Befehl angeben müssen:

```bash
rdc context set machine server-1    # Standard-Maschine
rdc context set team my-team        # Standard-Team (Cloud-Modus, experimentell)
```

Nach dem Festlegen einer Standard-Maschine können Sie `-m server-1` bei Befehlen weglassen:

```bash
rdc repo create my-app --size 10G   # Verwendet die Standard-Maschine
```

## Mehrere Kontexte

Verwalten Sie mehrere Umgebungen mit benannten Kontexten:

```bash
# Separate Kontexte erstellen
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# Einen bestimmten Kontext verwenden
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

Alle Kontexte anzeigen:

```bash
rdc context list
```

Aktuelle Kontextdetails anzeigen:

```bash
rdc context show
```
