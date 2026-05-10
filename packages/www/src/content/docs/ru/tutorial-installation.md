---
title: "Установка"
description: "Установите rdc CLI на ноутбук одной командой и проверьте результат с помощью rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: ru
sourceHash: "99d4ca1a4f89278e"
---

# Установка

Установка `rdc` состоит из трёх шагов: откройте страницу установки, выберите операционную систему, вставьте команду в терминал. Обычно весь процесс занимает одну-две минуты.

## Смотреть урок

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Три шага

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. Откройте [страницу установки](/en/install).
2. Выберите операционную систему.
3. Скопируйте команду установки и вставьте её в терминал.

## Установка на вашей платформе

Страница установки автоматически подберёт нужную команду, но вот универсальные однострочники.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> Префикс `time` является приёмом оболочки, который выводит время выполнения команды. Мы используем его на протяжении всей серии, чтобы вы видели реальную скорость каждого шага. Он необязателен: уберите его, если он вам не нужен.

## Проверка установки

После завершения скрипта убедитесь, что всё необходимое для `rdc` присутствует:

```bash
time rdc doctor
```

`rdc doctor` проверяет Node, SSH и остальные зависимости `rdc`, сообщая о любых пробелах.

## Почему `rdc` живёт на ноутбуке

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` является CLI на вашем ноутбуке. На сервере работает отдельный компонент `renet`, которым `rdc` управляет по SSH. Вам никогда не придётся вручную подключаться к серверу по SSH: `rdc` сделает это за вас.

В следующих двух уроках мы всё это настроим как положено.

---

Далее: [Настройка SSH-ключа](/en/docs/tutorial-ssh-keys).
