---
title: "Temizleme"
description: "Sahipsiz yedekleri, eski anlık görüntüleri, depo görüntülerini ve yerel yapılandırma artıklarını kaldırarak disk alanı kazanın ve durumu tutarlı tutun."
category: "Guides"
order: 12
language: tr
sourceHash: "9b74e1ea24b9735f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Temizleme

Temizleme, artık canlı bir kaynağa karşılık gelmeyen durumu tarar. Üç komut üç farklı kapsamı kapsar:

| Komut | Neyi temizler | Doğruluk kaynağı nerede yaşar |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Bulut depolamasındaki sahipsiz yedekler | Yerel CLI yapılandırması (bağlama güvenliği için yürütücü makineye karşı çapraz kontrol edilir) |
| `rdc machine prune --name <machine>` | Makine üzerindeki veri deposu yapıtaşları (her zaman); sahipsiz veya unknown depo görüntüleri (isteğe bağlı) | Yerel CLI yapılandırması + makinenin `.interim/state` aynası |
| `rdc config prune` | Yerel yapılandırma artıkları (sertifika önbelleği, süresi dolmuş arşivler, askıdaki çapraz referanslar) | Yalnızca yerel CLI yapılandırması |

Üçü birbirinden bağımsızdır. Herhangi birini diğerleri olmadan çalıştırabilirsiniz. Aşağıdaki [Güvenlik Modeli](#guvenlik-modeli) altında açıklanan ortak bir güvenlik modelini paylaşırlar.

## Bağlama güvenliği ön denetimi

`storage prune` ve `machine prune --prune-unknown`, herhangi bir şey silmeden önce bir **bağlama güvenliği ön denetimi** çalıştırır: yürütücü makineyi şu anda bağlı veya çalışan depolar için sorgular, silme adaylarıyla kesişimini alır ve **makinede hâlâ canlı olan bir adayı silmeyi reddeder**. Bağlı bir deponun makine dışı yedeğini silmek veya canlı bir depo görüntüsünü silmek gerçek bir veri kaybı tuzağıdır. Ön denetim bunu kazara yapmayı imkânsız kılar.

Geçersiz kılmak için (nadir; yalnızca canlı durumun yanlış olduğundan gerçekten emin olduğunuzda) `--force-delete-mounted` geçirin. Bu, `--force` bayrağından (arşiv ek süresini kontrol eder) ayrı bir bayraktır, böylece iki kaçış noktası ayrı kalır.

## Storage Prune

Bir depolama sağlayıcısını tarar ve GUID'leri herhangi bir yerel yapılandırma dosyasında artık görünmeyen yedekleri siler.

```bash
# Yalnızca önizleme — neyin silineceğini gösterir
rdc storage prune --name my-s3 -m server-1 --dry-run

# Sahipsiz yedekleri gerçekten sil (varsayılan davranış)
rdc storage prune --name my-s3 -m server-1

# Ek süreyi geçersiz kıl (varsayılan 7 gün)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Bağlama güvenliği kontrolünü geçersiz kıl (dikkatli kullanın)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` zorunludur çünkü rclone çağrıları dizüstü bilgisayarınızda değil, yürütücü makinede çalışır. Istemcilerin yerel olarak rclone yüklü olması beklenmez. Depolama kimlik bilgileri yine yerel yapılandırmanızdan gelir; makine yalnızca rclone çalıştırıcısıdır.

### Ne kontrol edilir

1. Adlandırılmış depolamadaki tüm yedek GUID'lerini listeler (hem `hot/` hem de `cold/` alt dizinlerinde. Bkz. [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore#zamanlanmis-yedeklemeler)).
2. Diskteki her yapılandırma dosyasını tarar (`~/.config/rediacc/*.json`).
3. Bir yedek, GUID'si herhangi bir yapılandırmanın depolar bölümünde referans verilmiyorsa **sahipsizdir**.
4. Ek süre içinde yakın zamanda arşivlenen depolar, aktif yapılandırmadan kaldırılmış olsalar bile **korunurlar**.
5. Bağlama güvenliği ön denetimi: `--machine` üzerinde şu anda bağlı olan GUID'ler atlanır ve raporlanır, asla silinmez.

### Performans

Silmeler depolama alt yolu başına gruplandırılır: `hot/` veya `cold/` dizini başına, kaç GUID kaldırıldığından bağımsız olarak tek bir rclone çağrısı yapılır. 11 sahipsiz girişlik bir birikim, ~50 saniye SSH yükünden alt yol başına tek bir gidiş-dönüşe iner.

## Machine Prune

Makine üzerindeki kaynakları üç aşamada temizler. 1. Aşama her zaman çalışır; 2. ve 3. aşamalar isteğe bağlı olup birlikte kullanılabilir.

### 1. Aşama: Veri deposu temizliği (her zaman çalışır)

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

authorized_keys taraması `/home/*/.ssh/authorized_keys` ve `/root/.ssh/authorized_keys` dosyalarına bakar. Bir girdi yalnızca `--guid` etiketi canlı bir bağlama dizini GUID'ine eşlenirse korunur, bu nedenle şu anda makinede dağıtılmış depolar, adları diskte herhangi bir yerde görünse de görünmese de her zaman korunur. renet `--guid` etiketini eklemeye başlamadan önce yazılan eski girdiler doğrulanamaz ve her zaman sahipsiz olarak raporlanır.

```bash
# Dry-run, neyin kaldırılacağını gösterir (değişiklik uygulanmaz)
rdc machine prune --name server-1 --dry-run

# Temizliği yürüt
rdc machine prune --name server-1
```

> **Zincirleme temizlik.** Bazı kategoriler öncekilere bağlıdır. Örneğin, boş bağlama dizinlerini silmek, destekleyen bağlaması az önce kaybolan ek sandbox sahipsizlerini ortaya çıkarabilir. `rdc machine prune` komutunu ikinci kez çalıştırmak zinciri yakalar ve temizliği bitirir. Yapılacak bir şey kalmadığında son dry-run `No orphaned resources found. Datastore is clean.` mesajıyla sonlanır.

### 2. Aşama: `--orphaned-repos` (kaba)

`--orphaned-repos` ile CLI, makinedeki **herhangi bir** yerel yapılandırma dosyasında görünmeyen depo görüntülerini de siler.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

Bu **kabadır**. Yerel yapılandırmanızda olmayan her şeyi siler; başka araçların yönettiği meşru çatallar veya başka bir operatörün CLI checkout'u dahil. renet `.interim/state` aynası bir depoyu doğru şekilde çatal olarak tanımlasa bile, yerel yapılandırma onu hiç görmediyse bu aşama yine de onu kaldırır. Muhafazakâr olmak istediğinizde 3. Aşama (`--prune-unknown`) tercih edin.

### 3. Aşama: `--prune-unknown` (cerrahi)

`--prune-unknown` ile CLI yalnızca **her iki** sinyalin de sınıflandıramadığı depoları siler: herhangi bir yerel yapılandırmada olmayan **ve** makinenin `.interim/state` aynasında çatal işaretli girişi olmayan (bkz. [Depolar. `Type` sütunu](/tr/docs/repositories#type-sutunu-ve-durum-aynasi)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

Pratikte rutin temizlik için istediğiniz `--prune-unknown`'dur; `--orphaned-repos` yalnızca yerel yapılandırmanızın makinedeki her deponun eksiksiz ve yetkili envanteri olduğundan emin olduğunuzda doğrudur. Ayna öncesi eski sahipsiz girişler ve yapılandırma girişi yanlışlıkla silinmiş depolar her ikisi de "unknown" kovasına düşer. Gerçekten belirsizdirler ve cerrahi bayrak operatörden bunu açıkça onaylamasını ister.

Bağlama güvenliği ön denetimi bu aşamada da çalışır: `--machine` üzerinde şu anda bağlı olan bir depo, `--force-delete-mounted` geçirilmedikçe raporlanır ve atlanır.

```bash
# Birleşik: cerrahi çatal-farkındalıklı yol ile tam makine temizliği
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

`~/.config/rediacc/<config>.json` adresindeki **yerel yapılandırma dosyasının içindeki** eski artıkları tarar. Tamamen yereldir. SSH yok, renet çağrısı yok. Üç kova temizlenir:

1. **ACME sertifika önbelleği girişleri**. Bağlantı noktaları (GUID, depo adı veya makine adı) artık aktif yapılandırmada olmayanlar. Sertifika joker karakterleri hiçbir yere yönlendiremez, bu nedenle ölü ağırlıktırlar.
2. **Süresi dolmuş arşivlenmiş depolar**. `resources.deletedRepositories[]` içindeki, `deletedAt` değeri `defaults.pruneGraceDays`'tan (varsayılan 7 gün) eski olan girişler. Ek süre içindeki girişler raporlanır (kalan günlerle birlikte) ve korunur.
3. **Yapılandırma kovaları arasındaki askıdaki çapraz referanslar:**
   - `resources.machines.<m>.backupStrategies[]` içinde artık var olmayan bir stratejiyi adlandıran girişler.
   - `resources.backupStrategies.<s>.exclude[]` ve `include[]` içinde artık var olmayan bir depoyu adlandıran girişler.
   - Hedef depolaması eksik olan depolama hedefleri. Uyarı olarak işaretlenir, otomatik kaldırılmaz (otomatik kaldırma strateji semantiğini değiştirirdi).

```bash
# Yalnızca önizleme
rdc config prune --dry-run

# Uygula (varsayılan davranış)
rdc config prune

# Tek bir kovaya kısıtla
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Ek süreden bağımsız olarak TÜM arşivlenmiş depoları sil
rdc config prune --purge-archived

# Bu çağrı için arşiv ek süresini geçersiz kıl
rdc config prune --grace-days 30
```

### Neye dokunmaz

- Aktif kaynaklar (machines, storages, repositories, backup strategies, bulut sağlayıcıları).
- Kimlik bilgileri, hesap bloğu, şifreleme bloğu, defaults.
- Depolama `vaultContent` (süresi dolmuş OneDrive `access_token` dahil. Refresh_token yenilerini basmaya devam eder; temizleme yeniden kimlik doğrulamayı zorlardı).
- `knownHosts` girişleri (otomatik yenileme yolu `rdc config machine scan-keys`'tir).
- Sıkıştırılmış sertifika blob dizisi (`infra.acmeCertCache.<base>.data[]`) temizlenmiş sertifika listesinden otomatik olarak yeniden oluşturulur; korunan bir adı kapsayan herhangi bir zinciri kaybetmezsiniz.

### İşlenmiş örnek

Dört sahipsiz GUID joker karakteri ve iki eski makine adı joker karakteri olan bir makinede gerçek bir çalıştırmanın çıktısı:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Bağlantı noktası canlı bir makine, depo veya GUID olan sertifika adları yalnız bırakılır; tek etiketli `<service>.<base>` veya kök `*.<base>` joker karakterleri de aynı şekilde dokunulmaz bırakılır.

## Taşıma: durum aynası doldurma

`--prune-unknown` ve `rdc repo list -m` çıktısındaki `Type` sütununu besleyen `.interim/state/<guid>/.rediacc.json` aynası şu zamanlarda yazılır:

- **Çatallama anında** (`rdc repo fork`). Çatal hiç bağlanmamış olsa bile anında.
- **Her durum kaydında** (`rdc repo mount` ve depo durumunu güncelleyen herhangi bir işlem). Ayna kodu yayınlanmadan önce oluşturulmuş depolar için.

**Ayna var olmadan önce oluşturulmuş ve yükseltmeden bu yana yeniden bağlanmamış** depoların ayna dosyası yoktur. `rdc repo list -m` çıktısında bazıları meşru çatal olsa bile `unknown` olarak görünürler. Bunu eski sahipsiz girişler için düzeltmek için makinede tek seferlik doldurma işlemini çalıştırın:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

Doldurma, şu anda bağlı depolar için canlı birim içi durumu aynaya kopyalar ve `--mark-as-fork` altında listelediğiniz GUID'ler için sentetik bir çatal işaretli ayna yazar. Doldurma sonrası, zamanlanmış yedeklemeler listelenen çatalları yüklemeyi durdurur (yükleme hattı aynayı `is_fork: true` için kontrol eder).

## Güvenlik Modeli

Temizleme, çoklu yapılandırma kurulumlarında varsayılan olarak güvenli olacak şekilde tasarlanmıştır.

### Çoklu yapılandırma farkındalığı

`storage prune` ve `machine prune --orphaned-repos`, yalnızca aktif olanı değil, `~/.config/rediacc/` içindeki **tüm** yapılandırma dosyalarını tarar. `production.json` tarafından referans verilen bir depo, `staging.json` dosyasında bulunmasa bile silinmez. Bu, yapılandırmalar farklı ortamlara yönelik olduğunda yanlışlıkla silmeyi önler.

### Ek süre

Bir depo `--archive-config` ile yapılandırmadan kaldırıldığında, kimlik bilgisi girişi `deletedAt` zaman damgasıyla `resources.deletedRepositories[]` listesine taşınır. Temizleme komutları, yakın zamanda arşivlenen depoların silinmeden korunduğu bir ek süreye (varsayılan 7 gün) saygı gösterir. Bu, yanlışlıkla kaldırılan bir depoyu geri yüklemek (`rdc config repository restore-archived --name <guid>`) için size zaman tanır. Ek süre dolduğunda, `storage prune`, `machine prune` ve `config prune` girişi otomatik olarak siler.

### Bağlama güvenliği ön denetimi

Yukarıda kapsanmıştır. `storage prune` ve `machine prune --prune-unknown`, yürütücü makinede şu anda bağlı veya çalışan depoları silmeyi reddeder. Yalnızca `--force-delete-mounted` ile geçersiz kılın.

### Varsayılan olarak uygula; önizleme için `--dry-run`

Üç temizleme komutu da varsayılan olarak değişiklikleri **uygular**. Yazmadan önizlemek için `--dry-run` geçirin. Bu, fiile uyar: "prune" tek başına yıkıcıdır ve bir dry-run bayrağı açık devre dışı bırakma yoludur.

## Yapılandırma

### `pruneGraceDays`

Her seferinde `--grace-days` geçmek zorunda kalmamak için yapılandırma dosyanızda özel bir varsayılan ek süre belirleyin:

```bash
# Aktif yapılandırmada ek süreyi 14 güne ayarla
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

CLI bayrağı `--grace-days` sağlandığında bu değeri geçersiz kılar.

### Öncelik sırası

1. `--grace-days <N>` bayrağı (en yüksek öncelik)
2. Yapılandırma dosyasındaki `pruneGraceDays`
3. Yerleşik varsayılan: 7 gün

## En İyi Uygulamalar

- **Üretimde önce dry-run çalıştırın.** Özellikle üretim depolamasında yıkıcı bir temizleme yürütmeden önce her zaman önizleme yapın.
- **Birden fazla yapılandırmayı güncel tutun.** Storage ve machine prune, yapılandırma dizinindeki tüm yapılandırmaları kontrol eder. Bir yapılandırma dosyası eskimişse veya silinmişse, depoları korumalarını kaybeder. Yapılandırma dosyalarını doğru tutun.
- **`--prune-unknown`'u `--orphaned-repos`'a tercih edin.** Cerrahi bayrak renet aynasına saygı gösterir; kaba bayrak başka araçların oluşturduğu çatalları memnuniyetle siler.
- **Üretim için cömert ek süreler kullanın.** Varsayılan 7 günlük ek süre çoğu iş akışı için uygundur. Seyrek bakım pencerelerine sahip üretim ortamları için 14 veya 30 günü düşünün.
- **Storage prune'u yedekleme çalıştırmalarından sonra planlayın.** Manuel müdahale olmadan depolama maliyetlerini kontrol altında tutmak için `storage prune` komutunu yedekleme planınızla eşleştirin.
- **Machine prune'u backup schedule ile birleştirin.** Yedekleme planlarını dağıttıktan sonra (`rdc machine backup schedule`), eski anlık görüntüleri ve sahipsiz veri deposu yapıtaşlarını temizlemek için periyodik bir makine temizlemesi ekleyin.
- **`config prune`'u periyodik olarak çalıştırın.** Yerel yapılandırma şişmesi (özellikle sertifika önbelleği) sessizce birikir; üç ayda bir `config prune --dry-run` yakalamak için yeterlidir.
- **`--force` veya `--force-delete-mounted` kullanmadan önce denetleyin.** Her iki bayrak da güvenlik kontrollerini atlar. `--force`'u yalnızca söz konusu depolara başka hiçbir yapılandırmanın referans vermediğinden emin olduğunuzda kullanın; `--force-delete-mounted`'ı yalnızca makinedeki canlı durumun yanlış olduğundan emin olduğunuzda kullanın.
