---
title: "Backup-Ziele"
description: "Schicken Sie jede Backup-Strategie an mehr als einen Store, stellen Sie aus dem Store mit dem besten Snapshot wieder her und lesen Sie eine Statuszeile pro Ziel."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: de
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Backup-Ziele

Eine Backup-Strategie kann in mehr als einen Store schreiben. Jedes Ziel ist ein eigener Wiederherstellungspunkt: Es bekommt seinen eigenen Snapshot, seinen eigenen Commit und seine eigene Statuszeile, sodass ein ausfallender Store keinen anderen beeinträchtigt.

Alle Stores gehören zu einem Account. Eine Config, eine Lizenz und eine Rechnung decken sie ab. Eine Maschine, die an zwei Accounts angemeldet ist, wird weiterhin abgewiesen, denn mehrere Ziele bedeuten mehrere Stores innerhalb eines Accounts.

## Stores

Ein Store ist ein Bucket, in das der Account-Server im Auftrag der Maschine schreibt. Jedes Abonnement hat von Anfang an einen, namens `home`: den gehosteten Store, den die Backup-Befehle schon immer verwendet haben. Ein Ziel ohne Store-Angabe schreibt nach `home`.

Daneben lassen sich zwei Arten registrieren.

| Art | Was es ist | Was die Registrierung braucht |
|-----|------------|-------------------------------|
| `hosted-r2` | Eine zweite gehostete Region, gewählt aus den Regionen, die das Deployment anbietet | Eine ID und die Region. Keine Zugangsdaten |
| `customer-s3` | Ein Bucket, den der Kunde selbst betreibt, auf S3, RustFS oder einem anderen S3-kompatiblen Dienst | Eine ID, der HTTPS-Endpunkt, der Bucket, die Signaturregion (Standard `us-east-1`), optional ein öffentlicher Endpunkt und ein Zugriffsschlüsselpaar |

Eine Maschine hält nie die Schlüssel eines Kunden-Buckets. Die Schlüssel liegen versiegelt auf dem Account-Server, und die Maschine erhält kurzlebige vorsignierte URLs für den einen Store, den ihre Sitzung benennt.

### Einen Store registrieren

Die Registrierung ist ein Aufruf der Account-API, kein `rdc`-Befehl. `POST /backups/stores` registriert einen Store, `GET /backups/stores` listet die registrierten auf, und `DELETE /backups/stores/<id>` nimmt einen außer Dienst. Registrieren, Rotieren und Außerdienststellen erfordern ein API-Token mit dem Scope `backup:manage`, das von einem aktuellen Owner oder Admin der Organisation erstellt wurde, und jede dieser Aktionen wird protokolliert. Das Auflisten braucht `backup:read`.

Der Server prüft einen Store, bevor er ihn annimmt.

- **Konformitätsprüfung.** Der Server führt dieselben Prüfungen aus, die ein gehosteter Store besteht. Ein Store, der keine Prüfsummen durchsetzt, wird bei der Registrierung abgewiesen, statt erst beim ersten Backup aufzufallen.
- **Löschprüfung.** Die Prüfung versucht auch ein Löschen. Verweigert der Store es, wird er mit deaktivierter Bereinigung registriert (siehe unten).
- **Endpunktregeln.** Nur HTTPS, Port 443 und kein Endpunkt in einem internen Netz.
- **Store-Limit.** Die Zahl der Stores pro Abonnement hängt vom Tarif ab, `home` eingeschlossen, außer Dienst gestellte Stores nicht mitgezählt.

| Tarif | Stores |
|-------|--------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Wer eine bereits vorhandene ID registriert, rotiert nur deren Zugangsdaten, und die Prüfung läuft erneut. Ein Store, dessen Zugangsdaten nicht mehr funktionieren, wird durch die erste abgelehnte Freigabe als gesperrt markiert. `GET /backups/stores` zeigt Endpunkt, Bucket und die letzten Zeichen der Schlüssel-ID, nie ein Secret.

Ein Store lässt sich nicht außer Dienst stellen, solange ein aktiviertes Ziel ihn noch nennt, und `home` lässt sich nie außer Dienst stellen.

## Den Store eines Ziels benennen

Ein Ziel benennt seinen Store mit `--target`, zusammen mit `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Option | Beschreibung |
|--------|--------------|
| `--destination <name>` | Das Ziel, das angelegt oder geändert wird |
| `--target <storeId>` | ID des registrierten Stores, in den das Ziel schreibt (Standard `home`). Erfordert `--destination` |

Zwei aktivierte Ziele einer Strategie dürfen nicht denselben Store nennen, und ein nicht registrierter Store wird mit der Liste der registrierten IDs abgewiesen.

Jeder geplante Lauf erstellt einen Snapshot pro aktiviertem Ziel, in der Reihenfolge, in der die Ziele deklariert wurden, jeweils mit eigener Bandbreitenbegrenzung. Jeder Snapshot ist ein frischer Copy-on-Write-Reflink und damit ein in sich konsistenter Zeitpunkt. Ein fehlgeschlagenes Ziel überspringt das nächste nicht. Die Unit endet trotzdem mit einem Fehlercode, wenn ein Ziel fehlgeschlagen ist, sodass systemd und die Prüfung auf verpasste Läufe den Fehler sehen.

## Aus einem Store wiederherstellen

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` und `rdc backup download --store` akzeptieren `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Ohne `--from` fragt die CLI den Account-Server, welche Stores die Lineage des Repositorys halten. Die Rangfolge stellt den Store zuerst, dessen neuester Snapshot die letzte Verifizierung bestanden hat, und die CLI probiert die Stores in dieser Reihenfolge. Ein Store ohne Snapshot wird übersprungen. Lässt sich die Rangfolge nicht lesen, verwendet die Wiederherstellung `home` und sagt das.

Ohne `--from` starten `backup restore`, `restore --path`, `browse --at` und `download --store` beim ersten Store dieser Rangfolge und weichen auf den nächsten Store aus, wenn der Fehler beim Store liegt: ein Serverfehler, eine abgelehnte Freigabe oder Sitzung oder ein Endpunkt, der nicht antwortet. Jeder Befehl nennt den Store, der ihn bedient hat. Keiner weicht bei einem Fehler des Snapshots selbst aus. Ein fehlender, abgelaufener oder beschädigter Snapshot sieht in jedem Store gleich aus, daher wird der Fehler angezeigt. Ein Befehl mit `--from` liest nur diesen Store und weicht nie aus.

Eine Snapshot-ID ohne `--from` wird in allen Stores der Lineage gesucht.

## Status pro Ziel

`rdc backup status` gibt neben der Zeitplantabelle eine Zeile pro Ziel aus:

| Spalte | Bedeutung |
|--------|-----------|
| Store | Die ID des Stores, in den das Ziel schreibt |
| Last run | Wann der letzte Lauf für diesen Store endete |
| Result | Das Ergebnis dieses Laufs |
| Newest snapshot | Der jüngste Snapshot, den der Store hält |
| Verify | Das Ergebnis der letzten Verifizierung des Stores |
| Clean-up | `enabled`, oder deaktiviert mit Begründung |

Ein Store, über den der Account nichts melden kann, zeigt `-` in seinen Spalten. Die Prüfung auf verpasste Läufe läuft pro Store, sodass ein Store, der keine Backups mehr erhält, seinen eigenen Alarm auslöst, während die anderen grün bleiben.

## Was auf die Quote angerechnet wird

Gehostete Stores, `home` und jede zweite Region, werden nach physisch gespeicherten eindeutigen Bytes gemessen, und ihre Bytes zählen auf dieselbe Tarifquote. `rdc backup usage` zeigt sie.

Die Bytes eines Kunden-Buckets speichert Rediacc nicht, und sie zählen nicht auf die Quote. Die Metadaten, die der Account dafür führt (Manifestzeilen, Verifizierungsläufe und Indexobjekte), werden wie bei einem gehosteten Store gemessen.

## Stores mit deaktivierter Bereinigung

Ein Store, dessen Löschen verweigert wird, behält jedes Objekt. Aufbewahrung und Garbage Collection löschen nie daraus. Läuft ein Snapshot ab, markiert der Sweep ihn im Account als abgelaufen, bietet ihn nicht mehr zur Wiederherstellung an und lässt seine Objekte im Bucket.

`rdc backup status` und die Backup-Gesundheitsübersicht melden den Store als Bereinigung deaktiviert. Der Bucket wächst weiter, bis Löschzugangsdaten hinzukommen, indem dieselbe ID erneut mit Schlüsseln registriert wird, die löschen dürfen.
