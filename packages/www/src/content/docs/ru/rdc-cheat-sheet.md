---
title: Шпаргалка по CLI RDC
description: "Краткая справка по rdc: конфиги, репозитории, машины, синхронизация файлов и контейнеры. Полный набор опций: добавьте --help к любой команде."
category: Guides
tags:
  - cli
subcategory: cli-tools
order: 3
cardGrid: true
language: ru
sourceHash: "14ed5791afa44326"
sourceCommit: "45cd71f8a80949d4cd621f233377c48715bbf531"
---

# Шпаргалка по CLI RDC

Здесь приведены не все команды `rdc`, а только те, которые встречаются при каждом развертывании. Для полного набора опций запустите любую команду rdc с флагом `--help`. Граничные случаи и редко используемые опции описаны в полной справке.

## Жизненный цикл репозитория

| Команда | Описание |
|---------|----------|
| `rdc repo create <repo> -m <machine>` | Создать новый репозиторий на машине |
| `rdc repo up <repo>@<machine>` | Развернуть или обновить репозиторий |
| `rdc repo down <repo>@<machine>` | Остановить репозиторий |
| `rdc repo delete <repo>@<machine>` | Удалить репозиторий |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Создать форк репозитория (мгновенно, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Повысить проверенный форк до продакшена под именем родительского репозитория |
| `rdc repo list` | Список всех репозиториев с именем и GUID |
| `rdc repo resize <repo> --size <size>` | Изменить размер тома остановленного репозитория |
| `rdc repo expand <repo> --size <size>` | Увеличить том работающего репозитория на месте |

## Секреты репозитория

Учетные данные с доступом только на запись при развертывании. `get` возвращает только дайджест. Значение никогда не возвращается. Полное руководство см. в разделе [Repositories § Secrets](/en/docs/repositories#secrets).

| Команда | Описание |
|---------|----------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Создать новый секрет (`--current ""` при первой записи) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Перезаписать существующий секрет (проверка как при смене пароля) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Перезаписать без проверки предыдущего значения (учитывается как ротация) |
| `rdc repo secret list <repo>` | Список имен секретов и режимов доставки (значения и дайджесты не показываются) |
| `rdc repo secret get <repo> --key <KEY>` | Показать дайджест секрета и режим (открытые значения никогда не выводятся) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Удалить секрет |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Удалить без проверки предыдущего значения |

> Форки не наследуют секреты. Установите их на форке явно с помощью `rdc repo secret set <repo>:<tag>`.

## Резервная копия и восстановление

| Команда | Описание |
|---------|----------|
| `rdc repo push ... --bwlimit <limit>` | Ограничить пропускную способность rsync при отправке (например `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Ограничить пропускную способность rsync при получении |
| `rdc repo push ... --checkpoint` | Создать контрольную точку контейнеров перед отправкой |
| `rdc backup manifests <repo-ref>` | Список снимков, хранящихся в чанковом хранилище |
| `rdc backup browse <repo-ref>` | Список файлов, содержащихся в репозитории (локально, только для чтения) |
| `rdc backup snapshot <repo>` | Загрузить снимок в чанковое хранилище: сначала полный инвентарь, затем только измененные ячейки |
| `rdc backup snapshot <repo> --dry-run` | Спланировать снимок без загрузки; сообщает, что переместилось бы |
| `rdc backup verify <repo>` | Проверить якорь резервной копии репозитория по чанковому хранилищу |
| `rdc backup usage` | Показать байты, хранящиеся в чанковом хранилище, относительно вашей квоты |
| `rdc backup manifests <repo>` | Список манифестов снимков, зарегистрированных на сервере |
| `rdc storage browse <storage>` | Просмотреть содержимое хранилища |

## Миграция репозитория

| Команда | Описание |
|---------|----------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Переместить репозиторий между машинами |
| `rdc repo migrate ... --provision` | Подготовить целевую машину перед передачей |
| `rdc repo migrate ... --checkpoint` | Создать контрольную точку перед миграцией |
| `rdc repo migrate ... --skip-dns` | Пропустить обновление DNS после миграции |
| `rdc repo migrate ... --bwlimit <limit>` | Ограничить пропускную способность передачи |

## Стратегии резервного копирования

| Команда | Описание |
|---------|----------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Создать или обновить именованную стратегию резервного копирования |
| `rdc backup strategy list` | Список всех определенных стратегий резервного копирования |
| `rdc backup strategy show <name>` | Показать детали стратегии |
| `rdc backup strategy remove <name>` | Удалить стратегию |
| `rdc backup schedule -m <machine>` | Развернуть настроенные стратегии на машине |

## Операции резервного копирования

| Команда | Описание |
|---------|----------|
| `rdc backup schedule -m <machine>` | Развернуть привязанные стратегии как systemd таймеры |
| `rdc backup schedule -m <machine> --dry-run` | Просмотреть модули таймеров без развертывания (токены скрыты) |
| `rdc backup run -m <machine>` | Запустить все привязанные стратегии сразу же |
| `rdc backup run <name> -m <machine>` | Запустить конкретную стратегию немедленно |
| `rdc backup status -m <machine>` | Показать статус таймера и результаты последних работ |
| `rdc backup status <name> -m <machine>` | Показать статус для конкретной стратегии |
| `rdc backup cancel -m <machine>` | Отменить выполняющиеся резервные копии |
| `rdc backup cancel <name> -m <machine>` | Отменить конкретную выполняющуюся резервную копию |

## Управление машинами

| Команда | Описание |
|---------|----------|
| `rdc machine status <machine>` | Полный статус машины (система, контейнеры, сервисы, репозитории, сеть) |
| `rdc machine status <machine> --system` | Только информация о системе |
| `rdc machine status <machine> --containers` | Только список контейнеров |
| `rdc machine status <machine> --repositories` | Только список репозиториев |
| `rdc machine status <machine> --services` | Только список сервисов |
| `rdc machine status <machine> --network` | Только сетевая информация |
| `rdc machine status <machine> --block-devices` | Только информация о блочных устройствах |
| `rdc machine list` | Вывести список всех машин в конфигурации |
| `rdc machine setup <machine>` | Запустить первоначальное развертывание машины |
| `rdc machine health <machine>` | Проверить состояние машины |
| `rdc machine scan-keys <machine>` | Обновить SSH-ключи хоста после пересборки |
| `rdc machine prune <machine>` | Удалить неиспользуемые ресурсы с машины |
| `rdc machine deprovision <machine>` | Полностью депровизионировать машину |

## Терминал и синхронизация

| Команда | Описание |
|---------|----------|
| `rdc term connect <machine>` | Открыть SSH-терминал к машине |
| `rdc term connect <repo>@<machine>` | Открыть SSH-терминал к репозиторию (устанавливает DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Выполнить команду на машине |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Загрузить один или несколько локальных файлов или каталогов в репозиторий |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Загрузить один локальный файл на явно указанный путь в репозитории |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Скачать каталог репозитория локально |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Скачать один файл из репозитория в локальный каталог |
| `rdc vscode connect <repo>@<machine>` | Открыть сеанс VS Code Remote SSH |
| `rdc vscode list` | Список SSH-конфигураций, созданных `vscode connect` |
| `rdc vscode cleanup --all` | Удалить все SSH-конфигурации, записанные `vscode connect` |
| `rdc repo tunnel <repo> -c <container> --port <port>` | Перенаправить порт контейнера через SSH |

## Конфигурация

| Команда | Описание |
|---------|----------|
| `rdc config init <name>` | Создать именованный файл конфигурации |
| `rdc config list` | Вывести список всех конфигураций на этой машине |
| `rdc config set machine <alias>` | Направить алиас на другую машину |
| `rdc machine add <machine> --ip <host> --user <user>` | Добавить машину в конфигурацию |
| `rdc storage import rclone.conf` | Импортировать провайдеров хранилища из конфигурации rclone |
| `rdc storage list` | Вывести список настроенных провайдеров хранилища |
| `rdc backup strategy set ...` | Определить именованную стратегию резервного копирования |
| `rdc --config <name> <command>` | Использовать именованный файл конфигурации |

## Отладка и прямой доступ

| Команда | Описание |
|---------|----------|
| `rdc repo logs <repo>@<machine> -c <container> --lines 200 --follow` | Транслировать журналы контейнера (рекомендуется) |
| `rdc repo exec <repo>@<machine> -c <container> -- <command>` | Выполнить команду в контейнере (рекомендуется) |
| `rdc repo exec <repo>@<machine> -c <container> -i -- bash` | Открыть интерактивную оболочку контейнера |
| `rdc term connect <repo>@<machine> -c "docker ps"` | Вывести список контейнеров в репозитории |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Получить журналы контейнера |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Выполнить команду в контейнере |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Перезапустить контейнер |
