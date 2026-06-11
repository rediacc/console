---
title: الشبكات
description: >-
  كشف الخدمات باستخدام الوكيل العكسي، وعلامات Docker، وشهادات TLS، وDNS، وتوجيه
  منافذ TCP/UDP.
category: Guides
order: 6
language: ar
sourceHash: 2bb63d224370c266
sourceCommit: 20f014619af1ee41e75cd46a3c8e4abc5add0983
---

# الشبكات

تشرح هذه الصفحة كيف تصبح الخدمات التي تعمل داخل Docker daemons معزولة متاحة من الإنترنت. تغطي نظام الوكيل العكسي، وعلامات Docker للتوجيه، وشهادات TLS، وDNS، وتوجيه منافذ TCP/UDP.

لمعرفة كيف تحصل الخدمات على عناوين IP الاسترجاعية ونظام الفتحات `.rediacc.json`، راجع [الخدمات](/ar/docs/services#شبكات-الخدمات-rediaccjson).

## عزل الشبكة

يتم عزل كل مستودع تلقائياً على مستوى النواة باستخدام خطافات الشبكة. يتطلب ذلك Linux kernel 6.1 أو أحدث. لا يلزم أي تكوين.

- **إعادة كتابة الربط التلقائية**: يمكن للخدمات الربط بـ `0.0.0.0` أو `127.0.0.1` كالمعتاد. تعيد النواة كتابة العنوان بشفافية إلى عنوان IP الاسترجاعي المُعيَّن للخدمة. لا حاجة للربط الصريح بـ `${SERVICE_IP}`.
- **حجب الاتصالات بين المستودعات**: إذا حاولت خدمة الاتصال بعنوان IP استرجاعي خارج نطاق `/26` الخاص بمستودعها، تقوم النواة بحجبه. لا يمكن لعملية في المستودع (أ) الوصول إلى خدمات في المستودع (ب). الفورك هو الاستثناء الوحيد: اتصالاته نحو شبكة الأصل الفرعية يُعاد توجيهها إلى خدمات الفورك نفسه (انظر [الحدود](/ar/docs/limits))، بينما يبقى الأصل نفسه غير قابل للوصول.
- **لا تغييرات على التطبيق مطلوبة**: تستخدم الخدمات `0.0.0.0` أو `localhost` للربط، وتضمن النواة استماعها فقط على عنوان IP الاسترجاعي الصحيح. العزل شفاف تماماً.

## كيف يعمل

يستخدم Rediacc نظام وكيل من مكوّنين لتوجيه حركة المرور الخارجية إلى الحاويات:

1. **خادم التوجيه**، خدمة systemd تكتشف الحاويات العاملة عبر جميع Docker daemons الخاصة بالمستودعات. يفحص علامات الحاويات ويُنشئ تكوين التوجيه المقدَّم كنقطة نهاية YAML.
2. **Traefik**، وكيل عكسي يستعلم خادم التوجيه كل 5 ثوانٍ ويُطبّق المسارات المكتشفة. يتعامل مع توجيه HTTP/HTTPS، وإنهاء TLS، وتوجيه TCP/UDP.

يبدو التدفق كالتالي:

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ polls every 5s
           Route Server (discovers containers)
               ↓ inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Containers (bound to 127.x.x.x loopback IPs)
```

عند إضافة العلامات الصحيحة إلى حاوية وتشغيلها باستخدام `renet compose`، تصبح قابلة للتوجيه تلقائياً، دون الحاجة لتكوين وكيل يدوي.

> يُحافظ على مزامنة ملف خادم التوجيه الثنائي مع إصدار CLI الخاص بك. عند تحديث CLI لملف renet الثنائي على جهاز، يُعاد تشغيل خادم التوجيه تلقائياً (حوالي 1-2 ثانية). لا يتسبب ذلك في أي توقف، حيث يواصل Traefik خدمة حركة المرور بآخر تكوين معروف له أثناء إعادة التشغيل ويلتقط التكوين الجديد في الاستعلام التالي. اتصالات العملاء الحالية لا تتأثر. حاويات تطبيقك لا تُمس.

## علامات Docker

يُتحكم في التوجيه عبر علامات حاويات Docker. هناك مستويان:

### المستوى 1: علامات `rediacc.*` (تلقائية)

هذه العلامات تُضاف **تلقائياً** بواسطة `renet compose` عند تشغيل الخدمات. لا تحتاج لإضافتها يدوياً.

| العلامة | الوصف | مثال |
|---------|-------|------|
| `rediacc.service_name` | هوية الخدمة | `myapp` |
| `rediacc.service_ip` | عنوان IP الاسترجاعي المُعيَّن | `127.0.11.2` |
| `rediacc.network_id` | معرّف Docker daemon الخاص بالمستودع | `2816` |
| `rediacc.repo_name` | اسم المستودع | `marketing` |
| `rediacc.tcp_ports` | منافذ TCP التي تستمع عليها الخدمة | `8080,8443` |
| `rediacc.udp_ports` | منافذ UDP التي تستمع عليها الخدمة | `53` |

عندما تحتوي حاوية على علامات `rediacc.*` فقط (بدون `traefik.enable=true`)، يُنشئ خادم التوجيه **مساراً تلقائياً** باستخدام اسم المستودع والنطاق الفرعي للجهاز:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

على سبيل المثال، خدمة اسمها `myapp` في مستودع يسمى `marketing` على جهاز `server-1` ونطاق أساسي `example.com` تحصل على:

```
myapp.marketing.server-1.example.com
```

بالنسبة للفروع، يُدمج اسم الخدمة مع الكلمة المحجوزة `fork` والوسم:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

على سبيل المثال، فرع `marketing` الموسوم بـ `staging` يحصل على:

```
myapp-fork-staging.marketing.server-1.example.com
```

يقع كل عنوان URL للفرع تحت النطاق الفرعي للمستودع الأصل ويُغطى بشهادة البدل الموجودة، لذا لا تحتاج لشهادة جديدة. الفاصل `-fork-` يمنع التعارض مع أي أسماء خدمات حقيقية في المستودع الأصلي. للخدمات ذات النطاقات المخصصة، استخدم علامات المستوى 2 أو علامة `rediacc.domain`.

#### نطاق مخصص عبر `rediacc.domain`

يمكنك تعيين نطاق مخصص لخدمة باستخدام علامة `rediacc.domain` في ملف `docker-compose.yml`. يُدعم كل من الأسماء القصيرة والنطاقات الكاملة:

```yaml
labels:
  # اسم قصير, يُحل إلى cloud.example.com باستخدام baseDomain الخاص بالجهاز
  - "rediacc.domain=cloud"

  # نطاق كامل, يُستخدم كما هو
  - "rediacc.domain=cloud.example.com"
```

القيمة بدون نقاط تُعامل كاسم قصير ويُضاف إليها `baseDomain` الخاص بالجهاز تلقائياً. القيمة مع نقاط تُستخدم كنطاق كامل.

عند تكوين `machineName`، تحصل خدمات النطاق المخصص على **مسارين**: واحد على النطاق الأساسي (`cloud.example.com`) وآخر على النطاق الفرعي للجهاز (`cloud.server-1.example.com`).

### المستوى 2: علامات `traefik.*` (مُعرَّفة من المستخدم)

أضف هذه العلامات إلى ملف `docker-compose.yml` عندما تريد توجيه نطاق مخصص، أو TLS، أو نقاط دخول محددة. تعيين `traefik.enable=true` يُخبر خادم التوجيه باستخدام قواعدك المخصصة بدلاً من إنشاء مسار تلقائي.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

تستخدم هذه [صيغة علامات Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/) القياسية.

> **تلميح:** الخدمات الداخلية فقط (قواعد البيانات، التخزين المؤقت، طوابير الرسائل) **لا ينبغي** أن تحتوي على `traefik.enable=true`. تحتاج فقط إلى علامات `rediacc.*` التي تُضاف تلقائياً.

## كشف خدمات HTTP/HTTPS

### المتطلبات المسبقة

1. البنية التحتية مُكوَّنة على الجهاز ([إعداد الجهاز، تكوين البنية التحتية](/ar/docs/setup#تكوين-البنية-التحتية)):

   ```bash
   # بيانات اعتماد مشتركة (مرة واحدة لكل إعداد، تُطبّق على جميع الأجهزة)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # إعدادات خاصة بالجهاز
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. سجلات DNS تشير إلى نطاقك على عنوان IP العام للخادم (راجع [تكوين DNS](#تكوين-dns) أدناه).

### إضافة العلامات

أضف علامات `traefik.*` إلى الخدمات التي تريد كشفها في ملف `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # بدون علامات traefik, قاعدة البيانات داخلية فقط
```

| العلامة | الغرض |
|---------|-------|
| `traefik.enable=true` | تفعيل توجيه Traefik المخصص لهذه الحاوية |
| `traefik.http.routers.{name}.rule` | قاعدة التوجيه، عادةً `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | المنافذ المُستمع عليها: `websecure` (HTTPS IPv4)، `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | محلل الشهادات، استخدم `letsencrypt` لشهادات Let's Encrypt التلقائية |
| `traefik.http.services.{name}.loadbalancer.server.port` | المنفذ الذي يستمع عليه تطبيقك داخل الحاوية |

`{name}` في العلامات هو معرّف عشوائي، يجب فقط أن يبقى متسقاً عبر علامات الموجّه/الخدمة/الوسيط المرتبطة.

> **ملاحظة:** علامات `rediacc.*` (`rediacc.service_name`، `rediacc.service_ip`، `rediacc.network_id`) تُضاف تلقائياً بواسطة `renet compose`. لا تحتاج لإضافتها إلى ملف compose الخاص بك.

## شهادات TLS

يتم الحصول على شهادات TLS تلقائياً عبر Let's Encrypt باستخدام تحدي Cloudflare DNS-01. تُكوَّن بيانات الاعتماد مرة واحدة لكل إعداد (مشتركة عبر جميع الأجهزة):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

تستخدم المسارات التلقائية **شهادات بدل** على مستوى النطاق الفرعي للمستودع (`*.marketing.server-1.example.com`) بدلاً من شهادات لكل خدمة. تُوفَّر الشهادة تلقائياً بواسطة Traefik عند أول `repo up`، لا خطوة يدوية مطلوبة. تُعيد الفروع استخدام شهادة البدل الموجودة للمستودع الأصل، لذا لا تُطلق طلب شهادة جديدة. مسارات النطاق المخصص تستخدم شهادات بدل على مستوى الجهاز (`*.server-1.example.com`).

> **يتطلب بيانات اعتماد Cloudflare.** تستخدم شهادات البدل تحدي DNS-01. بدون `--cf-dns-token` (واختياريًا `--cert-email`)، لا يستطيع Traefik إكمال التحدي ولن يعمل HTTPS. يبقى HTTP وظيفياً. كوِّن بيانات الاعتماد باستخدام `rdc config infra set` قبل أول نشر.

لمسارات المستوى 2 مع `traefik.http.routers.{name}.tls.certresolver=letsencrypt`، يتم حقن أسماء نطاقات البدل SAN تلقائياً بناءً على اسم المضيف للمسار.

يحتاج رمز Cloudflare DNS API إلى إذن `Zone:DNS:Edit` للنطاقات التي تريد تأمينها.

### دورة حياة شهادة TLS

المسار الكامل الذي تسلكه شهادة Let's Encrypt من الإصدار حتى حاويات كل مستودع:

1. **الإصدار على المضيف.** حاوية Traefik على مستوى الجهاز (`rediacc-proxy`، منشورة في `/opt/rediacc/proxy/`) تمتلك تجديد ACME. تُخزّن كل الحالة في `/opt/rediacc/proxy/letsencrypt/acme.json` على المضيف. يُطلق التجديد تلقائياً قبل انتهاء الصلاحية بحوالي 30 يوماً، لا يلزم أي إجراء من المشغّل طالما تم تكوين `--cf-dns-token`.

2. **التفريغ لكل مستودع (اختياري).** الخدمات التي تحتاج إلى ملفات شهادات داخل حاويتها الخاصة (مثل خادم بريد يقرأ `.pem` مباشرة) تنشر حاوية `traefik-certs-dumper` صغيرة بجانبها. يقوم المفرِّغ بتثبيت `/opt/rediacc/proxy/letsencrypt` للقراءة فقط ويكتب الشهادة والمفتاح المُستخرجَين في مجلد بيانات المستودع كـ `cert.pem` / `key.pem`. لهذا أن يعمل، يجب أن يكون Docker daemon الخاص بالمستودع قد أُضيف `/opt/rediacc/proxy` إلى قائمة السماح بمساحة الاسم. هذا مُضمَّن افتراضياً.

3. **ذاكرة التخزين المؤقت من جانب العميل (`rediacc.json`).** يُخزّن CLI نسخة مضغوطة من `acme.json` تحت `acmeCertCache` في ملف تكوينك، مفهرسة بـ `baseDomain`. يتيح ذلك لأجهزة متعددة مشاركة الشهادات (عبر `rdc config cert-cache push -m <machine>`) ويعمل كسجل غير متصل بالشبكة.

**محفزات المزامنة لذاكرة التخزين المؤقت للعميل:**

- تلقائياً بعد `rdc repo up`، لكن فقط إذا كانت ذاكرة التخزين المؤقت المحلية لـ `baseDomain` الجهاز أقدم من 6 ساعات. تُترك ذاكرات التخزين المؤقت الحديثة كما هي حتى لا تُرهق SSH بعمليات النشر المتتالية.
- عند الطلب: `rdc config cert-cache pull -m <machine>` (سحب قسري) أو `rdc machine query --name <machine> --sync-certs` (سحب كأثر جانبي لاستعلام الحالة).
- عند `rdc config infra push`، تُدفع ذاكرة التخزين المؤقت إلى الجهاز (الشهادات المحلية ذات انتهاء الصلاحية الأطول تفوز على الشهادات البعيدة).

**صيانة ذاكرة التخزين المؤقت:**

- إدخالات المسارات التلقائية القديمة (النطاقات القديمة الموسومة بمعرف الشبكة مثل `service-3200.rediacc.io`) تُحذف خلال كل عملية سحب.
- الشهادات التي انتهت صلاحيتها `notAfter` بأكثر من 7 أيام تُزال تماماً. إنها خاملة وتُضخّم ذاكرة التخزين المؤقت فقط.
- `rdc config cert-cache clear` يمسح كل شيء؛ `rdc config cert-cache status` يُظهر السجل.

**استكشاف الأخطاء:** إذا انهار `traefik-certs-dumper` مع `/traefik/acme.json: no such file or directory`، فإن daemon المستودع لا يستطيع رؤية مخزن letsencrypt الخاص بالمضيف. تحقق من (أ) وجود `/opt/rediacc/proxy/letsencrypt/acme.json` على المضيف (هذه مسؤولية `rediacc-proxy` على مستوى المضيف)، و(ب) بدء تشغيل daemon المستودع بإصدار renet حديث بما يكفي يُدرج `/opt/rediacc/proxy` في قائمة السماح. أعد نشر المستودع باستخدام `rdc repo up` بعد ترقية renet للتطبيق.

> **تجريبي:** شُحنت وتيرة المزامنة التلقائية والحذف القائم على انتهاء الصلاحية في renet 0.9+. إصدارات CLI/renet الأقدم تستخدم مزامنة يدوية بحتة عبر `rdc config cert-cache pull`.

## توجيه منافذ TCP/UDP

للبروتوكولات غير HTTP (خوادم البريد، DNS، قواعد البيانات المكشوفة خارجياً)، استخدم توجيه منافذ TCP/UDP.

### الخطوة 1: تسجيل المنافذ

أضف المنافذ المطلوبة أثناء تكوين البنية التحتية:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

ينشئ هذا نقاط دخول Traefik باسم `tcp-{port}` و`udp-{port}`.

> بعد إضافة أو إزالة المنافذ، قم دائماً بتشغيل `rdc config infra push` لتحديث تكوين الوكيل.

### الخطوة 2: إضافة علامات TCP/UDP

استخدم علامات `traefik.tcp.*` أو `traefik.udp.*` في ملف compose الخاص بك:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

المفاهيم الأساسية:
- **`HostSNI(\`*\`)`** يطابق أي اسم مضيف (للبروتوكولات التي لا ترسل SNI، مثل SMTP العادي)
- **`tls.passthrough=true`** يعني أن Traefik يُمرر اتصال TLS الخام دون فك التشفير، التطبيق يتعامل مع TLS بنفسه
- أسماء نقاط الدخول تتبع الاصطلاح `tcp-{port}` أو `udp-{port}`

### مثال TCP بسيط (قاعدة البيانات)

لكشف قاعدة بيانات خارجياً بدون TLS passthrough (Traefik يُمرر TCP الخام):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

المنفذ 5432 مُكوَّن مسبقاً (انظر أدناه)، لذا لا يلزم إعداد `--tcp-ports`.

> **ملاحظة أمنية:** كشف قاعدة بيانات للإنترنت يُشكّل خطراً. استخدم هذا فقط عندما يحتاج العملاء البعيدون إلى وصول مباشر. في معظم الإعدادات، احتفظ بقاعدة البيانات داخلية واتصل عبر تطبيقك.

### المنافذ المُكوَّنة مسبقاً

المنافذ TCP/UDP التالية لها نقاط دخول افتراضياً (لا حاجة لإضافتها عبر `--tcp-ports`). يتم إنشاء نقاط الدخول فقط لعائلات العناوين المُكوَّنة، نقاط دخول IPv4 تتطلب `--public-ipv4`، ونقاط دخول IPv6 تتطلب `--public-ipv6`:

| المنفذ | البروتوكول | الاستخدام الشائع |
|--------|-----------|-----------------|
| 80 | HTTP | الويب (إعادة توجيه تلقائي إلى HTTPS) |
| 443 | HTTPS | الويب (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | النطاق الديناميكي (تخصيص تلقائي) |

## تكوين DNS

### DNS التلقائي (Cloudflare)

عند تكوين `--cf-dns-token`، يقوم `rdc config infra push` تلقائياً بإنشاء سجلات DNS اللازمة في Cloudflare:

| السجل | النوع | المحتوى | أُنشئ بواسطة |
|-------|-------|---------|-------------|
| `server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `push-infra` |
| `*.server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `repo up` |

سجلات مستوى الجهاز تُنشأ بواسطة `push-infra` وتغطي مسارات النطاق المخصص (`rediacc.domain`). سجلات البدل لكل مستودع تُنشأ تلقائياً بواسطة `repo up` وتغطي المسارات التلقائية لذلك المستودع.

هذه العملية متساوية القوة: تُحدَّث السجلات الموجودة إذا تغير عنوان IP، وتُترك دون تغيير إذا كانت صحيحة بالفعل.

يجب إنشاء سجل البدل للنطاق الأساسي (`*.example.com`) يدوياً إذا كنت تستخدم تسميات نطاق مخصصة مثل `rediacc.domain=erp`.

### DNS اليدوي

إذا لم تكن تستخدم Cloudflare أو تدير DNS يدوياً، أنشئ سجلات A (IPv4) و/أو AAAA (IPv6):

```
# النطاق الفرعي للجهاز (لمسارات النطاق المخصص مثل rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# سجلات بدل لكل مستودع (للمسارات التلقائية مثل myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# سجل بدل النطاق الأساسي (لخدمات النطاق المخصص مثل rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

مع تكوين Cloudflare DNS، تُنشأ سجلات البدل لكل مستودع تلقائياً بواسطة `repo up`. مع أجهزة متعددة، يحصل كل جهاز على سجلات DNS خاصة به تشير إلى عنوان IP الخاص به.

## الوسائط

وسائط Traefik تُعدّل الطلبات والاستجابات. طبّقها عبر العلامات.

### HSTS (أمان نقل HTTP الصارم)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### تخزين رفع الملفات الكبيرة مؤقتاً

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### وسائط متعددة

اربط الوسائط بفصلها بفواصل:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

للقائمة الكاملة للوسائط المتاحة، راجع [وثائق وسائط Traefik](https://doc.traefik.io/traefik/middlewares/overview/).

## التشخيص

إذا لم تكن الخدمة متاحة، اتصل بالخادم عبر SSH وتحقق من نقاط نهاية خادم التوجيه:

### فحص الصحة

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

يعرض الحالة العامة، وعدد الموجّهات والخدمات المكتشفة، وما إذا كانت المسارات التلقائية مُفعّلة.

### المسارات المكتشفة

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

يسرد جميع موجّهات HTTP وTCP وUDP مع قواعدها ونقاط دخولها وخدمات الخلفية.

### تخصيصات المنافذ

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

يعرض تخصيصات منافذ TCP وUDP للمنافذ المُخصصة ديناميكياً.

### المشاكل الشائعة

| المشكلة | السبب | الحل |
|---------|-------|------|
| الخدمة غير موجودة في المسارات | الحاوية لا تعمل أو العلامات مفقودة | تحقق بـ `docker ps` على daemon المستودع؛ تحقق من العلامات |
| الشهادة لم تُصدر | DNS لا يشير إلى الخادم، أو رمز Cloudflare غير صالح | تحقق من حل DNS؛ تحقق من أذونات رمز Cloudflare API |
| 502 Bad Gateway | التطبيق لا يستمع على المنفذ المُعلن | تحقق من أن التطبيق يعمل وأن المنفذ يتطابق مع `loadbalancer.server.port` |
| منفذ TCP غير قابل للوصول | المنفذ غير مسجل في البنية التحتية | شغّل `rdc config infra set --tcp-ports ...` و`push-infra` |
| خادم التوجيه يعمل بإصدار قديم | تم تحديث الملف الثنائي لكن الخدمة لم تُعد تشغيلها | يحدث تلقائياً عند التوفير؛ يدوياً: `sudo systemctl restart rediacc-router` |
| ترحيل STUN/TURN غير قابل للوصول | عناوين الترحيل مُخزنة عند بدء التشغيل | أعد إنشاء الخدمة بعد تغييرات DNS أو IP حتى تلتقط تكوين الشبكة الجديد |

## مثال كامل

ينشر هذا تطبيق ويب مع قاعدة بيانات PostgreSQL. التطبيق متاح للعموم على `app.example.com` مع TLS؛ قاعدة البيانات داخلية فقط.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # بدون علامات traefik, داخلي فقط
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

أنشئ سجل A يوجّه `app.example.com` إلى عنوان IP العام لخادمك:

```
app.example.com   A   203.0.113.50
```

### النشر

```bash
rdc repo up --name my-app -m server-1
```

في غضون ثوانٍ قليلة، يكتشف خادم التوجيه الحاوية، ويلتقط Traefik المسار، ويطلب شهادة TLS، ويصبح `https://app.example.com` مباشراً.
