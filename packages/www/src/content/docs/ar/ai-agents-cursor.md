---
title: دليل إعداد Cursor
description: تهيئة بيئة تطوير Cursor للعمل مع بنية Rediacc التحتية باستخدام .cursorrules وتكامل الطرفية.
category: Guides
order: 32
language: ar
sourceHash: "6da857eb870d511e"
---

يتكامل Cursor مع Rediacc من خلال أوامر الطرفية وملف التهيئة `.cursorrules`.

## الإعداد السريع

1. ثبّت أداة CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. انسخ [قالب AGENTS.md](/ar/docs/agents-md-template) إلى جذر مشروعك كملف `.cursorrules`
3. افتح المشروع في Cursor

يقرأ Cursor ملف `.cursorrules` عند بدء التشغيل ويستخدمه كسياق للتطوير بمساعدة الذكاء الاصطناعي.

## تهيئة .cursorrules

أنشئ ملف `.cursorrules` في جذر مشروعك مع سياق بنية Rediacc التحتية. راجع [قالب AGENTS.md](/ar/docs/agents-md-template) الكامل للحصول على النسخة الكاملة.

الأقسام الرئيسية التي يجب تضمينها:

- اسم أداة CLI (`rdc`) والتثبيت
- الأوامر الشائعة مع علم `--output json`
- نظرة عامة على البنية (عزل المستودعات، Docker daemons)
- قواعد المصطلحات (محولات، وليس أوضاع)

## تكامل الطرفية

يمكن لـ Cursor تنفيذ أوامر `rdc` من خلال طرفيته المدمجة. الأنماط الشائعة:

### فحص الحالة

اسأل Cursor: *"تحقق من حالة خادم الإنتاج"*

يُنفّذ Cursor في الطرفية:
```bash
rdc machine info prod-1 -o json
```

### نشر التغييرات

اسأل Cursor: *"انشر تهيئة nextcloud المحدّثة"*

يُنفّذ Cursor في الطرفية:
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### عرض السجلات

اسأل Cursor: *"أرني سجلات حاوية mail الأخيرة"*

يُنفّذ Cursor في الطرفية:
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
```

## إعدادات مساحة العمل

للمشاريع الجماعية، أضف إعدادات Cursor الخاصة بـ Rediacc إلى `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## نصائح

- وضع Composer في Cursor يعمل بشكل جيد للمهام التحتية متعددة الخطوات
- استخدم `@terminal` في محادثة Cursor للإشارة إلى مخرجات الطرفية الأخيرة
- يمنح أمر `rdc agent capabilities` لـ Cursor مرجعًا كاملاً للأوامر
- ادمج `.cursorrules` مع ملف `CLAUDE.md` لتحقيق أقصى توافق عبر أدوات الذكاء الاصطناعي
