---
title: Сетевое взаимодействие
description: >-
  Предоставление сервисов через обратный прокси, Docker-метки, TLS-сертификаты,
  DNS и проброс TCP/UDP-портов.
category: Guides
order: 6
language: ru
sourceHash: "536db0c93646cad6"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Сетевое взаимодействие

На этой странице описывается, как сервисы, работающие внутри изолированных Docker-демонов, становятся доступными из интернета. Рассматривается система обратного прокси, Docker-метки для маршрутизации, TLS-сертификаты, DNS и проброс TCP/UDP-портов.

Информацию о том, как сервисы получают loopback IP-адреса и как работает система слотов `.rediacc.json`, см. в разделе [Сервисы](/ru/docs/services#сетевое-взаимодействие-сервисов-rediaccjson).

## Сетевая изоляция

Каждый репозиторий автоматически изолируется на уровне ядра с помощью сетевых хуков. Требуется Linux kernel 6.1 или новее. Никакой настройки не требуется.

- **Автоматическое переписывание bind**: Сервисы могут привязываться к `0.0.0.0` или `127.0.0.1` как обычно. Ядро прозрачно переписывает адрес на назначенный loopback IP сервиса. Явная привязка к `${SERVICE_IP}` не нужна.
- **Блокировка соединений между репозиториями**: Если сервис пытается подключиться к loopback IP за пределами подсети `/26` своего репозитория, ядро блокирует это. Процесс в репозитории А не может достичь сервисов в репозитории Б.
- **Никаких изменений в приложениях**: Сервисы используют `0.0.0.0` или `localhost` для привязки, и ядро гарантирует, что они слушают только на правильном loopback IP. Изоляция полностью прозрачна.

## Как это работает

Rediacc использует двухкомпонентную систему прокси для маршрутизации внешнего трафика к контейнерам:

1. **Сервер маршрутов**, systemd-сервис, который обнаруживает работающие контейнеры во всех Docker-демонах репозиториев. Он проверяет метки контейнеров и генерирует конфигурацию маршрутизации, предоставляемую как YAML-эндпоинт.
2. **Traefik**, обратный прокси, который опрашивает сервер маршрутов каждые 5 секунд и применяет обнаруженные маршруты. Он обрабатывает HTTP/HTTPS-маршрутизацию, TLS-терминацию и проброс TCP/UDP.

Поток трафика выглядит следующим образом:

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ polls every 5s
           Route Server (discovers containers)
               ↓ inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Containers (bound to 127.x.x.x loopback IPs)
```

Когда вы добавляете правильные метки к контейнеру и запускаете его с помощью `renet compose`, он автоматически становится маршрутизируемым, ручная настройка прокси не требуется.

> Бинарный файл сервера маршрутов поддерживается в синхронизации с версией вашего CLI. Когда CLI обновляет бинарный файл renet на машине, сервер маршрутов автоматически перезапускается (~1-2 секунды). Это не вызывает простоя, Traefik продолжает обслуживать трафик с последней известной конфигурацией во время перезапуска и получает новую конфигурацию при следующем опросе. Существующие клиентские соединения не затрагиваются. Контейнеры вашего приложения не изменяются.

## Docker-метки

Маршрутизация управляется с помощью меток Docker-контейнеров. Существуют два уровня:

### Уровень 1: Метки `rediacc.*` (автоматические)

Эти метки **автоматически внедряются** командой `renet compose` при запуске сервисов. Вам не нужно добавлять их вручную.

| Метка | Описание | Пример |
|-------|----------|--------|
| `rediacc.service_name` | Идентификатор сервиса | `myapp` |
| `rediacc.service_ip` | Назначенный loopback IP | `127.0.11.2` |
| `rediacc.network_id` | Идентификатор демона репозитория | `2816` |
| `rediacc.repo_name` | Имя репозитория | `marketing` |
| `rediacc.tcp_ports` | TCP-порты, на которых слушает сервис | `8080,8443` |
| `rediacc.udp_ports` | UDP-порты, на которых слушает сервис | `53` |

Когда контейнер имеет только метки `rediacc.*` (без `traefik.enable=true`), сервер маршрутов генерирует **автомаршрут** с использованием имени репозитория и поддомена машины:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Например, сервис с именем `myapp` в репозитории `marketing` на машине `server-1` с базовым доменом `example.com` получит:

```
myapp.marketing.server-1.example.com
```

Для форков имя сервиса объединяется с зарезервированным словом `fork` и тегом:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Например, форк `marketing` с тегом `staging` получит:

```
myapp-fork-staging.marketing.server-1.example.com
```

Каждый URL форка находится под поддоменом родительского репозитория и покрывается его существующим wildcard-сертификатом, поэтому новый сертификат не нужен. Разделитель `-fork-` предотвращает коллизии с реальными именами сервисов в продакшн-репозитории. Для сервисов с пользовательскими доменами используйте метки уровня 2 или метку `rediacc.domain`.

#### Пользовательский домен через `rediacc.domain`

Вы можете задать пользовательский домен для сервиса с помощью метки `rediacc.domain` в вашем `docker-compose.yml`. Поддерживаются как короткие имена, так и полные домены:

```yaml
labels:
  # Короткое имя, преобразуется в cloud.example.com с использованием baseDomain машины
  - "rediacc.domain=cloud"

  # Полный домен, используется как есть
  - "rediacc.domain=cloud.example.com"
```

Значение без точек обрабатывается как короткое имя, и `baseDomain` машины добавляется автоматически. Значение с точками используется как полный домен.

Когда настроен `machineName`, сервисы с пользовательским доменом получают **два маршрута**: один на базовом домене (`cloud.example.com`) и один на поддомене машины (`cloud.server-1.example.com`).

### Уровень 2: Метки `traefik.*` (пользовательские)

Добавьте эти метки в ваш `docker-compose.yml`, когда вам нужна маршрутизация по пользовательскому домену, TLS или определенные точки входа. Установка `traefik.enable=true` указывает серверу маршрутов использовать ваши пользовательские правила вместо генерации автомаршрута.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Здесь используется стандартный [синтаксис меток Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Совет:** Внутренние сервисы (базы данных, кеши, очереди сообщений) **не должны** иметь `traefik.enable=true`. Им нужны только метки `rediacc.*`, которые внедряются автоматически.

## Предоставление HTTP/HTTPS-сервисов

### Предварительные требования

1. Настроенная инфраструктура на машине ([Настройка машины, Настройка инфраструктуры](/ru/docs/setup#настройка-инфраструктуры)):

   ```bash
   # Общие учетные данные (один раз на конфигурацию, применяются ко всем машинам)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Настройки конкретной машины
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. DNS-записи, указывающие ваш домен на публичный IP сервера (см. [Настройка DNS](#настройка-dns) ниже).

### Добавление меток

Добавьте метки `traefik.*` к сервисам, которые хотите предоставить, в вашем `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # Без меток traefik, база данных только для внутреннего использования
```

| Метка | Назначение |
|-------|-----------|
| `traefik.enable=true` | Включает пользовательскую маршрутизацию Traefik для этого контейнера |
| `traefik.http.routers.{name}.rule` | Правило маршрутизации, обычно `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Точки входа: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Резолвер сертификатов, используйте `letsencrypt` для автоматического Let's Encrypt |
| `traefik.http.services.{name}.loadbalancer.server.port` | Порт, на котором ваше приложение слушает внутри контейнера |

`{name}` в метках это произвольный идентификатор; он должен быть согласованным во всех связанных метках маршрутизатора/сервиса/middleware.

> **Примечание:** Метки `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) внедряются автоматически командой `renet compose`. Вам не нужно добавлять их в ваш compose-файл.

## TLS-сертификаты

TLS-сертификаты получаются автоматически через Let's Encrypt с использованием DNS-01 проверки Cloudflare. Учетные данные настраиваются один раз на конфигурацию (общие для всех машин):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Автомаршруты используют **wildcard-сертификаты** на уровне поддомена репозитория (`*.marketing.server-1.example.com`) вместо сертификатов для каждого сервиса. Сертификат автоматически выпускается Traefik при первом `repo up`; никаких ручных шагов не требуется. Форки повторно используют существующий wildcard родительского репозитория, поэтому никогда не вызывают новый запрос сертификата. Маршруты с пользовательскими доменами используют wildcard на уровне машины (`*.server-1.example.com`).

> **Требуются учетные данные Cloudflare.** Wildcard-сертификаты используют DNS-01 проверку. Без `--cf-dns-token` (и опционально `--cert-email`) Traefik не сможет завершить проверку и HTTPS не будет работать. HTTP остается функциональным. Настройте учетные данные с помощью `rdc config infra set` перед первым деплоем.

Для маршрутов уровня 2 с `traefik.http.routers.{name}.tls.certresolver=letsencrypt` wildcard-домены SAN автоматически добавляются на основе имени хоста маршрута.

API-токен Cloudflare DNS должен иметь разрешение `Zone:DNS:Edit` для доменов, которые вы хотите защитить.

### Жизненный цикл TLS-сертификата

Полный путь, который проходит сертификат Let's Encrypt от выпуска до контейнеров каждого репозитория:

1. **Выпуск на хосте.** Контейнер Traefik на уровне машины (`rediacc-proxy`, развёрнутый в `/opt/rediacc/proxy/`) владеет обновлением ACME. Он хранит всё состояние в `/opt/rediacc/proxy/letsencrypt/acme.json` на хосте. Обновление запускается автоматически примерно за 30 дней до истечения срока; никаких действий оператора не требуется, пока настроен `--cf-dns-token`.

2. **Дамп для каждого репозитория (опционально).** Сервисы, которым нужны файлы сертификатов внутри собственного контейнера (например, почтовый сервер, читающий `.pem` напрямую), разворачивают рядом с собой небольшой контейнер `traefik-certs-dumper`. Дампер монтирует `/opt/rediacc/proxy/letsencrypt` в режиме только для чтения и записывает извлечённые сертификат и ключ в том данных репозитория как `cert.pem` / `key.pem`. Для этого Docker-демон репозитория должен иметь `/opt/rediacc/proxy` в списке разрешений пространства имён монтирования. Это уже включено по умолчанию.

3. **Кэш на стороне клиента (`rediacc.json`).** CLI кэширует сжатую копию `acme.json` под `acmeCertCache` в вашем файле конфигурации, с ключом по `baseDomain`. Это позволяет нескольким машинам совместно использовать сертификаты (через `rdc config cert-cache push -m <machine>`) и работает как оффлайн-инвентарь.

**Триггеры синхронизации для кэша клиента:**

- Автоматически после `rdc repo up`, но только если локальный кэш для `baseDomain` машины старше 6 часов. Свежие кэши остаются нетронутыми, чтобы последовательные деплои не нагружали SSH.
- По запросу: `rdc config cert-cache pull -m <machine>` (принудительное получение) или `rdc machine query --name <machine> --sync-certs` (получение как побочный эффект запроса статуса).
- При `rdc config infra push` кэш загружается на машину (локальные сертификаты с более долгим сроком действия имеют приоритет над удалёнными).

**Обслуживание кэша:**

- Устаревшие записи автомаршрутов (старые домены с тегом идентификатора сети, например `service-3200.rediacc.io`) удаляются при каждом получении.
- Сертификаты, у которых `notAfter` более чем на 7 дней в прошлом, удаляются полностью. Они инертны и только раздувают кэш.
- `rdc config cert-cache clear` очищает всё; `rdc config cert-cache status` показывает инвентарь.

**Устранение неполадок:** если `traefik-certs-dumper` падает с `/traefik/acme.json: no such file or directory`, демон репозитория не видит хранилище letsencrypt хоста. Проверьте (а) наличие `/opt/rediacc/proxy/letsencrypt/acme.json` на хосте (за это отвечает `rediacc-proxy` уровня хоста), и (б) что демон репозитория был запущен с достаточно новым renet, который добавляет `/opt/rediacc/proxy` в список разрешений. После обновления renet выполните `rdc repo up`, чтобы применить изменения.

> **Экспериментально:** Автоматическая частота синхронизации и удаление по истечении срока появились в renet 0.9+. Более старые версии CLI/renet используют исключительно ручную синхронизацию через `rdc config cert-cache pull`.

## Проброс TCP/UDP-портов

Для не-HTTP протоколов (почтовые серверы, DNS, базы данных с внешним доступом) используйте проброс TCP/UDP-портов.

### Шаг 1: Регистрация портов

Добавьте необходимые порты при настройке инфраструктуры:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Это создает точки входа Traefik с именами `tcp-{port}` и `udp-{port}`.

> После добавления или удаления портов всегда повторно выполняйте `rdc config infra push` для обновления конфигурации прокси.

### Шаг 2: Добавление TCP/UDP-меток

Используйте метки `traefik.tcp.*` или `traefik.udp.*` в вашем compose-файле:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Ключевые концепции:
- **`HostSNI(\`*\`)`** соответствует любому имени хоста (для протоколов, не отправляющих SNI, например, обычный SMTP)
- **`tls.passthrough=true`** означает, что Traefik пересылает необработанное TLS-соединение без расшифровки, приложение само обрабатывает TLS
- Имена точек входа следуют соглашению `tcp-{port}` или `udp-{port}`

### Пример простого TCP (база данных)

Чтобы предоставить доступ к базе данных снаружи без TLS passthrough (Traefik пересылает сырой TCP):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Порт 5432 предварительно настроен (см. ниже), поэтому настройка `--tcp-ports` не нужна.

> **Примечание по безопасности:** Открытие базы данных в интернет является риском. Используйте это только когда удалённым клиентам нужен прямой доступ. В большинстве случаев держите базу данных внутренней и подключайтесь через ваше приложение.

### Предварительно настроенные порты

Следующие TCP/UDP-порты имеют точки входа по умолчанию (не нужно добавлять через `--tcp-ports`). Точки входа генерируются только для настроенных семейств адресов, точки входа IPv4 требуют `--public-ipv4`, точки входа IPv6 требуют `--public-ipv6`:

| Порт | Протокол | Типичное использование |
|------|----------|----------------------|
| 80 | HTTP | Веб (автоперенаправление на HTTPS) |
| 443 | HTTPS | Веб (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | Динамический диапазон (автовыделение) |

## Настройка DNS

### Автоматический DNS (Cloudflare)

Когда настроен `--cf-dns-token`, `rdc config infra push` автоматически создает необходимые DNS-записи в Cloudflare:

| Запись | Тип | Содержимое | Создано |
|--------|-----|------------|---------|
| `server-1.example.com` | A / AAAA | Публичный IP машины | `push-infra` |
| `*.server-1.example.com` | A / AAAA | Публичный IP машины | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | Публичный IP машины | `repo up` |

Записи уровня машины создаются командой `push-infra` и покрывают маршруты с пользовательскими доменами (`rediacc.domain`). Wildcard-записи для каждого репозитория создаются автоматически командой `repo up` и покрывают автомаршруты этого репозитория.

Это идемпотентно, существующие записи обновляются при изменении IP и остаются без изменений, если уже корректны.

Wildcard базового домена (`*.example.com`) необходимо создать вручную, если вы используете пользовательские метки домена, например `rediacc.domain=erp`.

### Ручная настройка DNS

Если вы не используете Cloudflare или управляете DNS вручную, создайте A (IPv4) и/или AAAA (IPv6) записи:

```
# Поддомен машины (для маршрутов с пользовательским доменом, например rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Wildcard для каждого репозитория (для автомаршрутов вроде myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Wildcard базового домена (для сервисов с пользовательским доменом, например rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

При настроенном Cloudflare DNS wildcard-записи для каждого репозитория создаются автоматически командой `repo up`. При наличии нескольких машин каждая машина получает собственные DNS-записи, указывающие на её собственный IP.

## Middleware

Middleware Traefik модифицируют запросы и ответы. Применяйте их через метки.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Буферизация для больших файлов

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Несколько middleware

Объединяйте middleware через запятую:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Полный список доступных middleware см. в [документации Traefik middleware](https://doc.traefik.io/traefik/middlewares/overview/).

## Диагностика

Если сервис недоступен, подключитесь к серверу по SSH и проверьте эндпоинты сервера маршрутов:

### Проверка состояния

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Показывает общий статус, количество обнаруженных маршрутизаторов и сервисов, и включены ли автомаршруты.

### Обнаруженные маршруты

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Выводит список всех HTTP, TCP и UDP маршрутизаторов с их правилами, точками входа и бэкенд-сервисами.

### Выделение портов

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Показывает сопоставления TCP и UDP портов для динамически выделенных портов.

### Типичные проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| Сервис не отображается в маршрутах | Контейнер не запущен или отсутствуют метки | Проверьте с помощью `docker ps` на демоне репозитория; проверьте метки |
| Сертификат не выпущен | DNS не указывает на сервер или невалидный токен Cloudflare | Проверьте разрешение DNS; проверьте разрешения API-токена Cloudflare |
| 502 Bad Gateway | Приложение не слушает на объявленном порту | Убедитесь, что приложение запущено и порт совпадает с `loadbalancer.server.port` |
| TCP-порт недоступен | Порт не зарегистрирован в инфраструктуре | Выполните `rdc config infra set --tcp-ports ...` и `push-infra` |
| Сервер маршрутов работает на старой версии | Бинарный файл обновлён, но сервис не перезапущен | Происходит автоматически при провизионировании; вручную: `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN недоступен | Адреса relay закэшированы при запуске | Пересоздайте сервис после изменений DNS или IP, чтобы он получил новую конфигурацию сети |

## Полный пример

Этот пример развертывает веб-приложение с базой данных PostgreSQL. Приложение публично доступно по адресу `app.example.com` с TLS; база данных доступна только внутри.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Без меток traefik, только для внутреннего использования
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Создайте A-запись, указывающую `app.example.com` на публичный IP вашего сервера:

```
app.example.com   A   203.0.113.50
```

### Развертывание

```bash
rdc repo up --name my-app -m server-1
```

Через несколько секунд сервер маршрутов обнаружит контейнер, Traefik подхватит маршрут, запросит TLS-сертификат, и `https://app.example.com` станет доступен.
