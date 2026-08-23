---
title: "إعداد الجهاز"
description: "إنشاء إعداد، وإضافة أجهزة، وتجهيز الخوادم، وتهيئة البنية التحتية."
category: "Guides"
tags:
  - getting-started
  - operations
subcategory: setup
order: 3
language: ar
sourceHash: "a0f69282724c27ea"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# إعداد الجهاز

أربع خطوات لتشغيل جهازك الأول: إنشاء إعداد، وتسجيل خادم، وتجهيزه، وتهيئة البنية التحتية اختيارياً للوصول العام.

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
rdc machine add server-1 --ip 203.0.113.50 --user deploy
```

| الخيار | مطلوب | الافتراضي | الوصف |
|--------|-------|-----------|-------|
| `--ip <address>` | نعم | - | عنوان IP أو اسم المضيف للخادم البعيد |
| `--user <username>` | نعم | - | اسم مستخدم SSH على الخادم البعيد |
| `--port <port>` | لا | `22` | منفذ SSH |
| `--datastore <path>` | لا | `/mnt/rediacc` | المسار على الخادم حيث يخزّن Rediacc المستودعات المشفرة |

بعد إضافة الجهاز، يقوم rdc تلقائياً بتشغيل `ssh-keyscan` لجلب مفاتيح المضيف الخاصة بالخادم. يمكنك أيضاً تشغيل هذا يدوياً:

```bash
rdc machine scan-keys server-1
```

لعرض جميع الأجهزة المسجلة:

```bash
rdc machine list
```

## الخطوة 3: إعداد الجهاز

قم بتجهيز الخادم البعيد بجميع المتطلبات اللازمة:

```bash
rdc machine setup server-1
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

## طبقات مخزن البيانات

مخزن البيانات هو تجمع التخزين لكل جهاز الذي يحتفظ بصور المستودعات المشفرة. ينشئ `machine setup` مخزن بيانات **محلياً** افتراضياً: نظام ملفات BTRFS مدعوم بجهاز loop على قرص الخادم نفسه، بحجم يُحدَّد عبر `--datastore-size` (الافتراضي `95%` من القرص المتاح). هذه هي الطبقة الصحيحة لما يكاد يكون كل نشر بجهاز واحد ولا تحتاج إلى شيء غير الخادم نفسه.

### تحديد حجم مخزن البيانات

يقبل `--datastore-size` نسبة مئوية (`95%`) أو حجماً مطلقاً (`50G`، `1T`). يمكن توسيع مخزن البيانات لاحقاً أثناء التشغيل:

```bash
rdc datastore resize ds-server-1 --size 200G
```

يُحدَّد حجم المستودعات داخل مخزن البيانات بشكل مستقل عند `repo create` ويمكن توسيعها أثناء التشغيل، لذا لست بحاجة إلى تخصيص مساحة زائدة لمخزن البيانات مسبقاً.

### طبقة Ceph RBD

للتخزين المشترك أو القابل للتوسع أو الداعم لـ Kubernetes، هيّئ مخزن البيانات بدلاً من ذلك على عنقود Ceph خارجي. يعيش مخزن البيانات حينها على صورة RBD (BTRFS فوقها، دون طبقة LUKS لكل صورة)، وتستخدم التفريعات استنساخات نسخ عند الكتابة من RBD بدلاً من reflinks الخاصة بـ BTRFS.

```bash
# 1. تسجيل مرجع Ceph الخاص بالجهاز (التجمع + صورة RBD، غير سري)

# 2. تهيئة مخزن البيانات على طبقة Ceph
rdc datastore create ds-server-1 -m server-1 --backend ceph --pool rbd --image datastore-server1 --size 100G
```

تبقى مفاتيح Ceph على الأجهزة؛ يحتوي ملف الإعداد فقط على مراجع التجمع والصورة غير السرية. Ceph هي أيضاً طبقة التخزين التي تستهلكها عناقيد Kubernetes عبر ceph-csi. راجع دليل [Kubernetes](/ar/docs/kubernetes) للعناقيد والأحجام الثابتة، و[البنية المعمارية](/ar/docs/architecture) لمقارنة الطبقتين.

## إدارة مفاتيح المضيف

إذا تغيّر مفتاح SSH الخاص بالخادم (مثلاً بعد إعادة التثبيت)، قم بتحديث المفاتيح المخزّنة:

```bash
rdc machine scan-keys server-1
```

يُحدّث هذا حقل `knownHosts` في إعداداتك لهذا الجهاز.

## اختبار اتصال SSH

بعد إضافة جهاز، تحقق من إمكانية الوصول إليه:

```bash
rdc term connect server-1 -c "hostname"
```

يفتح هذا اتصال SSH بالجهاز وينفّذ الأمر. إذا نجح، فإن إعدادات SSH الخاصة بك صحيحة.

للحصول على تشخيصات أكثر تفصيلاً، شغّل:

```bash
rdc doctor
```

> **نصيحة**: للتحقق من اتصال SSH، شغّل `rdc term connect <machine> -c "hostname"` أو استخدم `ssh` مباشرة.

## تهيئة البنية التحتية

للأجهزة التي تحتاج إلى تقديم حركة المرور بشكل عام، قم بتهيئة إعدادات البنية التحتية:

### تعيين البنية التحتية

```bash
rdc machine infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| الخيار | النطاق | الوصف |
|--------|--------|-------|
| `--public-ipv4 <ip>` | Machine | عنوان IPv4 عام، يتم إنشاء نقاط دخول الوكيل فقط لعائلات العناوين المكونة |
| `--public-ipv6 <ip>` | Machine | عنوان IPv6 عام، يتم إنشاء نقاط دخول الوكيل فقط لعائلات العناوين المكونة |
| `--base-domain <domain>` | Machine | النطاق الأساسي للتطبيقات (مثل `example.com`) |
| `--cert-email <email>` | Config | البريد الإلكتروني لشهادات TLS من Let's Encrypt (مشترك عبر الأجهزة) |
| `--cf-dns-token <token>` | Config | رمز API لـ Cloudflare DNS لتحديات ACME DNS-01 (مشترك عبر الأجهزة) |
| `--tcp-ports <ports>` | Machine | منافذ TCP إضافية مفصولة بفواصل لإعادة التوجيه (مثل `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | منافذ UDP إضافية مفصولة بفواصل لإعادة التوجيه (مثل `53`) |

الخيارات ذات نطاق Machine تُخزّن لكل جهاز. الخيارات ذات نطاق Config (`--cert-email`، `--cf-dns-token`) مشتركة عبر جميع الأجهزة في الإعداد. عيّنها مرة واحدة وستُطبّق في كل مكان.

### عرض البنية التحتية

```bash
rdc machine infra show server-1
```

### الدفع إلى الخادم

أنشئ وانشر إعدادات وكيل Traefik العكسي على الخادم:

```bash
rdc machine infra push server-1
```

هذا الأمر:
1. ينشر ملف renet التنفيذي على الجهاز البعيد
2. يُهيئ وكيل Traefik العكسي والموجّه وخدمات systemd
3. يُنشئ سجلات DNS في Cloudflare للنطاق الفرعي للجهاز (`server-1.example.com` و `*.server-1.example.com`) إذا تم تعيين `--cf-dns-token`

خطوة DNS تلقائية ومتساوية القوة. تُنشئ السجلات المفقودة، وتُحدّث السجلات التي تغيّرت عناوين IP الخاصة بها، وتتخطى السجلات الصحيحة بالفعل. إذا لم يتم تكوين رمز Cloudflare، يتم تخطي DNS مع تحذير. يتم إنشاء سجلات DNS البرية لكل مستودع (لمسارات تلقائية) تلقائياً عند تشغيل `rdc repo up`.

## التزويد السحابي

بدلاً من إنشاء الأجهزة الافتراضية يدوياً، يمكنك تكوين مزود سحابي والسماح لـ `rdc` بتزويد الأجهزة تلقائياً باستخدام [OpenTofu](https://opentofu.org/).

### المتطلبات الأساسية

قم بتثبيت OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

تأكد من تسجيل مفتاح SSH مع `rdc`:

```bash
# Reads the key file and inlines the content under /credentials/ssh.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### إضافة مزود سحابي

```bash
rdc machine provider add my-linode \
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
5. تُهيئ وكيل Traefik و DNS الخاص بـ Cloudflare (يكتشف النطاق الأساسي تلقائياً من الأجهزة الأخرى، أو مرر `--base-domain` صراحةً)

| الخيار | الوصف |
|--------|-------|
| `--provider <name>` | اسم المزود السحابي (من `add-provider`) |
| `--region <region>` | تجاوز المنطقة الافتراضية للمزود |
| `--type <type>` | تجاوز نوع المثيل الافتراضي |
| `--image <image>` | تجاوز صورة نظام التشغيل الافتراضية |
| `--base-domain <domain>` | النطاق الأساسي للبنية التحتية. يتم اكتشافه تلقائياً من الأجهزة الأخرى إذا لم يتم تحديده |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | عرض مخرجات التزويد التفصيلية |

### إلغاء تزويد جهاز

```bash
rdc machine deprovision prod-2
```

يدمّر الجهاز الافتراضي عبر OpenTofu ويزيله من إعداداتك. يتطلب تأكيداً ما لم يُستخدم `--force`. يعمل فقط مع الأجهزة التي تم إنشاؤها باستخدام `machine provision`.

### عرض المزودين

```bash
rdc machine provider list
```

## تعيين القيم الافتراضية

عيّن قيماً افتراضية حتى لا تحتاج إلى تحديدها في كل أمر:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Default machine
rdc config set team my-team                   # الفريق الافتراضي لمخزن التكوين
```

بعد تعيين جهاز افتراضي، يمكنك حذف `-m server-1` من الأوامر:

```bash
rdc repo create my-app -m my-server --size 10G
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
