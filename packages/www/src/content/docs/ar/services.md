---
title: الخدمات
description: >-
  نشر وإدارة الخدمات المحتوية باستخدام ملفات Rediaccfile وشبكات الخدمات والتشغيل
  التلقائي.
category: Guides
order: 5
language: ar
sourceHash: "181ba0512ff98f9c"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# الخدمات

إذا لم تكن متاكدا من الاداة المناسبة، راجع [rdc vs renet](/ar/docs/rdc-vs-renet).

تغطي هذه الصفحة كيفية نشر وإدارة الخدمات المحتوية: ملفات Rediaccfile، وشبكات الخدمات، والتشغيل/الإيقاف، والعمليات المجمّعة، والتشغيل التلقائي.

## ملف Rediaccfile

**Rediaccfile** هو سكريبت Bash يحدد كيفية تشغيل خدماتك وإيقافها. يجب أن يُسمّى `Rediaccfile` أو `rediaccfile` (غير حساس لحالة الأحرف) ويُوضع داخل نظام ملفات المستودع المحمّل.

يتم اكتشاف ملفات Rediaccfile في موقعين:
1. **جذر** مسار تحميل المستودع
2. **المجلدات الفرعية من المستوى الأول** لمسار التحميل (غير تكراري)

يتم تخطي المجلدات المخفية (الأسماء التي تبدأ بـ `.`).

### دوال دورة الحياة

يحتوي Rediaccfile على ما يصل إلى دالتين:

| الدالة | وقت التشغيل | الغرض | سلوك الخطأ |
|--------|------------|-------|------------|
| `up()` | عند التشغيل | تشغيل الخدمات (مثل `renet compose -- up -d`) | فشل الجذر **حرج** (يوقف كل شيء). فشل المجلدات الفرعية **غير حرج** (يُسجّل ويستمر) |
| `down()` | عند الإيقاف | إيقاف الخدمات (مثل `renet compose -- down`) | **أفضل جهد** -- يتم تسجيل الأخطاء لكن يتم تنفيذ جميع ملفات Rediaccfile دائماً |

كلتا الدالتين اختيارية. إذا لم تُعرّف دالة في Rediaccfile، يتم تخطيها بصمت.

### ترتيب التنفيذ

- **التشغيل (`up`):** Rediaccfile الجذر أولاً، ثم المجلدات الفرعية بـ**ترتيب أبجدي** (A إلى Z).
- **الإيقاف (`down`):** المجلدات الفرعية بـ**ترتيب أبجدي عكسي** (Z إلى A)، ثم الجذر أخيراً.

### متغيرات البيئة

عند تنفيذ دالة Rediaccfile، تكون متغيرات البيئة التالية متاحة:

| المتغير | الوصف | مثال |
|---------|-------|------|
| `REDIACC_WORKING_DIR` | مسار تحميل المستودع | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | معرّف المستودع GUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | معرّف الشبكة (عدد صحيح) | `2816` |
| `DOCKER_HOST` | مقبس Docker لعملية Docker المعزولة لهذا المستودع | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | عنوان IP الحلقي لكل خدمة مُعرّفة في `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

يتم إنشاء متغيرات `{SERVICE}_IP` تلقائياً من `.rediacc.json`. تقوم قاعدة التسمية بتحويل اسم الخدمة إلى أحرف كبيرة مع استبدال الشرطات بشرطات سفلية، ثم إضافة `_IP`. على سبيل المثال، `listmonk-app` تصبح `LISTMONK_APP_IP`.

> **تحذير: لا تستخدم `sudo docker` في ملفات Rediaccfile.** يعيد أمر `sudo` تعيين متغيرات البيئة، مما يعني فقدان `DOCKER_HOST` واستهداف أوامر Docker لعملية النظام بدلاً من العملية المعزولة للمستودع. هذا يكسر عزل الحاويات وقد يسبب تعارضات في المنافذ. سيمنع Rediacc التنفيذ إذا اكتشف `sudo docker` بدون `-E`.
>
> استخدم `renet compose` في ملفات Rediaccfile -- فهو يتعامل تلقائياً مع `DOCKER_HOST`، ويحقن تسميات الشبكة لاكتشاف المسارات، ويهيئ شبكات الخدمات. راجع [الشبكات](/ar/docs/networking) لتفاصيل حول كيفية كشف الخدمات عبر الوكيل العكسي. إذا استدعيت Docker مباشرة، استخدم `docker` بدون `sudo` -- دوال Rediaccfile تعمل بالفعل بصلاحيات كافية. إذا كان يجب عليك استخدام sudo، استخدم `sudo -E docker` للحفاظ على متغيرات البيئة.

### مثال

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **هام:** استخدم دائماً `renet compose --` بدلاً من `docker compose`. يفرض غلاف `renet compose` شبكة المضيف، وتخصيص عناوين IP، وتسميات اكتشاف الخدمات المطلوبة من renet-proxy. تُضاف قدرات CRIU checkpoint/restore للحاويات التي تحمل تسمية `rediacc.checkpoint=true`. يتم رفض الاستخدام المباشر لـ `docker compose` بواسطة التحقق من صحة Rediaccfile. راجع [الشبكات](/ar/docs/networking) للتفاصيل.

### تخطيط متعدد الخدمات

للمشاريع التي تحتوي على مجموعات خدمات مستقلة متعددة، استخدم المجلدات الفرعية:

```
/mnt/rediacc/mounts/my-app/
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

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**مثال** لمعرّف الشبكة `2816` (`0x0B00`)، العنوان الأساسي `127.0.11.0`:

| الخدمة | الفتحة | عنوان IP |
|--------|--------|----------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

يدعم كل مستودع ما يصل إلى **61 خدمة** (الفتحات من 0 إلى 60).

### استخدام عناوين IP للخدمات في Docker Compose

بما أن كل مستودع يشغّل عملية Docker معزولة، يقوم `renet compose` تلقائياً بتهيئة `network_mode: host` لجميع الخدمات. يعيد النواة تلقائياً توجيه استدعاءات `bind()` إلى عنوان IP الحلقي المخصص للخدمة، لذا يمكن للخدمات الارتباط بـ `0.0.0.0` أو `localhost` دون تعارض. للاتصال **بالخدمات الأخرى**، استخدم **اسم الخدمة** -- يحقن renet كل اسم خدمة كاسم مضيف يُحلَّل دائماً إلى عنوان IP الصحيح، حتى في الفروع:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # لا حاجة لـ listen_addresses صريح -- تعيد النواة توجيه bind إلى عنوان IP الحلقي الصحيح

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # استخدام اسم الخدمة
      LISTEN_ADDR: 0.0.0.0:8080                                      # تعيد النواة توجيهه إلى IP الخدمة
```

> **أسماء الخدمات للاتصالات:** استخدم **اسم الخدمة** (مثل `postgres`، `redis`) للاتصال بالخدمات الأخرى -- يقوم renet تلقائياً بتعيين كل اسم خدمة إلى عنوان IP الحلقي الخاص به عبر `/etc/hosts`. تضمين `${POSTGRES_IP}` في سلاسل الاتصال المخزنة في قواعد البيانات أو ملفات الإعداد سيُثبّت عنوان IP الخام، مما يكسر عزل الفروع وهو **خطأ تحقق**. متغيرات `${SERVICE_IP}` لا تزال متاحة للاستخدام الصريح، لكن الارتباط يتم تلقائياً بواسطة النواة.

> **ملاحظة:** لا تضف `network_mode: host` يدوياً, يقوم `renet compose` بحقنه تلقائياً. سياسات إعادة التشغيل (مثل `restart: always`) آمنة للاستخدام, يزيلها renet تلقائياً لتوافق CRIU ويتولى watchdog استعادة الحاويات.

### استعادة الحاويات وسياسة إعادة التشغيل

يختلف renet وDocker عن قصد في كيفية التعامل مع إعادة تشغيل الحاويات. فهم هذا التقسيم مهم عند تشخيص سبب عودة حاوية إلى العمل أو عدمها.

**ترجمة سياسة إعادة التشغيل.** عند كتابة `restart: always` (أو `unless-stopped`، أو `on-failure`) في ملف compose، يقوم renet **بحذفها** عند تجميع نشر compose الفعلي ويستبدلها بـ `restart: no`. يتم حفظ القيمة الأصلية في `.rediacc.json` الخاص بالمستودع تحت `services.<name>.restart_policy`. هذا يمنع إعادة التشغيل التلقائية على مستوى Docker daemon من التدخل في عملية CRIU checkpoint/restore (فإعادة تشغيل يقودها daemon ستستأنف من حالة قديمة ما قبل نقطة التفتيش).

**تطبيق الـ watchdog.** يعمل watchdog الموجّه دورياً على كل جهاز. في كل دورة:

1. يقرأ `.rediacc.json` لكل مستودع ويجد الخدمات التي تحتوي على `restart_policy` قابلة للاسترداد.
2. يسرد جميع الحاويات لـ daemon ذلك المستودع، ويحدد الموقوفة منها، ويعيد تشغيلها وفق السياسة المحفوظة. فترة سماح مدتها 30 ثانية تمنع التعارض مع مشغّل نفّذ `docker stop` للتو.
3. تعالج نفس الحلقة أيضاً `/var/run/rediacc/cold-backup-<guid>.running.json` (انظر [دلالات النسخ الاحتياطية الباردة](backup-restore.md#cold-backup-semantics)). تُعاد تشغيل الحاويات المدرجة بغض النظر عن السياسة المحفوظة، لأن الـ sidecar يعني "أوقف renet هذه الحاويات عن قصد وعليه إعادة تشغيلها للمشغّل."

**لماذا قد تبدو `on-failure` معطوبة.** سياسة Docker `on-failure` تُعيد التشغيل فقط عند خروج الحاوية بكود غير صفري. الإيقاف الطبيعي (الخروج 0) من `docker stop` أو إيقاف daemon ليس "فشلاً" ولا يُشغّل إعادة تشغيل، لا بالمنطق الأصلي لـ Docker ولا بمسار السياسة المحفوظة لـ watchdog. sidecar النسخ الاحتياطية الباردة هو شبكة الأمان: أي حاوية أوقفناها عن قصد تُعاد تشغيلها بغض النظر عن سياستها.

**كيفية تفسير حالة وقت التشغيل:**

- `docker inspect <container>` ← `RestartPolicy.Name`: ستكون دائماً `no` للحاويات المُدارة بـ renet. لا تعتمد على هذا للسياسة الدلالية.
- `.rediacc.json` في جذر تحميل المستودع ← `services.<name>.restart_policy`: النية الحقيقية.
- `docker ps --format '{{.Status}}'`: حالة وقت التشغيل.

**كيفية إصلاح الانحراف.** إذا كانت السياسة المحفوظة في `.rediacc.json` للحاوية غير صحيحة (مثلاً لأنك عدّلت compose لكن لم تُعد إنشاء الحاوية)، أعد تشغيل `rdc repo up --name <repo> -m <machine>`. ستُعاد إنشاء الحاوية مع تسجيل السياسة المحدّثة.

> **تجريبي:** وصل استرداد sidecar النسخ الاحتياطية الباردة وعلامة `--sync-certs` في `rdc machine query` في renet 0.9+. الإصدارات الأقدم تعتمد كلياً على `restart_policy` المحفوظة لاسترداد watchdog، مما قد يترك حاويات `on-failure` عالقة بعد نسخة احتياطية باردة.

> **شبكات Docker bridge معطّلة لعمليات daemon الخاصة بكل مستودع.** يتم تكوين كل daemon خاص بمستودع (`FlavorRediacc`) بالقيم `"bridge": "none"` و `"iptables": false`. سيظل أمر `docker run <image>` البسيط داخل شل المستودع يبدأ التشغيل، لكن الحاوية ستحصل فقط على واجهة loopback وبدون DNS أو اتصال خارجي. هذا بالتصميم، لأن عزل الـ loopback بين المستودعات تفرضه خطاطيف cgroup الخاصة بـ eBPF، وهي خطاطيف تتجاوزها الحاويات التي تعمل عبر bridge. يجب أن تستخدم خدمات الإنتاج `renet compose` (الذي يحقن شبكة المضيف تلقائياً)؛ وللتصحيح العابر، مرّر `--network host` بشكل صريح: `docker run --rm --network host -it ubuntu bash`.
>
> عمليات Hub daemon الخاصة بكل مستخدم (`FlavorHub`، المستخدمة في بيئات التطوير) هي الاستثناء: فهي تضبط `bridge="docker0"` و`iptables=true` و`live-restore=true` لكي تحصل الحاويات التي يشغّلها المستخدم على شبكة bridge عادية واتصال خارجي.

> **ملاحظة:** مستودعات fork تحصل على مسارات تلقائية مسطحة تحت نطاق فرعي الأصل: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. يتم تخطي النطاقات المخصصة لمستودعات fork.

## تشغيل الخدمات

قم بتحميل المستودع وتشغيل جميع الخدمات:

```bash
rdc repo up --name my-app -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--skip-router-restart` | تخطي إعادة تشغيل خادم المسارات بعد العملية |

تسلسل التنفيذ هو:
1. تحميل المستودع المشفر بـ LUKS (تحميل تلقائي إذا لم يكن محمّلاً)
2. تشغيل عملية Docker المعزولة
3. إنشاء `.rediacc.json` تلقائياً من ملفات compose
4. تشغيل `up()` في جميع ملفات Rediaccfile (بترتيب A-Z)

بعد النشر، يُظهر الإخراج قسم **PROXY ROUTES** مع عناوين URL الفعلية لكل خدمة. الخدمات ذات تسميات Traefik المخصصة تُظهر نطاقاتها المخصصة كعناوين URL رئيسية:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

## إيقاف الخدمات

```bash
rdc repo down --name my-app -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--unmount` | إلغاء تحميل المستودع المشفر بعد إيقاف الخدمات. إذا لم يسرِ مفعوله، استخدم `rdc repo unmount` بشكل منفصل. |
| `--skip-router-restart` | تخطي إعادة تشغيل خادم المسارات بعد العملية |

تسلسل التنفيذ هو:
1. تشغيل `down()` في جميع ملفات Rediaccfile (بترتيب Z-A عكسي، أفضل جهد)
2. إيقاف عملية Docker المعزولة (إذا تم تحديد `--unmount`)
3. إلغاء تحميل وإغلاق وحدة LUKS المشفرة (إذا تم تحديد `--unmount`)

## العمليات المجمّعة

شغّل أو أوقف جميع المستودعات على جهاز دفعة واحدة:

```bash
rdc repo up -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--include-forks` | تضمين المستودعات المنسوخة |
| `--mount-only` | التحميل فقط، بدون تشغيل الحاويات |
| `--dry-run` | عرض ما سيتم تنفيذه |
| `--parallel` | تشغيل العمليات بالتوازي |
| `--concurrency <n>` | الحد الأقصى للعمليات المتزامنة (الافتراضي: 3) |
| `--skip-router-restart` | تخطي إعادة تشغيل خادم المسارات بعد العملية |

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
rdc repo autostart enable --name my-app -m server-1
```

سيُطلب منك إدخال عبارة مرور المستودع.

### تفعيل الكل

```bash
rdc repo autostart enable -m server-1
```

### تعطيل

```bash
rdc repo autostart disable --name my-app -m server-1
```

يزيل هذا ملف المفتاح ويحذف فتحة LUKS رقم 1.

### تحديث ملف المفتاح عند النشر

عند تفعيل التشغيل التلقائي، يتحقق `rdc repo up` من ملف مفتاح LUKS في الفتحة رقم 1.
إذا كان ملف المفتاح على القرص لا يزال مطابقاً لفتحة LUKS، لا يتم إجراء أي تغييرات.

بعد نقل مستودع بين الأجهزة عبر `repo push` / `repo pull`،
ملف المفتاح على الجهاز الجديد لن يتطابق. في هذه الحالة، يُعيد `repo up` تلقائياً
إنشاء ملف المفتاح وتحديث فتحة LUKS رقم 1. ستظهر رسائل السجل:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

هذا آمن، الفتحة 0 (عبارة مرورك) لا تُعدَّل أبداً. إذا لم يكن التشغيل التلقائي
مفعّلاً، يتم تخطي الفحص بصمت. الأخطاء غير حرجة ولا تعيق النشر.

### عرض الحالة

```bash
rdc repo autostart list -m server-1
```

لتفاصيل حول كيفية استرداد المُوفِّق الدوري للمستودعات التي تتوقف بعد الإقلاع، راجع [التشغيل التلقائي والاسترداد](/ar/docs/autostart-recovery).

## مثال كامل

ينشر هذا تطبيق ويب مع PostgreSQL و Redis وخادم API.

### 1. الإعداد

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. التحميل والتحضير

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. إنشاء ملفات التطبيق

داخل المستودع، أنشئ الملفات التالية:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up --name webapp -m prod-1
```

### 5. تفعيل التشغيل التلقائي

```bash
rdc repo autostart enable --name webapp -m prod-1
```
