---
title: Шпаргалка RDC CLI
description: >-
  Краткий справочник по всем командам rdc, конфигурации, репозиториям, машинам,
  синхронизации, контейнерам и многому другому.
category: Guides
order: 3
language: ru
sourceHash: "12956297c1157cd2"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Шпаргалка RDC CLI

Краткий справочник по наиболее часто используемым командам `rdc`. Запустите любую команду с `--help` для просмотра всех параметров.

## Жизненный цикл репозитория

| Команда | Описание |
|---------|----------|
| `rdc repo create --name <repo> -m <machine>` | Создать новый репозиторий на машине |
| `rdc repo up --name <repo> -m <machine>` | Развернуть или обновить репозиторий |
| `rdc repo down --name <repo> -m <machine>` | Остановить репозиторий |
| `rdc repo delete --name <repo> -m <machine>` | Удалить репозиторий |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Создать форк репозитория (почти мгновенно, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Взять на себя управление существующим репозиторием |
| `rdc config repository list` | Вывести список всех репозиториев с именем и GUID |

## Резервное копирование и восстановление

| Команда | Описание |
|---------|----------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Отправить резервную копию репозитория в хранилище |
| `rdc repo push --to <storage> -m <machine>` | Отправить все репозитории в хранилище |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Восстановить репозиторий из хранилища |
| `rdc repo pull --from <storage> -m <machine>` | Восстановить все репозитории из хранилища |
| `rdc repo push ... --bwlimit <limit>` | Ограничить пропускную способность rsync при отправке (например, `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Ограничить пропускную способность rsync при получении |
| `rdc repo push ... --checkpoint` | Создать контрольную точку контейнеров перед отправкой |
| `rdc repo backup list --from <storage> -m <machine>` | Вывести список доступных резервных копий в хранилище |
| `rdc storage browse --name <storage>` | Просмотреть содержимое хранилища |

## Миграция репозитория

| Команда | Описание |
|---------|----------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Перенести репозиторий между машинами |
| `rdc repo migrate ... --provision` | Подготовить целевую машину перед переносом |
| `rdc repo migrate ... --checkpoint` | Создать контрольную точку перед миграцией |
| `rdc repo migrate ... --skip-dns` | Пропустить обновление DNS после миграции |
| `rdc repo migrate ... --bwlimit <limit>` | Ограничить пропускную способность передачи |

## Стратегии резервного копирования

| Команда | Описание |
|---------|----------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Создать или обновить именованную стратегию резервного копирования |
| `rdc config backup-strategy list` | Вывести список всех определённых стратегий |
| `rdc config backup-strategy show --name <name>` | Показать детали стратегии |
| `rdc config backup-strategy remove --name <name>` | Удалить стратегию |
| `rdc machine backup schedule -m <machine>` | Развернуть настроенные стратегии резервного копирования на машине |

## Операции резервного копирования

| Команда | Описание |
|---------|----------|
| `rdc machine backup schedule -m <machine>` | Развернуть привязанные стратегии как таймеры systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Предварительный просмотр единиц таймера без развёртывания (токены скрыты) |
| `rdc machine backup now -m <machine>` | Немедленно запустить все привязанные стратегии |
| `rdc machine backup now -m <machine> --strategy <name>` | Немедленно запустить конкретную стратегию |
| `rdc machine backup status -m <machine>` | Показать состояние таймеров и результаты последних задач |
| `rdc machine backup status -m <machine> --strategy <name>` | Показать состояние конкретной стратегии |
| `rdc machine backup cancel -m <machine>` | Отменить выполняющееся резервное копирование |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Отменить конкретное выполняющееся резервное копирование |

## Управление машинами

| Команда | Описание |
|---------|----------|
| `rdc machine query --name <machine>` | Полный статус машины (система, контейнеры, сервисы, репозитории, сеть) |
| `rdc machine query --name <machine> --system` | Только информация о системе |
| `rdc machine query --name <machine> --containers` | Только список контейнеров |
| `rdc machine query --name <machine> --repositories` | Только список репозиториев |
| `rdc machine query --name <machine> --services` | Только список сервисов |
| `rdc machine query --name <machine> --network` | Только сетевая информация |
| `rdc machine query --name <machine> --block-devices` | Только информация о блочных устройствах |
| `rdc machine list` | Вывести список всех машин в конфигурации |
| `rdc config machine setup --name <machine>` | Запустить первоначальное развёртывание машины |
| `rdc machine prune --name <machine>` | Удалить неиспользуемые ресурсы с машины |
| `rdc machine deprovision --name <machine>` | Полностью депровизионировать машину |
| `rdc machine vault-status --name <machine>` | Показать состояние хранилища LUKS |

## Терминал и синхронизация

| Команда | Описание |
|---------|----------|
| `rdc term connect -m <machine>` | Открыть SSH-терминал к машине |
| `rdc term connect -m <machine> -r <repo>` | Открыть SSH-терминал к репозиторию (устанавливает DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Выполнить команду на машине |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Загрузить файл, каталог или несколько источников в репозиторий |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Скачать каталог репозитория локально |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Скачать один файл из репозитория в локальный каталог |
| `rdc vscode connect -m <machine> -r <repo>` | Открыть сеанс VS Code Remote SSH |

## Конфигурация

| Команда | Описание |
|---------|----------|
| `rdc config init --name <name>` | Создать именованный файл конфигурации |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Добавить машину в конфигурацию |
| `rdc config storage import --file rclone.conf` | Импортировать провайдеров хранилища из конфигурации rclone |
| `rdc config storage list` | Вывести список настроенных провайдеров хранилища |
| `rdc config backup-strategy set ...` | Определить именованную стратегию резервного копирования |
| `rdc --config <name> <command>` | Использовать именованный файл конфигурации |

## Отладка и прямой доступ

| Команда | Описание |
|---------|----------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Вывести список контейнеров в репозитории |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Получить журналы контейнера |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Выполнить команду в контейнере |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Перезапустить контейнер |
