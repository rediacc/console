---
title: "دليل الترحيل"
description: "ترحيل المشاريع الحالية إلى مستودعات Rediacc المشفرة."
category: "Guides"
order: 11
language: ar
sourceHash: "5e13e363e9dce55f"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# دليل الترحيل

قم بترحيل مشروع حالي، الملفات وخدمات Docker وقواعد البيانات، من خادم تقليدي أو بيئة تطوير محلية إلى مستودع Rediacc مشفر.

## المتطلبات الأساسية

- تثبيت واجهة سطر الأوامر `rdc` ([التثبيت](/ar/docs/installation))
- إضافة جهاز وتجهيزه ([الإعداد](/ar/docs/setup))
- مساحة قرص كافية على الخادم لمشروعك (تحقق باستخدام `rdc machine status`)

## الخطوة 1: إنشاء مستودع

أنشئ مستودعاً مشفراً بحجم يناسب مشروعك. خصص مساحة إضافية لصور Docker وبيانات الحاويات.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **نصيحة:** يمكنك تغيير الحجم لاحقاً باستخدام `rdc repo resize` إذا لزم الأمر، لكن يجب إلغاء تحميل المستودع أولاً. من الأسهل البدء بمساحة كافية.

## الخطوة 2: رفع الملفات

استخدم `rdc repo sync upload` لنقل ملفات مشروعك إلى المستودع.

```bash
# معاينة ما سيتم نقله (بدون إجراء تغييرات)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# رفع الملفات
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

يجب أن يكون المستودع محمّلاً قبل الرفع. إذا لم يكن محمّلاً بالفعل:

```bash
rdc repo mount --name my-project -m server-1
```

لعمليات المزامنة اللاحقة حيث تريد أن يطابق المحتوى البعيد دليلك المحلي تماماً:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> يحذف خيار `--mirror` الملفات على الخادم البعيد التي لا توجد محلياً. استخدم `--dry-run` أولاً للتحقق.

## الخطوة 3: إصلاح ملكية الملفات

تصل الملفات المرفوعة بمعرّف المستخدم المحلي الخاص بك (مثل 1000). يستخدم Rediacc مستخدماً موحداً (UID 7111) بحيث يتمتع VS Code وجلسات الطرفية والأدوات جميعها بوصول متسق. شغّل أمر الملكية للتحويل:

```bash
rdc repo ownership --name my-project -m server-1
```

### استثناء مدرك لـ Docker

إذا كانت حاويات Docker قيد التشغيل (أو تم تشغيلها سابقاً)، يكتشف أمر الملكية تلقائياً أدلة البيانات القابلة للكتابة الخاصة بها **ويتخطاها**. هذا يمنع تعطيل الحاويات التي تدير ملفاتها الخاصة بمعرّفات مستخدم مختلفة (مثل MariaDB يستخدم UID 999، وNextcloud يستخدم UID 33).

يعرض الأمر تقريراً بما يفعله:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### متى يتم التشغيل

- **بعد رفع الملفات**، لتحويل معرّف المستخدم المحلي إلى 7111
- **بعد بدء الحاويات**، إذا كنت تريد استثناء أدلة أحجام Docker تلقائياً. إذا لم تكن الحاويات قد بدأت بعد، فلا توجد أحجام للاستثناء وسيتم تغيير ملكية جميع الأدلة (وهذا مقبول، ستعيد الحاويات إنشاء بياناتها عند أول تشغيل)

### وضع الإجبار

لتخطي اكتشاف أحجام Docker وتغيير ملكية كل شيء، بما في ذلك أدلة بيانات الحاويات:

```bash
rdc repo ownership --name my-project -m server-1
```

> **تحذير:** قد يؤدي هذا إلى تعطيل الحاويات قيد التشغيل. أوقفها أولاً باستخدام `rdc repo down` إذا لزم الأمر.

### معرّف مستخدم مخصص

لتعيين معرّف مستخدم غير القيمة الافتراضية 7111:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

## الخطوة 4: إعداد Rediaccfile

أنشئ ملف `Rediaccfile` في جذر مشروعك. هذا السكربت بلغة Bash يحدد كيفية بدء خدماتك وإيقافها.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

دالتا دورة الحياة:

| الدالة | الغرض | سلوك الخطأ |
|--------|-------|------------|
| `up()` | بدء الخدمات | فشل الجذر حرج؛ فشل الأدلة الفرعية يُسجّل ويستمر |
| `down()` | إيقاف الخدمات | بأفضل جهد: يحاول دائماً تنفيذ الكل |

> **مهم:** استخدم دائماً `renet compose --` بدلاً من `docker compose` في Rediaccfile الخاص بك. يفرض غلاف `renet compose` شبكة المضيف، وقدرات CRIU للحفظ/الاستعادة، وتخصيص عناوين IP، واكتشاف الخدمات المطلوب من renet-proxy. استخدام `docker compose` مباشرة يتجاوز كل هذا وسيتم رفضه أثناء التحقق.
>
> لا تستخدم أبداً `sudo docker` أيضاً، يعيد `sudo` تعيين متغيرات البيئة بما في ذلك `DOCKER_HOST`، مما يؤدي إلى إنشاء الحاويات على Docker daemon الخاص بالنظام بدلاً من daemon المعزول للمستودع. تعمل دوال Rediaccfile بالفعل بصلاحيات كافية.

انظر [الخدمات](/ar/docs/services) للحصول على تفاصيل كاملة حول ملفات Rediaccfile وتخطيطات الخدمات المتعددة وترتيب التنفيذ.

## الخطوة 5: تهيئة شبكة الخدمات

يشغّل Rediacc Docker daemon معزولاً لكل مستودع. تستخدم الخدمات `network_mode: host` وتربط بعناوين loopback فريدة بحيث يمكنها استخدام المنافذ القياسية دون تعارضات بين المستودعات.

### تكييف docker-compose.yml

**قبل (التقليدي):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**بعد (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

التغييرات الرئيسية:

1. **إزالة تعيينات `ports:`** - يستخدم `renet compose` شبكة المضيف ويزيل تعيينات المنافذ تلقائياً
2. **إزالة `network_mode: host`** - يضيف `renet compose` هذا تلقائياً
3. **سياسات إعادة التشغيل آمنة للإبقاء عليها** - يقوم renet بإزالتها تلقائياً لتوافق CRIU، ويُعيد روتر watchdog الحاويات المتوقفة تلقائياً
4. **استخدم أسماء الخدمات للاتصالات بين الخدمات** (مثل `postgres` و`redis`) - يحقن renet كل اسم خدمة كاسم مضيف قابل للحل. لا تضمّن عناوين IP الخام في سلاسل الاتصال المخزنة في قواعد البيانات أو ملفات الإعداد؛ استخدم اسم الخدمة بدلاً منه للحفاظ على عزل النسخ (fork isolation)
5. **الربط تلقائي** - يعيد النواة كتابة `bind()` إلى عنوان loopback الصحيح. يمكن للخدمات استخدام `0.0.0.0` أو `localhost`

متغيرات `{SERVICE}_IP` لا تزال متاحة إذا احتجتها، لكن الربط الصريح لم يعد مطلوباً، إذ يُعالَج تلقائياً. قاعدة التسمية: أحرف كبيرة، استبدال الشرطات بشرطات سفلية، وإضافة لاحقة `_IP`. على سبيل المثال، `listmonk-app` يصبح `LISTMONK_APP_IP`.

انظر [شبكة الخدمات](/ar/docs/services#service-networking-rediaccjson) للتفاصيل حول تعيين عناوين IP و`.rediacc.json`.

## الخطوة 6: بدء الخدمات

قم بتحميل المستودع (إذا لم يكن محمّلاً بالفعل) وابدأ جميع الخدمات:

```bash
rdc repo up --name my-project -m server-1
```

سيقوم هذا بما يلي:
1. تحميل المستودع المشفر
2. بدء Docker daemon المعزول
3. إنشاء `.rediacc.json` تلقائياً مع تعيينات عناوين IP للخدمات
4. تشغيل `up()` من جميع ملفات Rediaccfile

تحقق من أن الحاويات تعمل:

```bash
rdc machine containers server-1
```

## الخطوة 7: تفعيل البدء التلقائي (اختياري)

بشكل افتراضي، يجب تحميل المستودعات وبدء تشغيلها يدوياً بعد إعادة تشغيل الخادم. فعّل البدء التلقائي حتى تبدأ خدماتك تلقائياً:

```bash
rdc repo autostart enable --name my-project -m server-1
```

سيُطلب منك إدخال عبارة مرور المستودع.

> **ملاحظة أمنية:** يخزّن البدء التلقائي ملف مفتاح LUKS على الخادم. أي شخص لديه صلاحيات root يمكنه تحميل المستودع بدون عبارة المرور. انظر [البدء التلقائي](/ar/docs/services#autostart-on-boot) للتفاصيل.

## سيناريوهات الترحيل الشائعة

### WordPress / PHP مع قاعدة بيانات

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # ملفات WordPress (UID 33 عند التشغيل)
├── database/data/          # بيانات MariaDB (UID 999 عند التشغيل)
└── wp-content/uploads/     # ملفات المستخدمين المرفوعة
```

1. ارفع ملفات مشروعك
2. ابدأ الخدمات أولاً (`rdc repo up`) حتى تنشئ الحاويات أدلة بياناتها
3. شغّل إصلاح الملكية، يتم استثناء أدلة بيانات MariaDB والتطبيق تلقائياً

### Node.js / Python مع Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # الكود المصدري للتطبيق
├── node_modules/           # التبعيات
└── redis-data/             # بيانات Redis المستمرة (UID 999 عند التشغيل)
```

1. ارفع مشروعك (فكّر في استثناء `node_modules` وسحبها في `up()`)
2. شغّل إصلاح الملكية بعد بدء الحاويات

### مشروع Docker مخصص

لأي مشروع يحتوي على خدمات Docker:

1. ارفع ملفات المشروع
2. كيّف `docker-compose.yml` (انظر الخطوة 5)
3. أنشئ `Rediaccfile` بدوال دورة الحياة
4. شغّل إصلاح الملكية
5. ابدأ الخدمات

## استكشاف الأخطاء وإصلاحها

### رفض الإذن بعد الرفع

لا تزال الملفات تحمل معرّف المستخدم المحلي الخاص بك. شغّل أمر الملكية:

```bash
rdc repo ownership --name my-project -m server-1
```

### الحاوية لا تبدأ

تحقق من أن الخدمات قيد التشغيل وراجع سجلاتها:

```bash
# تحقق من عناوين IP المعيّنة
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# تحقق من سجلات الحاوية
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### تعارض المنافذ بين المستودعات

يحصل كل مستودع على عناوين loopback فريدة، ويعيد النواة تلقائياً كتابة استدعاءات `bind()` إلى عنوان IP الصحيح. يجب ألا تحدث تعارضات في المنافذ بين المستودعات. إذا رأيت سلوكاً غير متوقع، تحقق من أن الخدمات تُبدأ عبر `renet compose` (وليس `docker compose`). للاتصال **بخدمات أخرى**، استخدم اسم الخدمة (مثل `postgres`) بدلاً من عناوين IP الخام؛ تُحلّ أسماء الخدمات بشكل صحيح في كل نسخة (fork).

### إصلاح الملكية يعطّل الحاويات

إذا شغّلت `rdc repo ownership` وتوقفت حاوية عن العمل، فقد تم تغيير ملكية ملفات بيانات الحاوية. أوقف الحاوية واحذف دليل بياناتها وأعد تشغيلها، ستعيد الحاوية إنشاءه:

```bash
rdc repo down --name my-project -m server-1
# احذف دليل بيانات الحاوية (مثل database/data)
rdc repo up --name my-project -m server-1
```
