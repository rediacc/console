---
title: "التثبيت"
description: "قم بتثبيت واجهة سطر أوامر Rediacc على Linux أو macOS أو Windows."
category: "Guides"
order: 1
language: ar
sourceHash: "2651baa400d94f8c"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# التثبيت

قم بتثبيت واجهة سطر الأوامر `rdc` على محطة العمل الخاصة بك. هذه هي الأداة الوحيدة التي تحتاج إلى تثبيتها يدويًا -- يتم التعامل مع كل شيء آخر تلقائيًا عند إعداد الأجهزة البعيدة.

## التثبيت السريع

### Linux و macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

يقوم هذا الأمر بتنزيل ملف `rdc` الثنائي إلى `$HOME/.local/bin/`. تأكد من أن هذا المجلد موجود في PATH الخاص بك:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

أضف هذا السطر إلى ملف تعريف shell الخاص بك (`~/.bashrc`، `~/.zshrc`، إلخ) لجعله دائمًا.

### Windows

قم بالتشغيل في PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

يقوم هذا الأمر بتنزيل `rdc.exe` إلى `%LOCALAPPDATA%\rediacc\bin\`. سيطلب منك المثبّت إضافته إلى PATH إذا لزم الأمر.

## مديرو الحزم

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / متوافق مع RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

تستخدم Oracle Linux وAlmaLinux وRocky Linux نفس مسار DNF؛ يمكن لأي توزيعة متوافقة مع RHEL تحتوي على `dnf` سحب المستودع أعلاه. ملاحظة: **Oracle Linux 10 هي التوزيعة الوحيدة من عائلة RHEL المدعومة رسميًا كهدف خادم Rediacc** (انظر [المتطلبات](/en/docs/requirements)). تفتقر Rocky/Alma 10 إلى وحدة نواة btrfs اللازمة لمستوى بيانات renet، وإن كان `rdc` CLI يُثبَّت عليها بشكل سليم.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

تم الاختبار على openSUSE Leap 16.0 وما فوق.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

ملاحظة: يتم تثبيت حزمة `gcompat` (طبقة التوافق مع glibc) تلقائيًا كتبعية.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

قم بسحب وتشغيل واجهة سطر الأوامر كحاوية:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

أنشئ اسمًا مستعارًا للراحة:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

علامات Docker المتاحة:

| العلامة | الوصف |
|---------|-------|
| `:stable` | أحدث إصدار مستقر (مُوصى به) |
| `:edge` | أحدث إصدار edge |
| `:0.8.4` | إصدار مثبّت (غير قابل للتغيير) |
| `:latest` | اسم مستعار لـ `:stable` |

## التحقق من التثبيت

```bash
rdc --version
```

## التحديث

التحديث إلى أحدث إصدار:

```bash
rdc update
```

التحقق من التحديثات دون التثبيت:

```bash
rdc update --check-only
```

عرض حالة التحديث الحالية:

```bash
rdc update --status
```

الرجوع إلى الإصدار السابق:

```bash
rdc update --rollback
```

## قنوات الإصدار

يستخدم Rediacc نظام إصدار قائم على القنوات. تحدد القناة الإصدار الذي تتلقاه لتحديثات CLI وعمليات تثبيت مدير الحزم وسحب Docker.

| القناة | الوصف | متى يتم التحديث |
|--------|-------|------------------|
| `stable` | إصدارات جاهزة للإنتاج | يتم الترقية من edge بعد فترة اختبار 7 أيام |
| `edge` | أحدث الميزات والإصلاحات | عند كل دمج في main |
| `pr-N` | بناءات معاينة PR | تلقائيًا لكل pull request |

### تبديل القنوات

```bash
rdc update --channel edge      # التبديل إلى قناة edge
rdc update --channel stable    # العودة إلى قناة stable
```

التثبيت مباشرة من قناة edge:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

لمديري الحزم، استبدل `stable` بـ `edge` في عنوان URL للمستودع:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### كيف تعمل القنوات

تُطبّق القناة بشكل موحد عبر جميع طرق التوزيع:

- **سكريبتات التثبيت**: متغير البيئة `REDIACC_CHANNEL` يحدد القناة
- **مستودعات الحزم**: `releases.rediacc.com/{التنسيق}/{القناة}/`
- **علامات Docker**: `ghcr.io/rediacc/elite/cli:{القناة}`
- **تحديثات CLI**: يتحقق `rdc update` من القناة المُعدّة أثناء التثبيت

### التكوين التلقائي لمعاينة PR

عند التثبيت من نشر معاينة PR (مثل `pr-420.rediacc.workers.dev`)، يتم تكوين القناة وخادم الحساب تلقائيًا:

- يتم تنزيل ملف CLI الثنائي من قناة `pr-420`
- يتحقق `rdc update` من قناة `pr-420` للتحديثات
- جميع أوامر الحساب/الاشتراك تتصل بخادم معاينة PR
- تعرض أوامر Docker على موقع المعاينة `cli:pr-420`

لا حاجة لتكوين يدوي. يكتشف سكريبت التثبيت سياق النشر من عنوان URL.

## تحديثات الملفات الثنائية البعيدة

عند تشغيل أوامر على جهاز بعيد، تقوم واجهة سطر الأوامر تلقائيًا بتوفير ملف `renet` الثنائي المطابق. إذا تم تحديث الملف الثنائي، يتم إعادة تشغيل خادم المسارات (`rediacc-router`) تلقائيًا لالتقاط الإصدار الجديد.

إعادة التشغيل شفافة ولا تسبب **أي توقف**:

- يُعاد تشغيل خادم المسارات في حوالي 1-2 ثانية.
- خلال تلك الفترة، يستمر Traefik في تقديم حركة المرور باستخدام آخر تكوين توجيه معروف. لا يتم إسقاط أي مسارات.
- يلتقط Traefik التكوين الجديد في دورة الاستطلاع التالية (خلال 5 ثوانٍ).
- **لا تتأثر اتصالات العملاء الحالية (HTTP، TCP، UDP).** خادم المسارات هو مزوّد تكوين -- وليس في مسار البيانات. يتعامل Traefik مع كل حركة المرور مباشرة.
- لا يتم المساس بحاويات التطبيقات الخاصة بك -- يتم إعادة تشغيل عملية خادم المسارات على مستوى النظام فقط.

لتخطي إعادة التشغيل التلقائية، مرّر `--skip-router-restart` إلى أي أمر، أو عيّن متغير البيئة `RDC_SKIP_ROUTER_RESTART=1`.
