---
title: İzleme
description: >-
  Makine sağlığını, konteynerleri, servisleri, depoları izleyin ve tanılama
  çalıştırın.
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: tr
sourceHash: "6e4968522e118c98"
sourceCommit: "9b8aa220de6eb4f7c7b7783456af6871202c8305"
---

# İzleme

Rediacc, makine sağlığını, çalışan konteynerleri, servisleri, depo durumunu ve sistem tanılamalarını incelemek için yerleşik izleme komutları sunar.

## Makine Sağlığı

Bir makine için tam bir sağlık raporu alın:

```bash
rdc machine health server-1
```

Rapor içeriği:
- **Sistem**: çalışma süresi, bellek (yüzde 80 üzerinde uyarı, yüzde 90 üzerinde hata), disk ve datastore kullanımı (yüzde 85 üzerinde uyarı, yüzde 95 üzerinde hata)
- **Konteynerler**: çalışan, sağlıklı ve sağlıksız konteyner sayıları; `Restarting` döngüsündeki bir konteyner kritiktir
- **Servisler**: başarısız systemd birimleri (hata) ve sürekli yeniden başlayan birimler (kritik)
- **Depolama**: SMART sağlık durumu (bozulan bir disk kritiktir) ve disk sıcaklığı
- **Depolar**: bağlı olmayan otomatik başlatmalı depolar ve her deponun dosya sistemi kullanımı (yüzde 85 üzerinde uyarı, yüzde 95 üzerinde hata)
- **Yedeklemeler**: 10 günden uzun süredir yedeklenmeyen, zamanlamasının veya hedefinin gerisinde kalan ya da son doğrulaması başarısız olan depolar
- **Lisanslar**: süresi dolmuş, eksik, eşleşmeyen veya geçersiz depo lisansları ile yenilenmesi gereken lisanslar
- **Renet süreçleri**: değiştirilmiş bir renet ikilisini hâlâ çalıştıran daemon'lar
- **Depo sağlığı**: bağlı her deponun kendi `health()` sonucu (aşağıya bakın)
- **Sertifikalar**: süresi dolmak üzere olan proxy sertifikaları ve paylaşılan ACME challenge CNAME kayıtları
- **Sorunlar**: tespit edilen sorunlar

Çıkış kodu hükmü verir: `0` sağlıklı, `1` uyarı, `2` hata, `3` kritik (bozulan bir disk ya da yeniden başlatma döngüsündeki bir konteyner veya servis). Makine tarafından okunabilir çıktı için `--output json` kullanın; çıktı `repo_health` (depo başına bir rapor) ve `findings` alanlarını içerir, her bulgu bir kod, bir önem derecesi (`info`, `warning`, `error` veya `critical`), bir konu, bir ayrıntı ve düzeltmesi varsa `fix` taşır ([Onarım](#repair) bölümüne bakın).

## Depo Sağlığı

Bir Rediaccfile, deponun kendi servislerini denetleyen bir `health()` fonksiyonu tanımlayabilir ([Servisler](/tr/docs/services)): çıkış `0` tamam, `1` uyarı, `2` hata. Tek bir depo için şöyle çalıştırılır:

```bash
rdc repo health my-app@server-1
```

Komut, deponun Rediaccfile'ları arasındaki en kötü düzeyle çıkar. Hiçbir Rediaccfile'ın `health()` tanımlamadığı bir depo **denetim yok** yazdırır ve `0` ile çıkar; asla sağlıklı olarak bildirilmez. Zaman aşımına uğrayan, sonlandırılan veya başka bir kodla çıkan bir `health()` hatadır; makineye ulaşılamaması da öyledir (çıkış `2`).

`rdc machine health`, bağlı her deponun `health()` fonksiyonunu tek çağrıda çalıştırır ve en kötü düzeyi kendi çıkış koduna katar; her depo için uyarı (`repo.health.warning`) veya hata (`repo.health.error`) düzeyinde bir bulgu üretilir. Denetimi olmayan depolar listelenir, bildirilmez. Makinedeki renet depo sağlık denetimlerinden eskiyse sonuç tek bir uyarıdır, `renet.repo-health.unsupported`; `rdc machine setup` onu güncelleyene kadar böyle kalır.

## Sertifika Süresi ve ACME Challenge'ları

`rdc machine health`, proxy'nin ACME sertifikalarını okur ve süresinin dolmasına 21 günden az kalan her sertifika için (uyarı) veya 7 günden az kalanlar için (hata) `cert.expiry.near` bildirir. Proxy 30 gün önceden yeniler; dolayısıyla 21 günün altındaki bir sertifika, yenilemesinin en az dokuz gündür başarısız olduğu anlamına gelir.

Ayrıca bir sertifika adının `_acme-challenge.<name>` kaydı, kendisi `_acme-challenge.` adı olmayan bir ada CNAME ile gidiyorsa ya da iki ad aynı adda sona eriyorsa `acme.challenge.cname-shared` bildirir. CNAME olan bir joker karakter kaydı bu şekli üretir: tüm challenge'lar tek bir ada düşer ve yenilemeler çakışır. Bilinçli bir yetkilendirme (örneğin `_acme-challenge.mail.example.com` kaydının `_acme-challenge.mail.example.io` adına işaret etmesi) bildirilmez; amaçlanan diğer yetkilendirmeleri proxy'nin `config.env` dosyasındaki `ACME_DELEGATED_NAMES` değişkenine (sertifika adlarının virgülle ayrılmış listesi) yazın. Challenge zinciri çözümlenemeyen bir ad (DNS hatası veya zaman aşımı), denetim o ad için çalışmadığından bir uyarı olan `acme.challenge.unknown` olarak bildirilir.

## Onarım

Her bulgu bir kod taşır; güvenli bir düzeltme varsa ayrıca `action`, güvenlik `class` değeri ve `window_only` içeren bir `fix` taşır. `rdc machine health` salt okunur kalır; işlemi yapan komut `rdc machine repair` komutudur:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Sınıf | Anlamı |
|---|---|
| `auto-safe` | Varsayılan olarak çalışır: bir konteyneri veya Traefik'i yeniden başlatma, trim ve temizlik, ACME çapasını yazma |
| `auto-with-backup` | Yalnızca `--with-backup` ile, deponun başarılı bir anlık görüntüsünden sonra çalışır; anlık görüntü başarısız olursa düzeltme iptal edilir |
| `operator-only` | Asla çalışmaz. Komut, elle çalıştırılacak tam komutu yazdırır. Adlandırılmış veriyi silen veya para harcayan her şey burada yer alır |

`window_only`, sınıfın üzerine eklenen bir koşuldur: düzeltme yalnızca makinenin bakım penceresi içinde çalışır; pencere UTC saatiyle `HH:MM-HH:MM` biçimindedir (gece yarısını aşabilir). Penceresi olmayan bir makine bu düzeltmeleri kendiliğinden hiç çalıştırmaz; `--window-override` bunları elle çalıştırır. Pencereyi şöyle ayarlayın veya kaldırın:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Her düzeltme önce bulgusunun hâlâ var olduğunu denetler; bu yüzden ikinci çalıştırma yapacak bir şey bulmaz. Aynı şey üzerinde etkili olan düzeltmeler bir kez çalışır (tek bir Traefik yeniden başlatması tüm sertifikaları kapsar). Her düzeltme makine günlüğüne `rediacc-repair` etiketiyle ve JSON çıktısındaki `actions` alanına (`code`, `subject`, `action`, `class`, `result`, `before`, `after`) kaydedilir; çalıştırma tam bir yeniden denetimle biter. Çıkış kodu, geriye bir şey kalmadığında `0`, uyarılar veya operator-only öğeler kaldığında `1`, bir hata kaldığında ya da bir düzeltme başarısız olduğunda `2` olur.

| Bulgu | Düzeltme | Sınıf |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim, ardından durdurulmuş konteynerleri, sahipsiz anonim birimleri ve kullanılmayan imajları temizleme | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Konteyneri yeniden başlatma | auto-safe |
| `renet.binary.replaced` | Etkilenen depo denetleyicilerini yeniden başlatma (`rdc machine restart-services --include-docker`, yalnızca bunlarla sınırlı) | auto-safe, yalnızca pencerede |
| `cert.expiry.near` | Traefik'i yeniden başlatıp yenilemeyi yeniden deneme | auto-safe |
| `acme.challenge.cname-shared` | ACME çapasını yazma (aşağıya bakın) | auto-safe |
| `repo.health.warning`, `repo.health.error` | Deponun `repair()` fonksiyonunu çalıştırma ([Servisler](/tr/docs/services)) | Rediaccfile'ın bildirdiği sınıf |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Çalıştırılacak komut olarak yazdırılır | operator-only |

Düzeltmesi olmayan bulgular (SMART arızaları, sıcaklık, bellek, sistem diski, başarısız bir doğrulama) bildirilir ve operatöre bırakılır.

Temizlik hub'a asla dokunmaz: `rediacc.hub.*` etiketli konteynerler ile `rediacc.hub.user` etiketli veya adı `rediacc-hub-home-*` olan birimler dışarıda tutulur; böylece bir hub kullanıcısının ana dizini her alan geri kazanımından sağ çıkar. Trim ve temizliğin boşaltamadığı artık (adlandırılmış birimler, büyük uygulama verileri) operatörün kararı olarak kalır.

### Depo Onarımı

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair`, deponun `repair()` fonksiyonlarını aynı sınıflarla çalıştırır: `auto-safe` çalışır, `auto-with-backup` için `--with-backup` gerekir, bildirimi olmayan (`operator-only`) bir `repair()` ise yalnızca sorusu yanıtlandıktan sonra ya da `--yes` ile çalışır. Ardından `health()` yeniden çalışır ve çıkış kodu, sonunda ulaşılan düzeyi izler: `0` tamam veya denetim yok, `1` uyarı, `2` hata veya başarısız bir `repair()`.

### ACME Çapası

CNAME olan bir joker karakterli DNS kaydı, her `_acme-challenge.<host>` adının onu izlemesine yol açar; böylece tüm challenge'lar tek bir ada düşer ve yenilemeler çakışır (`acme.challenge.cname-shared`). Düzeltme, proxy'nin Cloudflare belirteci üzerinden çakışan her `_acme-challenge.<name>` adına `rediacc-acme-anchor` değerli bir TXT kaydı yazar, ardından Traefik'i yeniden başlatır. Açık bir kayıt adı joker karakterin kapsamından çıkarır ve challenge olması gereken yere düşer. Düzeltme yalnızca kayıt ekler; var olan bir çapaya dokunulmaz.

`ACME_DELEGATED_NAMES` içinde (proxy'nin `config.env` dosyasında sertifika adlarının virgülle ayrılmış listesi) yer alan adlar bilinçli yetkilendirmelerdir: hiçbir zaman çapalanmaz ve bildirilmez. Proxy'nin kullanılabilir bir Cloudflare belirteci yoksa düzeltme `config.env` içindeki `LEGO_DISABLE_CNAME_SUPPORT=true` ayarına başvurur, ancak yalnızca hiçbir yetkilendirilmiş ad bildirilmemişse; çünkü bu değişken tüm adlar için CNAME takibini kapatır. Bir yetkilendirme bildirilmişse bulgu operator-only kalır. Aynı düzeltme her proxy kurulumunda (`rdc machine infra push`) ve makinede `renet proxy acme-fix` ile tek başına çalışır.

## Konteynerleri Listeleme

Bir makinedeki tüm depolardaki çalışan konteynerleri görüntüleyin:

```bash
rdc machine status server-1 --containers
```

| Sütun | Açıklama |
|-------|----------|
| Name | Konteyner adı |
| Status | Çalışma süresi veya çıkış nedeni |
| State | Çalışıyor, çıktı vb. |
| Health | Sağlıklı, sağlıksız, yok |
| CPU | CPU kullanım yüzdesi |
| Memory | Bellek kullanımı / limit |
| Repository | Konteynerin ait olduğu depo |

Seçenekler:
- `--health-check`, Konteynerlerde aktif sağlık kontrolleri gerçekleştir
- `--output json`, Makine tarafından okunabilir JSON çıktısı

JSON çıktısı tam konteyner ayrıntılarını (`labels`, `port_mappings`, `image`, `id`) ve ayrıca `repository` (çözümlenmiş ad), `repository_guid` (orijinal GUID), `domain` ve `autoRoute` alanlarını içerir.

## Servisleri Listeleme

Bir makinedeki Rediacc ile ilgili systemd servislerini görüntüleyin:

```bash
rdc machine status server-1 --services
```

| Sütun | Açıklama |
|-------|----------|
| Name | Servis adı |
| State | Aktif, inaktif, başarısız |
| Sub-state | Çalışıyor, ölü vb. |
| Restarts | Yeniden başlatma sayısı |
| Memory | Servis bellek kullanımı |
| Repository | İlişkili depo |

Seçenekler:
- `--stability-check`, Kararsız servisleri işaretle (başarısız, 3'ten fazla yeniden başlatma, otomatik yeniden başlatma)
- `--output json`, Makine tarafından okunabilir JSON çıktısı

JSON çıktısı, `repository` (çözümlenmiş ad) ve `repository_guid` (orijinal GUID) ile birlikte tam servis ayrıntılarını içerir.

## Depoları Listeleme

Bir makinedeki depoları ayrıntılı istatistiklerle görüntüleyin:

```bash
rdc machine status server-1 --repositories
```

| Sütun | Açıklama |
|-------|----------|
| Name | Depo adı |
| Size | Disk imaj boyutu |
| Mount | Bağlı veya bağlı değil |
| Docker | Docker daemon çalışıyor veya durdurulmuş |
| Containers | Konteyner sayısı |
| Disk Usage | Depo içindeki gerçek disk kullanımı |
| Modified | Son değişiklik zamanı |

Seçenekler:
- `--search <text>`, Ad veya bağlama yoluna göre filtrele
- `--output json`, Makine tarafından okunabilir JSON çıktısı

JSON çıktısı `name` (çözümlenmiş) ve `guid` (orijinal GUID) alanlarını içerir; ayrıca her depo için `containers` (`domain`, `autoRoute`, `repository`/`repository_guid` ile birlikte) ve `services` dizilerini iç içe verir.

## Depolama Sağlığı

Bir makinedeki tüm depolarda BTRFS parçalanmasını ve reflink paylaşımını inceleyin:

```bash
rdc machine status server-1 --storage-health
```

| Sütun | Açıklama |
|-------|----------|
| Quota | Deponun maksimum boyutu (büyüme tavanı; oluşturma sırasında veya resize/auto-grow ile belirlenir) |
| Allocated | Seyrek görüntünün havuzda şu anda gerçekte kapladığı alan |
| Unique | Yalnızca bu depoya ait gerçek benzersiz veriler |
| Shared | BTRFS reflinkleri aracılığıyla depolar arasında yeniden kullanılan veri blokları (ücretsiz kopyalar) |
| Reclaimable | [`repo trim`](/tr/docs/repositories#reclaim-space-trim) komutunun havuza geri döndürebileceği, ayrılmış-kullanılan alan farkı. Bağlı olmayan depolar için `-` gösterir |
| Discards | Şifreli birimin discard'ları iletip iletmediği (güncel bir sürümle bağlanan her depo için `on`) |
| Divergence | Görüntünün paylaşılan yerine bu depoya özgü yüzdesi (yüksekse silindiğinde daha fazla alan geri kazanılır) |
| Frag | Copy-on-write görüntüsünde GB başına extent sayısı (yalnızca bilgi amaçlı) |

Quota ve allocation farklı sayılardır; bu kasıtlıdır: 20 GB kotayla 6 GB veri depolayan bir depo, havuza yalnızca ayırdığı kadar maliyet getirir. Havuz bu nedenle fiziksel kapasitesinden fazla toplam kota vaat edebilir; Reclaimable sütunu ise her deponun tahsisatından ne kadarının artık kullanılmadığını ve trim ile geri kazanılabileceğini gösterir.

Tablonun altında bir havuz özeti, datastore doluluk düzeyini ve yedekleme anlık görüntülerinin ne kadar alan kilitlediğini raporlar:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Yedekleme çalışırken anlık görüntüsü, canlı depolarla paylaştığı her bloğu referans almaya devam eder; bu nedenle bu yedekleme döngüsü tamamlanıp anlık görüntü silinene kadar silme ve trim işlemleri daha az havuz alanı serbest bırakır. Kesintiye uğramış yedeklemelerden kalan eski anlık görüntüler, depolama bakıcısı tarafından dakikalar içinde otomatik olarak kaldırılır.

Özet, BTRFS reflinklerinden elde edilen toplam tasarrufları gösterir:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Sanal boyut**, tüm depo imaj boyutlarının toplamıdır. Bu, depoların görünümüdür; ancak reflinkler aracılığıyla paylaşılan blokları çift sayar.
- **Benzersiz veriler**, yalnızca bir depoda var olan depo verileri tarafından tüketilen gerçek depolama alanıdır. Bir depoyu silerken serbest bırakacağınız alan budur.
- **Paylaşılan**, BTRFS reflinkleri aracılığıyla depolar arasında yeniden kullanılan verilerdir. Bir depoyu çatallama, her iki taraftan biri yeni veriler yazana kadar blokları paylaşan reflink kopyaları oluşturur; bu noktada bloklar ayrışır.
- **Verimlilik**, reflinkler aracılığıyla yeniden kullanılan verilerin yüzdesidir. Yüksek olması iyidir. Aynı üst depodan çok sayıda çatallanmaya sahip bir makine, yüzde 100'e yakın verimlilik gösterir.

Frag sütunu yalnızca bilgi amaçlıdır. Copy-on-write görüntü dosyasının extentlerini sayar, uygulamanızın içinde okuduğu dosyaları değil; bu nedenle normal rastgele yazma iş yükleri (veritabanları, konteyner katmanları) altında yüksek görünür ve SSD destekli depolarda okuma performansını tahmin etmez. Rediacc kasıtlı olarak birleştirme komutu sunmaz: `btrfs filesystem defragment`, reflink bağlantılı çatallamaların ve anlık görüntülerin paylaşımını kaldırır; bu durum, neredeyse dolu bir havuzda kullanımı önemli ölçüde artırabilirken kıyaslamalar ölçülebilir bir okuma kazancı olmadığını gösterir. Tam ölçümler ve gerekçe için bkz. [Parçalanma Sayınız Korkunç Görünüyor. Ne Kadara Mal Olduğunu Ölçtüm.](/tr/blog/i-benchmarked-btrfs-fragmentation).

Tarama paralel olarak çalışır ve depo sayısına ve boyutuna bağlı olarak 5-15 saniye sürer. `--storage-health` belirtilmediğinde, sorgu çıktısından sonra bir hatırlatıcı olarak tek satırlık bir ipucu görünür.

## BTRFS Scrub

Rediacc, her makinede haftalık BTRFS scrub işlemini otomatik olarak zamanlar. Scrub, veri deposundaki her veri bloğunu okur, sağlama toplamlarını doğrular ve herhangi bir bozulmayı raportar. Bu, sessiz veri bozulmasını (bitrot) yedeklemelere ve çatallara yayılmadan önce tespit eder.

Scrub, her Pazar günü 02:00 yerel saatte (makine zaman dilimi) en fazla 1 saate kadar rastgele bir gecikme ile çalışır. Çalışan servislerle çakışmaması için en düşük G/Ç önceliğiyle (`ionice idle`, `nice 19`) çalışır. SSD destekli makinelerde, her 100 GB veri deposu için yaklaşık 8 dakika bekleyin.

Scrub zamanlayıcısı, renet yükseltmesinden sonraki ilk daemon başlangıcında otomatik olarak yüklenir. Scrub politikası gelecekteki bir renet sürümünde değiştiğinde, bir sonraki daemon başlangıcında kullanıcı müdahalesi gerekmeksizin kendini günceller.

### Scrub durumu

Son scrubun sonucu, BTRFS biriminin dışında (`/var/lib/rediacc/scrub-last-result.json`) kaydedilir; bu sayede birimde sorun olsa bile okunabilir kalır. `rdc machine status --system` çıktısı bir `scrub_status` alanı içerir:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Durum | Anlam |
|-------|-------|
| `ok` | Son scrub hatasız tamamlandı |
| `never_run` | Scrub henüz çalışmadı (zamanlayıcı yeni yüklendi) |
| `overdue` | Son scrub 14 günden fazla önce yapıldı |
| `errors_found` | Scrub sağlama toplamı uyumsuzlukları buldu (`total_errors` ve `uncorrectable` sayımlarını kontrol edin) |
| `failed` | Scrub işlemi sıfır dışı bir kodla sonlandı |

`uncorrectable` sıfırdan büyükse, etkilenen bloklar otomatik olarak onarılamaz (tek diskli BTRFS'te yedekli kopya yoktur). Etkilenen depoyu en son yedekten geri yükleyin.

### Manuel scrub

Bir scrub'u hemen çalıştırmak için (örneğin, güç kesintisi veya disk taşıma sonrasında):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Sonuç aynı JSON dosyasına kaydedilir ve bir sonraki `rdc machine status --system` çağrısında hemen görünür.

## Makine Genel Görünümü

Dağıtım bilgileri dahil bir makinenin tam genel görünümünü alın:

```bash
rdc machine status server-1
```

Sağlanan bilgiler:
- Ana bilgisayar adı ve çalışma süresi
- Bellek, disk ve datastore kullanımı
- Toplam depo sayısı, bağlı olan sayısı ve Docker daemon'ının yanıt verdiği depo sayısı
- Depo başına ayrıntılı bilgi

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Bağlantı Testi

Bir makineye SSH bağlantısını doğrulayın:

```bash
rdc term connect server-1 -c "hostname"
```

Bu komut, başarılı olduğunda uzak ana bilgisayar adını yazdırır, başarısız olduğunda ise bir bağlantı hatası gösterir; böylece DNS'i, SSH portunu ve anahtar kimlik doğrulamasını tek adımda doğrulamış olursunuz.

## Tanılama (doctor)

Rediacc ortamınızın tam bir tanılama kontrolünü çalıştırın:

```bash
rdc doctor
```

| Kategori | Kontroller |
|----------|-----------|
| **Ortam** | Node.js sürümü, CLI sürümü, SEA modu, Go kurulumu, Docker kullanılabilirliği |
| **Renet** | İkili dosya konumu, sürüm, CRIU, rsync, SEA gömülü varlıklar |
| **Yapılandırma** | Aktif yapılandırma, adaptör, makineler, SSH anahtarı |
| **Sanallaştırma** | Sisteminizin yerel sanal makineler çalıştırıp çalıştıramayacağını kontrol eder (`rdc ops`) |

Her kontrol **OK**, **Uyarı** veya **Hata** olarak raporlanır. Herhangi bir sorunu giderirken ilk adım olarak bunu kullanın.

Çıkış kodları: `0` = tümü geçti, `1` = uyarılar, `2` = hatalar.

## Servis Hazırlık Kontrolleri

`repo up` sırasında renet, HTTP servislerini hazır ilan etmeden önce bağlantı kabul edene kadar bekler. Bu bekleme süreci, sağlık kontrollerinden haberdar olarak çalışır:

- Docker'ın **sağlıklı** olarak raporladığı konteynerler anında güvenilir kabul edilir; TCP sondasına gerek kalmaz.
- Sağlık kontrolünün `start_period` süresindeki konteynerler, uyarı yerine bilgilendirici bir not kaydeder; proxy, servis bağlanana kadar yeniden denemeyi sürdürür.
- Çalışan konteyneri olmayan Compose servisleri (örneğin etkin olmayan bir profilin arkasındakiler) atlanır.
- Geri kalan her şey TCP üzerinden en fazla 15 saniye boyunca yoklanır (bunu değiştirmek için `REDIACC_READINESS_TIMEOUT` değişkenini saniye cinsinden ayarlayın).

Yavaş başlayan servislere [Docker sağlık kontrolü](https://docs.docker.com/reference/dockerfile/#healthcheck) tanımlamak, renet'e yetkili bir hazır sinyali verir ve dağıtım çıktısındaki sonda gürültüsünü ortadan kaldırır.
