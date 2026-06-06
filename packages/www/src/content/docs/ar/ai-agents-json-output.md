---
title: مرجع مخرجات JSON
description: >-
  مرجع كامل لتنسيق مخرجات JSON لأداة rdc CLI، ومخطط الغلاف، ومعالجة الأخطاء،
  وأوامر اكتشاف الوكيل.
category: Reference
order: 51
language: ar
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

تُخرج جميع أوامر `rdc` بيانات JSON منظمة. مرِّرها إلى نص برمجي أو أرسلها مباشرة إلى وكيل.

## تفعيل مخرجات JSON

### العلم الصريح

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### الاكتشاف التلقائي

عندما يعمل `rdc` في بيئة non-TTY (عبر أنبوب، أو صدفة فرعية، أو يُشغَّل بواسطة وكيل ذكاء اصطناعي)، تتحول المخرجات تلقائيًا إلى JSON. لا حاجة لأي علم.

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## غلاف JSON

يستخدم كل رد JSON غلافًا موحدًا:

```json
{
  "success": true,
  "command": "machine query",
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
| `command` | `string` | مسار الأمر الكامل (مثل `"machine query"`، `"repo up"`) |
| `data` | `object \| array \| null` | الحمولة الخاصة بالأمر عند النجاح، `null` عند الخطأ |
| `errors` | `array \| null` | كائنات الأخطاء عند الفشل، `null` عند النجاح |
| `warnings` | `string[]` | تحذيرات غير حرجة تم جمعها أثناء التنفيذ |
| `metrics` | `object` | بيانات وصفية عن التنفيذ |

## ردود الأخطاء

تُعيد الأوامر الفاشلة أخطاء منظمة مع تلميحات الاسترداد:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
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
| `code` | `string` | رمز خطأ قابل للقراءة آليًا (راجع ثوابت `ERROR_CODES` للقائمة الكاملة) |
| `message` | `string` | وصف مقروء بشريًا |
| `retryable` | `boolean` | ما إذا كانت إعادة المحاولة لنفس الأمر قد تنجح |
| `guidance` | `string` | تلميح نصي حر (قديم. يُفضَّل استخدام `next` للبيانات الإجرائية المنظمة) |
| `next` | `object?` | تلميح منظم للخطوة التالية (عند توفره). انظر أدناه |

### تلميحات الإجراء المنظمة عبر `next`

لرموز الأخطاء ذات القيمة العالية مثل `PRECONDITION_MISMATCH`، يتضمن الخطأ حقل `next` مع الأوامر الدقيقة لعرضها على المستخدم. ليس كل رمز خطأ يحمل هذا الحقل؛ فقط تلك التي يوجد لها مسار استرداد محدد. **ينبغي للوكلاء نقل `next.options[].run` حرفيًا إلى الإنسان بدلًا من صياغة أوامرهم الخاصة.** هذا يُقلل من حالات الفشل حين يخترع الوكيل أمرًا غير موجود، وهو ما يحدث أكثر مما تتوقع.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

المخطط:

| الحقل | النوع | الوصف |
|-------|------|-------------|
| `next.summary` | `string` | وصف من سطر واحد لما يحتاج المستخدم لاتخاذ قرار بشأنه |
| `next.options[]` | `array` | الإجراءات الملموسة؛ كل منها بديل يمكن للمستخدم اختياره |
| `next.options[].description` | `string` | شرح مقروء لهذا الخيار |
| `next.options[].run` | `string` | أمر CLI دقيق. انقله حرفيًا إلى المستخدم |

### الأخطاء القابلة لإعادة المحاولة

أنواع الأخطاء هذه مُعلَّمة بـ `retryable: true`:

- **NETWORK_ERROR**, فشل اتصال SSH أو الشبكة
- **RATE_LIMITED**, طلبات كثيرة جدًا، انتظر وأعد المحاولة
- **API_ERROR**, فشل مؤقت في الخلفية

الأخطاء غير القابلة لإعادة المحاولة (المصادقة، غير موجود، وسائط غير صالحة) تتطلب إجراءً تصحيحيًا قبل إعادة المحاولة.

## تصفية المخرجات

استخدم `--fields` لتحديد المخرجات بمفاتيح معينة وتقليل استهلاك الرموز:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## مخرجات التشغيل التجريبي

تدعم الأوامر المدمرة `--dry-run` لمعاينة ما سيحدث:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
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

يوفر الأمر الفرعي `rdc agent` طريقة منظمة لوكلاء الذكاء الاصطناعي لاكتشاف العمليات المتاحة في وقت التشغيل.

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
        "name": "machine query",
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
rdc agent schema --command "machine query"
```

يُعيد المخطط الكامل لأمر واحد: كل وسيطة وخيار مع نوعه وقيمته الافتراضية.

### التنفيذ عبر JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

يقبل JSON عبر stdin، ويربط المفاتيح بوسائط وخيارات الأمر، ويُنفَّذ مع فرض مخرجات JSON. استخدم هذا حين تفضل عدم بناء سلاسل أوامر shell في استدعاءات الوكيل إلى CLI.

## أمثلة التحليل

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
