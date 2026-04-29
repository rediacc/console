---
title: Depolar
description: 'Uzak makinelerde LUKS ile şifrelenmiş depoları oluşturma, yönetme ve işletme.'
category: Guides
order: 4
language: tr
sourceHash: "689a84ee2873fe00"
sourceCommit: "8165b06e0d06dd07530fff343b0df6ecb1697a47"
---

# Depolar

Bir **depo** (repository), uzak sunucudaki LUKS ile şifrelenmiş bir disk imajıdır. Bağlandığında şunları sağlar:
- Uygulama verileriniz için izole bir dosya sistemi
- Özel bir Docker daemon'u (ana bilgisayarın Docker'ından ayrı)
- /26 alt ağı içinde her servis için benzersiz loopback IP'leri

## Depo Oluşturma

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `-m, --machine <name>` | Evet | Deponun oluşturulacağı hedef makine |
| `--size <size>` | Evet | Şifrelenmiş disk imajının boyutu (ör. `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Hayır | İşlemden sonra rota sunucusunun yeniden başlatılmasını atla |

Çıktıda otomatik olarak oluşturulan üç değer gösterilir:

- **Depo GUID'i** -- Sunucudaki şifrelenmiş disk imajını tanımlayan bir UUID.
- **Kimlik Bilgisi** (Credential) -- LUKS birimini şifrelemek/çözmek için kullanılan rastgele bir parola.
- **Ağ Kimliği** (Network ID) -- Bu deponun servislerinin IP alt ağını belirleyen bir tamsayı (2816'dan başlar, 64'er artar).

> **Kimlik bilgisini güvenli bir şekilde saklayın.** Bu, deponuzun şifreleme anahtarıdır. Kaybedilmesi durumunda veriler kurtarılamaz. Kimlik bilgisi yerel `config.json` dosyanızda saklanır ancak sunucuda saklanmaz.

## Bağlama ve Ayırma

Bağlama işlemi şifresini çözer ve depo dosya sistemini erişilebilir hale getirir. Ayırma işlemi şifrelenmiş birimi kapatır.

```bash
rdc repo mount --name my-app -m server-1  # Şifresini çöz ve bağla
rdc repo unmount --name my-app -m server-1  # Ayır ve tekrar şifrele
```

| Seçenek | Açıklama |
|---------|----------|
| `--checkpoint` | Bağlama/ayırma öncesinde bir CRIU kontrol noktası oluştur (`rediacc.checkpoint=true` etiketli konteynerler için) |
| `--skip-router-restart` | İşlemden sonra rota sunucusunun yeniden başlatılmasını atla |

## Durum Kontrolü

```bash
rdc repo status --name my-app -m server-1
```

## Depoları Listeleme

```bash
rdc repo list -m server-1
```

## Yeniden Boyutlandırma

Depoyu tam bir boyuta ayarlayın veya belirli bir miktar genişletin:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Tam boyutu ayarla
rdc repo expand --name my-app -m server-1 --size 5G  # Mevcut boyuta 5G ekle
```

> Yeniden boyutlandırma öncesinde deponun bağlantısı kesilmiş olmalıdır.

## Çatallama (Fork)

Mevcut bir deponun güncel durumunun bir kopyasını oluşturun:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Çatallar name:tag modelini kullanır: ortaya çıkan çatal `my-app:staging` olarak adlandırılır. Bu, kendi GUID'i ve ağ kimliğine sahip yeni bir şifrelenmiş kopya oluşturur ve üst deponun adını paylaşır. Çatal, üst depo ile aynı LUKS kimlik bilgisini paylaşır.

> Çatallar, disk üzerinde saklanan tüm kimlik bilgileri dahil olmak üzere üst deponun verilerini BTRFS reflink aracılığıyla paylaşır. Bu kimlik bilgileri Stripe, AWS veya Railway gibi harici servislere yetki verdiğinde ortaya çıkan etkiler için [Rediacc'in izole etmediği şeyler](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate) bölümüne bakın.

## Doğrulama

Bir deponun dosya sistemi bütünlüğünü kontrol edin:

```bash
rdc repo validate --name my-app -m server-1
```

## Sahiplik

Depo içindeki dosya sahipliğini evrensel kullanıcıya (UID 7111) ayarlayın. Bu genellikle iş istasyonunuzdan dosya yükledikten sonra gereklidir, çünkü dosyalar yerel UID'nizle gelir.

```bash
rdc repo ownership --name my-app -m server-1
```

Komut, Docker konteyner veri dizinlerini (yazılabilir bind bağlamaları) otomatik olarak algılar ve hariç tutar. Bu, dosyaları kendi UID'leriyle yöneten konteynerlerin (ör. MariaDB=999, www-data=33) bozulmasını önler.

| Seçenek | Açıklama |
|---------|----------|
| `--uid <uid>` | 7111 yerine özel bir UID ayarla |
| `--skip-router-restart` | İşlemden sonra rota sunucusunun yeniden başlatılmasını atla |

Tüm dosyalar üzerinde sahipliği zorlamak için (konteyner verileri dahil):

```bash
rdc repo ownership --name my-app -m server-1
```


Sahipliğin ne zaman ve nasıl kullanılacağına dair eksiksiz bir kılavuz için [Taşıma Rehberi](/en/docs/migration) sayfasına bakın.

## Şablon

Bir depoyu dosyalarla başlatmak için şablon uygulayın:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Silme

Bir depoyu ve içindeki tüm verileri kalıcı olarak yok edin:

```bash
rdc repo delete --name my-app -m server-1
```

> Bu, şifrelenmiş disk imajını kalıcı olarak yok eder. Bu işlem geri alınamaz.

## Depo Taşıma

Bir depoyu minimum kesinti süresiyle bir makineden diğerine canlı olarak taşıyın.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Seçenek | Açıklama |
|---------|----------|
| `--provision` | Taşımadan önce hedef makinede depoyu hazırla (LUKS imajı oluşturur ve yapılandırmayı kaydeder) |
| `--checkpoint` | Geçiş öncesinde çalışan konteynerlerin CRIU kontrol noktasını oluştur |
| `--bwlimit <kbps>` | rsync bant genişliğini kilobayt/saniye cinsinden sınırla |
| `--skip-dns` | Geçiş sonrasında DNS kayıtlarının güncellenmesini atla |

**Üç aşamalı akış:**

1. **Sıcak ön kopyalama** - Depo kaynak üzerinde çalışmaya devam ederken rsync verileri aktarır. Büyük dosyalar herhangi bir kesinti olmadan önce aktarılır.
2. **Geçiş** - Depo kaynakta durdurulur, son rsync geçişi kalan değişiklikleri senkronize eder ve depo hedefte başlatılır.
3. **Hedefte başlatma** - renet, hedef makinede depoyu bağlar ve başlatır. `--skip-dns` geçirilmedikçe DNS güncellenir.

![Depo Canlı Taşıma](/img/repo-migrate-flow.svg)

**Push ile taşıma karşılaştırması:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| İşlem | Kopyalama | Taşıma |
| Kaynak sonrası | Değişmez | Durdurulmuş |
| Kesinti süresi | Yok (yalnızca kopyalama) | Kısa geçiş penceresi |
| DNS güncellemesi | Hayır | Evet (`--skip-dns` olmadan) |
| Kullanım senaryosu | Yedekleme, geliştirme klonu | Makine değiştirme, sunucu taşıma |

## Temizleme

Depoları sildikten veya başarısız işlemlerden kurtulduktan sonra, sahipsiz bağlama dizinleri, kilit dosyaları ve taşınamaz işaretçiler kalabilir. Temizleme bunları güvenli şekilde kaldırır:

```bash
# Neyin kaldırılacağını önizle
rdc machine prune --name server-1 --dry-run

# Sahipsiz kaynakları kaldır
rdc machine prune --name server-1
```

Yalnızca eşleşen depo imajı olmayan kaynaklar etkilenir. İçeriği boş olmayan bağlama dizinleri hiçbir zaman kaldırılmaz.
