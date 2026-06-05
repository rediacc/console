---
title: Risikofreie Upgrades
description: >-
  Testen Sie Datenbank-Upgrades ohne Risiko mithilfe von Instant Cloning und
  stündlichen Snapshots.
category: Use Cases
order: 4
language: de
sourceHash: "242617b8bede9535"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Alles testen. Nichts riskieren. Upgraden Sie mit Zuversicht.**

Kurzer Hinweis: Rediacc hat derzeit keine produktiven Kunden. Dies ist ein Anwendungsbeispiel, das zeigt, wie die Architektur dieses Szenario in der Praxis bewältigt, keine Fallstudie einer echten Bereitstellung.

**Krisenszenario:** Während eines Datenbank-Upgrades tritt ein **unerwarteter Fehler** auf, der sowohl das Zurücksetzen auf die alte Version als auch den Übergang zur neuen Version verhindert. Kunden können nicht auf Systeme zugreifen, und 5000+ Mitarbeiter können nicht arbeiten. Die einzige Lösung ist eine vollständige Systemwiederherstellung, die Stunden Engineerzeit kostet, während das Geschäft offline ist.

## Das Problem

Mehmet verwaltet Produktionsdatenbanken, die sein Team sich nicht leisten kann, offline zu nehmen. Heute führt er ein Upgrade einer **100 TB großen PostgreSQL-Datenbank von Version 13 auf 14** durch. Sein Plan:

1. **Ein Backup erstellen** → Allerdings dauert das Backup aufgrund der Datengröße **mehrere Tage**
2. **Das Upgrade am Wochenende durchführen** → Abteilungen werden von einem Ausfall am **Samstag 01:00–05:00 Uhr** benachrichtigt

## Krisenszenario-Auswirkungen

* Ein **unerwarteter Fehler** tritt während des Upgrades auf
* Die Datenbank **kann weder zur alten Version zurückkehren noch mit der neuen Version fortfahren**
* Selbst externe Support-Teams können das Problem nicht lösen

**Folgen:**
* Kunden **können nicht auf Zahlungs- und Bestellsysteme zugreifen**
* Mitarbeiter der Organisation (**5000+ Personen**) können nicht arbeiten
* **Reputationsverlust** und zunehmende Beschwerden entstehen

**Vorübergehende Lösung:**
* Das letzte Backup wird auf **einen neuen Server** geladen → **Hardwarekosten verdoppeln sich**
* Daten von Donnerstag und Freitag sind **nur in der Liveumgebung** vorhanden, daher tritt Datenverlust auf
* **Zwei Datenbanken mit unterschiedlichen Versionen** werden erstellt → Inkonsistenzen nehmen zu

## Rediacc-Lösung

So ändert sich alles mit Rediacc:

![Risk-Free Upgrades](/img/risk-free-upgrades.svg)

### 1. **Instant Cloning**
* Ein **Klon der 100 TB großen Datenbank wird innerhalb von Sekunden erstellt**
* Upgrade-Tests werden durchgeführt, **ohne das Livesystem zu beeinflussen**

### 2. **Stündliche Snapshots**
* Es wird bestimmt, **an welchem Schritt seit wann Fehler während des Upgrade-Prozesses auftreten**
* Problematische Vorgänge werden **im Voraus identifiziert** und korrigiert

### 3. **Nahtloses Upgrade**
* Falls das Upgrade fehlschlägt, ist **die Liveumgebung nicht betroffen**
* Falls das Upgrade erfolgreich ist, wird die neue Liveumgebung zum neuesten Klon

## Ergebnis

**Zeit- und Kosteneinsparungen:**
* Die Backup-Zeit wurde von **7 Tagen auf 10 Sekunden** reduziert

**Risikofreies Upgrade:**
* Fehler wurden im Voraus in der Testumgebung erkannt → **Keine Probleme im Livesystem**

**Keine Ausfallzeiten:**
* Kunden und Mitarbeiter **spürten keine Beeinträchtigung**
