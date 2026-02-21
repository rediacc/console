---
title: "rdc vs renet"
description: "متى تستخدم rdc ومتى تستخدم renet."
category: "Guides"
order: 1
language: ar
sourceHash: "cb2c174b8cf1a078"
---

# rdc vs renet

يستخدم Rediacc ملفين تنفيذيين:

- `rdc` هو واجهة CLI الموجهة للمستخدم وتعمل على جهازك المحلي.
- `renet` هو ملف تنفيذي منخفض المستوى يعمل على الخادم.

في معظم العمليات اليومية، استخدم `rdc`.

## النموذج الذهني

اعتبر `rdc` طبقة التحكم و`renet` طبقة التنفيذ.

`rdc`:
- يقرأ السياق المحلي وربط الاجهزة
- يتصل بالخوادم عبر SSH
- يثبت/يحدث `renet` عند الحاجة
- ينفذ العملية البعيدة المناسبة بالنيابة عنك

`renet`:
- يعمل بصلاحيات مرتفعة على الخادم
- يدير datastore ووحدات LUKS وعمليات mount وDocker daemon معزول
- ينفذ عمليات منخفضة المستوى على النظام والمستودعات

## ما الذي تستخدمه عمليا

### استخدم `rdc` (الافتراضي)

استخدم `rdc` في التدفقات العادية:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### استخدم `renet` (متقدم / جهة الخادم)

استخدم `renet` مباشرة فقط عندما تحتاج عمدا الى تحكم منخفض المستوى على الخادم، مثل:

- تصحيح طارئ مباشرة على الخادم
- صيانة واستعادة على مستوى المضيف
- التحقق من تفاصيل داخلية غير متاحة عبر `rdc`

معظم المستخدمين لا يحتاجون لتشغيل `renet` مباشرة في العمل اليومي.

### تجريبي: `rdc ops` (اجهزة افتراضية محلية)

`rdc ops` يغلف `renet ops` لادارة مجموعات الاجهزة الافتراضية المحلية على جهازك:

```bash
rdc ops setup    # تثبيت المتطلبات (KVM او QEMU)
rdc ops up --basic  # انشاء مجموعة بسيطة
rdc ops status   # التحقق من حالة الاجهزة الافتراضية
rdc ops ssh 1    # SSH الى جهاز Bridge الافتراضي
rdc ops down     # حذف المجموعة
```

تعمل هذه الاوامر على تشغيل `renet` محليا (وليس عبر SSH). راجع [الاجهزة الافتراضية التجريبية](/ar/docs/experimental-vms) للتوثيق الكامل.

## ملاحظة حول Rediaccfile

قد ترى `renet compose -- ...` داخل `Rediaccfile`. هذا متوقع: وظائف Rediaccfile تعمل على جهة الخادم حيث يتوفر `renet`.

من جهازك المحلي، غالبا ستستمر في تشغيل/ايقاف الاحمال عبر `rdc repo up` و`rdc repo down`.
