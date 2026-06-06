---
title: Быстрый старт
description: Запустите контейнерный сервис на вашем сервере за несколько минут.
category: Guides
order: -1
language: ru
sourceHash: "2047fd1ce3a47944"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Быстрый старт

Установите Rediacc на собственный сервер. Зашифрованные, изолированные контейнерные окружения, без облачных аккаунтов и SaaS-зависимостей. Ваше оборудование, ваш контроль.

---

## Введение

### Ключевые концепции

Репозиторий (repo) - это один зашифрованный файл на диске. Перемещайте его, создавайте резервные копии, форкайте. Это просто файл. При монтировании он становится папкой с выделенным Docker-демоном и данными вашего приложения внутри.

Думайте о репозитории как об USB-накопителе: подключите его к любой машине, и приложения с данными смонтируются, готовые к работе. Переносите между машинами или облачными провайдерами, не пересобирая ничего.

**Два инструмента, две роли:**

- **rdc** = CLI на вашем ноутбуке (TypeScript, устанавливается глобально)
- **renet** = оркестратор на сервере (Go-бинарник, управляет демонами/сетями/изоляцией)
- RDC автоматически устанавливает renet во время `config machine setup`. Ручная настройка на сервере не требуется.

> [Архитектура](/en/docs/architecture) описывает модель безопасности. [rdc vs renet](/en/docs/rdc-vs-renet) объясняет, какой инструмент когда использовать.

### 1. Установка CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Проверка: Node, SSH-ключ, renet, Docker
```

> Windows, Alpine, Arch: см. [Установка](/en/docs/installation). Полные системные требования: [Требования](/en/docs/requirements).

### 2. Настройка SSH-ключа

rdc подключается по SSH. Сервер должен доверять вашему открытому ключу, прежде чем rdc сможет к нему подключиться.

```bash
# Сгенерировать ключ (пропустите, если он уже есть)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Скопировать открытый ключ на сервер (потребуется ввести пароль)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Указать rdc, какой ключ использовать
rdc config ssh set --key ~/.ssh/id_ed25519
```

Теперь каждая команда rdc аутентифицируется с помощью этого ключа. Без паролей.

### 3. Добавление сервера

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # Устанавливает renet + создаёт хранилище данных
```

**Что происходит:** сканируется ключ хоста SSH, загружается бинарник renet, на сервере инициализируется зашифрованное хранилище данных. Готово к созданию репозиториев.

> Размер хранилища, Ceph RBD, облачные провайдеры: [Настройка машины](/en/docs/setup). Ошибки SSH: [Устранение неполадок](/en/docs/troubleshooting).

### 4. Файл конфигурации

```bash
rdc config show                            # Удобочитаемая сводка
cat ~/.config/rediacc/rediacc.json         # Исходный JSON: машины, репозитории, хранилища, SSH-ключ
```

**Один файл = одно окружение.** Скопируйте его на другой ноутбук, и всё готово к работе.

---

## Работа с репозиторием

### 1. Создание репозитория

```bash
rdc repo create --name my-app -m my-server --size 2G  # Создать зашифрованный репозиторий на 2 ГБ
```

Создаёт зашифрованный том, монтирует его и запускает Docker-демон. Репозиторий регистрируется в вашей конфигурации и готов к использованию.

> Изменение размера, удаление, валидация: [Репозитории](/en/docs/repositories).

### 2. Применение шаблона

```bash
rdc repo template list                                        # Показать встроенные шаблоны
rdc repo template apply --name app-postgres -m my-server -r my-app  # Развернуть docker-compose.yml + Rediaccfile
```

Шаблоны предоставляют `docker-compose.yml`, `Rediaccfile` и вспомогательные файлы. Без шаблона (или собственного compose-файла) запускать нечего. Используйте встроенный шаблон для первого репозитория. Это самый быстрый способ увидеть полный рабочий процесс от начала до конца.

### 3. Запуск репозитория

```bash
rdc repo up --name my-app -m my-server  # Выполнить Rediaccfile up()
rdc repo list -m my-server                           # Список всех репозиториев на машине
rdc repo status --name my-app -m my-server  # Состояние монтирования, Docker, размер, шифрование
```

`repo up` автоматически монтирует при необходимости. Дополнительные флаги не требуются.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # Открывает VS Code через SSH внутри песочницы репозитория
```

Вы редактируете файлы *внутри* зашифрованного тома. `docker ps` показывает только контейнеры этого репозитория. Сохраняйте, запускайте compose up, итерируйте.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Где запускаете** | На вашем ноутбуке (CLI) | Внутри песочницы VS Code |
| **Что делает** | SSH -> автомонтирование -> выполнение Rediaccfile `up()` | Выполняет Rediaccfile `up()` напрямую |
| **Сценарий использования** | CI/CD, автоматизация, удалённые операции | Внутренний цикл разработчика |
| **Изоляция** | Оркестрация снаружи | Уже внутри песочницы |

**Демонстрационный процесс:** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → редактирование `docker-compose.yml` → `renet dev up` → приложение работает → итерация.

> Структура Rediaccfile: [Сервисы](/en/docs/services). Когда какой инструмент использовать: [rdc vs renet](/en/docs/rdc-vs-renet).

### 6. Модель изоляции

- **Универсальный пользователь** (`rediacc`): одинаковый UID на каждой машине. Перенесите репозиторий на другой сервер, и владение файлами просто работает. Никаких проблем с `chown`.
- **Отдельный Docker-демон для каждого репозитория**: каждый репозиторий получает собственный изолированный Docker-демон. `docker ps` показывает только контейнеры ЭТОГО репозитория.
- **Песочница Landlock + OverlayFS**: оболочка VS Code ограничена файловой системой. Вы не можете читать другие репозитории. Записи в `$HOME` используют оверлеи для каждого репозитория.

> Как работает изоляция: [Архитектура](/en/docs/architecture). Жизненный цикл Rediaccfile: [Сервисы](/en/docs/services).

### 7. Терминал, синхронизация и туннель

**Терминал:**
```bash
rdc term connect -m my-server -r my-app                            # SSH в песочницу репозитория
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # Выполнить команду и выйти
rdc term connect -m my-server                                   # SSH на машину (без песочницы)
```

**Синхронизация файлов (rsync через SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # Загрузить каталог
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # Загрузить один файл
rdc repo sync download -m my-server -r my-app --local ./backup                              # Скачать каталог
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # Скачать один файл
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # Предварительный просмотр
```

**Туннель (SSH-проброс порта к контейнеру):**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # Автоопределение порта для контейнера app
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # Туннель к Postgres
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # Свой локальный порт
```

Запустите туннель -> откройте `localhost:3000` в браузере -> живое приложение с удалённого сервера.

> Синхронизация, терминал, подробности VS Code: [Инструменты](/en/docs/tools).

---

## Форк и резервное копирование

### 1. Гранд и форк репозиториев

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # Мгновенный CoW-клон + запуск
rdc repo list -m my-server                                  # Показывает: my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # Удалить форк, гранд не затронут
```

**Мгновенное клонирование без копирования.** CoW (copy-on-write). Микросекунды, данные не копируются. Блоки разделяются, пока одна из сторон не выполнит запись.

**Сценарии использования:**
- **AI / ML:** форк продакшен-датасета, запуск эксперимента, отмена или продвижение
- **DevOps:** форк -> тестирование миграции -> удаление при неудаче, продвижение при успехе
- **Резервное копирование:** форк = мгновенный снимок, отправка во внешнее хранилище

> Жизненный цикл форков, кросс-машинные форки: [Репозитории](/en/docs/repositories).

### 2. Отправка на другую машину

```bash
# Отправить репозиторий на другую машину
rdc repo push --name my-app -m my-server --to backup-server

# Отправить и автоматически развернуть на целевой машине
rdc repo push --name my-app -m my-server --to backup-server --up

# Отправить с CRIU-чекпоинтом (живая миграция, сохранение состояния памяти)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# Отправить на новую машину (автоматическое создание через облачного провайдера)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. Отправка в облачное хранилище (OneDrive, Google Drive, S3)

```bash
# Импортировать конфигурацию rclone как бэкенд хранилища
rdc config storage import --file ~/rclone.conf

# Список доступных хранилищ
rdc storage list

# Отправить репозиторий в облачное хранилище
rdc repo push --name my-app -m my-server --to my-s3-backup

# Список резервных копий в хранилище
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` автоматически определяет, является ли цель машиной или бэкендом хранилища. Работает с любым провайдером, поддерживаемым rclone: S3, R2, B2, OneDrive, Google Drive, SFTP и т.д.

### 4. Получение с удалённого источника

```bash
# Получить репозиторий с облачной машины на локальный сервер
rdc repo pull --name my-app -m my-local-server --from cloud-server

# Получить из облачного хранилища
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# Получить и сразу запустить
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**Зачем pull?** Ваша локальная машина за NAT. Облако не может отправить данные вам. Но вы можете обратиться к облаку. Pull доставляет репозиторий домой.

**Полный цикл:** создание на dev -> отправка в облако -> получение на production -> `--up`. Один репозиторий, любая машина, любое облако.

> Планирование, автоматическое резервное копирование, восстановление: [Резервное копирование и восстановление](/en/docs/backup-restore).

---

## Прокси и SSL

### 1. Конфигурация инфраструктуры

```bash
rdc config infra set -m my-server  # Настроить: базовый домен, публичные IP, диапазоны портов
rdc config infra show -m my-server  # Просмотр конфигурации
rdc config infra push -m my-server  # Отправить конфигурацию прокси на удалённый сервер
```

**Как работает маршрутизация:**
- Traefik автоматически обнаруживает контейнеры через метки `rediacc.service_name` и `rediacc.service_port`
- Маршруты: `{service}-{networkId}.{baseDomain}` -> IP контейнера:порт
- SSL: Let's Encrypt через Cloudflare DNS-01 challenge (автопродление, wildcard-сертификаты)

### 2. Шаблон прокси

```bash
rdc repo template apply --name proxy -m my-server -r infra  # Развернуть прокси в репозитории
rdc repo up --name infra -m my-server  # Запустить Traefik
```

Теперь Traefik маршрутизирует внешний трафик ко всем репозиториям на этой машине. Каждый контейнер автоматически получает HTTPS-эндпоинт.

```bash
# Перейдите на https://my-app.example.com -> маршрутизация к контейнеру
# TCP/UDP-проброс для баз данных:
#   rediacc.tcp_ports=3306,5432 -> автоматически выделенные внешние порты
```

> Правила маршрутизации, DNS, настройка TLS: [Сеть](/en/docs/networking).

---

## Дальнейшие шаги

- **[Руководство по миграции](/en/docs/migration)** - Перенос существующих проектов в репозитории Rediacc
- **[Мониторинг](/en/docs/monitoring)** - Состояние машины, контейнеры, сервисы, диагностика
- **[Справочник CLI](/en/docs/cli-application)** - Полный справочник команд
- **[Шпаргалка](/en/docs/rdc-cheat-sheet)** - Быстрый поиск команд
- **[Устранение неполадок](/en/docs/troubleshooting)** - Решения для распространённых проблем
- **[Правила Rediacc](/en/docs/rules-of-rediacc)** - Лучшие практики Rediaccfile и чеклист развёртывания
