---
title: "Config Storage (Rediacc Provider)"
description: "Безопасная синхронизация конфигурации CLI между устройствами и командами с шифрованием с нулевым разглашением."
category: "Guides"
order: 9
language: ru
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

Провайдер хранилища конфигурации Rediacc синхронизирует вашу конфигурацию CLI между устройствами и командами с шифрованием с нулевым разглашением. Ваши SSH-ключи, IP-адреса машин и учётные данные шифруются на стороне клиента перед отправкой -- даже операторы Rediacc не могут прочитать ваши данные.

## Предварительные требования

- **Провайдер passkey с поддержкой PRF**: Bitwarden, iCloud Keychain или Windows Hello
- **Включённая 2FA** для владельцев/администраторов организации (требуется для настройки хранилища и управления участниками)
- **Подписка аккаунта** с включённым config storage

## Быстрый старт

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Настройка

### Десктоп (с браузером)

```bash
rdc store add my-config --type rediacc
```

1. Открывается окно браузера с порталом аккаунта Rediacc
2. Зарегистрируйте passkey (всплывающее окно Bitwarden/iCloud/Windows Hello)
3. PRF-расширение passkey выводит ваши ключи шифрования
4. Ключи сохраняются в нативном защищённом хранилище вашей ОС (Keychain/keyctl/DPAPI)
5. Готово -- пароль запоминать не нужно

### Безголовые серверы (без браузера)

```bash
rdc store add my-config --type rediacc --headless
```

1. CLI показывает URL с кодом устройства
2. Откройте URL на телефоне или ноутбуке
3. Завершите регистрацию passkey в браузере
4. CLI автоматически получает ваши зашифрованные ключи через безопасный relay
5. Нулевое разглашение сохраняется -- сервер передаёт только непрозрачный зашифрованный blob

### Пользовательский URL сервера

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

После настройки push и pull работают без паролей и запросов:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Каждая операция использует ротационный токен, который самоуничтожается после одного использования. Никаких статических учётных данных.

## Управление командой

Участники команды управляются через веб-портал по адресу `/account/config-storage/members`.

### Добавление участников

1. Администратор открывает страницу участников config storage
2. Нажимает "Add Member" (требуется 2FA)
3. Браузер администратора шифрует командный ключ шифрования для нового участника
4. Новый участник входит в систему и принимает приглашение
5. Оба теперь могут делать push/pull одних и тех же конфигураций

### Удаление участников

1. Администратор нажимает "Remove" рядом с участником (требуется 2FA)
2. Ключи шифрования участника удаляются немедленно
3. В течение 30 секунд участник теряет весь доступ к зашифрованным конфигурациям

Ротация ключей не требуется -- сервер просто перестаёт предоставлять ключи дешифрования удалённому участнику.

## Свойства безопасности

| Свойство | Как |
|----------|-----|
| **Нулевое разглашение** | Клиент шифрует перед отправкой; сервер видит только непрозрачные blob |
| **Без мастер-пароля** | Биометрия passkey полностью заменяет пароли |
| **Разделённый вывод ключа** | CEK требует passkey_secret (клиент) + server_secret (сервер) |
| **Ротационные токены** | Каждый API-вызов генерирует новый токен; старые аннулируются |
| **Привязка к IP** | Токены привязываются к IP клиента при первом использовании |
| **Тройное шифрование** | SDK (временное окно) + CEK (клиент) + парольная фраза организации (сервер) |
| **Мгновенный отзыв** | Прекращение выдачи SDK удалённым участникам; максимальная задержка 30 секунд |
| **Обнаружение подделки** | HMAC по зашифрованным blob; проверяется при каждом pull |

Полную архитектуру безопасности смотрите в [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## Устранение неполадок

### "Passkey must support PRF extension"

Ваш провайдер passkey не поддерживает расширение PRF. Используйте:
- Bitwarden (десктопное приложение или расширение браузера)
- iCloud Keychain (Safari на macOS/iOS)
- Windows Hello

### "Two-factor authentication required"

Владельцы и администраторы организации должны включить 2FA перед настройкой config storage. Перейдите в Account Settings -> Security -> Enable 2FA.

### "Version conflict"

Другой участник команды отправил более новую версию. Сначала загрузите:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Токены истекают после 24 часов неактивности. Выполните любую команду для обновления:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

Ключ шифрования был потерян из защищённого хранилища ОС (перезагрузка на Linux, сброс keychain). Повторите настройку:
```bash
rdc store add my-config --type rediacc
```
