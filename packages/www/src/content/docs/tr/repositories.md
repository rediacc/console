---
title: Depolar
description: 'Uzak makinelerde LUKS ile şifrelenmiş depoları oluşturma, yönetme ve işletme.'
category: Guides
order: 4
language: tr
sourceHash: "a3b38ca25b01b511"
sourceCommit: "b249ac136e10333269e1a393dd7dc2d30a89d0f1"
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
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

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
| `--checkpoint` | Bağlama/ayırma öncesinde bir kontrol noktası oluştur |
| `--skip-router-restart` | Skip restarting the route server after the operation |

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

Çatallar name:tag modelini kullanır: ortaya çıkan çatal `my-app:staging` olarak adlandırılır. Bu, kendi GUID'i ve ağ kimliğine sahip yeni bir şifrelenmiş kopya oluşturur ve üst deponun adını paylaşır. Çatal (fork), üst depo ile aynı LUKS kimlik bilgisini paylaşır.

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
| `--skip-router-restart` | Skip restarting the route server after the operation |

Tüm dosyalar üzerinde sahipliği zorlamak için (konteyner verileri dahil):

```bash
rdc repo ownership --name my-app -m server-1
```


Sahipliğin ne zaman ve nasıl kullanılacağına dair eksiksiz bir yol haritası için [Taşıma Rehberi](/tr/docs/migration) sayfasına bakın.

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
