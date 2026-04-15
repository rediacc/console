---
title: İzleme
description: >-
  Makine sağlığını, konteynerleri, servisleri, depoları izleyin ve tanılama
  çalıştırın.
category: Guides
order: 9
language: tr
sourceHash: "1b60f9a60324f737"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# İzleme

Rediacc, makine sağlığını, çalışan konteynerleri, servisleri, depo durumunu ve sistem tanılamalarını incelemek için yerleşik izleme komutları sunar.

## Makine Sağlığı

Bir makine için kapsamlı bir sağlık raporu alın:

```bash
rdc machine health server-1
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
rdc machine containers server-1
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
rdc machine services server-1
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
rdc machine repos server-1
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
| Size | LUKS imaj dosyasının boyutu (deponun görünümü) |
| Unique | Yalnızca bu depoya ait gerçek benzersiz veriler |
| Shared | BTRFS reflinkleri aracılığıyla depolar arasında yeniden kullanılan veri blokları (ücretsiz kopyalar) |
| Extents | Dosya extent sayısı (yüksek = daha fazla parçalanma) |
| Frag | Parçalanma düzeyi: düşük, orta veya yüksek |

Özet, BTRFS reflinklerinden elde edilen toplam tasarrufları gösterir:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Sanal boyut**, tüm depo imaj boyutlarının toplamıdır. Bu, depoların görünümüdür; ancak reflinkler aracılığıyla paylaşılan blokları çift sayar.
- **Benzersiz veriler**, yalnızca bir depoda var olan depo verileri tarafından tüketilen gerçek depolama alanıdır. Bir depoyu silerken serbest bırakacağınız alan budur.
- **Paylaşılan**, BTRFS reflinkleri aracılığıyla depolar arasında yeniden kullanılan verilerdir. Bir depoyu çatallama, her iki taraftan biri yeni veriler yazana kadar blokları paylaşan reflink kopyaları oluşturur; bu noktada bloklar ayrışır.
- **Verimlilik**, reflinkler aracılığıyla yeniden kullanılan verilerin yüzdesidir. Yüksek olması iyidir. Aynı üst depodan çok sayıda çatallanmaya sahip bir makine, %100'e yakın verimlilik gösterir.

Yüksek parçalanma ve sıfır paylaşılan blok içeren depolar `btrfs filesystem defragment` ile güvenle birleştirilebilir. Paylaşılan bloklar içeren depolar birleştirilmemelidir; çünkü birleştirme, paylaşılan blokları benzersiz kopyalarla değiştirerek disk kullanımını artırır.

Tarama paralel olarak çalışır ve depo sayısına ve boyutuna bağlı olarak 5-15 saniye sürer. `--storage-health` belirtilmediğinde, sorgu çıktısından sonra bir hatırlatıcı olarak tek satırlık bir ipucu görünür.

## BTRFS Scrub

Rediacc, her makinede haftalık BTRFS scrub işlemini otomatik olarak zamanlar. Scrub, veri deposundaki her veri bloğunu okur, sağlama toplamlarını doğrular ve herhangi bir bozulmayı raporlar. Bu, sessiz veri bozulmasını (bitrot) yedeklemelere ve çatallara yayılmadan önce tespit eder.

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

## Vault Durumu

Dağıtım bilgileri dahil bir makinenin tam genel görünümünü alın:

```bash
rdc machine vault-status --name server-1
```

Sağlanan bilgiler:
- Ana bilgisayar adı ve çalışma süresi
- Bellek, disk ve datastore kullanımı
- Toplam depo sayısı, bağlı olan sayısı ve çalışan Docker sayısı
- Depo başına ayrıntılı bilgi

Makine tarafından okunabilir çıktı için `--output json` kullanın.

## Bağlantı Testi

> **Yalnızca bulut adaptörü.** Yerel adaptörde, bağlantıyı doğrulamak için `rdc term connect -m server-1 -c "hostname"` kullanın.

Bir makineye SSH bağlantısını doğrulayın:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Rapor içeriği:
- Bağlantı durumu (başarılı/başarısız)
- Kullanılan kimlik doğrulama yöntemi
- SSH anahtar yapılandırması
- Genel anahtar dağıtım durumu
- Known hosts kaydı

Seçenekler:
- `--port <number>`, SSH portu (varsayılan: 22)
- `--save -m server-1`, Doğrulanmış ana bilgisayar anahtarını makine yapılandırmasına kaydet

## Tanılama (doctor)

Rediacc ortamınızın kapsamlı bir tanılama kontrolünü çalıştırın:

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
