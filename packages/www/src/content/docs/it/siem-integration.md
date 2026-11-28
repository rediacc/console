---
title: "Integrazione SIEM"
description: "Instradare gli eventi di audit di Rediacc verso Splunk, OpenSearch, Sentinel o qualsiasi SIEM compatibile con OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: it
sourceHash: "69ec0d3d122d13df"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Integrazione SIEM

Ogni operazione a livello di macchina emessa tramite la CLI di Rediacc viene registrata nella tabella `event_log` del server account ed emessa contemporaneamente come record di log OpenTelemetry. Gli operatori instradano questi record verso un SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch, ecc.) puntando il server account a un OpenTelemetry Collector che esporta verso il SIEM scelto.

Questa pagina spiega come configurarlo. Lo schema degli eventi di audit e il deployment di riferimento del collector si trovano nel monorepo pubblico, in [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Cosa viene registrato

Ogni voce scritta nella tabella `event_log` del server account, sia gli eventi a livello di account (autenticazione, config storage, licenza) sia gli eventi CLI a livello di macchina (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …), viene replicata nella pipeline di log OTLP.

Il vocabolario dei tipi di evento è una unione discriminata chiusa, definita in [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Aggiungere un nuovo tipo di evento richiede una modifica al codice ed è controllato dalla CI, quindi chi scrive regole SIEM può contare sulla stabilità del vocabolario.

Ogni record di log porta attributi semantici OpenTelemetry:

| Attributo | Significato |
|---|---|
| `event.domain` | Valore fisso `rediacc.audit`: filtrare su questo per ignorare i log non correlati |
| `event.name` | Il tipo di evento canonico (ad es. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Utente che ha avviato l'operazione |
| `organization.id`, `team.id` | Ambito organizzazione/team |
| `cloud.account.id` | ID cliente Stripe |
| `subscription.id` | Sottoscrizione della licenza |
| `audit.data.*` | Payload dell'operazione, appiattito |

## Configurazione

### 1. Distribuire il collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Per impostazione predefinita il collector è in ascolto su `:4318` (OTLP/HTTP) e scrive sul proprio stdout tramite l'exporter `debug`, utile per verificare la pipeline prima di instradarla verso una destinazione costosa.

### 2. Puntare il server account al collector

Nell'ambiente del server account (i secret del Worker o l'ambiente di processo di un server on-premise):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Riavviare il server account. Gli eventi di audit iniziano subito a fluire verso il collector.

### 3. Configurare l'exporter del SIEM

Modificare `compose/otel-collector/config.yaml`. Il file include quattro esempi di exporter commentati:

- **OpenSearch / Elasticsearch**: exporter `opensearch`, richiede l'estensione `basicauth/opensearch`.
- **Splunk HEC**: exporter `splunk_hec`, richiede un token HEC e un indice.
- **AWS CloudWatch Logs**: exporter `awscloudwatchlogs`, richiede credenziali IAM nell'ambiente del collector.
- **Microsoft Sentinel**: tramite l'exporter `azuremonitor` con una connection string di App Insights.

Decommentarne uno solo, sostituirlo a `debug` nell'elenco `exporters:` della pipeline `logs:` e riavviare il collector.

Qualsiasi [exporter contrib dell'OTel Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) che accetta log funziona: la pipeline di audit produce record di log OTLP standard.

## Contenuti di rilevamento

Gli eventi di audit sono pensati per la scrittura di regole [Sigma](https://sigmahq.io). Le regole Sigma sono indipendenti dal fornitore e vengono convertite tramite `sigma-cli` in query native per OpenSearch, Splunk, Sentinel e altri.

Regola di esempio (`repo.fork` fallito da un utente inatteso):

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

## Postura di conformità

La pipeline di audit è la base dei requisiti di audit logging citati nella documentazione di conformità di Rediacc:

- **GDPR Art. 30**: registri delle attività di trattamento
- **SOC 2 CC6.1 / CC7.2**: logging degli accessi e monitoraggio
- **HIPAA 45 CFR 164.312(b)**: controlli di audit
- **PCI DSS Req 10**: tracciare e monitorare tutti gli accessi
- **NIS2 Art. 21**: gli eventi di audit sono un input per la gestione degli incidenti; la timeline dell'incidente, i timer e i report a fasi sono funzionalità separate
- **DORA Art. 10**: gli eventi di audit sono un input per il rilevamento; i rilevatori di anomalie girano sulla macchina e sul server sui record di flusso forensics, non su questa pipeline

## Affidabilità

L'emissione OTLP è di tipo fire-and-forget: un'interruzione del collector non bloccherà né farà fallire mai una richiesta API di Rediacc, e ogni evento resta comunque persistito nella tabella `event_log` del server account. Insieme al batching e ai retry del collector, questo rende la pipeline sicura da distribuire davanti a qualsiasi SIEM.
