---
title: "نشر تطبيقك الأول"
description: "انشر تطبيقًا في حاويات من قالب مدمج باستخدام renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: ar
sourceHash: "f75b5b6a716e94bf"
---

# نشر تطبيقك الأول

لديك مستودع فارغ. تأتي `rdc` بقوالب مدمجة حتى تتمكن من تشغيل تطبيقات حقيقية دون كتابة `docker-compose` من الصفر. ثلاث خطوات: اختر قالبًا، طبّقه، شغّله.

## شاهد الدرس التعليمي

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## اختر . طبّق . شغّل

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## الخطوة 1: الاختيار

تصفّح القوالب المتاحة:

```bash
time rdc repo template list
```

ستجد إعدادات جاهزة للتطبيقات الشائعة: Postgres وRedis وخوادم الويب وأكثر.

## الخطوة 2: التطبيق

أضف القالب إلى مستودعك. سنستخدم `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

يظهر ملفان جديدان في المستودع: `docker-compose.yml` و`Rediaccfile`. يصف ملف compose الحاويات؛ يُعرّف `Rediaccfile` ما يحدث عند بدء التطبيق وإيقافه (خطافات دورة الحياة `up` و`down`).

## الخطوة 3: التشغيل

أنت داخل صندوق الرمل الخاص بالمستودع (عبر اتصال VS Code من الدرس السابق)، لذا استخدم `renet` مباشرةً:

```bash
time renet dev up
```

هذا كل شيء. تطبيقك يعمل. تحقق منه:

```bash
time docker ps
```

يُدرج `docker ps` هنا حاويات هذا المستودع فقط. تمتلك المستودعات الأخرى على نفس الخادم محركات Docker خاصة بها وهي غير مرئية تمامًا من هنا.

---

التالي: [العمل مع مستودعك](/en/docs/tutorial-work-with-repo).
