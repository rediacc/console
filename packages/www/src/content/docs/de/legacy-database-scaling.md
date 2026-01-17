---
title: Skalierung älterer Datenbanken
description: Skalieren Sie Legacy-Datenbanken ohne Migration, indem Sie die Datenreplikation und Abfrageverteilung in Echtzeit nutzen.
category: Use Cases
order: 3
language: de
---

> **Ihre alte Datenbank hält Sie zurück. Befreien Sie sich, ohne es zu zerstören.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Trotz der zehnfachen Skalierung der Server mit Kubernetes verbesserte sich die Leistung nur um das Zweifache. Kunden beklagten sich über langsame Abfragezeiten, steigende Kosten ohne zufriedenstellende Ergebnisse und eine gefährdete Reputation.

## Das Problem

Die Dienste des Unternehmens in der Cloud-Umgebung hatten **Schwierigkeiten, darauf zu reagieren**. Als Lösung bietet das Software-Team: 
* **Horizontale Skalierung mit Kubernetes** durchgeführt und **die Anzahl der Server um das Zehnfache erhöht** 
* Allerdings verbesserte sich die Leistung **nur 2 Mal**

**Engpasserkennung:** 
* Es wurde davon ausgegangen, dass die Ursache des Problems eine **ältere Datenbank war, die nicht skaliert werden kann** 
* Die Datenbank konnte nicht wie in modernen Architekturen verteilt arbeiten

**Dilemma:** 
* Die Migration zu einer modernen Datenbank **könnte Jahre dauern** → Es erforderte ein Umschreiben des Codes, eine Datenmigration und Testprozesse 
* Kosten und Zeitverlust waren inakzeptabel

## Krisenauswirkungen

* Kunden beschweren sich wegen **langsamer Abfragezeiten** 
* Serverkosten steigen, aber **Leistung ist nicht zufriedenstellend** 
* Das Risiko eines **Reputationsverlusts** steigt in einem wettbewerbsintensiven Markt

## Rediacc-Lösung

Systemingenieur Yüksel nutzt die Cross-Backup-Funktion von Rediacc:

![Legacy-DB-Skalierung](/img/legacy-scaling.svg)

### 1. **Datenreplikation in Echtzeit** 
* Änderungen in der Legacy-Datenbank wurden **in 10-15-Minuten-Intervallen** auf andere Server übertragen. 
* **Nur geänderte Daten** wurden synchronisiert → **Bandbreitenverbrauch um 95 % reduziert**

### 2. **Abfrageverteilung** 
* Leseabfragen wurden **auf mehrere Maschinen verteilt** 
* Schreibvorgänge wurden **in der Hauptdatenbank** gespeichert, um die Konsistenz sicherzustellen

### 3. **Kostenlose Skalierung** 
* Das Altsystem wurde **ohne Änderungen** mit zusätzlichen Servern unterstützt 
* Keine Notwendigkeit für die Anschaffung neuer Hardware → **Cloud-Server wurden stundenweise angemietet** zur Kostenoptimierung

## Ergebnis

**Leistungssteigerung:** 
* Die Abfragezeiten wurden von **55 Sekunden auf 7 Sekunden** reduziert. 
* Systemkapazität **8-fach erhöht**

**Kostenkontrolle:** 
* Einsparungen durch die Umschreibung des Altsystems → **Finanzielle Ressourcen blieben erhalten**

**Zeitgewinn:** 
* Die Lösung wurde **innerhalb von 3 Wochen** implementiert 
* Kundenbeschwerden wurden zu **99,99 % gelöst (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots)**