---
title: البدء السريع
description: تشغيل خدمة حاويات على خادمك في 5 دقائق.
category: Guides
order: -1
language: ar
sourceHash: b368b94e7064efe1
---

# البدء السريع

انشر بيئة حاويات مشفرة ومعزولة على خادمك الخاص في 5 دقائق. لا حاجة لحسابات سحابية أو اعتماد على خدمات SaaS.

## المتطلبات الأساسية

- جهاز عمل يعمل بنظام Linux أو macOS
- خادم بعيد (Ubuntu 24.04+ أو Debian 12+ أو Fedora 43+) مع وصول SSH وصلاحيات sudo
- زوج مفاتيح SSH (مثلاً `~/.ssh/id_ed25519`)

## 1. تثبيت سطر الأوامر

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. إنشاء إعداد

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. إضافة الخادم

```bash
rdc config add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. تجهيز الخادم

```bash
rdc config setup-machine server-1
```

يقوم هذا الأمر بتثبيت Docker و cryptsetup وملف renet الثنائي على خادمك.

## 5. إنشاء مستودع مشفر

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. نشر الخدمات

قم بتوصيل المستودع، وأنشئ ملفات `docker-compose.yml` و `Rediaccfile` بداخله، ثم ابدأ التشغيل:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. التحقق

```bash
rdc machine containers server-1
```

يجب أن ترى حاوياتك قيد التشغيل.

## ما هو Rediacc؟

ينشر Rediacc خدمات حاويات على خوادم بعيدة تتحكم بها أنت. كل شيء مشفر في وضع السكون باستخدام LUKS، وكل مستودع يحصل على عملية Docker معزولة خاصة به، وكل التنسيق يتم عبر SSH من محطة عملك.

لا حسابات سحابية. لا اعتماد على خدمات SaaS. بياناتك تبقى على خوادمك.

## الخطوات التالية

- **[البنية التحتية](/ar/docs/architecture)** — فهم كيفية عمل Rediacc: اكتشاف المحوّلات، نموذج الأمان، عزل Docker
- **[rdc vs renet](/ar/docs/rdc-vs-renet)** — فهم أي سطر أوامر تستخدم للعمل اليومي مقابل العمل البعيد منخفض المستوى
- **[إعداد الجهاز](/ar/docs/setup)** — دليل الإعداد التفصيلي: الإعدادات، الأجهزة، تكوين البنية التحتية
- **[المستودعات](/ar/docs/repositories)** — إنشاء المستودعات وإدارتها وتغيير حجمها ونسخها والتحقق منها
- **[الخدمات](/ar/docs/services)** — ملفات Rediaccfile، شبكات الخدمات، النشر، التشغيل التلقائي
- **[النسخ الاحتياطي والاستعادة](/ar/docs/backup-restore)** — النسخ الاحتياطي إلى وحدة تخزين خارجية وجدولة النسخ الاحتياطية التلقائية
- **[المراقبة](/ar/docs/monitoring)** — صحة الجهاز، الحاويات، الخدمات، التشخيصات
- **[الأدوات](/ar/docs/tools)** — مزامنة الملفات، طرفية SSH، تكامل VS Code
- **[دليل الترحيل](/ar/docs/migration)** — نقل المشاريع الحالية إلى مستودعات Rediacc
- **[استكشاف الأخطاء وإصلاحها](/ar/docs/troubleshooting)** — حلول للمشكلات الشائعة
- **[مرجع سطر الأوامر](/ar/docs/cli-application)** — المرجع الكامل للأوامر
