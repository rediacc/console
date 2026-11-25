---
title: "التكامل مع SIEM"
description: "توجيه أحداث تدقيق Rediacc إلى Splunk أو OpenSearch أو Sentinel أو أي SIEM متوافق مع OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: ar
sourceHash: "224ef90a952edb1c"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# التكامل مع SIEM

تُسجَّل كل عملية على مستوى الآلة تُصدر عبر CLI الخاص بـ Rediacc في جدول `event_log` على خادم الحساب، وتُصدر في الوقت نفسه كسجل OpenTelemetry. يوجّه المشغّلون هذه السجلات إلى SIEM (Splunk وOpenSearch وMicrosoft Sentinel وAWS CloudWatch وغيرها) بتوجيه خادم الحساب إلى OpenTelemetry Collector يصدّر إلى الـ SIEM الذي يختارونه.

تشرح هذه الصفحة طريقة الإعداد. مخطط أحداث التدقيق والنشر المرجعي لـ collector موجودان في المستودع الأحادي العام ضمن [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## ما الذي يُسجَّل

كل إدخال يُكتب في جدول `event_log` على خادم الحساب يُنسخ إلى مسار سجلات OTLP. ويشمل ذلك أحداث مستوى الحساب (المصادقة وتخزين التكوين والترخيص) وأحداث CLI على مستوى الآلة (`cli.repo.up` و`cli.repo.fork` و`cli.backup.push` و`cli.sync.upload` و`cli.term.session` و…).

مفردات أنواع الأحداث اتحاد مميَّز مغلق معرَّف في [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). إضافة نوع حدث جديد تتطلب تغييراً في الشيفرة ويفحصها CI، فيستطيع كتّاب قواعد SIEM الاعتماد على ثبات المفردات.

يحمل كل سجل سمات دلالية من OpenTelemetry:

| السمة | المعنى |
|---|---|
| `event.domain` | القيمة الثابتة `rediacc.audit`، يُرشَّح بها لتجاهل السجلات غير ذات الصلة |
| `event.name` | نوع الحدث القياسي (مثل `cli.repo.up`) |
| `event.source` | `cli` أو `api` أو `system` أو … |
| `enduser.id` | المستخدم الذي بدأ العملية |
| `organization.id`، `team.id` | نطاق المنظمة والفريق |
| `cloud.account.id` | معرّف عميل Stripe |
| `subscription.id` | اشتراك الترخيص |
| `audit.data.*` | حمولة العملية بعد تسطيحها |

## خطوات الإعداد

### 1. نشر الـ collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

افتراضياً يستمع الـ collector على `:4318` (OTLP/HTTP) ويكتب إلى مخرجه القياسي عبر المُصدِّر `debug`، وهو مفيد للتحقق من المسار قبل توجيهه إلى أي وجهة مكلفة.

### 2. توجيه خادم الحساب إليه

في بيئة خادم الحساب (أسرار الـ Worker، أو بيئة العملية على خادم محلي):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

أعد تشغيل خادم الحساب. تبدأ أحداث التدقيق بالتدفق إلى الـ collector فوراً.

### 3. ضبط مُصدِّر SIEM

حرّر الملف `compose/otel-collector/config.yaml`. يأتي الملف بأربعة أمثلة معلَّقة للمُصدِّرات:

- **OpenSearch / Elasticsearch**: المُصدِّر `opensearch`، ويتطلب الامتداد `basicauth/opensearch`.
- **Splunk HEC**: المُصدِّر `splunk_hec`، ويتطلب رمز HEC وفهرساً.
- **AWS CloudWatch Logs**: المُصدِّر `awscloudwatchlogs`، ويتطلب بيانات اعتماد IAM في بيئة الـ collector.
- **Microsoft Sentinel**: عبر المُصدِّر `azuremonitor` مع سلسلة اتصال App Insights.

أزل التعليق عن مُصدِّر واحد بالضبط، واستبدله بـ `debug` في قائمة `exporters:` ضمن مسار `logs:`، ثم أعد تشغيل الـ collector.

يعمل أي [مُصدِّر contrib من OTel Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) يقبل السجلات، فمسار التدقيق ينتج سجلات OTLP قياسية.

## محتوى الكشف

أحداث التدقيق مصمَّمة لكتابة قواعد [Sigma](https://sigmahq.io). قواعد Sigma محايدة تجاه المورّدين وتتحوّل عبر `sigma-cli` إلى استعلامات أصلية لـ OpenSearch وSplunk وSentinel وغيرها.

قاعدة نموذجية (فشل `repo.fork` من مستخدم غير متوقع):

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## الموقف من الامتثال

مسار التدقيق هو الأساس لمتطلبات تسجيل التدقيق المشار إليها في وثائق الامتثال الخاصة بـ Rediacc:

- **GDPR المادة 30**: سجلات أنشطة المعالجة
- **SOC 2 CC6.1 / CC7.2**: تسجيل الوصول والمراقبة
- **HIPAA 45 CFR 164.312(b)**: ضوابط التدقيق
- **PCI DSS Req 10**: تتبع كل عمليات الوصول ومراقبتها
- **NIS2 المادة 21**: أحداث التدقيق مدخل لمعالجة الحوادث؛ أما الخط الزمني للحادثة وساعات المهل والتقارير المرحلية فميزات منفصلة
- **DORA المادة 10**: أحداث التدقيق مدخل للكشف؛ وتعمل كواشف الشذوذ على سجلات تدفق forensics لا على هذا المسار

## الموثوقية

إرسال OTLP من نوع «أطلق وانسَ»: انقطاع الـ collector لا يحجب أي طلب إلى واجهة Rediacc البرمجية ولا يُفشله، ويبقى كل حدث محفوظاً في جدول `event_log` على خادم الحساب في جميع الأحوال. ومع التجميع على دفعات وإعادة المحاولة في الـ collector، يصبح نشر المسار أمام أي SIEM آمناً.
