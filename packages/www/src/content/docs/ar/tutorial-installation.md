---
title: "التثبيت"
description: "ثبّت أداة rdc CLI على حاسوبك بأمر واحد وتحقق منها باستخدام rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: ar
sourceHash: "99d4ca1a4f89278e"
---

# التثبيت

تثبيت `rdc` يتم في ثلاث خطوات: افتح صفحة التثبيت، اختر نظام تشغيلك، والصق الأمر في الطرفية. تنتهي العملية عادةً في دقيقة أو دقيقتين.

## شاهد الدرس التعليمي

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## الخطوات الثلاث

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. افتح [صفحة التثبيت](/en/install).
2. اختر نظام التشغيل الخاص بك.
3. انسخ أمر التثبيت والصقه في الطرفية.

## التثبيت على منصتك

تقوم صفحة التثبيت بإنشاء الأمر الصحيح لك، لكن إليك الأوامر القياسية المختصرة.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> البادئة `time` خدعة في الصدفة تطبع المدة التي استغرقها الأمر. نستخدمها في هذه السلسلة حتى ترى السرعة الفعلية لكل خطوة. هي اختيارية، احذفها إن لم تحتجها.

## التحقق من التثبيت

بعد انتهاء السكريبت، تحقق من توافر كل ما يحتاجه `rdc`:

```bash
time rdc doctor
```

يمر `rdc doctor` على Node وSSH وبقية متطلبات `rdc` ويُبلّغ عن أي ثغرات.

## لماذا يعيش `rdc` على حاسوبك

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` هي أداة CLI على حاسوبك. يشغّل الخادم مكوّنًا منفصلًا يُسمى `renet`، تقوم `rdc` بتوفيره وتشغيله عبر SSH. لن تحتاج أبدًا للاتصال بالخادم يدويًا عبر SSH؛ `rdc` تفعل ذلك نيابةً عنك.

سنُعدّ ذلك بشكل صحيح في الدرسين التاليين.

---

التالي: [إعداد مفاتيح SSH](/en/docs/tutorial-ssh-keys).
