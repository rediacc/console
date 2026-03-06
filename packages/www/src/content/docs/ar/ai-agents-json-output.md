---
title: مرجع مخرجات JSON
description: مرجع كامل لتنسيق مخرجات JSON لأداة rdc CLI، ومخطط الغلاف، ومعالجة الأخطاء، وأوامر اكتشاف الوكيل.
category: Reference
order: 51
language: ar
---

تدعم جميع أوامر `rdc` مخرجات JSON المنظمة للاستهلاك البرمجي بواسطة وكلاء الذكاء الاصطناعي والنصوص البرمجية.

## تفعيل مخرجات JSON

### العلم الصريح

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### الاكتشاف التلقائي

عندما يعمل `rdc` في بيئة non-TTY (عبر أنبوب، أو صدفة فرعية، أو يُشغَّل بواسطة وكيل ذكاء اصطناعي)، تتحول المخرجات تلقائيًا إلى JSON. لا حاجة لأي علم.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## غلاف JSON

يستخدم كل رد JSON غلافًا موحدًا:

```json
{
  "success": true,
  "command": "machine info",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| الحقل | النوع | الوصف |
|-------|------|-------------|
| `success` | `boolean` | ما إذا اكتمل الأمر بنجاح |
| `command` | `string` | مسار الأمر الكامل (مثل `"machine info"`، `"repo up"`) |
| `data` | `object \| array \| null` | الحمولة الخاصة بالأمر عند النجاح، `null` عند الخطأ |
| `errors` | `array \| null` | كائنات الأخطاء عند الفشل، `null` عند النجاح |
| `warnings` | `string[]` | تحذيرات غير حرجة تم جمعها أثناء التنفيذ |
| `metrics` | `object` | بيانات وصفية عن التنفيذ |

## ردود الأخطاء

تُعيد الأوامر الفاشلة أخطاء منظمة مع تلميحات الاسترداد:

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### حقول الأخطاء

| الحقل | النوع | الوصف |
|-------|------|-------------|
| `code` | `string` | رمز خطأ قابل للقراءة آليًا |
| `message` | `string` | وصف مقروء بشريًا |
| `retryable` | `boolean` | ما إذا كانت إعادة المحاولة لنفس الأمر قد تنجح |
| `guidance` | `string` | الإجراء المقترح التالي لحل الخطأ |

### الأخطاء القابلة لإعادة المحاولة

أنواع الأخطاء هذه مُعلَّمة بـ `retryable: true`:

- **NETWORK_ERROR** — فشل اتصال SSH أو الشبكة
- **RATE_LIMITED** — طلبات كثيرة جدًا، انتظر وأعد المحاولة
- **API_ERROR** — فشل مؤقت في الخلفية

الأخطاء غير القابلة لإعادة المحاولة (المصادقة، غير موجود، وسائط غير صالحة) تتطلب إجراءً تصحيحيًا قبل إعادة المحاولة.

## تصفية المخرجات

استخدم `--fields` لتحديد المخرجات بمفاتيح معينة. هذا يقلل استهلاك الرموز عندما تحتاج فقط إلى بيانات محددة:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## مخرجات التشغيل التجريبي

تدعم الأوامر المدمرة `--dry-run` لمعاينة ما سيحدث:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

الأوامر التي تدعم `--dry-run`: `repo up`، `repo down`، `repo delete`، `snapshot delete`، `sync upload`، `sync download`.

## أوامر اكتشاف الوكيل

يوفر الأمر الفرعي `rdc agent` استبطانًا منظمًا لوكلاء الذكاء الاصطناعي لاكتشاف العمليات المتاحة في وقت التشغيل.

### عرض جميع الأوامر

```bash
rdc agent capabilities
```

يُعيد شجرة الأوامر الكاملة مع الوسائط والخيارات والأوصاف:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine info",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### الحصول على مخطط الأمر

```bash
rdc agent schema "machine info"
```

يُعيد المخطط التفصيلي لأمر واحد، بما في ذلك جميع الوسائط والخيارات مع أنواعها وقيمها الافتراضية.

### التنفيذ عبر JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

يقبل JSON عبر stdin، ويربط المفاتيح بوسائط وخيارات الأمر، ويُنفَّذ مع فرض مخرجات JSON. مفيد للاتصال المنظم بين الوكيل وأداة CLI دون إنشاء سلاسل أوامر shell.

## أمثلة التحليل

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
