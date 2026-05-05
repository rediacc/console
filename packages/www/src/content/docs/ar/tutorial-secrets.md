---
title: "إدارة الأسرار"
description: "تعيين أسرار لكل مستودع، توصيلها بـ compose، التحقق من وصولها إلى الحاوية، تدويرها، وتأكيد عدم وراثة الأشواك لأي منها."
category: "Tutorials"
order: 7
language: ar
sourceHash: "fb8bc967ed22fc10"
---

# كيفية إدارة الأسرار لكل مستودع باستخدام Rediacc

تحتاج التطبيقات الحقيقية إلى بيانات اعتماد: مفتاح Stripe live، كلمة مرور قاعدة بيانات، رمز API. المكان الخاطئ لوضعها هو داخل المستودع. يرث الشوك كل ما يعيش في الصورة المشفرة، وتبدأ حاوياته بتعريف نفسها كالأصل أمام الخدمات الخارجية. المكان الصحيح هو `rdc repo secret`. تهبط القيم خارج الصورة المشفرة، لذا تبدأ الأشواك بخريطة أسرار فارغة.

في هذا البرنامج التعليمي، تقوم بتعيين كلا وضعي السر، توصيلهما بملف compose، التحقق من وصولهما إلى الحاوية، تدوير واحد منهما، وتأكيد أن الشوكة لا ترث شيئاً.

## المتطلبات الأساسية

- تثبيت CLI `rdc` مع تكوين مهيأ
- آلة مهيأة ومستودع منشأ (انظر [البرنامج التعليمي: دورة حياة المستودع](/ar/docs/tutorial-repos))
- ملف `Rediaccfile` و `docker-compose.yml` يمكنك تحريرها

## الخطوة 1: تعيين سر

يتوفر وضعا تسليم. يصدر `env` القيمة كـ `REDIACC_SECRET_<KEY>` لاستيفاء `${...}` في compose. يكتب `file` القيمة إلى ملف tmpfs على جانب المضيف في `/var/run/rediacc/secrets/<networkID>/<KEY>` للاستخدام مع كتلة `secrets:` الخاصة بـ Docker compose. استخدم `file` لأي شيء حساس. تظهر القيم في وضع env في `docker inspect` و `/proc/<pid>/environ`.

للكتابة الأولى لمفتاح جديد تماماً، مرر `--current ""` (فارغ) للإقرار بعدم وجود قيمة سابقة.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## الخطوة 2: عرض ما هو موجود

```bash
rdc repo secret list --name my-app
```

الإخراج هو JSON يحتوي على اسم ووضع كل سر. لا تظهر القيم أبداً في القائمة. لا يتم حتى جلبها من القرص.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## الخطوة 3: التوصيل بـ compose

تتم الإشارة إلى كلا الوضعين من نفس `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`stripe_key` بالأحرف الصغيرة على الخدمة هو اسم ملف `/run/secrets/<name>` داخل الحاوية. `STRIPE_KEY` بالأحرف الكبيرة في مسار المضيف يطابق `--key` الذي قمت بتعيينه. يتم استيفاء `${REDIACC_NETWORK_ID}` بواسطة `renet compose` تلقائياً. هذا مهم لأن معرف الشبكة هو لكل شوكة، لذا يعمل نفس ملف compose في الأصل وفي أي شوكة (حيث، كما سترى في الخطوة 6، الملف ببساطة لن يكون موجوداً).

> **العزل عبر المستودعات مفروض.** يرفض مدقق compose التابع لـ renet أي مسار `secrets: file:` (أو `configs: file:`، أو `env_file:`) يستهدف معرف شبكة مستودع آخر. الرمز الحرفي `${REDIACC_NETWORK_ID}` (أو عدد صحيح لشبكتك الخاصة) هو الشكل الوحيد المقبول، ولا يتجاوز `--unsafe` ذلك. كما تحدد صندوق الحماية Landlock حول العملية الفرعية bash لـ Rediaccfile قراءات نظام الملفات إلى دليل أسرار شبكتك الخاصة. لذلك حتى `cat /var/run/rediacc/secrets/<other>/X` خبيثة من Rediaccfile تفشل مع EACCES في طبقة النواة. لا تحتاج إلى فعل أي شيء للاشتراك؛ الحماية مفعلة افتراضياً.

## الخطوة 4: النشر والتحقق

```bash
rdc repo up --name my-app -m server-1
```

بعد النشر، نفذ exec في الحاوية للتأكد من وصول كلا الوضعين:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

إذا كنت تريد فحص ملف tmpfs على جانب المضيف مباشرة:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## الخطوة 5: التدوير دون معرفة القيمة السابقة

يمكنك قراءة ملخص باستخدام `rdc repo secret get`، ولكن ليس القيمة بنص عادي أبداً. هذا هو نموذج الكتابة فقط. إذا كنت بحاجة إلى التحقق من أن القيمة المخزنة تطابق ما لديك، فمررها عبر `--current` وراقب الشرط المسبق ينجح أو يفشل:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

إذا نسيت القيمة السابقة تماماً (فقدها مدير كلمات المرور الخاص بك، أو ورثت المستودع)، استخدم `--rotate-secret` لتخطي الشرط المسبق. يسجل سجل التدقيق هذا بصوت عالٍ كتدوير:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` و `--rotate-secret` حصريان بشكل متبادل. اختر واحداً.

## الخطوة 6: تأكيد عدم وراثة الأشواك لأي شيء

النقطة الرئيسية: قم بتفريع المستودع وتحقق من قائمة أسرار الشوكة:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

فارغة. لا يمكن لحاويات الشوكة استيفاء `${REDIACC_SECRET_DB_HOST}` (المتغير غير معين، لذا سلسلة فارغة)، والملف في `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` ببساطة غير موجود. إذا حاول `repo up` للشوكة تركيبه عبر كتلة `secrets:` لـ compose، فسوف يفشل النشر بخطأ واضح. بالضبط وضع الفشل الذي تريده، لأنه يعني أن صندوق الحماية لا يمكنه التظاهر بأنه إنتاج أمام الخدمات الخارجية.

لاستخدام الأسرار في الشوكة، عيّنها على الشوكة بشكل صريح بقيم محددة لصندوق الحماية:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

الآن تتحدث الشوكة مع قاعدة بيانات اختبار وحساب صندوق رمل Stripe. لا تغادر بيانات اعتماد الإنتاج للأصل الأصل أبداً.

## التنظيف

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## انظر أيضاً

- [المستودعات § الأسرار](/ar/docs/repositories#secrets). المرجع الكامل
- [ورقة غش CLI RDC § الأسرار لكل مستودع](/ar/docs/rdc-cheat-sheet#per-repo-secrets). المرجع السريع للأوامر
- [سلامة وكيل الذكاء الاصطناعي](/ar/docs/ai-agents-safety). بوابة الطفرة المتماثلة وتلميحات الإجراء `next` المنظمة في مظاريف الأخطاء
- [الخدمات § استخدام الأسرار لكل مستودع في compose](/ar/docs/services#using-per-repo-secrets-in-compose). مرجع نمط compose
