---
title: rdc vs renet
description: 'Когда использовать rdc, а когда renet.'
category: Concepts
order: 1
language: ru
sourceHash: e0ef5f051cefb407
---

# rdc vs renet

У Rediacc два исполняемых файла. Вот когда использовать каждый из них.

| | rdc | renet |
|---|-----|-------|
| **Запускается на** | Вашей рабочей станции | Удалённом сервере |
| **Подключается через** | SSH | Запускается локально с правами root |
| **Используется** | Всеми | Только для расширенной отладки |
| **Установка** | Вы устанавливаете | `rdc` устанавливает автоматически |

> Для повседневной работы используйте `rdc`. Прямой доступ к `renet` требуется редко.

## Как они работают вместе

`rdc` подключается к вашему серверу по SSH и выполняет команды `renet` за вас. Вы вводите одну команду на рабочей станции, а `rdc` делает всё остальное:

1. Читает локальную конфигурацию (`~/.rediacc/rediacc.json`)
2. Подключается к серверу по SSH
3. Обновляет бинарный файл `renet` при необходимости
4. Выполняет соответствующую операцию `renet` на сервере
5. Возвращает результат в ваш терминал

## Используйте `rdc` для обычной работы

Все стандартные задачи выполняются через `rdc` на вашей рабочей станции:

```bash
# Set up a new server
rdc config setup-machine server-1

# Create and start a repository
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Stop a repository
rdc repo down my-app -m server-1

# Check machine health
rdc machine health server-1
```

Подробное пошаговое руководство см. в разделе [Быстрый старт](/ru/docs/quick-start).

## Используйте `renet` для отладки на сервере

Прямой доступ к `renet` нужен только при подключении к серверу по SSH для:

- Экстренной отладки, когда `rdc` не может подключиться
- Проверки системных внутренностей, недоступных через `rdc`
- Низкоуровневых операций восстановления

Все команды `renet` требуют привилегий root (`sudo`). Полный список команд `renet` см. в разделе [Справочник по серверу](/ru/docs/server-reference).

## Экспериментальный режим: `rdc ops` (локальные VM)

`rdc ops` является обёрткой для `renet ops` и позволяет управлять локальными кластерами VM на вашей рабочей станции:

```bash
rdc ops setup              # Install prerequisites (KVM or QEMU)
rdc ops up --basic         # Start a minimal cluster
rdc ops status             # Check VM status
rdc ops ssh 1              # SSH into bridge VM
rdc ops ssh 1 hostname     # Run a command on bridge VM
rdc ops down               # Destroy cluster
```

> Требуется локальный адаптер. Недоступен с облачным адаптером.

Эти команды запускают `renet` локально (не через SSH). Полную документацию см. в разделе [Экспериментальные VM](/ru/docs/experimental-vms).

## Примечание о Rediaccfile

Вы можете увидеть `renet compose -- ...` внутри `Rediaccfile`. Это нормально — функции Rediaccfile выполняются на сервере, где доступен `renet`.

С вашей рабочей станции запускайте и останавливайте рабочие нагрузки командами `rdc repo up` и `rdc repo down`.
