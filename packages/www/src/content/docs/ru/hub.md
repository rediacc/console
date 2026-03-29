---
title: "Hub"
description: "Предоставление аутентифицированных контейнерных сред для каждого пользователя с автоматическим развертыванием, управлением простоем и контрольными точками/восстановлением."
category: "Guides"
order: 14
language: ru
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Hub предоставляет контейнерные среды для каждого пользователя за OAuth-аутентификацией. Пользователи переходят по одному URL, аутентифицируются через любой OAuth2-провайдер и прозрачно перенаправляются в свой персональный контейнер. Контейнеры создаются по запросу и управляются автоматически.

Все настраивается через метки `docker-compose.yml`. Hub не знает и не заботится о том, что работает внутри контейнеров -- он обрабатывает аутентификацию, маршрутизацию и жизненный цикл. Поведение определяется репозиториями.

## Как это работает

![Архитектура Hub](/img/hub-architecture.svg)

1. Пользователь переходит на `code.example.com`
2. Hub проверяет cookie сессии. Если cookie отсутствует, пользователь перенаправляется к настроенному OAuth2-провайдеру (Nextcloud, Keycloak, GitHub и т.д.)
3. После аутентификации Hub идентифицирует пользователя и ищет его контейнер
4. Если контейнер не существует, он создается по запросу из настроенного шаблона
5. Запрос проксируется через обратный прокси в контейнер пользователя
6. Hub определяет порт для проксирования на основе имени хоста (например, `code.` -> порт 8080, `term.` -> порт 7681)

Простаивающие контейнеры автоматически останавливаются или сохраняются через контрольную точку (CRIU) для мгновенного возобновления при следующем входе.

## Быстрый старт

Добавьте Hub как сервис в `docker-compose.yml` вашего репозитория:

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # Маршрутизация: префикс поддомена -> порт на контейнерах пользователей
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Шаблон контейнера
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Маршруты Traefik (один на поддомен)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Создайте `hub.env` с учетными данными вашего OAuth2-провайдера:

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

Разверните с помощью `rdc repo up`.

## Настройка

Вся конфигурация Hub находится в метках Compose самого сервиса Hub. Внутри бинарного файла Hub нет файлов конфигурации.

### Маршрутизация

Сопоставляйте префиксы поддоменов с портами на контейнерах пользователей. Hub читает эти метки, чтобы знать, куда направлять каждый запрос.

| Метка | Описание | Пример |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Сопоставляет `{prefix}.{domain}` с этим портом на контейнере пользователя | `rediacc.hub.route.code=8080` |

Вы можете определить любое количество маршрутов. Префикс сопоставляется с первым сегментом имени хоста:

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Для каждого маршрута также нужен соответствующий маршрутизатор Traefik, указывающий на порт Hub (7112). Hub обрабатывает маршрутизацию по пользователям внутренне.

### Шаблон контейнера

Определите, как должны выглядеть контейнеры пользователей. Hub читает эти метки и использует их при создании нового контейнера для пользователя.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.image` | Образ контейнера | Значение флага `--container-image` |
| `rediacc.hub.command` | Команда запуска (совместимая с bash -c) | нет |
| `rediacc.hub.user` | Пользователь контейнера (рекомендуется не-root) | `vscode` |
| `rediacc.hub.workspace` | Точка монтирования рабочего пространства внутри контейнера | `/workspace` |
| `rediacc.hub.shm_size` | Размер общей памяти в байтах | `1073741824` (1 ГБ) |

Метка `command` поддерживает подстановку `${SERVICE_IP}`, которая заменяется назначенным loopback IP контейнера при его создании.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **Совет:** Используйте `$$` для литерального `$` в метках Compose, чтобы предотвратить преждевременную подстановку переменных окружения Docker Compose.

### Ограничения ресурсов

Установите ограничения ресурсов для каждого пользователя, чтобы предотвратить потребление всех ресурсов хоста одним пользователем.

| Метка | Описание | Пример |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Ограничение CPU (ядра) | `2` |
| `rediacc.hub.limits.memory` | Ограничение памяти | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### Хуки жизненного цикла

Выполняйте команды внутри контейнера пользователя в определенные моменты жизненного цикла.

| Метка | Когда выполняется | Пример |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | После создания контейнера (первый вход) | Клонирование репозиториев, установка зависимостей |
| `rediacc.hub.hook.on_start` | После запуска или восстановления контейнера | Монтирование секретов, обновление токенов |
| `rediacc.hub.hook.on_idle` | Перед остановкой или созданием контрольной точки контейнера | Сохранение состояния, отправка изменений |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### Контрольная точка / Восстановление

При включении простаивающие контейнеры сохраняются через контрольную точку CRIU вместо остановки. При следующем входе контейнер восстанавливается из контрольной точки за секунды, сохраняя точное состояние: открытые файлы, запущенные процессы, терминальные сессии.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Включить контрольную точку CRIU для контейнеров пользователей | `false` |

Также передайте `--checkpoint` при запуске Hub:

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...другие флаги...
```

> **Примечание:** Контрольная точка/восстановление требует наличия бинарного файла CRIU на хосте и работы контейнера в режиме сети хоста (по умолчанию для сервисов Rediacc).

### Контроль доступа

Ограничьте, кто может использовать Hub и кто имеет привилегии администратора.

| Метка | Описание | Пример |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Группы через запятую, которым разрешено использовать Hub | `developers,ops` |
| `rediacc.hub.admin_users` | Имена пользователей-администраторов через запятую | `alice,bob` |

Пользователи-администраторы могут видеть и управлять всеми контейнерами в панели управления. Обычные пользователи видят только свои.

### Эфемерный режим

По умолчанию рабочие пространства пользователей являются постоянными (сохраняются после перезапуска контейнера). Эфемерный режим предоставляет чистую среду при каждом входе, что полезно для демонстраций, обучения или CI.

| Метка | Описание | По умолчанию |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` или `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

В эфемерном режиме рабочее пространство использует tmpfs (на базе RAM), и контейнер автоматически удаляется при остановке.

### Поддержка нескольких шаблонов

Предлагайте несколько типов сред. Пользователи могут выбрать шаблон при первом входе или переключиться через панель управления.

```yaml
labels:
  # Шаблон по умолчанию
  - "rediacc.hub.template.default=fulldev"

  # Полная среда разработки
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # Облегченный вариант
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## Настройка OAuth

Hub работает с любым стандартным OAuth2-провайдером. Настройка выполняется через переменные окружения, а не метки Compose (секреты не должны быть в метках).

| Переменная | Описание | Обязательно |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID клиента OAuth2 | Да |
| `HUB_OAUTH_CLIENT_SECRET` | Секрет клиента OAuth2 | Да |
| `HUB_OAUTH_AUTHORIZE_URL` | Эндпоинт авторизации провайдера | Да |
| `HUB_OAUTH_TOKEN_URL` | Эндпоинт токена провайдера | Да |
| `HUB_OAUTH_USERINFO_URL` | Эндпоинт информации о пользователе провайдера | Да |
| `HUB_OAUTH_USERINFO_PATH` | Точечный путь для извлечения имени пользователя из JSON-ответа | Да |
| `HUB_OAUTH_REDIRECT_URI` | Переопределение URL обратного вызова (автоматически вычисляется, если пусто) | Нет |
| `HUB_OAUTH_SCOPES` | Дополнительные области (разделенные пробелами) | Нет |
| `HUB_SESSION_SECRET` | Шестнадцатеричная строка 32+ байт для подписи cookie | Рекомендуется |

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

`HUB_OAUTH_USERINFO_PATH` -- это путь через точку в JSON-ответе. Для вложенных объектов, таких как `{"ocs":{"data":{"id":"alice"}}}` в Nextcloud, используйте `ocs.data.id`.

## Панель управления

Hub включает панель самообслуживания по адресу `/_hub/dashboard`. Она отображает:

- Все запущенные среды с их статусом
- Ссылки на сервисы (один клик для открытия кода, терминала или рабочего стола)
- Таймеры простоя и использование ресурсов
- Элементы управления запуском/остановкой
- Администраторы могут видеть и управлять всеми контейнерами

Откройте панель управления, перейдя по адресу `https://code.example.com/_hub/dashboard` после аутентификации.

## Примеры

### Среда разработки (VS Code + Терминал + Рабочий стол)

Полная среда разработки с OpenVSCode Server, веб-терминалом (ttyd) и рабочим столом noVNC:

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Среда Jupyter Notebook

Среда для науки о данных с JupyterLab:

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### Простое веб-приложение

Среда с одним сервисом для веб-фреймворка:

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Связанные руководства

- [**Сервисы**](/ru/docs/services) -- Жизненный цикл Rediaccfile, шаблоны Compose
- [**Сеть**](/ru/docs/networking) -- Метки Docker, маршрутизация Traefik, TLS-сертификаты
- [**Резервное копирование и восстановление**](/ru/docs/backup-restore) -- Постоянство рабочего пространства и восстановление
- [**Среды разработки**](/ru/docs/development-environments) -- Клонирование продакшена для сред разработки
