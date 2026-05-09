---
title: "Сеть и домены"
description: "Сделайте приложение доступным в интернете с помощью домена, автоматического TLS и обратного прокси Traefik."
category: "Tutorials"
subcategory: advanced
order: 9
language: ru
sourceHash: "9f72a61ed1ff4cb9"
---

# Сеть и домены

Приложение работает, но до него пока никто не может добраться. В этом уроке вы получите реальный домен, автоматический TLS через Let's Encrypt и прокси Traefik, автоматически обнаруживающий ваши контейнеры. Вам понадобится домен на Cloudflare и API-токен.

## Смотреть урок

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## Четыре шага

![Token, configure, push, deploy](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Получите** API-токен Cloudflare.
2. **Настройте** инфраструктуру в `rdc`.
3. **Отправьте** конфигурацию на сервер.
4. **Разверните** прокси.

## Шаг 1: API-токен Cloudflare

В панели управления Cloudflare перейдите в **My Profile → API Tokens** и создайте токен с правом **Zone DNS Edit**. Скопируйте значение токена. Увидите его только один раз.

## Шаг 2: Настройка инфраструктуры

Укажите `rdc` ваш публичный IP, базовый домен, email для сертификата и токен:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Замените IP, домен, email и токен на свои.

`--cert-email` и `--cf-dns-token` используются для всех ваших машин, поэтому устанавливаются один раз.

## Шаг 3: Отправка конфигурации на сервер

```bash
time rdc config infra push -m my-server
```

Эта команда автоматически создаёт DNS-записи на Cloudflare и подготавливает конфигурацию прокси на сервере.

## Шаг 4: Развёртывание прокси

Сам прокси пока не запущен. Разверните его из встроенного шаблона `proxy` в небольшом репозитории `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

Готово. Traefik запущен. Ваше приложение доступно по адресу:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik обнаруживает ваши контейнеры каждые 5 секунд. TLS-сертификаты от Let's Encrypt получаются автоматически. Никакой ручной настройки прокси не нужно.

---

Далее: [Продакшен-режим](/en/docs/tutorial-production-mode).
