---
title: "Установка"
description: "Установка CLI Rediacc на Linux, macOS или Windows."
category: "Guides"
order: 1
language: ru
sourceHash: "f4d35bb8c2447783"
---

# Установка

Установите CLI `rdc` на вашу рабочую станцию. Это единственный инструмент, который нужно установить вручную — всё остальное обрабатывается автоматически при настройке удаленных машин.

## Linux и macOS

Запустите скрипт установки:

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Эта команда загружает бинарный файл `rdc` в `$HOME/.local/bin/`. Убедитесь, что эта директория добавлена в PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Добавьте эту строку в профиль вашей оболочки (`~/.bashrc`, `~/.zshrc` и т.д.), чтобы сделать это постоянным.

## Windows

Запустите скрипт установки в PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Это загружает исполняемый файл `rdc.exe` в `%LOCALAPPDATA%\rediacc\bin\`. Убедитесь, что этот каталог добавлен в PATH. Установщик предложит добавить его, если он ещё не присутствует.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://releases.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Примечание: Пакет `gcompat` (слой совместимости с glibc) устанавливается автоматически как зависимость.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Проверка установки

```bash
rdc --version
```

Вы должны увидеть номер установленной версии.

## Обновление

Для обновления `rdc` до последней версии:

```bash
rdc update
```

Для проверки наличия обновлений без установки:

```bash
rdc update --check-only
```

Для отката к предыдущей версии после обновления:

```bash
rdc update rollback
```

### Каналы обновлений

CLI поддерживает два канала выпуска:
- **stable** (по умолчанию): тщательно протестированные релизы, рекомендуется для продакшена
- **edge**: новейшие функции и исправления ошибок, обновляется с каждым релизом

```bash
rdc update --channel edge      # Переключиться на канал edge
rdc update --channel stable    # Вернуться на канал stable
rdc update --status            # Показать текущий канал и версию
```

Для установки напрямую из канала edge:
```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

### Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1–2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider — it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched — only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
