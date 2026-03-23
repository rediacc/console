---
title: "Config Storage (Rediacc Provider)"
description: "مزامنة تكوين CLI بشكل آمن عبر الأجهزة والفرق مع تشفير المعرفة الصفرية."
category: "Guides"
order: 9
language: ar
---

# Config Storage

يقوم مزود تخزين التكوين Rediacc بمزامنة تكوين CLI عبر الأجهزة والفرق مع تشفير المعرفة الصفرية. يتم تشفير مفاتيح SSH وعناوين IP للأجهزة وبيانات الاعتماد من جانب العميل قبل مغادرة جهازك -- حتى مشغلو Rediacc لا يمكنهم قراءة بياناتك.

## المتطلبات الأساسية

- **مزود Passkey مع دعم PRF**: Bitwarden أو iCloud Keychain أو Windows Hello
- **تفعيل المصادقة الثنائية** لمالكي/مسؤولي المؤسسة (مطلوب لإعداد المتجر وإدارة الأعضاء)
- **اشتراك حساب** مع تفعيل config storage

## البداية السريعة

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## الإعداد

### سطح المكتب (مع متصفح)

```bash
rdc store add my-config --type rediacc
```

1. تفتح نافذة متصفح إلى بوابة حساب Rediacc
2. سجّل passkey (نافذة منبثقة من Bitwarden/iCloud/Windows Hello)
3. يشتق امتداد PRF الخاص بـ passkey مفاتيح التشفير الخاصة بك
4. يتم تخزين المفاتيح في التخزين الآمن الأصلي لنظام التشغيل (Keychain/keyctl/DPAPI)
5. تم -- لا توجد كلمة مرور للتذكر

### خوادم بدون واجهة (بدون متصفح)

```bash
rdc store add my-config --type rediacc --headless
```

1. يعرض CLI عنوان URL مع رمز الجهاز
2. افتح العنوان على هاتفك أو حاسوبك المحمول
3. أكمل تسجيل passkey في المتصفح
4. يستقبل CLI تلقائياً مفاتيحك المشفرة عبر مرحل آمن
5. المعرفة الصفرية محفوظة -- الخادم يرحل فقط blob مشفر معتم

### عنوان خادم مخصص

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

بعد الإعداد، يعمل push وpull بدون أي كلمات مرور أو مطالبات:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

كل عملية تستخدم رمزاً دوّاراً يدمر نفسه بعد استخدام واحد. لا توجد بيانات اعتماد ثابتة.

## إدارة الفريق

تتم إدارة أعضاء الفريق من خلال بوابة الويب على `/account/config-storage/members`.

### إضافة أعضاء

1. يفتح المسؤول صفحة أعضاء config storage
2. ينقر على "Add Member" (يتطلب المصادقة الثنائية)
3. يقوم متصفح المسؤول بتشفير مفتاح تشفير الفريق للعضو الجديد
4. يسجل العضو الجديد دخوله ويقبل الدعوة
5. يمكن لكليهما الآن عمل push/pull لنفس التكوينات

### إزالة أعضاء

1. ينقر المسؤول على "Remove" بجانب العضو (يتطلب المصادقة الثنائية)
2. يتم حذف مفاتيح تشفير العضو فوراً
3. خلال 30 ثانية، يفقد العضو كل الوصول إلى التكوينات المشفرة

لا حاجة لتدوير المفاتيح -- يتوقف الخادم ببساطة عن تقديم مفاتيح فك التشفير للعضو المُزال.

## خصائص الأمان

| الخاصية | الطريقة |
|---------|---------|
| **المعرفة الصفرية** | العميل يشفر قبل الإرسال؛ الخادم يرى فقط blobs معتمة |
| **بدون كلمة مرور رئيسية** | المقاييس الحيوية للـ passkey تحل محل كلمات المرور بالكامل |
| **اشتقاق مفتاح مقسم** | CEK يتطلب كلاً من passkey_secret (العميل) + server_secret (الخادم) |
| **رموز دوّارة** | كل استدعاء API يولد رمزاً جديداً؛ القديمة تنتهي |
| **ربط IP** | الرموز مرتبطة بـ IP العميل عند الاستخدام الأول |
| **تشفير ثلاثي** | SDK (نافذة زمنية) + CEK (العميل) + عبارة المؤسسة (الخادم) |
| **إلغاء فوري** | إيقاف تقديم SDK للأعضاء المُزالين؛ تأخير أقصى 30 ثانية |
| **كشف التلاعب** | HMAC على blobs المشفرة؛ يتم التحقق في كل pull |

للاطلاع على معمارية الأمان الكاملة، راجع [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## استكشاف الأخطاء وإصلاحها

### "Passkey must support PRF extension"

مزود passkey الخاص بك لا يدعم امتداد PRF. استخدم:
- Bitwarden (تطبيق سطح المكتب أو إضافة المتصفح)
- iCloud Keychain (Safari على macOS/iOS)
- Windows Hello

### "Two-factor authentication required"

يجب على مالكي ومسؤولي المؤسسة تفعيل المصادقة الثنائية قبل إعداد config storage. اذهب إلى Account Settings -> Security -> Enable 2FA.

### "Version conflict"

عضو آخر في الفريق دفع نسخة أحدث. اسحب أولاً:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

تنتهي صلاحية الرموز بعد 24 ساعة من عدم النشاط. شغّل أي أمر للتحديث:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

فُقد مفتاح التشفير من التخزين الآمن لنظام التشغيل (إعادة تشغيل على Linux، إعادة تعيين keychain). أعد تشغيل الإعداد:
```bash
rdc store add my-config --type rediacc
```
