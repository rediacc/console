---
title: "Produktionsähnliche Entwicklungsumgebungen in Minuten"
description: "Verkürzen Sie die Einrichtung von Entwicklungsumgebungen mit Block-Level-Deduplizierung von Tagen auf Minuten."
category: Use Cases
order: 7
language: de
sourceHash: "2aa115fc621f5258"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Reduzieren Sie die Umgebungseinrichtung von Tagen auf Minuten mit der intelligenten Deduplizierungsspeicherarchitektur.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc die Entwicklungsarbeit beschleunigt. Wir sind ein Startup ohne zahlende Kunden, daher handelt es sich um ein Szenario, für das wir das Produkt entworfen haben, nicht um eine fertige Fallstudie.

## Das Problem

Mehmet leitet DevOps in einem E-Commerce-Unternehmen. Sein Team benötigt **produktionsähnliche Umgebungen** zum Testen, Staging und Entwickeln. Der Grund:

**Wo der alte Ansatz scheitert:**
* Das Einrichten produktionsähnlicher Umgebungen dauert **Stunden oder Tage** 
* Entwickler warten darauf, dass die Infrastrukturbereitstellung den Test abschließt 
* Inkonsistenzen in der Umgebung führen zu Problemen mit der Funktion „Funktioniert auf meinem Computer“.

Die Entwicklungszyklen schleppten sich dahin, weil das Aufsetzen einer neuen Umgebung Tage dauerte. Dieser Engpass:

* **Entwicklungsgeschwindigkeit** erheblich verlangsamt 
* Es entstanden Abhängigkeiten und Wartezeiten in der Entwicklungspipeline

## Krisenauswirkungen

* Die Speicherkosten wurden für das IT-Budget **untragbar** 
* Die Backup-Fenster haben die verfügbare Wartungszeit überschritten 
* Die Systemleistung wurde während Sicherungsvorgängen beeinträchtigt 
* Das Risiko eines Datenverlusts ist aufgrund unvollständiger Backups erhöht

## Rediacc-Lösung

Mehmet fand Rediacc. Damit:

![Backup-Diagramm](/img/backup-optimization.svg)

### Intelligente Backup-Technologie 
* **Anscheinend werden vollständige Backups erstellt**, aber nur **geänderte Daten** werden physisch gespeichert 
* Wenn es beispielsweise **durchschnittliche tägliche Änderungen von 100 GB** in einer 10-TB-Datenbank gibt, zeichnet das System **nur diese 100 GB auf** 
* Backups funktionieren **vollständig und nahtlos während der Wiederherstellung**, auch wenn sie als einzelne Datei gespeichert werden

### Hauptvorteile

**1. Kosteneinsparungen** 
* Selbst bei **100 GB** täglichen Änderungen in einer 10-TB-Datenbank sind die monatlichen Speicherkosten auf **~3 TB** begrenzt (bei dem alten System waren es **~300 TB**)

**2. Funktioniert mit jedem Stack**
* Rediacc ist nicht auf SQL Server beschränkt. Es funktioniert kompatibel mit **MySQL, PostgreSQL, MongoDB** und allen anderen Datenbanken 
* Es ist kein **separates Know-how** für verschiedene Systeme erforderlich

**3. Schnellere Zyklen, weniger Hardware**
* Die Backup-Zeit wird von **Stunden auf Minuten** reduziert. 
* Die Belastung der Festplatten- und Netzwerkressourcen sinkt um 99,99 % (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots).

## Ergebnis

Mit Rediacc hat das Team:
* Reduzierte Speicherkosten um **99,99 % (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots)** 
* Standardisierte Sicherungs- und Wiederherstellungsprozesse 
* Erfüllt alle Anforderungen mit **einer einzigen Lösung** für verschiedene Datenbanksysteme
