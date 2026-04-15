---
title: "Установка"
description: "Установите CLI Rediacc на Linux, macOS или Windows."
category: "Guides"
order: 1
language: ru
sourceHash: "2651baa400d94f8c"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Установка

Установите CLI `rdc` на свою рабочую станцию. Это единственный инструмент, который нужно установить вручную -- все остальное обрабатывается автоматически при настройке удаленных машин.

## Быстрая установка

### Linux и macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Эта команда загружает бинарный файл `rdc` в `$HOME/.local/bin/`. Убедитесь, что этот каталог присутствует в вашем PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Добавьте эту строку в профиль вашей оболочки (`~/.bashrc`, `~/.zshrc` и т.д.), чтобы сделать изменение постоянным.

### Windows

Выполните в PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Эта команда загружает `rdc.exe` в `%LOCALAPPDATA%\rediacc\bin\`. Установщик предложит добавить его в PATH при необходимости.

## Менеджеры пакетов

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / совместимые с RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux и Rocky Linux используют один и тот же поток DNF; любой совместимый с RHEL дистрибутив с `dnf` может подключить указанный репозиторий. Примечание: **Oracle Linux 10 является единственным дистрибутивом семейства RHEL, официально поддерживаемым в качестве целевой серверной платформы Rediacc** (см. [Требования](/en/docs/requirements)). В Rocky/Alma 10 отсутствует модуль ядра btrfs, необходимый для плоскости данных renet, хотя CLI `rdc` устанавливается на них без проблем.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Протестировано на openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Примечание: Пакет `gcompat` (слой совместимости с glibc) устанавливается автоматически как зависимость.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

Загрузите и запустите CLI как контейнер:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Создайте псевдоним для удобства:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Доступные теги Docker:

| Тег | Описание |
|-----|----------|
| `:stable` | Последний стабильный релиз (рекомендуется) |
| `:edge` | Последний edge-релиз |
| `:0.8.4` | Фиксированная версия (неизменяемая) |
| `:latest` | Псевдоним для `:stable` |

## Проверка установки

```bash
rdc --version
```

## Обновление

Обновить до последней версии:

```bash
rdc update
```

Проверить наличие обновлений без установки:

```bash
rdc update --check-only
```

Просмотреть текущий статус обновления:

```bash
rdc update --status
```

Откатить до предыдущей версии:

```bash
rdc update --rollback
```

## Каналы выпуска

Rediacc использует систему выпуска на основе каналов. Канал определяет, какую версию вы получаете при обновлениях CLI, установках через менеджеры пакетов и загрузках Docker.

| Канал | Описание | Когда обновляется |
|-------|----------|-------------------|
| `stable` | Релизы для продакшена | Продвигается из edge после 7-дневного тестирования |
| `edge` | Последние функции и исправления | При каждом мерже в main |
| `pr-N` | Превью-сборки PR | Автоматически для каждого pull request |

### Переключение каналов

```bash
rdc update --channel edge      # Переключиться на канал edge
rdc update --channel stable    # Вернуться на канал stable
```

Установить напрямую из канала edge:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Для менеджеров пакетов замените `stable` на `edge` в URL репозитория:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Как работают каналы

Канал применяется единообразно ко всем методам доставки:

- **Скрипты установки**: Переменная окружения `REDIACC_CHANNEL` выбирает канал
- **Репозитории пакетов**: `releases.rediacc.com/{формат}/{канал}/`
- **Теги Docker**: `ghcr.io/rediacc/elite/cli:{канал}`
- **Обновления CLI**: `rdc update` проверяет канал, настроенный при установке

### Автоматическая настройка превью PR

При установке из развертывания превью PR (например, `pr-420.rediacc.workers.dev`) канал и сервер аккаунта настраиваются автоматически:

- Бинарный файл CLI загружается из канала `pr-420`
- `rdc update` проверяет канал `pr-420` на наличие обновлений
- Все команды аккаунта/подписки подключаются к серверу превью PR
- Команды Docker на сайте превью показывают `cli:pr-420`

Ручная настройка не требуется. Скрипт установки определяет контекст развертывания из URL.

## Обновления удаленных бинарных файлов

При выполнении команд на удаленной машине CLI автоматически предоставляет соответствующий бинарный файл `renet`. Если бинарный файл обновляется, маршрутный сервер (`rediacc-router`) автоматически перезапускается для подхвата новой версии.

Перезапуск прозрачен и не вызывает **простоя**:

- Маршрутный сервер перезапускается за ~1-2 секунды.
- В течение этого окна Traefik продолжает обслуживать трафик, используя последнюю известную конфигурацию маршрутизации. Маршруты не теряются.
- Traefik подхватывает новую конфигурацию в следующем цикле опроса (в течение 5 секунд).
- **Существующие клиентские подключения (HTTP, TCP, UDP) не затрагиваются.** Маршрутный сервер является поставщиком конфигурации -- он не находится на пути данных. Traefik обрабатывает весь трафик напрямую.
- Контейнеры ваших приложений не затрагиваются -- перезапускается только системный процесс маршрутного сервера.

Чтобы пропустить автоматический перезапуск, передайте `--skip-router-restart` любой команде или установите переменную окружения `RDC_SKIP_ROUTER_RESTART=1`.
