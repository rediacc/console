---
title: Обзор интеграции с AI-агентами
description: "Как Claude Code, Cursor и Cline управляют инфраструктурой Rediacc через rdc: JSON-вывод, интроспекция агентов и защитные ограждения."
category: Guides
order: 30
language: ru
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Честно говоря, `rdc` изначально проектировался с учётом агентов. Claude Code, Cursor, Cline: любой AI-ассистент, вызывающий `rdc` в подоболочке, получает структурированный JSON-вывод, машиночитаемые ошибки и защитные ограждения, необходимые для автономного управления инфраструктурой Rediacc. Вот как работает эта интеграция.

## Почему самостоятельный хостинг + AI-агенты

Архитектура Rediacc хорошо подходит для агентов:

- **CLI в первую очередь**: каждая операция, это команда `rdc`, GUI не требуется
- **На основе SSH**: протокол, который агенты лучше всего знают из обучающих данных
- **JSON-вывод**: все команды поддерживают `--output json` с единообразным конвертом
- **Изоляция Docker**: каждый репозиторий получает собственный демон и сетевое пространство имён
- **Скриптуемость**: `--yes` пропускает подтверждения, `--dry-run` предварительно показывает деструктивные операции

## Подходы к интеграции

### 1. Шаблон AGENTS.md / CLAUDE.md

Самый быстрый способ начать. Скопируйте наш [шаблон AGENTS.md](/ru/docs/agents-md-template) в корень проекта:

- `CLAUDE.md` для Claude Code
- `.cursorrules` для Cursor
- `.windsurfrules` для Windsurf

Достаточно добавить файл, и агент получит полный справочник команд, архитектурный контекст и соглашения, необходимые для работы без угадывания.

### 2. Конвейер JSON-вывода

Когда агенты вызывают `rdc` в подоболочке, вывод автоматически переключается на JSON (определение не-TTY). Каждый JSON-ответ использует единообразный конверт:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Ответы с ошибками включают поля `retryable` и `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Обнаружение возможностей агента

Подкоманда `rdc agent` предоставляет структурированную интроспекцию:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Ключевые флаги для агентов

| Флаг | Назначение |
|------|---------|
| `--output json` / `-o json` | Машиночитаемый JSON-вывод |
| `--yes` / `-y` | Пропуск интерактивных подтверждений |
| `--quiet` / `-q` | Подавление информационного вывода в stderr |
| `--fields name,status` | Ограничение вывода определёнными полями |
| `--dry-run` | Предварительный просмотр деструктивных операций без выполнения |

## Безопасность и ограждения

CLI не приравнивает агентов к человеку за терминалом. Для чувствительных операций требуется подтверждение знания текущего состояния (флаг `--current`), интерактивные потоки с редактором по умолчанию отклоняются, и каждый отказ фиксируется в журнале аудита. Справочник [Безопасность и ограждения AI-агентов](/ru/docs/ai-agents-safety) охватывает полную таблицу правил, модель knowledge-gate, переопределение области действия `REDIACC_ALLOW_CONFIG_EDIT` и журнал аудита с хеш-цепочкой.

## Следующие шаги

- [Безопасность и ограждения AI-агентов](/ru/docs/ai-agents-safety), что агенты могут и не могут делать, knowledge-gate, журнал аудита
- [Руководство по настройке Claude Code](/ru/docs/ai-agents-claude-code), пошаговая настройка Claude Code
- [Руководство по настройке Cursor](/ru/docs/ai-agents-cursor), интеграция с Cursor IDE
- [Справочник по JSON-выводу](/ru/docs/ai-agents-json-output), полная документация JSON-вывода
- [Шаблон AGENTS.md](/ru/docs/agents-md-template), готовый шаблон конфигурации агента
