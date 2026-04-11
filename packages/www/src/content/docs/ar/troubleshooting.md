---
title: "استكشاف الأخطاء وإصلاحها"
description: "حلول للمشاكل الشائعة مع SSH والإعداد والمستودعات والخدمات وDocker."
category: "Guides"
order: 10
language: ar
sourceHash: "756725b9a8fb168f"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# استكشاف الأخطاء وإصلاحها

المشاكل الشائعة وحلولها. عند الشك، ابدأ بتشغيل `rdc doctor` لإجراء فحص تشخيصي شامل.

## فشل اتصال SSH

- تحقق من إمكانية الاتصال يدوياً: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- شغّل `rdc config machine scan-keys server-1` لتحديث مفاتيح المضيف
- تأكد من تطابق منفذ SSH: `--port 22`
- اختبر بأمر بسيط: `rdc term connect -m server-1 -c "hostname"`

## عدم تطابق مفتاح المضيف

إذا تمت إعادة تثبيت الخادم أو تغيّرت مفاتيح SSH الخاصة به، سترى "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

يقوم هذا الأمر بجلب مفاتيح المضيف الجديدة وتحديث إعداداتك.

## فشل إعداد الجهاز

- تأكد من أن مستخدم SSH لديه صلاحيات sudo بدون كلمة مرور، أو قم بتكوين `NOPASSWD` للأوامر المطلوبة
- تحقق من مساحة القرص المتوفرة على الخادم
- شغّل مع `--debug` للحصول على مخرجات مفصّلة: `rdc config machine setup server-1 --debug`

## فشل إنشاء المستودع

- تحقق من اكتمال الإعداد: يجب أن يكون مجلد مخزن البيانات موجوداً
- تحقق من مساحة القرص على الخادم
- تأكد من تثبيت ملف renet الثنائي (أعد تشغيل الإعداد إذا لزم الأمر)

## فشل بدء تشغيل الخدمات

- تحقق من صياغة Rediaccfile: يجب أن يكون Bash صالحاً
- تأكد من أن Rediaccfile يستخدم `renet compose --` (وليس `docker compose`)
- تحقق من إمكانية الوصول إلى صور Docker (فكّر في تشغيل `renet compose -- pull` في `up()`)
- تحقق من سجلات الحاوية باستخدام مقبس Docker الخاص بالمستودع:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

أو عرض جميع الحاويات:

```bash
rdc machine containers server-1
```

## أخطاء رفض الصلاحيات

- عمليات المستودع تتطلب صلاحيات root على الخادم (renet يعمل عبر `sudo`)
- تحقق من أن مستخدم SSH الخاص بك في مجموعة `sudo`
- تأكد من أن مجلد مخزن البيانات لديه الصلاحيات الصحيحة

## مشاكل مقبس Docker

كل مستودع لديه Docker daemon خاص به. عند تشغيل أوامر Docker يدوياً، يجب تحديد المقبس الصحيح:

```bash
# باستخدام rdc term (مُعدّ تلقائياً):
rdc term connect -m server-1 -r my-app -c "docker ps"

# أو يدوياً مع المقبس:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

استبدل `2816` بمعرّف الشبكة الخاص بمستودعك (يوجد في `rediacc.json` أو `rdc repo status`).

## `docker run` بدون شبكة، فشل `apt update`، تعليق `curl`

داخل شل المستودع، يؤدي تشغيل حاوية بدون `--network host` إلى الحصول على حاوية معزولة بواجهة loopback فقط، وبدون DNS، وبدون اتصال خارجي. أوامر مثل `apt update` أو `pip install` أو `curl https://...` أو أي جلب شبكي ستفشل فوراً بأخطاء DNS.

هذا مقصود. نموذج الشبكات في Rediacc هو **شبكة المضيف لكل خدمة**، ويفرضه `renet compose`. شبكة Docker bridge الافتراضية مع NAT ستتجاوز عزل الـ loopback على مستوى النواة الذي يمنع مستودعاً من الوصول إلى خدمات مستودع آخر، لذا يتم تكوين Docker daemon لكل مستودع بالقيم `"bridge": "none"` و `"iptables": false`. لا يوجد جسر قابل للتوجيه لكي ترتبط به حاوية `docker run` البسيطة.

**للحصول على وصول شبكي في حاوية عابرة، استخدم شبكة المضيف:**

```bash
# Inside a repository shell (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Now apt update, curl, pip install all work.
```

**لخدمات الإنتاج، استخدم Rediaccfile مع `renet compose`** بدلاً من `docker run` مباشرة. يحقن `renet compose` تلقائياً `network_mode: host` وتسميات IP للخدمة وتسميات توجيه Traefik. راجع [الخدمات](/ar/docs/services) للتفاصيل.

## رفض صلاحيات VS Code على ملفات sandbox

عند الاتصال باستخدام `rdc vscode connect -m <machine> -r <repo>`، ربما رأيت أخطاء مثل `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` بعد جلسة VS Code سابقة. كان سبب ذلك اختلاط ملكية الملفات داخل مجلد sandbox، الذي كان يحتوي على ملفات كتبها كل من مستخدم SSH الخاص بك والمستخدم الداخلي `rediacc`.

تعالج الإصدارات الحديثة من renet هذا عبر:

- إنشاء مساحة عمل sandbox لكل مستودع (`/mnt/rediacc/.interim/sandbox/<repo>/`) بالمجموعة `rediacc` وبت set-group-ID (الوضع `2775`)، بحيث يرث كل ملف يُكتب تحتها المجموعة الصحيحة.
- تطبيق `umask 002` داخل وقت تشغيل sandbox حتى تُنشأ الملفات الجديدة قابلة للكتابة على مستوى المجموعة (`0664`/`0775`).
- تطبيع شجرة `.vscode-server/` الحالية عند بدء التشغيل بحيث يتم إصلاح الملفات القديمة من قبل الإصلاح تلقائياً.

إذا ظهرت لك أخطاء صلاحيات بعد ذلك، أعد تشغيل Docker daemon الخاص بالمستودع مرة واحدة عبر `sudo systemctl restart rediacc-docker-<network-id>` من شل على الجهاز لتشغيل تمرير التطبيع، ثم أعد محاولة `rdc vscode connect`.

## فشل بدء الـ daemon بعد ترقية renet

قبل كل بدء، يعيد `renet daemon start-foreground` كتابة `daemon.json` و `containerd.toml` في مجلد تكوين المستودع من القوالب الحالية، بحيث يلتقط مستودعٌ أُنشئ تكوينه بإصدار أقدم من renet تلقائياً الصيغة الجديدة. لست بحاجة إلى تشغيل أي أمر ترحيل، ولست بحاجة إلى إعادة توليد وحدة systemd يدوياً. فقط أعد تشغيل الخدمة:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

إذا كانت الوحدة لا تزال تفشل، تحقق من السجل بحثاً عن خطأ محدد:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## إنشاء الحاويات على Docker Daemon خاطئ

إذا ظهرت حاوياتك على Docker daemon الخاص بالنظام المضيف بدلاً من daemon المستودع المعزول، فالسبب الأكثر شيوعاً هو استخدام `sudo docker` داخل Rediaccfile.

يقوم `sudo` بإعادة تعيين متغيرات البيئة، لذلك يُفقد `DOCKER_HOST` ويعود Docker إلى مقبس النظام (`/var/run/docker.sock`). يحظر Rediacc هذا تلقائياً، ولكن إذا واجهته:

- **استخدم `docker` مباشرة**, وظائف Rediaccfile تعمل بالفعل بصلاحيات كافية
- إذا كنت مضطراً لاستخدام sudo، استخدم `sudo -E docker` للحفاظ على متغيرات البيئة
- تحقق من Rediaccfile الخاص بك بحثاً عن أي أوامر `sudo docker` وأزل `sudo`

## الطرفية لا تعمل

إذا فشل `rdc term` في فتح نافذة الطرفية:

- استخدم الوضع المضمّن مع `-c` لتشغيل الأوامر مباشرة:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- أجبر الطرفية الخارجية باستخدام `--external` إذا كان الوضع المضمّن يواجه مشاكل
- على Linux، تأكد من تثبيت `gnome-terminal` أو `xterm` أو محاكي طرفية آخر

## تشغيل التشخيصات

```bash
rdc doctor
```

يتحقق هذا الأمر من بيئتك وتثبيت renet وإعدادات الإعداد وحالة المصادقة. يُبلِغ كل فحص بحالة OK أو Warning أو Error مع شرح مختصر.
