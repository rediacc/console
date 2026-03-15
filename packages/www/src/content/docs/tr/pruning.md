---
title: "Temizleme"
description: "Sahipsiz yedekleri, eski anlık görüntüleri ve kullanılmayan depo görüntülerini kaldırarak disk alanı kazanın."
category: "Guides"
order: 12
language: tr
sourceHash: "39df2a50797597f6"
---

# Temizleme

Temizleme, herhangi bir yapılandırma dosyası tarafından artık referans verilmeyen kaynakları kaldırır. Farklı kaynak türlerini hedefleyen iki temizleme komutu vardır:

- **`rdc storage prune`** -- bulut/harici depolamadan sahipsiz yedek dosyalarını siler
- **`rdc machine prune`** -- veri deposu yapıtaşlarını ve (isteğe bağlı olarak) makinedeki sahipsiz depo görüntülerini temizler

## Storage Prune

Bir depolama sağlayıcısını tarar ve GUID'leri herhangi bir yapılandırma dosyasında artık görünmeyen yedekleri siler.

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### Ne kontrol edilir

1. Belirtilen depolamadaki tüm yedek GUID'lerini listeler.
2. Diskteki tüm yapılandırma dosyalarını tarar (`~/.config/rediacc/*.json`).
3. Bir yedek, GUID'si herhangi bir yapılandırmanın depolar bölümünde referans verilmiyorsa **sahipsizdir**.
4. Ek süre içinde yakın zamanda arşivlenen depolar, aktif yapılandırmadan kaldırılmış olsalar bile **korunurlar**.

## Machine Prune

Makinedeki kaynakları iki aşamada temizler.

### Aşama 1: Veri deposu temizliği (her zaman çalışır)

Boş bağlama dizinlerini, eski kilit dosyalarını ve eski BTRFS anlık görüntülerini kaldırır.

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### Aşama 2: Sahipsiz depo görüntüleri (isteğe bağlı)

`--orphaned-repos` ile CLI, makinedeki herhangi bir yapılandırma dosyasında görünmeyen LUKS depo görüntülerini de tespit eder ve siler.

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
```

## Güvenlik Modeli

Temizleme, çoklu yapılandırma kurulumlarında varsayılan olarak güvenli olacak şekilde tasarlanmıştır.

### Çoklu yapılandırma farkındalığı

Her iki temizleme komutu da yalnızca aktif olanı değil, `~/.config/rediacc/` içindeki **tüm** yapılandırma dosyalarını tarar. `production.json` tarafından referans verilen bir depo, `staging.json` dosyasında bulunmasa bile silinmez. Bu, yapılandırmalar farklı ortamlara yönelik olduğunda yanlışlıkla silmeyi önler.

### Ek süre

Bir depo yapılandırmadan kaldırıldığında, zaman damgasıyla arşivlenebilir. Temizleme komutları, yakın zamanda arşivlenen depoların silinmeden korunduğu bir ek süreye (varsayılan 7 gün) saygı gösterir. Bu, yanlışlıkla kaldırılan bir depoyu geri yüklemek için size zaman tanır.

### Varsayılan olarak dry-run

`storage prune` ve `machine prune` varsayılan olarak dry-run modunda çalışır. Değişiklik yapmadan nelerin kaldırılacağını gösterirler. Gerçek silme işlemini yürütmek için `--no-dry-run` veya `--force` kullanın.

## Yapılandırma

### `pruneGraceDays`

Her seferinde `--grace-days` geçmek zorunda kalmamak için yapılandırma dosyanızda özel bir varsayılan ek süre belirleyin:

```bash
# Set grace period to 14 days in the active config
rdc config set pruneGraceDays 14
```

CLI bayrağı `--grace-days` sağlandığında bu değeri geçersiz kılar.

### Öncelik sırası

1. `--grace-days <N>` bayrağı (en yüksek öncelik)
2. Yapılandırma dosyasındaki `pruneGraceDays`
3. Yerleşik varsayılan: 7 gün

## En İyi Uygulamalar

- **Önce dry-run çalıştırın.** Özellikle üretim depolamasında yıkıcı bir temizleme yürütmeden önce her zaman önizleme yapın.
- **Birden fazla yapılandırmayı güncel tutun.** Temizleme, yapılandırma dizinindeki tüm yapılandırmaları kontrol eder. Bir yapılandırma dosyası eskimişse veya silinmişse, depoları korumalarını kaybeder. Yapılandırma dosyalarını doğru tutun.
- **Üretim için cömert ek süreler kullanın.** Varsayılan 7 günlük ek süre çoğu iş akışı için uygundur. Seyrek bakım pencerelerine sahip üretim ortamları için 14 veya 30 günü düşünün.
- **Storage prune'u yedekleme çalıştırmalarından sonra planlayın.** Manuel müdahale olmadan depolama maliyetlerini kontrol altında tutmak için `storage prune` komutunu yedekleme planınızla eşleştirin.
- **Machine prune'u deploy-backup ile birleştirin.** Yedekleme planlarını dağıttıktan sonra (`rdc machine deploy-backup`), eski anlık görüntüleri ve sahipsiz veri deposu yapıtaşlarını temizlemek için periyodik bir makine temizlemesi ekleyin.
- **`--force` kullanmadan önce denetleyin.** `--force` bayrağı ek süreyi atlar. Yalnızca söz konusu depolara başka hiçbir yapılandırmanın referans vermediğinden emin olduğunuzda kullanın.
