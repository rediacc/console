---
title: "Работа с репозиторием"
description: "Пробросьте порт в браузер, выполняйте команды внутри песочницы и синхронизируйте файлы между ноутбуком и репозиторием."
category: "Tutorials"
subcategory: essentials
order: 6
language: ru
sourceHash: "3d56eb69e72c1a5a"
---

# Работа с репозиторием

Приложение запущено, но пока вы видели его только через `docker ps`. Три команды покрывают повседневную работу: **tunnel** (открыть приложение в браузере), **term** (выполнять команды внутри песочницы), **sync** (перемещать файлы между ноутбуком и репозиторием).

## Смотреть урок

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## Три команды на каждый день

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: открыть приложение в браузере.
2. **Term**: выполнить команду внутри песочницы.
3. **Sync**: перемещать файлы туда и обратно.

## Tunnel: приложение в браузере

Приложение работает на сервере, а не на ноутбуке. Пробросьте порт контейнера по SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Откройте `localhost` в браузере. Приложение уже там. Нажмите `Ctrl+C`, когда закончите.

Для другого контейнера замените `-c` и укажите порт:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: выполнение команд внутри репозитория

Не нужен VS Code, когда достаточно оболочки:

```bash
rdc term connect -m my-server -r my-app
```

Теперь вы внутри песочницы репозитория. Попробуйте:

```bash
time docker ps
```

Вы видите только контейнеры `my-app`, тот же вид, что и в VS Code.

Для разовых команд используйте `-c` и пропустите интерактивную оболочку:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: перемещение файлов между ноутбуком и репозиторием

Загрузите папку с ноутбука в репозиторий:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Скачайте файлы обратно:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Если не уверены, сначала посмотрите превью. `--dry-run` покажет, что изменится, без фактического копирования:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Три команды для полного рабочего цикла.

---

Далее: [Форк репозитория](/en/docs/tutorial-forking).
