---
title: نظرة عامة على تكامل وكلاء الذكاء الاصطناعي
description: كيف تتكامل مساعدات البرمجة الذكية مثل Claude Code وCursor وCline مع بنية Rediacc التحتية للنشر والإدارة المستقلة.
category: Guides
order: 30
language: ar
---

يمكن لمساعدات البرمجة الذكية إدارة بنية Rediacc التحتية بشكل مستقل من خلال أداة `rdc` CLI. يغطي هذا الدليل مناهج التكامل وكيفية البدء.

## لماذا الاستضافة الذاتية + وكلاء الذكاء الاصطناعي

بنية Rediacc ملائمة للوكلاء بطبيعتها:

- **CLI أولاً**: كل عملية هي أمر `rdc` — لا حاجة لواجهة رسومية
- **قائم على SSH**: البروتوكول الذي يعرفه الوكلاء جيدًا من بيانات التدريب
- **مخرجات JSON**: جميع الأوامر تدعم `--output json` مع غلاف موحد
- **عزل Docker**: كل مستودع يحصل على daemon وفضاء شبكة خاص به
- **قابل للبرمجة**: `--yes` يتخطى التأكيدات، `--dry-run` يعاين العمليات المدمرة

## مناهج التكامل

### 1. قالب AGENTS.md / CLAUDE.md

أسرع طريقة للبدء. انسخ [قالب AGENTS.md](/ar/docs/agents-md-template) إلى جذر مشروعك:

- `CLAUDE.md` لـ Claude Code
- `.cursorrules` لـ Cursor
- `.windsurfrules` لـ Windsurf

يمنح هذا الوكيل السياق الكامل عن الأوامر المتاحة والبنية والاتفاقيات.

### 2. خط أنابيب مخرجات JSON

عندما يستدعي الوكلاء `rdc` في صدفة فرعية، تتحول المخرجات تلقائيًا إلى JSON (اكتشاف non-TTY). يستخدم كل رد JSON غلافًا موحدًا:

```json
{
  "success": true,
  "command": "machine info",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

تتضمن ردود الأخطاء حقلي `retryable` و`guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. اكتشاف قدرات الوكيل

يوفر الأمر الفرعي `rdc agent` استبطانًا منظمًا:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## أعلام مهمة للوكلاء

| العلم | الغرض |
|------|---------|
| `--output json` / `-o json` | مخرجات JSON قابلة للقراءة آليًا |
| `--yes` / `-y` | تخطي التأكيدات التفاعلية |
| `--quiet` / `-q` | كتم مخرجات stderr المعلوماتية |
| `--fields name,status` | تحديد المخرجات بحقول معينة |
| `--dry-run` | معاينة العمليات المدمرة دون تنفيذها |

## الخطوات التالية

- [دليل إعداد Claude Code](/ar/docs/ai-agents-claude-code) — تهيئة Claude Code خطوة بخطوة
- [دليل إعداد Cursor](/ar/docs/ai-agents-cursor) — تكامل بيئة تطوير Cursor
- [مرجع مخرجات JSON](/ar/docs/ai-agents-json-output) — توثيق كامل لمخرجات JSON
- [قالب AGENTS.md](/ar/docs/agents-md-template) — قالب تهيئة وكيل جاهز للنسخ واللصق
