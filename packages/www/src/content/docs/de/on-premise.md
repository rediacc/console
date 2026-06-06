---
title: "On-Premise-Installation"
description: "Den Account-Server und die CLI-Distribution auf eigener Infrastruktur betreiben."
category: "Guides"
order: 5
language: de
sourceHash: "eea76db2d612133f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc kann vollständig auf eigener Infrastruktur betrieben werden. Das Standalone-Docker-Image enthält den Account-Server, das Webportal, die Marketing-Website und den CLI-Distributionsendpunkt. Externe Abhängigkeiten von Rediacccs gehosteten Diensten sind nicht erforderlich.

## Docker-Image

Das Standalone-Image herunterladen:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Mit Standardeinstellungen starten:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

Das Image stellt Folgendes bereit:
- Account-API unter `/account/api/v1/`
- Webportal unter `/account/`
- Marketing-Website unter `/`
- CLI-Artefakte unter `/releases/`
- Renet-Binärdateien unter `/bin/`

## CLI vom eigenen Server installieren

Die CLI kann direkt vom On-Premise-Server installiert werden. Das Installationsskript erkennt den Update-Kanal automatisch und konfiguriert die CLI so, dass sie den eigenen Server auf Updates prüft.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Dieser einzelne Befehl:
1. Lädt die CLI-Binärdatei vom `/releases/`-Endpunkt des Servers herunter
2. Ruft `/account/api/v1/.well-known/server-info` ab, um den Update-Kanal zu ermitteln
3. Schreibt `server.json` mit der Server-URL, dem Update-Kanal und den Verschlüsselungsschlüsseln
4. Konfiguriert `rdc update` so, dass der eigene Server auf zukünftige Updates geprüft wird

Die Variable `REDIACC_CHANNEL` wird nicht benötigt. Das Installationsskript liest den Kanal automatisch aus der Serverkonfiguration.

## CLI-Konfiguration mit benannten Konfigurationen

Für Umgebungen, in denen sich mehrere Server verbunden werden (On-Premise, Produktion, Edge), isolieren benannte Konfigurationen jede Umgebung voneinander:

```bash
# Konfiguration für den On-Premise-Server erstellen
rdc config init --name myserver --server https://account.example.com

# Mit dieser Konfiguration anmelden
rdc --config myserver subscription login

# Alle Befehle mit --config verwenden den On-Premise-Server
rdc --config myserver machine query --name prod-1
```

Jede benannte Konfiguration speichert ihre eigene Account-Server-URL und ihr eigenes Abonnement-Token. Das Wechseln der Konfiguration wechselt den gesamten Serverkontext.

## Air-Gapped-Umgebungen

Für Umgebungen ohne Internetzugang werden sowohl die Server-URL als auch eine benutzerdefinierte Releases-URL gesetzt:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

Die CLI prüft dann `account.example.com/releases/cli/stable/manifest.json` auf Updates statt des öffentlichen Releases-CDN.

Wenn der Server vollständig offline ist, kann die CLI über npm aus dem mitgelieferten Tarball installiert werden:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Umgebungsvariablen-Referenz

| Variable | Verwendet von | Zweck |
|---|---|---|
| `REDIACC_SERVER_URL` | Installationsskript | Account-Server-URL. Erkennt Kanal und Verschlüsselungsschlüssel automatisch. |
| `REDIACC_RELEASES_URL` | Installationsskript, CLI-Updater | Benutzerdefinierter Releases-Endpunkt für CLI-Binärdateien. Standard: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Installationsskript | Update-Kanal überschreiben. Wird automatisch vom Server erkannt, wenn nicht gesetzt. |
| `REDIACC_ACCOUNT_SERVER` | CLI-Laufzeit | Account-Server-URL für alle CLI-Befehle überschreiben. |
| `RDC_UPDATE_CHANNEL` | CLI-Laufzeit | Update-Kanal für `rdc update` überschreiben. |

## Serverkonfiguration

Das On-Premise-Docker-Image verwendet dieselbe Variable `ENVIRONMENT` wie der gehostete Dienst. Sie wird in der Docker-Umgebung oder der Orchestrierungskonfiguration gesetzt:

- `ENVIRONMENT=production` (Standard): Standard-Ressourcenlimits; CLIs, die sich mit diesem Server verbinden, verwenden standardmäßig den **stable** Update-Kanal. Der Wertname `production` ist eine Legacy-Deploy-Kennung. Sowohl `production`- als auch `edge`-Modi sind produktionstauglich.
- `ENVIRONMENT=edge`: 2X Community-Limits; CLIs verwenden standardmäßig den **edge** Update-Kanal

Details zu den jeweiligen Umgebungen finden sich unter [Release-Kanäle](/de/docs/release-channels).

## Was der Server der CLI mitteilt

Wenn die CLI sich mit dem Server verbindet, ruft sie `/.well-known/server-info` ab und ermittelt:

- **E2E-Verschlüsselung öffentlicher Schlüssel**: für Zero-Knowledge-Konfigurationsspeicher
- **Minimale CLI-Version**: blockiert veraltete CLIs beim Verbinden
- **Update-Kanal**: teilt der CLI mit, welchen Release-Kanal sie für Updates verwenden soll
- **Umgebung**: Welches Deploy-Profil der Server ausführt (Standard-Limits vs. Edge-mit-2X-Limits)

Diese automatische Konfiguration bedeutet, dass nur die Server-URL benötigt wird. Alles andere wird automatisch ermittelt.

## Lizenzierung für Air-Gapped-Bereitstellungen

Air-Gapped- und selbst gehostete On-Premise-Server stellen Lizenzen lokal aus, mithilfe eines **Delegierungszertifikats**, das vom vorgelagerten Master-Schlüssel signiert wurde. Das Zertifikat beschränkt den On-Premise-Server auf seine Planlimits und erstellt eine manipulationssichere Kette. Weitere Informationen zum kryptografischen Design (Kettenintegrität, Fork-Erkennung, Prüfweise) finden sich unter [Lizenz-Chain & Delegation](/de/docs/license-chain).

Dieser Abschnitt beschreibt die operative Einrichtung: Schlüssel generieren, Zertifikat anfordern, automatische Erneuerung konfigurieren und den Offline-Erneuerungsablauf (Air-Gapped).

### Ein Abonnement, eine On-Premise-Installation

Ein Abonnement darf **höchstens ein aktives Delegierungszertifikat gleichzeitig** haben. Jede On-Premise-Installation erzwingt Pro-Monat- und Pro-Maschinen-Limits gegen ihr eigenes lokales Ausstellungs-Ledger, sodass mehrere aktive Zertifikate das effektive Kontingent ohne mögliche Abstimmung vervielfachen würden.

Wenn separate Umgebungen benötigt werden (Produktion, Staging, DR, Multi-Region), kaufen Sie ein Abonnement pro Installation. Die Single-Active-Durchsetzung kodifiziert diesen Vertrag: Ein Versuch, ein zweites aktives Zertifikat zu erstellen, gibt `409 DELEGATION_CERT_ALREADY_ACTIVE` mit der vorhandenen Zertifikat-ID und Anweisungen zur Erneuerung (bevorzugt, behält die Kette) oder zum Widerrufen und Neuerstellen (setzt die Kette zurück) zurück.

### 1. Ed25519-Schlüsselpaar für On-Premise generieren

Der On-Premise-Server verwendet ein separates Ed25519-Schlüsselpaar zum Signieren von Lizenzen. Das Delegierungszertifikat des vorgelagerten Systems autorisiert diesen spezifischen öffentlichen Schlüssel.

```bash
# Neues Schlüsselpaar generieren
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# In base64 konvertieren (das Format, das On-Premise in Umgebungsvariablen erwartet)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Den privaten Schlüssel neben anderen Geheimnissen speichern (z. B. als Docker-Secret oder Kubernetes-Secret). Er verlässt den On-Premise-Server nie.

### 2. Delegierungszertifikat vom vorgelagerten System anfordern

Das Zertifikat kann auf drei Arten vom vorgelagerten Account-Portal angefordert werden:

**Variante A: Kundenselbstbedienung (empfohlen).** Als Org-Owner oder Admin in das vorgelagerte Portal einloggen und zu **/account/delegation-certs** navigieren. Auf **Neu erstellen** klicken, den öffentlichen On-Premise-Schlüssel (base64 SPKI) einfügen, eine Gültigkeit wählen (oder den planmäßigen Standard akzeptieren) und die resultierende `.json`-Datei herunterladen.

**Variante B: Admin (kundenübergreifend).** Rediacc-Support oder der vorgelagerte Systemadministrator kann `POST /admin/delegation-certs` mit denselben Parametern aufrufen.

**Variante C: `rdc`-CLI (geplant).** Ein künftiger CLI-Befehl wird den Portal-Ablauf vereinfachen.

Das zurückgegebene `.json` sieht wie folgt aus:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

Die Gültigkeit des Zertifikats wird durch die Gültigkeitsrichtlinie bestimmt (planmäßige Standards und Obergrenzen, abonnementbezogene Überschreibung, gedeckelt auf Abonnementende plus 3 Tage Nachfrist). Die Antwort enthält auch `effectiveDays` und `reason`, damit der Wert nachvollzogen werden kann. Die vollständigen Regeln finden sich unter [Lizenz-Chain - Gültigkeitsrichtlinie](/de/docs/license-chain).

### 3. Zertifikat auf dem On-Premise-Server installieren

Die heruntergeladene `.json`-Datei an einem bekannten Pfad speichern und den On-Premise-Server darauf hinweisen:

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

Für ephemere/Docker-Secrets-Workflows kann das Zertifikat auch als base64 in einer Umgebungsvariable eingebettet werden:

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. Vorgelagerte Verifizierung und automatische Erneuerung konfigurieren (optional, aber empfohlen)

Wenn der On-Premise-Server ausgehenden HTTPS-Zugriff auf das vorgelagerte System hat, kann die automatische Erneuerung eingerichtet werden, sodass das Zertifikat vor dem Ablauf ohne manuellen Eingriff erneuert wird:

```bash
# Erforderlich für /onprem/cert-upload, um hochgeladene Zertifikate gegen den vorgelagerten Master-Schlüssel zu verifizieren.
# Schlägt beim Start fehl, wenn UPSTREAM_API_KEY ohne diesen Wert gesetzt ist.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# Erforderlich für die automatische Erneuerungsschleife. Über das Portal erstellen:
#   Org-Owner/Admin -> /account/delegation-certs -> "Auto-Renew-Token abrufen"
# Dies ist die EINZIGE Möglichkeit, einen delegation:renew-bezogenen API-Token zu erhalten.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Optionale Anpassung (Standardwerte angezeigt).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

Die automatische Erneuerungsschleife des On-Premise-Servers läuft einmal beim Start und dann im konfigurierten Intervall. Sie verwendet einen **adaptiven Schwellenwert** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`), sodass ein 15-tägiges COMMUNITY-Zertifikat bei 5 verbleibenden Tagen erneuert wird, anstatt die Erneuerung am ersten Tag auszulösen. Ein 90-tägiges BUSINESS-Zertifikat wird bei 14 verbleibenden Tagen erneuert (die konfigurierte Obergrenze).

Wenn die Erneuerung fehlschlägt, bleibt das Zertifikat bis zum natürlichen Ablauf in Verwendung. Der Fehler wird nach 1 Stunde wiederholt und in `${DELEGATION_CERT_PATH}.status.json` aufgezeichnet sowie über `GET /onprem/cert-status` bereitgestellt.

### 5. Air-Gapped-Erneuerung (kein ausgehender HTTPS)

Wenn der On-Premise-Server das vorgelagerte System nicht erreichen kann, wird der manuelle Übertragungsablauf verwendet:

1. **Erneuerungsanforderung vom On-Premise-Adminportal herunterladen.** Als On-Premise-Systemroot `GET /onprem/renewal-request` aufrufen. Dies gibt ein JSON-Manifest zurück, das den lokalen Kettenkopf, den delegierten öffentlichen Schlüssel und eine manipulationssichere Ed25519-Signatur des privaten On-Premise-Schlüssels enthält.
2. **Das Manifest an das vorgelagerte System übertragen** per USB, verschlüsselter E-Mail oder einem anderen Out-of-Band-Kanal. Das Manifest ist klein (einige KB) und enthält keine Geheimnisse.
3. **Das Manifest beim vorgelagerten System verarbeiten.** Org-Owner/Admin öffnet **/account/delegation-certs** > **Erneuerungsanforderung hochladen** > wählt die Manifestdatei aus. Das vorgelagerte System verifiziert die Manifestsignatur gegen den `delegatedPublicKey` des aktiven Zertifikats (beweist, dass es von einem Inhaber des privaten On-Premise-Schlüssels stammt), prüft Anti-Replay (Manifeste älter als 7 Tage werden abgelehnt) und stellt dann ein neues Zertifikat aus.
4. **Das neue Zertifikat** vom vorgelagerten Portal als `.json`-Datei herunterladen.
5. **Das Zertifikat zurück** auf den On-Premise-Server übertragen.
6. **Auf den On-Premise-Server hochladen** über das lokale Adminportal (`POST /onprem/cert-upload`). Der On-Premise-Server verifiziert das neue Zertifikat gegen `UPSTREAM_PUBLIC_KEY` und prüft, ob `genesisSequence` des Zertifikats noch mit einem Eintrag im lokalen Ausstellungs-Ledger verbunden ist (Sequenzfortschritt während des Transits wird unterstützt - die Kette verlängert sich natürlich).

Diese gesamte Schleife erfordert keinen Netzwerkabgang vom On-Premise-Server.

#### Manifest-Fehlermodi

| Code | Ursache | Behebung |
|---|---|---|
| `NO_ACTIVE_CERT` | Das vorgelagerte System hat kein aktives Zertifikat für dieses Abonnement | Ein neues Zertifikat über den Erstellungsablauf ausstellen statt zu erneuern |
| `DELEGATED_KEY_MISMATCH` | `delegatedPublicKey` des Manifests weicht vom aktiven Zertifikat ab | Das Manifest könnte eine Wiederholung von einer anderen On-Prem-Installation sein |
| `MANIFEST_SIGNATURE_INVALID` | Signatur kann nicht gegen den delegierten öffentlichen Schlüssel verifiziert werden | Das Manifest wurde während des Transits manipuliert, oder es wurde auf einer anderen On-Prem-Installation generiert |
| `MANIFEST_EXPIRED` | Manifest ist älter als 7 Tage | Eine neue Erneuerungsanforderung vom On-Premise-Server generieren |

#### Zertifikat-Upload-Fehlermodi

| Code | Ursache | Behebung |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | `genesisSequence` des neuen Zertifikats liegt vor dem lokalen Kettenkopf | Das vorgelagerte System befindet sich auf einer abgezweigten Kette - untersuchen |
| `CHAIN_FORK_ON_UPLOAD` | Chain-Hash an `genesisSequence` des Zertifikats stimmt nicht mit dem lokalen Ledger überein | Die lokale Kette hat sich vom vorgelagerten System abgezweigt - untersuchen |
| `Signature verification failed` | Zertifikat ist nicht vom konfigurierten `UPSTREAM_PUBLIC_KEY` signiert | Prüfung, ob `UPSTREAM_PUBLIC_KEY` mit dem vorgelagerten Master-Public-Key übereinstimmt |

### 6. Status und Monitoring

Den lokalen Zertifikatsstatus des On-Premise-Servers jederzeit abfragen:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Gibt `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` des geladenen Zertifikats zurück, sowie den `autoRenew`-Block (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Dies in den Monitoring-Stack einbinden, um bei veraltetem `lastSuccessAt` oder nicht-nullem `lastError` zu warnen.

Für Backup und Audit kann der On-Premise-Admin das aktuell geladene signierte Zertifikat auch über `GET /onprem/cert-current` herunterladen (erhöhte Sitzung erforderlich).

### Delegierungszertifikat-Umgebungsvariablen-Referenz

| Variable | Erforderlich? | Zweck |
|---|---|---|
| `ON_PREMISE_MODE` | Ja | Auf `true` setzen, um die On-Premise-Route-Teilmenge zu aktivieren |
| `ON_PREMISE_PRIVATE_KEY` | Ja | Base64 PKCS8 Ed25519-Privatschlüssel für delegiertes Signieren |
| `ON_PREMISE_PUBLIC_KEY` | Ja | Base64 SPKI Ed25519-Öffentlichschlüssel (muss mit `delegatedPublicKey` des Zertifikats übereinstimmen) |
| `DELEGATION_CERT_PATH` | Eines davon | Dateisystempfad zur signierten Zertifikat-JSON-Datei |
| `DELEGATION_CERT_BASE64` | Eines davon | Base64-kodiertes Zertifikat-JSON (Alternative zum Dateipfad) |
| `UPSTREAM_PUBLIC_KEY` | Erforderlich, wenn `UPSTREAM_API_KEY` gesetzt ist, oder damit `/onprem/cert-upload` funktioniert | Base64 SPKI des vorgelagerten Master-Public-Keys. Fail-Fast beim Start, wenn fehlend. |
| `UPSTREAM_URL` | Für automatische Erneuerung | Basis-URL des vorgelagerten Account-Servers, z. B. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Für automatische Erneuerung | Ein `delegation:renew`-bezogener API-Token. Über das Portal erstellen - siehe Schritt 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Optional | Standard 24. Wie oft geprüft wird, ob das Zertifikat erneuert werden muss. |
| `RENEW_THRESHOLD_DAYS` | Optional | Standard 14. Dient als Obergrenze für den adaptiven 1/3-der-Gültigkeitsschwellenwert. |

### Zusammenfassung des Bedrohungsmodells

Das Delegierungszertifikat-Modell schützt vor:

- **Gefälschten Lizenzen**: Der On-Premise-Server kann nur innerhalb seiner Planlimits signieren; renet lehnt alles ab, was außerhalb der Zertifikatsgrenzen liegt.
- **Zertifikatsfreigabe zwischen Bereitstellungen**: Kettenabweichung wird bei der Erneuerung erkannt (gibt `CHAIN_FORK_DETECTED` zurück).
- **Kontingentumgehung durch Multi-Installation**: Wird vom vorgelagerten System durch Single-Active durchgesetzt (ein Zertifikat pro Abonnement).
- **Ketten-Rollback**: renet speichert die höchste gesehene Sequenz pro Abonnement und lehnt alle Blobs mit einer niedrigeren Sequenz ab.
- **Kompromittierte vorgelagerte Anmeldeinformationen**: Das Bootstrap-Token `delegation:renew` kann nur über den dedizierten Portalendpunkt erstellt werden und ist admin-gesichert. Das Token gewährt nur Erneuerung - es kann keine anderen Ressourcen lesen oder anderweitig verändern.
- **Replay-Angriffe auf Manifeste**: Manifeste älter als 7 Tage werden abgelehnt.

Was es **nicht** schützt:

- **Kompromittierter privater On-Premise-Schlüssel**: Ein geleakter privater Schlüssel ermöglicht es einem Angreifer, Lizenzen bis zum `validUntil` des Zertifikats zu signieren. Abhilfe: Das Schlüsselpaar rotieren (altes Zertifikat widerrufen und neues mit neuem Schlüssel erstellen) und alle vom alten Schlüssel signierten Lizenzen als verdächtig behandeln.
- **Kompromittierter vorgelagerter Master-Schlüssel**: Dies ist der Vertrauensanker. Rotationsverfahren sind hier nicht behandelt.
