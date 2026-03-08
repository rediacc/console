---
title: Справочник по JSON-выводу
description: Полный справочник по формату JSON-вывода rdc CLI, схеме конверта, обработке ошибок и командам обнаружения агентов.
category: Reference
order: 51
language: ru
sourceHash: "a516c49fdaf9a901"
---

Все команды `rdc` поддерживают структурированный JSON-вывод для программного использования AI-агентами и скриптами.

## Включение JSON-вывода

### Явный флаг

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### Автоопределение

Когда `rdc` запускается в не-TTY среде (конвейер, подоболочка или запуск AI-агентом), вывод автоматически переключается на JSON. Флаг не требуется.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## JSON-конверт

Каждый JSON-ответ использует единообразный конверт:

```json
{
  "success": true,
  "command": "machine info",
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
| `command` | `string` | Полный путь команды (например, `"machine info"`, `"repo up"`) |
| `data` | `object \| array \| null` | Полезная нагрузка команды при успехе, `null` при ошибке |
| `errors` | `array \| null` | Объекты ошибок при сбое, `null` при успехе |
| `warnings` | `string[]` | Некритичные предупреждения, собранные при выполнении |
| `metrics` | `object` | Метаданные выполнения |

## Ответы с ошибками

Неуспешные команды возвращают структурированные ошибки с подсказками по восстановлению:

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
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
| `code` | `string` | Машиночитаемый код ошибки |
| `message` | `string` | Описание, понятное человеку |
| `retryable` | `boolean` | Может ли повторная попытка той же команды быть успешной |
| `guidance` | `string` | Рекомендуемое действие для устранения ошибки |

### Повторяемые ошибки

Следующие типы ошибок помечены как `retryable: true`:

- **NETWORK_ERROR** — сбой SSH-соединения или сети
- **RATE_LIMITED** — слишком много запросов, подождите и повторите
- **API_ERROR** — временный сбой бэкенда

Неповторяемые ошибки (аутентификация, не найдено, недопустимые аргументы) требуют корректирующих действий перед повторной попыткой.

## Фильтрация вывода

Используйте `--fields` для ограничения вывода определёнными ключами. Это снижает потребление токенов, когда нужны только определённые данные:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Вывод пробного запуска

Деструктивные команды поддерживают `--dry-run` для предварительного просмотра:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
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

Подкоманда `rdc agent` предоставляет структурированную интроспекцию для AI-агентов, позволяя обнаруживать доступные операции во время выполнения.

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
        "name": "machine info",
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
rdc agent schema "machine info"
```

Возвращает подробную схему для отдельной команды, включая все аргументы и опции с их типами и значениями по умолчанию.

### Выполнение через JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

Принимает JSON на stdin, сопоставляет ключи с аргументами и опциями команды и выполняет с принудительным JSON-выводом. Удобно для структурированного взаимодействия агента с CLI без построения строк shell-команд.

## Примеры парсинга

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
