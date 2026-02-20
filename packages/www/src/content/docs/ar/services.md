---
title: الخدمات
description: >-
  نشر وإدارة الخدمات المحتوية باستخدام ملفات Rediaccfile وشبكات الخدمات والتشغيل
  التلقائي.
category: Guides
order: 5
language: ar
sourceHash: 8add6342eea14e41
---

# الخدمات

إذا لم تكن متاكدا من الاداة المناسبة، راجع [rdc vs renet](/ar/docs/rdc-vs-renet).

تغطي هذه الصفحة كيفية نشر وإدارة الخدمات المحتوية: ملفات Rediaccfile، وشبكات الخدمات، والتشغيل/الإيقاف، والعمليات المجمّعة، والتشغيل التلقائي.

## ملف Rediaccfile

**Rediaccfile** هو سكريبت Bash يحدد كيفية تحضير خدماتك وتشغيلها وإيقافها. يجب أن يُسمّى `Rediaccfile` أو `rediaccfile` (غير حساس لحالة الأحرف) ويُوضع داخل نظام ملفات المستودع المحمّل.

يتم اكتشاف ملفات Rediaccfile في موقعين:
1. **جذر** مسار تحميل المستودع
2. **المجلدات الفرعية من المستوى الأول** لمسار التحميل (غير تكراري)

يتم تخطي المجلدات المخفية (الأسماء التي تبدأ بـ `.`).

### دوال دورة الحياة

يحتوي Rediaccfile على ما يصل إلى ثلاث دوال:

| الدالة | وقت التشغيل | الغرض | سلوك الخطأ |
|--------|------------|-------|------------|
| `prep()` | قبل `up()` | تثبيت المتطلبات، سحب الصور، تشغيل عمليات الترحيل | **إيقاف فوري** -- إذا فشلت أي `prep()`، تتوقف العملية بأكملها فوراً |
| `up()` | بعد اكتمال جميع `prep()` | تشغيل الخدمات (مثل `docker compose up -d`) | فشل الجذر **حرج** (يوقف كل شيء). فشل المجلدات الفرعية **غير حرج** (يُسجّل ويستمر) |
| `down()` | عند الإيقاف | إيقاف الخدمات (مثل `docker compose down`) | **أفضل جهد** -- يتم تسجيل الأخطاء لكن يتم تنفيذ جميع ملفات Rediaccfile دائماً |

جميع الدوال الثلاث اختيارية. إذا لم تُعرّف دالة في Rediaccfile، يتم تخطيها بصمت.

### ترتيب التنفيذ

- **التشغيل (`up`):** Rediaccfile الجذر أولاً، ثم المجلدات الفرعية بـ**ترتيب أبجدي** (A إلى Z).
- **الإيقاف (`down`):** المجلدات الفرعية بـ**ترتيب أبجدي عكسي** (Z إلى A)، ثم الجذر أخيراً.

### متغيرات البيئة

عند تنفيذ دالة Rediaccfile، تكون متغيرات البيئة التالية متاحة:

| المتغير | الوصف | مثال |
|---------|-------|------|
| `REPOSITORY_PATH` | مسار تحميل المستودع | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | معرّف المستودع GUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | معرّف الشبكة (عدد صحيح) | `2816` |
| `DOCKER_HOST` | مقبس Docker لعملية Docker المعزولة لهذا المستودع | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | عنوان IP الحلقي لكل خدمة مُعرّفة في `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

يتم إنشاء متغيرات `{SERVICE}_IP` تلقائياً من `.rediacc.json`. تقوم قاعدة التسمية بتحويل اسم الخدمة إلى أحرف كبيرة مع استبدال الشرطات بشرطات سفلية، ثم إضافة `_IP`. على سبيل المثال، `listmonk-app` تصبح `LISTMONK_APP_IP`.

> **تحذير: لا تستخدم `sudo docker` في ملفات Rediaccfile.** يعيد أمر `sudo` تعيين متغيرات البيئة، مما يعني فقدان `DOCKER_HOST` واستهداف أوامر Docker لعملية النظام بدلاً من العملية المعزولة للمستودع. هذا يكسر عزل الحاويات وقد يسبب تعارضات في المنافذ. سيمنع Rediacc التنفيذ إذا اكتشف `sudo docker` بدون `-E`.
>
> استخدم `renet compose` في ملفات Rediaccfile -- فهو يتعامل تلقائياً مع `DOCKER_HOST`، ويحقن تسميات الشبكة لاكتشاف المسارات، ويهيئ شبكات الخدمات. راجع [الشبكات](/ar/docs/networking) لتفاصيل حول كيفية كشف الخدمات عبر الوكيل العكسي. إذا استدعيت Docker مباشرة، استخدم `docker` بدون `sudo` -- دوال Rediaccfile تعمل بالفعل بصلاحيات كافية. إذا كان يجب عليك استخدام sudo، استخدم `sudo -E docker` للحفاظ على متغيرات البيئة.

### مثال

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> يعمل `docker compose` أيضاً لأن `DOCKER_HOST` يُعيّن تلقائياً، لكن `renet compose` مفضّل لأنه يحقن أيضاً تسميات `rediacc.*` اللازمة لاكتشاف مسارات الوكيل العكسي. راجع [الشبكات](/ar/docs/networking) للتفاصيل.

### تخطيط متعدد الخدمات

للمشاريع التي تحتوي على مجموعات خدمات مستقلة متعددة، استخدم المجلدات الفرعية:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: shared setup
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Database services
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API server
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

ترتيب التنفيذ لـ `up`: الجذر، ثم `backend`، `database`، `monitoring` (A-Z).
ترتيب التنفيذ لـ `down`: `monitoring`، `database`، `backend`، ثم الجذر (Z-A).

## شبكات الخدمات (.rediacc.json)

يحصل كل مستودع على شبكة فرعية /26 (64 عنوان IP) في نطاق `127.x.x.x` الحلقي. ترتبط الخدمات بعناوين IP حلقية فريدة بحيث يمكنها العمل على نفس المنافذ دون تعارض.

### ملف .rediacc.json

يربط أسماء الخدمات بأرقام **الفتحات (slots)**. تتوافق كل فتحة مع عنوان IP فريد ضمن الشبكة الفرعية للمستودع.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### الإنشاء التلقائي من Docker Compose

لا تحتاج إلى إنشاء `.rediacc.json` يدوياً. عند تشغيل `rdc repo up`، يقوم Rediacc تلقائياً بما يلي:

1. فحص جميع المجلدات التي تحتوي على Rediaccfile بحثاً عن ملفات compose (`docker-compose.yml` أو `docker-compose.yaml` أو `compose.yml` أو `compose.yaml`)
2. استخراج أسماء الخدمات من قسم `services:`
3. تعيين الفتحة التالية المتاحة لأي خدمة جديدة
4. حفظ النتيجة في `{repository}/.rediacc.json`

### حساب عنوان IP

يُحسب عنوان IP للخدمة من معرّف شبكة المستودع وفتحة الخدمة. يتم توزيع معرّف الشبكة على الثُمانية الثانية والثالثة والرابعة من عنوان الاسترجاع `127.x.y.z`. تحصل كل خدمة على إزاحة `slot + 2` (الإزاحتان 0 و 1 محجوزتان).

**مثال** لمعرّف الشبكة `2816` (`0x0B00`)، العنوان الأساسي `127.0.11.0`:

| الخدمة | الفتحة | عنوان IP |
|--------|--------|----------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

يدعم كل مستودع ما يصل إلى **61 خدمة** (الفتحات من 0 إلى 60).

### استخدام عناوين IP للخدمات في Docker Compose

بما أن كل مستودع يشغّل عملية Docker معزولة، تستخدم الخدمات `network_mode: host` وترتبط بعناوين IP الحلقية المخصصة لها:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## تشغيل الخدمات

قم بتحميل المستودع وتشغيل جميع الخدمات:

```bash
rdc repo up my-app -m server-1 --mount
```

| الخيار | الوصف |
|--------|-------|
| `--mount` | تحميل المستودع أولاً إن لم يكن محمّلاً بالفعل |
| `--prep-only` | تشغيل دوال `prep()` فقط، وتخطي `up()` |

تسلسل التنفيذ هو:
1. تحميل المستودع المشفر بـ LUKS (إذا تم تحديد `--mount`)
2. تشغيل عملية Docker المعزولة
3. إنشاء `.rediacc.json` تلقائياً من ملفات compose
4. تشغيل `prep()` في جميع ملفات Rediaccfile (بترتيب A-Z، إيقاف فوري عند الفشل)
5. تشغيل `up()` في جميع ملفات Rediaccfile (بترتيب A-Z)

## إيقاف الخدمات

```bash
rdc repo down my-app -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--unmount` | إلغاء تحميل المستودع المشفر بعد إيقاف الخدمات |

تسلسل التنفيذ هو:
1. تشغيل `down()` في جميع ملفات Rediaccfile (بترتيب Z-A عكسي، أفضل جهد)
2. إيقاف عملية Docker المعزولة (إذا تم تحديد `--unmount`)
3. إلغاء تحميل وإغلاق وحدة LUKS المشفرة (إذا تم تحديد `--unmount`)

## العمليات المجمّعة

شغّل أو أوقف جميع المستودعات على جهاز دفعة واحدة:

```bash
rdc repo up-all -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--include-forks` | تضمين المستودعات المنسوخة |
| `--mount-only` | التحميل فقط، بدون تشغيل الحاويات |
| `--dry-run` | عرض ما سيتم تنفيذه |
| `--parallel` | تشغيل العمليات بالتوازي |
| `--concurrency <n>` | الحد الأقصى للعمليات المتزامنة (الافتراضي: 3) |

## التشغيل التلقائي عند الإقلاع

افتراضياً، يجب تحميل المستودعات وتشغيلها يدوياً بعد إعادة تشغيل الخادم. يقوم **التشغيل التلقائي** بتهيئة المستودعات للتحميل تلقائياً، وتشغيل Docker، وتنفيذ `up()` في Rediaccfile عند إقلاع الخادم.

### كيف يعمل

عند تفعيل التشغيل التلقائي لمستودع:

1. يتم إنشاء ملف مفتاح LUKS عشوائي بحجم 256 بايت وإضافته إلى فتحة LUKS رقم 1 للمستودع (تبقى الفتحة 0 لعبارة مرور المستخدم)
2. يُخزّن ملف المفتاح في `{datastore}/.credentials/keys/{guid}.key` بصلاحيات `0600` (الجذر فقط)
3. يتم تثبيت خدمة systemd (`rediacc-autostart`) تعمل عند الإقلاع لتحميل جميع المستودعات المفعّلة وتشغيل خدماتها

عند إيقاف النظام، تقوم الخدمة بإيقاف جميع الخدمات بسلاسة (Rediaccfile `down()`)، وإيقاف عمليات Docker، وإغلاق وحدات LUKS.

> **ملاحظة أمنية:** تفعيل التشغيل التلقائي يخزّن ملف مفتاح LUKS على قرص الخادم. يمكن لأي شخص لديه صلاحيات الجذر على الخادم تحميل المستودع بدون عبارة المرور. قيّم هذا بناءً على نموذج التهديد الخاص بك.

### تفعيل

```bash
rdc repo autostart enable my-app -m server-1
```

سيُطلب منك إدخال عبارة مرور المستودع.

### تفعيل الكل

```bash
rdc repo autostart enable-all -m server-1
```

### تعطيل

```bash
rdc repo autostart disable my-app -m server-1
```

يزيل هذا ملف المفتاح ويحذف فتحة LUKS رقم 1.

### عرض الحالة

```bash
rdc repo autostart list -m server-1
```

## مثال كامل

ينشر هذا تطبيق ويب مع PostgreSQL و Redis وخادم API.

### 1. الإعداد

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. التحميل والتحضير

```bash
rdc repo mount webapp -m prod-1
```

### 3. إنشاء ملفات التطبيق

داخل المستودع، أنشئ الملفات التالية:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. التشغيل

```bash
rdc repo up webapp -m prod-1
```

### 5. تفعيل التشغيل التلقائي

```bash
rdc repo autostart enable webapp -m prod-1
```
