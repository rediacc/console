---
title: "Lisans Zinciri ve Yetkilendirme"
description: "Kurcalamaya karşı kanıt lisans düzenleme, yerinde yetkilendirilmiş imzalama ve çatal algılama."
category: "Guides"
order: 8
language: tr
sourceHash: "5e6afbdf05c21b67"
---

# Lisans Zinciri ve Yetkilendirme

Rediacc, lisans düzenleme için kurcalamaya karşı kanıt hash zinciri ve yerinde dağıtımlar için bir yetkilendirme sertifikası modeli kullanır. Bu sayfa, sistemin kurcalama, tekrar oynatma saldırıları ve lisans paylaşımına karşı nasıl korunduğunu açıklar.

## Neden Zincir?

Bir hesap sunucusu tarafından düzenlenen her lisans, salt ekleme yapılan bir deftere kaydedilir. Her girdi, SHA-256 hash'i aracılığıyla öncekine bağlanarak bir zincir oluşturur. Zincirin kurcalamayı tespit edilebilir kılan üç özelliği vardır:

1. **Sıra numaraları** abonelik başına global ve monotoniktir. Girdileri atlamak veya yeniden sıralamak zinciri bozar.
2. **Zincir hash'leri** her girdiyi önceki tüm girdilere bağlar. Geçmişteki herhangi bir girdiyi değiştirmek, onu izleyen her girdiyi geçersiz kılar.
3. **Renet, gördüğü en yüksek sırayı** abonelik başına saklar. Sırasını geri alan bir sunucu anında tespit edilir.

## Lisans Nasıl Düzenlenir

CLI bir makine aktivasyonu veya depo lisansı talep ettiğinde, hesap sunucusu:

1. Abonelik için mevcut zincir başını (son sıra ve hash) okur.
2. Sonraki sıra numarasını ve önceki zincir hash'ini içeren lisans yükünü oluşturur.
3. Yükü Ed25519 ile imzalar.
4. `chainHash = SHA256(prevChainHash + ":" + signedPayload)` hesaplar.
5. Girdiyi düzenleme defterine atomik olarak ekler. İki eş zamanlı istek aynı sıra üzerinde çakışırsa, kaybeden bir sonraki sırayı yeniden alır ve yeniden imzalar.
6. İmzalı blob'u zincir hash'iyle birlikte CLI'ya döndürür.

`sequence` ve `prevChainHash`, imzalı yükün içindedir (dolayısıyla imzayı geçersiz kılmadan değiştirilemezler). `chainHash` zarfın üzerindedir (döngüsel bağımlılıktan kaçınmak için imzalamadan sonra hesaplanır).

## Renet Nasıl Doğrular

Renet çalıştıran her makine, son bilinen zincir durumunu `{licenseDir}/chain-state.json` adresinde saklar. Her lisans doğrulamasında Renet şunları kontrol eder:

| Kontrol | Başarısızlık anlamı |
|---|---|
| Ed25519 imzası geçerli | Lisans sahte veya kurcalanmış |
| `sequence > lastKnownSequence` | Sunucu zinciri geri aldı (tekrar oynatma saldırısı) |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | Zincir girdisi değiştirilmiş |
| `issuedAt >= lastKnownIssuedAt` | Saat manipülasyonu (sunucu saati geriye ayarlandı) |

Herhangi bir kontrol başarısız olursa, lisans reddedilir ve başarısızlık nedeni raporlanır.

## Yetkilendirme Sertifikaları (Yerinde)

Hava boşluklu veya kendi kendine barındırılan dağıtımlar için, yukarı akış hesap sunucusu kendi Ed25519 anahtarıyla lisans imzalama yetkisi veren bir **yetkilendirme sertifikası** düzenler. Sertifika, yerinde sunucunun yapabileceklerini kısıtlar.

### Sertifika yapısı

Bir yetkilendirme sertifikası şunları içerir:

- `subscriptionId` -- bu sertifikanın uygulandığı abonelik
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- içine gömülü plan limitleri
- `maxTotalIssuances` -- zincir sıra numarasının üst sınırı
- `delegatedPublicKey` -- yerinde sunucunun Ed25519 genel anahtarı (SPKI base64)
- `genesisHash` -- zincir başlangıç noktası (önceki sertifikadan devam veya "genesis")
- `genesisSequence` -- düzenleme zamanındaki zincir sırası. Zincir transit sırasında ilerlediğinde yeni sertifikanın yerel düzenleme defterindeki bilinen bir girdiye bağlandığını doğrulamak için `/onprem/cert-upload` tarafından kullanılır. Geriye dönük uyumluluk için isteğe bağlıdır (eksikse 0 olarak değerlendirilir).
- `validFrom`, `validUntil` -- geçerlilik penceresi (aşağıdaki geçerlilik politikası tarafından yönetilir)
- Yukarı akış ana Ed25519 anahtarı tarafından imzalanmıştır

### Yetkilendirme nasıl çalışır

1. Enterprise yöneticisi yerinde sunucuda bir Ed25519 anahtar çifti oluşturur.
2. Yönetici yukarı akıştan yetkilendirme sertifikası talep eder:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. Yukarı akış, sertifikayı ana anahtarıyla imzalar ve döndürür.
4. Yerinde sunucu sertifikayı ve özel anahtarını saklayarak lisans imzalamaya hazır hale gelir.
5. CLI yerinde sunucudan lisans talep ettiğinde, sunucu yetkilendirilmiş anahtarıyla imzalar ve sertifikaya referans ekler.
6. Renet **iki düzeyli doğrulama** yapar:
   - Sertifikanın imzasını içine gömülü yukarı akış ana anahtarına karşı doğrular.
   - Blob'un imzasını sertifikadaki yetkilendirilmiş anahtara karşı doğrular.
   - `blob.sequence <= cert.maxTotalIssuances` olduğunu kontrol eder.
   - Standart zincir kontrollerinin tamamını uygular.

Yerinde sunucu şunları yapamaz:
- Yetkilendirme sertifikasının plan limitleri dışında lisans oluşturamaz (renet reddeder).
- `maxTotalIssuances` toplam işlemi aşacak şekilde düzenleyemez (renet sıra taşmasını reddeder).
- Sertifikayı değiştiremez (yukarı akış imzası bozulur).

## Geçerlilik Politikası

Yetkilendirme sertifikasının geçerlilik penceresi, hem yukarı akış arka ucunda hem de müşteri portalı ön ucunda çalışan paylaşılan bir politika yardımcısı (`computeDelegationCertValidity()`) tarafından hesaplanır. Aynı girdiler her zaman aynı `validUntil` değerini üretir; böylece müşteriler oluşturma modalinde göndermeden önce geçerli geçerliliği önizleyebilir.

### Plan başına varsayılanlar ve tavanlar

| Plan | Varsayılan geçerlilik | Plan tavanı |
|---|---|---|
| COMMUNITY | 15 gün | 30 gün |
| PROFESSIONAL | 60 gün | 120 gün |
| BUSINESS | 90 gün | 180 gün |
| ENTERPRISE | 120 gün | 365 gün |

Varsayılan, çağıran `validDays` parametresini atladığında oluşturma uç noktasının seçtiği değerdir. Tavan, çağıranın talep edebileceği üst sınırdır.

### Abonelik başına geçersiz kılma

Yöneticiler, yönetici Abonelik Detay sayfası aracılığıyla belirli bir abonelikte özel bir `delegationCertDefaultDays` değeri ayarlayabilir. **Geçersiz kılma, o abonelik için hem varsayılanı hem de tavanı değiştirir** - özel müşteriler için bir kaçış kapısıdır (örn. COMMUNITY planında 200 günlük sertifika gerektiren bir kurumsal sözleşme). Zod şeması yine de mutlak `1..365` aralığını uygular.

### Sert tavan: abonelik sonu + 3 günlük yetkisiz kullanım süresi

Plan tavanı ve geçersiz kılmadan bağımsız olarak, her sertifika `subscription.expiresAt + 3 gün` ile sert biçimde sınırlandırılır (mevcut `SUBSCRIPTION_CONFIG.gracePeriodDays`). Bu şu anlama gelir:

- Süresiz abonelikler (`expiresAt = null`) için son kullanma sınırı uygulanmaz - yalnızca plan tavanı geçerlidir.
- Stripe üzerinden aylık faturalandırılan abonelikler için tavan, yaklaşık bir sonraki fatura tarihi + 3 gündür. Stripe her ay `expiresAt`'ı ilerlettiğinde, tavan da bununla birlikte hareket eder.
- Deneme abonelikleri için tavan, deneme sonu + 3 gündür.

### Etkin günler ve neden

Her oluşturma/yenileme yanıtı, arayanın sertifikanın neden bu geçerliliği aldığını görebilmesi için `effectiveDays` ve `reason` içerir:

| Neden | Anlam |
|---|---|
| `plan_default` | İstek yok, geçersiz kılma yok - plan başına varsayılan kullanıldı |
| `subscription_override` | İstek yok - abonelik başına geçersiz kılma varsayılan olarak kullanıldı |
| `requested` | Arayanın isteği tüm tavanlar dahilinde karşılandı |
| `plan_max_clamp` | Arayanın isteği plan başına tavanı aştı - aşağı kısıtlandı |
| `override_max_clamp` | Arayanın isteği abonelik başına geçersiz kılmayı aştı - aşağı kısıtlandı |
| `subscription_cap_clamp` | Aksi takdirde geçerli hedef, aboneliğin `expiresAt + 3 gün` tarihini aşacaktı |

Müşteri portalı oluşturma modali, müşterilerin körü körüne gönderme yapmaması için bu nedenleri canlı bir önizleme oluşturmak üzere kullanır ("18 günlük sertifika alacaksınız. Sertifika, abonelik bitiş tarihinizi 3 günden fazla aşamayacağı için kısıtlandı.").

### Uyarlanabilir yenileme eşiği

Yerinde otomatik yenileme döngüsü, Let's Encrypt'i model alan uyarlanabilir bir eşik kullanır:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

15 günlük COMMUNITY sertifikası 5 gün kala yenilenir. 90 günlük BUSINESS sertifikası 14 gün kala yenilenir (env tarafından yapılandırılan tavan devreye girer). 120 günlük ENTERPRISE sertifikası 14 gün kala yenilenir. Bu, kısa ömürlü sertifikaların yenilemeyi hemen tetiklemesini önlerken uzun ömürlü sertifikalara rahat bir tampon sağlar.

## Tek Aktif Uygulama

Bir aboneliğin **aynı anda en fazla bir aktif yetkilendirme sertifikası** olabilir (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Neden bir tane?

Her yerinde kurulum, `maxRepoLicenseIssuancesPerMonth`, `maxActivations` ve zincir bütünlüğünü kendi yerel düzenleme defterine karşı uygular. Yerinde sunucu, kullanım sayılarını yukarı akışla senkronize etmez - çevrimdışı yetenekli yetkilendirmenin tüm amacı budur.

Bir aboneliğin birden fazla aktif sertifikası olsaydı (kurulum başına bir tane), her kurulum limiti bağımsız olarak uygulardı:

- 3 aktif sertifikaya sahip 500/aylık abonelik pratikte **1.500 düzenleme/aya** kadar izin verir.
- Her biri genesis'e bağlı, olası denetim uzlaştırması olmayan üç paralel zincir.

Yerinde sunucular çevrimdışı çalışmak üzere tasarlandığından yukarı akış bu atlamayı tespit edemez. **Tek aktif, uygulanabilir tek modeldir.** Çoklu kurulum müşterileri (üretim + hazırlama + DR) kurulum başına bir abonelik satın almalıdır.

### Çakışma davranışı

`POST /admin/delegation-certs` ve `POST /portal/delegation-certs`, ikinci bir oluşturmayı şu şekilde reddeder:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

Müşteri portalı bunu sonuçları açıklayan özel bir diyalogla gösterir:

- **Yenile (önerilen)** - mevcut zinciri uzatır. Daha önce düzenlenmiş tüm depo lisansları çalışmaya devam eder.
- **İptal Et ve Oluştur** - mevcut zinciri atar ve genesis'ten yeniden başlar. ESKİ sertifikanın `validUntil` tarihi geçtikten sonra daha önce düzenlenmiş depo lisansları doğrulanamaz hale gelir. Yalnızca farklı bir imzalama anahtarına sahip yeni bir yerinde sunucuya geçiş yaptığınızda veya ele geçirilmiş bir anahtardan kurtulurken kullanın.

`renew()`, tek aktif durumu koruyan atomik bir değiş tokuştur ve 409 çakışma kontrolüne **tabi değildir**.

### Hız sınırı

Tek aktif olsa bile, kötü niyetli bir çağıran yukarı akış ana anahtar imzalama döngülerini tüketmek için `iptal -> oluştur -> iptal -> oluştur` döngüsü yapabilir. Her iki oluşturma uç noktası da mevcut `rateLimits` tablosu aracılığıyla abonelik başına **her döner 24 saatte 10 deneme** ile kısıtlar:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

Sayaç, sonuçtan bağımsız olarak her denemede artar (çakışma spam döngüleri de kısıtlanır).

## Çatal Algılama

Bir müşteri yetkilendirme sertifikasını başka bir tarafla paylaşırsa (veya aynı sertifikadan iki yerinde sunucu çalıştırırsa), zincirler ayrışır. Yukarı akış bunu yenileme zamanında tespit eder.

### Yenileme akışı

1. Yerinde yönetici, mevcut zincir başıyla `POST /admin/delegation-certs/renew` çağrısı yapar:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. Yukarı akış, zincir girdilerini kendi defter kaydına karşı karşılaştırır.
3. `currentChainHash`, `currentSequence`'taki yukarı akışın kayıtlı zinciriyle eşleşmiyorsa çatal algılanır:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. Yeni sertifikanın `genesisHash`'i mevcut zincir hash'ine ayarlanır; böylece eski zincir durumuna sahip makineler kaldıkları yerden devam edebilir.

Sertifika müşteri olmayan biriyle paylaşılırsa:
- Sertifikanın geçerlilik süresi boyunca kullanabilirler.
- İlk yenilemede, yukarı akış yalnızca bir zincir görür (meşru olan).
- Yeni sertifikanın `genesisHash`'i yalnızca meşru zincirle eşleşir.
- Paylaşılan zincirdeki makineler, saklanan `chainHash`'lerinin yeni sertifikanın `genesisHash`'ine bağlanmaması nedeniyle yeni lisansları hemen reddeder.

## Hava Boşluklu Yenileme

Yukarı akışa giden HTTPS erişimi olmayan yerinde kurulumlar için, yenileme akışı tamamen çevrimdışıdır. Döngüyü kapatan üç yeni uç nokta vardır:

**Yerinde sunucuda (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - şu anda yüklü olan imzalı sertifikayı indir (yedek, denetim, yeniden içe aktarma)
- `GET /onprem/renewal-request` - yerel zincir başı ve yetkilendirilmiş genel anahtarı içeren, yerinde özel anahtarla imzalanmış bir manifesto oluştur

**Yukarı akışta (yönetici veya org kapsamlı portal):**
- `POST /admin/delegation-certs/process-renewal-request` (çapraz müşteri sistem kökü)
- `POST /portal/delegation-certs/process-renewal-request` (org sahibi/yöneticisi)

### Yenileme isteği manifestosu

Yenileme isteği küçük bir JSON belgesidir:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

İmza, yerinde özel anahtarı kullanarak manifestonun kanonik kodlaması (anahtarlar alfabetik olarak sıralanmış, ardından `JSON.stringify`) üzerinden hesaplanır. Bu, nesne oluşturma sırasından bağımsız olarak her iki tarafın da özdeş baytlar hesapladığını garanti eder.

### Yukarı akışta doğrulama

`processRenewalManifest()` beş kontrol çalıştırır:

1. **Aktif sertifika mevcut** manifestonun aboneliği için. Aksi takdirde `404 NO_ACTIVE_CERT` döndürür - müşteri yenileme değil oluşturma akışını kullanmalıdır.
2. **Yetkilendirilmiş genel anahtar eşleşiyor** etkin sertifikayla. Aksi takdirde `400 DELEGATED_KEY_MISMATCH` döndürür - farklı bir yerinde sunucudan tekrar oynatmaya karşı korur.
3. **Manifesto imzası doğrulanıyor** etkin sertifikanın `delegatedPublicKey`'ine karşı. Aksi takdirde `400 MANIFEST_SIGNATURE_INVALID` döndürür - manifestonun yerinde özel anahtarın sahibinden geldiğini kanıtlar.
4. **Manifesto yaşı** 7 gün içinde (`RENEWAL_MANIFEST_MAX_AGE_MS`). Aksi takdirde `400 MANIFEST_EXPIRED` döndürür - tekrar oynatma önleme çapası.
5. **Zincir hash bağlantısı** manifestonun `currentSequence`'ındaki yukarı akışın defteriyle eşleşiyor. Aksi takdirde `409 CHAIN_FORK_DETECTED` döndürür - çatallanmış zincirlere karşı korur.

Tüm kontroller geçilirse, `processRenewalManifest`, eski sertifikayı atomik olarak sona erdiren ve yenisini ekleyen mevcut `renew()` akışını çağırır. **Atomik değiş tokuş olduğu için, 2 adımlı iptal+oluştur değil, oluşturma tarafının tek aktif 409 kontrolüne tabi değildir.**

### Transit sırasında sıra ilerlemesi

Bir yenileme isteği manifestosu, oluşturulduğu andaki zincir başını yakalar. Manifesto transit halindeyken (USB teslimatı, şifreli e-posta), yerinde sunucu depo lisansı düzenlemeye devam edebilir ve yerel zincirini ilerletebilir.

Yeni sertifika yerinde sunucuya geri yüklendiğinde, `/onprem/cert-upload` yeni sertifikanın `genesisSequence`'ının yerel düzenleme defterindeki bilinen bir girdiye hala bağlandığını doğrular:

- `cert.genesisSequence > localHead.sequence` ise `409 CHAIN_HEAD_BEHIND` döndürür (yukarı akış çatallanmış bir zincirde).
- `cert.genesisSequence > 0` ve o sıradaki yerel defter girdisi `cert.genesisHash`'ten farklı bir `chainHash`'e sahipse `409 CHAIN_FORK_ON_UPLOAD` döndürür (yerel zincir ayrışmış).
- Aksi takdirde sertifika kabul edilir. Gelecekteki düzenlemeler `localHead.sequence + 1`'den devam eder.

Bu, **transit sırasında yazma dondurması gerekmediği** anlamına gelir. Zincir her iki tarafta da doğal olarak genişler. X.509 sertifika yenilemenin yürütme halindeki seri numaralarını nasıl ele aldığıyla aynı.

## Periyodik Denetim

Yukarı akış, sertifikayı yenilemeden zincir bütünlüğünü doğrulamak için bir denetim uç noktası sağlar:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

Yukarı akış girdileri karşılaştırır ve `{ valid: true }` ya da `{ valid: false, divergedAtSequence: N, expected, actual }` döndürür.

Yerinde sunucular, çatalları erken tespit etmek için bu uç noktayı periyodik olarak çağırmalıdır (varsayılan: `UPSTREAM_AUDIT_URL` env var aracılığıyla haftalık).

### Makine tarafı denetim kanıtları

Renet, `VerifyAuditProof` kullanarak yerel olarak zincir sürekliliğini doğrulayabilir. Bir makine uzun bir aranın ardından lisansını yenilediğinde, sunucu ara zincir girdilerini kanıt olarak döndürebilir. Makine, yukarı akışa başvurmadan herhangi bir kurcalamayı yakalayarak her `chainHash`'in SHA-256 aracılığıyla önceki `prevHash + blobHash`'ten türediğini doğrulamak için kanıtı karşılaştırır.

## Eş Zamanlılık Güvenliği

D1 (Cloudflare'in veritabanı) etkileşimli işlemleri desteklemez. Aynı abonelik için eş zamanlı lisans düzenleme, sıra numarasında çakışabilir. Hesap sunucusu bunu şöyle ele alır:

1. Sonraki sırayı ve önceki zincir hash'ini okur.
2. O sıra içine gömülü blob'u oluşturur ve imzalar.
3. `onConflictDoNothing` ile defter girdisini ekler.
4. Ekleme 0 satır değişimi döndürürse, sıra başka bir istek tarafından alınmış demektir - sırayı yeniden al, yeniden oluştur, **yeniden imzala** ve yeniden dene.
5. 10 başarısız denemeden sonra hata ile başarısız ol.

Kritik ayrıntı: yeniden deneme blob'u **yeniden imzalar**. Yalnızca defter girdisini güncelleyen naif bir yeniden deneme, imzalı blob'u eski bir sıra numarasıyla bırakır ve zinciri bozar.

## E-posta Taşıma

Hesap sunucusu, iki takılabilir taşıma aracılığıyla işlemsel e-postalar (magic link'ler, parola sıfırlama, güvenlik bildirimleri) gönderebilir:

| Taşıma | Yapılandırma |
|---|---|
| `ses` (varsayılan) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Her iki taşıma da bulut ve yerinde dağıtımlar için çalışır. Altyapınıza uygun olanı seçin: kendi AWS hesabınızla AWS SES veya herhangi bir SMTP sunucusu (Microsoft Exchange, Postfix, SendGrid, Mailgun vb.).

Taşıma, `EMAIL_TRANSPORT` ortam değişkeni aracılığıyla başlangıçta seçilir. SMTP bağlantı havuzu ve geç yükleme kullanır; dolayısıyla SMTP istemci kütüphanesi yalnızca SMTP seçilirse başlatılır.

Tüm e-posta şablonları ve genel e-posta API'si taşımalar arasında aynıdır.

## İlgili Belgeler

- [Yerinde Kurulum](/tr/docs/on-premise) -- yerinde sunucuyu nasıl dağıtacağınız
- [Abonelik ve Lisanslama](/tr/docs/subscription-licensing) -- plan limitleri ve makine slotları
- [Sürüm Kanalları](/tr/docs/release-channels) -- edge ve stable kanalları
- [Veri Bölgeleri](/tr/docs/data-regions) -- bölgesel veri yerleşimi
