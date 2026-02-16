---
title: "دليل البدء السريع"
description: "دليل خطوة بخطوة لنشر بنية تحتية مشفرة ومعزولة على خوادمك الخاصة باستخدام Rediacc في الوضع المحلي."
category: "Core Concepts"
order: 0
language: ar
---

# دليل البدء السريع

يرشدك هذا الدليل خلال نشر بنية تحتية مشفرة ومعزولة على خوادمك الخاصة باستخدام Rediacc في **الوضع المحلي**. بنهاية هذا الدليل، سيكون لديك مستودع يعمل بالكامل يشغّل خدمات حاويات على جهاز بعيد، وكل ذلك يُدار من محطة عملك.

الوضع المحلي يعني أن كل شيء يعمل على بنية تحتية تتحكم بها أنت. لا حسابات سحابية، ولا اعتماد على خدمات SaaS. محطة عملك تنظّم الخوادم البعيدة عبر SSH، وجميع الحالات تُخزّن محلياً على جهازك وعلى الخوادم نفسها.

## نظرة عامة على البنية

يستخدم Rediacc بنية ثنائية الأدوات:

```
Your Workstation                    Remote Server
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** يعمل على محطة عملك (macOS أو Linux). يقرأ الإعدادات المحلية، ويتصل بالأجهزة البعيدة عبر SSH، ويستدعي أوامر renet.
- **renet** يعمل على الخادم البعيد بصلاحيات الجذر. يدير صور الأقراص المشفرة بـ LUKS، وعمليات Docker المعزولة، وتنسيق الخدمات، وإعدادات الوكيل العكسي.

كل أمر تكتبه محلياً يُترجم إلى استدعاء SSH ينفّذ renet على الجهاز البعيد. لن تحتاج أبداً إلى الاتصال بالخوادم يدوياً عبر SSH.

## ما ستحتاجه

قبل البدء، تأكد من توفر ما يلي:

**على محطة عملك:**
- نظام macOS أو Linux مع عميل SSH
- زوج مفاتيح SSH (مثل `~/.ssh/id_ed25519` أو `~/.ssh/id_rsa`)

**على الخادم البعيد:**
- نظام Ubuntu 20.04+ أو Debian 11+ (قد تعمل توزيعات Linux أخرى لكنها غير مختبرة)
- حساب مستخدم بصلاحيات `sudo`
- مفتاحك العام لـ SSH مُضاف إلى `~/.ssh/authorized_keys`
- مساحة قرص فارغة لا تقل عن 20 جيجابايت (أكثر حسب أحمال العمل)

## الخطوة 1: تثبيت rdc

ثبّت واجهة سطر أوامر Rediacc على محطة عملك:

```bash
curl -fsSL https://get.rediacc.com | sh
```

يقوم هذا بتنزيل ملف `rdc` التنفيذي إلى `$HOME/.local/bin/`. تأكد من أن هذا المجلد موجود في متغير PATH. تحقق من التثبيت:

```bash
rdc --help
```

> للتحديث لاحقاً، شغّل `rdc update`.

## الخطوة 2: إنشاء سياق محلي

**السياق** هو إعداد مسمّى يخزّن بيانات اعتماد SSH، وتعريفات الأجهزة، وربط المستودعات. فكّر فيه كمساحة عمل للمشروع.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `--ssh-key <path>` | نعم | مسار مفتاح SSH الخاص بك. يتم توسيع رمز التلدة (`~`) تلقائياً. |
| `--renet-path <path>` | لا | مسار مخصص لملف renet التنفيذي على الأجهزة البعيدة. القيمة الافتراضية هي موقع التثبيت القياسي. |

ينشئ هذا سياقاً محلياً باسم `my-infra` ويخزّنه في `~/.rediacc/config.json`.

> يمكنك إنشاء سياقات متعددة (مثل `production`، `staging`، `dev`). بدّل بينها باستخدام خيار `--context` مع أي أمر.

## الخطوة 3: إضافة جهاز

سجّل خادمك البعيد كجهاز في السياق:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| الخيار | مطلوب | الافتراضي | الوصف |
|--------|-------|-----------|-------|
| `--ip <address>` | نعم | - | عنوان IP أو اسم المضيف للخادم البعيد. |
| `--user <username>` | نعم | - | اسم مستخدم SSH على الخادم البعيد. |
| `--port <port>` | لا | `22` | منفذ SSH. |
| `--datastore <path>` | لا | `/mnt/rediacc` | المسار على الخادم حيث يخزّن Rediacc المستودعات المشفرة. |

بعد إضافة الجهاز، يقوم rdc تلقائياً بتشغيل `ssh-keyscan` لجلب مفاتيح المضيف الخاصة بالخادم. يمكنك أيضاً تشغيل هذا يدوياً:

```bash
rdc context scan-keys server-1
```

لعرض جميع الأجهزة المسجلة:

```bash
rdc context machines
```

## الخطوة 4: إعداد الجهاز

قم بتجهيز الخادم البعيد بجميع المتطلبات اللازمة:

```bash
rdc context setup-machine server-1
```

يقوم هذا الأمر بما يلي:
1. رفع ملف renet التنفيذي إلى الخادم عبر SFTP
2. تثبيت Docker و containerd و cryptsetup (إن لم تكن موجودة)
3. إنشاء مجلد مخزن البيانات وتحضيره للمستودعات المشفرة

| الخيار | مطلوب | الافتراضي | الوصف |
|--------|-------|-----------|-------|
| `--datastore <path>` | لا | `/mnt/rediacc` | مجلد مخزن البيانات على الخادم. |
| `--datastore-size <size>` | لا | `95%` | نسبة القرص المتاح المخصصة لمخزن البيانات. |
| `--debug` | لا | `false` | تفعيل المخرجات التفصيلية لاستكشاف الأخطاء. |

> يجب تشغيل الإعداد مرة واحدة فقط لكل جهاز. من الآمن إعادة تشغيله عند الحاجة.

## الخطوة 5: إنشاء مستودع

**المستودع** هو صورة قرص مشفرة بـ LUKS على الخادم البعيد. عند تحميله، يوفر:
- نظام ملفات معزول لبيانات تطبيقك
- عملية Docker مخصصة (منفصلة عن Docker المضيف)
- عناوين IP حلقية فريدة لكل خدمة ضمن شبكة فرعية /26

أنشئ مستودعاً:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `-m, --machine <name>` | نعم | الجهاز المستهدف حيث سيتم إنشاء المستودع. |
| `--size <size>` | نعم | حجم صورة القرص المشفرة (مثل `5G`، `10G`، `50G`). |

ستظهر في المخرجات ثلاث قيم مُنشأة تلقائياً:

- **معرّف المستودع (GUID)** -- معرّف UUID يحدد صورة القرص المشفرة على الخادم.
- **بيانات الاعتماد (Credential)** -- عبارة مرور عشوائية تُستخدم لتشفير وفك تشفير وحدة LUKS.
- **معرّف الشبكة (Network ID)** -- عدد صحيح (يبدأ من 2816، ويزداد بمقدار 64) يحدد الشبكة الفرعية لعناوين IP لخدمات هذا المستودع.

> **احفظ بيانات الاعتماد بأمان.** إنها مفتاح التشفير لمستودعك. في حالة فقدانها، لا يمكن استرجاع البيانات. يتم تخزين بيانات الاعتماد في ملف `config.json` المحلي ولكن لا تُخزّن على الخادم.

## الخطوة 6: ملف Rediaccfile

**Rediaccfile** هو سكريبت Bash يحدد كيفية تحضير خدماتك وتشغيلها وإيقافها. إنه الآلية الأساسية لإدارة دورة حياة الخدمات.

### ما هو Rediaccfile؟

Rediaccfile هو سكريبت Bash عادي يحتوي على ما يصل إلى ثلاث دوال: `prep()` و `up()` و `down()`. يجب أن يُسمّى `Rediaccfile` أو `rediaccfile` (غير حساس لحالة الأحرف) ويُوضع داخل نظام ملفات المستودع المحمّل.

يتم اكتشاف ملفات Rediaccfile في موقعين:
1. **جذر** مسار تحميل المستودع
2. **المجلدات الفرعية من المستوى الأول** لمسار التحميل (غير تكراري)

يتم تخطي المجلدات المخفية (الأسماء التي تبدأ بـ `.`).

### دوال دورة الحياة

| الدالة | وقت التشغيل | الغرض | سلوك الخطأ |
|--------|------------|-------|------------|
| `prep()` | قبل `up()` | تثبيت المتطلبات، سحب الصور، تشغيل عمليات الترحيل | **إيقاف فوري** -- إذا فشلت أي `prep()`، تتوقف العملية بأكملها فوراً. |
| `up()` | بعد اكتمال جميع `prep()` | تشغيل الخدمات (مثل `docker compose up -d`) | فشل Rediaccfile الجذر **حرج** (يوقف كل شيء). فشل المجلدات الفرعية **غير حرج** (يُسجّل ويستمر للتالي). |
| `down()` | عند الإيقاف | إيقاف الخدمات (مثل `docker compose down`) | **أفضل جهد** -- يتم تسجيل الأخطاء لكن يتم تنفيذ جميع ملفات Rediaccfile دائماً. |

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

يتم إنشاء متغيرات `{SERVICE}_IP` تلقائياً من `.rediacc.json` (انظر الخطوة 7). تقوم قاعدة التسمية بتحويل اسم الخدمة إلى أحرف كبيرة مع استبدال الشرطات بشرطات سفلية، ثم إضافة `_IP`. على سبيل المثال، `listmonk-app` تصبح `LISTMONK_APP_IP`.

### مثال على Rediaccfile

ملف Rediaccfile بسيط لتطبيق ويب:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### مثال متعدد الخدمات

للمشاريع التي تحتوي على مجموعات خدمات مستقلة متعددة، استخدم المجلدات الفرعية:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: shared setup (e.g., create Docker networks)
├── docker-compose.yml       # Root compose file
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

## الخطوة 7: شبكات الخدمات (.rediacc.json)

يحصل كل مستودع على شبكة فرعية /26 (64 عنوان IP) في نطاق `127.x.x.x` الحلقي. ترتبط الخدمات بعناوين IP حلقية فريدة بحيث يمكنها العمل على نفس المنافذ دون تعارض. على سبيل المثال، يمكن لنسختين من PostgreSQL الاستماع على المنفذ 5432، كل منهما على عنوان IP مختلف.

### ملف .rediacc.json

يربط ملف `.rediacc.json` أسماء الخدمات بأرقام **الفتحات (slots)**. تتوافق كل فتحة مع عنوان IP فريد ضمن الشبكة الفرعية للمستودع.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

تُكتب الخدمات بترتيب أبجدي.

### الإنشاء التلقائي من Docker Compose

لا تحتاج إلى إنشاء `.rediacc.json` يدوياً. عند تشغيل `rdc repo up`، يقوم Rediacc تلقائياً بما يلي:

1. فحص جميع المجلدات التي تحتوي على Rediaccfile بحثاً عن ملفات compose (`docker-compose.yml` أو `docker-compose.yaml` أو `compose.yml` أو `compose.yaml`).
2. استخراج أسماء الخدمات من قسم `services:` في كل ملف compose.
3. تعيين الفتحة التالية المتاحة لأي خدمة جديدة.
4. حفظ النتيجة في `{repository}/.rediacc.json`.

### حساب عنوان IP

يُحسب عنوان IP للخدمة من معرّف شبكة المستودع وفتحة الخدمة:

```
Base IP = 127.{networkID / 65536}.{(networkID / 256) % 256}.{networkID % 256}
Service IP = 127.{(networkID + slot + 2) / 65536}.{((networkID + slot + 2) / 256) % 256}.{(networkID + slot + 2) % 256}
```

أول إزاحتين (0 و 1) محجوزتان لعنوان الشبكة والبوابة. تبدأ فتحات الخدمات من الإزاحة 2.

**مثال** لمعرّف الشبكة `2816`:

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

يتم تصدير المتغيرات `${POSTGRES_IP}` و `${API_IP}` تلقائياً من `.rediacc.json` عند تشغيل Rediaccfile.

## الخطوة 8: تشغيل الخدمات

قم بتحميل المستودع وتشغيل جميع الخدمات:

```bash
rdc repo up my-app -m server-1 --mount
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `-m, --machine <name>` | نعم | الجهاز المستهدف. |
| `--mount` | لا | تحميل المستودع أولاً إن لم يكن محمّلاً بالفعل. بدون هذا الخيار، يجب أن يكون المستودع محمّلاً مسبقاً. |
| `--prep-only` | لا | تشغيل دوال `prep()` فقط، وتخطي `up()`. مفيد لسحب الصور مسبقاً أو تشغيل عمليات الترحيل. |

تسلسل التنفيذ هو:

1. تحميل المستودع المشفر بـ LUKS (إذا تم تحديد `--mount`)
2. تشغيل عملية Docker المعزولة لهذا المستودع
3. إنشاء `.rediacc.json` تلقائياً من ملفات compose
4. تشغيل `prep()` في جميع ملفات Rediaccfile (بترتيب A-Z، إيقاف فوري عند الفشل)
5. تشغيل `up()` في جميع ملفات Rediaccfile (بترتيب A-Z)

## الخطوة 9: إيقاف الخدمات

أوقف جميع الخدمات في مستودع:

```bash
rdc repo down my-app -m server-1
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `-m, --machine <name>` | نعم | الجهاز المستهدف. |
| `--unmount` | لا | إلغاء تحميل المستودع المشفر بعد إيقاف الخدمات. يقوم أيضاً بإيقاف عملية Docker المعزولة وإغلاق وحدة LUKS. |

تسلسل التنفيذ هو:

1. تشغيل `down()` في جميع ملفات Rediaccfile (بترتيب Z-A عكسي، أفضل جهد)
2. إيقاف عملية Docker المعزولة (إذا تم تحديد `--unmount`)
3. إلغاء تحميل وإغلاق وحدة LUKS المشفرة (إذا تم تحديد `--unmount`)

## عمليات شائعة أخرى

### التحميل وإلغاء التحميل (بدون تشغيل الخدمات)

```bash
rdc repo mount my-app -m server-1     # Decrypt and mount
rdc repo unmount my-app -m server-1   # Unmount and re-encrypt
```

### التحقق من حالة المستودع

```bash
rdc repo status my-app -m server-1
```

### عرض جميع المستودعات

```bash
rdc repo list -m server-1
```

### تغيير حجم مستودع

```bash
rdc repo resize my-app -m server-1 --size 20G    # Set to exact size
rdc repo expand my-app -m server-1 --size 5G      # Add 5G to current size
```

### حذف مستودع

```bash
rdc repo delete my-app -m server-1
```

> يؤدي هذا إلى تدمير صورة القرص المشفرة وجميع البيانات الموجودة فيها بشكل دائم.

### نسخ مستودع (Fork)

أنشئ نسخة من مستودع موجود في حالته الحالية:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

ينشئ هذا نسخة مشفرة جديدة بمعرّف GUID ومعرّف شبكة خاصين بها. تشترك النسخة في نفس بيانات اعتماد LUKS مع المستودع الأصلي.

### التحقق من سلامة مستودع

تحقق من سلامة نظام ملفات مستودع:

```bash
rdc repo validate my-app -m server-1
```

## التشغيل التلقائي عند الإقلاع

افتراضياً، يجب تحميل المستودعات وتشغيلها يدوياً بعد إعادة تشغيل الخادم. يقوم **التشغيل التلقائي** بتهيئة المستودعات للتحميل تلقائياً، وتشغيل Docker، وتنفيذ `up()` في Rediaccfile عند إقلاع الخادم.

### كيف يعمل

عند تفعيل التشغيل التلقائي لمستودع:

1. يتم إنشاء ملف مفتاح LUKS عشوائي بحجم 256 بايت وإضافته إلى فتحة LUKS رقم 1 للمستودع (تبقى الفتحة 0 لعبارة مرور المستخدم).
2. يُخزّن ملف المفتاح في `{datastore}/.credentials/keys/{guid}.key` بصلاحيات `0600` (الجذر فقط).
3. يتم تثبيت خدمة systemd (`rediacc-autostart`) تعمل عند الإقلاع لتحميل جميع المستودعات المفعّلة وتشغيل خدماتها.

عند إيقاف النظام أو إعادة تشغيله، تقوم الخدمة بإيقاف جميع الخدمات بسلاسة (Rediaccfile `down()`)، وإيقاف عمليات Docker، وإغلاق وحدات LUKS.

> **ملاحظة أمنية:** تفعيل التشغيل التلقائي يخزّن ملف مفتاح LUKS على قرص الخادم. يمكن لأي شخص لديه صلاحيات الجذر على الخادم تحميل المستودع بدون عبارة المرور. هذا تنازل بين الراحة (التشغيل التلقائي عند الإقلاع) والأمان (طلب إدخال عبارة المرور يدوياً). قيّم هذا بناءً على نموذج التهديد الخاص بك.

### تفعيل التشغيل التلقائي

```bash
rdc repo autostart enable my-app -m server-1
```

سيُطلب منك إدخال عبارة مرور المستودع. هذا ضروري للسماح بإضافة ملف المفتاح إلى وحدة LUKS.

### تفعيل التشغيل التلقائي لجميع المستودعات

```bash
rdc repo autostart enable-all -m server-1
```

### تعطيل التشغيل التلقائي

```bash
rdc repo autostart disable my-app -m server-1
```

يزيل هذا ملف المفتاح ويحذف فتحة LUKS رقم 1. لن يتم تحميل المستودع تلقائياً عند الإقلاع بعد ذلك.

### عرض حالة التشغيل التلقائي

```bash
rdc repo autostart list -m server-1
```

يعرض المستودعات التي تم تفعيل التشغيل التلقائي لها وما إذا كانت خدمة systemd مثبّتة.

## مثال كامل: نشر تطبيق ويب

يوضح هذا المثال الشامل نشر تطبيق ويب مع PostgreSQL و Redis وخادم API.

### 1. إعداد البيئة

```bash
# Install rdc
curl -fsSL https://get.rediacc.com | sh

# Create a local context
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Register your server
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Provision the server
rdc context setup-machine prod-1

# Create an encrypted repository (10 GB)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. تحميل المستودع وتحضيره

```bash
rdc repo mount webapp -m prod-1
```

اتصل بالخادم عبر SSH وأنشئ ملفات التطبيق داخل المستودع المحمّل. يظهر مسار التحميل في المخرجات (عادةً `/mnt/rediacc/repos/{guid}`).

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
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
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
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. تشغيل كل شيء

```bash
rdc repo up webapp -m prod-1
```

سيقوم هذا بما يلي:
1. إنشاء `.rediacc.json` تلقائياً مع فتحات لـ `api` و `postgres` و `redis`
2. تشغيل `prep()` لإنشاء المجلدات وسحب الصور
3. تشغيل `up()` لتشغيل جميع الحاويات

### 5. تفعيل التشغيل التلقائي

```bash
rdc repo autostart enable webapp -m prod-1
```

بعد إعادة تشغيل الخادم، سيتم تحميل المستودع وتشغيل جميع الخدمات تلقائياً.

## فهم إعدادات السياق

يتم تخزين جميع إعدادات السياق في `~/.rediacc/config.json`. فيما يلي مثال مشروح لما يبدو عليه هذا الملف بعد إكمال الخطوات أعلاه:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**الحقول الرئيسية:**

| الحقل | الوصف |
|-------|-------|
| `mode` | `"local"` للوضع المحلي، `"s3"` للسياقات المدعومة بـ S3. |
| `apiUrl` | `"local://"` يشير إلى الوضع المحلي (بدون API بعيد). |
| `ssh.privateKeyPath` | مسار مفتاح SSH الخاص المستخدم لجميع اتصالات الأجهزة. |
| `machines.<name>.knownHosts` | مفاتيح مضيف SSH من `ssh-keyscan`، تُستخدم للتحقق من هوية الخادم. |
| `repositories.<name>.repositoryGuid` | معرّف UUID يحدد صورة القرص المشفرة على الخادم. |
| `repositories.<name>.credential` | عبارة مرور تشفير LUKS. **لا تُخزّن على الخادم.** |
| `repositories.<name>.networkId` | معرّف الشبكة الذي يحدد الشبكة الفرعية لعناوين IP (2816 + n*64). يُعيَّن تلقائياً. |

> يحتوي هذا الملف على بيانات حساسة (مسارات مفاتيح SSH، بيانات اعتماد LUKS). يُخزّن بصلاحيات `0600` (قراءة/كتابة للمالك فقط). لا تشاركه أو تضعه في نظام التحكم بالإصدارات.

## استكشاف الأخطاء وإصلاحها

### فشل اتصال SSH

- تحقق من إمكانية الاتصال يدوياً: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- شغّل `rdc context scan-keys server-1` لتحديث مفاتيح المضيف
- تأكد من تطابق منفذ SSH: `--port 22`

### فشل إعداد الجهاز

- تأكد من أن المستخدم لديه صلاحيات sudo بدون كلمة مرور، أو قم بتهيئة `NOPASSWD` للأوامر المطلوبة
- تحقق من المساحة المتاحة على القرص في الخادم
- شغّل مع `--debug` للمخرجات التفصيلية: `rdc context setup-machine server-1 --debug`

### فشل إنشاء المستودع

- تحقق من اكتمال الإعداد: يجب أن يكون مجلد مخزن البيانات موجوداً
- تحقق من مساحة القرص على الخادم
- تأكد من تثبيت ملف renet التنفيذي (أعد تشغيل الإعداد إذا لزم الأمر)

### فشل تشغيل الخدمات

- تحقق من صيغة Rediaccfile: يجب أن يكون Bash صالحاً
- تأكد من أن ملفات `docker compose` تستخدم `network_mode: host`
- تحقق من إمكانية الوصول إلى صور Docker (ضع في اعتبارك `docker compose pull` في `prep()`)
- تحقق من سجلات الحاويات: اتصل بالخادم عبر SSH واستخدم `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### أخطاء رفض الصلاحيات

- عمليات المستودع تتطلب صلاحيات الجذر على الخادم (renet يعمل عبر `sudo`)
- تحقق من أن المستخدم في مجموعة `sudo`
- تأكد من صحة صلاحيات مجلد مخزن البيانات

## الخطوات التالية

- **مرجع سطر الأوامر** -- راجع صفحة [تطبيق سطر الأوامر](/ar/docs/cli-application) للحصول على المرجع الكامل للأوامر.
- **النسخ الاحتياطي والاسترداد** -- قم بإعداد نسخ احتياطية خارج الموقع إلى تخزين متوافق مع S3 للتعافي من الكوارث.
- **الوكيل العكسي** -- قم بتهيئة Traefik لـ HTTPS مع شهادات Let's Encrypt التلقائية.
- **نقاط فحص CRIU واستعادتها** -- أنشئ نقاط فحص للحاويات قيد التشغيل للترحيل الفوري أو التراجع.
