---
title: الأدوات
description: مزامنة الملفات والوصول عبر SSH وتكامل VS Code وتحديثات CLI.
category: Guides
order: 9
language: ar
sourceHash: "4b3aebff5e82416f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# الأدوات

يوفر Rediacc أربع أدوات للعمل اليومي على آلاتك ومستودعاتك: مزامنة الملفات عبر SSH، طرفية SSH، تكامل VS Code، وتحديثات واجهة سطر الأوامر. جميع هذه الأدوات تعمل عبر SSH. لا يلزم أي عامل أو daemon على الجانب البعيد. إذا كنت تبحث عن واجهة رسومية، فأنت في الصفحة الخاطئة.

## مزامنة الملفات (sync)

نقل الملفات بين جهاز العمل الخاص بك ومستودع بعيد باستخدام rsync عبر SSH.

### رفع الملفات

يقبل `--local` مسارًا واحدًا أو أكثر. قد يكون كل مسار ملفًا أو مجلدًا. تُنزل الملفات في `<remote>/<basename>`؛ محتويات المجلد تندمج في `<remote>/`. لملف واحد، يُفضل استخدام `--remote-file` لتحديد مسار الوجهة بوضوح.

```bash
# Directory (contents merged into remote)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Single file dropped into a remote directory (basename preserved)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Single file, explicit destination path
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Multiple sources in one call
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` و `--remote-file` متنافيتان. يتطلب `--remote-file` مسار `--local` واحد بالضبط يشير إلى ملف.

لا يمكن دمج `--mirror` مع مصدر ملف؛ سيحذف الملفات الشقيقة في المجلد البعيد.

### تنزيل الملفات

استخدم `--remote` للمجلد (الافتراضي) أو `--remote-file` لملف واحد. الرايتان متنافيتان.

```bash
# Directory
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Single file — --local must be an existing directory
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### التحقق من حالة المزامنة

```bash
rdc repo sync status -m server-1 -r my-app
```

### الخيارات

| Option | الوصف |
|--------|-------------|
| `-m, --machine <name>` | الجهاز المستهدف |
| `-r, --repository <name>` | المستودع المستهدف |
| `--local <paths...>` | مسار واحد أو أكثر لملف أو مجلد محلي (رفع) أو مجلد الوجهة المحلي (تنزيل) |
| `--remote <path>` | مجلد بعيد (نسبي إلى نقطة تحميل المستودع) |
| `--remote-file <path>` | مسار ملف بعيد لعمليات الرفع أو التنزيل الفردية (بديل لـ `--remote`) |
| `--dry-run` | معاينة التغييرات دون نقل الملفات |
| `--mirror` | مطابقة المصدر مع الوجهة، حذف الملفات الزائدة (مصادر المجلدات فقط) |
| `--verify` | التحقق من المجاميع الاختبارية بعد النقل |
| `--confirm` | تأكيد تفاعلي مع عرض التفاصيل |
| `--exclude <patterns...>` | استثناء أنماط الملفات |
| `--skip-router-restart` | تخطي إعادة تشغيل خادم التوجيه بعد العملية |

## طرفية SSH (term)

فتح جلسة SSH تفاعلية للاتصال بجهاز أو الدخول إلى بيئة مستودع.

### الصيغة المختصرة

أسرع طريقة للاتصال:

```bash
rdc term connect -m server-1                    # الاتصال بجهاز
rdc term connect -m server-1 -r my-app             # الاتصال بمستودع
```

### تنفيذ أمر

تنفيذ أمر دون فتح جلسة تفاعلية:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

عند الاتصال بمستودع، يتم تعيين `DOCKER_HOST` تلقائيًا إلى مقبس Docker المعزول الخاص بالمستودع، لذا فإن `docker ps` يعرض حاويات ذلك المستودع فقط.

### الأمر الفرعي connect

أو استخدم الأمر الفرعي `connect` للحصول على نفس النتيجة، مع رايات صريحة:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### إجراءات الحاويات

التفاعل مباشرة مع حاوية قيد التشغيل:

```bash
# Open a shell inside a container
rdc term connect -m server-1 -r my-app --container <container-id>

# View container logs
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Follow logs in real-time
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# View container stats
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Execute a command in a container
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| Option | الوصف |
|--------|-------------|
| `--container <id>` | معرّف حاوية Docker المستهدفة |
| `--container-action <action>` | الإجراء: `terminal` (افتراضي)، `logs`، `stats`، `exec` |
| `--log-lines <n>` | عدد أسطر السجل المعروضة (الافتراضي: 50) |
| `--follow` | متابعة السجلات بشكل مستمر |
| `--external` | استخدام طرفية خارجية بدلاً من SSH المضمّن |

## تكامل VS Code (vscode)

فتح جلسة SSH عن بُعد في VS Code، مُعدّة مسبقًا بإعدادات SSH الصحيحة.

### الاتصال بمستودع

```bash
rdc vscode connect -r my-app -m server-1
```

يقوم هذا الأمر بما يلي:
1. اكتشاف تثبيت VS Code الخاص بك
2. تكوين اتصال SSH في `~/.ssh/config`
3. حفظ مفتاح SSH للجلسة
4. فتح VS Code مع اتصال Remote SSH إلى مسار المستودع

### عرض الاتصالات المُعدّة

```bash
rdc vscode list
```

### تنظيف الاتصالات

```bash
rdc vscode cleanup
```

إزالة تكوينات SSH الخاصة بـ VS Code التي لم تعد مطلوبة.

### فحص التكوين

```bash
rdc vscode check
```

التحقق من تثبيت VS Code، وإضافة Remote SSH، والاتصالات النشطة.

> **متطلب مسبق:** قم بتثبيت إضافة [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) في VS Code.

## تحديثات واجهة سطر الأوامر (update)

الحفاظ على تحديث واجهة سطر الأوامر `rdc`.

### التحقق من التحديثات

```bash
rdc update --check-only
```

### تطبيق التحديث

```bash
rdc update
```

يتم تنزيل التحديثات وتطبيقها في مكانها. تختار واجهة سطر الأوامر تلقائيًا الملف الثنائي المناسب لمنصتك (Linux أو macOS أو Windows). يسري الإصدار الجديد عند التشغيل التالي.

### التراجع

```bash
rdc update --rollback
```

العودة إلى الإصدار المثبت سابقًا. متاح فقط بعد تطبيق تحديث.

### حالة التحديث

```bash
rdc update --status
```

عرض الإصدار الحالي وقناة التحديث وتكوين التحديث التلقائي.

#### قنوات الإصدار

```bash
rdc update --channel edge      # التحديثات المنشورة بشكل مستمر للإنتاج
rdc update --channel stable    # الإصدارات المعززة من edge بعد 7 أيام من التثبيت (الافتراضي)
rdc update --status            # عرض القناة الحالية ومعلومات الإصدار
```
