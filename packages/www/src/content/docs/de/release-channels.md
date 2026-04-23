---
title: "Release-Kanäle"
description: "Edge- und Stable-Release-Kanäle verstehen, ihre Unterschiede und wie die richtige Wahl getroffen wird."
category: "Concepts"
order: 2
language: de
sourceHash: "d6ff18f9265392d2"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

Rediacc veröffentlicht Updates über zwei Release-Kanäle: **Stable** und **Edge**. Jeder Kanal richtet sich an eine andere Zielgruppe und bietet unterschiedliche Kompromisse.

## Stable-Kanal

Stable ist der Standardkanal für alle Benutzer. Releases werden nach einer 7-tägigen Einlaufphase ohne gemeldete Probleme von Edge gefördert.

- Empfohlen, wenn Sie eine konservative Update-Kadenz bevorzugen und Zugang zu kostenpflichtigen Plänen möchten
- Nach 7 Testtagen auf Edge bereitgestellt
- Kritische Hotfixes können direkt verteilt werden
- Domains: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge-Kanal

Edge erhält jede Änderung unmittelbar nachdem sie in den Hauptzweig eingeführt wurde. Es ist die neueste Version der Software, die kontinuierlich bereitgestellt wird.

- Neueste Funktionen und Fixes, bei jedem Merge bereitgestellt
- Doppelte Community-Plan-Limits (siehe Tabelle unten)
- Dauerhaft kostenlos. Keine kostenpflichtigen Pläne auf Edge verfügbar.
- Separate Konten von Stable. Daten werden nicht zwischen Kanälen übertragen.
- Domains: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Vergleich

| | Stable | Edge |
|---|---|---|
| **Bereitstellungsrhythmus** | Nach 7-tägiger Einlaufphase | Bei jedem Merge in main |
| **Stabilität** | 7 Tage getestet | Neuester Code, weniger Einlaufzeit |
| **Community-Plan-Limits** | 10 GB Repos, 500 Ausstellungen/Monat, 2 Maschinen | 20 GB Repos, 1.000 Ausstellungen/Monat, 4 Maschinen |
| **Kostenpflichtige Pläne** | Verfügbar (Professional, Business, Enterprise) | Nicht verfügbar |
| **Konten** | Unabhängig | Unabhängig (von Stable getrennt) |
| **Geeignet für** | Produktion, kostenpflichtige Workloads | Tests, Evaluierung, Nebenprojekte, Early Access |

## Edge-Doppellimits

Edge-Benutzer im Community-Plan erhalten kostenlos verdoppelte Ressourcenlimits:

| Ressource | Stable Community | Edge Community |
|---|---|---|
| Repository-Größe | 10 GB | 20 GB |
| Lizenzausstellungen pro Monat | 500 | 1.000 |
| Maschinenaktivierungen | 2 | 4 |

Werden höhere Limits oder Funktionen eines kostenpflichtigen Plans benötigt, wird ein Konto im Stable-Kanal erstellt und dort aufgewertet.

## Getrennte Konten

Edge und Stable laufen auf separater Infrastruktur mit separaten Datenbanken. Ein auf Edge erstelltes Konto existiert nicht auf Stable und umgekehrt. Es gibt keinen Migrationspfad zwischen den Kanälen. Wer mit Edge beginnt und später einen kostenpflichtigen Plan möchte, muss ein neues Konto auf Stable erstellen.

## Wie Förderungen funktionieren

1. Jeder Merge in den Hauptzweig wird sofort auf Edge bereitgestellt.
2. Nach 7 Tagen ohne Probleme wird Edge automatisch auf Stable gefördert.
3. Kritische Hotfixes können gleichzeitig auf beide Kanäle verteilt werden.

Das bedeutet, Stable liegt immer höchstens 7 Tage hinter Edge. Die Einlaufphase erkennt Regressionen, bevor sie von Edge nach Stable übernommen werden.

## Welchen Kanal wählen?

**Stable wählen, wenn:**
- eine konservative Update-Kadenz mit 7-tägigem Einlauffenster bevorzugt wird
- Kostenpflichtige Pläne benötigt werden (Professional, Business, Enterprise)
- Maximale Zuverlässigkeit gegenüber neuesten Funktionen bevorzugt wird

**Edge wählen, wenn:**
- Neue Funktionen frühzeitig ausprobiert werden sollen
- Die Plattform evaluiert wird
- Großzügige kostenlose Limits für Nebenprojekte gewünscht werden
- Neuerer, weniger getesteter Code akzeptabel ist

## Installation

Befehle zur Installation von einem der beiden Kanäle, einschließlich Paketverwaltungskonfiguration und Docker-Tags, finden sich unter [Installation](/de/docs/installation).

## CLI-Kanalverwaltung

Die CLI verwendet automatisch den während der Installation oder Anmeldung konfigurierten Kanal. So wechselt man den Kanal:

```bash
rdc update --channel edge      # Zu Edge wechseln
rdc update --channel stable    # Zu Stable wechseln
```

Beim Ausführen von `rdc subscription login` und Auswahl einer Edge-Region konfiguriert die CLI automatisch den Edge-Update-Kanal. Kein manueller `--channel`-Parameter ist erforderlich.
