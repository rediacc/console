---
title: "Maschineneinrichtung"
description: "Konfiguration erstellen, Maschinen hinzufügen, Server provisionieren und Infrastruktur konfigurieren."
category: "Guides"
order: 3
language: de
sourceHash: "19a208e453f7d742"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Maschineneinrichtung

Vier Schritte bringen Ihre erste Maschine zum Laufen: eine Konfiguration erstellen, den Server registrieren, ihn provisionieren und optional die Infrastruktur für öffentlichen Traffic konfigurieren.

## Schritt 1: Konfiguration erstellen

Eine **Konfiguration** ist eine benannte Konfigurationsdatei, die Ihre SSH-Zugangsdaten, Maschinendefinitionen und Repository-Zuordnungen speichert. Betrachten Sie sie als Projekt-Arbeitsbereich.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
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
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Option | Erforderlich | Standard | Beschreibung |
|--------|-------------|----------|--------------|
| `--ip <address>` | Ja | - | IP-Adresse oder Hostname des entfernten Servers |
| `--user <username>` | Ja | - | SSH-Benutzername auf dem entfernten Server |
| `--port <port>` | Nein | `22` | SSH-Port |
| `--datastore <path>` | Nein | `/mnt/rediacc` | Pfad auf dem Server, an dem Rediacc verschlüsselte Repositories speichert |

Nach dem Hinzufügen der Maschine führt rdc automatisch `ssh-keyscan` aus, um die Host-Schlüssel des Servers abzurufen. Sie können dies auch manuell ausführen:

```bash
rdc config machine scan-keys -m server-1
```

Um alle registrierten Maschinen anzuzeigen:

```bash
rdc config machine list
```

## Schritt 3: Die Maschine einrichten

Provisionieren Sie den entfernten Server mit allen erforderlichen Abhängigkeiten:

```bash
rdc config machine setup --name server-1
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
rdc config machine scan-keys -m server-1
```

Dies aktualisiert das `knownHosts`-Feld in Ihrer Konfiguration für diese Maschine.

## SSH-Konnektivität testen

Nach dem Hinzufügen einer Maschine prüfen Sie, ob sie erreichbar ist:

```bash
rdc term connect -m server-1 -c "hostname"
```

Dies öffnet eine SSH-Verbindung zur Maschine und führt den Befehl aus. Bei Erfolg ist Ihre SSH-Konfiguration korrekt.

Für eine detailliertere Diagnose führen Sie aus:

```bash
rdc doctor
```

> **Tipp**: Um die SSH-Konnektivität zu prüfen, führen Sie `rdc term connect -m <machine> -c "hostname"` aus oder verwenden Sie direkt `ssh`.

## Infrastruktur-Konfiguration

Für Maschinen, die Traffic öffentlich bereitstellen müssen, konfigurieren Sie die Infrastruktureinstellungen:

### Infrastruktur festlegen

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Bereich | Beschreibung |
|--------|---------|-------------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address, proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address, proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | Basis-Domain für Anwendungen (z. B. `example.com`) |
| `--cert-email <email>` | Config | E-Mail für Let's Encrypt TLS-Zertifikate (maschinenübergreifend geteilt) |
| `--cf-dns-token <token>` | Config | Cloudflare DNS API-Token für ACME DNS-01-Challenges (maschinenübergreifend geteilt) |
| `--tcp-ports <ports>` | Machine | Kommagetrennte zusätzliche TCP-Ports zur Weiterleitung (z. B. `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Kommagetrennte zusätzliche UDP-Ports zur Weiterleitung (z. B. `53`) |

Machine-Optionen werden pro Maschine gespeichert. Config-Optionen (`--cert-email`, `--cf-dns-token`) gelten für alle Maschinen in der Konfiguration. Einmal setzen und sie gelten überall.

### Infrastruktur anzeigen

```bash
rdc config infra show -m server-1
```

### Auf den Server übertragen

Generieren und verteilen Sie die Traefik-Reverse-Proxy-Konfiguration auf den Server:

```bash
rdc config infra push -m server-1
```

Dieser Befehl:
1. Verteilt die renet-Binary auf die entfernte Maschine
2. Konfiguriert den Traefik-Reverse-Proxy, Router und systemd-Dienste
3. Erstellt Cloudflare-DNS-Einträge für die Maschinen-Subdomain (`server-1.example.com` und `*.server-1.example.com`), wenn `--cf-dns-token` gesetzt ist

Der DNS-Schritt ist automatisch und idempotent: er erstellt fehlende Einträge, aktualisiert Einträge mit geänderten IPs und überspringt bereits korrekte Einträge. Wenn kein Cloudflare-Token konfiguriert ist, wird DNS mit einer Warnung übersprungen. Per-Repo-Wildcard-DNS-Einträge (für automatische Routen) werden automatisch erstellt, wenn Sie `rdc repo up` ausführen.

## Cloud-Provisionierung

Anstatt VMs manuell zu erstellen, können Sie einen Cloud-Provider konfigurieren und `rdc` Maschinen automatisch mit [OpenTofu](https://opentofu.org/) provisionieren lassen.

### Voraussetzungen

Installieren Sie OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Stellen Sie sicher, dass Ihre SSH-Konfiguration einen registrierten Schlüssel bei `rdc` hat:

```bash
# Liest die Schlüsseldatei und inline ihren Inhalt unter /credentials/ssh.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Einen Cloud-Provider hinzufügen

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `--provider <source>` | Ja* | Bekannte Provider-Quelle (z. B. `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Ja* | Benutzerdefinierte OpenTofu-Provider-Quelle (für unbekannte Provider) |
| `--token <token>` | Ja | API-Token für den Cloud-Provider |
| `--region <region>` | Nein | Standard-Region für neue Maschinen |
| `--type <type>` | Nein | Standard-Instanztyp/-größe |
| `--image <image>` | Nein | Standard-Betriebssystem-Image |
| `--ssh-user <user>` | Nein | SSH-Benutzername (Standard: `root`) |

\* Entweder `--provider` oder `--source` ist erforderlich. Verwenden Sie `--provider` für bekannte Provider (eingebaute Standardwerte). Verwenden Sie `--source` mit zusätzlichen `--resource`, `--ipv4-output`, `--ssh-key-attr` Flags für benutzerdefinierte Provider.

### Eine Maschine provisionieren

```bash
rdc machine provision --name prod-2 --provider my-linode
```

Dieser einzelne Befehl:
1. Erstellt eine VM beim Cloud-Provider über OpenTofu
2. Wartet auf SSH-Konnektivität
3. Registriert die Maschine in Ihrer Konfiguration
4. Installiert renet und alle Abhängigkeiten
5. Konfiguriert Traefik-Proxy und Cloudflare DNS (erkennt automatisch die Basis-Domain von benachbarten Maschinen, oder geben Sie `--base-domain` explizit an)

| Option | Beschreibung |
|--------|--------------|
| `--provider <name>` | Name des Cloud-Providers (von `add-provider`) |
| `--region <region>` | Überschreibt die Standard-Region des Providers |
| `--type <type>` | Überschreibt den Standard-Instanztyp |
| `--image <image>` | Überschreibt das Standard-Betriebssystem-Image |
| `--base-domain <domain>` | Basis-Domain für die Infrastruktur. Wird automatisch von benachbarten Maschinen erkannt, falls nicht angegeben |
| `--no-infra` | Infrastruktur-Konfiguration (Proxy und DNS) vollständig überspringen |
| `--debug` | Zeigt detaillierte Provisionierungsausgabe |

### Eine Maschine deprovisionieren

```bash
rdc machine deprovision --name prod-2
```

Zerstört die VM über OpenTofu und entfernt sie aus Ihrer Konfiguration. Erfordert eine Bestätigung, es sei denn `--force` wird verwendet. Funktioniert nur für Maschinen, die mit `machine provision` erstellt wurden.

### Provider auflisten

```bash
rdc config provider list
```

## Standardwerte festlegen

Legen Sie Standardwerte fest, damit Sie sie nicht bei jedem Befehl angeben müssen:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Standard-Maschine
rdc config set --key team --value my-team                   # Standard-Team für den Config-Store
```

Nach dem Festlegen einer Standard-Maschine können Sie `-m server-1` bei Befehlen weglassen:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Mehrere Konfigurationen

Verwalten Sie mehrere Umgebungen mit benannten Konfigurationen:

```bash
# Separate Konfigurationen erstellen
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

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
