---
title: "Lizenz-Chain & Delegation"
description: "Manipulationssichere Lizenzausstellung, delegiertes Signieren für On-Premise und Fork-Erkennung."
category: "Guides"
order: 8
language: de
sourceHash: "6486263bfb9ebf98"
sourceCommit: "fc24769cfd0684622952395c5bafe44e6180530d"
---

# Lizenz-Chain & Delegation

Rediacc verwendet eine manipulationssichere Hash-Chain für die Lizenzausstellung und ein Delegierungszertifikat-Modell für On-Premise-Bereitstellungen. Diese Seite erklärt, wie das System gegen Manipulation, Replay-Angriffe und Lizenzfreigabe schützt.

## Warum eine Chain?

Jede von einem Account-Server ausgestellte Lizenz wird in einem Append-Only-Ledger aufgezeichnet. Jeder Eintrag ist über einen SHA-256-Hash mit dem vorherigen verknüpft und bildet eine Kette. Die Chain hat drei Eigenschaften, die Manipulationen erkennbar machen:

1. **Sequenznummern** sind global und monoton pro Abonnement. Das Überspringen oder Neuanordnen von Einträgen unterbricht die Kette.
2. **Chain-Hashes** binden jeden Eintrag an alle vorherigen. Die Änderung eines vergangenen Eintrags macht alle nachfolgenden ungültig.
3. **Renet speichert die höchste gesehene Sequenz** pro Signierschlüssel und Abonnement. Ein Server, der seine Sequenz zurücksetzt, wird sofort erkannt.

## Wie eine Lizenz ausgestellt wird

Wenn die CLI eine Maschinenaktivierung oder Repo-Lizenz anfordert, führt der Account-Server folgende Schritte aus:

1. Den aktuellen Kettenkopf (letzte Sequenz und Hash) für das Abonnement lesen.
2. Den Lizenzpayload mit der nächsten Sequenznummer und dem vorherigen Chain-Hash erstellen.
3. Den Payload mit Ed25519 signieren.
4. `chainHash = SHA256(prevChainHash + ":" + signedPayload)` berechnen.
5. Den Eintrag atomar in das Ausstellungs-Ledger einfügen. Wenn zwei gleichzeitige Anfragen auf dieselbe Sequenz stoßen, erwirbt der Verlierer die nächste Sequenz und signiert erneut.
6. Den signierten Blob mit dem Chain-Hash an die CLI zurückgeben.

`sequence` und `prevChainHash` befinden sich im signierten Payload (können also nicht verändert werden, ohne die Signatur zu entwerten). `chainHash` befindet sich auf dem Envelope (nach dem Signieren berechnet, um eine zirkulare Abhängigkeit zu vermeiden).

## Wie eine Lizenz erneuert wird

Die Ausstellung läuft von Ihrer Workstation aus, authentifiziert als Sie. Die Erneuerung läuft von der Maschine aus, die überhaupt keine Account-Zugangsdaten hält. Sie braucht eine andere Tür:

```
POST /licenses/renew
{ license: <der installierte signierte Blob>, machineId, clusterId? }
```

**Die vorgelegte Lizenz ist der Berechtigungsnachweis.** An diesem Endpunkt gibt es kein API-Token. Der Server prüft die Ed25519-Signatur des Blobs, und über das Delegierungszertifikat, wenn der Blob eines mitbringt, genau so, wie Renet es auf der Maschine tut. Eine gültig signierte Lizenz für ein Repository zu besitzen ist der Nachweis der Berechtigung, und eine Maschine, die eine hat, hat sie bereits einmal zugesprochen bekommen.

Die vollständige URL dieses Endpunkts reist als `renewalUrl` in jeder Lizenz mit, die der Server ausstellt oder erneuert. Eine Maschine liest die Adresse ihres eigenen Account-Servers aus ihrer eigenen Lizenz, statt damit konfiguriert zu werden, und genau das erlaubt es einer Maschine, die zwei Account-Universen bedient, gegen beide zu erneuern.

Der erneuerte Blob behält die Repository-GUID, die Grand-GUID und die Art des vorgelegten Blobs, nimmt die nächste Sequenz aus demselben Ledger mitsamt dem daraus folgenden Chain-Hash und erhält frisch berechnete Gültigkeitsfenster. Die Maschinen-ID wird neu an die Maschine gebunden, die den Blob vorgelegt hat, und so heilt sich eine VM-Migration innerhalb der 40-Tage-Kulanzfrist von selbst. Die Speicheridentität (die LUKS-UUID oder der Speicherfingerabdruck) wird unverändert übernommen, denn ein Netzwerkaufruf kann die Festplatte, die er beschreibt, nicht neu einlesen.

### Ablehnungen

| Code | Status | Bedeutung |
|---|---|---|
| `INVALID_LICENSE_SIGNATURE` | 403 | Die Signatur des Blobs ließ sich nicht verifizieren, oder sein Chain-Hash passt bei dieser Sequenz nicht zum Ledger des Servers |
| `INVALID_LICENSE_PAYLOAD` | 400 | Der Blob ist fehlerhaft aufgebaut |
| `DELEGATION_CERT_INVALID` | 403 | Das beigefügte Zertifikat hat eine Beschränkung oder seine Master-Key-Signatur nicht erfüllt |
| `DELEGATION_CERT_EXPIRED` | 403 | Das beigefügte Zertifikat liegt außerhalb seines Gültigkeitsfensters |
| `DELEGATION_CERT_REVOKED` | 403 | Das beigefügte Zertifikat wurde vorgelagert widerrufen |
| `LICENSE_IDENTITY_MISMATCH` | 403 | Die vorlegende Maschine ist nicht die lizenzierte, und die 40-Tage-Kulanzfrist ist vorbei |
| `SUBSCRIPTION_LAPSED` | 403 | Das Abonnement ist abgelaufen oder ausgesetzt |
| `GRACE_PERIOD_ENDED` | 403 | Die Kulanzfrist des Abonnements ist vorüber |
| `TRIAL_REQUIRED` | 403 | Das Abonnement braucht eine aktive Testphase oder einen aktiven Plan |
| `REPO_GUID_OWNERSHIP_CONFLICT` | 403 | Die Repository-GUID gehört zu einem anderen Abonnement |
| `LICENSE_RENEWAL_FAILED` | 500 | Alles, was sich nicht einordnen lässt |

Eine Ablehnung lässt die installierte Lizenz unangetastet. Die Maschine läuft mit dem weiter, was sie hat, bis diese Lizenz hart abläuft.

### Erneuerung und der Maschinenplatz

Eine erfolgreiche Erneuerung rührt an die Aktivierungszeile der Maschine: Sie beansprucht einen Platz, wenn die Maschine keinen hatte, und frischt ihn auf, wenn sie einen hatte. Anders als die Ausstellung wird sie nie wegen Überschreitung des Limits abgelehnt. Die Antwort führt `overLimit` mit, und die Aktivierung wird markiert, damit das Portal, der License-Status-Endpunkt und `rdc subscription status` es anzeigen können. Eine wirklich neue Lizenz auszustellen blockiert weiterhin hart an der Obergrenze. Die Begründung steht unter [Abonnement & Lizenzierung - Maschinenplätze](/de/docs/subscription-licensing).

### Reihenfolge beim Ausrollen

Account-Server werden vor den CLI- und Renet-Agent-Builds ausgerollt, die auf die oben genannten Felder angewiesen sind. Ein Renet Agent, der in einer Lizenz keine `renewalUrl` findet, überspringt dieses Repository und sagt das auch, statt fehlzuschlagen. Eine ältere Lizenz funktioniert also weiter, bis eine Aktualisierung von der Workstation aus das Feld nachträgt. In der umgekehrten Reihenfolge bekommen Sie Maschinen, die nach einem Endpunkt fragen, den es noch nicht gibt.

## Wie Renet validiert

Jede Maschine mit Renet speichert ihren letzten bekannten Kettenzustand unter `{licenseDir}/chain-state.json` (also `/var/lib/rediacc/license/chain-state.json`, ein Geschwisterverzeichnis des Pro-Repo-Verzeichnisses `repos/`). Der Kettenzustand ist pro Signierschlüssel, Abonnement, Repository und Datastore abgegrenzt, mit dem Schlüssel `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` (der Datastore-Anteil bleibt leer für ein Repository auf dem Standard-Datastore der Maschine).

Der Repository- und der Datastore-Anteil dieses Schlüssels sind tragend. Sequenznummern sind auf dem Server pro Abonnement vergeben. Auf einer Maschine mit mehreren Repositories unter einem Abonnement läge ein für Repository B festgehaltener Kettenkopf also vor der Lizenz, die Repository A gerade vorlegen will, und Repository A würde als Replay abgelehnt, mit dem es nichts zu tun hat. Ein Datastore-Fork verschärft dasselbe Problem: Der Klon behält die GUID des Repositories, nur seine Datastore-Identität wird neu vergeben. Ohne den Datastore-Anteil würde die frischere Lizenz des Forks also einen Kopf fortschreiben, gegen den das Original weiterhin validiert. Den festgehaltenen Kopf auf das Repository und den Datastore zu begrenzen, die die Lizenz nennt, beseitigt beides. Einträge, die ein älterer Renet Agent in einem kürzeren Schlüsselformat geschrieben hat, werden beim ersten Speichern des Zustands verworfen, und die nächste Validierung setzt den Kopf neu.

Der Kettenzustand wird nur bei den Operationen gelesen und fortgeschrieben, die auf der vollen Stufe validieren. Die Betriebsstufe liest ihn weder noch schreibt sie ihn fort, das Starten eines Repositories kann einen Kopf also nie verschieben.

Bei jeder Lizenzvalidierung prüft Renet:

| Prüfung | Fehler bedeutet |
|---|---|
| Ed25519-Signatur ist gültig | Lizenz wurde gefälscht oder manipuliert |
| `sequence >= lastKnownSequence` | Server hat die Kette zurückgesetzt (Replay-Angriff) |
| Eine Wiederholung von `lastKnownSequence` trägt denselben `chainHash` | Eine abgezweigte Kette hat eine Sequenznummer wiederverwendet |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | Chain-Eintrag wurde verändert |

Die bereits installierte Lizenz erneut zu validieren ist kein Rückschritt: Dieselbe Sequenz mit demselben Chain-Hash wird akzeptiert, und genau das erlaubt es einer Maschine, bei jedem Start eines Repositories dieselbe Datei zu validieren.

Schlägt eine Prüfung fehl, wird die Lizenz abgelehnt und der Fehlergrund gemeldet.

## Delegierungszertifikate (On-Premise)

Für Air-Gapped- oder selbst gehostete Bereitstellungen stellt der vorgelagerte Account-Server ein **Delegierungszertifikat** aus, das einen On-Premise-Server autorisiert, Lizenzen mit seinem eigenen Ed25519-Schlüssel zu signieren. Das Zertifikat beschränkt, was der On-Premise-Server tun kann.

### Zertifikatsstruktur

Ein Delegierungszertifikat enthält:

- `subscriptionId` - für welches Abonnement dieses Zertifikat gilt
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` - eingebackene Planlimits
- `maxTotalIssuances` - Obergrenze für die Chain-Sequenznummer
- `delegatedPublicKey` - der Ed25519-Öffentlichschlüssel des On-Premise-Servers (SPKI base64). Sein 16-stelliger Hex-Fingerabdruck (die ersten 8 Bytes von `SHA-256` über den rohen Schlüssel) ist die `publicKeyId`, die auf jedem Lizenz-Blob vermerkt wird, den dieser Schlüssel signiert. `publicKeyId` ist immer ein echter Schlüssel-Fingerabdruck, niemals ein Platzhalter wie `"default"`.
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
5. Wenn eine CLI eine Lizenz vom On-Premise-Server anfordert, signiert der Server mit seinem delegierten Schlüssel und **bettet das vollständige Delegierungszertifikat in den Lizenz-Blob ein** (das Feld `delegationCert`). Das Zertifikat wird nicht separat abgerufen; es reist mit jeder Repo-Lizenz mit.
6. Renet führt eine **zweistufige Validierung** in dieser Reihenfolge durch:
   - Signatur des Zertifikats gegen den eingebackenen vorgelagerten Master-Schlüssel verifizieren.
   - Setzt das Gültigkeitsfenster des Zertifikats (`validFrom` / `validUntil`) bei Wachstumsoperationen (`repo create`, `fork`, `resize`, `expand`) und beim Backup-Transfer (`repo push`, `pull`, Backups) durch. Die Betriebsstufe (`repo up`, `up all`, Autostart) überspringt nur das Fenster, genau wie sie bereits den Lizenzablauf überspringt: Ihre laufenden Workloads stoppen nie, weil ein Zertifikat abgelaufen ist, aber ein abgelaufenes Zertifikat kann nichts Neues autorisieren. Signatur, Schlüsselbindung und jede sonstige Zertifikatsbeschränkung bleiben auf allen Stufen durchgesetzt.
   - Verlangen, dass `fingerprint(cert.delegatedPublicKey) == blob.publicKeyId` (der 16-stellige Hex-Schlüssel-Fingerabdruck), sodass das Zertifikat nur für Lizenzen bürgen kann, die mit genau dem Schlüssel signiert wurden, an den es delegiert.
   - Signatur des Blobs gegen den delegierten Schlüssel aus dem Zertifikat verifizieren.
   - Die Zertifikatsbeschränkungen durchsetzen: Abonnement-Übereinstimmung, Plan-Übereinstimmung, Größenobergrenze (`maxRepositorySizeGb`) und `blob.sequence <= cert.maxTotalIssuances`.
   - Alle Standard-Chain-Prüfungen anwenden.

Ein Zertifikatsfehler schlägt sofort mit einem eigenen Grund fehl: `cert_expired` (außerhalb des Gültigkeitsfensters) oder `cert_invalid` (ungültige Master-Key-Signatur oder eine verletzte Beschränkung). Diese werden **vor** `invalid_signature` geprüft, der Zertifikatsgrund gewinnt also.

Der On-Premise-Server kann nicht:
- Eine Lizenz außerhalb der Planlimits des Delegierungszertifikats fälschen (renet lehnt sie ab).
- Mehr als `maxTotalIssuances` Gesamtoperationen ausstellen (renet lehnt Sequenzüberlauf ab).
- Nach dem `validUntil` des Zertifikats weiterhin lauffähige Lizenzen signieren (das Fenster wird auch bei Operationen durchgesetzt, die den Ablauf sonst überspringen).
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
