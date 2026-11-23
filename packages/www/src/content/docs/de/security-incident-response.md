---
title: "Reaktion auf Sicherheitsvorfälle"
description: "Wie Rediacc mit eigenen Sicherheitsvorfällen umgeht: die gestuften Kundenmitteilungen, die Angaben nach DSGVO Art. 33(3), der CRA-Meldeweg und was Kunden erhalten."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: de
sourceHash: "6b9f728f093ecb0c"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Diese Seite beschreibt, was geschieht, wenn Rediacc selbst einen Sicherheitsvorfall hat, etwa eine Kompromittierung der eigenen Systeme oder eine aktiv ausgenutzte Schwachstelle in den Produkten. Vorfälle in den eigenen Repositories eines Kunden untersucht und meldet der Kunde selbst; Rediacc stellt dafür die Werkzeuge zur Beweissicherung bereit. Schwachstellenmeldungen von außen regelt die [Richtlinie zur Offenlegung](/de/docs/security-disclosure-policy).

## Stufen

Für jeden Vorfall läuft eine Frist ab dem Moment, in dem Rediacc davon erfährt. Informationen werden in Stufen freigegeben, weil das ganze Bild am ersten Tag selten feststeht und DSGVO Art. 33(4) eine schrittweise Bereitstellung erlaubt.

| Stufe | Fällig | Inhalt |
|-------|--------|--------|
| Frühwarnung | innerhalb von 24 Stunden | was bisher bekannt ist und ob böswillige Handlungen vermutet werden |
| Meldung | innerhalb von 72 Stunden | die Art des Vorfalls, eine erste Bewertung und die ergriffenen Maßnahmen |
| Abschlussbericht | innerhalb eines Monats | eine detaillierte Beschreibung, die Ursache sowie die umgesetzten und laufenden Maßnahmen |

## Die Angaben nach Art. 33(3)

Jede Stufe enthält die vier in DSGVO Art. 33(3) genannten Punkte:

1. die Art der Verletzung, mit den Kategorien und der ungefähren Zahl der betroffenen Personen und der betroffenen Datensätze
2. Name und Kontaktdaten der Anlaufstelle für weitere Informationen
3. die wahrscheinlichen Folgen
4. die ergriffenen oder vorgeschlagenen Maßnahmen zur Behandlung der Verletzung, einschließlich Maßnahmen zur Abmilderung möglicher nachteiliger Auswirkungen

Ist ein Wert noch nicht bekannt, sagt die Stufe das und nennt das Datum, bis zu dem er vorliegen wird.

## Was Kunden erhalten

Betrifft ein Vorfall eine Organisation:

- wird jede Stufe als Mitteilung im Account-Portal und als E-Mail an die Eigentümer und Admins der Organisation sowie an deren Sicherheitskontakt gesendet
- werden Mitteilung und E-Mail unabhängig von den Benachrichtigungseinstellungen versandt, weil es sich um Sicherheitskommunikation handelt
- verweist ein Banner im Portal auf die Vorfallseite, die jede veröffentlichte Stufe zeigt
- bietet jede Stufe ein STIX 2.1-Bundle mit den Kompromittierungsindikatoren in einem maschinenlesbaren Format, das Sicherheitswerkzeuge importieren können

Eine nicht betroffene Organisation erhält nichts. Eigentümer und Admins legen den Sicherheitskontakt der Organisation im Portal fest, damit die E-Mail die richtige Person erreicht.

## Behördliche Meldungen

Rediacc meldet eigene Vorfälle, wo das Gesetz es verlangt.

- **DSGVO.** Handelt Rediacc als Auftragsverarbeiter, informiert die gestufte Mitteilung den Verantwortlichen unverzüglich (Art. 33(2)), und der Verantwortliche entscheidet über die Meldung an seine Aufsichtsbehörde. Ist Rediacc selbst Verantwortlicher, meldet es die Verletzung möglichst binnen 72 Stunden an die zuständige Aufsichtsbehörde (Art. 33(1)).
- **Cyber Resilience Act.** Seit dem 11. September 2026 verlangt Art. 14 der Verordnung (EU) 2024/2847 von Herstellern, eine aktiv ausgenutzte Schwachstelle oder einen schwerwiegenden Vorfall, der die Sicherheit eines Produkts mit digitalen Elementen beeinträchtigt, über die zentrale Meldeplattform dem benannten CSIRT und der ENISA zu melden. Es gelten dieselben Schritte nach 24 Stunden, 72 Stunden und der Abschlussbericht, und derselbe Vorfallsdatensatz speist sowohl die Kundenmitteilung als auch die Meldung.

## Einen Verdachtsfall melden

Wer einen Vorfall vermutet, der Rediacc betrifft, einschließlich Kunden, die an einer Rediacc-Komponente unerwartetes Verhalten beobachten, schreibt an [security@rediacc.com](mailto:security@rediacc.com). Für die Meldung einer Schwachstelle gilt die [Richtlinie zur Offenlegung](/de/docs/security-disclosure-policy).
