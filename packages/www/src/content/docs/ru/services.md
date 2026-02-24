---
title: Сервисы
description: >-
  Развертывание и управление контейнеризированными сервисами с помощью
  Rediaccfile, сетевого взаимодействия и автозапуска.
category: Guides
order: 5
language: ru
sourceHash: 294f92dc32f10c86
---

# Сервисы

Если вы не уверены, какой инструмент использовать, см. [rdc vs renet](/ru/docs/rdc-vs-renet).

На этой странице описывается развертывание и управление контейнеризированными сервисами: Rediaccfile, сетевое взаимодействие сервисов, запуск/остановка, массовые операции и автозапуск.

## Rediaccfile

**Rediaccfile** — это Bash-скрипт, определяющий, как ваши сервисы подготавливаются, запускаются и останавливаются. Он должен называться `Rediaccfile` или `rediaccfile` (регистр не имеет значения) и размещаться внутри смонтированной файловой системы репозитория.

Rediaccfile обнаруживается в двух местах:
1. В **корне** пути монтирования репозитория
2. В **поддиректориях первого уровня** пути монтирования (не рекурсивно)

Скрытые директории (имена начинаются с `.`) пропускаются.

### Функции жизненного цикла

Rediaccfile содержит до трех функций:

| Функция | Когда выполняется | Назначение | Поведение при ошибке |
|---------|-------------------|------------|----------------------|
| `prep()` | Перед `up()` | Установка зависимостей, загрузка образов, выполнение миграций | **Немедленная остановка** — если любой `prep()` завершится с ошибкой, весь процесс немедленно останавливается |
| `up()` | После завершения всех `prep()` | Запуск сервисов (например, `docker compose up -d`) | Ошибка корневого Rediaccfile — **критическая** (останавливает всё). Ошибки в поддиректориях — **некритические** (логируются, продолжение к следующему) |
| `down()` | При остановке | Остановка сервисов (например, `docker compose down`) | **Максимальные усилия** — ошибки логируются, но все Rediaccfile всегда обрабатываются |

Все три функции необязательны. Если функция не определена в Rediaccfile, она тихо пропускается.

### Порядок выполнения

- **Запуск (`up`):** Сначала корневой Rediaccfile, затем поддиректории в **алфавитном порядке** (от A до Z).
- **Остановка (`down`):** Поддиректории в **обратном алфавитном порядке** (от Z до A), затем корневой последним.

### Переменные окружения

При выполнении функции Rediaccfile доступны следующие переменные окружения:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `REPOSITORY_PATH` | Путь монтирования репозитория | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | GUID репозитория | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | Идентификатор сети (целое число) | `2816` |
| `DOCKER_HOST` | Docker-сокет для изолированного демона данного репозитория | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | Loopback IP для каждого сервиса, определенного в `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Переменные `{SERVICE}_IP` автоматически генерируются из `.rediacc.json`. Соглашение об именовании преобразует имя сервиса в верхний регистр с заменой дефисов на подчеркивания, а затем добавляет `_IP`. Например, `listmonk-app` становится `LISTMONK_APP_IP`.

> **Предупреждение: Не используйте `sudo docker` в Rediaccfile.** Команда `sudo` сбрасывает переменные окружения, из-за чего теряется `DOCKER_HOST` и команды Docker обращаются к системному демону вместо изолированного демона репозитория. Это нарушает изоляцию контейнеров и может вызвать конфликты портов. Rediacc автоматически блокирует выполнение при обнаружении `sudo docker` без `-E`.
>
> Используйте `renet compose` в ваших Rediaccfile — он автоматически обрабатывает `DOCKER_HOST`, внедряет сетевые метки для обнаружения маршрутов и настраивает сетевое взаимодействие сервисов. Подробнее о том, как сервисы предоставляются через обратный прокси, см. в разделе [Сетевое взаимодействие](/ru/docs/networking). Если вы вызываете Docker напрямую, используйте `docker` без `sudo` — функции Rediaccfile уже запускаются с достаточными привилегиями. Если необходимо использовать sudo, применяйте `sudo -E docker` для сохранения переменных окружения.

### Пример

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` тоже работает, поскольку `DOCKER_HOST` устанавливается автоматически, но `renet compose` предпочтительнее, так как дополнительно внедряет метки `rediacc.*`, необходимые для обнаружения маршрутов обратным прокси. Подробнее см. в разделе [Сетевое взаимодействие](/ru/docs/networking).

### Пример с несколькими сервисами

Для проектов с несколькими независимыми группами сервисов используйте поддиректории:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Корневой: общая настройка
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Сервисы базы данных
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API-сервер
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana и т.д.
    └── docker-compose.yml
```

Порядок выполнения для `up`: корневой, затем `backend`, `database`, `monitoring` (A-Z).
Порядок выполнения для `down`: `monitoring`, `database`, `backend`, затем корневой (Z-A).

## Сетевое взаимодействие сервисов (.rediacc.json)

Каждый репозиторий получает подсеть /26 (64 IP-адреса) в loopback-диапазоне `127.x.x.x`. Сервисы привязываются к уникальным loopback IP-адресам, что позволяет им работать на одних и тех же портах без конфликтов.

### Файл .rediacc.json

Сопоставляет имена сервисов с номерами **слотов**. Каждый слот соответствует уникальному IP-адресу в подсети репозитория.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Автоматическая генерация из Docker Compose

Вам не нужно создавать `.rediacc.json` вручную. При выполнении `rdc repo up` Rediacc автоматически:

1. Сканирует все директории, содержащие Rediaccfile, на наличие compose-файлов (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` или `compose.yaml`)
2. Извлекает имена сервисов из секции `services:`
3. Назначает следующий доступный слот каждому новому сервису
4. Сохраняет результат в `{repository}/.rediacc.json`

### Вычисление IP-адресов

IP-адрес сервиса вычисляется из идентификатора сети репозитория и слота сервиса. Идентификатор сети распределяется по второму, третьему и четвёртому октетам loopback-адреса `127.x.y.z`. Каждый сервис получает смещение `slot + 2` (смещения 0 и 1 зарезервированы).

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Пример** для идентификатора сети `2816` (`0x0B00`), базовый адрес `127.0.11.0`:

| Сервис | Слот | IP-адрес |
|--------|------|----------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Каждый репозиторий поддерживает до **61 сервиса** (слоты от 0 до 60).

### Использование IP-адресов сервисов в Docker Compose

Поскольку каждый репозиторий работает с изолированным Docker-демоном, сервисы используют `network_mode: host` и привязываются к назначенным loopback IP-адресам:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## Запуск сервисов

Смонтируйте репозиторий и запустите все сервисы:

```bash
rdc repo up my-app -m server-1 --mount
```

| Опция | Описание |
|-------|----------|
| `--mount` | Сначала смонтировать репозиторий, если он еще не смонтирован |
| `--prep-only` | Выполнить только функции `prep()`, пропустить `up()` |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Последовательность выполнения:
1. Монтирование LUKS-зашифрованного репозитория (если указан `--mount`)
2. Запуск изолированного Docker-демона
3. Автоматическая генерация `.rediacc.json` из compose-файлов
4. Выполнение `prep()` во всех Rediaccfile (в алфавитном порядке, с немедленной остановкой при ошибке)
5. Выполнение `up()` во всех Rediaccfile (в алфавитном порядке)

## Остановка сервисов

```bash
rdc repo down my-app -m server-1
```

| Опция | Описание |
|-------|----------|
| `--unmount` | Размонтировать зашифрованный репозиторий после остановки сервисов. Если это не вступит в силу, используйте `rdc repo unmount` отдельно. |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Последовательность выполнения:
1. Выполнение `down()` во всех Rediaccfile (в обратном алфавитном порядке, максимальные усилия)
2. Остановка изолированного Docker-демона (если указан `--unmount`)
3. Размонтирование и закрытие LUKS-зашифрованного тома (если указан `--unmount`)

## Массовые операции

Запуск или остановка всех репозиториев на машине одновременно:

```bash
rdc repo up-all -m server-1
```

| Опция | Описание |
|-------|----------|
| `--include-forks` | Включить форкнутые репозитории |
| `--mount-only` | Только смонтировать, не запускать контейнеры |
| `--dry-run` | Показать, что будет выполнено |
| `--parallel` | Выполнять операции параллельно |
| `--concurrency <n>` | Максимальное количество параллельных операций (по умолчанию: 3) |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Автозапуск при загрузке

По умолчанию репозитории необходимо вручную монтировать и запускать после перезагрузки сервера. **Автозапуск** настраивает репозитории на автоматическое монтирование, запуск Docker и выполнение Rediaccfile `up()` при загрузке сервера.

### Как это работает

При включении автозапуска для репозитория:

1. Генерируется случайный LUKS-ключевой файл размером 256 байт и добавляется в LUKS-слот 1 репозитория (слот 0 остается для пользовательской парольной фразы)
2. Ключевой файл сохраняется по пути `{datastore}/.credentials/keys/{guid}.key` с правами `0600` (только root)
3. Устанавливается systemd-сервис (`rediacc-autostart`), который при загрузке монтирует все включенные репозитории и запускает их сервисы

При завершении работы или перезагрузке системы сервис корректно останавливает все сервисы (Rediaccfile `down()`), останавливает Docker-демоны и закрывает тома LUKS.

> **Примечание по безопасности:** Включение автозапуска сохраняет LUKS-ключевой файл на диске сервера. Любой пользователь с root-доступом к серверу может смонтировать репозиторий без парольной фразы. Оцените это с учетом вашей модели угроз.

### Включение

```bash
rdc repo autostart enable my-app -m server-1
```

Вам будет предложено ввести парольную фразу репозитория.

### Включение для всех репозиториев

```bash
rdc repo autostart enable-all -m server-1
```

### Отключение

```bash
rdc repo autostart disable my-app -m server-1
```

Эта команда удаляет ключевой файл и деактивирует LUKS-слот 1.

### Список статусов

```bash
rdc repo autostart list -m server-1
```

## Полный пример

Этот пример развертывает веб-приложение с PostgreSQL, Redis и API-сервером.

### 1. Настройка

```bash
curl -fsSL https://get.rediacc.com | sh
rdc config init production --ssh-key ~/.ssh/id_ed25519
rdc config add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc config setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Монтирование и подготовка

```bash
rdc repo mount webapp -m prod-1
```

### 3. Создание файлов приложения

Внутри репозитория создайте:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Запуск

```bash
rdc repo up webapp -m prod-1
```

### 5. Включение автозапуска

```bash
rdc repo autostart enable webapp -m prod-1
```
