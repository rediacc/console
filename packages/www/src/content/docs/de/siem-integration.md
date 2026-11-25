---
title: "SIEM-Integration"
description: "Rediacc-Audit-Ereignisse an Splunk, OpenSearch, Sentinel oder ein beliebiges OpenTelemetry-kompatibles SIEM weiterleiten"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: de
sourceHash: "f0f5dae9694c8e27"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# SIEM-Integration

Jede Operation auf Maschinenebene, die über die Rediacc-CLI ausgelöst wird, wird in die Tabelle `event_log` des Account-Servers geschrieben und zugleich als OpenTelemetry-Log-Record ausgegeben. Operatoren leiten diese Records in ein SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch usw.), indem sie den Account-Server auf einen OpenTelemetry Collector zeigen lassen, der in das SIEM ihrer Wahl exportiert.

Diese Seite beschreibt die Einrichtung. Das Audit-Ereignisschema und die Referenz-Bereitstellung des Collectors liegen im öffentlichen Monorepo unter [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Was protokolliert wird

Jeder Eintrag in der Tabelle `event_log` des Account-Servers wird in die OTLP-Logs-Pipeline gespiegelt. Dazu zählen sowohl Ereignisse auf Kontoebene (Auth, Config Storage, Lizenz) als auch CLI-Ereignisse auf Maschinenebene (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …).

Das Vokabular der Ereignistypen ist eine geschlossene diskriminierte Union, definiert in [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Ein neuer Ereignistyp erfordert eine Codeänderung und wird von der CI geprüft, sodass Autoren von SIEM-Regeln sich auf ein stabiles Vokabular verlassen können.

Jeder Log-Record trägt semantische OpenTelemetry-Attribute:

| Attribut | Bedeutung |
|---|---|
| `event.domain` | Fest `rediacc.audit`, hiernach filtern, um fremde Logs auszublenden |
| `event.name` | Der kanonische Ereignistyp (z. B. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Auslösender Benutzer |
| `organization.id`, `team.id` | Organisations-/Team-Bereich |
| `cloud.account.id` | Stripe-Kunden-ID |
| `subscription.id` | Lizenz-Abonnement |
| `audit.data.*` | Abgeflachte Nutzlast der Operation |

## Einrichtung

### 1. Collector bereitstellen

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Standardmäßig lauscht der Collector auf `:4318` (OTLP/HTTP) und schreibt über den Exporter `debug` auf seine eigene Standardausgabe. Das eignet sich, um die Pipeline zu prüfen, bevor etwas Kostspieliges angebunden wird.

### 2. Account-Server darauf ausrichten

In der Umgebung des Account-Servers (`private/account/.env` oder das entsprechende Docker-/Wrangler-Äquivalent):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Den Account-Server neu starten. Audit-Ereignisse fließen danach sofort an den Collector.

### 3. SIEM-Exporter konfigurieren

`compose/otel-collector/config.yaml` bearbeiten. Die Datei enthält vier auskommentierte Exporter-Beispiele:

- **OpenSearch / Elasticsearch**: Exporter `opensearch`, benötigt die Extension `basicauth/opensearch`.
- **Splunk HEC**: Exporter `splunk_hec`, benötigt ein HEC-Token und einen Index.
- **AWS CloudWatch Logs**: Exporter `awscloudwatchlogs`, benötigt IAM-Zugangsdaten in der Umgebung des Collectors.
- **Microsoft Sentinel**: über den Exporter `azuremonitor` mit einem App-Insights-Verbindungsstring.

Genau einen Exporter einkommentieren, in der Liste `exporters:` der `logs:`-Pipeline gegen `debug` austauschen und den Collector neu starten.

Jeder [OTel-Collector-Contrib-Exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter), der Logs annimmt, funktioniert: Die Audit-Pipeline erzeugt standardkonforme OTLP-Log-Records.

## Erkennungsinhalte

Audit-Ereignisse sind auf das Verfassen von [Sigma](https://sigmahq.io)-Regeln ausgelegt. Sigma-Regeln sind herstellerneutral und lassen sich über `sigma-cli` in native Abfragen für OpenSearch, Splunk, Sentinel und andere umwandeln.

Beispielregel (fehlgeschlagenes `repo.fork` durch einen unerwarteten Benutzer):

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## Compliance-Einordnung

Die Audit-Pipeline ist die Grundlage für die Anforderungen an die Audit-Protokollierung, auf die die Compliance-Dokumentation von Rediacc verweist:

- **DSGVO Art. 30**: Verzeichnis von Verarbeitungstätigkeiten
- **SOC 2 CC6.1 / CC7.2**: Zugriffsprotokollierung und Überwachung
- **HIPAA 45 CFR 164.312(b)**: Audit-Kontrollen
- **PCI DSS Req 10**: Alle Zugriffe nachverfolgen und überwachen
- **NIS2 Art. 21**: Die Audit-Ereignisse sind eine Eingabe für die Vorfallsbehandlung; Vorfall-Timeline, Fristuhren und gestufte Berichte sind eigene Funktionen
- **DORA Art. 10**: Die Audit-Ereignisse sind eine Eingabe für die Erkennung; die Anomalie-Detektoren laufen auf Forensics-Flow-Records, nicht auf dieser Pipeline

## Zuverlässigkeit

Die OTLP-Ausgabe ist Fire-and-Forget: Ein Ausfall des Collectors blockiert oder scheitert nie eine Rediacc-API-Anfrage, und jedes Ereignis wird unabhängig davon weiterhin in der Tabelle `event_log` des Account-Servers gespeichert. Zusammen mit dem Batching und den Wiederholungen des Collectors macht das die Pipeline sicher einsetzbar vor jedem SIEM.
