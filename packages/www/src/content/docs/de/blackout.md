---
title: Bankkontinuität während eines Stromausfalls
description: Halten Sie den Bankbetrieb auch bei Stromausfällen mit interkontinentaler Datenspiegelung aufrecht.
category: Use Cases
order: 6
language: de
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

### 1. **Interkontinentale Datenspiegelung** 
* Kernbankdatenbanken und Transaktionssysteme wurden **kontinuierlich** in Rechenzentren in den Vereinigten Staaten repliziert 
* Alle Kundendaten und Transaktionsaufzeichnungen wurden mit **weniger als 3 Sekunden Verzögerung** synchronisiert

### 2. **Nahtloser Betriebsübergang** 
* Als die spanischen Server ausfielen, wurde der Datenverkehr **automatisch** auf in den USA ansässige Systeme umgeleitet 
* Kunden erlebten nur eine kurze Unterbrechung von 47 Sekunden, bevor die Dienste wieder aufgenommen wurden

### 3. **Fortsetzung des Remote-Service** 
* Callcenter in nicht betroffenen Ländern griffen auf die replizierten Systeme zu, um den Kundensupport aufrechtzuerhalten 
* Mobile-Banking-Apps blieben durch die Anbindung an alternative Rechenzentren funktionsfähig

## Mögliches Ergebnis

**Geschäftskontinuität:** 
* Während die Konkurrenz mehr als 14 Stunden lang offline war, konnte die Bank **eine Serviceverfügbarkeit von 98 %** aufrechterhalten.

**Kundenvertrauen:** 
* Die Bank war das einzige große Finanzinstitut, das während der Krise Transaktionen abwickelte 
* Die Kundenzufriedenheit stieg in Umfragen nach der Krise um 27 %

**Finanzielle Absicherung:** 
* Die Bank konnte etwa 370 Millionen Euro an Verlusten durch Transaktionsfehler vermeiden 
* Es gingen keine Daten verloren oder wurden beschädigt, wodurch kostspielige Wiederherstellungsvorgänge entfallen

**Wettbewerbsvorteil:** 
* Die Bank gewann im folgenden Monat 140.000 neue Kunden von Wettbewerbern, die ihren Service nicht aufrechterhalten konnten