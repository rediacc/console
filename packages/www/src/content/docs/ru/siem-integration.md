---
title: "Интеграция с SIEM"
description: "Маршрутизация событий аудита Rediacc в Splunk, OpenSearch, Sentinel или любой SIEM, совместимый с OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: ru
sourceHash: "224ef90a952edb1c"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# Интеграция с SIEM

Каждая операция уровня машины, выполненная через CLI Rediacc, записывается в таблицу `event_log` сервера аккаунтов и одновременно отправляется как лог-запись OpenTelemetry. Операторы направляют эти записи в SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch и другие), указывая серверу аккаунтов OpenTelemetry Collector, который экспортирует данные в выбранный SIEM.

На этой странице описано, как это настроить. Схема событий аудита и эталонное развёртывание коллектора находятся в публичном монорепозитории в [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Что записывается

Каждая запись в таблице `event_log` сервера аккаунтов -- включая как события уровня аккаунта (аутентификация, хранилище конфигураций, лицензии), так и события CLI уровня машины (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …) -- дублируется в конвейер логов OTLP.

Словарь типов событий -- это закрытое размеченное объединение, определённое в [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). Добавление нового типа события требует изменения кода и проверяется в CI, поэтому авторы правил для SIEM могут рассчитывать на стабильность словаря.

Каждая лог-запись несёт семантические атрибуты OpenTelemetry:

| Атрибут | Значение |
|---|---|
| `event.domain` | Фиксированное значение `rediacc.audit` -- фильтрация по нему отсекает посторонние логи |
| `event.name` | Каноническое имя типа события (например, `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Инициировавший пользователь |
| `organization.id`, `team.id` | Область организации и команды |
| `cloud.account.id` | Идентификатор клиента в Stripe |
| `subscription.id` | Подписка на лицензию |
| `audit.data.*` | Развёрнутая полезная нагрузка операции |

## Настройка

### 1. Развёртывание коллектора

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

По умолчанию коллектор слушает порт `:4318` (OTLP/HTTP) и пишет в собственный stdout через экспортёр `debug` -- это удобно для проверки конвейера до маршрутизации в более дорогую систему.

### 2. Указание коллектора серверу аккаунтов

В окружении сервера аккаунтов (секреты Worker или окружение процесса локального сервера):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

После перезапуска сервера аккаунтов события аудита сразу начинают поступать в коллектор.

### 3. Настройка экспортёра в SIEM

Нужно отредактировать `compose/otel-collector/config.yaml`. В файле есть четыре закомментированных примера экспортёров:

- **OpenSearch / Elasticsearch** -- экспортёр `opensearch`, требует расширение `basicauth/opensearch`.
- **Splunk HEC** -- экспортёр `splunk_hec`, требует токен HEC и индекс.
- **AWS CloudWatch Logs** -- экспортёр `awscloudwatchlogs`, требует учётные данные IAM в окружении коллектора.
- **Microsoft Sentinel** -- через экспортёр `azuremonitor` со строкой подключения App Insights.

Раскомментируется ровно один из них, он ставится вместо `debug` в списке `exporters:` конвейера `logs:`, после чего коллектор перезапускается.

Подойдёт любой [экспортёр OTel Collector contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter), принимающий логи -- конвейер аудита выдаёт стандартные лог-записи OTLP.

## Содержимое для обнаружения

События аудита рассчитаны на написание правил [Sigma](https://sigmahq.io). Правила Sigma не привязаны к вендору и преобразуются через `sigma-cli` в нативные запросы для OpenSearch, Splunk, Sentinel и других систем.

Пример правила (неудачный `repo.fork` от неожиданного пользователя):

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

## Соответствие требованиям

Конвейер аудита -- основа для требований к журналированию аудита, упомянутых в документации Rediacc по соответствию:

- **GDPR Art. 30** -- записи о деятельности по обработке
- **SOC 2 CC6.1 / CC7.2** -- журналирование доступа и мониторинг
- **HIPAA 45 CFR 164.312(b)** -- средства контроля аудита
- **PCI DSS Req 10** -- отслеживание и мониторинг всего доступа
- **NIS2 Art. 21** -- события аудита служат входными данными для обработки инцидентов; временная шкала инцидента, таймеры и поэтапные отчёты -- отдельные функции
- **DORA Art. 10** -- события аудита служат входными данными для обнаружения; детекторы аномалий работают на записях потоков forensics, а не на этом конвейере

## Надёжность

Отправка OTLP выполняется по принципу «отправил и забыл» -- сбой коллектора никогда не блокирует и не проваливает запрос к API Rediacc, а каждое событие в любом случае сохраняется в таблице `event_log` сервера аккаунтов. В сочетании с пакетной обработкой и повторными попытками коллектора это делает конвейер безопасным для развёртывания перед любым SIEM.
