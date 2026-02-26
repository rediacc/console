---
title: "Maschineneinrichtung"
description: "Konfiguration erstellen, Maschinen hinzufügen, Server provisionieren und Infrastruktur konfigurieren."
category: "Guides"
order: 3
language: de
sourceHash: "0c725f9eb65e6c0f"
---

# Maschineneinrichtung

Diese Seite führt Sie durch die Einrichtung Ihrer ersten Maschine: eine Konfiguration erstellen, einen Server registrieren, ihn provisionieren und optional die Infrastruktur für öffentlichen Zugriff konfigurieren.

## Schritt 1: Konfiguration erstellen

Eine **Konfiguration** ist eine benannte Konfigurationsdatei, die Ihre SSH-Zugangsdaten, Maschinendefinitionen und Repository-Zuordnungen speichert. Betrachten Sie sie als Projekt-Arbeitsbereich.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `--ssh-key <path>` | Ja | Pfad zu Ihrem privaten SSH-Schlüssel. Die Tilde (`~`) wird automatisch expandiert. |
| `--renet-path <path>` | Nein | Benutzerdefinierter Pfad zur renet-Binary auf entfernten Rechnern. Standardmäßig der Standard-Installationspfad. |

Dies erstellt eine Konfiguration namens `my-infra` und speichert sie in `~/.config/rediacc/my-infra.json`. Die Standardkonfiguration (wenn kein Name angegeben wird) wird als `~/.config/rediacc/rediacc.json` gespeichert.

> Sie können mehrere Konfigurationen haben (z. B. `production`, `staging`, `dev`). Wechseln Sie zwischen ihnen mit dem `--config`-Flag bei jedem Befehl.

## Schritt 2: Eine Maschine hinzufügen

Registrieren Sie Ihren entfernten Server als Maschine in der Konfiguration:

```bash
rdc config add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--ip <address>` | Ja | - | IP-Adresse oder Hostname des entfernten Servers |
| `--user <username>` | Ja | - | SSH-Benutzername auf dem entfernten Server |
| `--port <port>` | Nein | `22` | SSH-Port |
| `--datastore <path>` | Nein | `/mnt/rediacc` | Pfad auf dem Server, an dem Rediacc verschlüsselte Repositories speichert |

Nach dem Hinzufügen der Maschine führt rdc automatisch `ssh-keyscan` aus, um die Host-Schlüssel des Servers abzurufen. Sie können dies auch manuell ausführen:

```bash
rdc config scan-keys server-1
```

Um alle registrierten Maschinen anzuzeigen:

```bash
rdc config machines
```

## Schritt 3: Die Maschine einrichten

Provisionieren Sie den entfernten Server mit allen erforderlichen Abhängigkeiten:

```bash
rdc config setup-machine server-1
```

Dieser Befehl:
1. Lädt die renet-Binary per SFTP auf den Server hoch
2. Installiert Docker, containerd und cryptsetup (falls nicht vorhanden)
3. Erstellt den `rediacc`-Systembenutzer (UID 7111)
4. Erstellt das Datastore-Verzeichnis und bereitet es für verschlüsselte Repositories vor

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--datastore <path>` | Nein | `/mnt/rediacc` | Datastore-Verzeichnis auf dem Server |
| `--datastore-size <size>` | Nein | `95%` | Anteil des verfügbaren Speichers, der für den Datastore reserviert wird |
| `--debug` | Nein | `false` | Aktiviert ausführliche Ausgabe zur Fehlerbehebung |

> Die Einrichtung muss nur einmal pro Maschine ausgeführt werden. Eine erneute Ausführung ist bei Bedarf sicher möglich.

## Host-Schlüssel-Verwaltung

Wenn sich der SSH-Host-Schlüssel eines Servers ändert (z. B. nach einer Neuinstallation), aktualisieren Sie die gespeicherten Schlüssel:

```bash
rdc config scan-keys server-1
```

Dies aktualisiert das `knownHosts`-Feld in Ihrer Konfiguration für diese Maschine.

## SSH-Konnektivität testen

Nach dem Hinzufügen einer Maschine prüfen Sie, ob sie erreichbar ist:

```bash
rdc term server-1 -c "hostname"
```

Dies öffnet eine SSH-Verbindung zur Maschine und führt den Befehl aus. Bei Erfolg ist Ihre SSH-Konfiguration korrekt.

Für eine detailliertere Diagnose führen Sie aus:

```bash
rdc doctor
```

> **Nur Cloud-Adapter**: Der Befehl `rdc machine test-connection` liefert detaillierte SSH-Diagnosen, erfordert aber den Cloud-Adapter. Für den lokalen Adapter verwenden Sie `rdc term` oder direkt `ssh`.

## Infrastruktur-Konfiguration

Für Maschinen, die Traffic öffentlich bereitstellen müssen, konfigurieren Sie die Infrastruktureinstellungen:

### Infrastruktur festlegen

```bash
rdc config set-infra server-1 \
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
rdc config show-infra server-1
```

### Auf den Server übertragen

Generieren und verteilen Sie die Traefik-Reverse-Proxy-Konfiguration auf den Server:

```bash
rdc config push-infra server-1
```

Dies überträgt die Proxy-Konfiguration basierend auf Ihren Infrastruktureinstellungen. Traefik übernimmt die TLS-Terminierung, das Routing und die Portweiterleitung.

## Standardwerte festlegen

Legen Sie Standardwerte fest, damit Sie sie nicht bei jedem Befehl angeben müssen:

```bash
rdc config set machine server-1    # Standard-Maschine
rdc config set team my-team        # Standard-Team (Cloud-Adapter, experimentell)
```

Nach dem Festlegen einer Standard-Maschine können Sie `-m server-1` bei Befehlen weglassen:

```bash
rdc repo create my-app --size 10G   # Verwendet die Standard-Maschine
```

## Mehrere Konfigurationen

Verwalten Sie mehrere Umgebungen mit benannten Konfigurationen:

```bash
# Separate Konfigurationen erstellen
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# Eine bestimmte Konfiguration verwenden
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Alle Konfigurationen anzeigen:

```bash
rdc config list
```

Aktuelle Konfigurationsdetails anzeigen:

```bash
rdc config show
```
