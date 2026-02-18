---
title: "Depolar"
description: "Uzak makinelerde LUKS ile sifrelenmis depolari olusturma, yonetme ve isletme."
category: "Guides"
order: 4
language: tr
---

# Depolar

Bir **depo** (repository), uzak sunucudaki LUKS ile şifrelenmiş bir disk imajıdır. Bağlandığında şunları sağlar:
- Uygulama verileriniz için izole bir dosya sistemi
- Özel bir Docker daemon'u (ana bilgisayarın Docker'ından ayrı)
- /26 alt ağı içinde her servis için benzersiz loopback IP'leri

## Depo Oluşturma

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `-m, --machine <name>` | Evet | Deponun oluşturulacağı hedef makine |
| `--size <size>` | Evet | Şifrelenmiş disk imajının boyutu (ör. `5G`, `10G`, `50G`) |

Çıktıda otomatik olarak oluşturulan üç değer gösterilir:

- **Depo GUID'i** -- Sunucudaki şifrelenmiş disk imajını tanımlayan bir UUID.
- **Kimlik Bilgisi** (Credential) -- LUKS birimini şifrelemek/çözmek için kullanılan rastgele bir parola.
- **Ağ Kimliği** (Network ID) -- Bu deponun servislerinin IP alt ağını belirleyen bir tamsayı (2816'dan başlar, 64'er artar).

> **Kimlik bilgisini güvenli bir şekilde saklayın.** Bu, deponuzun şifreleme anahtarıdır. Kaybedilmesi durumunda veriler kurtarılamaz. Kimlik bilgisi yerel `config.json` dosyanızda saklanır ancak sunucuda saklanmaz.

## Bağlama ve Ayırma

Bağlama işlemi şifresini çözer ve depo dosya sistemini erişilebilir hale getirir. Ayırma işlemi şifrelenmiş birimi kapatır.

```bash
rdc repo mount my-app -m server-1       # Şifresini çöz ve bağla
rdc repo unmount my-app -m server-1     # Ayır ve tekrar şifrele
```

| Seçenek | Açıklama |
|---------|----------|
| `--checkpoint` | Bağlama/ayırma öncesinde bir kontrol noktası oluştur |

## Durum Kontrolü

```bash
rdc repo status my-app -m server-1
```

## Depoları Listeleme

```bash
rdc repo list -m server-1
```

## Yeniden Boyutlandırma

Depoyu tam bir boyuta ayarlayın veya belirli bir miktar genişletin:

```bash
rdc repo resize my-app -m server-1 --size 20G    # Tam boyutu ayarla
rdc repo expand my-app -m server-1 --size 5G      # Mevcut boyuta 5G ekle
```

> Yeniden boyutlandırma öncesinde deponun bağlantısı kesilmiş olmalıdır.

## Çatallama (Fork)

Mevcut bir deponun güncel durumunun bir kopyasını oluşturun:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Bu, kendi GUID'i ve ağ kimliğine sahip yeni bir şifrelenmiş kopya oluşturur. Çatal (fork), üst depo ile aynı LUKS kimlik bilgisini paylaşır.

## Doğrulama

Bir deponun dosya sistemi bütünlüğünü kontrol edin:

```bash
rdc repo validate my-app -m server-1
```

## Sahiplik

Depo içindeki dosya sahipliğini evrensel kullanıcıya (UID 7111) ayarlayın. Bu genellikle iş istasyonunuzdan dosya yükledikten sonra gereklidir, çünkü dosyalar yerel UID'nizle gelir.

```bash
rdc repo ownership my-app -m server-1
```

Komut, Docker konteyner veri dizinlerini (yazılabilir bind bağlamaları) otomatik olarak algılar ve hariç tutar. Bu, dosyaları kendi UID'leriyle yöneten konteynerlerin (ör. MariaDB=999, www-data=33) bozulmasını önler.

| Seçenek | Açıklama |
|---------|----------|
| `--uid <uid>` | 7111 yerine özel bir UID ayarla |
| `--force` | Docker birim algılamayı atla ve her şeyi sahiplendir |

Tüm dosyalar üzerinde sahipliği zorlamak için (konteyner verileri dahil):

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Uyarı:** Çalışan konteynerlerde `--force` kullanmak onları bozabilir. Gerekiyorsa önce `rdc repo down` ile servisleri durdurun.

Sahipliğin ne zaman ve nasıl kullanılacağına dair eksiksiz bir yol haritası için [Taşıma Rehberi](/tr/docs/migration) sayfasına bakın.

## Şablon

Bir depoyu dosyalarla başlatmak için şablon uygulayın:

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Silme

Bir depoyu ve içindeki tüm verileri kalıcı olarak yok edin:

```bash
rdc repo delete my-app -m server-1
```

> Bu, şifrelenmiş disk imajını kalıcı olarak yok eder. Bu işlem geri alınamaz.
