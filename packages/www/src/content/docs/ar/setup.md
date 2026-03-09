---
title: "إعداد الجهاز"
description: "إنشاء إعداد، وإضافة أجهزة، وتجهيز الخوادم، وتهيئة البنية التحتية."
category: "Guides"
order: 3
language: ar
sourceHash: "5256e189c350ee18"
---

# إعداد الجهاز

ترشدك هذه الصفحة خلال إعداد جهازك الأول: إنشاء إعداد، وتسجيل خادم، وتجهيزه، وتهيئة البنية التحتية اختيارياً للوصول العام.

## الخطوة 1: إنشاء إعداد

**الإعداد** هو ملف إعداد مسمّى يخزّن بيانات اعتماد SSH، وتعريفات الأجهزة، وربط المستودعات. فكّر فيه كمساحة عمل للمشروع.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `--ssh-key <path>` | نعم | مسار مفتاح SSH الخاص بك. يتم توسيع رمز التلدة (`~`) تلقائياً. |
| `--renet-path <path>` | لا | مسار مخصص لملف renet التنفيذي على الأجهزة البعيدة. القيمة الافتراضية هي موقع التثبيت القياسي. |

ينشئ هذا إعداداً باسم `my-infra` ويخزّنه في `~/.config/rediacc/my-infra.json`. الإعداد الافتراضي (عند عدم تحديد اسم) يُخزَّن باسم `~/.config/rediacc/rediacc.json`.

> يمكنك إنشاء إعدادات متعددة (مثل `production`، `staging`، `dev`). بدّل بينها باستخدام خيار `--config` مع أي أمر.

## الخطوة 2: إضافة جهاز

سجّل خادمك البعيد كجهاز في الإعداد:

```bash
rdc config add-machine server-1 --ip 203.0.113.50 --user deploy
```

| الخيار | مطلوب | الافتراضي | الوصف |
|--------|-------|-----------|-------|
| `--ip <address>` | نعم | - | عنوان IP أو اسم المضيف للخادم البعيد |
| `--user <username>` | نعم | - | اسم مستخدم SSH على الخادم البعيد |
| `--port <port>` | لا | `22` | منفذ SSH |
| `--datastore <path>` | لا | `/mnt/rediacc` | المسار على الخادم حيث يخزّن Rediacc المستودعات المشفرة |

بعد إضافة الجهاز، يقوم rdc تلقائياً بتشغيل `ssh-keyscan` لجلب مفاتيح المضيف الخاصة بالخادم. يمكنك أيضاً تشغيل هذا يدوياً:

```bash
rdc config scan-keys server-1
```

لعرض جميع الأجهزة المسجلة:

```bash
rdc config machines
```

## الخطوة 3: إعداد الجهاز

قم بتجهيز الخادم البعيد بجميع المتطلبات اللازمة:

```bash
rdc config setup-machine server-1
```

يقوم هذا الأمر بما يلي:
1. رفع ملف renet التنفيذي إلى الخادم عبر SFTP
2. تثبيت Docker و containerd و cryptsetup (إن لم تكن موجودة)
3. إنشاء مستخدم النظام `rediacc` (UID 7111)
4. إنشاء مجلد مخزن البيانات وتحضيره للمستودعات المشفرة

| الخيار | مطلوب | الافتراضي | الوصف |
|--------|-------|-----------|-------|
| `--datastore <path>` | لا | `/mnt/rediacc` | مجلد مخزن البيانات على الخادم |
| `--datastore-size <size>` | لا | `95%` | نسبة القرص المتاح المخصصة لمخزن البيانات |
| `--debug` | لا | `false` | تفعيل المخرجات التفصيلية لاستكشاف الأخطاء |

> يجب تشغيل الإعداد مرة واحدة فقط لكل جهاز. من الآمن إعادة تشغيله عند الحاجة.

## إدارة مفاتيح المضيف

إذا تغيّر مفتاح SSH الخاص بالخادم (مثلاً بعد إعادة التثبيت)، قم بتحديث المفاتيح المخزّنة:

```bash
rdc config scan-keys server-1
```

يُحدّث هذا حقل `knownHosts` في إعداداتك لهذا الجهاز.

## اختبار اتصال SSH

بعد إضافة جهاز، تحقق من إمكانية الوصول إليه:

```bash
rdc term server-1 -c "hostname"
```

يفتح هذا اتصال SSH بالجهاز وينفّذ الأمر. إذا نجح، فإن إعدادات SSH الخاصة بك صحيحة.

للحصول على تشخيصات أكثر تفصيلاً، شغّل:

```bash
rdc doctor
```

> **محوّل السحابة فقط**: يوفر أمر `rdc machine test-connection` تشخيصات SSH مفصّلة ولكنه يتطلب محوّل السحابة. للمحوّل المحلي، استخدم `rdc term` أو `ssh` مباشرة.

## تهيئة البنية التحتية

للأجهزة التي تحتاج إلى تقديم حركة المرور بشكل عام، قم بتهيئة إعدادات البنية التحتية:

### تعيين البنية التحتية

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| الخيار | النطاق | الوصف |
|--------|--------|-------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address — proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address — proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | النطاق الأساسي للتطبيقات (مثل `example.com`) |
| `--cert-email <email>` | Config | البريد الإلكتروني لشهادات TLS من Let's Encrypt (مشترك عبر الأجهزة) |
| `--cf-dns-token <token>` | Config | رمز API لـ Cloudflare DNS لتحديات ACME DNS-01 (مشترك عبر الأجهزة) |
| `--tcp-ports <ports>` | Machine | منافذ TCP إضافية مفصولة بفواصل لإعادة التوجيه (مثل `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | منافذ UDP إضافية مفصولة بفواصل لإعادة التوجيه (مثل `53`) |

الخيارات ذات نطاق Machine تُخزّن لكل جهاز. الخيارات ذات نطاق Config (`--cert-email`، `--cf-dns-token`) مشتركة عبر جميع الأجهزة في الإعداد — عيّنها مرة واحدة وستُطبّق في كل مكان.

### عرض البنية التحتية

```bash
rdc config show-infra server-1
```

### الدفع إلى الخادم

أنشئ وانشر إعدادات وكيل Traefik العكسي على الخادم:

```bash
rdc config push-infra server-1
```

هذا الأمر:
1. ينشر ملف renet التنفيذي على الجهاز البعيد
2. يُهيئ وكيل Traefik العكسي والموجّه وخدمات systemd
3. يُنشئ سجلات DNS في Cloudflare للنطاق الفرعي للجهاز (`server-1.example.com` و `*.server-1.example.com`) إذا تم تعيين `--cf-dns-token`

خطوة DNS تلقائية ومتساوية القوة — تُنشئ السجلات المفقودة، وتُحدّث السجلات التي تغيّرت عناوين IP الخاصة بها، وتتخطى السجلات الصحيحة بالفعل. إذا لم يتم تكوين رمز Cloudflare، يتم تخطي DNS مع تحذير. Per-repo wildcard DNS records (for auto-routes) are created automatically when you run `rdc repo up`.

## التزويد السحابي

بدلاً من إنشاء الأجهزة الافتراضية يدوياً، يمكنك تكوين مزود سحابي والسماح لـ `rdc` بتزويد الأجهزة تلقائياً باستخدام [OpenTofu](https://opentofu.org/).

### المتطلبات الأساسية

قم بتثبيت OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

تأكد من أن إعدادات SSH تتضمن مفتاحاً عاماً:

```bash
rdc config set-ssh --private-key ~/.ssh/id_ed25519 --public-key ~/.ssh/id_ed25519.pub
```

### إضافة مزود سحابي

```bash
rdc config add-provider my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| الخيار | مطلوب | الوصف |
|--------|-------|-------|
| `--provider <source>` | نعم* | مصدر مزود معروف (مثل `linode/linode`، `hetznercloud/hcloud`) |
| `--source <source>` | نعم* | مصدر مزود OpenTofu مخصص (للمزودين غير المعروفين) |
| `--token <token>` | نعم | رمز API للمزود السحابي |
| `--region <region>` | لا | المنطقة الافتراضية للأجهزة الجديدة |
| `--type <type>` | لا | نوع/حجم المثيل الافتراضي |
| `--image <image>` | لا | صورة نظام التشغيل الافتراضية |
| `--ssh-user <user>` | لا | اسم مستخدم SSH (الافتراضي: `root`) |

\* يجب تحديد إما `--provider` أو `--source`. استخدم `--provider` للمزودين المعروفين (إعدادات مدمجة). استخدم `--source` مع خيارات `--resource` و `--ipv4-output` و `--ssh-key-attr` الإضافية للمزودين المخصصين.

### تزويد جهاز

```bash
rdc machine provision prod-2 --provider my-linode
```

يقوم هذا الأمر الواحد بما يلي:
1. إنشاء جهاز افتراضي على المزود السحابي عبر OpenTofu
2. انتظار اتصال SSH
3. تسجيل الجهاز في إعداداتك
4. تثبيت renet وجميع المتطلبات
5. Configures Traefik proxy and Cloudflare DNS (auto-detects base domain from sibling machines, or pass `--base-domain` explicitly)

| الخيار | الوصف |
|--------|-------|
| `--provider <name>` | اسم المزود السحابي (من `add-provider`) |
| `--region <region>` | تجاوز المنطقة الافتراضية للمزود |
| `--type <type>` | تجاوز نوع المثيل الافتراضي |
| `--image <image>` | تجاوز صورة نظام التشغيل الافتراضية |
| `--base-domain <domain>` | Base domain for infrastructure. Auto-detected from sibling machines if not specified |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | عرض مخرجات التزويد التفصيلية |

### إلغاء تزويد جهاز

```bash
rdc machine deprovision prod-2
```

يدمّر الجهاز الافتراضي عبر OpenTofu ويزيله من إعداداتك. يتطلب تأكيداً ما لم يُستخدم `--force`. يعمل فقط مع الأجهزة التي تم إنشاؤها باستخدام `machine provision`.

### عرض المزودين

```bash
rdc config providers
```

## تعيين القيم الافتراضية

عيّن قيماً افتراضية حتى لا تحتاج إلى تحديدها في كل أمر:

```bash
rdc config set machine server-1    # الجهاز الافتراضي
rdc config set team my-team        # الفريق الافتراضي (محوّل السحابة، تجريبي)
```

بعد تعيين جهاز افتراضي، يمكنك حذف `-m server-1` من الأوامر:

```bash
rdc repo create my-app --size 10G   # يستخدم الجهاز الافتراضي
```

## إعدادات متعددة

أدر بيئات متعددة باستخدام إعدادات مسمّاة:

```bash
# إنشاء إعدادات منفصلة
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# استخدام إعداد محدد
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

عرض جميع الإعدادات:

```bash
rdc config list
```

عرض تفاصيل الإعداد الحالي:

```bash
rdc config show
```
