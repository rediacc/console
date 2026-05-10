---
title: "Продакшен-режим"
description: "Запустите приложение независимо от ноутбука и настройте автозапуск после перезагрузки сервера."
category: "Tutorials"
subcategory: advanced
order: 10
language: ru
sourceHash: "0e070fcd877900ab"
---

# Продакшен-режим

До сих пор вы запускали приложение командой `renet dev up` изнутри репозитория. Для разработки это отлично. Для продакшена вы управляете всем с ноутбука через `rdc`. Закройте ноутбук: приложение продолжит работать.

## Смотреть урок

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Dev против prod

Разница проста:

- `renet dev up` работает **внутри репозитория**. Нужно оставаться подключённым.
- `rdc repo up` работает **с ноутбука**. После этого соединение не нужно.

Три действия переводят вас из dev в prod:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Шаг 1: Остановка dev-сессии

Подключитесь к репозиторию и остановите его:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Шаг 2: Запуск в продакшен-режиме

Из терминала ноутбука:

```bash
time rdc repo up --name my-app -m my-server
```

Готово. Приложение работает, и вы можете закрыть ноутбук. `Rediaccfile` берёт на себя всё. `rdc repo up` вызывает ту же функцию `up`, что и `renet dev up`. Тот же `Rediaccfile`, другой способ вызова.

## Шаг 3: Выживание после перезагрузки сервера

Убедитесь, что приложение автоматически восстановится при перезапуске сервера:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Проверьте, у каких репозиториев включён автозапуск:

```bash
time rdc repo autostart list -m my-server
```

## Остановка в продакшене

Когда нужно остановить приложение:

```bash
time rdc repo down --name my-app -m my-server
```

Одна команда для запуска, одна для остановки. Всё с ноутбука.

---

Далее: [Резервное копирование и восстановление](/en/docs/tutorial-backup-restore).
