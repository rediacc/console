---
title: "إنشاء مستودعك الأول"
description: "أنشئ مستودعًا مشفرًا على خادمك وافتحه في VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: ar
sourceHash: "1294b0494f20671b"
---

# إنشاء مستودعك الأول

مستودع Rediacc هو ملف مشفر واحد على خادمك. عند تحميله، يصبح مجلدًا بمحرك Docker خاص به وبيانات تطبيق خاصة به: معزول تمامًا وقابل للنقل بالكامل.

فكّر فيه كمحرك USB للإنتاج: ملف في حالة السكون، وخادم في حالة التشغيل.

## شاهد الدرس التعليمي

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## ملف على القرص، بيئة عند التحميل

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

الشكل على القرص هو صورة مشفرة واحدة. عند التحميل، تحصل على:

- محرك Docker مخصص (منفصل عن محرك المضيف)
- بيانات التطبيق داخل الحجم المشفر
- عناوين IP الاسترجاعية التي لا تتعارض مع أي شيء آخر على الخادم

المستودعات قابلة للنقل. يمكنك نقل مستودع بين أجهزة أو نسخه احتياطيًا أو نسخه فوريًا. كل مستودع معزول عن أي مستودع آخر على نفس الخادم.

## إنشاء مستودع

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

يُنشئ هذا الأمر مستودعًا مشفرًا بحجم 2 جيجابايت على `my-server`. تحقق منه:

```bash
time rdc repo list -m my-server
```

## فتحه في VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

يفتح VS Code مباشرةً داخل المستودع. لاحظ أن مساحة العمل فارغة. هذه بيئتك المعزولة. كل ما تنشئه هنا يعيش داخل الحجم المشفر، وهو غير مرئي لأي مستودع آخر على نفس الخادم.

---

التالي: [نشر تطبيقك الأول](/en/docs/tutorial-deploy-app).
