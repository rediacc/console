---
title: "إعداد مفاتيح SSH"
description: "اضبط مفتاح SSH الخاص بك حتى تتمكن rdc من الاتصال بخوادمك دون كلمات مرور."
category: "Tutorials"
subcategory: essentials
order: 2
language: ar
sourceHash: "009a1bd345e93413"
---

# إعداد مفاتيح SSH

تتصل `rdc` بخوادمك عبر SSH، لذا يجب أن يثق كل خادم بمفتاح SSH الخاص بك. ثلاث خطوات إجمالًا: خطوتان لمرة واحدة فقط، وخطوة تتكرر مع كل خادم جديد.

## شاهد الدرس التعليمي

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## الخطوات الثلاث

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **أنشئ** مفتاح SSH على حاسوبك. مرة واحدة فقط.
2. **انسخه** إلى خادمك. كرر ذلك مع كل خادم جديد.
3. **سجّله** مع `rdc`. مرة واحدة فقط.

## الخطوة 1: إنشاء مفتاح

إذا كان لديك مفتاح تريد استخدامه، تخطَّ هذه الخطوة. وإلا:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` هو الخيار الحديث الافتراضي: صغير وسريع ومدعوم على نطاق واسع.

## الخطوة 2: نسخ المفتاح إلى خادمك

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

استبدل `user` و`your-server-ip` بمستخدم SSH وعنوان IP الخاص بخادمك. ستُطلب منك كلمة مرور الخادم لآخر مرة. بعد ذلك، لن يكون التحقق بكلمة المرور مطلوبًا.

## الخطوة 3: تسجيل المفتاح مع `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

هذا كل شيء. من الآن فصاعدًا، تتحقق كل أوامر `rdc` باستخدام هذا المفتاح. لا كلمات مرور، لا موجّهات تفاعلية.

---

التالي: [إضافة خادمك الأول](/en/docs/tutorial-add-server).
