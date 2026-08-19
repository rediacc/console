---
title: "rdc مقابل renet"
description: "متى تستخدم rdc ومتى تستخدم renet."
category: Concepts
tags:
  - cli
  - operations
order: 1
language: ar
sourceHash: "ac6dd16161829495"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# rdc مقابل renet

يتضمن Rediacc ملفين تنفيذيين. وظيفتان، مكانان. إليك أيهما الذي يُستخدم.

| | rdc | renet |
|---|-----|-------|
| **يعمل على** | جهاز العمل الخاص بك | الخادم البعيد |
| **يتصل عبر** | SSH | يعمل محليًا بصلاحيات الجذر |
| **يستخدمه** | الجميع | تصحيح الأخطاء المتقدم فقط |
| **التثبيت** | تقوم بتثبيته أنت | يقوم `rdc` بتوفيره تلقائيًا |

> للعمل اليومي، استخدم `rdc`. نادرًا ما تحتاج إلى `renet` مباشرة.

## كيف يعملان معًا

على جهاز العمل الخاص بك تشغّل `rdc`. يفتح اتصال SSH بخادمك وينفذ أمر `renet` المقابل هناك نيابة عنك. أمر واحد، مكان واحد لتشغيله:

1. يقرأ الإعداد المحلي (`~/.config/rediacc/rediacc.json`)
2. يتصل بالخادم عبر SSH
3. يحدّث ملف `renet` الثنائي إذا لزم الأمر
4. ينفذ عملية `renet` المطابقة على الخادم
5. يعيد النتيجة إلى طرفيتك

## استخدم `rdc` للعمل العادي

جميع المهام الشائعة تمر عبر `rdc` على جهاز العمل الخاص بك:

```bash
# Set up a new server
rdc machine setup server-1

# Create and start a repository
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app

# Stop a repository
rdc repo down my-app

# Check machine health
rdc machine health server-1
```

راجع [البدء السريع](/ar/docs/quick-start) للاطلاع على شرح تفصيلي كامل.

## استخدم `renet` لتصحيح الأخطاء على الخادم

تحتاج إلى `renet` مباشرة فقط عند الاتصال بالخادم عبر SSH من أجل:

- تصحيح الأخطاء الطارئ عندما يتعذر على `rdc` الاتصال
- فحص تفاصيل النظام الداخلية غير المتاحة عبر `rdc`
- عمليات الاسترداد منخفضة المستوى

جميع أوامر `renet` تتطلب صلاحيات الجذر (`sudo`). لا يغلف `rdc` كل أمر فرعي من أوامر `renet`؛ لأي عملية غير مغطاة، قم بالاتصال عبر SSH واستدع `renet` مباشرة. راجع [مرجع الخادم](/ar/docs/server-reference) للاطلاع على القائمة الكاملة لأوامر `renet`.

## تجريبي: `rdc ops` (أجهزة افتراضية محلية)

يغلّف `rdc ops` أوامر `renet ops` لإدارة مجموعات الأجهزة الافتراضية المحلية على جهاز العمل الخاص بك:

```bash
rdc ops setup              # Install prerequisites (KVM or QEMU)
rdc ops up --basic         # Start a minimal cluster
rdc ops status             # Check VM status
rdc ops ssh --vm-id 1  # SSH into bridge VM
rdc ops ssh --vm-id 1 -c hostname  # Run a command on bridge VM
rdc ops down               # Destroy cluster
```

> يعمل عبر المحوّل المحلي.

تعمل هذه الأوامر بتشغيل `renet` محليًا (وليس عبر SSH). راجع [الأجهزة الافتراضية التجريبية](/ar/docs/experimental-vms) للاطلاع على التوثيق الكامل.

## ملاحظة حول Rediaccfile

ستجد `renet compose -- ...` داخل ملف `Rediaccfile`. لا داعي للقلق. دوال Rediaccfile تعمل على الخادم، حيث يكون `renet` مثبتًا بالفعل.

من جهاز العمل الخاص بك، قم بتشغيل وإيقاف أحمال العمل باستخدام `rdc repo up` و `rdc repo down`.
