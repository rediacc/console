---
title: Cross-Backup-Strategie
description: "Ihr Backup ist nur so sicher wie die Maschine, auf der es läuft. Rediacc repliziert Snapshots auf einer separaten Maschine – so dass ein Laufwerksausfall nicht alles mitreißt."
category: Use Cases
order: 5
language: de
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Werden Ihre Daten im Katastrophenfall überleben? Mit Rediacc ist das immer der Fall.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Diese Szenarien sind potenzielle Anwendungen, keine abgeschlossenen Fallstudien.

**Krisenszenario:** Ein Kundenanruf offenbart das Problem: **Festplattenfehler**. Das letzte Backup auf dem Remote-Backup-Server ist **3 Wochen alt**. Wochen an Daten, verloren.

## Das Problem

Backups nur auf der gleichen Maschine wie die zu schützenden Daten zu speichern, ist keine richtige Strategie. Hier ist, was dieser Fehler offenbart:
* Hardwarefehler
* Cyberangriffe
* Physische Katastrophen wie Krieg, Erdbeben, Feuer, Überschwemmung
* Unzureichender Schutz vor Datenverlust

**Nach einer Lösung suchen:**
* Man entschließt sich, 20 TB Daten auf **einen Remote-Server** zu sichern.
* Mit herkömmlichen Methoden dauert dieses Backup jedoch **2 Wochen** und belegt **99,99 % (abhängig vom Änderungsverhältnis der Gesamtdaten zwischen Snapshots)** der Bandbreite

## Krisenauswirkungen

Nach einem Kundenanruf:
* Es wird festgestellt, dass **Dienste nicht funktionieren**
* Es wird ein **Festplattenfehler** erkannt
* Bei der Überprüfung des Remote-Backup-Servers wird klar, dass **das letzte Backup vor 3 Wochen erstellt wurde**

**Ergebnisse:**
* Manuelle Wiederherstellungsversuche der Festplatte schlagen **fehl**
* Aufgrund von 3 Wochen Datenverlust werden **Kundenverträge gekündigt**
* Der **Ruf des Unternehmens ist ernsthaft geschädigt**

## Rediacc-Lösung

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **Erstes Backup**
* Die erste Übertragung von 20 TB Daten auf einen Remote-Server dauert 2 Wochen

### 2. **Stündliche Cross-Backups**
* Stündlich wird eine vollständige Backup-Abbildung erstellt, es werden jedoch **nur geänderte Daten** übertragen

### 3. **Vorbereitung auf Katastrophenszenarien**
* Daten können sogar auf **interkontinentalen** Servern gesichert werden
* Selbst wenn die Hauptmaschine abstürzt, werden Daten von vor einer Stunde **innerhalb von Minuten aktiviert**

## Ergebnis

**Zeitersparnis:**
* Die Backup-Zeit wurde von **2 Wochen auf durchschnittlich 4 Minuten** reduziert.
* Das Risiko eines Datenverlusts wurde auf **1 Stunde** reduziert.

**Kostenoptimierung:**
* Bandbreitenverbrauch um **98 %** gesunken

**Ununterbrochene Geschäftskontinuität:**
* Als der Hauptserver abstürzte, wurde das Remote-Backup in **7 Minuten** aktiviert.
