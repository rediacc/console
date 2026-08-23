---
title: دليل إعداد Claude Code
description: دليل خطوة بخطوة لتهيئة Claude Code لإدارة بنية Rediacc التحتية بشكل مستقل.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 31
language: ar
sourceHash: "2c925f7e46d63e9a"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
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
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## أذونات الأدوات

سيطلب Claude Code إذنًا لتشغيل أوامر `rdc`. يمكنك التفويض المسبق للعمليات الشائعة بإضافتها إلى إعدادات Claude Code الخاصة بك:

- السماح بـ `rdc machine status *`, فحوصات الحالة للقراءة فقط
- السماح بـ `rdc machine status * --containers`, عرض الحاويات
- السماح بـ `rdc machine health *`, فحوصات السلامة
- السماح بـ `rdc repo list`, عرض المستودعات

بالنسبة للعمليات المدمرة (`rdc repo up`، `rdc repo delete`)، سيطلب Claude Code دائمًا التأكيد ما لم تفوضها صراحةً.

## أمثلة سير العمل

### فحص حالة البنية التحتية

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### نشر مستودع

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### تشخيص مشاكل الحاويات

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### مزامنة الملفات

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## نصائح

- يكتشف Claude Code تلقائيًا بيئة non-TTY ويتحول إلى مخرجات JSON, لا حاجة لتحديد `-o json` في معظم الحالات
- استخدم `rdc --help-all` لتمكين Claude Code من اكتشاف جميع الأوامر المتاحة
- يساعد علم `--fields` في تقليل استخدام نافذة السياق عندما تحتاج فقط إلى بيانات محددة
