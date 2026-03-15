---
title: النسخ الاحتياطي والاستعادة
description: >-
  نسخ المستودعات المشفرة احتياطياً إلى وحدات تخزين خارجية، والاستعادة من النسخ
  الاحتياطية، وجدولة النسخ الاحتياطي التلقائي.
category: Guides
order: 7
language: ar
sourceHash: "2ac1e17539336175"
---

# النسخ الاحتياطي والاستعادة

يمكن لـ Rediacc نسخ المستودعات المشفرة احتياطياً إلى مزودي تخزين خارجيين واستعادتها على نفس الجهاز أو على جهاز مختلف. النسخ الاحتياطية مشفرة -- يلزم بيانات اعتماد LUKS الخاصة بالمستودع للاستعادة.

## تكوين التخزين

قبل إرسال النسخ الاحتياطية، قم بتسجيل مزود تخزين. يدعم Rediacc أي تخزين متوافق مع rclone: S3 وB2 وGoogle Drive وغيرها الكثير.

### الاستيراد من rclone

إذا كان لديك بالفعل جهاز rclone بعيد مُكوَّن:

```bash
rdc config storage import rclone.conf
```

يستورد هذا تكوينات التخزين من ملف إعدادات rclone إلى التكوين الحالي. الأنواع المدعومة: S3 وB2 وGoogle Drive وOneDrive وMega وDropbox وBox وAzure Blob وSwift.

### عرض وحدات التخزين

```bash
rdc config storage list
```

## إرسال نسخة احتياطية

إرسال نسخة احتياطية من مستودع إلى تخزين خارجي:

```bash
rdc repo push my-app -m server-1 --to my-storage
```

| الخيار | الوصف |
|--------|-------|
| `--to <storage>` | موقع التخزين الهدف |
| `--to-machine <machine>` | الجهاز الهدف للنسخ الاحتياطي من جهاز إلى جهاز |
| `--dest <filename>` | اسم ملف الوجهة المخصص |
| `--checkpoint` | إنشاء نقطة تحقق قبل الإرسال |
| `--force` | استبدال نسخة احتياطية موجودة |
| `--tag <tag>` | وسم النسخة الاحتياطية |
| `-w, --watch` | مراقبة تقدم العملية |
| `--debug` | تفعيل الإخراج التفصيلي |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## سحب / استعادة نسخة احتياطية

سحب نسخة احتياطية لمستودع من تخزين خارجي:

```bash
rdc repo pull my-app -m server-1 --from my-storage
```

| الخيار | الوصف |
|--------|-------|
| `--from <storage>` | موقع التخزين المصدر |
| `--from-machine <machine>` | الجهاز المصدر للاستعادة من جهاز إلى جهاز |
| `--force` | استبدال النسخة الاحتياطية المحلية الموجودة |
| `-w, --watch` | مراقبة تقدم العملية |
| `--debug` | تفعيل الإخراج التفصيلي |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## عرض النسخ الاحتياطية

عرض النسخ الاحتياطية المتاحة في موقع تخزين:

```bash
rdc repo backup list --from my-storage -m server-1
```

## المزامنة المجمّعة

إرسال أو سحب جميع المستودعات دفعة واحدة:

### إرسال الكل إلى التخزين

```bash
rdc repo push --to my-storage -m server-1
```

### سحب الكل من التخزين

```bash
rdc repo pull --from my-storage -m server-1
```

| الخيار | الوصف |
|--------|-------|
| `--to <storage>` | التخزين الهدف (اتجاه الإرسال) |
| `--from <storage>` | التخزين المصدر (اتجاه السحب) |
| `--repo <name>` | مزامنة مستودعات محددة (قابل للتكرار) |
| `--override` | استبدال النسخ الاحتياطية الموجودة |
| `--debug` | تفعيل الإخراج التفصيلي |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## النسخ الاحتياطي المجدول

أتمتة النسخ الاحتياطي بجدول cron يعمل كمؤقت systemd على الجهاز البعيد.

### تعيين الجدول

```bash
rdc config backup-strategy set --destination my-storage --cron "0 2 * * *" --enable
```

يمكنك تكوين وجهات متعددة بجداول مختلفة:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

| الخيار | الوصف |
|--------|-------|
| `--destination <storage>` | وجهة النسخ الاحتياطي (يمكن تعيينها لكل وجهة) |
| `--cron <expression>` | تعبير cron (مثال: `"0 2 * * *"` للتشغيل يومياً الساعة 2 صباحاً) |
| `--enable` | تفعيل الجدول |
| `--disable` | تعطيل الجدول |

### إرسال الجدول إلى الجهاز

نشر تكوين الجدول على جهاز كمؤقت systemd:

```bash
rdc machine deploy-backup server-1
```

### عرض الجدول

```bash
rdc config backup-strategy show
```

## تصفح التخزين

تصفح محتويات موقع تخزين:

```bash
rdc storage browse my-storage
```

## أفضل الممارسات

- **جدولة النسخ الاحتياطي اليومي** لمزود تخزين واحد على الأقل
- **اختبار الاستعادة** بشكل دوري للتحقق من سلامة النسخ الاحتياطية
- **استخدام مزودي تخزين متعددين** للبيانات الحساسة (مثال: S3 + B2)
- **الحفاظ على أمان بيانات الاعتماد** -- النسخ الاحتياطية مشفرة لكن بيانات اعتماد LUKS مطلوبة للاستعادة
