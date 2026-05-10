---
title: "الشبكات والنطاقات"
description: "اجعل تطبيقك متاحًا على الإنترنت بنطاق وTLS تلقائي ووكيل عكسي Traefik."
category: "Tutorials"
subcategory: advanced
order: 9
language: ar
sourceHash: "9f72a61ed1ff4cb9"
---

# الشبكات والنطاقات

تطبيقك يعمل، لكن لا أحد يستطيع الوصول إليه بعد. يُرشدك هذا الدرس للحصول على نطاق حقيقي وTLS تلقائي عبر Let's Encrypt ووكيل Traefik يكتشف حاوياتك تلقائيًا. تحتاج إلى نطاق على Cloudflare ورمز API.

## شاهد الدرس التعليمي

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## أربع خطوات

![Token, configure, push, deploy](/img/tutorials/tutorial-networking/slide-1.svg)

1. **احصل** على رمز Cloudflare API.
2. **اضبط** البنية التحتية في `rdc`.
3. **ادفع** إلى خادمك.
4. **انشر** الوكيل.

## الخطوة 1: رمز Cloudflare API

في لوحة تحكم Cloudflare الخاصة بك، انتقل إلى **My Profile > API Tokens** وأنشئ رمزًا بصلاحية **Zone DNS Edit**. انسخ قيمة الرمز. ستراها مرة واحدة فقط.

## الخطوة 2: ضبط البنية التحتية

أخبر `rdc` بعنوان IP العام ونطاقك الأساسي وبريد الشهادة والرمز:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

استبدل عنوان IP والنطاق والبريد والرمز بقيمك الخاصة.

يُشارَك `--cert-email` و`--cf-dns-token` عبر جميع أجهزتك، لذا تضبطهما مرة واحدة فقط.

## الخطوة 3: الدفع إلى الخادم

```bash
time rdc config infra push -m my-server
```

يُنشئ هذا سجلات DNS على Cloudflare تلقائيًا ويُحضّر إعداد الوكيل على خادمك.

## الخطوة 4: نشر الوكيل

الوكيل نفسه لا يعمل بعد. انشره من قالب `proxy` المدمج، داخل مستودع صغير باسم `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

هذا كل شيء. Traefik يعمل الآن. تطبيقك متاح على:

```
myapp.my-app.my-server.yourdomain.com
```

يكتشف Traefik حاوياتك كل 5 ثوانٍ. تأتي شهادات TLS من Let's Encrypt تلقائيًا. لا حاجة لأي إعداد وكيل يدوي.

---

التالي: [وضع الإنتاج](/en/docs/tutorial-production-mode).
