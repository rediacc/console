---
title: "Forensik: Beweise aus einem kompromittierten Repository"
description: "Netzwerkflüsse und Öffnungen sensibler Dateien pro Repository, in einer vom Kunden gewählten Detailtiefe, alle 30 Sekunden als signierte, verkettete Batches ausgeliefert. Behandelt die drei Erfassungsstufen, den Spike-Trigger, Tarifkontingente, Offline- und Server-Erkennung und was der Server lesen kann."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: de
sourceHash: "cb8be2dcf3970c81"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Forensik

Die Forensik beantwortet zwei Fragen für den Fall, dass Software in einem Repository kompromittiert wurde: Wann wurden Daten abgezogen, und welche. Rediacc kann eine Lücke in Software von Drittanbietern nicht schließen, deshalb zeichnet die Funktion Beweise auf, die eine Kompromittierung überstehen. Die Aufzeichnungen schreibt ein Collector mit Root-Rechten auf der Maschine, außerhalb der Repository-Sandbox. Sie landen in einem Bucket, den die Administratoren des Kunden nicht erreichen.

Die Aufzeichnungen zeigen Volumen, Ziel und Zeitpunkt. Flow-Datensätze belegen Volumen und Ziel, nicht den Inhalt. Der [Incident-Workflow](/de/docs/incident-response) liest sie aus, und [Incident-Berichte](/de/docs/incident-reports) machen daraus signierte Dokumente für eine Aufsichtsbehörde.

## Was aufgezeichnet wird

Die Erfassung gilt pro Repository. Repositories nutzen das Host-Netzwerk, daher wird der Verkehr über cgroup (die eigene Slice des Repositorys) zugeordnet, nie über die IP-Adresse.

| Datensatz | Inhalt |
|---|---|
| Netzwerkfluss | Zeit, Prozess, Zieladresse und Port, Protokoll, gesendete und empfangene Bytes, DNS-Name falls bekannt, sowie ASN und Land des Ziels falls bekannt |
| Dateiöffnung | Zeit, Prozess und Pfad, für einen Pfad, der zur Liste sensibler Pfade passt |
| Heartbeat | Eine signierte Markierung in jedem Batch, sodass ein gestoppter Collector als Lücke sichtbar wird und nicht als Stille |

Die Standardliste sensibler Pfade umfasst `.env`-Dateien, Schlüssel- und Zertifikatsdateien (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), Passwortdatenbanken (`*.kdbx`), Datenbank-Dumps und -Dateien (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) und Datenverzeichnisse von Datenbanken wie `pgdata`. Ein Repository kann die Liste erweitern oder durch eigene Muster ersetzen.

Paketinhalte und Dateiinhalte werden nie aufgezeichnet.

## Erfassungsstufen

Jedes Repository hat genau eine Stufe, standardmäßig die kleinste. Eine höhere Stufe zeichnet alles auf, was die niedrigere aufzeichnet.

| Stufe | Aufgezeichnet |
|---|---|
| `basic` | Alle 5 Minuten eine Zusammenfassung pro Ziel, Port und Protokoll, mit Bytes rein und raus |
| `standard` | Jede Minute ein Flow-Datensatz, mit Prozess und DNS-Name |
| `full` | Standard, plus Dateiöffnungen auf sensiblen Pfaden |

Die Stufe wird pro Repository gesetzt:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

Der Collector begrenzt die Stufe auf das, was der Tarif enthält. Hat ein Tarif kein Forensik-Kontingent, zeichnet das Repository nichts auf.

### Der Spike-Trigger

Jede Stufe schaltet einen Trigger scharf. Steigen die ausgehenden Bytes eines Repositorys in einer Minute über das Zehnfache seines eigenen gleitenden Durchschnitts (und über 50 MiB pro Minute), nachdem das Repository 24 Stunden beobachtet wurde, wechselt es für 24 Stunden auf Full. Eine auslösende Minute fließt nicht in den Durchschnitt ein, sodass ein einzelner Datenabfluss nicht die Baseline anheben kann, die den nächsten erkennen soll.

## Tarife und Kontingente

Die Forensik gehört zu den kostenpflichtigen Tarifen und zeichnet nur auf, solange der Tarif bezahlt ist. Ein Upgrade beginnt ohne Historie.

| Tarif | Forensik-Kontingent |
|---|---|
| Free, Community | 0 (nichts wird aufgezeichnet) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, oder ein individuelles Kontingent, das Rediacc-Administratoren festlegen |

Das Kontingent entspricht einem Viertel des Backup-Kontingents des Tarifs und wird getrennt vom Backup abgerechnet. Mehr Kontingent gibt es nur über ein Tarif-Upgrade.

Ist das Kontingent voll, werden zuerst die ältesten Datensätze verdrängt (FIFO). Die neuesten 7 Tage sind gesperrt und werden nie verdrängt, weil der Bucket sie 7 Tage lang sperrt. Würden allein die gesperrten Bytes das Kontingent überschreiten, werden neue Batches abgelehnt. Passt die erwartete Aufnahme von 7 Tagen nicht mehr hinein, wird die Stufe auf Basic begrenzt. Inhaber und Admins erhalten eine Benachrichtigung bei 80 Prozent des Kontingents, wenn die Begrenzung auf Basic greift und wenn ein Batch abgelehnt wird.

Datensätze innerhalb eines deklarierten Incidents sind von der Verdrängung ausgenommen, bis 30 Tage nach dem Abschluss des Incidents vergangen sind. Siehe [Incident Response](/de/docs/incident-response).

## Auslieferung und Integrität

Der Collector schneidet alle 30 Sekunden einen Batch ab. Jeder Batch wird mit dem Spool-Schlüssel der Maschine signiert und enthält den Hash des vorherigen Batches, sodass ein entfernter oder veränderter Batch die Kette bricht. Die Uploads laufen über Presigned-URLs, die nur das Anlegen erlauben und aus dem Lizenz-Blob der Maschine erzeugt werden. Die Maschine kann also Datensätze hinzufügen, aber nicht überschreiben oder löschen. Bei Verbindungsverlust warten die Batches in einem lokalen, signierten Spool und werden ausgeliefert, sobald die Verbindung wieder steht.

Die nächtliche Kompaktierung fasst die Batches zu einer Tagesdatei pro Repository und einer Header-Datei pro Maschine zusammen, in der jeder signierte Header aufgeführt und jede Lücke markiert ist. Die Audit-Tagesdateien des Kontos werden auf dieselbe Weise verkettet, pro Organisation und Tag.

`rdc forensics verify` und die Schaltfläche „Verify evidence“ der Untersuchungsseite berechnen diese Ketten neu. Siehe [Incident Response](/de/docs/incident-response).

## Erkennung

Die Anomalieerkennung läuft zweimal. Ein statistischer Detektor auf der Maschine reagiert sofort und schaltet das Repository auf Full. Der Server betreibt beim Eingang eigene Detektoren, sodass die Erkennung auch bei einem kompromittierten Host funktioniert. Pro Logeintrag läuft keine KI.

Die Detektoren sind geschichtet, und jedes Repository lernt aus seinem eigenen Verkehr:

| Detektor | Sucht nach |
|---|---|
| Baselines nach Stunde der Woche | Bytes, Verbindungen, verschiedenen Zielen, neuen DNS-Namen und neuen Prozessen außerhalb des üblichen Rhythmus des Repositorys für diese Stunde der Woche |
| Half-Space Trees | Einem Flow, der den bisher gesehenen Flows nicht ähnelt |
| ECOD und HBOS | Flow-Batches, die als Ausreißer bewertet werden, mit den Merkmalen, die die Bewertung bestimmt haben |
| Erstmals gesehen | Einem Prozess, der eine sensible Datei öffnet, die er zuvor nie geöffnet hat |

Jeder Befund trägt die Gründe pro Merkmal, die ihn ausgelöst haben, und die Erklärung ist eine aus diesen Gründen gebaute Vorlage. Offline gibt es kein Sprachmodell. Ein Befund wird zu einer Kontobenachrichtigung und einer E-Mail an Inhaber, Admins und den Sicherheitskontakt. Ist die Maschine offline, handelt sie sofort lokal (Full-Erfassung und ein Eintrag in ihrem signierten Spool) und liefert den Alarm nach, sobald die Verbindung wieder steht, mit dem ursprünglichen Erkennungszeitpunkt.

### Modellpakete

Die Detektorparameter werden als signierte Pakete unter `data.rediacc.com/models/` verteilt und vom Publish-Job hochgeladen (dort ist noch kein Kanal veröffentlicht): inhaltsadressierte Dateien, ein Manifest, signiert mit einem Offline-Ed25519-Modellschlüssel, der in renet eingebaut ist, eine Mindestversion von renet und eine Version, die nur steigt, sodass ein Downgrade abgelehnt wird. Ein Paket wird vor der Installation geprüft, und das vorherige lässt sich wiederherstellen.

```bash
renet models status
renet models update
renet models rollback
```

Air-Gapped-Installationen erhalten dasselbe signierte Paket innerhalb von `rdc server bundle`, außer wenn `--no-models` übergeben wird.

## Was der Server lesen kann

Der Account-Server liest die Aufzeichnungen, weil Zeitleiste, Verifikation und Server-Detektoren sie brauchen: Ziele, Ports, Prozessnamen, DNS-Namen, Byte-Zähler und Pfade sensibler Dateien. Paketinhalte und Dateiinhalte erhält er nicht.

Eine eingehende Client-Adresse wird in den Aufzeichnungen gekürzt gespeichert (auf /24 bei IPv4 und /48 bei IPv6), und die vollständige Adresse liegt in einem separaten Abschnitt, der nach 30 Tagen gelöscht wird. Der Hash des gelöschten Abschnitts bleibt im signierten Header, sodass die Kette weiterhin verifiziert und der Verifizierer die Adresse als geschwärzt meldet. Ausgehende Ziele bleiben vollständig, weil sie der Beweis sind.

Kunden öffnen die Aufzeichnungen über eine Untersuchung, die einen bezahlten Tarif, die Rolle Inhaber oder Admin und eine aktuelle erneute Authentifizierung voraussetzt, und jede Ansicht wird auditiert. Rediacc-Support sieht Forensikdaten nur mit einer zeitlich begrenzten Freigabe, die der Kunde erteilt. Die Verarbeitungsbedingungen stehen in der [Auftragsverarbeitungsvereinbarung](/de/data-processing-agreement).
