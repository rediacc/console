---
title: rdc vs renet
description: متى تستخدم rdc ومتى تستخدم renet.
category: Concepts
order: 1
language: ar
sourceHash: "d3e2a6750f95b6c1"
---

# rdc مقابل renet

يحتوي Rediacc على ملفين تنفيذيين. إليك متى تستخدم كلًا منهما.

| | rdc | renet |
|---|-----|-------|
| **يعمل على** | جهاز العمل الخاص بك | الخادم البعيد |
| **يتصل عبر** | SSH | يعمل محليًا بصلاحيات الجذر |
| **يستخدمه** | الجميع | تصحيح الأخطاء المتقدم فقط |
| **التثبيت** | تقوم بتثبيته أنت | يقوم `rdc` بتوفيره تلقائيًا |

> للعمل اليومي، استخدم `rdc`. نادرًا ما تحتاج إلى `renet` مباشرة.

## كيف يعملان معًا

يتصل `rdc` بخادمك عبر SSH وينفذ أوامر `renet` نيابة عنك. تكتب أمرًا واحدًا على جهاز العمل الخاص بك، ويتولى `rdc` الباقي:

1. يقرأ الإعداد المحلي (`~/.config/rediacc/rediacc.json`)
2. يتصل بالخادم عبر SSH
3. يحدّث ملف `renet` الثنائي إذا لزم الأمر
4. ينفذ عملية `renet` المطابقة على الخادم
5. يعيد النتيجة إلى طرفيتك

## استخدم `rdc` للعمل العادي

جميع المهام الشائعة تمر عبر `rdc` على جهاز العمل الخاص بك:

```bash
# Set up a new server
rdc config setup-machine server-1

# Create and start a repository
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Stop a repository
rdc repo down my-app -m server-1

# Check machine health
rdc machine health server-1
```

راجع [البدء السريع](/ar/docs/quick-start) للاطلاع على شرح تفصيلي كامل.

## استخدم `renet` لتصحيح الأخطاء على الخادم

تحتاج إلى `renet` مباشرة فقط عند الاتصال بالخادم عبر SSH من أجل:

- تصحيح الأخطاء الطارئ عندما يتعذر على `rdc` الاتصال
- فحص تفاصيل النظام الداخلية غير المتاحة عبر `rdc`
- عمليات الاسترداد منخفضة المستوى

جميع أوامر `renet` تتطلب صلاحيات الجذر (`sudo`). راجع [مرجع الخادم](/ar/docs/server-reference) للاطلاع على القائمة الكاملة لأوامر `renet`.

## تجريبي: `rdc ops` (أجهزة افتراضية محلية)

يغلّف `rdc ops` أوامر `renet ops` لإدارة مجموعات الأجهزة الافتراضية المحلية على جهاز العمل الخاص بك:

```bash
rdc ops setup              # Install prerequisites (KVM or QEMU)
rdc ops up --basic         # Start a minimal cluster
rdc ops status             # Check VM status
rdc ops ssh 1              # SSH into bridge VM
rdc ops ssh 1 hostname     # Run a command on bridge VM
rdc ops down               # Destroy cluster
```

> يتطلب المحوّل المحلي. غير متاح مع محوّل السحابة.

تعمل هذه الأوامر بتشغيل `renet` محليًا (وليس عبر SSH). راجع [الأجهزة الافتراضية التجريبية](/ar/docs/experimental-vms) للاطلاع على التوثيق الكامل.

## ملاحظة حول Rediaccfile

قد ترى `renet compose -- ...` داخل ملف `Rediaccfile`. هذا أمر طبيعي — تعمل دوال Rediaccfile على الخادم حيث يكون `renet` متاحًا.

من جهاز العمل الخاص بك، قم بتشغيل وإيقاف أحمال العمل باستخدام `rdc repo up` و `rdc repo down`.
