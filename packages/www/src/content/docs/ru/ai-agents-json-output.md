---
title: Справочник по JSON-выводу
description: >-
  Полный справочник по формату JSON-вывода rdc CLI, схеме конверта, обработке
  ошибок и командам обнаружения агентов.
category: Reference
order: 51
language: ru
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Все команды `rdc` выводят структурированный JSON. Результат можно передать в скрипт или напрямую в агент.

## Включение JSON-вывода

### Явный флаг

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### Автоопределение

Когда `rdc` запускается в не-TTY среде (конвейер, подоболочка или запуск AI-агентом), вывод автоматически переключается на JSON. Флаг не требуется.

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## JSON-конверт

Каждый JSON-ответ использует единообразный конверт:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Поле | Тип | Описание |
|-------|------|-------------|
| `success` | `boolean` | Успешно ли завершилась команда |
| `command` | `string` | Полный путь команды (например, `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Полезная нагрузка команды при успехе, `null` при ошибке |
| `errors` | `array \| null` | Объекты ошибок при сбое, `null` при успехе |
| `warnings` | `string[]` | Некритичные предупреждения, собранные при выполнении |
| `metrics` | `object` | Метаданные выполнения |

## Ответы с ошибками

Неуспешные команды возвращают структурированные ошибки с подсказками по восстановлению:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Поля ошибок

| Поле | Тип | Описание |
|-------|------|-------------|
| `code` | `string` | Машиночитаемый код ошибки (полный перечень см. в константах `ERROR_CODES`) |
| `message` | `string` | Описание, понятное человеку |
| `retryable` | `boolean` | Может ли повторная попытка той же команды быть успешной |
| `guidance` | `string` | Произвольная подсказка (устаревшее поле. Для структурированных данных о действии используйте `next`) |
| `next` | `object?` | Структурированная подсказка о следующем действии (если присутствует). См. ниже |

### Структурированные подсказки для действий `next`

Для ряда важных кодов ошибок, таких как `PRECONDITION_MISMATCH`, ошибка содержит поле `next` с точными командами, которые следует предложить пользователю. Это поле есть не у каждого кода ошибки -- только у тех, для которых определён путь восстановления. **Агентам следует передавать `next.options[].run` пользователю дословно, не составляя команды самостоятельно.** Это исключает ситуацию, когда агент придумывает несуществующую команду. Такое случается чаще, чем кажется.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Схема:

| Поле | Тип | Описание |
|-------|------|-------------|
| `next.summary` | `string` | Краткое описание того, что нужно решить пользователю |
| `next.options[]` | `array` | Конкретные действия; каждый вариант является альтернативой на выбор |
| `next.options[].description` | `string` | Описание варианта, понятное человеку |
| `next.options[].run` | `string` | Точная команда CLI. Передавать пользователю дословно |

### Повторяемые ошибки

Следующие типы ошибок помечены как `retryable: true`:

- **NETWORK_ERROR**, сбой SSH-соединения или сети
- **RATE_LIMITED**, слишком много запросов, подождите и повторите
- **API_ERROR**, временный сбой бэкенда

Неповторяемые ошибки (аутентификация, не найдено, недопустимые аргументы) требуют корректирующих действий перед повторной попыткой.

## Фильтрация вывода

Используйте `--fields` для ограничения вывода определёнными ключами и сокращения потребления токенов:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## Вывод пробного запуска

Деструктивные команды поддерживают `--dry-run` для предварительного просмотра:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Команды с поддержкой `--dry-run`: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Команды обнаружения агентов

Подкоманда `rdc agent` предоставляет AI-агентам структурированный способ обнаружения доступных операций во время выполнения.

### Список всех команд

```bash
rdc agent capabilities
```

Возвращает полное дерево команд с аргументами, опциями и описаниями:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Получение схемы команды

```bash
rdc agent schema --command "machine query"
```

Возвращает полную схему для отдельной команды: каждый аргумент и опцию с типом и значением по умолчанию.

### Выполнение через JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Принимает JSON на stdin, сопоставляет ключи с аргументами и опциями команды и выполняет её с принудительным JSON-выводом. Удобно, когда не хочется вручную формировать строки shell-команд для вызовов агент--CLI.

## Примеры парсинга

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
