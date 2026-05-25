---
title: "مرجع الخادم"
description: "تخطيط المجلدات، وأوامر renet، وخدمات systemd، وسير العمل على الخادم البعيد."
category: "Concepts"
order: 3
language: ar
sourceHash: "40a33f0e2fa34548"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# مرجع الخادم

تغطي هذه الصفحة ما تجده عند الاتصال بخادم Rediacc عبر SSH: تخطيط المجلدات، وأوامر `renet`، وخدمات systemd، وسير العمل الشائعة.

يدير معظم المستخدمين الخوادم من خلال `rdc` من جهاز العمل الخاص بهم ولا يحتاجون إلى هذه الصفحة. هي موجودة لتصحيح الأخطاء المتقدم أو عندما تحتاج إلى العمل مباشرة على الخادم.

للاطلاع على البنية العامة، راجع [البنية التحتية](/ar/docs/architecture). للتعرف على الفرق بين `rdc` و `renet`، راجع [rdc مقابل renet](/ar/docs/rdc-vs-renet).

## تخطيط المجلدات

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## أوامر renet

`renet` هو الملف الثنائي على جانب الخادم. جميع الأوامر تتطلب صلاحيات الجذر (`sudo`).

### دورة حياة المستودع

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

تنفيذ أوامر compose على عملية Docker daemon الخاصة بمستودع معين:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

تنفيذ أوامر Docker مباشرة:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

يمكنك أيضًا استخدام مقبس Docker مباشرةً:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> قم دائمًا بتشغيل compose من المجلد الذي يحتوي على `docker-compose.yml`، وإلا لن يتمكن Docker من العثور على الملف.

### عزل نظام الملفات

```bash
# التحقق من دعم Landlock
renet sandbox-exec --detect

# تشغيل أمر داخل عزل Landlock (يُستخدم داخليًا)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

يطبق `sandbox-exec` قيود نظام الملفات الخاصة بـ Landlock LSM، ثم ينفذ الأمر المحدد. يُستدعى تلقائيًا بواسطة `sandbox-gateway` (معالج SSH ForceCommand) لجميع اتصالات مستوى المستودع.

### المحور لكل مستخدم (بيئات التطوير)

يمنح Hub كل مستخدم daemon Docker خاصًا به لبيئات التطوير، مستقلًا عن daemons `FlavorRediacc` الخاصة بكل مستودع.

```bash
# تثبيت / إزالة وحدات systemd الخاصة بـ Hub لكل مستخدم
sudo renet hub install
sudo renet hub uninstall

# تنظيف daemons Hub الخاملة لكل مستخدم
sudo renet hub gc
```

تعمل الـ daemons تحت أحد نوعين، يُحدد عبر `--flavor`:

```bash
# daemon معزول لكل مستودع (bridge=none, iptables=false) — الافتراضي
sudo renet daemon start-foreground --flavor=rediacc ...

# daemon Hub لكل مستخدم (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

يُتيح نوع `hub` شبكة bridge العادية حتى تتمتع الحاويات التي يشغّلها المستخدم باتصال خارجي؛ أما نوع `rediacc` فيفرض عزل loopback بين المستودعات. تُكتب سجلات تدقيق Hub في `/var/log/rediacc/hub/<user>.log`.

**الأعلام:**
- `--allow-rw`، `--allow-ro`، `--allow-exec`: قواعد مسارات Landlock
- `--home-overlay`: تركيب OverlayFS فوق المجلد الرئيسي لعزل الكتابة لكل مستودع
- `--sandbox-dir`: مساحة عمل لكل مستودع (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: تعيين دليل العمل وتحميل `.envrc` لبيئة المستودع
- `--run-as`: إسقاط الامتيازات للمستخدم المستهدف بعد الإعداد
- `--reset-home`: مسح طبقة التراكب الرئيسية لكل مستودع للبدء من جديد

**`sandbox-gateway`** هو معالج SSH ForceCommand المعين عبر `command=` في `authorized_keys`. يُشغّل مفتاح SSH الخاص بكل مستودع البوابة مع اسم المستودع المضمّن فيه، وهو أمر لا يمكن للعميل تزويره. تقوم البوابة ببناء وسائط sandbox-exec وتنفيذها عبر sudo.

### الوكيل والتوجيه

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

يتم اكتشاف المسارات تلقائيًا من تسميات الحاويات. راجع [الشبكات](/ar/docs/networking) لمعرفة كيفية تكوين تسميات Traefik.

### حالة النظام

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### إدارة العمليات الخلفية

يعمل كل مستودع بعملية Docker daemon خاصة به. يمكنك إدارتها بشكل فردي:

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### النسخ الاحتياطي والاستعادة

إرسال النسخ الاحتياطية إلى جهاز آخر أو إلى التخزين السحابي:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> يجب على معظم المستخدمين استخدام `rdc repo push/pull` بدلاً من ذلك. تتعامل أوامر `rdc` مع بيانات الاعتماد وتحليل الأجهزة تلقائيًا.

### نقاط التحقق (CRIU)

تحفظ نقاط التحقق حالة الحاويات قيد التشغيل بحيث يمكن استعادتها لاحقًا:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### الصيانة

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## خدمات systemd

ينشئ كل مستودع وحدات systemd التالية:

| الوحدة | الغرض |
|------|---------|
| `rediacc-docker-{id}.service` | عملية Docker daemon معزولة |
| `rediacc-docker-{id}.socket` | تفعيل مقبس Docker API |
| `rediacc-loopback-{id}.service` | إعداد عنوان IP الاسترجاعي |

الخدمات العامة المشتركة بين جميع المستودعات:

| الوحدة | الغرض |
|------|---------|
| `rediacc-router.service` | اكتشاف المسارات (المنفذ 7111) |
| `rediacc-autostart.service` | تحميل المستودعات عند الإقلاع |

## سير العمل الشائعة

### نشر خدمة جديدة

1. إنشاء مستودع مشفر:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. تحميله وإضافة ملفات `docker-compose.yml` و `Rediaccfile` و `.rediacc.json`.
3. تشغيله:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### الوصول إلى حاوية قيد التشغيل

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### العثور على مقبس Docker الذي يشغّل حاوية

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### إعادة إنشاء خدمة بعد تغيير التكوين

```bash
sudo renet compose -- up -d
```

قم بتشغيل هذا من المجلد الذي يحتوي على `docker-compose.yml`. يتم إعادة إنشاء الحاويات المُعدّلة تلقائيًا.

### فحص جميع الحاويات عبر جميع العمليات الخلفية

```bash
renet list containers
```

## نصائح

- استخدم دائمًا `sudo` لأوامر `renet compose` و `renet repository` و `renet docker`، فهي تحتاج صلاحيات الجذر لعمليات LUKS و Docker
- الفاصل `--` مطلوب قبل تمرير الوسائط إلى `renet compose` و `renet docker`
- قم بتشغيل compose من المجلد الذي يحتوي على `docker-compose.yml`
- تعيينات فتحات `.rediacc.json` ثابتة، لا تغيّرها بعد النشر
- استخدم مسارات `/run/rediacc/docker-{id}.sock` (قد يغيّر systemd مسارات `/var/run/` القديمة)
- قم بتشغيل `renet prune --dry-run` من وقت لآخر للعثور على الموارد المعزولة
- لقطات BTRFS (`renet backup`) سريعة وقليلة التكلفة، استخدمها قبل إجراء تغييرات محفوفة بالمخاطر
- المستودعات مشفرة بـ LUKS، فقدان كلمة المرور يعني فقدان البيانات
