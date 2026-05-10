---
title: "Gizli Bilgileri Yönetin"
description: "Dağıtım zamanı kimlik bilgilerini fork'ların erişemeyeceği bir yere koyun. Tasarım gereği yalnızca yazılabilir."
category: "Tutorials"
subcategory: advanced
order: 8
language: tr
sourceHash: "0b4d72c80b489e12"
---

# Gizli Bilgileri Yönetin

Gerçek uygulamalar gerçek kimlik bilgilerine ihtiyaç duyar: Stripe canlı anahtarı, veritabanı parolası, API token'ı. Bunları depoya koymak yanlış bir tercihtir; çünkü bir fork, şifreli görüntünün içindeki her şeyi devralır. Aniden sandbox'ınız gerçek müşteri kartlarını faturalıyor olabilir.

Doğru yer `rdc repo secret`'tır. İki iletim modu, tasarım gereği yalnızca yazılabilir ve fork boş başlar.

## Öğreticiyi izleyin

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## Tuzak: depodaki `.env`

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

Çoğu ekip `.env` dosyasını depoya koyar. Göz önündeki tercih bu.

Sonra fork alırlar.

Fork, üst görüntünün bayt bayt kopyasıdır. `.env`'de ne varsa fork'un `.env`'sinde de vardır. Fork'un container'ları başlar. Aynı Stripe anahtarını okurlar. Üretim kimlik bilgileriyle aynı Stripe API'ını çağırırlar. Stripe tarafından bakıldığında, o çağrı *sizden* gelmiştir.

Bu kötü bir gün demektir.

## Gizli bilgi ayarlayın

Çözüm `rdc repo secret`'tır. `env` modunda bir gizli bilgi ayarlayın. Değer, container'ın içinde ortam değişkeni olarak yer alır:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Dikkat edilmesi gereken iki nokta:

- `--mode env`. Değer ortam değişkeni olarak yer alır.
- `--current ""`. Boş dize. Bunu önceden değeri olmayan, yepyeni bir gizli bilgi olarak tanımlıyoruz.

Hassas her şey için `file` modunda bir tane daha ayarlayın:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file` modu, değeri container'ın ortamına hiçbir zaman koymaz. Docker'ın standart mekanizmasını kullanarak `/run/secrets/stripe_key` yoluna yazar.

Neler ayarladığınızı listeleyin:

```bash
time rdc repo secret list --name my-app
```

Adları ve modları görürsünüz. **Değer yok.** Liste hiçbir zaman değerleri göstermez.

## Compose'a bağlayın

`docker-compose.yml`'yi açın. Her iki moda da başvurun:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}`, `env` modudur: `renet`'in compose sarmalayıcısı bunu dağıtım sırasında gizli deponuzdan genişletir.

`secrets:` bloğu, Docker'ın standart mekanizmasını kullanan `file` modudur. Host yolu, aynı compose'un hem üst hem de fork'lar için çalışması amacıyla `${REDIACC_NETWORK_ID}` kullanır. Her fork'un kendi ağ kimliği vardır.

Dağıtın:

```bash
time rdc repo up --name my-app -m my-server
```

## Container içinde doğrulayın

Her iki mod da artık container'ın içinde olmalıdır. Env modundaki gizli bilgiyi kontrol edin:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. Env modundaki gizli bilgi container'ın ortamına ulaştı.

Şimdi file modundakine bakın:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. Dosya, Docker'ın standart gizli bilgi mekanizması aracılığıyla bağlandı.

## Geri okuyamazsınız

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Şimdi insanları şaşırtan kısım:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Bir özet alırsınız. **Değeri değil.** Değeri döndüren bir bayrak yoktur. Düz metin değeri geri verecek herhangi bir komut da yoktur.

Bu, GitHub Actions modelidir: yalnızca yazılabilir. `--current <değer>` girerek ön koşulun geçtiğini izleyerek bir gizli bilgiyi bildiğinizi kanıtlayabilirsiniz. Ancak Rediacc'tan değeri söylemesini isteyemezsiniz.

Değeri kaybettiniz mi? **Gözetlemeyin. Döndürün.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret`, ön koşulu atlar. Denetim günlüğü bunu bir döndürme olarak işaretler: açık, kasıtlı.

Eski değeri hatırlıyorsanız bunun yerine kanıtlayın:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

Bu daha güvenli yoldur. "Yanlış terminaldeyim" hatasını yakalar.

## Fork'un sonuç darbesi

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Tuzağı hatırlıyor musunuz? Depoyu fork'layın ve bakın:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Boş.**

Fork'un Stripe anahtarı yok. Veritabanı parolası yok. API token'ı yok. Fork'taki container'lar `${REDIACC_SECRET_STRIPE_KEY}`'i işleyemez. `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` yolundaki dosya yoktur.

Fork sizi taklit edemez.

Test için fork'ta gizli bilgi isterseniz, bunları sandbox değerleriyle açıkça fork üzerinde ayarlayın:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Artık fork, Stripe sandbox'ına bağlanır. Üretim kimlik bilgileri hiçbir zaman üretimi terk etmedi.

## Özet

- `rdc repo secret`, kimlik bilgilerinizi depo görüntüsünün dışına koyar.
- Fork onlara erişemez.
- `get` bir özet döndürür, değeri asla.
- Unuttuğunuzda döndürün. Gözetlemeyin.

Fork'un takip edemeyeceği gizli bilgiler.

---

Sonraki: [Ağ ve Alan Adları](/en/docs/tutorial-networking).
