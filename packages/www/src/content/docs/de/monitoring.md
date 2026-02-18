---
title: "Überwachung"
description: "Maschinengesundheit, Container, Dienste, Repositories und Diagnose überwachen."
category: "Guides"
order: 9
language: de
---

# Überwachung

Rediacc bietet integrierte Überwachungsbefehle, um Maschinengesundheit, laufende Container, Dienste, Repository-Status und Systemdiagnose zu inspizieren.

## Maschinengesundheit

Einen umfassenden Gesundheitsbericht für eine Maschine abrufen:

```bash
rdc machine health server-1
```

Dieser meldet:
- **System**: Laufzeit, Speicherauslastung, Festplattennutzung
- **Datastore**: Kapazität und Auslastung
- **Container**: Anzahl laufender, gesunder und ungesunder Container
- **Dienste**: Status und Neustart-Zähler
- **Speicher**: SMART-Gesundheit und Temperatur
- **Repositories**: Einbindungsstatus und Docker-Daemon-Status
- **Probleme**: Erkannte Probleme

Verwenden Sie `--output json` für maschinenlesbare Ausgabe.

## Container auflisten

Alle laufenden Container über alle Repositories auf einer Maschine anzeigen:

```bash
rdc machine containers server-1
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Container-Name |
| Status | Laufend, gestoppt usw. |
| Gesundheit | Gesund, ungesund, keine |
| CPU | CPU-Auslastung in Prozent |
| Speicher | Speicherauslastung |
| Repository | Welchem Repository der Container gehört |

Optionen:
- `--health-check` -- Aktive Gesundheitsprüfungen an Containern durchführen
- `--output json` -- Maschinenlesbare JSON-Ausgabe

## Dienste auflisten

Systemd-Dienste im Zusammenhang mit Rediacc auf einer Maschine anzeigen:

```bash
rdc machine services server-1
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Dienstname |
| Zustand | Aktiv, inaktiv, fehlgeschlagen |
| Unterzustand | Laufend, beendet usw. |
| Neustarts | Neustart-Zähler |
| Speicher | Speicherauslastung des Dienstes |
| Repository | Zugehöriges Repository |

Optionen:
- `--stability-check` -- Instabile Dienste markieren (fehlgeschlagen, >3 Neustarts, automatischer Neustart)
- `--output json` -- Maschinenlesbare JSON-Ausgabe

## Repositories auflisten

Repositories auf einer Maschine mit detaillierten Statistiken anzeigen:

```bash
rdc machine repos server-1
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Repository-Name |
| Größe | Disk-Image-Größe |
| Eingebunden | Eingebunden oder ausgehängt |
| Docker | Docker-Daemon läuft oder gestoppt |
| Container | Container-Anzahl |
| Festplattennutzung | Tatsächliche Festplattennutzung innerhalb des Repositories |
| Geändert | Letzte Änderungszeit |

Optionen:
- `--search <text>` -- Nach Name oder Einbindungspfad filtern
- `--output json` -- Maschinenlesbare JSON-Ausgabe

## Vault-Status

Einen vollständigen Überblick über eine Maschine einschließlich Bereitstellungsinformationen erhalten:

```bash
rdc machine vault-status server-1
```

Dies liefert:
- Hostname und Laufzeit
- Speicher-, Festplatten- und Datastore-Auslastung
- Gesamtzahl der Repositories, Anzahl der eingebundenen und laufenden Docker-Instanzen
- Detaillierte Informationen pro Repository

Verwenden Sie `--output json` für maschinenlesbare Ausgabe.

## Verbindung testen

SSH-Konnektivität zu einer Maschine überprüfen:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Meldet:
- Verbindungsstatus (Erfolg/Fehlgeschlagen)
- Verwendete Authentifizierungsmethode
- SSH-Schlüssel-Konfiguration
- Status der Public-Key-Bereitstellung
- Known-Hosts-Eintrag

Optionen:
- `--port <number>` -- SSH-Port (Standard: 22)
- `--save -m server-1` -- Verifizierten Host-Schlüssel in der Maschinenkonfiguration speichern

## Diagnose (doctor)

Eine umfassende Diagnoseprüfung Ihrer Rediacc-Umgebung durchführen:

```bash
rdc doctor
```

| Kategorie | Prüfungen |
|-----------|-----------|
| **Umgebung** | Node.js-Version, CLI-Version, SEA-Modus, Go-Installation, Docker-Verfügbarkeit |
| **Renet** | Binary-Standort, Version, CRIU, rsync, SEA eingebettete Assets |
| **Konfiguration** | Aktiver Kontext, Modus, Maschinen, SSH-Schlüssel |
| **Authentifizierung** | Anmeldestatus, Benutzer-E-Mail |

Jede Prüfung meldet **OK**, **Warnung** oder **Fehler**. Verwenden Sie dies als ersten Schritt bei der Fehlerbehebung jeglicher Probleme.

Exit-Codes: `0` = alles bestanden, `1` = Warnungen, `2` = Fehler.
