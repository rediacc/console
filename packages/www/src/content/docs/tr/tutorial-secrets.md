---
title: "Sırları yönetme"
description: "Depo başına sırları ayarlayın, compose'a bağlayın, konteynere ulaştıklarını doğrulayın, döndürün ve fork'ların hiçbir şey miras almadığını onaylayın."
category: "Tutorials"
order: 7
language: tr
sourceHash: "fb8bc967ed22fc10"
---

# Rediacc ile depo başına sırları nasıl yönetirsiniz

Gerçek uygulamaların kimlik bilgilerine ihtiyacı vardır: bir Stripe canlı anahtarı, bir veritabanı şifresi, bir API belirteci. Bunları koymak için yanlış yer deponun içidir. Bir fork, şifrelenmiş imajda bulunan her şeyi miras alır ve fork'un konteynerleri kendilerini dış servislere karşı ebeveyn olarak tanıtarak başlar. Doğru yer `rdc repo secret`'tır. Değerler şifrelenmiş imajın dışına iner, bu nedenle fork'lar boş bir sır haritasıyla başlar.

Bu derste sırrın her iki modunu ayarlar, bunları bir compose dosyasına bağlar, konteynere ulaştıklarını doğrular, birini döndürür ve bir fork'un hiçbir şey miras almadığını onaylarsınız.

## Ön koşullar

- Yapılandırma başlatılmış `rdc` CLI yüklü
- Sağlanmış bir makine ve oluşturulmuş bir depo (bkz. [Eğitim: Depo Yaşam Döngüsü](/tr/docs/tutorial-repos))
- Düzenleyebileceğiniz bir `Rediaccfile` ve `docker-compose.yml`

## Adım 1: Bir sır ayarla

İki teslim modu mevcuttur. `env`, değeri compose'un `${...}` enterpolasyonu için `REDIACC_SECRET_<KEY>` olarak dışa aktarır. `file`, değeri Docker compose'un `secrets:` bloğu ile kullanım için `/var/run/rediacc/secrets/<networkID>/<KEY>` adresindeki host tarafı tmpfs dosyasına yazar. Hassas her şey için `file` kullanın. env modundaki değerler `docker inspect` ve `/proc/<pid>/environ`'da görünür.

Yepyeni bir anahtarın ilk yazımı için, önceki bir değer olmadığını kabul etmek üzere `--current ""` (boş) geçirin.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Adım 2: Orada ne var listele

```bash
rdc repo secret list --name my-app
```

Çıktı, her sırrın adı ve modunu içeren JSON'dur. Değerler asla listelemede görünmez. Diskten bile getirilmezler.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Adım 3: Compose'a bağla

Her iki mod da aynı `docker-compose.yml`'den referans alınır:

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

Servisteki küçük harfli `stripe_key`, konteyner içindeki `/run/secrets/<name>` dosya adıdır. Host yolundaki büyük harfli `STRIPE_KEY`, ayarladığınız `--key` ile eşleşir. `${REDIACC_NETWORK_ID}` `renet compose` tarafından otomatik olarak enterpole edilir. Bu önemlidir çünkü ağ ID'si fork başınadır, bu nedenle aynı compose dosyası ebeveyn ve herhangi bir fork'ta çalışır (orada 6. adımda göreceğiniz gibi dosya basitçe var olmaz).

> **Depolar arası izolasyon zorunlu.** renet'in compose doğrulayıcısı, başka bir deponun ağ ID'sini hedefleyen herhangi bir `secrets: file:` (veya `configs: file:` veya `env_file:`) yolunu reddeder. Literal `${REDIACC_NETWORK_ID}` belirteci (veya kendi ağınızın tam sayısı) kabul edilen tek formdur ve `--unsafe` bunu geçersiz KILMAZ. Rediaccfile bash alt sürecinin etrafındaki Landlock korumalı alanı, dosya sistemi okumalarını da kendi ağınızın sırlar dizinine kapsar. Yani Rediaccfile'dan kötü niyetli `cat /var/run/rediacc/secrets/<diğer>/X` bile çekirdek katmanında EACCES ile başarısız olur. Etkinleştirmek için hiçbir şey yapmanıza gerek yok; koruma varsayılan olarak aktiftir.

## Adım 4: Dağıt ve doğrula

```bash
rdc repo up --name my-app -m server-1
```

Dağıtımdan sonra, her iki modun da indiğini doğrulamak için konteynere exec edin:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

Host tarafı tmpfs dosyasını doğrudan incelemek istiyorsanız:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Adım 5: Önceki değeri bilmeden döndür

`rdc repo secret get` ile bir özet okuyabilirsiniz ama asla düz metin değeri okuyamazsınız. Bu yazma-yalnızca modeldir. Saklanan bir değerin elinizdekiyle eşleştiğini doğrulamanız gerekiyorsa, onu `--current` aracılığıyla geçirin ve ön koşulun geçişini veya başarısızlığını izleyin:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

Önceki değeri tamamen unuttuysanız (parola yöneticiniz onu kaybetti veya depoyu miras aldınız), ön koşulu atlamak için `--rotate-secret` kullanın. Denetim günlüğü bunu yüksek sesle bir döndürme olarak kaydeder:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` ve `--rotate-secret` karşılıklı dışlayıcıdır. Birini seçin.

## Adım 6: Fork'ların hiçbir şey miras almadığını onayla

Bütün amaç: depoyu fork'layın ve fork'un sır listesini kontrol edin:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Boş. Fork'un konteynerleri `${REDIACC_SECRET_DB_HOST}`'u enterpole edemez (değişken ayarlanmamıştır, yani boş dize) ve `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY`'deki dosya basitçe var olmaz. Fork'un `repo up`'ı bunu compose `secrets:` bloğu aracılığıyla bağlamaya çalışırsa, dağıtım net bir hatayla başarısız olur. Tam olarak istediğiniz başarısızlık modu, çünkü bu, korumalı alanın dış servislere karşı üretim gibi davranamayacağı anlamına gelir.

Fork'ta sırları kullanmak için, bunları fork'a açıkça korumalı alan kapsamlı değerlerle ayarlayın:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Şimdi fork bir test veritabanı ve bir Stripe sandbox hesabıyla konuşur. Ebeveynin üretim kimlik bilgileri ebeveyni asla terk etmez.

## Temizlik

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## Ayrıca bakınız

- [Depolar § Sırlar](/tr/docs/repositories#secrets). Tam referans
- [RDC CLI Hızlı Notlar § Depo başına sırlar](/tr/docs/rdc-cheat-sheet#per-repo-secrets). Komut hızlı referansı
- [AI Aracı Güvenliği](/tr/docs/ai-agents-safety). Simetrik mutasyon kapısı ve hata zarflarındaki yapılandırılmış `next` aksiyon ipuçları
- [Servisler § Compose'da depo başına sırları kullanma](/tr/docs/services#using-per-repo-secrets-in-compose). Compose örüntü referansı
