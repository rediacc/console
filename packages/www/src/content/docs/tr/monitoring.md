---
title: İzleme
description: >-
  Makine sağlığını, konteynerleri, servisleri, depoları izleyin ve tanılama
  çalıştırın.
category: Guides
order: 9
language: tr
sourceHash: "e2f5d37c534fc40d"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# İzleme

Rediacc, makine sağlığını, çalışan konteynerleri, servisleri, depo durumunu ve sistem tanılamalarını incelemek için yerleşik izleme komutları sunar.

## Makine Sağlığı

Bir makine için tam bir sağlık raporu alın:

```bash
rdc machine health --name server-1
```

Rapor içeriği:
- **Sistem**: çalışma süresi, disk kullanımı, datastore kullanımı
- **Konteynerler**: çalışan, sağlıklı ve sağlıksız konteyner sayıları
- **Depolama**: SMART sağlık durumu
- **Sorunlar**: tespit edilen sorunlar

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Konteynerleri Listeleme

Bir makinedeki tüm depolardaki çalışan konteynerleri görüntüleyin:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| Sütun | Açıklama |
|-------|----------|
| Quota | Deponun maksimum boyutu (büyüme tavanı; oluşturma sırasında veya resize/auto-grow ile belirlenir) |
| Allocated | Seyrek görüntünün havuzda şu anda gerçekte kapladığı alan |
| Unique | Yalnızca bu depoya ait gerçek benzersiz veriler |
| Shared | BTRFS reflinkleri aracılığıyla depolar arasında yeniden kullanılan veri blokları (ücretsiz kopyalar) |
| Reclaimable | [`repo trim`](/tr/docs/repositories#alan-kazanma-trim) komutunun havuza geri döndürebileceği, ayrılmış-kullanılan alan farkı. Bağlı olmayan depolar için `-` gösterir |
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

Son scrubun sonucu, BTRFS biriminin dışında (`/var/lib/rediacc/scrub-last-result.json`) kaydedilir; bu sayede birimde sorun olsa bile okunabilir kalır. `rdc machine query --system` çıktısı bir `scrub_status` alanı içerir:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Sonuç aynı JSON dosyasına kaydedilir ve bir sonraki `rdc machine query --system` çağrısında hemen görünür.

## Makine Genel Görünümü

Dağıtım bilgileri dahil bir makinenin tam genel görünümünü alın:

```bash
rdc machine query --name server-1
```

Sağlanan bilgiler:
- Ana bilgisayar adı ve çalışma süresi
- Bellek, disk ve datastore kullanımı
- Toplam depo sayısı, bağlı olan sayısı ve çalışan Docker sayısı
- Depo başına ayrıntılı bilgi

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Bağlantı Testi

Bir makineye SSH bağlantısını doğrulayın:

```bash
rdc term connect -m server-1 -c "hostname"
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
