---
title: "Hub"
description: "Предоставляет аутентифицированные контейнерные среды для каждого пользователя с персональными Docker daemon, выбором множества шаблонов, контрольными точками/восстановлением CRIU, журналами аудита и сборкой мусора data-root."
category: "Guides"
order: 14
language: ru
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Hub предоставляет контейнерные среды для каждого пользователя за OAuth-аутентификацией. Пользователи переходят по единому URL, проходят аутентификацию у любого провайдера OAuth2 и прозрачно перенаправляются в свой личный контейнер. Контейнеры создаются по требованию, каждый пользователь получает собственный изолированный Docker daemon, а простаивающие сессии сохраняются через контрольные точки CRIU для мгновенного возобновления.

Всё настраивается через метки `docker-compose.yml`. Сам Hub работает как системный сервис хоста, создаваемый командой `renet hub install` из Compose-файла вашего репозитория. Репозитории определяют поведение; Hub управляет аутентификацией, маршрутизацией, жизненным циклом и изоляцией для каждого пользователя.

## Принцип работы

1. Пользователь переходит по адресу `code.example.com` (или `term.`, `desktop.`, или любому другому настроенному префиксу).
2. Hub проверяет cookie сессии. Если его нет, пользователь перенаправляется к настроенному провайдеру OAuth2 (Nextcloud, Keycloak, GitHub и т. д.).
3. После аутентификации Hub идентифицирует пользователя и ищет его контейнер.
4. Если контейнер не существует, Hub создаёт выделенный Docker daemon для этого пользователя на хосте, а затем запускает его контейнер.
5. Запрос проксируется в контейнер пользователя через loopback-сеть.
6. Простаивающие контейнеры сохраняются через CRIU, а персональный daemon пользователя останавливается для освобождения памяти. При следующем входе daemon запускается снова, и CRIU восстанавливает состояние контейнера за несколько секунд.

## Быстрый старт

Добавьте Hub как сервис в `docker-compose.yml` вашего репозитория. Сервис помечается `install_as=systemd`, чтобы работать как хостовый сервис, а не контейнер Docker (необходимо для управления daemon'ами для каждого пользователя через systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Сопоставление маршрутов: префикс поддомена -> порт на контейнерах пользователей
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Шаблон контейнера
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Маршруты Traefik (файловый провайдер; rediacc-router тоже читает эти метки)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Создайте `hub/.env` с учётными данными вашего провайдера OAuth2:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Установите хостовый systemd-юнит (один раз, требует root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Это читает сервисы `install_as=systemd` и записывает:

- `/etc/systemd/system/rediacc-hub.service` (юнит)
- `/etc/rediacc/hub/hub.labels.yaml` (метки шаблона)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (маршруты файлового провайдера Traefik)

Затем `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Для удаления: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Справочник команды install

| Команда | Назначение |
|---------|---------|
| `sudo renet hub install <compose-file>` | Преобразовать сервисы `install_as=systemd` из Compose-файла в артефакты хоста и запустить юнит. |
| `sudo renet hub uninstall <compose-file>` | Остановить, отключить и удалить все артефакты сервисов. Data-root'ы в `<workspace>/<user>-docker/` сохраняются. |
| `sudo renet hub gc <workspace-dir>` | Очистить брошенные персональные data-root'ы (по умолчанию: старше 30 дней без активного daemon). Флаги: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | JSON-статус всех контейнеров через API работающего Hub. |
| `renet hub stop <username>` | Остановить контейнер конкретного пользователя. |

## Настройка

Вся конфигурация Hub находится в метках Compose сервиса Hub. Секреты (OAuth client_secret, session_secret) помещаются в `hub/.env`, а не в метки.

### Сопоставление маршрутов

Сопоставляйте префиксы поддоменов с портами на контейнерах пользователей. Hub читает эти метки, чтобы знать, куда проксировать каждый запрос.

| Метка | Описание | Пример |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Сопоставляет `{prefix}.{domain}` с этим портом на контейнере пользователя | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Каждый маршрут также требует соответствующего Traefik-роутера, указывающего на порт Hub (7112). Hub обрабатывает маршрутизацию для каждого пользователя внутри на основе имени хоста.

### Шаблон контейнера

Определите, как выглядят контейнеры пользователей. Hub читает эти метки и использует их при создании нового контейнера.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.image` | Образ контейнера | Значение флага `--container-image` |
| `rediacc.hub.command` | Команда запуска (совместима с bash -c) | нет |
| `rediacc.hub.user` | Пользователь контейнера (рекомендуется не root) | `vscode` |
| `rediacc.hub.workspace` | Точка монтирования workspace внутри контейнера | `/workspace` |
| `rediacc.hub.shm_size` | Размер общей памяти в байтах | `1073741824` (1 ГБ) |
| `rediacc.hub.docker` | `per-user` для выделенного dockerd на пользователя (настоятельно рекомендуется) | `""` |

Метка `command` поддерживает подстановку `${SERVICE_IP}` и `__SERVICE_IP__` (последний вариант избегает предварительного раскрытия Compose) для назначенного loopback IP контейнера.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Docker daemon для каждого пользователя

Когда установлено `rediacc.hub.docker=per-user`, каждый пользователь получает выделенный экземпляр `dockerd` на хосте, монтируемый как `/var/run/docker.sock` внутри его контейнера. Это обеспечивает:

- Полноценные `docker ps`, `docker run`, `docker build` внутри пользовательской среды без привилегированных контейнеров или Docker-in-Docker.
- Полную изоляцию между пользователями (пользователь A не может видеть контейнеры или образы пользователя B).
- Персональный BTRFS data-root по адресу `<workspace-dir>/<user>-docker/.rediacc/docker/data`, сохраняемый между сессиями, так что кешированные образы переживают циклы idle-checkpoint.

Daemon'ы размещаются в выделенном диапазоне network-ID, начиная с 32768. Файл-маркер `.networkid` в data-root каждого пользователя записывает назначенный ID, чтобы возвращающиеся пользователи получали тот же daemon.

### Ограничения ресурсов

Устанавливайте ограничения ресурсов для каждого пользователя, чтобы один пользователь не потреблял все ресурсы хоста. Ограничения применяются как к контейнеру пользователя, так и к его экземпляру dockerd (через systemd `CPUQuota=` / `MemoryMax=`).

| Метка | Описание | Пример |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Значение systemd CPUQuota | `200%` (2 ядра) |
| `rediacc.hub.limits.memory` | Значение systemd MemoryMax | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemon'ы помещаются в systemd-срез `rediacc.slice`, чтобы наследовать ограничения уровня среза.

### Поддержка нескольких шаблонов

Предлагайте несколько типов сред. Пользователи выбирают шаблон при входе, посещая `https://code.example.com/_hub/login?template=python` (выбор передаётся через состояние OAuth). Смена шаблона при последующих входах пересоздаёт контейнер.

Определяйте шаблоны с метками `rediacc.hub.templates.<name>.<field>`. Плоские метки `rediacc.hub.image` / `rediacc.hub.command` / и т. д. продолжают определять неявный шаблон "по умолчанию" для пользователей, которые не выбирают ни один.

```yaml
labels:
  # Шаблон по умолчанию, когда ?template=... не указан.
  - "rediacc.hub.template=fulldev"

  # Полноценная среда VS Code + рабочий стол + терминал.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Только VS Code, лёгкий вариант.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Среда для Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Хуки жизненного цикла

Выполняйте команды внутри контейнера пользователя в точках жизненного цикла. Хуки выполняются от имени пользователя контейнера (не root).

| Метка | Когда выполняется | Пример |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | После создания контейнера (первый вход) | Клонирование репозиториев, установка зависимостей |
| `rediacc.hub.hook.checkpoint.pre_dump` | Перед контрольной точкой CRIU простаивающей сессии | Остановить daemon'ы, которые нельзя сохранить (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | После восстановления CRIU | Перезапустить daemon'ы, остановленные в pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Контрольная точка / Восстановление

Когда задан флаг `--checkpoint`, простаивающие контейнеры пользователей сохраняются через CRIU, а их персональный daemon останавливается для освобождения памяти. При следующем входе daemon перезапускается, и CRIU восстанавливает состояние контейнера с диска, сохраняя открытые файлы, запущенные процессы и сессии терминала. Типичное время возобновления составляет несколько секунд независимо от нагрузки.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Включить контрольные точки CRIU для контейнеров пользователей | `false` |

Передайте `--checkpoint` и ненулевой `--idle-timeout` (например, `30m`) в команде Hub. Директории с контрольными точками находятся в `<workspace-dir>/<user>/.checkpoint/`.

Если CRIU трижды подряд завершается ошибкой для пользователя, контрольные точки для этого пользователя отключаются, и резервной стратегией становится остановка и пересоздание.

### Эфемерный режим

По умолчанию рабочие пространства пользователей постоянны (сохраняются после перезапуска). Эфемерный режим предоставляет чистую среду при каждом входе, что удобно для демонстраций, обучения или CI.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` или `ephemeral` | `persistent` |

В эфемерном режиме рабочее пространство использует tmpfs (поддерживается ОЗУ) и контейнер автоматически удаляется при остановке.

### Тайм-аут простоя

| Флаг | Описание | По умолчанию |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Остановить/сохранить контрольную точку контейнеров, простаивающих дольше этого времени | `0` (отключено) |

`0` оставляет контейнеры работающими вечно. Практическое значение -- `30m`: простаивающие пользователи освобождают память через полчаса, а возвращающиеся возобновляют работу за секунды через CRIU.

### Управление доступом

| Переменная | Описание |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Разделённые запятыми группы, которым разрешено использовать Hub (когда провайдер предоставляет claim'ы групп) |
| `HUB_ADMIN_USERS` | Разделённые запятыми имена пользователей-администраторов. Администраторы видят и управляют контейнерами других пользователей в панели управления. |

## Журнал аудита

Каждое инициированное пользователем событие контейнера/образа (create, start, stop, destroy, kill, pull, push) в персональном daemon добавляется как запись JSON с разделением строками в `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Записи переживают контрольные точки и восстановление CRIU (поток аудита перевооружается при восстановлении). Используйте `logrotate` для ограничения использования диска; пример конфигурации:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Панель управления

Hub включает панель управления самообслуживания по адресу `/_hub/dashboard`. Она показывает:

- Все работающие среды с их статусом
- Выбранный шаблон
- Ссылки на сервисы (один клик для открытия кода, терминала, рабочего стола или любого другого маршрута)
- Таймеры простоя
- Использование диска на пользователя, количество запущенных контейнеров и образов
- Администраторы видят все контейнеры; обычные пользователи -- только свои

Статистика собирается каждые 30 секунд.

## Сборка мусора data-root

Персональные data-root'ы накапливаются на долго работающих хостах. Запланируйте `renet hub gc` для очистки заброшенных. Таймер systemd хорошо подходит для этого:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` фиксирует кандидатов без удаления. Data-root считается подходящим, когда его файл-маркер `.networkid` старше `--max-age` И записанный daemon больше не настроен на хосте.

## Настройка OAuth

Hub работает с любым стандартным провайдером OAuth2. Конфигурация выполняется через переменные окружения.

| Переменная | Описание | Обязательно |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 client ID | Да |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 client secret | Да |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint авторизации провайдера | Да |
| `HUB_OAUTH_TOKEN_URL` | Endpoint токена провайдера | Да |
| `HUB_OAUTH_USERINFO_URL` | Endpoint userinfo провайдера | Да |
| `HUB_OAUTH_USERINFO_PATH` | Точечный путь для извлечения имени пользователя из JSON-ответа | Да |
| `HUB_OAUTH_REDIRECT_URI` | Переопределить URL обратного вызова (вычисляется автоматически, если пусто) | Нет |
| `HUB_OAUTH_SCOPES` | Дополнительные области (разделены пробелами) | Нет |
| `HUB_SESSION_SECRET` | Шестнадцатеричная строка длиной 32+ байт для подписи cookie | Рекомендуется |

### Примеры провайдеров

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` -- это путь с разделителями-точками в JSON-ответе. Для вложенных объектов, таких как `{"ocs":{"data":{"id":"alice"}}}` в Nextcloud, используйте `ocs.data.id`.

## Примеры

### Среда разработки (VS Code + Терминал + Рабочий стол)

Полноценная среда разработки с OpenVSCode Server, веб-терминалом (ttyd) и рабочим столом noVNC. Пользователи получают собственный Docker daemon внутри.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Traefik-роутеры для каждого префикса ...
```

### Среда Jupyter Notebook

Среда для анализа данных с JupyterLab:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Простое веб-приложение (Эфемерное)

Среда с единственным сервисом, начинающая с чистого листа при каждом входе:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Связанные руководства

- [**Сервисы**](/ru/docs/services) -- Жизненный цикл Rediaccfile, шаблоны Compose
- [**Сеть**](/ru/docs/networking) -- Метки Docker, маршрутизация Traefik, TLS-сертификаты
- [**Резервное копирование и восстановление**](/ru/docs/backup-restore) -- Сохранность рабочего пространства и восстановление
- [**Среды разработки**](/ru/docs/development-environments) -- Клонирование производственной среды для разработки
