---
title: "Hub"
description: "توفير بيئات حاويات مصادق عليها لكل مستخدم مع التوفير التلقائي وادارة الخمول ونقاط الحفظ/الاستعادة."
category: "Guides"
order: 14
language: ar
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

يوفر Hub بيئات حاويات لكل مستخدم خلف مصادقة OAuth. يزور المستخدمون عنوان URL واحد، ويصادقون مع اي مزود OAuth2، ويتم توجيههم بشفافية الى حاويتهم الشخصية. يتم انشاء الحاويات عند الطلب وادارتها تلقائيا.

يتم تكوين كل شيء من خلال تسميات `docker-compose.yml`. لا يعرف Hub ما يعمل داخل الحاويات ولا يهتم بذلك -- فهو يتولى المصادقة والتوجيه ودورة الحياة. المستودعات تحدد السلوك.

## كيف يعمل

![بنية Hub](/img/hub-architecture.svg)

1. يزور مستخدم `code.example.com`
2. يتحقق Hub من ملف تعريف ارتباط الجلسة. اذا كان غائبا، يتم اعادة توجيه المستخدم الى مزود OAuth2 المكون (Nextcloud، Keycloak، GitHub، الخ)
3. بعد المصادقة، يحدد Hub المستخدم ويبحث عن حاويته
4. اذا لم تكن هناك حاوية، يتم انشاء واحدة عند الطلب من القالب المكون
5. يتم توجيه الطلب عبر الوكيل العكسي الى حاوية المستخدم
6. يحدد Hub المنفذ الذي سيتم التوجيه اليه بناء على اسم المضيف (مثلا `code.` -> المنفذ 8080، `term.` -> المنفذ 7681)

يتم ايقاف الحاويات الخاملة تلقائيا او حفظها كنقطة تفتيش (CRIU) للاستئناف الفوري عند تسجيل الدخول التالي.

## البداية السريعة

اضف Hub كخدمة في ملف `docker-compose.yml` الخاص بمستودعك:

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # تعيين المسارات: بادئة النطاق الفرعي -> المنفذ على حاويات المستخدم
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # قالب الحاوية
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # مسارات Traefik (واحد لكل نطاق فرعي)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

انشئ `hub.env` مع بيانات اعتماد مزود OAuth2 الخاص بك:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

انشر باستخدام `rdc repo up`.

## التكوين

يوجد تكوين Hub بالكامل في تسميات Compose الخاصة بخدمة Hub نفسها. لا توجد ملفات تكوين داخل ملف Hub الثنائي.

### تعيين المسارات

قم بتعيين بادئات النطاقات الفرعية الى المنافذ على حاويات المستخدم. يقرا Hub هذه التسميات لمعرفة اين يوجه كل طلب.

| التسمية | الوصف | مثال |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | يعين `{prefix}.{domain}` الى هذا المنفذ على حاوية المستخدم | `rediacc.hub.route.code=8080` |

يمكنك تعريف اي عدد من المسارات. تتم مطابقة البادئة مع الجزء الاول من اسم المضيف:

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

يحتاج كل مسار ايضا الى موجه Traefik مطابق يشير الى منفذ Hub (7112). يتولى Hub التوجيه لكل مستخدم داخليا.

### قالب الحاوية

حدد كيف تبدو حاويات المستخدم. يقرا Hub هذه التسميات ويستخدمها عند انشاء حاوية جديدة لمستخدم.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.image` | صورة الحاوية | قيمة علم `--container-image` |
| `rediacc.hub.command` | امر البدء (متوافق مع bash -c) | لا شيء |
| `rediacc.hub.user` | مستخدم الحاوية (يوصى بغير root) | `vscode` |
| `rediacc.hub.workspace` | نقطة تحميل مساحة العمل داخل الحاوية | `/workspace` |
| `rediacc.hub.shm_size` | حجم الذاكرة المشتركة بالبايت | `1073741824` (1 جيجابايت) |

تدعم تسمية `command` توسيع `${SERVICE_IP}`، الذي يتم استبداله بعنوان IP الحلقي المعين للحاوية وقت الانشاء.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **تلميح:** استخدم `$$` للحصول على `$` حرفي في تسميات Compose لمنع التوسيع المبكر لمتغيرات البيئة بواسطة Docker Compose.

### حدود الموارد

حدد حدود الموارد لكل مستخدم لمنع اي مستخدم واحد من استهلاك جميع موارد المضيف.

| التسمية | الوصف | مثال |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | حد المعالج (النوى) | `2` |
| `rediacc.hub.limits.memory` | حد الذاكرة | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### خطافات دورة الحياة

قم بتشغيل اوامر داخل حاوية المستخدم في نقاط محددة من دورة الحياة.

| التسمية | وقت التشغيل | مثال |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | بعد انشاء الحاوية (تسجيل الدخول الاول) | استنساخ المستودعات، تثبيت التبعيات |
| `rediacc.hub.hook.on_start` | بعد بدء او استعادة الحاوية | تحميل الاسرار، تحديث الرموز |
| `rediacc.hub.hook.on_idle` | قبل ايقاف او حفظ نقطة تفتيش الحاوية | حفظ الحالة، دفع التغييرات |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### نقطة التفتيش / الاستعادة

عند التفعيل، يتم حفظ الحاويات الخاملة كنقطة تفتيش باستخدام CRIU بدلا من ايقافها. عند تسجيل الدخول التالي، يتم استعادة الحاوية من نقطة التفتيش في ثوان، مع الحفاظ على الحالة الدقيقة: الملفات المفتوحة، العمليات الجارية، جلسات الطرفية.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | تفعيل نقطة تفتيش CRIU لحاويات المستخدم | `false` |

مرر ايضا `--checkpoint` عند بدء Hub:

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...اعلام اخرى...
```

> **ملاحظة:** تتطلب نقطة التفتيش/الاستعادة ان يكون ملف CRIU الثنائي متاحا على المضيف وان تعمل الحاوية في وضع شبكة المضيف (الافتراضي لخدمات Rediacc).

### التحكم في الوصول

قيد من يمكنه استخدام Hub ومن لديه صلاحيات المسؤول.

| التسمية | الوصف | مثال |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | مجموعات مفصولة بفواصل مسموح لها باستخدام Hub | `developers,ops` |
| `rediacc.hub.admin_users` | اسماء مستخدمين مسؤولين مفصولة بفواصل | `alice,bob` |

يمكن للمستخدمين المسؤولين رؤية وادارة جميع الحاويات في لوحة المعلومات. يرى المستخدمون العاديون حاوياتهم فقط.

### الوضع المؤقت

بشكل افتراضي، مساحات عمل المستخدم دائمة (تبقى بعد اعادة تشغيل الحاوية). يوفر الوضع المؤقت بيئة نظيفة عند كل تسجيل دخول، وهو مفيد للعروض التوضيحية والتدريب او CI.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` او `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

في الوضع المؤقت، تستخدم مساحة العمل tmpfs (مدعومة بالذاكرة) ويتم حذف الحاوية تلقائيا عند الايقاف.

### دعم القوالب المتعددة

قدم انواع بيئات متعددة. يمكن للمستخدمين اختيار قالبهم عند تسجيل الدخول الاول او التبديل عبر لوحة المعلومات.

```yaml
labels:
  # القالب الافتراضي
  - "rediacc.hub.template.default=fulldev"

  # بيئة تطوير كاملة
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # خيار خفيف
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## اعداد OAuth

يعمل Hub مع اي مزود OAuth2 قياسي. يتم التكوين عبر متغيرات البيئة، وليس تسميات Compose (يجب الا تكون الاسرار في التسميات).

| المتغير | الوصف | مطلوب |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | معرف عميل OAuth2 | نعم |
| `HUB_OAUTH_CLIENT_SECRET` | سر عميل OAuth2 | نعم |
| `HUB_OAUTH_AUTHORIZE_URL` | نقطة نهاية التفويض للمزود | نعم |
| `HUB_OAUTH_TOKEN_URL` | نقطة نهاية الرمز للمزود | نعم |
| `HUB_OAUTH_USERINFO_URL` | نقطة نهاية معلومات المستخدم للمزود | نعم |
| `HUB_OAUTH_USERINFO_PATH` | مسار منقط لاستخراج اسم المستخدم من استجابة JSON | نعم |
| `HUB_OAUTH_REDIRECT_URI` | تجاوز عنوان URL لاعادة الاتصال (يحسب تلقائيا اذا كان فارغا) | لا |
| `HUB_OAUTH_SCOPES` | نطاقات اضافية (مفصولة بمسافات) | لا |
| `HUB_SESSION_SECRET` | سلسلة سداسية عشرية 32+ بايت لتوقيع ملفات تعريف الارتباط | موصى به |

### امثلة المزودين

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` هو مسار مفصول بنقاط في استجابة JSON. للكائنات المتداخلة مثل `{"ocs":{"data":{"id":"alice"}}}` في Nextcloud، استخدم `ocs.data.id`.

## لوحة المعلومات

يتضمن Hub لوحة معلومات للخدمة الذاتية في `/_hub/dashboard`. تعرض:

- جميع البيئات العاملة مع حالتها
- روابط الخدمات (نقرة واحدة لفتح الكود او الطرفية او سطح المكتب)
- مؤقتات الخمول واستخدام الموارد
- عناصر تحكم البدء/الايقاف
- يمكن للمستخدمين المسؤولين رؤية وادارة جميع الحاويات

يمكنك الوصول الى لوحة المعلومات بزيارة `https://code.example.com/_hub/dashboard` بعد المصادقة.

## امثلة

### بيئة التطوير (VS Code + طرفية + سطح مكتب)

بيئة تطوير كاملة مع OpenVSCode Server وطرفية ويب (ttyd) وسطح مكتب noVNC:

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### بيئة Jupyter Notebook

بيئة علوم البيانات مع JupyterLab:

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### تطبيق ويب بسيط

بيئة خدمة واحدة لاطار عمل ويب:

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## ادلة ذات صلة

- [**الخدمات**](/ar/docs/services) -- دورة حياة Rediaccfile، انماط Compose
- [**الشبكات**](/ar/docs/networking) -- تسميات Docker، توجيه Traefik، شهادات TLS
- [**النسخ الاحتياطي والاستعادة**](/ar/docs/backup-restore) -- استمرارية مساحة العمل والاستعادة
- [**بيئات التطوير**](/ar/docs/development-environments) -- استنساخ الانتاج لبيئات التطوير
