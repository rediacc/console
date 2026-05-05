---
title: ورقة مرجعية لـ RDC CLI
description: >-
  مرجع سريع لجميع أوامر rdc، الإعدادات، المستودعات، الأجهزة، المزامنة، الحاويات
  والمزيد.
category: Guides
order: 3
language: ar
sourceHash: "ec3f99cf89fde4b3"
sourceCommit: 35b53352026ae87fb6800c7fed10b793223ca1da
---

# ورقة مرجعية لـ RDC CLI

مرجع سريع لأكثر أوامر `rdc` استخداماً. شغّل أي أمر مع `--help` للاطلاع على كامل الخيارات.

## دورة حياة المستودع

| الأمر | الوصف |
|-------|-------|
| `rdc repo create --name <repo> -m <machine>` | إنشاء مستودع جديد على جهاز |
| `rdc repo up --name <repo> -m <machine>` | نشر مستودع أو تحديثه |
| `rdc repo down --name <repo> -m <machine>` | إيقاف مستودع |
| `rdc repo delete --name <repo> -m <machine>` | حذف مستودع |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | تفريع مستودع (شبه فوري، باستخدام BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | تولي ملكية مستودع موجود |
| `rdc config repository list` | عرض جميع المستودعات باسمها ومعرف GUID |

## النسخ الاحتياطي والاستعادة

| الأمر | الوصف |
|-------|-------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | رفع نسخة احتياطية للمستودع إلى التخزين |
| `rdc repo push --to <storage> -m <machine>` | رفع نسخ احتياطية لجميع المستودعات |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | استعادة مستودع من التخزين |
| `rdc repo pull --from <storage> -m <machine>` | استعادة جميع المستودعات من التخزين |
| `rdc repo push ... --bwlimit <limit>` | تحديد عرض نطاق rsync أثناء الرفع (مثال: `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | تحديد عرض نطاق rsync أثناء السحب |
| `rdc repo push ... --checkpoint` | عمل نقطة تحقق للحاويات قبل الرفع |
| `rdc repo backup list --from <storage> -m <machine>` | عرض النسخ الاحتياطية المتاحة في التخزين |
| `rdc storage browse --name <storage>` | تصفح محتويات التخزين |

## نقل المستودعات

| الأمر | الوصف |
|-------|-------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | نقل مستودع بين جهازين |
| `rdc repo migrate ... --provision` | تجهيز الجهاز الهدف قبل النقل |
| `rdc repo migrate ... --checkpoint` | عمل نقطة تحقق قبل النقل |
| `rdc repo migrate ... --skip-dns` | تخطي تحديث DNS بعد النقل |
| `rdc repo migrate ... --bwlimit <limit>` | تحديد عرض نطاق النقل |

## استراتيجيات النسخ الاحتياطي

| الأمر | الوصف |
|-------|-------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | إنشاء أو تحديث استراتيجية نسخ احتياطي مسماة |
| `rdc config backup-strategy list` | عرض جميع استراتيجيات النسخ الاحتياطي المحددة |
| `rdc config backup-strategy show --name <name>` | عرض تفاصيل استراتيجية |
| `rdc config backup-strategy remove --name <name>` | حذف استراتيجية |
| `rdc config machine set <machine> --backup-strategies <s1,s2>` | ربط الاستراتيجيات بجهاز |

## عمليات النسخ الاحتياطي

| الأمر | الوصف |
|-------|-------|
| `rdc machine backup schedule -m <machine>` | نشر الاستراتيجيات المرتبطة كمؤقتات systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | معاينة وحدات المؤقت دون نشر (الرموز مخفية) |
| `rdc machine backup now -m <machine>` | تشغيل جميع الاستراتيجيات المرتبطة فوراً |
| `rdc machine backup now -m <machine> --strategy <name>` | تشغيل استراتيجية محددة فوراً |
| `rdc machine backup status -m <machine>` | عرض حالة المؤقتات ونتائج المهام الأخيرة |
| `rdc machine backup status -m <machine> --strategy <name>` | عرض حالة استراتيجية محددة |
| `rdc machine backup cancel -m <machine>` | إلغاء النسخ الاحتياطية الجارية |
| `rdc machine backup cancel -m <machine> --strategy <name>` | إلغاء نسخة احتياطية جارية محددة |

## إدارة الأجهزة

| الأمر | الوصف |
|-------|-------|
| `rdc machine query --name <machine>` | الحالة الكاملة للجهاز (النظام، الحاويات، الخدمات، المستودعات، الشبكة) |
| `rdc machine query --name <machine> --system` | معلومات النظام فقط |
| `rdc machine query --name <machine> --containers` | قائمة الحاويات فقط |
| `rdc machine query --name <machine> --repositories` | قائمة المستودعات فقط |
| `rdc machine query --name <machine> --services` | قائمة الخدمات فقط |
| `rdc machine query --name <machine> --network` | معلومات الشبكة فقط |
| `rdc machine query --name <machine> --block-devices` | معلومات أجهزة التخزين فقط |
| `rdc machine list` | عرض جميع الأجهزة في الإعدادات |
| `rdc config machine setup --name <machine>` | تشغيل التجهيز الأولي للجهاز |
| `rdc machine prune --name <machine>` | إزالة الموارد غير المستخدمة من الجهاز |
| `rdc machine deprovision --name <machine>` | إلغاء تجهيز الجهاز بالكامل |
| `rdc machine vault-status --name <machine>` | عرض حالة خزينة LUKS |

## الطرفية والمزامنة

| الأمر | الوصف |
|-------|-------|
| `rdc term connect -m <machine>` | فتح طرفية SSH للجهاز |
| `rdc term connect -m <machine> -r <repo>` | فتح طرفية SSH للمستودع (تعيين DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | تشغيل أمر على الجهاز |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | رفع ملف أو مجلد أو عدة مصادر إلى المستودع |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | تنزيل مجلد المستودع محلياً |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | تنزيل ملف واحد من المستودع إلى مجلد محلي |
| `rdc vscode connect -m <machine> -r <repo>` | فتح جلسة VS Code Remote SSH |

## الإعدادات

| الأمر | الوصف |
|-------|-------|
| `rdc config init --name <name>` | إنشاء ملف إعدادات مسمى |
| `rdc config machine add --name <machine> --host <host> --user <user>` | إضافة جهاز إلى الإعدادات |
| `rdc config storage import --file rclone.conf` | استيراد مزودي التخزين من إعدادات rclone |
| `rdc config storage list` | عرض مزودي التخزين المهيأين |
| `rdc config backup-strategy set ...` | تحديد استراتيجية نسخ احتياطي مسماة |
| `rdc --config <name> <command>` | استخدام ملف إعدادات مسمى |

## التشخيص والوصول المباشر

| الأمر | الوصف |
|-------|-------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | عرض الحاويات في مستودع |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | جلب سجلات الحاوية |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | تنفيذ أمر داخل حاوية |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | إعادة تشغيل حاوية |
