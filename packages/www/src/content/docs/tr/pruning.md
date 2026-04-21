---
title: "Temizleme"
description: "Sahipsiz yedekleri, eski anlık görüntüleri ve kullanılmayan depo görüntülerini kaldırarak disk alanı kazanın."
category: "Guides"
order: 12
language: tr
sourceHash: "f355a0921afb72e9"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# Temizleme

Temizleme, herhangi bir yapılandırma dosyası tarafından artık referans verilmeyen kaynakları kaldırır. Farklı kaynak türlerini hedefleyen iki temizleme komutu vardır:

- **`rdc storage prune`** -- bulut/harici depolamadan sahipsiz yedek dosyalarını siler
- **`rdc machine prune`** -- veri deposu yapıtaşlarını ve (isteğe bağlı olarak) makinedeki sahipsiz depo görüntülerini temizler

## Storage Prune

Bir depolama sağlayıcısını tarar ve GUID'leri herhangi bir yapılandırma dosyasında artık görünmeyen yedekleri siler.

```bash
# Dry-run (default), shows what would be deleted
rdc storage prune --name my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune --name my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune --name my-s3 -m server-1 --grace-days 14
```

### Ne kontrol edilir

1. Belirtilen depolamadaki tüm yedek GUID'lerini listeler.
2. Diskteki tüm yapılandırma dosyalarını tarar (`~/.config/rediacc/*.json`).
3. Bir yedek, GUID'si herhangi bir yapılandırmanın depolar bölümünde referans verilmiyorsa **sahipsizdir**.
4. Ek süre içinde yakın zamanda arşivlenen depolar, aktif yapılandırmadan kaldırılmış olsalar bile **korunurlar**.

## Machine Prune

Makinedeki kaynakları iki aşamada temizler.

### Aşama 1: Veri deposu temizliği (her zaman çalışır)

Bir depo silindiğinde veya makine düzeyinde bir yeniden düzenleme bir adlandırma kuralını geri çektiğinde geride kalabilecek her tür kaynağı kaldırır. Her kategori bağımsız olarak taranır ve temizleme tek bir idempotent geçiştir, bu nedenle prune'u tekrar tekrar çalıştırmak güvenlidir ve temiz bir veri deposunda yakınsar.

| Kategori | Neyi kaldırır |
|----------|---------------|
| Boş bağlama dizinleri | Destekleyen depo görüntüsü olmayan `mounts/<guid>/` dizinleri |
| Sahipsiz immovable dizinleri | Destekleyen depo görüntüsü olmayan `immovable/<guid>/` dizinleri |
| Eski kilit dosyaları | Silinen depolar için `repositories/.lock-<guid>` |
| Eski yedek anlık görüntüleri | Sonlandırılan yedekleme çalıştırmalarından geriye kalan `.snapshot-*` ve `.backup-*` |
| Sahipsiz VS Code sandbox dizinleri | Makinede artık aktif olmayan depolar için `.interim/sandbox/<name>` |
| Sahipsiz iptables zincirleri | Silinen ağlar için `REDIACC_WILDCARD_<N>` ve `DOCKER_ISOLATED_NET_<N>` zincirleri |
| Sahipsiz authorized_keys girdileri | `--guid` değeri artık aktif bir bağlama dizinine eşlenmeyen `sandbox-gateway <repo> --guid <uuid>` satırları |

authorized_keys taraması `/home/*/.ssh/authorized_keys` ve `/root/.ssh/authorized_keys` dosyalarına bakar. Bir girdi yalnızca `--guid` etiketi canlı bir bağlama dizini GUID'ine eşlenirse korunur, bu nedenle şu anda makinede dağıtılmış depolar, adları diskte herhangi bir yerde görünse de görünmese de her zaman korunur. Renet `--guid` etiketini eklemeye başlamadan önce yazılan eski girdiler doğrulanamaz ve her zaman sahipsiz olarak raporlanır.

```bash
# Dry-run, shows what would be removed (no changes applied)
rdc machine prune --name server-1 --dry-run

# Execute cleanup
rdc machine prune --name server-1
```

> **Zincirleme temizlik.** Bazı kategoriler öncekilere bağlıdır. Örneğin, boş bağlama dizinlerini silmek, destekleyen bağlaması az önce kaybolan ek sandbox sahipsizlerini ortaya çıkarabilir. `rdc machine prune` komutunu ikinci kez çalıştırmak zinciri yakalar ve temizliği bitirir. Yapılacak bir şey kalmadığında son dry-run `No orphaned resources found. Datastore is clean.` mesajıyla sonlanır.

### Aşama 2: Sahipsiz depo görüntüleri (isteğe bağlı)

`--orphaned-repos` ile CLI, makinedeki herhangi bir yapılandırma dosyasında görünmeyen LUKS depo görüntülerini de tespit eder ve siler.

```bash
# Dry-run (default behavior when is set)
rdc machine prune --name server-1

# Actually delete orphaned repos
rdc machine prune --name server-1

# Custom grace period
rdc machine prune --name server-1 --grace-days 30
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
rdc config set --key pruneGraceDays --value 14
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
- **Machine prune'u backup schedule ile birleştirin.** Yedekleme planlarını dağıttıktan sonra (`rdc machine backup schedule`), eski anlık görüntüleri ve sahipsiz veri deposu yapıtaşlarını temizlemek için periyodik bir makine temizlemesi ekleyin.
- **`--force` kullanmadan önce denetleyin.** `--force` bayrağı ek süreyi atlar. Yalnızca söz konusu depolara başka hiçbir yapılandırmanın referans vermediğinden emin olduğunuzda kullanın.
