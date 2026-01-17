---
title: Beschleunigte Entwicklungsvorgänge
description: Reduzieren Sie die Einrichtung der Umgebung mit intelligentem Deduplizierungsspeicher von Tagen auf Minuten.
category: Use Cases
order: 7
language: de
---

> **Reduzieren Sie die Umgebungseinrichtung von Tagen auf Minuten mit der intelligenten Deduplizierungsspeicherarchitektur.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie die Infrastrukturautomatisierungsplattform von Rediacc, die für KI-gesteuerte Abläufe entwickelt wurde, die Entwicklung beschleunigen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

## Das Problem

Mehmet arbeitet als DevOps-Ingenieur in einem E-Commerce-Unternehmen. Das Entwicklungsteam benötigt **produktionsähnliche Umgebungen** zum Testen, Staging und Entwickeln. Das liegt daran:

**Traditionelle Umweltherausforderungen:** 
* Das Einrichten produktionsähnlicher Umgebungen dauert **Stunden oder Tage** 
* Entwickler warten darauf, dass die Infrastrukturbereitstellung den Test abschließt 
* Inkonsistenzen in der Umgebung führen zu Problemen mit der Funktion „Funktioniert auf meinem Computer“.

Das Unternehmen hatte mit langsamen Entwicklungszyklen zu kämpfen, da die Bereitstellung der Umgebung einen Engpass darstellte. Diese Situation:

* **Entwicklungsgeschwindigkeit** erheblich verlangsamt 
* Es entstanden Abhängigkeiten und Wartezeiten in der Entwicklungspipeline

## Krisenauswirkungen

* Die Speicherkosten wurden für das IT-Budget **untragbar** 
* Die Backup-Fenster haben die verfügbare Wartungszeit überschritten 
* Die Systemleistung wurde während Sicherungsvorgängen beeinträchtigt 
* Das Risiko eines Datenverlusts ist aufgrund unvollständiger Backups erhöht

## Rediacc-Lösung

Mehmet hat Rediacc entdeckt und mit diesem System:

![Backup-Diagramm](/img/backup-optimization.svg)

### Intelligente Backup-Technologie 
* **Anscheinend werden vollständige Backups erstellt**, aber nur **geänderte Daten** werden physisch gespeichert 
* Wenn es beispielsweise **durchschnittliche tägliche Änderungen von 100 GB** in einer 10-TB-Datenbank gibt, zeichnet das System **nur diese 100 GB auf** 
* Backups funktionieren **vollständig und nahtlos während der Wiederherstellung**, auch wenn sie als einzelne Datei gespeichert werden

### Hauptvorteile

**1. Kosteneinsparungen** 
* Selbst bei **100 GB** täglichen Änderungen in einer 10-TB-Datenbank sind die monatlichen Speicherkosten auf **~3 TB** begrenzt (bei dem alten System waren es **~300 TB**)

**2. Universelle Unterstützung** 
* Rediacc ist nicht auf SQL Server beschränkt. Es funktioniert kompatibel mit **MySQL, PostgreSQL, MongoDB** und allen anderen Datenbanken 
* Es ist kein **separates Know-how** für verschiedene Systeme erforderlich

**3. Zeit- und Ressourceneffizienz** 
* Die Backup-Zeit wird von **Stunden auf Minuten** reduziert. 
* Die Belastung der Festplatten- und Netzwerkressourcen sinkt um 99,99 % (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots).

## Ergebnis

Dank Rediacc hat das Unternehmen: 
* Reduzierte Speicherkosten um **99,99 % (abhängig vom Aktualisierungsverhältnis der Gesamtdaten zwischen Snapshots)** 
* Standardisierte Sicherungs- und Wiederherstellungsprozesse 
* Erfüllt alle Anforderungen mit **einer einzigen Lösung** für verschiedene Datenbanksysteme