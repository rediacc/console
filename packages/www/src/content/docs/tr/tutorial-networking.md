---
title: "Ağ ve Alan Adları"
description: "Uygulamanızı bir alan adı, otomatik TLS ve Traefik ters proxy ile internete açın."
category: "Tutorials"
subcategory: advanced
order: 9
language: tr
sourceHash: "9f72a61ed1ff4cb9"
---

# Ağ ve Alan Adları

Uygulamanız çalışıyor, ancak henüz kimse erişemiyor. Bu öğretici size gerçek bir alan adı, Let's Encrypt aracılığıyla otomatik TLS ve container'larınızı otomatik keşfeden bir Traefik proxy kuruluyor. Cloudflare'de bir alan adına ve API token'ına ihtiyacınız var.

## Öğreticiyi izleyin

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## Dört adım

![Token, configure, push, deploy](/img/tutorials/tutorial-networking/slide-1.svg)

1. Cloudflare API token'ınızı **alın**.
2. `rdc`'de altyapıyı **yapılandırın**.
3. Sunucunuza **gönderin**.
4. Proxy'yi **dağıtın**.

## Adım 1: Cloudflare API token'ı

Cloudflare panonuzda **My Profile → API Tokens** bölümüne gidin ve **Zone DNS Edit** iznine sahip bir token oluşturun. Token değerini kopyalayın. Yalnızca bir kez görebilirsiniz.

## Adım 2: Altyapıyı yapılandırın

`rdc`'ye genel IP'nizi, temel alan adınızı, sertifika e-postanızı ve token'ı bildirin:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

IP, alan adı, e-posta ve token'ı kendinizinkilerle değiştirin.

`--cert-email` ve `--cf-dns-token` tüm makinelerinizde paylaşılır; yalnızca bir kez ayarlarsınız.

## Adım 3: Sunucuya gönderin

```bash
time rdc config infra push -m my-server
```

Bu komut, Cloudflare'de DNS kayıtlarını otomatik olarak oluşturur ve sunucunuzda proxy yapılandırmasını hazırlar.

## Adım 4: Proxy'yi dağıtın

Proxy henüz çalışmıyor. Bunu `infra` adlı küçük bir depo içinde yerleşik `proxy` şablonundan dağıtın:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

Hepsi bu kadar. Traefik artık çalışıyor. Uygulamanıza şu adresten erişilebilir:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik, container'larınızı her 5 saniyede bir keşfeder. TLS sertifikaları Let's Encrypt'ten otomatik olarak gelir. Manuel proxy yapılandırması gerekmez.

---

Sonraki: [Üretim Modu](/en/docs/tutorial-production-mode).
