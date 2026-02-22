---
title: البنية التحتية
description: 'كيف يعمل Rediacc: بنية الأداتين، أوضاع التشغيل، نموذج الأمان، وهيكل الإعدادات.'
category: Concepts
order: 0
language: ar
sourceHash: 58ba0da9645bb9dd
---

# البنية التحتية

إذا لم تكن متاكدا من الاداة المناسبة، راجع [rdc vs renet](/ar/docs/rdc-vs-renet).

تشرح هذه الصفحة كيف يعمل Rediacc من الداخل: بنية الأداتين، أوضاع التشغيل، نموذج الأمان، وهيكل الإعدادات.

## Full Stack Overview

Traffic flows from the internet through a reverse proxy, into isolated Docker daemons, each backed by encrypted storage:

![Full Stack Architecture](/img/arch-full-stack.svg)

Each repository gets its own Docker daemon, loopback IP subnet (/26 = 64 IPs), and LUKS-encrypted BTRFS volume. The route server discovers running containers across all daemons and feeds routing configuration to Traefik.

## بنية الأداتين

يستخدم Rediacc ملفين تنفيذيين يعملان معاً عبر SSH:

![بنية الأداتين](/img/arch-two-tool.svg)

- **rdc** يعمل على محطة عملك (macOS أو Linux أو Windows). يقرأ الإعدادات المحلية، ويتصل بالأجهزة البعيدة عبر SSH، ويستدعي أوامر renet.
- **renet** يعمل على الخادم البعيد بصلاحيات الجذر. يدير صور الأقراص المشفرة بـ LUKS، وعمليات Docker المعزولة، وتنسيق الخدمات، وإعدادات الوكيل العكسي.

كل أمر تكتبه محلياً يُترجم إلى استدعاء SSH ينفّذ renet على الجهاز البعيد. لن تحتاج أبداً إلى الاتصال بالخوادم يدوياً عبر SSH.

## أوضاع التشغيل

يدعم Rediacc ثلاثة أوضاع، يحدد كل منها مكان تخزين الحالة وكيفية تنفيذ الأوامر.

![أوضاع التشغيل](/img/arch-operating-modes.svg)

### الوضع المحلي

الوضع الافتراضي للاستضافة الذاتية. تُخزّن جميع الحالات في `~/.rediacc/config.json` على محطة عملك.

- اتصالات SSH مباشرة بالأجهزة
- لا حاجة لخدمات خارجية
- مستخدم واحد، محطة عمل واحدة
- يُنشأ السياق باستخدام `rdc context create-local`

### الوضع السحابي (تجريبي)

يستخدم واجهة برمجة تطبيقات Rediacc لإدارة الحالة والتعاون الجماعي.

- تُخزّن الحالة في واجهة برمجة التطبيقات السحابية
- فرق متعددة المستخدمين مع التحكم في الوصول بناءً على الأدوار
- وحدة تحكم ويب للإدارة المرئية
- يُنشأ السياق باستخدام `rdc context create`

> **ملاحظة:** أوامر الوضع السحابي تجريبية. فعّلها باستخدام `rdc --experimental <command>` أو بتعيين `REDIACC_EXPERIMENTAL=1`.

### وضع S3

يخزّن الحالة المشفرة في حاوية متوافقة مع S3. يجمع بين طبيعة الاستضافة الذاتية للوضع المحلي وإمكانية النقل بين محطات العمل.

- تُخزّن الحالة في حاوية S3/R2 كملف `state.json`
- تشفير AES-256-GCM بكلمة مرور رئيسية
- قابل للنقل: أي محطة عمل لديها بيانات اعتماد الحاوية يمكنها إدارة البنية التحتية
- يُنشأ السياق باستخدام `rdc context create-s3`

تستخدم الأوضاع الثلاثة نفس أوامر سطر الأوامر. الوضع يؤثر فقط على مكان تخزين الحالة وكيفية عمل المصادقة.

## مستخدم rediacc

عند تشغيل `rdc context setup-machine`، يُنشئ renet مستخدم نظام باسم `rediacc` على الخادم البعيد:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (لا يمكن تسجيل الدخول عبر SSH)
- **الغرض**: يمتلك ملفات المستودعات ويشغّل دوال Rediaccfile

لا يمكن الوصول إلى مستخدم `rediacc` عبر SSH مباشرة. بدلاً من ذلك، يتصل rdc بمستخدم SSH الذي قمت بتهيئته (مثل `deploy`)، وينفّذ renet عمليات المستودع عبر `sudo -u rediacc /bin/sh -c '...'`. هذا يعني:

1. يحتاج مستخدم SSH الخاص بك إلى صلاحيات `sudo`
2. جميع بيانات المستودع مملوكة لـ `rediacc`، وليس لمستخدم SSH الخاص بك
3. دوال Rediaccfile (`prep()` و `up()` و `down()`) تعمل بصفة `rediacc`

يضمن هذا الفصل أن بيانات المستودع لها ملكية متسقة بغض النظر عن مستخدم SSH الذي يديرها.

## عزل Docker

يحصل كل مستودع على عملية Docker معزولة خاصة به. عند تحميل مستودع، يبدأ renet عملية `dockerd` مخصصة بمقبس فريد:

![عزل Docker](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

على سبيل المثال، مستودع بمعرّف شبكة `2816` يستخدم:
```
/var/run/rediacc/docker-2816.sock
```

هذا يعني:
- الحاويات من مستودعات مختلفة لا يمكنها رؤية بعضها البعض
- كل مستودع له ذاكرة تخزين مؤقت خاصة للصور والشبكات والأحجام
- عملية Docker المضيفة (إن وُجدت) منفصلة تماماً

تُعيّن متغير البيئة `DOCKER_HOST` تلقائياً للمقبس الصحيح في دوال Rediaccfile.

## تشفير LUKS

المستودعات هي صور أقراص مشفرة بـ LUKS مخزّنة على مخزن بيانات الخادم (الافتراضي: `/mnt/rediacc`). كل مستودع:

1. لديه عبارة مرور تشفير مُولّدة عشوائياً ("بيانات الاعتماد")
2. يُخزّن كملف: `{datastore}/repos/{guid}.img`
3. يُحمّل عبر `cryptsetup` عند الوصول إليه

تُخزّن بيانات الاعتماد في ملف `config.json` المحلي ولكن **لا تُخزّن أبداً** على الخادم. بدون بيانات الاعتماد، لا يمكن قراءة بيانات المستودع. عند تفعيل التشغيل التلقائي، يُخزّن ملف مفتاح LUKS ثانوي على الخادم للسماح بالتحميل التلقائي عند الإقلاع.

## هيكل الإعدادات

تُخزّن جميع الإعدادات في `~/.rediacc/config.json`. فيما يلي مثال مشروح:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "storages": {
        "backblaze": {
          "provider": "b2",
          "vaultContent": { "...": "..." }
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**الحقول الرئيسية:**

| الحقل | الوصف |
|-------|-------|
| `mode` | `"local"` أو `"s3"` أو محذوف للوضع السحابي |
| `apiUrl` | `"local://"` للوضع المحلي، عنوان URL لواجهة برمجة التطبيقات للوضع السحابي |
| `ssh.privateKeyPath` | مفتاح SSH الخاص المستخدم لجميع اتصالات الأجهزة |
| `machines.<name>.user` | اسم مستخدم SSH للاتصال بالجهاز |
| `machines.<name>.knownHosts` | مفاتيح مضيف SSH من `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | معرّف UUID يحدد صورة القرص المشفرة |
| `repositories.<name>.credential` | عبارة مرور تشفير LUKS (**لا تُخزّن على الخادم**) |
| `repositories.<name>.networkId` | يحدد الشبكة الفرعية لعناوين IP (2816 + n*64)، يُعيَّن تلقائياً |
| `nextNetworkId` | عدّاد عام لتعيين معرّفات الشبكة |
| `universalUser` | تجاوز مستخدم النظام الافتراضي (`rediacc`) |

> يحتوي هذا الملف على بيانات حساسة (مسارات مفاتيح SSH، بيانات اعتماد LUKS). يُخزّن بصلاحيات `0600` (قراءة/كتابة للمالك فقط). لا تشاركه أو تضعه في نظام التحكم بالإصدارات.
