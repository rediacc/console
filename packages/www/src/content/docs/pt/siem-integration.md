---
title: "Integração com SIEM"
description: "Encaminhe os eventos de auditoria do Rediacc para Splunk, OpenSearch, Sentinel ou qualquer SIEM compatível com OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: pt
sourceHash: "69ec0d3d122d13df"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Integração com SIEM

Todas as operações ao nível da máquina emitidas através da CLI do Rediacc são registadas na tabela `event_log` do servidor de contas e emitidas em simultâneo como registos de log OpenTelemetry. Os operadores encaminham esses registos para um SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch, etc.) apontando o servidor de contas para um OpenTelemetry Collector que exporta para o SIEM escolhido.

Esta página explica como configurar a ligação. O esquema dos eventos de auditoria e a implementação de referência do Collector estão no monorepo público, em [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## O que é registado

Cada entrada escrita na tabela `event_log` do servidor de contas -- o que inclui eventos ao nível da conta (autenticação, armazenamento de configuração, licença) e eventos de CLI ao nível da máquina (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …) -- é replicada para o pipeline de logs OTLP.

O vocabulário de tipos de evento é uma união discriminada fechada, definida em [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Adicionar um novo tipo de evento exige uma alteração de código e é validado pela CI, pelo que quem escreve regras de SIEM pode contar com um vocabulário estável.

Cada registo de log traz atributos semânticos do OpenTelemetry:

| Atributo | Significado |
|---|---|
| `event.domain` | Valor fixo `rediacc.audit` -- filtre por este campo para ignorar logs não relacionados |
| `event.name` | O tipo de evento canónico (por exemplo, `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Utilizador que iniciou a operação |
| `organization.id`, `team.id` | Âmbito de organização/equipa |
| `cloud.account.id` | ID de cliente Stripe |
| `subscription.id` | Subscrição da licença |
| `audit.data.*` | Payload da operação, achatado |

## Configuração

### 1. Implementar o Collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Por predefinição, o Collector escuta em `:4318` (OTLP/HTTP) e escreve no seu próprio stdout através do exporter `debug` -- útil para verificar o pipeline antes de o encaminhar para um destino dispendioso.

### 2. Apontar o servidor de contas para o Collector

No ambiente do servidor de contas (os segredos do Worker ou o ambiente de processo de um servidor local):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Reinicie o servidor de contas. Os eventos de auditoria começam a fluir para o Collector de imediato.

### 3. Configurar o exporter do SIEM

Edite `compose/otel-collector/config.yaml`. O ficheiro inclui quatro exemplos de exporters comentados:

- **OpenSearch / Elasticsearch** -- exporter `opensearch`, requer a extensão `basicauth/opensearch`.
- **Splunk HEC** -- exporter `splunk_hec`, requer um token HEC e um índice.
- **AWS CloudWatch Logs** -- exporter `awscloudwatchlogs`, requer credenciais IAM no ambiente do Collector.
- **Microsoft Sentinel** -- através do exporter `azuremonitor`, com uma connection string do App Insights.

Descomente exatamente um, substitua `debug` por ele na lista `exporters:` do pipeline `logs:` e reinicie o Collector.

Qualquer [exporter contrib do OTel Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) que aceite logs funciona -- o pipeline de auditoria produz registos de log OTLP padrão.

## Conteúdo de deteção

Os eventos de auditoria foram concebidos para a escrita de regras [Sigma](https://sigmahq.io). As regras Sigma são neutras quanto ao fornecedor e são convertidas pelo `sigma-cli` em consultas nativas para OpenSearch, Splunk, Sentinel e outros.

Regra de exemplo (falha de `repo.fork` por um utilizador inesperado):

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

## Postura de conformidade

O pipeline de auditoria é a base dos requisitos de registo de auditoria referenciados na documentação de conformidade do Rediacc:

- **RGPD Art. 30** -- registos das atividades de tratamento
- **SOC 2 CC6.1 / CC7.2** -- registo de acessos e monitorização
- **HIPAA 45 CFR 164.312(b)** -- controlos de auditoria
- **PCI DSS Req. 10** -- acompanhar e monitorizar todos os acessos
- **NIS2 Art. 21** -- os eventos de auditoria são um contributo para o tratamento de incidentes; a cronologia do incidente, os relógios e os relatórios por fases são funcionalidades separadas
- **DORA Art. 10** -- os eventos de auditoria são um contributo para a deteção; os detetores de anomalias correm na máquina e no servidor sobre os registos de fluxo forenses, não sobre este pipeline

## Fiabilidade

A emissão OTLP é do tipo fire-and-forget -- uma falha do Collector nunca bloqueia nem faz falhar um pedido à API do Rediacc, e cada evento continua a ser persistido na tabela `event_log` do servidor de contas, independentemente disso. Combinado com o batching e o comportamento de repetição do Collector, isto torna o pipeline seguro para colocar à frente de qualquer SIEM.
