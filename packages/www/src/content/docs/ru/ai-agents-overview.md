---
title: Обзор интеграции с AI-агентами
description: Как AI-ассистенты для кодирования, такие как Claude Code, Cursor и Cline, интегрируются с инфраструктурой Rediacc для автономного развёртывания и управления.
category: Guides
order: 30
language: ru
sourceHash: "3374e0f154375ffb"
---

AI-ассистенты для кодирования могут автономно управлять инфраструктурой Rediacc через CLI `rdc`. Это руководство описывает подходы к интеграции и начало работы.

## Почему самостоятельный хостинг + AI-агенты

Архитектура Rediacc изначально дружественна к агентам:

- **CLI в первую очередь**: каждая операция — это команда `rdc`, GUI не требуется
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

Это даёт агенту полный контекст о доступных командах, архитектуре и соглашениях.

### 2. Конвейер JSON-вывода

Когда агенты вызывают `rdc` в подоболочке, вывод автоматически переключается на JSON (определение не-TTY). Каждый JSON-ответ использует единообразный конверт:

```json
{
  "success": true,
  "command": "machine info",
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
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. Обнаружение возможностей агента

Подкоманда `rdc agent` предоставляет структурированную интроспекцию:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## Ключевые флаги для агентов

| Флаг | Назначение |
|------|---------|
| `--output json` / `-o json` | Машиночитаемый JSON-вывод |
| `--yes` / `-y` | Пропуск интерактивных подтверждений |
| `--quiet` / `-q` | Подавление информационного вывода в stderr |
| `--fields name,status` | Ограничение вывода определёнными полями |
| `--dry-run` | Предварительный просмотр деструктивных операций без выполнения |

## Следующие шаги

- [Руководство по настройке Claude Code](/ru/docs/ai-agents-claude-code) — пошаговая настройка Claude Code
- [Руководство по настройке Cursor](/ru/docs/ai-agents-cursor) — интеграция Cursor IDE
- [Справочник по JSON-выводу](/ru/docs/ai-agents-json-output) — полная документация JSON-вывода
- [Шаблон AGENTS.md](/ru/docs/agents-md-template) — готовый шаблон конфигурации агента
