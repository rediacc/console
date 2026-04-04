---
title: البدء السريع
description: تشغيل خدمة حاويات على خادمك في دقائق.
category: Guides
order: -1
language: ar
sourceHash: "50b448b7b1e7b85b"
---

# البدء السريع

انشر بيئة حاويات مشفرة ومعزولة على خادمك الخاص. لا حاجة لحسابات سحابية أو اعتماد على خدمات SaaS. كل شيء يعمل على أجهزة تتحكم بها أنت.

---

## مقدمة

### المفاهيم الأساسية

المستودع هو ملف مشفر واحد على القرص. يمكنك نقله أو نسخه احتياطيًا أو استنساخه. إنه مجرد ملف. عند توصيله، يصبح مجلدًا يحتوي على Docker daemon مخصص وبيانات تطبيقك بداخله.

فكّر في المستودع كأنه محرك أقراص USB. إنه شيء في يدك، وعندما تقوم بتوصيله يصبح مرئيًا ومتاحًا للنظام. تطبيقاتك وبياناتك محمولة بالكامل. وصّل وشغّل على أي جهاز لدى أي مزود سحابي.

**أداتان، دوران:**

- **rdc** = سطر الأوامر على جهازك المحمول (TypeScript، يُثبَّت عالميًا)
- **renet** = المنسق على الخادم (ملف Go ثنائي، يدير العمليات/الشبكات/العزل)
- يقوم RDC بتجهيز renet تلقائيًا أثناء `config machine setup`. لا حاجة لإعداد يدوي على الخادم.

> صفحة [البنية التحتية](/en/docs/architecture) تشرح نموذج الأمان. صفحة [rdc vs renet](/en/docs/rdc-vs-renet) تشرح متى تستخدم كل أداة.

### 1. تثبيت سطر الأوامر

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # تحقق من: Node، مفتاح SSH، renet، Docker
```

> أنظمة Windows وAlpine وArch: انظر [التثبيت](/en/docs/installation). متطلبات النظام الكاملة: [المتطلبات](/en/docs/requirements).

### 2. إعداد مفتاح SSH

يتصل rdc عبر SSH. يجب أن يثق الخادم بمفتاحك العام قبل أن يتمكن rdc من الوصول إليه.

```bash
# أنشئ مفتاحًا (تخطَّ هذا إذا كان لديك مفتاح بالفعل)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# انسخ المفتاح العام إلى الخادم (سيطلب كلمة المرور)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# أخبر rdc بالمفتاح الذي يجب استخدامه
rdc config ssh set --key ~/.ssh/id_ed25519
```

كل أوامر rdc الآن تُصادق باستخدام هذا المفتاح. لا حاجة لكلمات مرور.

### 3. أضف خادمك

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # يجهّز renet + ينشئ مخزن البيانات
```

**ما يحدث:** يتم فحص مفتاح مضيف SSH، ورفع ملف renet الثنائي، وتهيئة مخزن البيانات المشفر على الخادم. جاهز للمستودعات.

> حجم مخزن البيانات، Ceph RBD، مزودو الخدمات السحابية: [إعداد الجهاز](/en/docs/setup). مشاكل SSH: [استكشاف الأخطاء وإصلاحها](/en/docs/troubleshooting).

### 4. ملف الإعدادات

```bash
rdc config show                            # ملخص سهل القراءة
cat ~/.config/rediacc/rediacc.json         # ملف JSON الخام: الأجهزة، المستودعات، التخزين، مفتاح SSH
```

**ملف واحد = بيئة واحدة.** انسخه إلى جهاز محمول آخر وستكون جاهزًا.

---

## العمل مع مستودع

### 1. إنشاء مستودع

```bash
rdc repo create --name my-app -m my-server --size 2G  # إنشاء مستودع مشفر بحجم 2 جيجابايت
```

ينشئ وحدة التخزين المشفرة، ويوصّلها، ويبدأ Docker daemon الخاص بها. يتم تسجيل المستودع في إعداداتك ويصبح جاهزًا للاستخدام.

> تغيير الحجم، الحذف، التحقق: [المستودعات](/en/docs/repositories).

### 2. تطبيق قالب

```bash
rdc repo template list                                        # عرض القوالب المضمنة
rdc repo template apply --name app-postgres -m my-server -r my-app  # نشر docker-compose.yml + Rediaccfile
```

توفر القوالب ملف `docker-compose.yml` وملف `Rediaccfile` وملفات مساعدة. بدون قالب (أو ملف compose خاص بك)، لا يوجد شيء لتشغيله.

### 3. تشغيل المستودع

```bash
rdc repo up --name my-app -m my-server  # تنفيذ Rediaccfile up()
rdc repo list -m my-server                           # عرض جميع المستودعات على الجهاز
rdc repo status --name my-app -m my-server  # حالة التوصيل، Docker، الحجم، التشفير
```

يقوم `repo up` بالتوصيل التلقائي عند الحاجة. لا حاجة لمعاملات إضافية.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # يفتح VS Code عبر SSH، داخل صندوق حماية المستودع
```

أنت تعدّل الملفات *داخل* وحدة التخزين المشفرة. `docker ps` يعرض فقط حاويات هذا المستودع. احفظ، نفّذ compose up، وكرّر العملية.

### 5. `rdc repo up` مقابل `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **أين تنفّذه** | جهازك المحمول (سطر الأوامر) | داخل صندوق حماية VS Code |
| **ما يفعله** | SSH ثم توصيل تلقائي ثم تنفيذ Rediaccfile `up()` | ينفّذ Rediaccfile `up()` مباشرة |
| **حالة الاستخدام** | CI/CD، الأتمتة، العمليات عن بُعد | حلقة التطوير الداخلية |
| **العزل** | ينسّق من الخارج | موجود بالفعل داخل صندوق الحماية |

**سير العمل التجريبي:** `rdc repo template apply` ثم `rdc vscode connect -m my-server -r my-app` ثم عدّل `docker-compose.yml` ثم `renet dev up` ثم شاهد التطبيق يعمل ثم كرّر.

> هيكل Rediaccfile: [الخدمات](/en/docs/services). متى تستخدم كل أداة: [rdc vs renet](/en/docs/rdc-vs-renet).

### 6. نموذج العزل

- **المستخدم الموحد** (`rediacc`): نفس UID على كل جهاز. انقل مستودعًا إلى خادم آخر وملكية الملفات تعمل مباشرة. لا مشاكل مع `chown`.
- **Docker daemon لكل مستودع**: كل مستودع يحصل على Docker daemon معزول خاص به. `docker ps` يعرض فقط حاويات هذا المستودع.
- **صندوق حماية Landlock + OverlayFS**: واجهة VS Code مقيدة على مستوى نظام الملفات. لا يمكنك قراءة المستودعات الأخرى. الكتابة إلى `$HOME` تتم عبر طبقات overlay لكل مستودع.

> كيف يعمل العزل: [البنية التحتية](/en/docs/architecture). دورة حياة Rediaccfile: [الخدمات](/en/docs/services).

### 7. الطرفية، المزامنة والأنفاق

**الطرفية:**
```bash
rdc term connect -m my-server -r my-app                            # SSH إلى صندوق حماية المستودع
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # تنفيذ أمر والخروج
rdc term connect -m my-server                                   # SSH إلى الجهاز (بدون صندوق حماية)
```

**مزامنة الملفات (rsync عبر SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src       # رفع الملفات المحلية إلى المستودع
rdc repo sync download -m my-server -r my-app --local ./backup  # سحب ملفات المستودع إلى المحلي
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run  # معاينة أولاً
```

**النفق (تحويل منفذ SSH إلى الحاوية):**
```bash
rdc repo tunnel -m my-server -r my-app  # كشف تلقائي للحاوية والمنفذ
rdc repo tunnel -m my-server -r my-app --port 5432  # نفق Postgres
rdc repo tunnel -m my-server -r my-app --port 5432 --local 15432  # منفذ محلي مخصص
```

شغّل النفق ثم افتح `localhost:3000` في المتصفح ثم شاهد التطبيق الحي من الخادم البعيد.

> تفاصيل المزامنة، الطرفية، VS Code: [الأدوات](/en/docs/tools).

---

## الاستنساخ والنسخ الاحتياطي

### 1. المستودعات الأصلية والمتفرعة

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # استنساخ فوري بتقنية CoW + تشغيل
rdc repo list -m my-server                                  # يعرض: my-app (أصلي) + my-app:experiment (متفرع)
rdc repo delete --name my-app:experiment -m my-server  # حذف المتفرع، الأصلي لا يتأثر
```

**استنساخ فوري بدون نسخ.** تقنية CoW (النسخ عند الكتابة). يتم في أجزاء من الثانية، بدون نسخ بيانات. تُشارَك الكتل حتى يقوم أحد الطرفين بالكتابة.

**حالات الاستخدام:**
- **الذكاء الاصطناعي / التعلم الآلي:** استنسخ بيانات الإنتاج، نفّذ تجربة، تخلّص منها أو اعتمدها
- **DevOps:** استنسخ ثم اختبر الترحيل ثم احذف إذا فشل، واعتمد إذا نجح
- **النسخ الاحتياطي:** الاستنساخ = لقطة فورية، أرسلها خارج الموقع

> دورة حياة الاستنساخ، الاستنساخ عبر الأجهزة: [المستودعات](/en/docs/repositories).

### 2. الدفع إلى جهاز آخر

```bash
# دفع المستودع إلى جهاز آخر
rdc repo push --name my-app -m my-server --to backup-server

# دفع مع نشر تلقائي على الهدف
rdc repo push --name my-app -m my-server --to backup-server --up

# دفع مع نقطة تفتيش CRIU (ترحيل حي، يحفظ حالة الذاكرة)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# دفع إلى جهاز جديد (تجهيز تلقائي عبر مزود سحابي)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. الدفع إلى التخزين السحابي (OneDrive، Google Drive، S3)

```bash
# استيراد إعدادات rclone كخلفية تخزين
rdc config storage import --file ~/rclone.conf

# عرض وحدات التخزين المتاحة
rdc storage list

# دفع المستودع إلى التخزين السحابي
rdc repo push --name my-app -m my-server --to my-s3-backup

# عرض النسخ الاحتياطية على التخزين
rdc repo backup list --from my-s3-backup -m my-server
```

يكشف `--to` تلقائيًا ما إذا كان الهدف جهازًا أو خلفية تخزين. يعمل مع أي مزود يدعمه rclone: S3، R2، B2، OneDrive، Google Drive، SFTP، وغيرها.

### 4. السحب من مصدر بعيد

```bash
# سحب مستودع من جهاز سحابي إلى خادمك المحلي
rdc repo pull --name my-app -m my-local-server --from cloud-server

# سحب من التخزين السحابي
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# سحب وتشغيل فوري
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**لماذا السحب؟** جهازك المحلي خلف NAT. السحابة لا تستطيع الدفع إليك. لكنك تستطيع الوصول إلى السحابة. السحب يجلب المستودع إلى بيئتك.

**الدورة الكاملة:** أنشئ على بيئة التطوير ثم ادفع إلى السحابة ثم اسحب إلى الإنتاج ثم `--up`. مستودع واحد، أي جهاز، أي سحابة.

> الجدولة، النسخ الاحتياطي التلقائي، الاستعادة: [النسخ الاحتياطي والاستعادة](/en/docs/backup-restore).

---

## الوكيل العكسي وشهادات SSL

### 1. إعداد البنية التحتية

```bash
rdc config infra set -m my-server  # إعداد: النطاق الأساسي، عناوين IP العامة، نطاقات المنافذ
rdc config infra show -m my-server  # مراجعة الإعدادات
rdc config infra push -m my-server  # دفع إعدادات الوكيل إلى الخادم البعيد
```

**كيف يعمل التوجيه:**
- يكتشف Traefik الحاويات تلقائيًا عبر تسميات `rediacc.service_name` و `rediacc.service_port`
- المسارات: `{service}-{networkId}.{baseDomain}` تُوجَّه إلى عنوان الحاوية IP:port
- شهادات SSL: عبر Let's Encrypt باستخدام تحدي Cloudflare DNS-01 (تجديد تلقائي، شهادات wildcard)

### 2. قالب الوكيل العكسي

```bash
rdc repo template apply --name proxy -m my-server -r infra  # نشر الوكيل في مستودع
rdc repo up --name infra -m my-server  # تشغيل Traefik
```

الآن يقوم Traefik بتوجيه حركة المرور الخارجية إلى جميع المستودعات على هذا الجهاز. كل حاوية تحصل على نقطة نهاية HTTPS تلقائيًا.

```bash
# انتقل إلى https://my-app.example.com لرؤية التوجيه إلى الحاوية
# تحويل TCP/UDP لقواعد البيانات:
#   rediacc.tcp_ports=3306,5432 → منافذ خارجية مخصصة تلقائيًا
```

> قواعد التوجيه، DNS، إعدادات TLS: [الشبكات](/en/docs/networking).

---

## الخطوات التالية

- **[دليل الترحيل](/en/docs/migration)** - نقل المشاريع الحالية إلى مستودعات Rediacc
- **[المراقبة](/en/docs/monitoring)** - صحة الجهاز، الحاويات، الخدمات، التشخيصات
- **[مرجع سطر الأوامر](/en/docs/cli-application)** - المرجع الكامل للأوامر
- **[ورقة الغش](/en/docs/rdc-cheat-sheet)** - بحث سريع عن الأوامر
- **[استكشاف الأخطاء وإصلاحها](/en/docs/troubleshooting)** - حلول للمشكلات الشائعة
- **[قواعد Rediacc](/en/docs/rules-of-rediacc)** - أفضل ممارسات Rediaccfile وقائمة التحقق من النشر
