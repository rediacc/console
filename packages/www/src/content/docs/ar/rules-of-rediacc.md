---
title: "قواعد Rediacc"
description: "القواعد والاصطلاحات الأساسية لبناء التطبيقات على منصة Rediacc. يغطي Rediaccfile و compose والشبكات والتخزين و CRIU والنشر."
category: "Guides"
order: 5
language: ar
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
---

# قواعد Rediacc

يعمل كل مستودع Rediacc داخل بيئة معزولة تحتوي على Docker daemon خاص به، ووحدة تخزين LUKS مشفرة، ونطاق IP مخصص. تضمن هذه القواعد أن تطبيقك يعمل بشكل صحيح ضمن هذه البنية.

## Rediaccfile

- **كل مستودع يحتاج إلى Rediaccfile** — سكريبت bash يحتوي على دوال دورة الحياة.
- **دوال دورة الحياة**: `up()`، `down()`. اختياري: `info()`.
- `up()` يبدأ خدماتك. `down()` يوقفها.
- `info()` يوفر معلومات الحالة (حالة الحاويات، السجلات الأخيرة، الصحة).
- يتم تحميل Rediaccfile بواسطة renet — لديه وصول إلى متغيرات الشل، وليس فقط متغيرات البيئة.

### متغيرات البيئة المتاحة في Rediaccfile

| المتغير | مثال | الوصف |
|---------|------|-------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | المسار الجذري للمستودع المُركّب |
| `REPOSITORY_NETWORK_ID` | `6336` | معرّف عزل الشبكة |
| `REPOSITORY_NAME` | `abc123-...` | GUID المستودع |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | عنوان IP loopback لكل خدمة (اسم الخدمة بأحرف كبيرة) |

### Rediaccfile الأدنى

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **استخدم `renet compose`، ولا تستخدم `docker compose` أبداً** — يقوم renet بحقن عزل الشبكة، وشبكة المضيف، وعناوين IP loopback، وتسميات الخدمة.
- **لا تقم بتعيين `network_mode`** في ملف compose — يفرض renet `network_mode: host` على جميع الخدمات. أي قيمة تعيّنها سيتم الكتابة فوقها.
- **لا تقم بتعيين تسميات `rediacc.*`** — يقوم renet بالحقن التلقائي لـ `rediacc.network_id` و `rediacc.service_ip` و `rediacc.service_name`.
- **يتم تجاهل تعيينات `ports:`** في وضع شبكة المضيف. استخدم تسمية `rediacc.service_port` لتوجيه الوكيل إلى المنافذ غير 80.
- **سياسات إعادة التشغيل (`restart: always`، `on-failure`، إلخ) آمنة للاستخدام** — يقوم renet بإزالتها تلقائياً لتوافق CRIU. يقوم watchdog الموجّه باستعادة الحاويات الموقوفة تلقائياً بناءً على السياسة الأصلية المحفوظة في `.rediacc.json`.
- **الإعدادات الخطرة محظورة بشكل افتراضي** — يتم رفض `privileged: true` و `pid: host` و `ipc: host` والـ bind mounts إلى مسارات النظام. استخدم `renet compose --unsafe` للتجاوز على مسؤوليتك الخاصة.

### متغيرات البيئة داخل الحاويات

يقوم Renet بحقن هذه تلقائياً في كل حاوية:

| المتغير | الوصف |
|---------|-------|
| `SERVICE_IP` | عنوان IP loopback المخصص لهذه الحاوية |
| `REPOSITORY_NETWORK_ID` | معرّف عزل الشبكة |

### تسمية الخدمات والتوجيه

- **اسم الخدمة** في compose يصبح بادئة URL للمسار التلقائي.
- مثال: الخدمة `myapp` مع networkId 6336 ونطاق أساسي `example.com` تصبح `https://myapp-6336.example.com`.
- للنطاقات المخصصة، استخدم تسميات Traefik (ملاحظة: النطاقات المخصصة غير متوافقة مع الفروع).
- تستخدم مستودعات fork مسارات تلقائية مسطحة تحت شهادة wildcard للجهاز. يتم تجاهل النطاقات المخصصة (`rediacc.domain`) في الفروع — النطاق ينتمي إلى المستودع grand.

## الشبكات

- **كل مستودع يحصل على Docker daemon خاص به** في `/var/run/rediacc/docker-<networkId>.sock`.
- **كل خدمة تحصل على عنوان IP loopback فريد** ضمن شبكة فرعية /26 (مثال: `127.0.24.192/26`).
- **اربط بـ `SERVICE_IP`** — تحصل كل خدمة على عنوان IP loopback فريد.
- **يجب أن تستخدم فحوصات الصحة `${SERVICE_IP}`**، وليس `localhost`. مثال: `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **الاتصال بين الخدمات**: استخدم عناوين IP loopback أو متغير البيئة `SERVICE_IP`. أسماء DNS الخاصة بـ Docker لا تعمل في وضع المضيف.
- **تعارض المنافذ مستحيل** بين المستودعات — كل منها لديه Docker daemon ونطاق IP خاص به.
- **إعادة توجيه منافذ TCP/UDP**: أضف تسميات لكشف المنافذ غير HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## التخزين

- **يتم تخزين جميع بيانات Docker داخل المستودع المشفر** — يقع `data-root` الخاص بـ Docker في `{mount}/.rediacc/docker/data` داخل وحدة تخزين LUKS. وحدات التخزين المسماة والصور وطبقات الحاويات جميعها مشفرة ومنسوخة احتياطياً ومُفرّعة تلقائياً.
- **يُوصى بالـ bind mounts إلى `${REPOSITORY_PATH}/...`** للوضوح، لكن وحدات التخزين المسماة تعمل أيضاً بأمان.
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data        # bind mount (موصى به)
    - pgdata:/var/lib/postgresql/data      # named volume (آمن أيضاً)
  ```
- يتم تركيب وحدة تخزين LUKS في `/mnt/rediacc/mounts/<guid>/`.
- تلتقط لقطات BTRFS ملف دعم LUKS بالكامل، بما في ذلك جميع البيانات المُركّبة بـ bind.
- مخزن البيانات هو ملف مجموعة BTRFS ذو حجم ثابت على قرص النظام. استخدم `rdc machine query <name> --system` لرؤية المساحة الحرة الفعلية. قم بالتوسعة مع `rdc datastore resize`.

## CRIU (الترحيل الحي)

- **`backup push --checkpoint`** يلتقط ذاكرة العمليات الجارية + حالة القرص.
- **`repo up --mount --checkpoint`** يستعيد الحاويات من نقطة التحقق (بدون بدء جديد).
- **تصبح اتصالات TCP قديمة بعد الاستعادة** — يجب على التطبيقات التعامل مع `ECONNRESET` وإعادة الاتصال.
- **وضع Docker التجريبي** يتم تفعيله تلقائياً على أدوات daemon لكل مستودع.
- **يتم تثبيت CRIU** أثناء `rdc config machine setup`.
- **`/etc/criu/runc.conf`** يتم تكوينه مع `tcp-established` للحفاظ على اتصالات TCP.
- **يتم حقن إعدادات أمان الحاويات تلقائياً بواسطة renet** — يضيف `renet compose` تلقائياً ما يلي إلى كل حاوية لتوافق CRIU:
  - `cap_add`: `CHECKPOINT_RESTORE`، `SYS_PTRACE`، `NET_ADMIN` (الحد الأدنى لـ CRIU على النواة 5.9+)
  - `security_opt`: `apparmor=unconfined` (دعم AppArmor في CRIU ليس مستقراً بعد في المنبع)
  - `userns_mode: host` (يتطلب CRIU الوصول إلى مساحة اسم init لـ `/proc/pid/map_files`)
- يتم الحفاظ على ملف تعريف seccomp الافتراضي لـ Docker — يستخدم CRIU `PTRACE_O_SUSPEND_SECCOMP` (النواة 4.3+) لتعليق المرشحات مؤقتاً أثناء checkpoint/restore.
- **لا تقم بتعيين هذه يدوياً** في ملف compose — يتولى renet ذلك. تعيينها بنفسك يخاطر بالتكرار أو التعارض.
- راجع [قالب heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) للحصول على تطبيق مرجعي متوافق مع CRIU.

### أنماط التطبيقات المتوافقة مع CRIU

- تعامل مع `ECONNRESET` على جميع الاتصالات المستمرة (مجمّعات قواعد البيانات، websockets، طوابير الرسائل).
- استخدم مكتبات مجمّعات الاتصال التي تدعم إعادة الاتصال التلقائي.
- أضف `process.on("uncaughtException")` كشبكة أمان لأخطاء المقابس القديمة من كائنات المكتبات الداخلية.
- يتم إدارة سياسات إعادة التشغيل تلقائياً بواسطة renet (تُزال لـ CRIU، watchdog يتولى الاستعادة).
- تجنب الاعتماد على DNS الخاص بـ Docker — استخدم عناوين IP loopback للاتصال بين الخدمات.

## الأمان

- **تشفير LUKS** إلزامي للمستودعات القياسية. كل مستودع لديه مفتاح تشفير خاص به.
- **يتم تخزين بيانات الاعتماد في تكوين CLI** (`~/.config/rediacc/rediacc.json`). فقدان التكوين يعني فقدان الوصول إلى وحدات التخزين المشفرة.
- **لا تقم أبداً بإرسال بيانات الاعتماد** إلى نظام التحكم بالإصدارات. استخدم `env_file` وقم بتوليد الأسرار في `up()`.
- **عزل المستودع**: Docker daemon والشبكة والتخزين لكل مستودع معزولة تماماً عن المستودعات الأخرى على نفس الجهاز.
- **عزل الوكلاء**: تعمل وكلاء الذكاء الاصطناعي في وضع fork-only بشكل افتراضي. كل مستودع لديه مفتاح SSH خاص به مع تطبيق sandbox من جانب الخادم (ForceCommand `sandbox-gateway`). جميع الاتصالات محاطة بـ sandbox مع Landlock LSM، وOverlayFS home overlay، وTMPDIR لكل مستودع. يتم حظر الوصول إلى نظام الملفات بين المستودعات من قبل النواة.

## النشر

- **`rdc repo up`** ينفذ `up()` في جميع ملفات Rediaccfile.
- **`rdc repo up --mount`** يفتح وحدة تخزين LUKS أولاً، ثم ينفذ دورة الحياة. مطلوب بعد `backup push` إلى جهاز جديد.
- **`rdc repo down`** ينفذ `down()` ويوقف Docker daemon.
- **`rdc repo down --unmount`** يغلق أيضاً وحدة تخزين LUKS (يقفل التخزين المشفر).
- **الفروع** (`rdc repo fork`) تنشئ نسخة CoW (copy-on-write) بـ GUID و networkId جديدين. يشارك الفرع مفتاح تشفير الأصل.
- **التسلّم** (`rdc repo takeover <fork> -m <machine>`) يستبدل بيانات المستودع grand ببيانات فرع. يحتفظ grand بهويته (GUID، networkId، النطاقات، الإقلاع التلقائي، سلسلة النسخ الاحتياطية). يتم حفظ بيانات الإنتاج القديمة كفرع احتياطي. الاستخدام: اختبار الترقية على فرع، التحقق، ثم تسلّم الإنتاج. الرجوع بـ `rdc repo takeover <backup-fork> -m <machine>`.
- **مسارات الوكيل** تستغرق حوالي 3 ثوانٍ لتصبح نشطة بعد النشر. تحذير "Proxy is not running" أثناء `repo up` هو إعلامي في بيئات ops/dev.

## الأخطاء الشائعة

- استخدام `docker compose` بدلاً من `renet compose` — لن تحصل الحاويات على عزل الشبكة.
- سياسات إعادة التشغيل آمنة — يقوم renet بإزالتها تلقائياً ويتولى watchdog الاستعادة.
- استخدام `privileged: true` — غير ضروري، إذ يقوم renet بحقن صلاحيات CRIU المحددة عوضاً عن ذلك.
- عدم الربط بـ `SERVICE_IP` — يسبب تعارض المنافذ بين المستودعات.
- ترميز عناوين IP بشكل ثابت — استخدم متغير البيئة `SERVICE_IP`؛ يتم تخصيص عناوين IP ديناميكياً لكل networkId.
- نسيان `--mount` في أول نشر بعد `backup push` — تحتاج وحدة تخزين LUKS إلى فتح صريح.
- استخدام `rdc term -c` كحل بديل للأوامر الفاشلة — أبلغ عن الأخطاء بدلاً من ذلك.
- `repo delete` ينفذ تنظيفاً كاملاً يشمل عناوين IP loopback ووحدات systemd. شغّل `rdc machine prune <name>` لتنظيف بقايا عمليات الحذف القديمة.
