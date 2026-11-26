---
title: "Incident Response: Untersuchen, Deklarieren und Beweise sichern"
description: "Öffnen Sie eine Untersuchung zu einem Repository oder einer Maschine, lesen Sie eine Zeitleiste aus Audit, Läufen, Flüssen und Dateiöffnungen, verifizieren Sie die Hash-Ketten, deklarieren Sie einen Incident, um die Beweise einzufrieren und die Fristen von 24 Stunden, 72 Stunden und einem Monat zu starten, und steuern Sie alles über rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: de
sourceHash: "0e7681b5366968f0"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Incident Response

Gemeint ist hier ein Vorfall, der sich in den eigenen Repositories eines Kunden abspielt. Die Untersuchungsseite, die `rdc incident`-Befehle und die Leser `rdc repo flows` und `rdc repo opens` arbeiten alle mit den Aufzeichnungen, die unter [Forensik](/de/docs/forensics) beschrieben sind. Vorfälle in den eigenen Systemen von Rediacc folgen dem Dokument [Security Incident Response](/de/docs/security-incident-response).

## Zugriff

Eine Untersuchung setzt einen bezahlten Tarif und die Rolle Inhaber oder Admin voraus. Beim Öffnen wird eine aktuelle erneute Authentifizierung verlangt, und eine geöffnete Untersuchung bleibt 60 Minuten gültig. Jede Ansicht wird im Audit-Log festgehalten.

Rediacc-Support sieht Forensikdaten nur mit einer Support-Freigabe, die der Kunde erteilt. Eine Freigabe gilt höchstens 7 Tage und kann jederzeit widerrufen werden.

Die Lesezugriffe der CLI brauchen den Scope `forensics:read`, Deklarieren und Abschließen brauchen `incident:manage`. Ein CLI-Login trägt beide für Inhaber und Admins nach einer erhöhten Freigabe im Browser. Meldet ein Befehl, dass eine aktuelle erhöhte Freigabe nötig ist, fragt das Konto-Portal sie ab, und der Befehl lässt sich erneut ausführen.

## Die Zeitleiste

Die Seite Investigate führt einen Bereich (ein Repository oder eine Maschine) zu einer Zeitleiste mit fünf Zeilenarten zusammen: Konsolen-Auditereignisse, Läufe, Netzwerkflüsse, Dateiöffnungen und Anomalien. Änderungen seit dem letzten Snapshot lassen sich mit diesem vergleichen. Ein Zeitfenster-Schieber legt das Fenster fest, und ein Fenster umfasst höchstens 31 Tage.

Eine Strecke ohne Beweise erscheint als Lückenzeile, die Maschine und Grund nennt, nie als leere Strecke. Ein Diagramm der ausgehenden Bytes pro Minute und eine Liste der häufigsten Ziele stehen über den Zeilen.

Dieselben Lesezugriffe gibt es auf der Kommandozeile:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` und `--until` akzeptieren einen ISO-8601-Zeitpunkt oder eine Spanne rückwärts ab jetzt wie `90m`, `24h` oder `7d`. Standardfenster sind die letzten 24 Stunden. Flow-Zeilen zeigen Zeit, Prozess, Ziel, Bytes raus und rein sowie ASN und Land, falls bekannt. Öffnungszeilen zeigen Zeit, Prozess und Pfad, wobei sensible Pfade markiert sind.

## Beweise verifizieren

Verify evidence berechnet im Browser die Hash-Kette der Audit-Tagesdateien und die signierten Batch-Ketten der Forensikdaten für das Fenster neu und listet jede Lücke und jede Änderung auf. Batch-Signaturen werden mit den Spool-Schlüsseln geprüft, die der Account-Server für jede Maschine fest hinterlegt hat. Einem Schlüssel, der innerhalb der Beweise steht, wird nie vertraut. Das Ergebnis wird in exportierte Berichte gestempelt.

Beweise über 2 GiB sind für den Browser zu groß. Dasselbe Modul läuft auf der Kommandozeile:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

Der Befehl endet mit Exit-Code 1, sobald eine Lücke oder Änderung gefunden wird. `--machine-key <machine>=<public-key-hex>` (der Schlüssel hat 64 Hex-Zeichen) liefert einen Schlüssel von außerhalb des Verzeichnisses und lässt sich wiederholen. Eine Maschine ohne externen Schlüssel schlägt fehl.

## Einen Incident deklarieren

Das Deklarieren friert die Beweise ein. Zuerst wird der Kontoeintrag angelegt, danach wird das Repository für die Untersuchung vorbereitet:

1. Der Incident wird mit seinem Fenster, dem Deklarierenden und dem Zeitpunkt festgehalten, an dem die Organisation davon erfuhr.
2. Eine Verdrängungssperre deckt das Fenster ab, und die Bucket-Sperrregeln erstrecken sich darauf, sodass FIFO diese Tage nicht entfernen kann.
3. Das Repository wird als forensischer Snapshot geforkt, mit dem Tag `incident-<id>`.
4. Die Erfassungsstufe des Repositorys wechselt auf Full.

Ab dem Zeitpunkt der Kenntnisnahme laufen drei Fristen. Dieser kann früher als die Deklaration gesetzt werden, aber nie später: Die Frühwarnung ist 24 Stunden nach Kenntnisnahme fällig, die Meldung 72 Stunden danach, und der Abschlussbericht einen Kalendermonat nach der Meldung (gezählt ab der Meldefrist, bis eine Meldung erfasst ist). Die Seite zeigt jede Frist als ausstehend, in 6 Stunden fällig, überfällig oder erledigt.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Ein fehlgeschlagener Maschinenschritt lässt den Eintrag und seine Sperre bestehen, endet mit Exit-Code 1 und nennt den Befehl, der nur die fehlgeschlagenen Schritte erneut ausführt:

```bash
rdc incident declare mail --resume <id>
```

`--resume` behält Fenster und Kenntnisnahme der ursprünglichen Deklaration bei, daher werden `--since`, `--until` und `--aware-at` nicht damit kombiniert.

## Die Beweise exportieren

`rdc incident export` schreibt das Fenster des Incidents in ein Verzeichnis: den Incident-Eintrag mit seinen Fristen, die zusammengeführte Zeitleiste, die Aggregate der ausgehenden Bytes, das rohe Ketten-Manifest und die rohen Dateien, die es aufführt. Listet das Manifest Audit-Tagesdateien oder Forensik-Header-Dateien, werden die Ketten dabei verifiziert, und das Ergebnis geht in `verification.json`. Der Befehl endet mit Exit-Code 1, wenn die Beweise eine Lücke oder Änderung zeigen.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Mit `--stage` schreibt derselbe Befehl stattdessen einen signierten Bericht. Siehe [Incident-Berichte](/de/docs/incident-reports).

## Einen Incident abschließen

```bash
rdc incident close <id>
```

Nichts wird sofort freigegeben. Die Verdrängungssperre und die Bucket-Sperrregeln enden 30 Tage nach dem Abschluss.

## KI fragen

Die Untersuchungsseite hat einen Assistenten, der Fragen zu Bereich und Fenster der geöffneten Untersuchung beantwortet. Er liest nur diesen Bereich und dieses Fenster, mit einem Einmal-Ticket, das aus der geöffneten Untersuchung erzeugt wird und 15 Minuten einlösbar bleibt. Die Frage und die gelesenen Zeilen gehen an den eigenen KI-Anbieter der Organisation. Der Assistent kann die obigen `rdc`-Befehle unter denselben Berechtigungsregeln ausführen wie jeder andere Befehl.

## Befehle

| Befehl | Zweck |
|---|---|
| `rdc repo flows <ref>` | Netzwerkflüsse eines Repositorys in einem Fenster |
| `rdc repo opens <ref>` | Öffnungen sensibler Dateien eines Repositorys in einem Fenster |
| `rdc forensics level <ref> <level>` | Erfassungsstufe setzen |
| `rdc forensics verify` | Ein Beweisverzeichnis oder einen signierten Bericht verifizieren |
| `rdc incident declare <ref>` | Einen Incident erfassen, das Repository forken und auf Full wechseln |
| `rdc incident status [id]` | Incidents auflisten oder einen mit seinen Fristen anzeigen |
| `rdc incident export <id>` | Das Beweisfenster schreiben, oder mit `--stage` einen signierten Bericht |
| `rdc incident close <id>` | Einen Incident abschließen |
