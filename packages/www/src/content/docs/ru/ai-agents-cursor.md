---
title: Руководство по настройке Cursor
description: Настройка Cursor IDE для работы с инфраструктурой Rediacc с помощью .cursorrules и интеграции терминала.
category: Guides
order: 32
language: ru
sourceHash: "b5e835461de00400"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Кратко: `.cursorrules` загружает контекст Rediacc в AI Cursor, а терминал позволяет выполнять команды `rdc` на ваших реальных машинах.

## Быстрая настройка

1. Установите CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Скопируйте [шаблон AGENTS.md](/ru/docs/agents-md-template) в корень проекта как `.cursorrules`
3. Откройте проект в Cursor

Cursor читает `.cursorrules` при запуске. Важный момент: действуют ограничения контекстного окна, поэтому держите файл сфокусированным на ваших конкретных машинах и репозиториях, не засоряйте его общими шаблонами.

## Настройка .cursorrules

Создайте `.cursorrules` в корне проекта с контекстом инфраструктуры Rediacc. Полную версию см. в [шаблоне AGENTS.md](/ru/docs/agents-md-template).

Ключевые разделы для включения:

- Название CLI-инструмента (`rdc`) и установка
- Основные команды с флагом `--output json`
- Обзор архитектуры (изоляция репозиториев, Docker-демоны)
- Правила терминологии (адаптеры, а не режимы)

## Интеграция терминала

Cursor может выполнять команды `rdc` через встроенный терминал. Типичные сценарии:

### Проверка статуса

Спросите Cursor: *«Проверь статус моего продакшен-сервера»*

Cursor выполняет в терминале:
```bash
rdc machine query --name prod-1 -o json
```

### Развёртывание изменений

Спросите Cursor: *«Разверни обновлённую конфигурацию nextcloud»*

Cursor выполняет в терминале:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### Просмотр логов

Спросите Cursor: *«Покажи последние логи почтового контейнера»*

Cursor выполняет в терминале:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## Настройки рабочего пространства

Для командных проектов добавьте специфичные для Rediacc настройки Cursor в `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Советы

- Режим Composer в Cursor хорошо подходит для многошаговых инфраструктурных задач
- Используйте `@terminal` в чате Cursor для ссылки на недавний вывод терминала
- Команда `rdc agent capabilities` предоставляет Cursor полный справочник команд
- Сочетание `.cursorrules` с файлом `CLAUDE.md` обеспечивает максимальную совместимость между AI-инструментами
