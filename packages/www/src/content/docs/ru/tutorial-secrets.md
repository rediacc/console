---
title: "Управление секретами"
description: "Установите секреты для каждого репозитория, подключите их к compose, проверьте, что они достигают контейнера, ротируйте их и подтвердите, что форки ничего не наследуют."
category: "Tutorials"
order: 7
language: ru
sourceHash: "fb8bc967ed22fc10"
---

# Как управлять секретами для каждого репозитория с Rediacc

Реальным приложениям нужны учётные данные: ключ Stripe live, пароль базы данных, токен API. Неправильное место для них, внутри репозитория. Форк наследует всё, что живёт в зашифрованном образе, и его контейнеры запускаются, идентифицируя себя как родителя перед внешними сервисами. Правильное место это `rdc repo secret`. Значения попадают вне зашифрованного образа, поэтому форки начинают с пустой картой секретов.

В этом руководстве вы устанавливаете оба режима секрета, подключаете их к файлу compose, проверяете, что они достигают контейнера, ротируете один и подтверждаете, что форк ничего не наследует.

## Предварительные требования

- CLI `rdc` установлен с инициализированной конфигурацией
- Подготовленная машина и созданный репозиторий (см. [Руководство: Жизненный цикл репозитория](/ru/docs/tutorial-repos))
- Файлы `Rediaccfile` и `docker-compose.yml`, которые вы можете редактировать

## Шаг 1: Установите секрет

Доступны два режима доставки. `env` экспортирует значение как `REDIACC_SECRET_<KEY>` для интерполяции `${...}` в compose. `file` записывает значение в tmpfs-файл на стороне хоста в `/var/run/rediacc/secrets/<networkID>/<KEY>` для использования с блоком `secrets:` Docker compose. Используйте `file` для всего чувствительного. Значения в режиме env появляются в `docker inspect` и в `/proc/<pid>/environ`.

При первой записи совершенно нового ключа передайте `--current ""` (пусто), чтобы подтвердить отсутствие предыдущего значения.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Шаг 2: Перечислите, что есть

```bash
rdc repo secret list --name my-app
```

Вывод представляет собой JSON с именем и режимом каждого секрета. Значения никогда не появляются в листинге. Они даже не извлекаются с диска.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Шаг 3: Подключите к compose

Оба режима ссылаются из одного и того же `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

Строчное `stripe_key` на сервисе это имя файла `/run/secrets/<name>` внутри контейнера. Прописное `STRIPE_KEY` в пути хоста соответствует `--key`, который вы установили. `${REDIACC_NETWORK_ID}` интерполируется автоматически `renet compose`. Это важно, потому что идентификатор сети это для каждого форка, поэтому один и тот же файл compose работает в родителе и в любом форке (где, как вы увидите на шаге 6, файла просто не будет).

> **Изоляция между репозиториями принудительна.** Валидатор compose renet отклоняет любой путь `secrets: file:` (или `configs: file:`, или `env_file:`), который указывает на идентификатор сети другого репозитория. Литерал `${REDIACC_NETWORK_ID}` (или целое число вашей собственной сети) это единственная принятая форма, и `--unsafe` НЕ переопределяет это. Песочница Landlock вокруг подпроцесса bash Rediaccfile также ограничивает чтение файловой системы каталогом секретов вашей собственной сети. Поэтому даже вредоносный `cat /var/run/rediacc/secrets/<другой>/X` из Rediaccfile завершается с EACCES на уровне ядра. Вам не нужно ничего делать для активации; защита включена по умолчанию.

## Шаг 4: Разверните и проверьте

```bash
rdc repo up --name my-app -m server-1
```

После развёртывания войдите в контейнер через exec, чтобы убедиться, что оба режима поступили:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

Если вы хотите напрямую проверить tmpfs-файл на стороне хоста:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Шаг 5: Ротация без знания предыдущего значения

Вы можете прочитать дайджест с помощью `rdc repo secret get`, но никогда значение в открытом виде. Это модель только для записи. Если вам нужно проверить, что сохранённое значение совпадает с тем, что у вас есть, передайте его через `--current` и наблюдайте, как предусловие проходит или не проходит:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

Если вы полностью забыли предыдущее значение (ваш менеджер паролей потерял его, или вы унаследовали репозиторий), используйте `--rotate-secret`, чтобы пропустить предусловие. Журнал аудита громко записывает это как ротацию:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` и `--rotate-secret` взаимоисключающие. Выберите одно.

## Шаг 6: Подтвердите, что форки ничего не наследуют

Главный смысл: форкните репозиторий и проверьте список секретов форка:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Пусто. Контейнеры форка не могут интерполировать `${REDIACC_SECRET_DB_HOST}` (переменная не установлена, поэтому пустая строка), и файл по адресу `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` просто не существует. Если `repo up` форка попытается смонтировать его через блок `secrets:` compose, развёртывание завершится с чёткой ошибкой. Именно тот режим отказа, который вам нужен, потому что это означает, что песочница не может выдавать себя за продакшн перед внешними сервисами.

Чтобы использовать секреты в форке, установите их на форке явно с значениями, ограниченными песочницей:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Теперь форк общается с тестовой базой данных и аккаунтом песочницы Stripe. Учётные данные продакшна родителя никогда не покидают родителя.

## Очистка

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## См. также

- [Репозитории § Секреты](/ru/docs/repositories#secrets). Полный справочник
- [Шпаргалка CLI RDC § Секреты для каждого репозитория](/ru/docs/rdc-cheat-sheet#per-repo-secrets). Быстрый справочник команд
- [Безопасность ИИ-агентов](/ru/docs/ai-agents-safety). Симметричный шлюз мутации и структурированные подсказки действия `next` в конвертах ошибок
- [Сервисы § Использование секретов для каждого репозитория в compose](/ru/docs/services#using-per-repo-secrets-in-compose). Справочник шаблона compose
