---
title: "Hub"
description: "توفير بيئات حاويات مصادق عليها لكل مستخدم مع Docker daemon خاص لكل مستخدم واختيار قوالب متعددة ونقاط حفظ/استعادة CRIU وسجلات تدقيق وجمع مهملات جذور البيانات."
category: "Guides"
order: 14
language: ar
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

يوفر Hub بيئات حاويات لكل مستخدم خلف مصادقة OAuth. يزور المستخدمون عنوان URL واحد، ويصادقون مع أي مزود OAuth2، ويتم توجيههم بشفافية إلى حاويتهم الشخصية. يتم إنشاء الحاويات عند الطلب، ويحصل كل مستخدم على Docker daemon معزول خاص به، ويتم حفظ الجلسات الخاملة كنقاط تفتيش CRIU لاستئنافها فوراً.

يتم تكوين كل شيء من خلال تسميات `docker-compose.yml`. يعمل Hub نفسه كخدمة systemd مضيفة يتم إنشاؤها بواسطة أمر `renet hub install` من ملف Compose الخاص بمستودعك. تحدد المستودعات السلوك، ويتولى Hub المصادقة والتوجيه ودورة الحياة والعزل لكل مستخدم.

## كيف يعمل

1. يزور مستخدم `code.example.com` (أو `term.` أو `desktop.` أو أي بادئة مكونة أخرى).
2. يتحقق Hub من ملف تعريف ارتباط الجلسة. إذا كان غائباً، يتم إعادة توجيه المستخدم إلى مزود OAuth2 المكون (Nextcloud أو Keycloak أو GitHub أو غيره).
3. بعد المصادقة، يحدد Hub المستخدم ويبحث عن حاويته.
4. إذا لم تكن هناك حاوية، يُنشئ Hub Docker daemon مخصصاً لذلك المستخدم على المضيف، ثم يُنشئ حاويته.
5. يتم توجيه الطلب عبر الوكيل العكسي إلى حاوية المستخدم عبر شبكة الحلقة الداخلية.
6. يتم حفظ الحاويات الخاملة كنقاط تفتيش CRIU ويتم إيقاف daemon الخاص بالمستخدم لتحرير الذاكرة. عند تسجيل الدخول التالي يعود الـ daemon ويستعيد CRIU حالة الحاوية في ثوانٍ.

## البداية السريعة

أضف Hub كخدمة في ملف `docker-compose.yml` الخاص بمستودعك. الخدمة مُعلَّمة بـ `install_as=systemd` لتعمل كخدمة مضيفة بدلاً من حاوية Docker (مطلوب لإدارة daemon لكل مستخدم، التي تستخدم systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # تعيين المسارات: بادئة النطاق الفرعي -> المنفذ على حاويات المستخدم
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # قالب الحاوية
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # مسارات Traefik (مزود الملف؛ يقرأ rediacc-router هذه التسميات أيضاً)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

أنشئ `hub/.env` ببيانات اعتماد مزود OAuth2 الخاص بك:

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

ثبّت وحدة systemd المضيفة (مرة واحدة، يتطلب صلاحيات root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

يقرأ هذا الأمر خدمات `install_as=systemd` ويكتب:

- `/etc/systemd/system/rediacc-hub.service` (الوحدة)
- `/etc/rediacc/hub/hub.labels.yaml` (تسميات القالب)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (مسارات مزود ملف Traefik)

ثم `systemctl daemon-reload && systemctl enable --now rediacc-hub`. للإزالة: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## مرجع أمر التثبيت

| الأمر | الغرض |
|---------|---------|
| `sudo renet hub install <compose-file>` | ترجمة خدمات `install_as=systemd` من ملف Compose إلى مواد مضيفة وتشغيل الوحدة. |
| `sudo renet hub uninstall <compose-file>` | إيقاف وتعطيل وإزالة جميع المواد الخاصة بالخدمات. يتم الحفاظ على جذور البيانات ضمن `<workspace>/<user>-docker/`. |
| `sudo renet hub gc <workspace-dir>` | تنظيف جذور البيانات المهجورة لكل مستخدم (الافتراضي: أقدم من 30 يوماً بلا daemon نشط). الأعلام: `--max-age=30d`، `--dry-run`. |
| `renet hub status` | حالة JSON لجميع الحاويات عبر واجهة برمجة Hub المُشغَّلة. |
| `renet hub stop <username>` | إيقاف حاوية مستخدم محدد. |

## التكوين

يوجد تكوين Hub بالكامل في تسميات Compose الخاصة بخدمة Hub. تذهب الأسرار (OAuth client_secret وsession_secret) إلى `hub/.env` لا إلى التسميات.

### تعيين المسارات

قم بتعيين بادئات النطاقات الفرعية إلى المنافذ على حاويات المستخدم. يقرأ Hub هذه التسميات لمعرفة أين يوكّل كل طلب.

| التسمية | الوصف | مثال |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | يعين `{prefix}.{domain}` إلى هذا المنفذ على حاوية المستخدم | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

يحتاج كل مسار أيضاً إلى موجه Traefik مطابق يشير إلى منفذ Hub (7112). يتولى Hub التوجيه لكل مستخدم داخلياً استناداً إلى اسم المضيف.

### قالب الحاوية

حدد كيف تبدو حاويات المستخدم. يقرأ Hub هذه التسميات ويستخدمها عند إنشاء حاوية جديدة.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.image` | صورة الحاوية | قيمة علم `--container-image` |
| `rediacc.hub.command` | أمر البدء (متوافق مع bash -c) | لا شيء |
| `rediacc.hub.user` | مستخدم الحاوية (يوصى بغير root) | `vscode` |
| `rediacc.hub.workspace` | نقطة تحميل مساحة العمل داخل الحاوية | `/workspace` |
| `rediacc.hub.shm_size` | حجم الذاكرة المشتركة بالبايت | `1073741824` (1 جيجابايت) |
| `rediacc.hub.docker` | `per-user` لتوفير dockerd مخصص لكل مستخدم (موصى به بشدة) | `""` |

تدعم تسمية `command` توسيع `${SERVICE_IP}` و`__SERVICE_IP__` (الأخير يتجنب التوسيع المسبق من Compose) لعنوان IP الحلقي المعين للحاوية.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Docker Daemon لكل مستخدم

عند تعيين `rediacc.hub.docker=per-user`، يحصل كل مستخدم على نسخة `dockerd` مخصصة على المضيف تُوصَّل كـ `/var/run/docker.sock` داخل حاويته. يتيح ذلك:

- تشغيل `docker ps` و`docker run` و`docker build` كاملاً داخل بيئة المستخدم بدون حاويات ذات امتيازات أو Docker-in-Docker.
- عزل كامل بين المستخدمين (لا يستطيع المستخدم أ رؤية حاويات أو صور المستخدم ب).
- جذر بيانات BTRFS خاص بكل مستخدم في `<workspace-dir>/<user>-docker/.rediacc/docker/data`، يُحفظ عبر الجلسات بحيث تبقى الصور المخزنة مؤقتاً بعد دورات نقطة التفتيش الخاملة.

يتم تخصيص الـ daemons في نطاق معرّف شبكة مخصص يبدأ من 32768. يُسجّل ملف `.networkid` في جذر بيانات كل مستخدم معرّفه المخصص حتى يلتقط المستخدمون العائدون نفس الـ daemon.

### حدود الموارد

عيّن حدود موارد لكل مستخدم لمنع أي مستخدم منفرد من استهلاك جميع موارد المضيف. تُطبَّق الحدود على كل من حاوية المستخدم ونسخة dockerd الخاصة به (عبر systemd `CPUQuota=` / `MemoryMax=`).

| التسمية | الوصف | مثال |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | قيمة systemd CPUQuota | `200%` (نواتان) |
| `rediacc.hub.limits.memory` | قيمة systemd MemoryMax | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

يتم وضع الـ daemons في شريحة systemd `rediacc.slice` بحيث ترث حدود مستوى الشريحة.

### دعم القوالب المتعددة

قدّم أنواع بيئات متعددة. يختار المستخدمون قالباً عند تسجيل الدخول بزيارة `https://code.example.com/_hub/login?template=python` (يمر الاختيار عبر حالة OAuth). يؤدي تغيير القوالب عند تسجيل الدخول لاحقاً إلى إعادة بناء الحاوية.

عرّف القوالب بتسميات `rediacc.hub.templates.<name>.<field>`. تستمر تسميات `rediacc.hub.image` / `rediacc.hub.command` / إلخ في تعريف القالب "الافتراضي" الضمني للمستخدمين الذين لا يختارون قالباً.

```yaml
labels:
  # القالب الافتراضي عند حذف ?template=...
  - "rediacc.hub.template=fulldev"

  # بيئة VS Code + سطح مكتب + طرفية متكاملة.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # VS Code خفيف الوزن فقط.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # بيئة مخصصة للغة Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### خطافات دورة الحياة

شغّل أوامر داخل حاوية المستخدم في نقاط دورة الحياة. تعمل الخطافات بصفة مستخدم الحاوية (لا root).

| التسمية | وقت التشغيل | مثال |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | بعد إنشاء الحاوية (تسجيل الدخول الأول) | استنساخ المستودعات، تثبيت التبعيات |
| `rediacc.hub.hook.checkpoint.pre_dump` | قبل نقطة تفتيش CRIU لجلسة خاملة | إيقاف الـ daemons التي لا يمكن حفظ نقطة تفتيش لها (X server، dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | بعد استعادة CRIU | إعادة تشغيل الـ daemons التي أُوقفت في pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### نقطة التفتيش / الاستعادة

عند تعيين `--checkpoint`، يتم حفظ حاويات المستخدم الخاملة كنقاط تفتيش CRIU ويتم إيقاف daemon الخاص بكل مستخدم لتحرير الذاكرة. عند تسجيل الدخول التالي يُعاد تشغيل الـ daemon ويستعيد CRIU حالة الحاوية من القرص، محافظاً على الملفات المفتوحة والعمليات الجارية وجلسات الطرفية. يبلغ وقت الاستئناف المعتاد بضع ثوانٍ بغض النظر عن حجم العمل.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | تفعيل نقطة تفتيش CRIU لحاويات المستخدم | `false` |

مرّر `--checkpoint` و`--idle-timeout` غير الصفري (مثلاً `30m`) في أمر Hub. تقع مجلدات نقاط التفتيش في `<workspace-dir>/<user>/.checkpoint/`.

إذا فشل CRIU 3 مرات متتالية لأحد المستخدمين، يتم تعطيل نقطة التفتيش لذلك المستخدم ويصبح الاحتياط هو الإيقاف وإعادة الإنشاء.

### الوضع المؤقت

بشكل افتراضي، مساحات عمل المستخدم دائمة (تبقى بعد إعادة التشغيل). يوفر الوضع المؤقت بيئة نظيفة عند كل تسجيل دخول، وهو مفيد للعروض التوضيحية أو التدريب أو CI.

| التسمية | الوصف | القيمة الافتراضية |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` أو `ephemeral` | `persistent` |

في الوضع المؤقت تستخدم مساحة العمل tmpfs (مدعومة بالذاكرة) ويتم حذف الحاوية تلقائياً عند الإيقاف.

### مهلة الخمول

| العلم | الوصف | القيمة الافتراضية |
|------|-------------|---------|
| `--idle-timeout=<dur>` | إيقاف/حفظ نقطة تفتيش الحاويات الخاملة لأطول من هذه المدة | `0` (معطّل) |

`0` يُبقي الحاويات تعمل إلى الأبد. قيمة عملية هي `30m`: يحرر المستخدمون الخاملون الذاكرة بعد نصف ساعة، ويستأنف المستخدمون العائدون في ثوانٍ عبر CRIU.

### التحكم في الوصول

| المتغير | الوصف |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | مجموعات مفصولة بفواصل مسموح لها باستخدام Hub (عندما يكشف المزود عن مطالبات المجموعات) |
| `HUB_ADMIN_USERS` | أسماء مستخدمين مسؤولين مفصولة بفواصل. يستطيع المسؤولون رؤية وتحكم حاويات المستخدمين الآخرين في لوحة المعلومات. |

## سجل التدقيق

يتم إلحاق كل حدث حاوية/صورة بمبادرة المستخدم (إنشاء، بدء، إيقاف، تدمير، قتل، سحب، دفع) على daemon الخاص بالمستخدم كسجل JSON مقسوم بأسطر إلى `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

تبقى الإدخالات بعد نقطة تفتيش/استعادة CRIU (يُعاد تسليح تدفق التدقيق عند الاستعادة). استخدم `logrotate` للتحكم في استخدام القرص؛ مثال تكوين:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## لوحة المعلومات

يتضمن Hub لوحة معلومات للخدمة الذاتية في `/_hub/dashboard`. تعرض:

- جميع البيئات العاملة مع حالتها
- القالب المختار
- روابط الخدمات (نقرة واحدة لفتح الكود أو الطرفية أو سطح المكتب أو أي مسار آخر)
- مؤقتات الخمول
- استخدام القرص لكل مستخدم وعدد الحاويات الجارية وعدد الصور
- يرى المسؤولون جميع الحاويات؛ يرى المستخدمون العاديون حاوياتهم فقط

يتم أخذ الإحصائيات كل 30 ثانية.

## جمع مهملات جذر البيانات

تتراكم جذور البيانات لكل مستخدم على المضيفات طويلة التشغيل. جدوّل `renet hub gc` لتنظيف المهجورة منها. يعمل مؤقت systemd بشكل جيد:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

يسجّل `--dry-run` المرشحين بدون حذف. يصبح جذر البيانات مؤهلاً عندما يكون ملف `.networkid` الخاص به أقدم من `--max-age` ولم يعد الـ daemon المسجّل مكوّناً على المضيف.

## إعداد OAuth

يعمل Hub مع أي مزود OAuth2 قياسي. يتم التكوين عبر متغيرات البيئة.

| المتغير | الوصف | مطلوب |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | معرف عميل OAuth2 | نعم |
| `HUB_OAUTH_CLIENT_SECRET` | سر عميل OAuth2 | نعم |
| `HUB_OAUTH_AUTHORIZE_URL` | نقطة نهاية التفويض للمزود | نعم |
| `HUB_OAUTH_TOKEN_URL` | نقطة نهاية الرمز للمزود | نعم |
| `HUB_OAUTH_USERINFO_URL` | نقطة نهاية معلومات المستخدم للمزود | نعم |
| `HUB_OAUTH_USERINFO_PATH` | مسار منقوط لاستخراج اسم المستخدم من استجابة JSON | نعم |
| `HUB_OAUTH_REDIRECT_URI` | تجاوز عنوان URL لإعادة الاتصال (يحسب تلقائياً إذا كان فارغاً) | لا |
| `HUB_OAUTH_SCOPES` | نطاقات إضافية (مفصولة بمسافات) | لا |
| `HUB_SESSION_SECRET` | سلسلة سداسية عشرية 32+ بايت لتوقيع ملفات تعريف الارتباط | موصى به |

### أمثلة المزودين

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

## أمثلة

### بيئة التطوير (VS Code + طرفية + سطح مكتب)

بيئة تطوير كاملة مع OpenVSCode Server وطرفية ويب (ttyd) وسطح مكتب noVNC. يحصل المستخدمون على Docker daemon خاص بداخلها.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... موجهات Traefik لكل بادئة ...
```

### بيئة Jupyter Notebook

بيئة علوم البيانات مع JupyterLab:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### تطبيق ويب بسيط (مؤقت)

بيئة خدمة واحدة تبدأ من جديد عند كل تسجيل دخول:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## أدلة ذات صلة

- [**الخدمات**](/ar/docs/services) -- دورة حياة Rediaccfile، أنماط Compose
- [**الشبكات**](/ar/docs/networking) -- تسميات Docker، توجيه Traefik، شهادات TLS
- [**النسخ الاحتياطي والاستعادة**](/ar/docs/backup-restore) -- استمرارية مساحة العمل والاستعادة
- [**بيئات التطوير**](/ar/docs/development-environments) -- استنساخ الإنتاج لبيئات التطوير
