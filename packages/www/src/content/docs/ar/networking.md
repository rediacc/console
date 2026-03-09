---
title: الشبكات
description: >-
  كشف الخدمات باستخدام الوكيل العكسي، وعلامات Docker، وشهادات TLS، وDNS، وتوجيه
  منافذ TCP/UDP.
category: Guides
order: 6
language: ar
sourceHash: "51ec174f68da3b34"
---

# الشبكات

تشرح هذه الصفحة كيف تصبح الخدمات التي تعمل داخل Docker daemons معزولة متاحة من الإنترنت. تغطي نظام الوكيل العكسي، وعلامات Docker للتوجيه، وشهادات TLS، وDNS، وتوجيه منافذ TCP/UDP.

لمعرفة كيف تحصل الخدمات على عناوين IP الاسترجاعية ونظام الفتحات `.rediacc.json`، راجع [الخدمات](/ar/docs/services#شبكات-الخدمات-rediaccjson).

## كيف يعمل

يستخدم Rediacc نظام وكيل من مكوّنين لتوجيه حركة المرور الخارجية إلى الحاويات:

1. **خادم التوجيه** -- خدمة systemd تكتشف الحاويات العاملة عبر جميع Docker daemons الخاصة بالمستودعات. يفحص علامات الحاويات ويُنشئ تكوين التوجيه المقدَّم كنقطة نهاية YAML.
2. **Traefik** -- وكيل عكسي يستعلم خادم التوجيه كل 5 ثوانٍ ويُطبّق المسارات المكتشفة. يتعامل مع توجيه HTTP/HTTPS، وإنهاء TLS، وتوجيه TCP/UDP.

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

عند إضافة العلامات الصحيحة إلى حاوية وتشغيلها باستخدام `renet compose`، تصبح قابلة للتوجيه تلقائياً -- دون الحاجة لتكوين وكيل يدوي.

> The route server binary is kept in sync with your CLI version. When the CLI updates the renet binary on a machine, the route server is automatically restarted (~1–2 seconds). This causes no downtime — Traefik continues serving traffic with its last known configuration during the restart and picks up the new config on the next poll. Existing client connections are not affected. Your application containers are not touched.

## علامات Docker

يُتحكم في التوجيه عبر علامات حاويات Docker. هناك مستويان:

### المستوى 1: علامات `rediacc.*` (تلقائية)

هذه العلامات تُضاف **تلقائياً** بواسطة `renet compose` عند تشغيل الخدمات. لا تحتاج لإضافتها يدوياً.

| العلامة | الوصف | مثال |
|---------|-------|------|
| `rediacc.service_name` | هوية الخدمة | `myapp` |
| `rediacc.service_ip` | عنوان IP الاسترجاعي المُعيَّن | `127.0.11.2` |
| `rediacc.network_id` | معرّف Docker daemon الخاص بالمستودع | `2816` |
| `rediacc.repo_name` | Repository name | `marketing` |
| `rediacc.tcp_ports` | TCP ports the service listens on | `8080,8443` |
| `rediacc.udp_ports` | UDP ports the service listens on | `53` |

عندما تحتوي حاوية على علامات `rediacc.*` فقط (بدون `traefik.enable=true`)، يُنشئ خادم التوجيه **مساراً تلقائياً** باستخدام اسم المستودع والنطاق الفرعي للجهاز:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

على سبيل المثال، خدمة اسمها `myapp` في مستودع يسمى `marketing` على جهاز `server-1` ونطاق أساسي `example.com` تحصل على:

```
myapp.marketing.server-1.example.com
```

لكل مستودع مستوى نطاق فرعي خاص به، لذا لا تتعارض الفروع والمستودعات المختلفة أبداً. عند إنشاء نسخة من مستودع (مثل `marketing-staging`)، تحصل النسخة تلقائياً على مسارات مميزة. لخدمات ذات النطاقات المخصصة، استخدم علامات المستوى 2 أو علامة `rediacc.domain`.

#### نطاق مخصص عبر `rediacc.domain`

يمكنك تعيين نطاق مخصص لخدمة باستخدام علامة `rediacc.domain` في ملف `docker-compose.yml`. يُدعم كل من الأسماء القصيرة والنطاقات الكاملة:

```yaml
labels:
  # اسم قصير — يُحل إلى cloud.example.com باستخدام baseDomain الخاص بالجهاز
  - "rediacc.domain=cloud"

  # نطاق كامل — يُستخدم كما هو
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

1. البنية التحتية مُكوَّنة على الجهاز ([إعداد الجهاز -- تكوين البنية التحتية](/ar/docs/setup#تكوين-البنية-التحتية)):

   ```bash
   # بيانات اعتماد مشتركة (مرة واحدة لكل إعداد، تُطبّق على جميع الأجهزة)
   rdc config set-infra server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # إعدادات خاصة بالجهاز
   rdc config set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config push-infra server-1
   ```

2. سجلات DNS تشير إلى نطاقك على عنوان IP العام للخادم (راجع [تكوين DNS](#تكوين-dns) أدناه).

### إضافة العلامات

أضف علامات `traefik.*` إلى الخدمات التي تريد كشفها في ملف `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # بدون علامات traefik — قاعدة البيانات داخلية فقط
```

| العلامة | الغرض |
|---------|-------|
| `traefik.enable=true` | تفعيل توجيه Traefik المخصص لهذه الحاوية |
| `traefik.http.routers.{name}.rule` | قاعدة التوجيه -- عادةً `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | المنافذ المُستمع عليها: `websecure` (HTTPS IPv4)، `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | محلل الشهادات -- استخدم `letsencrypt` لشهادات Let's Encrypt التلقائية |
| `traefik.http.services.{name}.loadbalancer.server.port` | المنفذ الذي يستمع عليه تطبيقك داخل الحاوية |

`{name}` في العلامات هو معرّف عشوائي -- يجب فقط أن يكون متسقاً عبر علامات الموجّه/الخدمة/الوسيط المرتبطة.

> **ملاحظة:** علامات `rediacc.*` (`rediacc.service_name`، `rediacc.service_ip`، `rediacc.network_id`) تُضاف تلقائياً بواسطة `renet compose`. لا تحتاج لإضافتها إلى ملف compose الخاص بك.

## شهادات TLS

يتم الحصول على شهادات TLS تلقائياً عبر Let's Encrypt باستخدام تحدي Cloudflare DNS-01. تُكوَّن بيانات الاعتماد مرة واحدة لكل إعداد (مشتركة عبر جميع الأجهزة):

```bash
rdc config set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

تستخدم المسارات التلقائية **شهادات بدل** على مستوى النطاق الفرعي للمستودع (`*.marketing.server-1.example.com`) بدلاً من شهادات لكل خدمة. هذا يتجنب حدود معدل Let's Encrypt ويُسرّع بدء التشغيل. مسارات النطاق المخصص تستخدم شهادات بدل على مستوى الجهاز (`*.server-1.example.com`).

لمسارات المستوى 2 مع `traefik.http.routers.{name}.tls.certresolver=letsencrypt`، يتم حقن أسماء نطاقات البدل SAN تلقائياً بناءً على اسم المضيف للمسار.

يحتاج رمز Cloudflare DNS API إلى إذن `Zone:DNS:Edit` للنطاقات التي تريد تأمينها.

## توجيه منافذ TCP/UDP

للبروتوكولات غير HTTP (خوادم البريد، DNS، قواعد البيانات المكشوفة خارجياً)، استخدم توجيه منافذ TCP/UDP.

### الخطوة 1: تسجيل المنافذ

أضف المنافذ المطلوبة أثناء تكوين البنية التحتية:

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config push-infra server-1
```

ينشئ هذا نقاط دخول Traefik باسم `tcp-{port}` و`udp-{port}`.

### Plain TCP Example (Database)

To expose a database externally without TLS passthrough (Traefik forwards raw TCP):

```yaml
services:
  postgres:
    image: postgres:17
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 is pre-configured (see below), so no `--tcp-ports` setup is needed.

> **Security note:** Exposing a database to the internet is a risk. Use this only when remote clients need direct access. For most setups, keep the database internal and connect through your application.

> بعد إضافة أو إزالة المنافذ، قم دائماً بتشغيل `rdc config push-infra` لتحديث تكوين الوكيل.

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

      # IMAPS (port 993) — TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

المفاهيم الأساسية:
- **`HostSNI(\`*\`)`** يطابق أي اسم مضيف (للبروتوكولات التي لا ترسل SNI، مثل SMTP العادي)
- **`tls.passthrough=true`** يعني أن Traefik يُمرر اتصال TLS الخام دون فك التشفير -- التطبيق يتعامل مع TLS بنفسه
- أسماء نقاط الدخول تتبع الاصطلاح `tcp-{port}` أو `udp-{port}`

### المنافذ المُكوَّنة مسبقاً

المنافذ TCP/UDP التالية لها نقاط دخول افتراضياً (لا حاجة لإضافتها عبر `--tcp-ports`). يتم إنشاء نقاط الدخول فقط لعائلات العناوين المُكوَّنة — نقاط دخول IPv4 تتطلب `--public-ipv4`، ونقاط دخول IPv6 تتطلب `--public-ipv6`:

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
| 10000–10010 | TCP | النطاق الديناميكي (تخصيص تلقائي) |

## تكوين DNS

### DNS التلقائي (Cloudflare)

عند تكوين `--cf-dns-token`، يقوم `rdc config push-infra` تلقائياً بإنشاء سجلات DNS اللازمة في Cloudflare:

| السجل | النوع | المحتوى | أُنشئ بواسطة |
|-------|-------|---------|-------------|
| `server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `push-infra` |
| `*.server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | عنوان IP العام للجهاز | `repo up` |

سجلات مستوى الجهاز تُنشأ بواسطة `push-infra` وتغطي مسارات النطاق المخصص (`rediacc.domain`). سجلات البدل لكل مستودع تُنشأ تلقائياً بواسطة `repo up` وتغطي المسارات التلقائية لذلك المستودع.

هذه العملية متساوية القوة — يتم تحديث السجلات الموجودة إذا تغير عنوان IP، وتُترك دون تغيير إذا كانت صحيحة بالفعل.

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
| 502 Bad Gateway | التطبيق لا يستمع على المنفذ المُعلن | تحقق من أن التطبيق مرتبط بـ `{SERVICE}_IP` وأن المنفذ يتطابق مع `loadbalancer.server.port` |
| منفذ TCP غير قابل للوصول | المنفذ غير مسجل في البنية التحتية | شغّل `rdc config set-infra --tcp-ports ...` و`push-infra` |
| Route server running old version | Binary was updated but service not restarted | Happens automatically on provisioning; manual: `sudo systemctl restart rediacc-router` |
| STUN/TURN relay not reachable | Relay addresses cached at startup | Recreate the service after DNS or IP changes so it picks up the new network config |

## مثال كامل

ينشر هذا تطبيق ويب مع قاعدة بيانات PostgreSQL. التطبيق متاح للعموم على `app.example.com` مع TLS؛ قاعدة البيانات داخلية فقط.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
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
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # بدون علامات traefik — داخلي فقط
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
rdc repo up my-app -m server-1 --mount
```

في غضون ثوانٍ قليلة، يكتشف خادم التوجيه الحاوية، ويلتقط Traefik المسار، ويطلب شهادة TLS، ويصبح `https://app.example.com` مباشراً.
