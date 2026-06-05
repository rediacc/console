---
title: نظرة عامة على تكامل وكلاء الذكاء الاصطناعي
description: "كيف تُدير Claude Code وCursor وCline بنية Rediacc التحتية عبر rdc: مخرجات JSON، واستبطان الوكيل، وضوابط الأمان."
category: Guides
order: 30
language: ar
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

صراحةً، `rdc` مصمّم مع مراعاة الوكلاء من الأساس. سواء كنت تستخدم Claude Code أو Cursor أو Cline، فأي مساعد ذكاء اصطناعي ينادي `rdc` في صدفة فرعية يحصل على مخرجات JSON منظمة، وأخطاء قابلة للقراءة آليًا، وضوابط أمان تناسب إدارة بنية Rediacc التحتية باستقلالية. إليك كيف يعمل التكامل.

## لماذا الاستضافة الذاتية + وكلاء الذكاء الاصطناعي

بنية Rediacc ملائمة للوكلاء بطبيعتها:

- **CLI أولاً**: كل عملية هي أمر `rdc`, لا حاجة لواجهة رسومية
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

ضعه في المكان المناسب وسيمتلك الوكيل المرجع الكامل للأوامر، وسياق البنية، والاتفاقيات التي يحتاجها للعمل دون تخمين.

### 2. خط أنابيب مخرجات JSON

عندما يستدعي الوكلاء `rdc` في صدفة فرعية، تتحول المخرجات تلقائيًا إلى JSON (اكتشاف non-TTY). يستخدم كل رد JSON غلافًا موحدًا:

```json
{
  "success": true,
  "command": "machine query",
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
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. اكتشاف قدرات الوكيل

يوفر الأمر الفرعي `rdc agent` استبطانًا منظمًا:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## أعلام مهمة للوكلاء

| العلم | الغرض |
|------|---------|
| `--output json` / `-o json` | مخرجات JSON قابلة للقراءة آليًا |
| `--yes` / `-y` | تخطي التأكيدات التفاعلية |
| `--quiet` / `-q` | كتم مخرجات stderr المعلوماتية |
| `--fields name,status` | تحديد المخرجات بحقول معينة |
| `--dry-run` | معاينة العمليات المدمرة دون تنفيذها |

## السلامة والضوابط

لا يتعامل CLI مع الوكلاء بالطريقة ذاتها التي يتعامل بها مع إنسان أمام الطرفية. العمليات الحساسة تتطلب إثبات معرفتك بالحالة الراهنة عبر العلم `--current`، وتدفقات المحرر التفاعلية مرفوضة افتراضيًا، وكل رفض يُسجَّل في سجل التدقيق. يغطي مرجع [السلامة والضوابط لوكلاء الذكاء الاصطناعي](/ar/docs/ai-agents-safety) جدول جدار الحماية الكامل، ونموذج بوابة المعرفة، ونطاق التجاوز `REDIACC_ALLOW_CONFIG_EDIT`، وسجل التدقيق المرتبط بالتجزئة.

## الخطوات التالية

- [السلامة والضوابط لوكلاء الذكاء الاصطناعي](/ar/docs/ai-agents-safety), ما يستطيع الوكلاء فعله وما لا يستطيعونه، بوابة المعرفة، سجل التدقيق
- [دليل إعداد Claude Code](/ar/docs/ai-agents-claude-code), تهيئة Claude Code خطوة بخطوة
- [دليل إعداد Cursor](/ar/docs/ai-agents-cursor), تكامل بيئة تطوير Cursor
- [مرجع مخرجات JSON](/ar/docs/ai-agents-json-output), توثيق كامل لمخرجات JSON
- [قالب AGENTS.md](/ar/docs/agents-md-template), قالب تهيئة وكيل جاهز للنسخ واللصق
