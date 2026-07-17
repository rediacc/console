---
title: ورقة مرجعية لـ RDC CLI
description: "مرجع سريع لـ rdc: الإعدادات والمستودعات والأجهزة ومزامنة الملفات والحاويات. للحصول على الخيارات الكاملة، أضف --help إلى أي أمر."
category: Guides
order: 3
language: ar
sourceHash: "c9f10ececc124587"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# ورقة مرجعية لـ RDC CLI

لا تتضمن هذه الورقة جميع أوامر `rdc`، فقط تلك التي تستخدم في كل نشر. للحصول على مجموعة الخيارات الكاملة، شغّل أي أمر مع `--help`. الحالات الخاصة والخيارات النادرة موجودة في المرجع الكامل.

## دورة حياة المستودع

| الأمر | الوصف |
|-------|-------|
| `rdc repo create <repo> -m <machine>` | إنشاء مستودع جديد على جهاز |
| `rdc repo up <repo>@<machine>` | نشر مستودع أو تحديثه |
| `rdc repo down <repo>@<machine>` | إيقاف مستودع |
| `rdc repo delete <repo>@<machine>` | حذف مستودع |
| `rdc repo fork <repo>@<machine> --tag <tag>` | تفريع مستودع (شبه فوري، باستخدام BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | تولي ملكية مستودع موجود |
| `rdc repo list` | عرض جميع المستودعات باسمها ومعرف GUID |

## أسرار المستودع

بيانات اعتماد وقت النشر (كتابة فقط). يعيد `get` الملخص فقط. لا تُرجع القيمة أبداً. راجع [المستودعات § الأسرار](/ar/docs/repositories#secrets) للدليل الكامل.

| الأمر | الوصف |
|-------|-------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | إنشاء سر جديد (`--current ""` للكتابة الأولى) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | الكتابة فوق سر موجود (شرط على نمط كلمة المرور) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | الكتابة فوق دون التحقق من القيمة السابقة (مسجلة كدوران) |
| `rdc repo secret list <repo>` | عرض أسماء الأسرار ووسائط التسليم (بدون قيم أبداً، بدون ملخصات) |
| `rdc repo secret get <repo> --key <KEY>` | عرض ملخص السر والوضع (بدون قيمة نصية عادية أبداً) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | حذف سر |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | حذف دون التحقق من القيمة السابقة |

> التفريعات لا ترث أي أسرار. اضبطها على التفرع بشكل صريح مع `rdc repo secret set <repo>:<tag>`.

## النسخ الاحتياطي والاستعادة

| الأمر | الوصف |
|-------|-------|
| `rdc repo push <repo>@<machine> --to <storage>` | رفع نسخة احتياطية للمستودع إلى التخزين |
| `rdc repo push --to <storage> -m <machine>` | رفع نسخ احتياطية لجميع المستودعات |
| `rdc repo pull <repo>@<machine> --from <storage>` | استعادة مستودع من التخزين |
| `rdc repo pull --from <storage> -m <machine>` | استعادة جميع المستودعات من التخزين |
| `rdc repo push ... --bwlimit <limit>` | تحديد عرض نطاق rsync أثناء الرفع (مثال: `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | تحديد عرض نطاق rsync أثناء السحب |
| `rdc repo push ... --checkpoint` | عمل نقطة تحقق للحاويات قبل الرفع |
| `rdc backup list --storage <storage> -m <machine>` | عرض النسخ الاحتياطية المتاحة في التخزين |
| `rdc storage browse <storage>` | تصفح محتويات التخزين |

## نقل المستودعات

| الأمر | الوصف |
|-------|-------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | نقل مستودع بين جهازين |
| `rdc repo migrate ... --provision` | تجهيز الجهاز الهدف قبل النقل |
| `rdc repo migrate ... --checkpoint` | عمل نقطة تحقق قبل النقل |
| `rdc repo migrate ... --skip-dns` | تخطي تحديث DNS بعد النقل |
| `rdc repo migrate ... --bwlimit <limit>` | تحديد عرض نطاق النقل |

## استراتيجيات النسخ الاحتياطي

| الأمر | الوصف |
|-------|-------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | إنشاء أو تحديث استراتيجية نسخ احتياطي مسماة |
| `rdc backup strategy list` | عرض جميع استراتيجيات النسخ الاحتياطي المحددة |
| `rdc backup strategy show <name>` | عرض تفاصيل استراتيجية |
| `rdc backup strategy remove <name>` | حذف استراتيجية |
| `rdc backup schedule -m <machine>` | نشر استراتيجيات النسخ الاحتياطي المُكوَّنة على جهاز |

## عمليات النسخ الاحتياطي

| الأمر | الوصف |
|-------|-------|
| `rdc backup schedule -m <machine>` | نشر الاستراتيجيات المرتبطة كمؤقتات systemd |
| `rdc backup schedule -m <machine> --dry-run` | معاينة وحدات المؤقت دون نشر (الرموز مخفية) |
| `rdc backup run -m <machine>` | تشغيل جميع الاستراتيجيات المرتبطة فوراً |
| `rdc backup run <name> -m <machine>` | تشغيل استراتيجية محددة فوراً |
| `rdc backup status -m <machine>` | عرض حالة المؤقتات ونتائج المهام الأخيرة |
| `rdc backup status <name> -m <machine>` | عرض حالة استراتيجية محددة |
| `rdc backup cancel -m <machine>` | إلغاء النسخ الاحتياطية الجارية |
| `rdc backup cancel <name> -m <machine>` | إلغاء نسخة احتياطية جارية محددة |

## إدارة الأجهزة

| الأمر | الوصف |
|-------|-------|
| `rdc machine status <machine>` | الحالة الكاملة للجهاز (النظام، الحاويات، الخدمات، المستودعات، الشبكة) |
| `rdc machine status <machine> --system` | معلومات النظام فقط |
| `rdc machine status <machine> --containers` | قائمة الحاويات فقط |
| `rdc machine status <machine> --repositories` | قائمة المستودعات فقط |
| `rdc machine status <machine> --services` | قائمة الخدمات فقط |
| `rdc machine status <machine> --network` | معلومات الشبكة فقط |
| `rdc machine status <machine> --block-devices` | معلومات أجهزة التخزين فقط |
| `rdc machine list` | عرض جميع الأجهزة في الإعدادات |
| `rdc machine setup <machine>` | تشغيل التجهيز الأولي للجهاز |
| `rdc machine prune <machine>` | إزالة الموارد غير المستخدمة من الجهاز |
| `rdc machine deprovision <machine>` | إلغاء تجهيز الجهاز بالكامل |

## الطرفية والمزامنة

| الأمر | الوصف |
|-------|-------|
| `rdc term connect <machine>` | فتح طرفية SSH للجهاز |
| `rdc term connect <repo>@<machine>` | فتح طرفية SSH للمستودع (تعيين DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | تشغيل أمر على الجهاز |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | رفع ملف أو مجلد أو عدة مصادر إلى المستودع |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | رفع ملف محلي واحد إلى مسار بعيد محدد |
| `rdc repo sync download <repo>@<machine> --local <dir>` | تنزيل مجلد المستودع محلياً |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | تنزيل ملف واحد من المستودع إلى مجلد محلي |
| `rdc vscode connect <repo>@<machine>` | فتح جلسة VS Code Remote SSH |

## الإعدادات

| الأمر | الوصف |
|-------|-------|
| `rdc config init <name>` | إنشاء ملف إعدادات مسمى |
| `rdc machine add <machine> --ip <host> --user <user>` | إضافة جهاز إلى الإعدادات |
| `rdc storage import rclone.conf` | استيراد مزودي التخزين من إعدادات rclone |
| `rdc storage list` | عرض مزودي التخزين المهيأين |
| `rdc backup strategy set ...` | تحديد استراتيجية نسخ احتياطي مسماة |
| `rdc --config <name> <command>` | استخدام ملف إعدادات مسمى |

## التشخيص والوصول المباشر

| الأمر | الوصف |
|-------|-------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | عرض الحاويات في مستودع |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | جلب سجلات الحاوية |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | تنفيذ أمر داخل حاوية |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | إعادة تشغيل حاوية |
