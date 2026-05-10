---
title: "النسخ الاحتياطي والاستعادة"
description: "ادفع مستودعك إلى تخزين خارجي واستعده على خادم جديد عند الحاجة."
category: "Tutorials"
subcategory: advanced
order: 11
language: ar
sourceHash: "8b48f3b19352aebe"
---

# النسخ الاحتياطي والاستعادة

تطبيقك يعمل في الإنتاج. الآن تأكد من أنك لن تفقده أبدًا. يمكن لـ`rdc` دفع مستودعك كاملًا (التطبيق وقاعدة البيانات والملفات والإعدادات) إلى تخزين خارجي وسحبه في أي وقت. النجاة من برامج الفدية وأعطال الأجهزة وأي شيء آخر.

## شاهد الدرس التعليمي

![Tutorial: Backup and restore](/assets/tutorials/tutorial-backup-restore.cast)

## ثلاث خطوات

![Configure, push, restore](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **اضبط** مزود التخزين.
2. **ادفع** نسخة احتياطية.
3. **استعد** عند الحاجة.

## الخطوة 1: ضبط التخزين

تحتاج إلى ملف إعداد `rclone`. إذا كنت تستخدم rclone بالفعل، استورده مباشرةً:

```bash
time rdc config storage import --file rclone.conf
```

يدعم هذا S3 وB2 وGoogle Drive وDropbox وغيرها الكثير. تحقق مما هو مربوط:

```bash
time rdc config storage list
```

## الخطوة 2: دفع نسخة احتياطية

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

مستودعك كاملًا (التطبيق وقاعدة البيانات والملفات وكل شيء) تم نسخه احتياطيًا الآن. لأن المستودع نفسه مشفر، النسخة الاحتياطية مشفرة أيضًا. لا إدارة مفاتيح إضافية.

أدرج نسخك الاحتياطية في أي وقت:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## لماذا لا يوجد توقف؟

التطبيق يواصل العمل أثناء رفع النسخة الاحتياطية. كيف يكون ذلك متسقًا؟

نفس منطق [النسخ](/en/docs/tutorial-forking). تنسخ `rdc` أولًا، ثم ترفع النسخة. تلتقط النسخة اللحظة؛ تطبيقك المباشر يواصل العمل. لا توقف، لا تناقض.

## الخطوة 3: الاستعادة على خادم جديد

لنفترض أن خادمك تعطّل. جهّز خادمًا جديدًا، أضفه إلى `rdc`، واسحب:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

ثم شغّله:

```bash
time rdc repo up --name my-app -m new-server
```

تطبيقك عاد. نفس البيانات، نفس الحاويات، جهاز مختلف.

## نسخ احتياطي أسرع: من جهاز إلى جهاز

يمكنك أيضًا الدفع مباشرةً بين الأجهزة بدون تخزين سحابي وسيط:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **نصيحة احترافية.** تُرسل رفعات التخزين دائمًا كل شيء. الجهاز إلى الجهاز يُرسل الفرق فقط. تستغرق أول عملية رفع من جهاز إلى جهاز الوقت المعتاد، لكن كل رفع بعدها أسرع بكثير. رائع للنسخ الاحتياطية المتكررة.

---

التالي: [المراقبة](/en/docs/tutorial-monitoring).
