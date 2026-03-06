---
title: دليل إعداد Claude Code
description: دليل خطوة بخطوة لتهيئة Claude Code لإدارة بنية Rediacc التحتية بشكل مستقل.
category: Guides
order: 31
language: ar
---

يعمل Claude Code بشكل أصلي مع Rediacc من خلال أداة `rdc` CLI. يغطي هذا الدليل الإعداد والأذونات وسير العمل الشائعة.

## الإعداد السريع

1. ثبّت أداة CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. انسخ [قالب AGENTS.md](/ar/docs/agents-md-template) إلى جذر مشروعك كملف `CLAUDE.md`
3. ابدأ Claude Code في مجلد المشروع

يقرأ Claude Code ملف `CLAUDE.md` عند بدء التشغيل ويستخدمه كسياق دائم لجميع التفاعلات.

## تهيئة CLAUDE.md

ضع هذا الملف في جذر مشروعك. راجع [قالب AGENTS.md](/ar/docs/agents-md-template) الكامل للحصول على النسخة الكاملة. الأقسام الرئيسية:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine info <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## أذونات الأدوات

سيطلب Claude Code إذنًا لتشغيل أوامر `rdc`. يمكنك التفويض المسبق للعمليات الشائعة بإضافتها إلى إعدادات Claude Code الخاصة بك:

- السماح بـ `rdc machine info *` — فحوصات الحالة للقراءة فقط
- السماح بـ `rdc machine containers *` — عرض الحاويات
- السماح بـ `rdc machine health *` — فحوصات السلامة
- السماح بـ `rdc config repositories` — عرض المستودعات

بالنسبة للعمليات المدمرة (`rdc repo up`، `rdc repo delete`)، سيطلب Claude Code دائمًا التأكيد ما لم تفوضها صراحةً.

## أمثلة سير العمل

### فحص حالة البنية التحتية

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine info prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### نشر مستودع

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### تشخيص مشاكل الحاويات

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### مزامنة الملفات

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## نصائح

- يكتشف Claude Code تلقائيًا بيئة non-TTY ويتحول إلى مخرجات JSON — لا حاجة لتحديد `-o json` في معظم الحالات
- استخدم `rdc agent capabilities` لتمكين Claude Code من اكتشاف جميع الأوامر المتاحة
- استخدم `rdc agent schema "command name"` للحصول على معلومات تفصيلية عن الوسائط والخيارات
- يساعد علم `--fields` في تقليل استخدام نافذة السياق عندما تحتاج فقط إلى بيانات محددة
