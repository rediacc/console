---
title: Zeitreise-Erholung
description: Stellen Sie mit Snapshot-basierten Zeitreisen versehentlich gelöschte Daten von vor Wochen wieder her.
category: Use Cases
order: 2
language: de
---

> **Wenn andere Daten für immer verlieren, können Sie in die Vergangenheit reisen.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Ein neu eingestellter Mitarbeiter hat vor drei Wochen **versehentlich** kritische Daten aus der Live-Datenbank gelöscht. Das Backup-System des Unternehmens speicherte Backups nur zwei Wochen lang, was eine Datenwiederherstellung mit herkömmlichen Mitteln nahezu unmöglich machte.

## Das Problem

Mehmet ist als Systemexperte für die Datenbank eines großen Online-Shopping-Unternehmens verantwortlich. Eines Morgens bemerkte er aufgrund von Kundenbeschwerden, dass einige frühere Bestelldaten im System **nicht sichtbar** sind. Die Untersuchung ergab, dass ein neu eingestellter Mitarbeiter vor drei Wochen **versehentlich** einige wichtige Daten aus der Live-Datenbank gelöscht** hat, indem er **eine Verbindung zur Live-Datenbank statt zur Testumgebung herstellte**.

**Vorhandenes Backup-System:** 
* Vollständige Backups werden einmal pro Woche erstellt 
* **Inkrementelle Backups** werden täglich aufgezeichnet

**Dilemma:** Die Löschung erfolgte **vor dem Datum der Vollsicherungen**, sodass die verlorenen Daten nicht in den Sicherungen enthalten sind. Tägliche Backups zeichnen **nur die neuesten Daten auf**, sodass **gelöschte Elemente nicht wiederhergestellt werden können**.

## Krisenauswirkungen

Aufgrund verlorener Daten: 
* Kunden können **Rückerstattungsanträge nicht bearbeiten** 
* Im Zahlungssystem treten Inkonsistenzen auf 
* Beschwerden verbreiten sich schnell in den sozialen Medien

**Ergebnisse:** 
* Das Kundensupport-Team steht unter **starkem Druck** 
* Der Ruf des Unternehmens wird **schnell geschädigt** 
* Manuelle Datenwiederherstellungsbemühungen erzielen **nur 15 % Erfolg**

**Zusätzliche Herausforderung:** 
* Um die Speicherkosten zu senken, behält das Unternehmen **nur die Backups der letzten 2 Wochen** 
* Die gelöschten Daten befinden sich nicht in den **aktuellen Backups**

## Rediacc-Lösung

Mehmet bietet mit Rediacc eine „Zeitmaschinen“-ähnliche Lösung:

### 1. **Schnappschüsse** 
* Rediacc erstellt automatisch stündlich Snapshots des Systems 
* Diese Schnappschüsse decken auch die Momente unmittelbar vor dem Löschen der Daten ab

### 2. **Reise in die Vergangenheit** 
* Mehmet wählt das Datum und die Uhrzeit des Löschvorgangs in der Rediacc-Schnittstelle aus 
* Stellt in 1 Minute einen Snapshot des Systems von vor 3 Wochen auf einer neuen Instanz wieder her

### 3. **Vollständige Wiederherstellung** 
* Verlorene Daten werden vollständig und konsistent wiederhergestellt

## Ergebnis

* Der Ruf des Unternehmens wurde **innerhalb von 24 Stunden** wiederhergestellt 
* Finanzieller Verlust wurde um **95 %** verhindert 
* Rediacc hat bewiesen, dass häufige Backups erstellt werden können, **ohne die Speicherkosten zu erhöhen**