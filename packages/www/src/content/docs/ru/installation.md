---
title: "Установка"
description: "Установка CLI Rediacc на Linux, macOS или Windows."
category: "Getting Started"
order: 1
language: ru
---

# Установка

Установите CLI `rdc` на вашу рабочую станцию. Это единственный инструмент, который нужно установить вручную — всё остальное обрабатывается автоматически при настройке удаленных машин.

## Linux и macOS

Запустите скрипт установки:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Эта команда загружает бинарный файл `rdc` в `$HOME/.local/bin/`. Убедитесь, что эта директория добавлена в PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Добавьте эту строку в профиль вашей оболочки (`~/.bashrc`, `~/.zshrc` и т.д.), чтобы сделать это постоянным.

## Windows (WSL2)

Rediacc работает внутри WSL2 на Windows. Если у вас ещё не настроен WSL2:

```powershell
wsl --install
```

Затем внутри вашего Linux-дистрибутива WSL2 запустите тот же скрипт установки:

```bash
curl -fsSL https://get.rediacc.com | sh
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
