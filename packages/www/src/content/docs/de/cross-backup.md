---
title: Cross-Backup-Strategie
description: Schützen Sie Daten mit effizienten kontinentalübergreifenden Backups und schneller Wiederherstellung vor Katastrophen.
category: Use Cases
order: 5
language: de
---

> **Werden Ihre Daten im Katastrophenfall überleben? Mit Rediacc ist das immer der Fall.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Nach einem Kundenanruf wurde festgestellt, dass die Dienste aufgrund eines **Festplattenfehlers** nicht funktionierten. Das letzte Backup des Remote-Backup-Servers war **3 Wochen alt**, was zu einem erheblichen Datenverlust führte.

## Das Problem

Das Unternehmen wird sich der Risiken einer Datensicherung **nur auf demselben Rechner** bewusst: 
* Hardwarefehler 
* Cyberangriffe 
* Physische Katastrophen wie Krieg, Erdbeben, Feuer, Überschwemmung 
* Unzureichender Schutz vor Datenverlust

**Nach Lösung suchen:** 
* Es wurde beschlossen, 20 TB Daten auf **einem Remote-Server** zu sichern. 
* Mit herkömmlichen Methoden dauert diese Sicherung jedoch **2 Wochen** und belegt **99,99 % (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots)** der Bandbreite

## Krisenauswirkungen

Nach einem Kundenanruf: 
* Es wurde festgestellt, dass **Dienste nicht funktionieren** 
* Es wurde ein **Festplattenfehler** erkannt 
* Bei der Überprüfung des Remote-Backup-Servers wird davon ausgegangen, dass **das letzte Backup vor 3 Wochen erstellt wurde**

**Ergebnisse:** 
* Manuelle Wiederherstellungsversuche der Festplatte schlagen **fehl** 
* Aufgrund von 3 Wochen Datenverlust werden **Kundenverträge gekündigt** 
* Der **Ruf des Unternehmens ist ernsthaft geschädigt**

## Rediacc-Lösung

### 1. **Erstes Backup** 
* Die erste Übertragung von 20 TB Daten auf einen Remote-Server dauert 2 Wochen

### 2. **Stündliche Cross-Backups** 
* Stündlich wird ein vollständiges Backup erstellt, es werden jedoch **nur geänderte Daten** übertragen

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