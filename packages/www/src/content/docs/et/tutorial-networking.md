---
title: "Võrgustik ja domeenid"
description: "Tee oma rakendus interneti kaudu kättesaadavaks domeeni, automaatse TLS-i ja Traefik pöördproksi abil."
category: "Tutorials"
subcategory: advanced
order: 9
language: et
sourceHash: "9f72a61ed1ff4cb9"
---

# Võrgustik ja domeenid

Sinu rakendus töötab, kuid keegi ei pääse sellele veel ligi. See juhendvideo annab sulle päris domeeni, automaatse TLS-i Let's Encrypt kaudu ja Traefik proksi, mis avastab sinu konteinerid automaatselt. Sul on vaja domeeni Cloudflare'is ja API tokenit.

## Vaata juhendvideot

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## Neli sammu

![Token, configure, push, deploy](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Hangi** oma Cloudflare API token.
2. **Seadista** infrastruktuur `rdc`-s.
3. **Tõuka** see oma serverisse.
4. **Juuruta** proksi.

## 1. samm: Cloudflare API token

Oma Cloudflare armatuurlaual mine **My Profile → API Tokens** ja loo token **Zone DNS Edit** õigusega. Kopeeri tokeni väärtus. Sa näed seda ainult üks kord.

## 2. samm: seadista infrastruktuur

Teavita `rdc`-d oma avalikust IP-st, baasdomäänist, sertifikaadi e-postist ja tokenist:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Asenda IP, domeen, e-post ja token enda omadega.

`--cert-email` ja `--cf-dns-token` on jagatud kõigi sinu masinate vahel, seega seadistad need ainult üks kord.

## 3. samm: tõuka serverisse

```bash
time rdc config infra push -m my-server
```

See loob DNS-kirjed Cloudflare'is automaatselt ja valmistab proksi konfiguratsiooni sinu serveris ette.

## 4. samm: juuruta proksi

Proksi ise ei tööta veel. Juuruta see sisseehitatud `proxy` mallist väikese repositooriumi sees nimega `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

See ongi kõik. Traefik töötab nüüd. Sinu rakendus on kättesaadav aadressil:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik avastab sinu konteinerid iga 5 sekundi järel. TLS sertifikaadid tulevad Let's Encryptist automaatselt. Käsitsi proksi konfigureerimine pole vajalik.

---

Edasi: [Tootmisrežiim](/en/docs/tutorial-production-mode).
