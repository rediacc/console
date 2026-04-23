---
title: امان الحساب وAPI
description: المصادقة ورموز API وادارة الجلسات ونموذج الصلاحيات.
category: Guides
order: 13
language: ar
sourceHash: "c4e24e7a3494b6f6"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

### المصادقة

يدعم Rediacc طرق مصادقة متعددة:

![Auth Flow](/img/account-auth-flow.svg)

- **كلمة المرور**: تسجيل الدخول التقليدي بالبريد الالكتروني وكلمة المرور
- **Magic Link**: تسجيل دخول بدون كلمة مرور عبر رابط بالبريد الالكتروني (ينتهي خلال 15 دقيقة)
- **المصادقة الثنائية (2FA)**: قائمة على TOTP مع رموز احتياطية

عند تفعيل المصادقة الثنائية، يتطلب تسجيل الدخول كلمة المرور (او Magic Link) ورمز TOTP المكون من 6 ارقام.

### رموز API

تقوم رموز API بمصادقة العمليات بين الاجهزة (تنشيط ترخيص CLI، فحوصات الحالة).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**النطاقات:**
- `license:read` -- الاستعلام عن حالة الاشتراك والترخيص
- `license:activate` -- تنشيط الاجهزة واصدار تراخيص المستودعات
- `subscription:read` -- قراءة تفاصيل الاشتراك

**ميزات الامان:**
- ربط IP: يقوم الطلب الاول بقفل الرمز على عنوان IP هذا
- نطاق الفريق: يمكن تقييد الرموز بفريق محدد
- الالغاء التلقائي: يتم الغاء الرموز عند ازالة المنشئ من المؤسسة

انشاء رمز:
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### تدفق رمز الجهاز

يمكن لـ CLI المصادقة على الاجهزة بدون شاشة باستخدام تدفق رمز الجهاز:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

للتكوين المشفر والمتزامن مع الخادم، راجع [Config Storage](/en/docs/config-storage) للدليل الكامل. يستخدم Config Storage:
- تشفير بدون معرفة (الخادم لا يرى النص العادي ابدا)
- اشتقاق المفاتيح القائم على Passkey (WebAuthn + PRF)
- رموز دوارة مع تدوير لكل طلب

### امان الجلسة

| نوع الرمز | مدة الصلاحية | التخزين | التحديث |
|-----------|-------------|---------|---------|
| Access Token (JWT) | 15 دقيقة | HttpOnly cookie | تلقائي عبر refresh token |
| Refresh Token | 7 ايام | HttpOnly cookie | يتم التدوير عند كل استخدام |
| Elevated Session | 10 دقائق | جانب الخادم | يتم تشغيله بواسطة اعادة المصادقة |

الجلسات المرتفعة مطلوبة للعمليات الحساسة: تغيير كلمة المرور، تغيير البريد الالكتروني، اعداد المصادقة الثنائية، نقل الملكية، والاجراءات الادارية المدمرة.

### نموذج الصلاحيات

يستخدم Rediacc ثلاث طبقات صلاحيات مستقلة:

![Permission Flow](/img/account-permission-flow.svg)

**الطبقة 1: دور النظام** -- يحدد الوصول الى نقاط نهاية ادارة النظام.

**الطبقة 2: دور المؤسسة** -- يتحكم فيما يمكن للمستخدم القيام به داخل مؤسسته (owner، admin، member).

**الطبقة 3: دور الفريق** -- يحدد نطاق الوصول الى موارد فريق معين (team_admin، member). يتجاوز مالكو ومديرو المؤسسة فحوصات دور الفريق.

يمر كل طلب API عبر جميع الطبقات المطبقة بالتسلسل. يجب ان يستوفي الطلب الى نقطة نهاية محددة بنطاق الفريق مصادقة الجلسة وعضوية المؤسسة والوصول الى الفريق.

### قنوات التحديث

يدعم CLI قناتي اصدار:
- **stable** (الافتراضي): تمت الترقية من edge بعد فترة نقع لمدة 7 أيام؛ اختر هذه القناة للحصول على وتيرة ترقية محافظة
- **edge**: احدث الميزات، يتم التحديث عند كل اصدار

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
