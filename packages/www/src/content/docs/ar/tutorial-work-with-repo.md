---
title: "العمل مع مستودعك"
description: "أحِل منفذًا إلى متصفحك، ونفّذ أوامر داخل صندوق الرمل، وزامن الملفات بين حاسوبك والمستودع."
category: "Tutorials"
subcategory: essentials
order: 6
language: ar
sourceHash: "3d56eb69e72c1a5a"
---

# العمل مع مستودعك

تطبيقك يعمل، لكنك حتى الآن لم تره إلا من خلال `docker ps`. تغطي ثلاثة أوامر سير العمل اليومي: **tunnel** لرؤية التطبيق في المتصفح، **term** لتنفيذ الأوامر داخل صندوق الرمل، **sync** لنقل الملفات بين حاسوبك والمستودع.

## شاهد الدرس التعليمي

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## الثلاثة اليومية

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: افتح تطبيقك في متصفح.
2. **Term**: نفّذ أمرًا داخل صندوق الرمل.
3. **Sync**: انقل الملفات داخلًا وخارجًا.

## Tunnel: رؤية تطبيقك في المتصفح

يعمل التطبيق على الخادم، لا على حاسوبك. أحِل منفذ الحاوية عبر SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

افتح `localhost` في متصفحك. تطبيقك موجود هناك. اضغط `Ctrl+C` عند الانتهاء.

لحاوية مختلفة، غيّر `-c` واختر المنفذ:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: تنفيذ الأوامر داخل المستودع

تخطَّ VS Code عندما تحتاج فقط إلى صدفة:

```bash
rdc term connect -m my-server -r my-app
```

أنت الآن داخل صندوق رمل المستودع. جرّبه:

```bash
time docker ps
```

ترى حاويات `my-app` فقط، نفس العرض الذي ستراه في VS Code.

للأوامر الفردية، استخدم `-c` وتخطَّ الصدفة التفاعلية:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: نقل الملفات بين الحاسوب والمستودع

ادفع مجلدًا من حاسوبك إلى المستودع:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

اسحب الملفات للخلف:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

استعرض أولًا إذا لم تكن متأكدًا. يُظهر `--dry-run` ما سيتغير دون نسخ فعلي:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel وterm وsync. ثلاثة أوامر تغطي الحلقة اليومية.

---

التالي: [نسخ مستودع](/en/docs/tutorial-forking).
