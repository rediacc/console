---
title: "Развёртывание первого приложения"
description: "Разверните контейнеризированное приложение из встроенного шаблона с помощью renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: ru
sourceHash: "f75b5b6a716e94bf"
---

# Развёртывание первого приложения

У вас есть пустой репозиторий. `rdc` поставляется со встроенными шаблонами, позволяющими запускать реальные приложения без написания `docker-compose` с нуля. Три шага: выберите шаблон, примените его, запустите.

## Смотреть урок

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Выбрать · Применить · Запустить

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Шаг 1: Выбор шаблона

Просмотрите доступные шаблоны:

```bash
time rdc repo template list
```

Вы увидите готовые конфигурации для популярных приложений: Postgres, Redis, веб-серверы и многое другое.

## Шаг 2: Применение шаблона

Добавьте шаблон в репозиторий. Используем `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

В репозитории появятся два новых файла: `docker-compose.yml` и `Rediaccfile`. Compose-файл описывает контейнеры; `Rediaccfile` определяет, что происходит при запуске и остановке приложения (хуки жизненного цикла `up` и `down`).

## Шаг 3: Запуск

Вы уже находитесь внутри песочницы репозитория (через подключение VS Code из предыдущего урока), поэтому используйте `renet` напрямую:

```bash
time renet dev up
```

Готово. Приложение запущено. Проверьте:

```bash
time docker ps
```

Здесь `docker ps` показывает только контейнеры этого репозитория. Другие репозитории на том же сервере имеют собственные Docker-демоны и отсюда полностью невидимы.

---

Далее: [Работа с репозиторием](/en/docs/tutorial-work-with-repo).
