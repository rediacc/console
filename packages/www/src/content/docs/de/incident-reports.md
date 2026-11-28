---
title: "Incident-Berichte: gestuft, signiert und verifizierbar"
description: "Erzeugen Sie Frühwarnung, Meldung und Abschlussbericht zu einem Incident in einem Kunden-Repository als JSON, STIX 2.1 oder PDF. Jeder Bericht ist mit Ed25519 signiert, trägt einen QR-Verifizierungslink und bildet seine Felder auf NIS2, das Format 2025/302 und DSGVO Art. 33 Abs. 3 ab."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: de
sourceHash: "d7f6e084c5c1d0d9"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Incident-Berichte

Ein deklarierter Incident ([Incident Response](/de/docs/incident-response)) erzeugt drei gestufte Berichte, die der Kunde bei einer Aufsichtsbehörde einreichen kann. Rediacc erstellt die Dokumente aus den Beweisen. Ob ein Vorfall erheblich oder meldepflichtig ist, bleibt die Einschätzung des Kunden, und jeder Bericht sagt das ausdrücklich.

## Stufen

Jede Stufe ergänzt die unten aufgeführten Abschnitte und übernimmt die der vorherigen Stufe, sodass ein Abschnitt, den keine Stufe verlangt, entfällt, statt leer zu bleiben.

| Stufe | Fällig | Ergänzt |
|---|---|---|
| Frühwarnung | 24 Stunden nach Kenntnisnahme | Kopfdaten, Zeitleiste, Kompromittierungsindikatoren, vermutete böswillige und grenzüberschreitende Auswirkung |
| Meldung | 72 Stunden nach Kenntnisnahme | Erstbewertung, Datenauswirkung (Kategorien, ungefähre Anzahlen, Mitgliedstaaten) und ATT&CK-Techniken |
| Abschluss | Ein Kalendermonat nach der Meldung | Grundursache und Abhilfemaßnahmen |

Der Abschlussbericht folgt auf eine Meldung, daher wird zuerst die Meldung erzeugt.

Jede Tatsache in einem Bericht gibt an, woher man sie kennt: in den Beweisen beobachtet, vom Kunden eingegeben oder abgeleitet. Eine abgeleitete Tatsache trägt eine Konfidenz und die Begründung des Detektors. Bewertung, Datenkategorien, Mitgliedstaaten, vermutete Ursache, ergriffene Maßnahmen, Kontaktstelle und Techniken sind Eingaben, die der Kunde vor dem Erzeugen auf der Incident-Seite einträgt.

## Formate

| Format | Verwendung |
|---|---|
| JSON | Die kanonische, verifizierbare Form |
| STIX 2.1 | Ein Bündel von Indikatoren für Threat-Intelligence-Werkzeuge |
| PDF | Ein lesbares Dokument mit eingebetteter Noto Sans (Latein, Kyrillisch und Türkisch) oder Noto Sans Arabic; japanische, koreanische und chinesische Berichte werden abgelehnt, bis ihre Schriftarten festgelegt sind. Mit Haftungshinweis, QR-Code und Berichts-Hash in jeder Fußzeile |

Auf der Incident-Seite hat jede Stufe pro Format eine Download-Schaltfläche. Auf der Kommandozeile:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

Das Format ist standardmäßig JSON. `--format` gilt nur zusammen mit `--stage`. Die Datei wird unter ihrer Berichts-ID geschrieben.

## Signatur und Verifikation

Jeder Bericht wird mit einem Ed25519-Berichtsschlüssel signiert, und Berichts-ID, Stufe und Hash stehen in einem öffentlichen Register. Die Signatur deckt den kanonischen Inhalt des Berichts ab, sodass jede Änderung nach dem Signieren erkannt wird.

Ein Bericht wird an drei Stellen geprüft:

- Die Verifizierungsseite unter `/account/verify/report/<id>`, die der QR-Code im PDF öffnet. Die Prüfung läuft im Browser gegen den veröffentlichten Berichtsschlüssel, und nichts wird hochgeladen. Eine JSON-Datei wird vollständig geprüft. Ein PDF lässt sich im Browser nicht neu hashen, daher bestätigt die Seite, dass das PDF den Hash des Berichts trägt, und verweist für die vollständige Prüfung auf die JSON-Datei.
- Die Kommandozeile, für einen JSON-Bericht:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

Der Befehl endet mit Exit-Code 1, wenn Inhalt oder Signatur nicht passen. Ein PDF wird über den JSON-Bericht verifiziert, aus dem es erzeugt wurde.

- Der Beweisstempel im Bericht, der das Ergebnis von Verify evidence für das Fenster festhält: wer verifiziert hat, mit welcher Version und wann.

## Feldzuordnung

Jedes Berichtsfeld wird auf die Regelwerke abgebildet, nach denen der Kunde meldet, sodass sich der Inhalt ohne erneutes Abtippen übernehmen lässt. Die Zuordnung deckt drei Regelwerke ab: NIS2 Art. 23 Abs. 4, das Meldeformat der Durchführungsverordnung (EU) 2025/302 und DSGVO Art. 33 Abs. 3. Beispiele:

| Berichtsfeld | NIS2 | DSGVO |
|---|---|---|
| Zeitpunkt der Kenntnisnahme | Art. 23(4)(a) | Art. 33(1) |
| Chronologie | Art. 23(4)(d) | Art. 33(3)(a) |
| Kontaktstelle | Art. 23(4) | Art. 33(3)(b) |

Ein Feld ohne Entsprechung in einem Regelwerk nennt den Grund, statt wegzufallen. Die Meldung nach DSGVO Art. 33 Abs. 3 kennt zum Beispiel weder ein Aktenzeichen noch einen Abschlusszeitpunkt.

## Was ein Bericht nicht behauptet

In jeder Stufe stehen zwei Aussagen:

- Flow-Datensätze belegen Volumen und Ziel, nicht den Inhalt.
- Ob der Vorfall erheblich oder meldepflichtig ist, liegt in der Einschätzung des Kunden.

Rediacc reicht im Namen des Kunden nichts bei einer Aufsichtsbehörde ein.
