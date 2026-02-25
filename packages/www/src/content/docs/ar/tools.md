---
title: الأدوات
description: مزامنة الملفات، والوصول عبر الطرفية، وتكامل VS Code، والتحديثات، والتشخيصات.
category: Guides
order: 9
language: ar
sourceHash: 80ca3cd3e1a55d4b
---

# الأدوات

يتضمن Rediacc أدوات إنتاجية للعمل مع المستودعات البعيدة: مزامنة الملفات، وطرفية SSH، وتكامل VS Code، وتحديثات واجهة سطر الأوامر.

## مزامنة الملفات (sync)

نقل الملفات بين جهاز العمل الخاص بك ومستودع بعيد باستخدام rsync عبر SSH.

### رفع الملفات

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### تنزيل الملفات

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### التحقق من حالة المزامنة

```bash
rdc sync status -m server-1 -r my-app
```

### الخيارات

| Option | الوصف |
|--------|-------------|
| `-m, --machine <name>` | الجهاز المستهدف |
| `-r, --repository <name>` | المستودع المستهدف |
| `--local <path>` | مسار المجلد المحلي |
| `--remote <path>` | المسار البعيد (نسبي إلى نقطة تحميل المستودع) |
| `--dry-run` | معاينة التغييرات دون نقل الملفات |
| `--mirror` | مطابقة المصدر مع الوجهة (حذف الملفات الزائدة) |
| `--verify` | التحقق من المجاميع الاختبارية بعد النقل |
| `--confirm` | تأكيد تفاعلي مع عرض التفاصيل |
| `--exclude <patterns...>` | استثناء أنماط الملفات |
| `--skip-router-restart` | تخطي إعادة تشغيل خادم التوجيه بعد العملية |

## طرفية SSH (term)

فتح جلسة SSH تفاعلية للاتصال بجهاز أو الدخول إلى بيئة مستودع.

### الصيغة المختصرة

أسرع طريقة للاتصال:

```bash
rdc term server-1                    # الاتصال بجهاز
rdc term server-1 my-app             # الاتصال بمستودع
```

### تنفيذ أمر

تنفيذ أمر دون فتح جلسة تفاعلية:

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

عند الاتصال بمستودع، يتم تعيين `DOCKER_HOST` تلقائيًا إلى مقبس Docker المعزول الخاص بالمستودع، لذا فإن `docker ps` يعرض حاويات ذلك المستودع فقط.

### الأمر الفرعي connect

يوفر الأمر الفرعي `connect` نفس الوظيفة مع خيارات صريحة:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### إجراءات الحاويات

التفاعل مباشرة مع حاوية قيد التشغيل:

```bash
# Open a shell inside a container
rdc term server-1 my-app --container <container-id>

# View container logs
rdc term server-1 my-app --container <container-id> --container-action logs

# Follow logs in real-time
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# View container stats
rdc term server-1 my-app --container <container-id> --container-action stats

# Execute a command in a container
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
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
rdc vscode connect my-app -m server-1
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
rdc vscode clean
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
rdc update rollback
```

العودة إلى الإصدار المثبت سابقًا. متاح فقط بعد تطبيق تحديث.

### حالة التحديث

```bash
rdc update status
```

عرض الإصدار الحالي، وقناة التحديث، وتكوين التحديث التلقائي.
