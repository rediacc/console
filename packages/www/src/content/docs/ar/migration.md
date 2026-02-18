---
title: "دليل الترحيل"
description: "ترحيل المشاريع الحالية إلى مستودعات Rediacc المشفرة."
category: "Guides"
order: 11
language: ar
---

# دليل الترحيل

قم بترحيل مشروع حالي — الملفات وخدمات Docker وقواعد البيانات — من خادم تقليدي أو بيئة تطوير محلية إلى مستودع Rediacc مشفر.

## المتطلبات الأساسية

- تثبيت واجهة سطر الأوامر `rdc` ([التثبيت](/ar/docs/installation))
- إضافة جهاز وتجهيزه ([الإعداد](/ar/docs/setup))
- مساحة قرص كافية على الخادم لمشروعك (تحقق باستخدام `rdc machine status`)

## الخطوة 1: إنشاء مستودع

أنشئ مستودعاً مشفراً بحجم يناسب مشروعك. خصص مساحة إضافية لصور Docker وبيانات الحاويات.

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **نصيحة:** يمكنك تغيير الحجم لاحقاً باستخدام `rdc repo resize` إذا لزم الأمر، لكن يجب إلغاء تحميل المستودع أولاً. من الأسهل البدء بمساحة كافية.

## الخطوة 2: رفع الملفات

استخدم `rdc sync upload` لنقل ملفات مشروعك إلى المستودع.

```bash
# معاينة ما سيتم نقله (بدون إجراء تغييرات)
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# رفع الملفات
rdc sync upload -m server-1 -r my-project --local ./my-project
```

يجب أن يكون المستودع محمّلاً قبل الرفع. إذا لم يكن محمّلاً بالفعل:

```bash
rdc repo mount my-project -m server-1
```

لعمليات المزامنة اللاحقة حيث تريد أن يطابق المحتوى البعيد دليلك المحلي تماماً:

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> يحذف خيار `--mirror` الملفات على الخادم البعيد التي لا توجد محلياً. استخدم `--dry-run` أولاً للتحقق.

## الخطوة 3: إصلاح ملكية الملفات

تصل الملفات المرفوعة بمعرّف المستخدم المحلي الخاص بك (مثل 1000). يستخدم Rediacc مستخدماً موحداً (UID 7111) بحيث يتمتع VS Code وجلسات الطرفية والأدوات جميعها بوصول متسق. شغّل أمر الملكية للتحويل:

```bash
rdc repo ownership my-project -m server-1
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

- **بعد رفع الملفات** — لتحويل معرّف المستخدم المحلي إلى 7111
- **بعد بدء الحاويات** — إذا كنت تريد استثناء أدلة أحجام Docker تلقائياً. إذا لم تكن الحاويات قد بدأت بعد، فلا توجد أحجام للاستثناء وسيتم تغيير ملكية جميع الأدلة (وهذا مقبول — ستعيد الحاويات إنشاء بياناتها عند أول تشغيل)

### وضع الإجبار

لتخطي اكتشاف أحجام Docker وتغيير ملكية كل شيء، بما في ذلك أدلة بيانات الحاويات:

```bash
rdc repo ownership my-project -m server-1 --force
```

> **تحذير:** قد يؤدي هذا إلى تعطيل الحاويات قيد التشغيل. أوقفها أولاً باستخدام `rdc repo down` إذا لزم الأمر.

### معرّف مستخدم مخصص

لتعيين معرّف مستخدم غير القيمة الافتراضية 7111:

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## الخطوة 4: إعداد Rediaccfile

أنشئ ملف `Rediaccfile` في جذر مشروعك. هذا السكربت بلغة Bash يحدد كيفية تحضير خدماتك وبدئها وإيقافها.

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

الدوال الثلاث لدورة الحياة:

| الدالة | الغرض | سلوك الخطأ |
|--------|-------|------------|
| `prep()` | سحب الصور، تشغيل عمليات الترحيل، تثبيت التبعيات | إيقاف فوري: أي فشل يوقف كل شيء |
| `up()` | بدء الخدمات | فشل الجذر حرج؛ فشل الأدلة الفرعية يُسجّل ويستمر |
| `down()` | إيقاف الخدمات | بأفضل جهد: يحاول دائماً تنفيذ الكل |

> **مهم:** استخدم `docker` مباشرة في Rediaccfile — لا تستخدم أبداً `sudo docker`. يعيد أمر `sudo` تعيين متغيرات البيئة، مما يؤدي إلى فقدان `DOCKER_HOST` وإنشاء الحاويات على Docker daemon الخاص بالنظام بدلاً من daemon المعزول للمستودع. تعمل دوال Rediaccfile بالفعل بصلاحيات كافية. انظر [الخدمات](/ar/docs/services#environment-variables) للتفاصيل.

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
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

التغييرات الرئيسية:

1. **إضافة `network_mode: host`** لكل خدمة
2. **إزالة تعيينات `ports:`** (غير مطلوبة مع شبكة المضيف)
3. **ربط الخدمات بمتغيرات البيئة `${SERVICE_IP}`** (يتم حقنها تلقائياً بواسطة Rediacc)
4. **الإشارة إلى الخدمات الأخرى بعنوان IP الخاص بها** بدلاً من أسماء Docker DNS (مثل `${POSTGRES_IP}` بدلاً من `postgres`)

يتم إنشاء متغيرات `{SERVICE}_IP` تلقائياً من أسماء الخدمات في ملف compose الخاص بك. قاعدة التسمية: أحرف كبيرة، استبدال الشرطات بشرطات سفلية، وإضافة لاحقة `_IP`. على سبيل المثال، `listmonk-app` يصبح `LISTMONK_APP_IP`.

انظر [شبكة الخدمات](/ar/docs/services#service-networking-rediaccjson) للتفاصيل حول تعيين عناوين IP و`.rediacc.json`.

## الخطوة 6: بدء الخدمات

قم بتحميل المستودع (إذا لم يكن محمّلاً بالفعل) وابدأ جميع الخدمات:

```bash
rdc repo up my-project -m server-1 --mount
```

سيقوم هذا بما يلي:
1. تحميل المستودع المشفر
2. بدء Docker daemon المعزول
3. إنشاء `.rediacc.json` تلقائياً مع تعيينات عناوين IP للخدمات
4. تشغيل `prep()` من جميع ملفات Rediaccfile
5. تشغيل `up()` من جميع ملفات Rediaccfile

تحقق من أن الحاويات تعمل:

```bash
rdc machine containers server-1
```

## الخطوة 7: تفعيل البدء التلقائي (اختياري)

بشكل افتراضي، يجب تحميل المستودعات وبدء تشغيلها يدوياً بعد إعادة تشغيل الخادم. فعّل البدء التلقائي حتى تبدأ خدماتك تلقائياً:

```bash
rdc repo autostart enable my-project -m server-1
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
3. شغّل إصلاح الملكية — يتم استثناء أدلة بيانات MariaDB والتطبيق تلقائياً

### Node.js / Python مع Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # الكود المصدري للتطبيق
├── node_modules/           # التبعيات
└── redis-data/             # بيانات Redis المستمرة (UID 999 عند التشغيل)
```

1. ارفع مشروعك (فكّر في استثناء `node_modules` وسحبها في `prep()`)
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
rdc repo ownership my-project -m server-1
```

### الحاوية لا تبدأ

تحقق من أن الخدمات تربط بعنوان IP المعيّن لها، وليس `0.0.0.0` أو `localhost`:

```bash
# تحقق من عناوين IP المعيّنة
rdc term server-1 my-project -c "cat .rediacc.json"

# تحقق من سجلات الحاوية
rdc term server-1 my-project -c "docker logs <container-name>"
```

### تعارض المنافذ بين المستودعات

يحصل كل مستودع على عناوين loopback فريدة. إذا رأيت تعارضات في المنافذ، تحقق من أن `docker-compose.yml` يستخدم `${SERVICE_IP}` للربط بدلاً من `0.0.0.0`. الخدمات المربوطة بـ `0.0.0.0` تستمع على جميع الواجهات وستتعارض مع المستودعات الأخرى.

### إصلاح الملكية يعطّل الحاويات

إذا شغّلت `rdc repo ownership --force` وتوقفت حاوية عن العمل، فقد تم تغيير ملكية ملفات بيانات الحاوية. أوقف الحاوية واحذف دليل بياناتها وأعد تشغيلها — ستعيد الحاوية إنشاءه:

```bash
rdc repo down my-project -m server-1
# احذف دليل بيانات الحاوية (مثل database/data)
rdc repo up my-project -m server-1
```
