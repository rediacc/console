---
title: Zeitreisen-Wiederherstellung
description: "Stellen Sie vor Wochen gelöschte Daten mithilfe von btrfs-Snapshots wieder her, auch wenn Ihre normalen Sicherungen diese Zeit bereits überschritten haben."
category: Use Cases
order: 2
language: de
sourceHash: "e55d51b8df91b20f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Wenn andere Daten für immer verlieren, können Sie in die Vergangenheit reisen.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc mit dieser Art von Problem umgeht. Wir sind ein Startup. Das sind realistische Szenarien, für die das Produkt entwickelt wurde, keine Kundenfallstudien, die wir bereits abgeliefert haben.

**Krisenszenario:** Ein neuer Mitarbeiter hat vor drei Wochen **versehentlich** kritische Zeilen aus Ihrer Live-Datenbank gelöscht. Ihr Backup-System bewahrt nur 2 Wochen an Verlauf. Mit einem normalen Setup sind diese Daten verloren.

## Das Problem

Mehmet ist für die Datenbank einer großen E-Commerce-Plattform zuständig. Eines Morgens beschweren sich Kunden, dass frühere Bestelldaten **nicht mehr sichtbar** sind. Er untersucht die Situation. Ein neu eingestellter Entwickler hatte vor drei Wochen **versehentlich** kritische Zeilen aus der Live-Datenbank gelöscht, indem er **sich mit der Live-Datenbank statt mit der Testumgebung verband**. Der klassische Fehler, den jeder DBA entweder selbst gemacht hat oder bei einem Junior beobachtet hat.

**Vorhandenes Backup-System:**
* Vollständige Backups werden einmal pro Woche erstellt
* **Inkrementelle Backups** werden täglich aufgezeichnet

**Das Dilemma:** Die Löschung erfolgte **vor dem Datum der Vollsicherungen**, sodass die verlorenen Daten in keiner Backup-Datei enthalten sind. Tägliche Backups zeichnen **nur die neuesten Daten auf**, sodass **gelöschte Elemente nicht wiederhergestellt werden können**.

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

Hier ist das Zeitmaschinen-Setup, das Mehmet mit Rediacc aufbaut:

![Time Travel Recovery](/img/time-travel-recovery.svg)

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
