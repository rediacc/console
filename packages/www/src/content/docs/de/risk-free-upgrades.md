---
title: Risikofreie Upgrades
description: Testen Sie Datenbank-Upgrades ohne Risiko mithilfe von Instant Cloning und stündlichen Snapshots.
category: Use Cases
order: 4
language: de
---

> **Alles testen. Nichts riskieren. Upgraden Sie mit Zuversicht.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Während eines Datenbank-Upgrades ist ein **unerwarteter Fehler** aufgetreten, der das Zurücksetzen auf die alte Version oder den Übergang zur neuen Version verhinderte. Kunden hatten keinen Zugriff auf Systeme und mehr als 5.000 Mitarbeiter konnten nicht arbeiten.

## Das Problem

Mehmet ist ein erfahrener Systemadministrator, der große Datenbanken verwaltet. Er beschließt, **eine 100 TB große PostgreSQL-Datenbank von Version 13 auf 14 zu aktualisieren**. Sein Plan:

1. **Erstellen Sie ein Backup** → Allerdings dauert das Backup aufgrund der Datengröße **mehrere Tage** 
2. **Führen Sie das Upgrade am Wochenende durch** → Abteilungen werden am **Samstag von 01:00–05:00 Uhr** über einen Ausfall benachrichtigt.

## Krisenauswirkungen

* Während des Upgrades tritt ein **unerwarteter Fehler** auf 
* Die Datenbank **kann weder zur alten Version zurückkehren noch mit der neuen Version fortfahren** 
* Selbst externe Support-Teams können das Problem nicht lösen

**Auswirkungen:** 
* Kunden **können nicht auf Zahlungs- und Bestellsysteme zugreifen** 
* Mitarbeiter des Unternehmens (**5000+ Personen**) können nicht arbeiten 
* **Reputationsverlust** und zunehmende Beschwerden beginnen

**Vorübergehende Lösung:** 
* Das letzte Backup wird auf **einen neuen Server** geladen → **Hardwarekosten verdoppeln sich** 
* Donnerstags- und Freitagsdaten liegen **nur in der Live-Umgebung** vor, daher kommt es zu Datenverlust 
* **Es werden zwei Datenbanken mit unterschiedlichen Versionen** erstellt → Inkonsistenzen nehmen zu

## Rediacc-Lösung

Mehmet löst das Problem grundsätzlich mit Rediacc:

### 1. **Sofortiges Klonen** 
* Ein **Klon der 100-TB-Datenbank wird innerhalb von Sekunden erstellt** 
* Upgrade-Tests werden durchgeführt, **ohne das Live-System zu beeinträchtigen**

### 2. **Stündliche Schnappschüsse** 
* Während des Upgrade-Vorgangs wird ermittelt, **welcher Schritt seit wann fehlschlägt** 
* Problematische Vorgänge werden **vorab identifiziert** und korrigiert

### 3. **Nahtloses Upgrade** 
* Wenn das Upgrade fehlschlägt, ist **die Live-Umgebung nicht betroffen** 
* Wenn das Upgrade erfolgreich ist, wird die neue Live-Umgebung zum neuesten Klon

## Ergebnis

**Zeit- und Kosteneinsparungen:** 
* Die Backup-Zeit wurde von **7 Tagen auf 10 Sekunden** reduziert.

**Risikofreies Upgrade:** 
* Fehler wurden vorab in der Testumgebung erkannt → **Keine Probleme im Live-System**

**Keine Ausfallzeiten:** 
* Kunden und Mitarbeiter **spürten keine Störung**