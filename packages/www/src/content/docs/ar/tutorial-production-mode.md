---
title: "وضع الإنتاج"
description: "شغّل تطبيقك منفصلًا عن حاسوبك وتحمّل إعادة تشغيل الخادم مع التشغيل التلقائي."
category: "Tutorials"
subcategory: advanced
order: 10
language: ar
sourceHash: "0e070fcd877900ab"
---

# وضع الإنتاج

حتى الآن كنت تشغّل التطبيق بـ`renet dev up` من داخل المستودع. هذا رائع للتطوير. للإنتاج، تدير كل شيء من حاسوبك عبر `rdc`. أغلق حاسوبك والتطبيق يواصل العمل.

## شاهد الدرس التعليمي

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## التطوير مقابل الإنتاج

الفرق بسيط:

- `renet dev up` يعمل **من داخل المستودع**. تحتاج إلى أن تكون متصلًا.
- `rdc repo up` يعمل **من حاسوبك**. لا اتصال مطلوب بعد ذلك.

ثلاثة إجراءات تنقلك من التطوير إلى الإنتاج:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## الخطوة 1: إيقاف جلسة التطوير

اتصل بالمستودع وأوقفه:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## الخطوة 2: البدء في وضع الإنتاج

من طرفية حاسوبك:

```bash
time rdc repo up --name my-app -m my-server
```

هذا كل شيء. تطبيقك يعمل ويمكنك إغلاق حاسوبك. يتولى `Rediaccfile` كل شيء. يستدعي `rdc repo up` نفس دالة `up` التي استدعاها `renet dev up`. نفس `Rediaccfile`، طريقة استدعاء مختلفة.

## الخطوة 3: التعامل مع إعادة تشغيل الخادم

تأكد من أن تطبيقك يعود تلقائيًا عند إعادة تشغيل الخادم:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

تحقق من المستودعات التي لديها تشغيل تلقائي مُفعَّل:

```bash
time rdc repo autostart list -m my-server
```

## الإيقاف في الإنتاج

عندما تحتاج لإيقاف تطبيقك:

```bash
time rdc repo down --name my-app -m my-server
```

أمر واحد للتشغيل، أمر واحد للإيقاف. كل شيء من حاسوبك.

---

التالي: [النسخ الاحتياطي والاستعادة](/en/docs/tutorial-backup-restore).
