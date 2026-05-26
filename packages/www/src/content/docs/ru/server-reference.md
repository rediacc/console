---
title: "Справочник по серверу"
description: "Структура каталогов, команды renet, службы systemd и рабочие процессы для удалённого сервера."
category: "Concepts"
order: 3
language: ru
sourceHash: "f68c27543a2fe3ff"
sourceCommit: "a3b80f4e653e80766813a8c1d7ef563f00904147"
---

# Справочник по серверу

На этой странице описано, что вы обнаружите при подключении по SSH к серверу Rediacc: структура каталогов, команды `renet`, службы systemd и типичные рабочие процессы.

Большинство пользователей управляют серверами через `rdc` со своей рабочей станции и не нуждаются в этой странице. Она предназначена для расширенной отладки или для случаев, когда требуется работать непосредственно на сервере.

Общую архитектуру см. в разделе [Архитектура](/ru/docs/architecture). Различия между `rdc` и `renet` описаны в разделе [rdc vs renet](/ru/docs/rdc-vs-renet).

## Структура каталогов

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## Команды renet

`renet` является серверным бинарным файлом. Все команды требуют привилегий root (`sudo`).

### Жизненный цикл репозитория

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Выполнение команд compose для Docker-демона конкретного репозитория:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Выполнение команд Docker напрямую:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Вы также можете использовать Docker-сокет напрямую:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Всегда запускайте compose из каталога, содержащего `docker-compose.yml`, иначе Docker не найдёт файл.

### Песочница файловой системы

```bash
# Проверить поддержку Landlock
renet sandbox-exec --detect

# Выполнить команду в песочнице Landlock (используется внутри)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` применяет ограничения файловой системы Landlock LSM, а затем выполняет указанную команду. Вызывается автоматически компонентом `sandbox-gateway` (обработчиком SSH ForceCommand) для всех подключений на уровне репозитория.

### Пользовательский Hub (среды разработки)

Hub предоставляет каждому пользователю собственный Docker-демон для сред разработки, отдельный от демонов `FlavorRediacc` на уровне репозитория.

```bash
# Установить / удалить systemd-юниты пользовательского Hub
sudo renet hub install
sudo renet hub uninstall

# Очистить простаивающие пользовательские Hub-демоны
sudo renet hub gc
```

Демоны работают под одним из двух флейворов, задаваемым параметром `--flavor`:

```bash
# Изолированный демон на уровне репозитория (bridge=none, iptables=false) — по умолчанию
sudo renet daemon start-foreground --flavor=rediacc ...

# Пользовательский Hub-демон (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

Флейвор `hub` включает обычное bridge-сетевое взаимодействие, обеспечивая контейнерам пользователя исходящую связь; флейвор `rediacc` принудительно изолирует репозитории через loopback. Журналы аудита Hub записываются в `/var/log/rediacc/hub/<user>.log`.

**Флаги:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: правила путей Landlock
- `--home-overlay`: монтирует OverlayFS поверх домашнего каталога для изоляции записи на уровне репозитория
- `--sandbox-dir`: рабочее пространство репозитория (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: задаёт рабочий каталог и загружает `.envrc` для окружения репозитория
- `--run-as`: понижает привилегии до целевого пользователя после настройки
- `--reset-home`: очищает оверлей домашнего каталога репозитория для чистого старта

**`sandbox-gateway`** является обработчиком SSH ForceCommand, устанавливаемым через `command=` в `authorized_keys`. SSH-ключ каждого репозитория запускает шлюз с вшитым именем репозитория, которое клиент не может подделать. Шлюз формирует аргументы sandbox-exec и выполняет их через sudo.

### Прокси и маршрутизация

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Маршруты обнаруживаются автоматически по меткам контейнеров. Настройку меток Traefik см. в разделе [Сетевое взаимодействие](/ru/docs/networking).

### Состояние системы

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Управление демонами

Каждый репозиторий запускает собственный Docker-демон. Вы можете управлять ими по отдельности:

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Резервное копирование и восстановление

Отправка резервных копий на другую машину или в облачное хранилище:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> Большинству пользователей следует использовать `rdc repo push/pull`. Команды `rdc` автоматически обрабатывают учётные данные и определяют машину.

### Контрольные точки (CRIU)

Контрольные точки сохраняют состояние работающих контейнеров для последующего восстановления:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Обслуживание

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Службы systemd

Каждый репозиторий создаёт следующие юниты systemd:

| Юнит | Назначение |
|------|------------|
| `rediacc-docker-{id}.service` | Изолированный Docker-демон |
| `rediacc-docker-{id}.socket` | Активация сокета Docker API |
| `rediacc-loopback-{id}.service` | Настройка псевдонима loopback IP |

Глобальные службы, общие для всех репозиториев:

| Юнит | Назначение |
|------|------------|
| `rediacc-router.service` | Обнаружение маршрутов (порт 7111) |
| `rediacc-autostart.service` | Монтирование репозиториев при загрузке |
| `rediacc-autostart-reconcile.service` | Периодический реконсилятор автозапуска (запускается таймером ниже) |
| `rediacc-autostart-reconcile.timer` | Запускает `renet repository reconcile` примерно каждые 3 минуты для восстановления репозиториев с автозапуском, остановившихся после загрузки |

## Типичные рабочие процессы

### Развёртывание нового сервиса

1. Создайте зашифрованный репозиторий:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Смонтируйте его и добавьте файлы `docker-compose.yml`, `Rediaccfile` и `.rediacc.json`.
3. Запустите:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Доступ к работающему контейнеру

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Определение Docker-сокета контейнера

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Пересоздание сервиса после изменения конфигурации

```bash
sudo renet compose -- up -d
```

Запустите эту команду из каталога с `docker-compose.yml`. Изменённые контейнеры будут автоматически пересозданы.

### Просмотр всех контейнеров на всех демонах

```bash
renet list containers
```

## Советы

- Всегда используйте `sudo` для команд `renet compose`, `renet repository` и `renet docker`, им необходим root для операций LUKS и Docker
- Разделитель `--` обязателен перед передачей аргументов в `renet compose` и `renet docker`
- Запускайте compose из каталога, содержащего `docker-compose.yml`
- Назначения слотов в `.rediacc.json` стабильны, не изменяйте их после развёртывания
- Используйте пути `/run/rediacc/docker-{id}.sock` (systemd может изменять устаревшие пути `/var/run/`)
- Периодически выполняйте `renet prune --dry-run` для обнаружения осиротевших ресурсов
- Снимки BTRFS (`renet backup`) быстры и экономичны, создавайте их перед рискованными изменениями
- Репозитории зашифрованы с помощью LUKS, потеря пароля означает потерю данных
