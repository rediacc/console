---
title: "نسخ مستودع"
description: "انسخ مستودعًا كاملًا (التطبيق وقاعدة البيانات والملفات) في ثوانٍ. بأي حجم. دون قرص إضافي."
category: "Tutorials"
subcategory: advanced
order: 7
language: ar
sourceHash: "9237f00dce2ee5ec"
---

# نسخ مستودع

هذه هي الميزة الجوهرية: نسخ بيئة إنتاجية كاملة (التطبيق وقاعدة البيانات وملفات الإعداد) في ثوانٍ. بأي حجم. دون قرص إضافي. انسخ كما تشاء.

الشعار: **انسخ الإنتاج، دون أي خسارة.**

## شاهد الدرس التعليمي

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## جهّز شيئًا للمخاطرة به

أولًا، أضف ملفًا للتطبيق الجاري حتى تتمكن من إثبات عزل النسخة. افتح المستودع في VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

داخل المستودع، أنشئ ملف علامة:

```bash
time echo "Hello from production" > index.html
```

الآن انسخه.

## النسخ

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

أمر واحد. نسخ كل شيء (التطبيق وقاعدة البيانات وملفات الإعداد) وحدث ذلك في ثوانٍ. شغّله مرة أخرى وتحصل على نسخة مستقلة أخرى.

## لماذا هو سريع جدًا؟

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

تخيّل مشاركة رابط مجلد. الرابط هو نفسه سواء كان المجلد صغيرًا أو ضخمًا. المجلد ثقيل، الرابط خفيف.

![1 GB, 100 GB, 1 TB. Same time, every time.](/img/tutorials/tutorial-forking/slide-3.svg)

النسخ يعمل بالطريقة نفسها. 1 جيجابايت، 100 جيجابايت، 1 تيرابايت. نفس الوقت، في كل مرة.

## ما هو مشترك، وما هو لك

![Many mirrors, one sun: shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

فكّر في المستودع الأصل كالشمس. لا يمكنك الإمساك بالشمس، لكن يمكنك الإمساك بمرآة تعكسها. تلك المرآة هي نسختك. ارسم على المرآة ورسوماتك ملكك. تبقى الشمس كما هي، مهما كان عدد المرايا التي تواجهها.

> لا يمكنك الإمساك بالشمس، لكن يمكنك رؤيتها في مرآة.

## ماذا لو تغيّر الأصل لاحقًا؟

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

الآن فكّر في نهر. الماء يتدفق باستمرار. كل لحظة مختلفة عن التي قبلها. عندما تنسخ، تلتقط صورة للنهر مجمّدة في تلك اللحظة. النهر يواصل تدفقه. صورتك لا تتغير.

إذا تغيّر المستودع الأصل لاحقًا، تبقى نسختك في مكانها.

> لا يمكنك الإمساك بنهر، لكن يمكنك الإمساك به في صورة.

## استخدام القرص يبقى ثابتًا

![Five forks of a 100 GB repo, still about 100 GB total](/img/tutorials/tutorial-forking/slide-6.svg)

لهذا السبب لا ينفجر قرصك. خمس نسخ من مستودع 100 جيجابايت؟ لا تزال حوالي 100 جيجابايت إجمالًا. تدفع قرصًا فقط لما تغيّره في كل نسخة.

> انسخ خمس مرات إذا أردت. قرصك لن يلاحظ حتى.

## ما لا ترثه النسخ: الأسرار

هناك شيء واحد لا تتبعه النسخة عن قصد: الأسرار. تبدأ النسخة بدون مفاتيح API، دون كلمات مرور قواعد البيانات، دون رموز Stripe. لهذا السبب يعمل شعار "انسخ الإنتاج، دون أي خسارة" بالفعل. لا يمكن لصندوق الرمل الخاص بك محاسبة عملاء حقيقيين لأنه لا يستطيع التظاهر بأنه أنت. سنُعدّ ذلك بشكل صحيح في درس [إدارة الأسرار](/en/docs/tutorial-managing-secrets).

## التحقق من العزل

أدرج المستودعين جنبًا إلى جنب:

```bash
time rdc repo list -m my-server
```

ستجد `my-app` و`my-app:experiment` يعملان بالتزامن.

في المستودع الأصلي، تحقق مما يعمل:

```bash
time docker ps
```

لاحظ وقت التشغيل. هذه هي الحاويات الأصلية. الآن انتقل إلى النسخة:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

نفس الصور، لكن وقت التشغيل جديد. بدأت هذه عندما بدأت النسخة.

اجعل الفرق أكثر وضوحًا. أضف حاوية فقط إلى النسخة:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx يعمل، لكن فقط داخل هذه النسخة.

جرّب شيئًا تدميريًا:

```bash
time rm index.html
```

اختفى هنا. الآن ارجع إلى الأصلي:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

لا nginx. بقيت حاويات النسخة في النسخة. و`index.html` لا يزال هنا سليمًا. لم يعلم الأصلي بأي شيء حدث. نفس الصور، محركات Docker منفصلة، أنظمة ملفات منفصلة.

## التنظيف

عند الانتهاء، احذف النسخة فقط:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

يبقى الأصل كما كان تمامًا. **انسخ، وجرّب، وكسّر الأشياء، واحذف.** دون أي خطر.

---

التالي: [إدارة الأسرار](/en/docs/tutorial-managing-secrets).
