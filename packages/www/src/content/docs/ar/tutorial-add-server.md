---
title: "إضافة خادمك الأول"
description: "سجّل خادمك الأول في rdc، وجهّزه، وافهم بنية rdc + renet."
category: "Tutorials"
subcategory: essentials
order: 3
language: ar
sourceHash: "2b5de59f61cfb88c"
---

# إضافة خادمك الأول

قبل إضافة خادم، من المفيد أن تفهم كيف تعمل `rdc`. تعتمد Rediacc على بنية من أداتين: `rdc` على حاسوبك، و`renet` على الخادم.

## شاهد الدرس التعليمي

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## لماذا أداتان؟

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** هي أداة CLI على حاسوبك. هنا تكتب أوامرك.
- **`renet`** هو المنسق على الخادم. يدير التشفير وDocker والعزل.

عندما تشغّل أمرًا محليًا، تتصل `rdc` عبر SSH وتُنفّذ `renet` على الخادم. لن تحتاج أبدًا للاتصال بخوادمك يدويًا عبر SSH؛ `rdc` تفعل ذلك نيابةً عنك.

## الخطوة 1: تسجيل الخادم

أخبر `rdc` عن الخادم. استبدل الاسم وعنوان IP والمستخدم بقيمك الخاصة.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## الخطوة 2: التجهيز

يقوم الإعداد بتثبيت `renet` وإنشاء مخزن البيانات المشفر على الخادم.

```bash
time rdc config machine setup --name my-server
```

عند الانتهاء، يكون خادمك جاهزًا لاستضافة المستودعات.

## مكان حفظ الإعداد

تحقق مما تعرفه `rdc` عن إعدادك:

```bash
time rdc config show
```

أو افتح ملف JSON مباشرةً:

```bash
vim ~/.config/rediacc/rediacc.json
```

يحتوي هذا الملف الواحد على كل شيء: الأجهزة والمستودعات ومفتاح SSH وبيانات اعتماد التشفير. انسخه إلى حاسوب آخر وستكون مستعدًا للعمل من ذلك الجهاز أيضًا.

---

التالي: [إنشاء مستودعك الأول](/en/docs/tutorial-create-repo).
