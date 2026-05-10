---
title: "Управление секретами"
description: "Храните учётные данные в месте, недоступном для форков. Только запись, по замыслу."
category: "Tutorials"
subcategory: advanced
order: 8
language: ru
sourceHash: "0b4d72c80b489e12"
---

# Управление секретами

Реальным приложениям нужны реальные учётные данные: живой ключ Stripe, пароль к базе данных, API-токен. Неправильное место для них: репозиторий, потому что форк наследует всё, что находится внутри зашифрованного образа. И вот ваша песочница начинает списывать деньги с реальных карт клиентов.

Правильное место: `rdc repo secret`. Два режима доставки, только запись по умолчанию, и форк стартует пустым.

## Смотреть урок

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## Ловушка: `.env` в репозитории

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

Большинство команд кладут `.env` в репозиторий. Очевидный шаг.

Потом они делают форк.

Форк является побайтовой копией образа родителя. Что есть в `.env` родителя, то есть и в `.env` форка. Контейнеры форка запускаются. Они читают тот же ключ Stripe. Они вызывают тот же Stripe API с продакшен-учётными данными. Для Stripe этот вызов исходит от *вас*.

Плохой день.

## Установка секрета

Решение: `rdc repo secret`. Установите секрет в режиме `env`. Значение попадёт как переменная окружения в контейнер:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Два момента:

- `--mode env`. Значение попадает как переменная окружения.
- `--current ""`. Пустая строка. Мы объявляем, что это совершенно новый секрет без предыдущего значения.

Установите ещё один в режиме `file` для всего чувствительного:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

Режим `file` никогда не помещает значение в окружение контейнера. Вместо этого он записывает его в `/run/secrets/stripe_key`, используя стандартный механизм Docker.

Посмотрите, что у вас есть:

```bash
time rdc repo secret list --name my-app
```

Вы видите имена и режимы. **Никаких значений.** Список никогда не показывает значения.

## Подключение к compose

Откройте `docker-compose.yml`. Укажите оба режима:

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

`${REDIACC_SECRET_DB_HOST}` использует режим `env`: обёртка compose в `renet` раскрывает его из хранилища секретов во время развёртывания.

Блок `secrets:` соответствует режиму `file` и использует стандартный механизм Docker. В пути хоста используется `${REDIACC_NETWORK_ID}`, поэтому один и тот же compose-файл работает для родителей и форков. У каждого форка свой сетевой ID.

Разверните:

```bash
time rdc repo up --name my-app -m my-server
```

## Проверка внутри контейнера

Оба режима должны быть доступны внутри контейнера. Проверьте секрет в режиме `env`:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. Секрет в режиме `env` попал в окружение контейнера.

Теперь в режиме `file`:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. Файл смонтирован через стандартный механизм секретов Docker.

## Прочитать его обратно невозможно

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Теперь часть, которая удивляет людей:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Вы получите дайджест. **Не значение.** Нет флага, который заставит вернуть значение. Нет команды, которая выдаст вам открытый текст обратно.

Это модель GitHub Actions: только запись. Вы можете доказать, что знаете значение секрета, передав `--current <value>` и убедившись, что предусловие выполняется. Но попросить Rediacc сказать вам, что это такое, нельзя.

Забыли значение? **Не пытайтесь подсмотреть. Ротируйте.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` пропускает проверку предусловия. Журнал аудита отмечает изменение как намеренную ротацию: громкую и осознанную.

Если вы помните старое значение, лучше докажите это:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

Это безопаснее. Защищает от ошибки «я не в том терминале».

## Финальный аккорд: форк

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Помните ловушку? Сделайте форк репозитория и посмотрите:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Пусто.**

В форке нет ключа Stripe. Нет пароля к базе данных. Нет API-токена. Контейнеры в форке не могут раскрыть `${REDIACC_SECRET_STRIPE_KEY}`. Файла по пути `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` не существует.

Форк не может притворяться вами.

Если вам нужны секреты в форке для тестирования, установите их явно с sandbox-значениями:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Теперь форк обращается к Stripe-песочнице. Продакшен-учётные данные не покинули продакшен.

## Итого

- `rdc repo secret` хранит учётные данные вне образа репозитория.
- Форк не имеет к ним доступа.
- `get` возвращает дайджест, но не значение.
- Забыли значение? Ротируйте. Не пытайтесь подсмотреть.

Секреты, которые форк не может забрать.

---

Далее: [Сеть и домены](/en/docs/tutorial-networking).
