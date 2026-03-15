---
title: "Backup & Netzwerk"
description: "Automatische Backup-Zeitpläne konfigurieren, Speicheranbieter verwalten, Infrastruktur-Netzwerk einrichten und Service-Ports registrieren."
category: "Tutorials"
order: 6
language: de
sourceHash: "14244f699c506ce9"
---

# So konfigurieren Sie Backups und Netzwerk mit Rediacc

Automatische Backups schützen Ihre Repositories, und Infrastruktur-Netzwerk macht Services nach außen verfügbar. In diesem Tutorial konfigurieren Sie Backup-Zeitpläne mit Speicheranbietern, richten öffentliches Netzwerk mit TLS-Zertifikaten ein, registrieren Service-Ports und überprüfen die Konfiguration. Nach Abschluss ist Ihre Maschine bereit für Produktionsbetrieb.

## Voraussetzungen

- Die `rdc` CLI installiert mit einer initialisierten Konfiguration
- Eine bereitgestellte Maschine (siehe [Tutorial: Maschine einrichten](/de/docs/tutorial-setup))

## Interaktive Aufzeichnung

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### Schritt 1: Aktuelle Speicher anzeigen

Speicheranbieter (S3, B2, Google Drive, etc.) dienen als Backup-Ziele. Prüfen Sie, welche Anbieter konfiguriert sind.

```bash
rdc config storage list
```

Listet alle konfigurierten Speicheranbieter auf, die aus rclone-Konfigurationen importiert wurden. Falls leer, fügen Sie zuerst einen Speicheranbieter hinzu — siehe [Backup & Restore](/de/docs/backup-restore).

### Schritt 2: Backup-Zeitplan konfigurieren

Richten Sie automatische Backups ein, die nach einem Cron-Zeitplan ausgeführt werden.

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
```

Sie können mehrere Ziele mit verschiedenen Zeitplänen konfigurieren:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

Dies plant tägliche Backups um 2 Uhr morgens zu `my-s3` und um 6 Uhr morgens zu `azure-backup`. Jedes Ziel erhält seinen eigenen Zeitplan. Die Zeitpläne werden in Ihrer Konfiguration gespeichert und können als systemd-Timer auf Maschinen bereitgestellt werden.

### Schritt 3: Backup-Zeitplan anzeigen

Überprüfen Sie, ob der Zeitplan angewendet wurde.

```bash
rdc config backup-strategy show
```

Zeigt die aktuelle Backup-Konfiguration: Ziel, Cron-Ausdruck und Aktivierungsstatus.

### Schritt 4: Infrastruktur konfigurieren

Für öffentlich zugängliche Services benötigt die Maschine ihre externe IP, Basisdomain und eine Zertifikats-E-Mail für Let's Encrypt TLS.

```bash
rdc config infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc generiert eine Traefik-Reverse-Proxy-Konfiguration aus diesen Einstellungen.

### Schritt 5: TCP/UDP-Ports hinzufügen

Wenn Ihre Services Nicht-HTTP-Ports benötigen (z.B. SMTP, DNS), registrieren Sie diese als Traefik-Einstiegspunkte.

```bash
rdc config infra set server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Dies erstellt Traefik-Einstiegspunkte (`tcp-25`, `udp-53`, etc.), auf die Docker-Services über Labels verweisen können.

### Schritt 6: Infrastrukturkonfiguration anzeigen

Überprüfen Sie die vollständige Infrastrukturkonfiguration.

```bash
rdc config infra show server-1
```

Zeigt öffentliche IPs, Domain, Zertifikats-E-Mail und alle registrierten Ports an.

### Schritt 7: Backup-Zeitplan deaktivieren

Um automatische Backups zu stoppen, ohne die Konfiguration zu entfernen:

```bash
rdc config backup-strategy set --disable
rdc config backup-strategy show
```

Die Konfiguration bleibt erhalten und kann später mit `--enable` wieder aktiviert werden.

## Fehlerbehebung

**"Invalid cron expression"**
Das Cron-Format ist `minute hour day month weekday`. Gängige Zeitpläne: `0 2 * * *` (täglich 2 Uhr), `0 */6 * * *` (alle 6 Stunden), `0 0 * * 0` (wöchentlich Sonntag Mitternacht).

**"Storage destination not found"**
Der Zielname muss mit einem konfigurierten Speicheranbieter übereinstimmen. Führen Sie `rdc config storage list` aus, um verfügbare Namen zu sehen. Fügen Sie neue Anbieter über die rclone-Konfiguration hinzu.

**"Infrastructure config incomplete" beim Deployment**
Alle drei Felder sind erforderlich: `--public-ipv4`, `--base-domain` und `--cert-email`. Führen Sie `rdc config infra show <machine>` aus, um fehlende Felder zu prüfen.

## Nächste Schritte

Sie haben automatische Backups konfiguriert, Infrastruktur-Netzwerk eingerichtet, Service-Ports registriert und die Konfiguration überprüft. Zur Verwaltung von Backups:

- [Backup & Restore](/de/docs/backup-restore) — Vollständige Referenz für Push-, Pull-, List- und Sync-Befehle
- [Networking](/de/docs/networking) — Docker-Labels, TLS-Zertifikate, DNS und TCP/UDP-Weiterleitung
- [Tutorial: Maschine einrichten](/de/docs/tutorial-setup) — Ersteinrichtung und Bereitstellung
