---
title: Руководство по настройке Claude Code
description: >-
  Пошаговое руководство по настройке Claude Code для автономного управления
  инфраструктурой Rediacc.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 31
language: ru
sourceHash: "81cd5da23b9747e0"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
---

Claude Code нативно работает с Rediacc через CLI `rdc`. Это руководство охватывает настройку, разрешения и типичные рабочие процессы.

> **Сначала безопасность**: Прежде чем подключать агента к чему-либо, что касается секретов, прочитайте [Безопасность и ограждения AI-агентов](/ru/docs/ai-agents-safety). Claude Code, запущенный под `rdc`, определяется как агент. Для чувствительных изменений требуется `--current <previous-value>` (предусловие passwd-стиля) как для людей, так и для агентов; `--rotate-secret` (подтверждённая ротация с записью в аудит) засчитывается только человеку в терминале. `rdc config edit` (интерактивный, `--apply`, `--reveal`) отклоняется без какого-либо переопределения, а grand-репозитории и прямой SSH к машине остаются закрытыми, пока человек не даст явное согласие в рамках того, что разрешает политика. Если предусловие не выполнено, поле `errors[].next.options[].run` в JSON-конверте сообщает агенту точную команду CLI, которую стоит предложить пользователю. Передайте её дословно.

## Быстрая настройка

1. Установите CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Скопируйте [шаблон AGENTS.md](/ru/docs/agents-md-template) в корень проекта как `CLAUDE.md`
3. Запустите Claude Code в директории проекта

Claude Code читает `CLAUDE.md` при запуске и использует его как постоянный контекст для всех взаимодействий.

## Настройка CLAUDE.md

Разместите файл в корне проекта. Полную версию см. в [шаблоне AGENTS.md](/ru/docs/agents-md-template). Ключевые разделы:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine|repo-ref>

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Разрешения инструментов

Claude Code запрашивает разрешение на выполнение команд `rdc`. Вы можете предварительно авторизовать частые операции в настройках Claude Code:

- Разрешить `rdc machine status *`, проверка статуса только для чтения
- Разрешить `rdc machine status * --containers`, список контейнеров
- Разрешить `rdc machine health *`, проверки состояния
- Разрешить `rdc repo list`, список репозиториев

Для деструктивных операций (`rdc repo up`, `rdc repo delete`) Claude Code всегда запрашивает подтверждение, если вы явно их не авторизовали.

## Примеры рабочих процессов

### Проверка статуса инфраструктуры

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Развёртывание репозитория

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### Диагностика проблем с контейнерами

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc repo logs nextcloud@prod-1 -c nextcloud-app --lines 50
→ Checks recent logs
```

### Синхронизация файлов

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## Советы

- Claude Code автоматически определяет не-TTY среду и переключается на JSON вывод, в большинстве случаев указывать `-o json` не нужно
- Используйте `rdc --help-all`, чтобы Claude Code мог обнаружить все доступные команды
- Флаг `--fields` помогает снизить использование контекстного окна, когда нужны только определённые данные
