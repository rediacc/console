---
title: "التثبيت"
description: "تثبيت سطر أوامر Rediacc على Linux أو macOS أو Windows."
category: "Getting Started"
order: 1
language: ar
---

# التثبيت

ثبّت سطر أوامر `rdc` على محطة عملك. هذه هي الأداة الوحيدة التي تحتاج لتثبيتها يدوياً — كل شيء آخر يُعالج تلقائياً عند إعداد الأجهزة البعيدة.

## Linux و macOS

شغّل سكريبت التثبيت:

```bash
curl -fsSL https://get.rediacc.com | sh
```

يقوم هذا بتنزيل ملف `rdc` التنفيذي إلى `$HOME/.local/bin/`. تأكد من أن هذا المجلد موجود في متغير PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

أضف هذا السطر إلى ملف تعريف الصدفة الخاص بك (`~/.bashrc` أو `~/.zshrc` وغيرها) لجعله دائماً.

## Windows (WSL2)

يعمل Rediacc داخل WSL2 على Windows. إذا لم يكن WSL2 مُعداً لديك:

```powershell
wsl --install
```

ثم داخل توزيعة Linux على WSL2، شغّل نفس سكريبت التثبيت:

```bash
curl -fsSL https://get.rediacc.com | sh
```

## التحقق من التثبيت

```bash
rdc --version
```

يجب أن ترى رقم الإصدار المثبّت.

## التحديث

لتحديث `rdc` إلى أحدث إصدار:

```bash
rdc update
```

للتحقق من وجود تحديثات بدون تثبيتها:

```bash
rdc update --check-only
```

للتراجع إلى الإصدار السابق بعد التحديث:

```bash
rdc update rollback
```
