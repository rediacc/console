---
title: "Richtlinie zur Offenlegung von Schwachstellen"
description: "So melden Sie eine Sicherheitslücke in Rediacc: Geltungsbereich, Safe Harbour, Meldeweg und zu erwartende Reaktionszeiten."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: de
sourceHash: "49a84775c19854ee"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Rediacc freut sich über Meldungen von Sicherheitslücken in seinen Produkten und Diensten. Diese Richtlinie beschreibt, was im Geltungsbereich liegt, wie gemeldet wird und was Meldende im Gegenzug erwarten können. Die maschinenlesbare Kontaktdatei liegt unter [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Geltungsbereich

Im Geltungsbereich:

- die `rdc`-CLI und der Maschinen-Orchestrator `renet`
- der Account-Server, sein Webportal und seine API
- die Rediacc-Websites unter `rediacc.com` und `rediacc.cloud`
- die Release-Artefakte: Binärdateien, Container-Images und Installer

Außerhalb des Geltungsbereichs:

- Befunde, die physischen Zugriff auf eine Maschine voraussetzen, oder ein kompromittierter Endpunkt, den die meldende Person bereits kontrolliert
- Denial-of-Service durch Masse, Spam oder Social Engineering gegen Mitarbeitende
- Meldungen automatischer Scanner ohne nachgewiesene Auswirkung
- Schwachstellen in Drittsoftware, die Rediacc nur unverändert weitergibt; diese gehören zum Upstream-Projekt, eine Kopie an uns ist willkommen

## So melden Sie

Senden Sie die Meldung an [security@rediacc.com](mailto:security@rediacc.com). Bitte angeben:

- das betroffene Produkt samt Version oder die URL
- die Schritte zur Reproduktion oder einen Proof of Concept
- die erwartete Auswirkung
- ob das Problem bereits öffentlich bekannt ist oder ausgenutzt wird
- eine Kontaktadresse für Rückfragen und ob eine namentliche Erwähnung gewünscht ist

Meldungen auf Englisch werden bevorzugt. Echte Kundendaten gehören nicht in die Meldung: Ein minimaler Nachweis des Zugriffs genügt.

## Safe Harbour

Rediacc verfolgt keine rechtlichen Schritte gegen Meldende, die nach dieser Richtlinie in gutem Glauben handeln, und unterstützt solche Schritte auch nicht. Das heißt, die meldende Person:

- testet nur an eigenen Konten, Maschinen und Daten oder an Ressourcen, die Rediacc gehören
- hört auf, sobald das Problem belegt ist, und liest, ändert, kopiert oder löscht keine Daten Dritter
- beeinträchtigt den Dienst für andere Nutzer nicht
- meldet zügig und hält die Details bis zum unten genannten Termin der koordinierten Offenlegung vertraulich

Arbeiten innerhalb dieser Grenzen gelten als autorisiert, und Rediacc bestätigt das gegenüber Dritten, die danach fragen.

## Reaktionszeiten

| Schritt | Ziel |
|---------|------|
| Eingangsbestätigung der Meldung | 2 Werktage |
| Erste Bewertung samt Schweregrad | 5 Werktage |
| Statusmeldungen, solange der Fall offen ist | mindestens alle 14 Tage |
| Behebung oder Abhilfe bei einem kritischen Problem | 14 Tage ab der Bewertung |
| Behebung oder Abhilfe bei anderen bestätigten Problemen | 90 Tage ab der Bewertung |

Die Zeiten sind Zielvorgaben. Braucht eine Meldung mehr Zeit, folgen eine Erklärung und ein neuer Termin.

## Koordinierte Offenlegung

Die Details werden zusammen mit dem Fix veröffentlicht, in der Regel innerhalb von 90 Tagen nach der Meldung. Wer eine frühere oder spätere Veröffentlichung wünscht, nennt den Termin in der Meldung, und beide Seiten einigen sich auf einen Termin. Eine bereits aktiv ausgenutzte Schwachstelle wird als Vorfall behandelt, wie auf der Seite zur [Reaktion auf Sicherheitsvorfälle](/de/docs/security-incident-response) beschrieben.

## Erwähnung

Eine bestätigte Meldung wird in den Release Notes oder im Advisory unter dem Namen oder Pseudonym genannt, den die meldende Person wählt. Rediacc betreibt kein Bug-Bounty-Programm mit Vergütung.

## Siehe auch

- [Reaktion auf Sicherheitsvorfälle](/de/docs/security-incident-response)
- [Kontosicherheit und API](/de/docs/account-security)
