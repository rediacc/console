---
title: "Integración con SIEM"
description: "Enruta los eventos de auditoría de Rediacc a Splunk, OpenSearch, Sentinel o cualquier SIEM compatible con OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: es
sourceHash: "f0f5dae9694c8e27"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# Integración con SIEM

Toda operación a nivel de máquina emitida mediante la CLI de Rediacc se registra en la tabla `event_log` del servidor de cuentas y se emite a la vez como registro de log de OpenTelemetry. Los operadores encaminan esos registros a un SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch, etc.) apuntando el servidor de cuentas a un OpenTelemetry Collector que exporta al SIEM de su elección.

Esta página explica cómo configurarlo. El esquema de eventos de auditoría y el despliegue de referencia del collector están en el monorepo público, en [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Qué se registra

Cada entrada escrita en la tabla `event_log` del servidor de cuentas se refleja en la canalización de logs OTLP. Esto incluye tanto los eventos a nivel de cuenta (autenticación, almacenamiento de configuración, licencia) como los eventos de CLI a nivel de máquina (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …).

El vocabulario de tipos de evento es una unión discriminada cerrada, definida en [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Añadir un tipo de evento nuevo exige un cambio de código y lo controla la CI, de modo que quienes escriben reglas de SIEM pueden confiar en que el vocabulario es estable.

Cada registro de log lleva atributos semánticos de OpenTelemetry:

| Atributo | Significado |
|---|---|
| `event.domain` | Fijo `rediacc.audit`; se filtra por él para ignorar logs ajenos |
| `event.name` | El tipo de evento canónico (p. ej. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Usuario que inicia la operación |
| `organization.id`, `team.id` | Ámbito de organización y equipo |
| `cloud.account.id` | ID de cliente de Stripe |
| `subscription.id` | Suscripción de licencia |
| `audit.data.*` | Carga útil de la operación, aplanada |

## Puesta en marcha

### 1. Desplegar el collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Por defecto el collector escucha en `:4318` (OTLP/HTTP) y escribe en su propia salida estándar mediante el exportador `debug`, útil para verificar la canalización antes de encaminar nada costoso.

### 2. Apuntar el servidor de cuentas al collector

En el entorno del servidor de cuentas (`private/account/.env` o su equivalente de Docker/Wrangler):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Reiniciar el servidor de cuentas. Los eventos de auditoría empiezan a fluir al collector de inmediato.

### 3. Configurar el exportador del SIEM

Editar `compose/otel-collector/config.yaml`. El archivo incluye cuatro ejemplos de exportador comentados:

- **OpenSearch / Elasticsearch**: exportador `opensearch`, requiere la extensión `basicauth/opensearch`.
- **Splunk HEC**: exportador `splunk_hec`, requiere un token HEC y un índice.
- **AWS CloudWatch Logs**: exportador `awscloudwatchlogs`, requiere credenciales IAM en el entorno del collector.
- **Microsoft Sentinel**: mediante el exportador `azuremonitor` con una cadena de conexión de App Insights.

Descomentar exactamente uno, sustituir `debug` por él en la lista `exporters:` de la canalización `logs:` y reiniciar el collector.

Sirve cualquier [exportador contrib del OTel Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) que acepte logs: la canalización de auditoría produce registros de log OTLP estándar.

## Contenido de detección

Los eventos de auditoría están pensados para redactar reglas [Sigma](https://sigmahq.io). Las reglas Sigma son neutrales respecto al proveedor y se convierten con `sigma-cli` en consultas nativas para OpenSearch, Splunk, Sentinel y otros.

Regla de ejemplo (`repo.fork` fallido de un usuario inesperado):

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

## Postura de cumplimiento

La canalización de auditoría es la base de los requisitos de registro de auditoría a los que remite la documentación de cumplimiento de Rediacc:

- **RGPD Art. 30**: registros de las actividades de tratamiento
- **SOC 2 CC6.1 / CC7.2**: registro de accesos y monitorización
- **HIPAA 45 CFR 164.312(b)**: controles de auditoría
- **PCI DSS Req 10**: seguimiento y monitorización de todos los accesos
- **NIS2 Art. 21**: los eventos de auditoría son una entrada para la gestión de incidentes; la línea de tiempo del incidente, los relojes y los informes por etapas son funciones aparte
- **DORA Art. 10**: los eventos de auditoría son una entrada para la detección; los detectores de anomalías se ejecutan sobre los registros de flujo de forensics, no sobre esta canalización

## Fiabilidad

La emisión OTLP es de tipo «disparar y olvidar»: una caída del collector nunca bloquea ni hace fallar una petición a la API de Rediacc, y cada evento se sigue guardando en la tabla `event_log` del servidor de cuentas en cualquier caso. Junto con el procesamiento por lotes y los reintentos del collector, esto hace que la canalización se pueda desplegar con seguridad delante de cualquier SIEM.
