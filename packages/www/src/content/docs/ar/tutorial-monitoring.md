---
title: "المراقبة"
description: "تحقق من صحة خوادمك ومستودعاتك من حاسوبك باستخدام أوامر rdc machine."
category: "Tutorials"
subcategory: advanced
order: 12
language: ar
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# المراقبة

تطبيقك منشور ويعمل ومنسوخ احتياطيًا. الآن تأكد من بقاء كل شيء سليمًا. تمنحك `rdc` صورة كاملة عن أي خادم (الصحة والحاويات والمستودعات) من حاسوبك.

## شاهد الدرس التعليمي

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## ثلاثة أشياء يمكنك فحصها

![Health, containers, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## الصحة: معلومات النظام

ابدأ بعرض النظام:

```bash
time rdc machine query --name my-server --system
```

يُظهر هذا وقت تشغيل النظام واستخدام القرص وحالة التخزين. إذا كان هناك خطأ، يُخبرك.

## الحاويات

لرؤية جميع الحاويات الجارية عبر كل مستودع على الجهاز:

```bash
time rdc machine query --name my-server --containers
```

تحصل على الاسم والحالة والصحة ووحدة المعالجة المركزية والذاكرة لكل حاوية، بالإضافة إلى المستودع الذي تنتمي إليه.

## المستودعات

للتحقق من مستودعاتك:

```bash
time rdc machine query --name my-server --repositories
```

يُظهر هذا كل مستودع مع حجمه وحالة التحميل وحالة Docker واستخدام القرص.

## كل شيء في لقطة واحدة

```bash
time rdc machine query --name my-server
```

معلومات النظام والمستودعات والحاويات، كلها في أمر واحد. يُرجع نفس أمر `query` بدون مرشحات الصورة الكاملة؛ مع `--system` أو `--containers` أو `--repositories` أو `--services` أو `--network` أو `--block-devices` يُضيّق النتائج إلى ذلك القسم فقط.

## فحص محلي سريع

يفحص `rdc doctor` إعدادك المحلي (Node ومفتاح SSH و`renet` وDocker)، بصرف النظر عن أي خادم محدد:

```bash
time rdc doctor
```

## انتهيت

هذه هي السلسلة الكاملة. يمكنك الآن التثبيت والإعداد والنشر والنسخ والتفعيل والتشغيل التلقائي والنسخ الاحتياطي والمراقبة. كل ذلك من طرفيتك، على خوادمك الخاصة.
