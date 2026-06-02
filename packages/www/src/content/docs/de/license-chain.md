---
title: "Lizenz-Chain & Delegation"
description: "Manipulationssichere Lizenzausstellung, delegiertes Signieren für On-Premise und Fork-Erkennung."
category: "Guides"
order: 8
language: de
sourceHash: "9b062d6866c1ccb4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Lizenz-Chain & Delegation

Rediacc verwendet eine manipulationssichere Hash-Chain für die Lizenzausstellung und ein Delegierungszertifikat-Modell für On-Premise-Bereitstellungen. Diese Seite erklärt, wie das System gegen Manipulation, Replay-Angriffe und Lizenzfreigabe schützt.

## Warum eine Chain?

Jede von einem Account-Server ausgestellte Lizenz wird in einem Append-Only-Ledger aufgezeichnet. Jeder Eintrag ist über einen SHA-256-Hash mit dem vorherigen verknüpft und bildet eine Kette. Die Chain hat drei Eigenschaften, die Manipulationen erkennbar machen:

1. **Sequenznummern** sind global und monoton pro Abonnement. Das Überspringen oder Neuanordnen von Einträgen unterbricht die Kette.
2. **Chain-Hashes** binden jeden Eintrag an alle vorherigen. Die Änderung eines vergangenen Eintrags macht alle nachfolgenden ungültig.
3. **Renet speichert die höchste gesehene Sequenz** pro Abonnement. Ein Server, der seine Sequenz zurücksetzt, wird sofort erkannt.

## Wie eine Lizenz ausgestellt wird

Wenn die CLI eine Maschinenaktivierung oder Repo-Lizenz anfordert, führt der Account-Server folgende Schritte aus:

1. Den aktuellen Kettenkopf (letzte Sequenz und Hash) für das Abonnement lesen.
2. Den Lizenzpayload mit der nächsten Sequenznummer und dem vorherigen Chain-Hash erstellen.
3. Den Payload mit Ed25519 signieren.
4. `chainHash = SHA256(prevChainHash + ":" + signedPayload)` berechnen.
5. Den Eintrag atomar in das Ausstellungs-Ledger einfügen. Wenn zwei gleichzeitige Anfragen auf dieselbe Sequenz stoßen, erwirbt der Verlierer die nächste Sequenz und signiert erneut.
6. Den signierten Blob mit dem Chain-Hash an die CLI zurückgeben.

`sequence` und `prevChainHash` befinden sich im signierten Payload (können also nicht verändert werden, ohne die Signatur zu entwerten). `chainHash` befindet sich auf dem Envelope (nach dem Signieren berechnet, um eine zirkulare Abhängigkeit zu vermeiden).

## Wie Renet validiert

Jede Maschine mit Renet speichert ihren letzten bekannten Kettenzustand unter `{licenseDir}/chain-state.json`. Bei jeder Lizenzvalidierung prüft Renet:

| Prüfung | Fehler bedeutet |
|---|---|
| Ed25519-Signatur ist gültig | Lizenz wurde gefälscht oder manipuliert |
| `sequence > lastKnownSequence` | Server hat die Kette zurückgesetzt (Replay-Angriff) |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | Chain-Eintrag wurde verändert |
| `issuedAt >= lastKnownIssuedAt` | Uhrenmanipulation (Serveruhr zurückgestellt) |

Schlägt eine Prüfung fehl, wird die Lizenz abgelehnt und der Fehlergrund gemeldet.

## Delegierungszertifikate (On-Premise)

Für Air-Gapped- oder selbst gehostete Bereitstellungen stellt der vorgelagerte Account-Server ein **Delegierungszertifikat** aus, das einen On-Premise-Server autorisiert, Lizenzen mit seinem eigenen Ed25519-Schlüssel zu signieren. Das Zertifikat beschränkt, was der On-Premise-Server tun kann.

### Zertifikatsstruktur

Ein Delegierungszertifikat enthält:

- `subscriptionId` - für welches Abonnement dieses Zertifikat gilt
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` - eingebackene Planlimits
- `maxTotalIssuances` - Obergrenze für die Chain-Sequenznummer
- `delegatedPublicKey` - der Ed25519-Öffentlichschlüssel des On-Premise-Servers (SPKI base64)
- `genesisHash` - der Startpunkt der Kette (Fortsetzung vom vorherigen Zertifikat oder "genesis")
- `genesisSequence` - Chain-Sequenz zum Ausstellungszeitpunkt. Wird von `/onprem/cert-upload` verwendet, um zu prüfen, ob das neue Zertifikat noch mit einem bekannten Eintrag im lokalen Ausstellungs-Ledger verbunden ist, wenn die Kette während des Transits fortgeschritten ist. Optional für Abwärtskompatibilität (wird als 0 behandelt, wenn nicht vorhanden).
- `validFrom`, `validUntil` - Gültigkeitsfenster (durch die Gültigkeitsrichtlinie unten geregelt)
- Signiert vom vorgelagerten Master-Ed25519-Schlüssel

### Wie Delegation funktioniert

1. Enterprise-Admin generiert ein Ed25519-Schlüsselpaar auf dem On-Premise-Server.
2. Admin fordert ein Delegierungszertifikat vom vorgelagerten System an:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. Das vorgelagerte System signiert das Zertifikat mit seinem Master-Schlüssel und gibt es zurück.
4. Der On-Premise-Server speichert das Zertifikat und seinen privaten Schlüssel, bereit zum Signieren von Lizenzen.
5. Wenn eine CLI eine Lizenz vom On-Premise-Server anfordert, signiert der Server mit seinem delegierten Schlüssel und fügt eine Referenz auf das Zertifikat ein.
6. Renet führt eine **zweistufige Validierung** durch:
   - Signatur des Zertifikats gegen den eingebackenen vorgelagerten Master-Schlüssel verifizieren.
   - Signatur des Blobs gegen den delegierten Schlüssel aus dem Zertifikat verifizieren.
   - Prüfen, dass `blob.sequence <= cert.maxTotalIssuances`.
   - Alle Standard-Chain-Prüfungen anwenden.

Der On-Premise-Server kann nicht:
- Eine Lizenz außerhalb der Planlimits des Delegierungszertifikats fälschen (renet lehnt sie ab).
- Mehr als `maxTotalIssuances` Gesamtoperationen ausstellen (renet lehnt Sequenzüberlauf ab).
- Das Zertifikat ändern (die vorgelagerte Signatur bricht).

## Gültigkeitsrichtlinie

Das Gültigkeitsfenster eines Delegierungszertifikats wird von einem gemeinsamen Richtlinien-Helfer (`computeDelegationCertValidity()`) berechnet, der sowohl auf dem vorgelagerten Backend als auch auf dem Kundenportal-Frontend läuft. Dieselben Eingaben erzeugen immer dasselbe `validUntil`, sodass Kunden die effektive Gültigkeit im Erstellungsdialog vorab anzeigen können, bevor sie abschicken.

### Planmäßige Standards und Obergrenzen

| Plan | Standard-Gültigkeit | Plan-Obergrenze |
|---|---|---|
| COMMUNITY | 15 Tage | 30 Tage |
| PROFESSIONAL | 60 Tage | 120 Tage |
| BUSINESS | 90 Tage | 180 Tage |
| ENTERPRISE | 120 Tage | 365 Tage |

Der Standard wird vom Erstellungsendpunkt gewählt, wenn der Aufrufer `validDays` weglässt. Die Obergrenze ist das Maximum, das der Aufrufer anfordern kann.

### Abonnementbezogene Überschreibung

Administratoren können für ein bestimmtes Abonnement einen benutzerdefinierten `delegationCertDefaultDays`-Wert über die Admin-Abonnementdetailseite setzen. **Die Überschreibung ersetzt sowohl den Standard als auch die Obergrenze für dieses Abonnement.** Sie ist ein Sicherheitsventil für Sonderkunden (z. B. ein Enterprise-Vertrag, der ein 200-Tage-Zertifikat auf einem COMMUNITY-Plan benötigt). Das Zod-Schema erzwingt weiterhin einen absoluten Bereich von `1..365`.

### Hartes Limit: Abonnementende + 3 Tage Nachfrist

Unabhängig von der Plan-Obergrenze und der Überschreibung ist jedes Zertifikat auf `subscription.expiresAt + 3 Tage` begrenzt (das bestehende `SUBSCRIPTION_CONFIG.gracePeriodDays`). Das bedeutet:

- Für unbefristete Abonnements (`expiresAt = null`) gilt keine Ablaufobergrenze - nur die Plan-Obergrenze.
- Für monatlich über Stripe abgerechnete Abonnements entspricht die Obergrenze in etwa dem nächsten Abrechnungsdatum + 3 Tage. Wenn Stripe `expiresAt` jeden Monat vorwärts rollt, bewegt sich die Obergrenze entsprechend.
- Für Testabonnements entspricht die Obergrenze dem Testende + 3 Tage.

### Effektive Tage und Grund

Jede Erstell-/Erneuerungsantwort enthält `effectiveDays` und `reason`, sodass der Aufrufer genau erkennen kann, warum das Zertifikat die erhaltene Gültigkeit hat:

| Grund | Bedeutung |
|---|---|
| `plan_default` | Keine Anforderung, keine Überschreibung - planmäßigen Standard verwendet |
| `subscription_override` | Keine Anforderung - abonnementbezogene Überschreibung als Standard verwendet |
| `requested` | Aufruferanforderung innerhalb aller Obergrenzen erfüllt |
| `plan_max_clamp` | Aufruferanforderung überschritt Plan-Obergrenze - nach unten begrenzt |
| `override_max_clamp` | Aufruferanforderung überschritt abonnementbezogene Überschreibung - nach unten begrenzt |
| `subscription_cap_clamp` | Anderweitig gültiges Ziel überdauert `expiresAt + 3 Tage` des Abonnements |

Das Kundenportal-Erstellungsdialog nutzt diese Gründe, um eine Livevorschau anzuzeigen ("Sie erhalten ein 18-Tage-Zertifikat. Begrenzt, weil das Zertifikat das Abonnementende nicht um mehr als 3 Tage überschreiten darf."), damit Kunden nicht blind abschicken.

### Adaptiver Erneuerungsschwellenwert

Die automatische Erneuerungsschleife des On-Premise-Servers verwendet einen adaptiven Schwellenwert, modelliert nach Let's Encrypt:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

Ein 15-tägiges COMMUNITY-Zertifikat wird bei 5 verbleibenden Tagen erneuert. Ein 90-tägiges BUSINESS-Zertifikat wird bei 14 verbleibenden Tagen erneuert (die konfigurierte Obergrenze greift). Ein 120-tägiges ENTERPRISE-Zertifikat wird bei 14 verbleibenden Tagen erneuert. Dies verhindert, dass kurzlebige Zertifikate sofort eine Erneuerung auslösen, während langlebigen Zertifikaten noch ein komfortabler Puffer verbleibt.

## Single-Active-Durchsetzung

Ein Abonnement darf **höchstens ein aktives Delegierungszertifikat gleichzeitig** haben (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Warum nur eines?

Jede On-Premise-Installation erzwingt `maxRepoLicenseIssuancesPerMonth`, `maxActivations` und Kettenintegrität gegen ihr eigenes lokales Ausstellungs-Ledger. Der On-Premise-Server synchronisiert Nutzungszahlen nicht mit dem vorgelagerten System. Das ist der Sinn der offline-fähigen Delegation.

Hätte ein Abonnement mehrere aktive Zertifikate (eines pro Installation), würde jede Installation das Limit unabhängig erzwingen:

- Ein 500/Monat-Abonnement mit 3 aktiven Zertifikaten erlaubt in der Praxis bis zu **1.500 Ausstellungen/Monat**.
- Drei parallele Ketten, jeweils am Genesis verankert, ohne mögliche Prüfsabstimmung.

Das vorgelagerte System kann diese Umgehung nicht erkennen, weil die On-Prem-Server für den Offline-Betrieb konzipiert sind. **Single-Active ist das einzige durchsetzbare Modell.** Multi-Install-Kunden (Produktion, Staging, DR) müssen ein Abonnement pro Installation erwerben.

### Kollisionsverhalten

`POST /admin/delegation-certs` und `POST /portal/delegation-certs` lehnen ein zweites Erstellen ab mit:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

Das Kundenportal zeigt dies mit einem dedizierten Dialog an, der die Konsequenzen erklärt:

- **Erneuern (empfohlen)** - verlängert die vorhandene Kette. Alle zuvor ausgestellten Repo-Lizenzen funktionieren weiterhin.
- **Widerrufen und neu erstellen** - verwirft die vorhandene Kette und beginnt neu bei Genesis. Zuvor ausgestellte Repo-Lizenzen werden unverifizierbar, sobald das `validUntil` des ALTEN Zertifikats abgelaufen ist. Nur verwenden, wenn auf ein neues On-Prem mit einem anderen Signaturschlüssel migriert wurde, oder zur Wiederherstellung nach einem kompromittierten Schlüssel.

`renew()` ist der atomare Tausch, der Single-Active beibehält und **nicht** der 409-Kollisionsprüfung unterliegt.

### Rate-Limit

Selbst mit Single-Active könnte ein bösartiger Aufrufer `revoke -> create -> revoke -> create` in einer Schleife ausführen, um Master-Key-Signaturzyklen zu verbrennen. Beide Erstellungsendpunkte begrenzen auf **10 Versuche pro rollenden 24 Stunden** pro Abonnement über die bestehende `rateLimits`-Tabelle:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

Der Zähler wird bei jedem Versuch unabhängig vom Ergebnis erhöht (auch Kollisions-Spam-Schleifen werden begrenzt).

## Fork-Erkennung

Wenn ein Kunde sein Delegierungszertifikat mit einer anderen Partei teilt (oder zwei On-Premise-Server mit demselben Zertifikat betreibt), divergieren die Ketten. Das vorgelagerte System erkennt dies zum Erneuerungszeitpunkt.

### Erneuerungsablauf

1. On-Premise-Admin ruft `POST /admin/delegation-certs/renew` mit dem aktuellen Kettenkopf auf:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. Das vorgelagerte System durchläuft die Ketteneinträge gegen seinen eigenen Ledger-Datensatz.
3. Wenn `currentChainHash` nicht mit dem aufgezeichneten Kettenstand des vorgelagerten Systems bei `currentSequence` übereinstimmt, wird ein Fork erkannt:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. `genesisHash` des neuen Zertifikats wird auf den aktuellen Chain-Hash gesetzt, sodass Maschinen mit dem alten Kettenzustand von dort weitermachen können, wo sie aufgehört haben.

Wenn das Zertifikat mit einem Nicht-Kunden geteilt wird:
- Er kann es während der Gültigkeitsdauer des Zertifikats verwenden.
- Bei der ersten Erneuerung sieht das vorgelagerte System nur eine Kette (die legitime).
- `genesisHash` des neuen Zertifikats stimmt nur mit der legitimen Kette überein.
- Maschinen auf der geteilten Kette lehnen neue Lizenzen sofort ab, weil ihr gespeicherter `chainHash` nicht mit `genesisHash` des neuen Zertifikats verbunden ist.

## Air-Gapped-Erneuerung

Für On-Premise-Installationen ohne ausgehenden HTTPS-Zugriff auf das vorgelagerte System ist der Erneuerungsablauf vollständig offline. Drei neue Endpunkte schließen den Kreislauf:

**Auf dem On-Premise-Server (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - das aktuell geladene signierte Zertifikat herunterladen (Backup, Audit, Reimport)
- `GET /onprem/renewal-request` - ein signiertes Manifest generieren, das den lokalen Kettenkopf und den delegierten öffentlichen Schlüssel enthält, signiert mit dem privaten On-Premise-Schlüssel

**Auf dem vorgelagerten System (Admin oder org-bezogenes Portal):**
- `POST /admin/delegation-certs/process-renewal-request` (systemübergreifendes Systemroot)
- `POST /portal/delegation-certs/process-renewal-request` (Org-Owner/Admin)

### Erneuerungsanforderungs-Manifest

Die Erneuerungsanforderung ist ein kleines JSON-Dokument:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

Die Signatur wird über die kanonische Kodierung des Manifests berechnet (Schlüssel alphabetisch sortiert, dann `JSON.stringify`) unter Verwendung des privaten On-Premise-Schlüssels. Dies stellt sicher, dass beide Seiten identische Bytes berechnen, unabhängig von der Objektkonstruktionsreihenfolge.

### Verifizierung beim vorgelagerten System

`processRenewalManifest()` führt fünf Prüfungen durch:

1. **Aktives Zertifikat vorhanden** für das Abonnement des Manifests. Gibt andernfalls `404 NO_ACTIVE_CERT` zurück - der Kunde sollte den Erstellungsablauf verwenden, nicht erneuern.
2. **Delegierter öffentlicher Schlüssel stimmt überein** mit dem aktiven Zertifikat. Gibt andernfalls `400 DELEGATED_KEY_MISMATCH` zurück - schützt vor Replay von einem anderen On-Prem.
3. **Manifest-Signatur verifiziert** gegen `delegatedPublicKey` des aktiven Zertifikats. Gibt andernfalls `400 MANIFEST_SIGNATURE_INVALID` zurück - beweist, dass das Manifest von einem Inhaber des privaten On-Premise-Schlüssels stammt.
4. **Manifestalter** liegt innerhalb von 7 Tagen (`RENEWAL_MANIFEST_MAX_AGE_MS`). Gibt andernfalls `400 MANIFEST_EXPIRED` zurück - Anti-Replay-Anker.
5. **Chain-Hash-Verbindung** bei `currentSequence` des Manifests stimmt mit dem Ledger des vorgelagerten Systems überein. Gibt andernfalls `409 CHAIN_FORK_DETECTED` zurück - schützt vor abgezweigten Ketten.

Wenn alle Prüfungen bestanden sind, ruft `processRenewalManifest` den bestehenden `renew()`-Ablauf auf, der das alte Zertifikat atomar ablaufen lässt und ein neues einfügt. **Er unterliegt nicht der erstellungsseitigen Single-Active-409**, weil es ein atomarer Tausch ist, kein 2-Schritt-Widerrufen+Erstellen.

### Sequenzfortschritt während des Transits

Ein Erneuerungsanforderungs-Manifest erfasst den Kettenkopf zum Generierungszeitpunkt. Während das Manifest in Transit ist (USB-Lieferung, verschlüsselte E-Mail), kann der On-Premise-Server weiterhin Repo-Lizenzen ausstellen und seine lokale Kette fortschreiben.

Wenn das neue Zertifikat zurück auf den On-Premise-Server hochgeladen wird, prüft `/onprem/cert-upload`, ob `genesisSequence` des neuen Zertifikats noch mit einem bekannten Eintrag im lokalen Ausstellungs-Ledger verbunden ist:

- Wenn `cert.genesisSequence > localHead.sequence` - gibt `409 CHAIN_HEAD_BEHIND` zurück (vorgelagertes System befindet sich auf einer abgezweigten Kette).
- Wenn `cert.genesisSequence > 0` und der lokale Ledger-Eintrag an dieser Sequenz einen anderen `chainHash` als `cert.genesisHash` hat - gibt `409 CHAIN_FORK_ON_UPLOAD` zurück (lokale Kette hat sich abgezweigt).
- Andernfalls wird das Zertifikat akzeptiert. Zukünftige Ausstellungen setzen bei `localHead.sequence + 1` fort.

Das bedeutet, **während des Transits ist kein Schreibstopp erforderlich**. Die Kette verlängert sich auf beiden Seiten natürlich. Entspricht der Handhabung von In-Flight-Seriennummern bei der X.509-Zertifikatserneuerung.

## Periodisches Audit

Das vorgelagerte System stellt einen Audit-Endpunkt zur Verifizierung der Kettenintegrität bereit, ohne das Zertifikat zu erneuern:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

Das vorgelagerte System durchläuft die Einträge und gibt entweder `{ valid: true }` oder `{ valid: false, divergedAtSequence: N, expected, actual }` zurück.

On-Premise-Server sollten diesen Endpunkt regelmäßig aufrufen (Standard: wöchentlich über die Umgebungsvariable `UPSTREAM_AUDIT_URL`), um Forks frühzeitig zu erkennen.

### Maschinenseitige Audit-Beweise

Renet kann die Kettenkontinuität lokal mit `VerifyAuditProof` verifizieren. Wenn eine Maschine ihre Lizenz nach einer langen Pause erneuert, kann der Server die Zwischen-Chain-Einträge als Beweis zurückgeben. Die Maschine durchläuft den Beweis, um zu verifizieren, dass jeder `chainHash` aus dem vorherigen `prevHash + blobHash` via SHA-256 abgeleitet wird, und erkennt so jede Manipulation, ohne das vorgelagerte System zu kontaktieren.

## Nebenläufigkeitssicherheit

D1 (Cloudflares Datenbank) unterstützt keine interaktiven Transaktionen. Gleichzeitige Lizenzausstellung für dasselbe Abonnement könnte auf der Sequenznummer kollidieren. Der Account-Server behandelt dies wie folgt:

1. Nächste Sequenz und vorherigen Chain-Hash lesen.
2. Blob mit dieser Sequenz eingebaut erstellen und signieren.
3. Den Ledger-Eintrag mit `onConflictDoNothing` einfügen.
4. Wenn der Einfügevorgang 0 geänderte Zeilen zurückgibt, wurde die Sequenz von einer anderen Anfrage beansprucht - Sequenz erneut erwerben, neu erstellen, **erneut signieren** und wiederholen.
5. Nach 10 fehlgeschlagenen Versuchen mit einem Fehler abbrechen.

Das kritische Detail: Der Wiederholungsversuch **signiert den Blob neu**. Ein naiver Wiederholungsversuch, der nur den Ledger-Eintrag aktualisierte, würde den signierten Blob mit einer veralteten Sequenznummer hinterlassen und die Kette unterbrechen.

## E-Mail-Transport

Der Account-Server kann transaktionale E-Mails (Magic-Links, Passwortzurücksetzungen, Sicherheitsbenachrichtigungen) über zwei austauschbare Transporte senden:

| Transport | Konfiguration |
|---|---|
| `ses` (Standard) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Beide Transporte funktionieren für Cloud- und On-Premise-Bereitstellungen. Es wird derjenige gewählt, der zur eigenen Infrastruktur passt: AWS SES mit eigenem AWS-Konto oder ein beliebiger SMTP-Server (Microsoft Exchange, Postfix, SendGrid, Mailgun usw.).

Der Transport wird beim Start über die Umgebungsvariable `EMAIL_TRANSPORT` ausgewählt. SMTP verwendet Connection-Pooling und Lazy-Loading, sodass die SMTP-Client-Bibliothek nur initialisiert wird, wenn SMTP ausgewählt ist.

Alle E-Mail-Templates und die öffentliche E-Mail-API sind über alle Transporte hinweg identisch.

## Weitergehende Dokumentation

- [On-Premise-Installation](/de/docs/on-premise) - Bereitstellung des On-Premise-Servers
- [Abonnement & Lizenzierung](/de/docs/subscription-licensing) - Planlimits und Maschinenplätze
- [Release-Kanäle](/de/docs/release-channels) - Edge vs. Stable
- [Datenregionen](/de/docs/data-regions) - Regionale Datenhaltung
