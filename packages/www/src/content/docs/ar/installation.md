---
title: "التثبيت"
description: "تثبيت سطر أوامر Rediacc على Linux أو macOS أو Windows."
category: "Guides"
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

## Windows

شغّل سكريبت التثبيت في PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

يُنزل هذا الملف التنفيذي `rdc.exe` إلى `%LOCALAPPDATA%\rediacc\bin\`. تأكد من أن هذا المجلد موجود في PATH. سيطلب منك المُثبِّت إضافته إذا لم يكن موجوداً بالفعل.

## ألباين لينكس (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

ملاحظة: يتم تثبيت حزمة `gcompat` (طبقة التوافق مع glibc) تلقائيًا كتبعية.

## آرتش لينكس (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
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
