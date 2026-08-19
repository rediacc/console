---
title: Bankkontinuität während eines Stromausfalls
description: >-
  Halten Sie den Bankbetrieb auch bei Stromausfällen mit interkontinentaler
  Datenspiegelung aufrecht.
category: Use Cases
tags:
  - backup
  - migration
order: 6
language: de
sourceHash: "8817b7a0a9304cd0"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
---

> **Wenn das Licht ausgeht, läuft Ihr Geschäft weiter.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Am 28. April 2025 kam es in Spanien und Portugal zu einem massiven Stromausfall, der durch eine beschädigte Übertragungsleitung in Frankreich ausgelöst wurde. Durch den Stromausfall kam es zu einem Ausfall kritischer IT-Infrastrukturen, wodurch große Banken und Technologieunternehmen den Zugriff auf ihre Systeme verloren.

## Das Problem

Das iberische Stromnetz war mit einer katastrophalen Ausfallkaskade konfrontiert:

* Ein **Brand im Südwesten Frankreichs** beschädigte eine wichtige Übertragungsleitung 
* Der Schaden verursachte eine **plötzliche Unterbrechung** der grenzüberschreitenden Verbindungsleitungen 
* Spanien und Portugal wurden vom europäischen Stromnetz **elektrisch isoliert**

**Auswirkungen auf Unternehmen:** 
* Rechenzentren in ganz Spanien erlitten **sofortigen Stromausfall** 
* An mehreren Standorten konnten die Backup-Generatoren aufgrund von Fehlern im Steuerungssystem nicht aktiviert werden 
* Bankensysteme gingen offline und verhinderten Transaktionen im ganzen Land

**Herausforderungen für die IT-Infrastruktur:** 
* **Lokale Backup-Systeme** waren wirkungslos, da sie sich in derselben betroffenen Region befanden 
* **Notfallwiederherstellungsverfahren** beruhten auf lokalem Zugriff auf physische Server 
* **Business-Continuity-Pläne** berücksichtigten keinen landesweiten Stromausfall von mehr als 4 Stunden

## Krisenauswirkungen

Die Störung des IT-Dienstes führte zu Folgendem: 
* **Zusammenbruch des Finanzsystems** mit geschätzten Transaktionsverzögerungen in Höhe von 4,5 Milliarden Euro 
* Kritische Geschäftsdaten sind für mehr als 14 Stunden nicht mehr zugänglich 
* Große E-Commerce-Plattformen erleben eine vollständige Schließung 
* Kundendienstsysteme versagen in mehreren Branchen

## Rediacc-Lösung

Eine große spanische Bankengruppe, die die kontinentalübergreifende Replikationslösung von Rediacc implementierte, hielt den Betrieb während der gesamten Krise aufrecht:

![Banking Continuity During Blackout](/img/blackout-continuity.svg)

### 1. **Interkontinentale Datenspiegelung** 
* Kernbankdatenbanken und Transaktionssysteme würden **kontinuierlich** in Rechenzentren in den Vereinigten Staaten repliziert 
* Kundendaten und Transaktionsdatensätze blieben synchron, innerhalb der Replikationsverzögerung, die Ihre Verbindung und Ihr Datenvolumen zulassen

### 2. **Nahtloser Betriebsübergang** 
* Würden die spanischen Server ausfallen, würde der Datenverkehr **automatisch** auf die in den USA ansässigen Systeme umgeleitet 
* Kunden würden nur eine kurze Unterbrechung bemerken, bis die Umleitung abgeschlossen ist, statt eines Ausfalls in der Dauer des Netzausfalls

### 3. **Fortsetzung des Remote-Service** 
* Callcenter in nicht betroffenen Ländern könnten die replizierten Systeme erreichen und den Kundensupport weiter aufrechterhalten 
* Mobile-Banking-Apps blieben funktionsfähig, indem sie sich mit den alternativen Rechenzentren verbinden

## Mögliches Ergebnis

**Geschäftskontinuität:** 
* Wettbewerber waren über 14 Stunden offline. Eine Bank mit dieser Architektur würde im selben Zeitraum weiter im Dienst bleiben

**Kontinuität des Service:** 
* Sie könnte weiterhin Transaktionen verarbeiten, während Institute ohne zweite Region dazu nicht in der Lage wären

**Finanzielle Absicherung:** 
* Es würden die Verluste durch Transaktionsausfälle vermieden, die für jede Stunde anfallen, in der ein Zahlungssystem ausfällt
* Es gingen keine Daten verloren oder wurden beschädigt, sodass keine Wiederherstellungsvorgänge nötig wären

