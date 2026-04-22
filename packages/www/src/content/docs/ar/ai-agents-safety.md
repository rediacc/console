---
title: أمان وضمانات وكلاء الذكاء الاصطناعي
description: 'كيف تمنع واجهة سطر أوامر Rediacc مساعدي البرمجة بالذكاء الاصطناعي من تسريب الأسرار أو الكتابة فوق بيانات الاعتماد أو تصعيد الصلاحيات: بوابات المعرفة والتعتيم والتجاوزات المعتمدة بالسلف وسجل تدقيق مرتبط بالتجزئة.'
category: Concepts
order: 35
language: ar
sourceHash: "6a4f4ccd6ae806ee"
sourceCommit: "4bef9a170fb07db00a4ee2ef504aa27706bcd15a"
---

عندما يتحكم Claude Code أو Cursor أو Gemini CLI أو Copilot CLI أو أي مساعد برمجة آخر بالذكاء الاصطناعي في تشغيل `rdc`، تتعامل معه واجهة سطر الأوامر بشكل مختلف عن الإنسان الجالس أمام لوحة المفاتيح. تشرح هذه الصفحة ما يمكن للوكيل فعله، وما لا يمكنه فعله، وكيف تصمد الضمانات حتى عندما يحاول الوكيل التحايل عليها.

## مرجع سريع: ما يمكن للوكلاء فعله وما لا يمكنهم فعله

| العملية | الإعداد الافتراضي للوكيل | كيفية الفتح لحالة استخدام محددة |
|---|---|---|
| `rdc config show` (معتَّم) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (نموذج معتَّم أو ملخص) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (حقل عام) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (حقل حساس، **مع `--current` صحيح**) | ✅ allowed |  |
| `rdc config edit --dump` (JSONC معتَّم) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (حقل حساس، بدون `--current`) | 🔴 refused | تزويد `--current "<القيمة القديمة>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | استخدام `--digest` بدلاً من ذلك |
| `rdc config show --reveal` | 🔴 refused | استخدام `rdc config show` العادي |
| `rdc config edit` (المحرر التفاعلي) | 🔴 refused | يضع الإنسان `REDIACC_ALLOW_CONFIG_EDIT=*` قبل تشغيل الوكيل |
| `rdc config edit --apply <file>` | 🔴 refused | نفس التجاوز |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | نفس التجاوز؛ يستخدم تأكيداً تفاعلياً |
| `rdc term connect -m <machine>` (SSH مباشر إلى الجهاز) | 🔴 refused | تفريع مستودع أولاً والاتصال بالنسخة المفرعة |

كل ما يُرفض للوكيل يُكتب في سجل التدقيق مع `outcome: refused` وسبب الرفض.

## كيف يتم اكتشاف الوكلاء

تتعامل واجهة سطر الأوامر مع العملية على أنها وكيل عند تحقق أي من الشروط التالية:

- أي من المتغيرات `REDIACC_AGENT` أو `CLAUDECODE` أو `GEMINI_CLI` أو `COPILOT_CLI` مضبوط على `"1"`، أو `CURSOR_TRACE_ID` مضبوط بأي قيمة.
- على Linux: أي عملية أصل في سلسلة السلف تحتوي على إحدى هذه المتغيرات في بيئتها (عبر `/proc/<pid>/environ`). حتى لو قام الوكيل بحذف متغيراته الخاصة باستخدام `env -i` أو سكريبت مغلف، تظل سلسلة الأصل تخبر واجهة سطر الأوامر بمن بدأ التشغيل.

يعمل الاكتشاف مرة واحدة لكل عملية ويُخزَّن مؤقتاً. ولا يمكن تعطيله.

## نموذج بوابة المعرفة

التعديلات الحساسة تتبع اتفاقية `passwd(1)`: لتغيير سر، أثبت أنك كنت تعرفه بالفعل.

- تريد تدوير رمز API مخزَّن في `/credentials/cfDnsApiToken`؟
- تسأل واجهة سطر الأوامر: "ما هي القيمة الحالية؟"
- يزوّد الوكيل النص الصريح عبر `--current "$OLD"`. تُجزِّئ واجهة سطر الأوامر `$OLD` بـ SHA-256 وتقارنه بملخص القيمة المخزَّنة حالياً. تطابق → تنفيذ الكتابة. عدم تطابق → رفض، تسجيل.

النموذج بسيط لكنه يغلق ثلاث أسطح هجومية:

1. **التدوير الصامت**: الوكيل الذي لم يكن له وصول سابق إلى `$OLD` لا يستطيع استبداله بقيمة من اختياره.
2. **التسرب عبر الاستطلاع**: استجابة الملخص لا تحتوي أبداً على نص صريح؛ حتى سجل التدقيق المخترق يُظهر `expected abc12345…, got deadbeef…`، وليس القيم الأساسية.
3. **الكتابة فوق إعدادات المستخدم عن طريق الخطأ**: يتطلب `--current` متعمداً في كل مرة؛ لا كتابة فوق تلقائية عند `set`.

### مثال توضيحي

```bash
# الحصول على الملخص القصير لنموذج التعتيم (آمن للوكلاء).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# محاولة الكتابة فوق بلا إثبات: مرفوض.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# تزويد النص الصريح الحالي: مسموح.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

إذا لم يكن للوكيل `$OLD_CF_TOKEN` قط، فلا يمكنه الوفاء بالشرط المسبق وسيُرفض التدوير. المستخدم الذي *يمتلكه* لا يزال بإمكانه القيام بذلك إما عبر المحرر أو بتمرير `--current` من shell الخاص به.

## التعتيم افتراضياً

كل أمر `rdc` يقرأ الحالة الحساسة: `config show`، `config field get`، `config machine list`، `config edit --dump`: يُرجع **نماذج تعتيم** لحقول الأسرار، وليس نصاً صريحاً:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

اللاحقة السداسية عشرية المكونة من 8 أحرف في النموذج هي أول 8 أحرف من `sha256(canonicalize(value))`: كافية للتمييز بين قيمتين مختلفتين بنظرة واحدة، غير كافية للعكس. يمكن للوكيل استخدام النموذج لتتبع ما إذا كانت القيمة قد تغيرت دون رؤيتها قط.

`--reveal` يرفع التعتيم للبشر على TTY تفاعلي. يُرفض الوكلاء بغض النظر عن حالة TTY. كل منح يكتب قيداً في سجل التدقيق بـ `reveal_granted`؛ كل رفض يكتب قيداً `refused` مع إشارات الوكيل للجهة الفاعلة مرفقة.

## التجاوز `REDIACC_ALLOW_CONFIG_EDIT`

بعض العمليات: المحرر التفاعلي، `--apply`، `field rotate`: موجودة للبشر وليس لها مسار آمن للوكلاء. إذا كنت تريد بنشاط أن يقوم وكيل بإحداها، تضبط:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # تجاوز كامل
# أو
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (نطاقات glob مفصولة بفواصل: أحرف * البدل مسموحة لكل شريحة)
```

…ويرث الوكيل هذا.

**تفصيل حاسم**: يجب أن يظهر التجاوز في عملية **فوق** الوكيل في سلسلة السلف. إذا ضبطه الوكيل في بيئته الخاصة (أو في shell فرعي أنشأه)، ترفض واجهة سطر الأوامر وتعلمك بذلك:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

الأثر: لا يستطيع الوكيل تجاوز ضمانة بتشغيل `export REDIACC_ALLOW_CONFIG_EDIT='*'` في منتصف الجلسة. فقط عملية أصل (أنت، في طرفيتك، قبل تشغيل الوكيل) يمكنها فتح ذلك الباب.

## سجل التدقيق

كل تعديل، كل رفض، كل منح `--reveal` يكتب سطر JSONL في `~/.config/rediacc/audit.log.jsonl` (النمط `0600`، يتدوّر عند 10 ميجابايت). كل سطر مرتبط بتجزئة: حقل `prevHash` الخاص به هو `sha256("<السطر السابق>")`. العبث بأي سطر يكسر السلسلة في كل سطر تالٍ.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### الفحص

```bash
# سرد القيود الأخيرة
rdc config audit log --since 24h

# التصفية بنمط glob للمؤشر
rdc config audit log --path '/credentials/*'

# القيود الصادرة عن الوكلاء فقط
rdc config audit log --actor agent

# بث القيود الجديدة مباشرةً (Ctrl+C للإيقاف)
rdc config audit tail

# التحقق من سلامة سلسلة التجزئة
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   أو
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### ما لا يظهر أبداً في سجل التدقيق

- قيم الأسرار بنص صريح
- كلمات المرور والرموز ومفاتيح SSH
- القيم القديمة/الجديدة في حالة عدم تطابق الشرط المسبق `--current` (بادئة الملخص المكونة من 8 أحرف فقط)

السجل آمن للمشاركة مع مراجع الأمن أو إرفاقه بتقرير خطأ.

## حدود النموذج السلوكي

ضمانات الوكيل **سلوكية، وليست مشفَّرة**. الوكيل المصمم أو الموجَّه الذي يعمل بنفس UID ملف الإعدادات يستطيع دائماً تشغيل `cat ~/.config/rediacc/rediacc.json` وقراءة النص الصريح، لأن الملف قابل للقراءة من قِبَل العملية.

للتطبيق المشفَّر الحقيقي، استخدم [مخزن الإعدادات المشفَّر](/ar/docs/config-storage): تعيش الأسرار على الجانب الخادم، كل حقل حساس يحمل التزام HMAC خاصاً به، وعامل الحساب يرفض الكتابات التي لا يتطابق شرطها المسبق `--current` مع ما هو مُخزَّن بالتجزئة. الخادم لا يرى النص الصريح أبداً: معرفة صفرية: لكنه يُطبِّق البوابة.

مسار الملف المحلي هو "الطريق السهل آمن". مسار المخزن البعيد هو "الطريق الصعب صعب أيضاً".

## وصفات سريعة

### السماح لوكيل بتدوير رمز سحابي واحد

```bash
# بوصفك أنت، قبل بدء الوكيل:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # أو cursor أو gemini إلخ
```

الآن يستطيع الوكيل تشغيل `config field rotate /credentials/cfDnsApiToken --new …` لكنه لا يزال غير قادر على تحرير `/credentials/ssh/privateKey` أو فتح المحرر التفاعلي.

### السماح لوكيل بجلسة تحرير إعدادات واسعة

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

يستطيع الوكيل فتح `rdc config edit` واستخدام `--reveal` وتشغيل `field rotate`. كل إجراء لا يزال مُسجَّلاً في سجل التدقيق مع `actor.kind: agent` وإشارة `CLAUDECODE`.

### اكتشاف الحقول التي يُسمح للوكيل بلمسها

```bash
rdc config field list --sensitive --output json
```

يُرجع كل قالب مؤشر ونوعه (`secret` / `credential` / `pii` / `identifier`) وما إذا كان ملتزماً بغلاف HMAC من جانب الخادم.

## انظر أيضاً

- [نظرة عامة على تكامل وكيل الذكاء الاصطناعي](/ar/docs/ai-agents-overview): الجولة الشاملة
- [إعداد Claude Code](/ar/docs/ai-agents-claude-code): قالب التكامل
- [غلاف إخراج JSON](/ar/docs/ai-agents-json-output): استجابات قابلة للقراءة الآلية
- [مخزن الإعدادات المشفَّر](/ar/docs/config-storage): التطبيق المشفَّر من جانب الخادم
- [أمان الحساب](/ar/docs/account-security): وضع الأمان من جانب المشغِّل
