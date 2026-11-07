---
title: "Yedekleme Hedefleri"
description: "Her yedekleme stratejisini birden fazla depoya gönderin, en iyi anlık görüntüyü tutan depodan geri yükleyin ve her hedef için ayrı bir durum satırı okuyun."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: tr
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Yedekleme Hedefleri

Bir yedekleme stratejisi birden fazla depoya yazabilir. Her hedef ayrı bir kurtarma noktasıdır: kendi anlık görüntüsü, kendi commit'i ve kendi durum satırı vardır; bu yüzden başarısız olan bir depo diğerini bozmaz.

Tüm depolar tek bir hesaba aittir. Tek bir config, tek bir lisans ve tek bir fatura hepsini kapsar. İki hesaba giriş yapmış bir makine yine reddedilir, çünkü birden fazla hedef, tek bir hesap içinde birden fazla depo demektir.

## Depolar

Depo, hesap sunucusunun makine adına yazdığı bir bucket'tır. Her aboneliğin ilk günden itibaren `home` adında bir deposu vardır: yedekleme komutlarının her zaman kullandığı barındırılan depo. Depo belirtmeyen bir hedef `home` deposuna yazar.

Bunun yanında iki tür daha kaydedilebilir.

| Tür | Nedir | Kayıt için gerekenler |
|-----|-------|-----------------------|
| `hosted-r2` | Dağıtımın sunduğu bölgeler arasından seçilen ikinci bir barındırılan bölge | Bir kimlik ve bölge. Kimlik bilgisi gerekmez |
| `customer-s3` | Müşterinin işlettiği, S3, RustFS veya S3 uyumlu herhangi bir hizmet üzerindeki bir bucket | Bir kimlik, HTTPS uç noktası, bucket, imzalama bölgesi (varsayılan `us-east-1`), isteğe bağlı bir herkese açık uç nokta ve bir erişim anahtarı çifti |

Bir makine müşteri bucket'ının anahtarlarını asla tutmaz. Anahtarlar mühürlü olarak hesap sunucusunda durur; makine yalnızca oturumunun adını verdiği tek depo için kısa ömürlü önceden imzalanmış URL'ler alır.

### Depo kaydetme

Kayıt, `rdc` komutu değil, hesap API'sine yapılan bir çağrıdır. `POST /backups/stores` bir depo kaydeder, `GET /backups/stores` kayıtlı depoları listeler ve `DELETE /backups/stores/<id>` bir depoyu kullanımdan kaldırır. Kaydetme, anahtar yenileme ve kullanımdan kaldırma, kuruluşun mevcut bir sahibi veya yöneticisi tarafından oluşturulmuş, `backup:manage` kapsamına sahip bir API belirteci ister ve her biri denetim kaydına yazılır. Listeleme için `backup:read` gerekir.

Sunucu, bir depoyu kabul etmeden önce denetler.

- **Uyumluluk yoklaması.** Sunucu, barındırılan bir deponun geçtiği kontrollerin aynısını çalıştırır. Sağlama toplamlarını zorunlu kılmayan bir depo, ilk yedekte fark edilmek yerine kayıt sırasında reddedilir.
- **Silme yoklaması.** Yoklama bir silme de dener. Depo bunu reddederse, temizlik devre dışı olarak kaydedilir (aşağıya bakın).
- **Uç nokta kuralları.** Yalnızca HTTPS, 443 numaralı bağlantı noktası ve iç ağdaki hiçbir uç nokta.
- **Depo sınırı.** Abonelik başına depo sayısı plana bağlıdır; `home` dahildir, kullanımdan kaldırılan depolar sayılmaz.

| Plan | Depolar |
|------|---------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Zaten var olan bir kimliği kaydetmek yalnızca kimlik bilgilerini yeniler ve yoklama yeniden çalışır. Kimlik bilgileri çalışmayı bırakan bir depo, reddedilen ilk yetkilendirmede askıya alınmış olarak işaretlenir. `GET /backups/stores` uç noktayı, bucket'ı ve anahtar kimliğinin son karakterlerini gösterir, gizli anahtarı asla göstermez.

Etkin bir hedef hâlâ adını veriyorsa bir depo kullanımdan kaldırılamaz, `home` ise hiçbir zaman kaldırılamaz.

## Bir hedefin deposunu belirtme

Bir hedef, deposunu `--destination` ile birlikte kullanılan `--target` ile belirtir:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Seçenek | Açıklama |
|---------|----------|
| `--destination <name>` | Oluşturulacak veya değiştirilecek hedef |
| `--target <storeId>` | Hedefin yazdığı kayıtlı deponun kimliği (varsayılan `home`). `--destination` gerektirir |

Bir stratejinin iki etkin hedefi aynı depoyu belirtemez ve kayıtlı olmayan bir depo, kayıtlı kimliklerin listesiyle birlikte reddedilir.

Zamanlanmış her çalıştırma, hedeflerin tanımlandığı sırayla, her biri kendi bant genişliği sınırıyla, etkin hedef başına bir anlık görüntü alır. Her anlık görüntü yeni bir copy-on-write reflink'tir; dolayısıyla her biri kendi başına tutarlı bir zaman noktasıdır. Başarısız olan bir hedef bir sonrakini atlatmaz. Herhangi bir hedef başarısız olduysa birim yine sıfırdan farklı bir kodla çıkar; böylece systemd ve kaçırılan çalıştırma denetimi hatayı görür.

## Bir depodan geri yükleme

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` ve `rdc backup download --store` komutları `--from <storeId>` kabul eder:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

`--from` verilmezse CLI, hesap sunucusuna deponun soy hattını hangi depoların tuttuğunu sorar. Sıralamada en yeni anlık görüntüsü son doğrulamayı geçen depo başa gelir ve CLI depoları bu sırayla dener. Anlık görüntüsü olmayan depo atlanır. Sıralama okunamazsa geri yükleme `home` deposunu kullanır ve bunu söyler.

`--from` verilmezse `backup restore`, `restore --path`, `browse --at` ve `download --store` bu sıralamanın ilk deposundan başlar ve hata depodan kaynaklanıyorsa sonraki depoya geçer: sunucu hatası, reddedilen yetkilendirme veya oturum, ya da yanıt vermeyen bir uç nokta. Her biri hangi deponun kendisine hizmet verdiğini söyler. Hiçbiri anlık görüntünün kendi arızası yüzünden başka depoya geçmez. Eksik, süresi dolmuş veya bozuk bir anlık görüntü her depoda aynı görünür; bu yüzden hata gösterilir. `--from` verilen bir komut yalnızca o depoyu okur ve asla başka depoya geçmez.

`--from` olmadan verilen bir anlık görüntü kimliği, soy hattının tüm depolarında aranır.

## Hedef başına durum

`rdc backup status`, zamanlama tablosunun yanında hedef başına bir satır yazdırır:

| Sütun | Anlamı |
|-------|--------|
| Store | Hedefin yazdığı deponun kimliği |
| Last run | O depo için son çalıştırmanın bittiği zaman |
| Result | O çalıştırmanın sonucu |
| Newest snapshot | Deponun tuttuğu en yeni anlık görüntü |
| Verify | Deponun son doğrulamasının sonucu |
| Clean-up | `enabled` veya nedeniyle birlikte devre dışı |

Hesabın raporlayamadığı bir depo, sütunlarında `-` gösterir. Kaçırılan çalıştırma denetimi depo başına yapılır; bu yüzden yedek almayı bırakan bir depo kendi alarmını verirken diğerleri yeşil kalır.

## Kotaya neler sayılır

Barındırılan depolar, yani `home` ve ikinci bölgelerin tümü, fiziksel olarak saklanan benzersiz baytlara göre ölçülür ve baytları aynı plan kotasına sayılır. `rdc backup usage` bunları gösterir.

Bir müşteri bucket'ının baytlarını Rediacc saklamaz ve bunlar kotaya sayılmaz. Hesabın onun için tuttuğu meta veriler (manifest satırları, doğrulama çalıştırmaları ve dizin nesneleri) barındırılan bir depodaki gibi ölçülür.

## Temizliği devre dışı depolar

Silme işlemini reddeden bir depo tüm nesneleri korur. Saklama ve çöp toplama ondan hiçbir zaman silmez. Bir anlık görüntünün süresi dolduğunda süpürme işlemi onu hesapta süresi dolmuş olarak işaretler, geri yükleme için sunmayı bırakır ve nesnelerini bucket'ta bırakır.

`rdc backup status` ve yedekleme sağlık özeti depoyu temizliği devre dışı olarak bildirir. Silme yetkisi olan anahtarlarla aynı kimlik yeniden kaydedilerek silme kimlik bilgileri eklenene kadar bucket büyümeye devam eder.
