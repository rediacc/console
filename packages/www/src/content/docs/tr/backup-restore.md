---
title: Yedekleme ve Geri Yükleme
description: >-
  Şifrelenmiş depoları harici depolamaya yedekleyin, yedeklerden geri yükleyin
  ve otomatik yedeklemeler planlayın.
category: Guides
order: 7
language: tr
sourceHash: "29bb767d837eab9a"
sourceCommit: "a3b80f4e653e80766813a8c1d7ef563f00904147"
---

# Yedekleme ve Geri Yükleme

Rediacc, şifrelenmiş depoları harici depolama sağlayıcılarına yedekleyebilir ve aynı veya farklı makinelerde geri yükleyebilir. Yedekler şifrelenmiştir; geri yükleme için deponun LUKS kimlik bilgisi gereklidir.

## Depolamayı Yapılandırma

Yedekleri göndermeden önce bir depolama sağlayıcısı kaydedin. Rediacc, rclone uyumlu tüm depolamaları destekler: S3, B2, Google Drive ve daha fazlası.

### rclone'dan İçe Aktarma

Zaten yapılandırılmış bir rclone uzak bağlantınız varsa:

```bash
rdc config storage import --file rclone.conf
```

Bu, bir rclone yapılandırma dosyasındaki depolama yapılandırmalarını mevcut yapılandırmaya aktarır. Desteklenen türler: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ve Swift.

### Depolamaları Görüntüleme

```bash
rdc config storage list
```

## Yedek Gönderme

Bir depo yedeğini harici depolamaya gönderin:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

Push, yazmadan önce her zaman hedef deponun bağlı olup olmadığını kontrol eder. Bağlı değilse işlem iptal edilir.

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama konumu |
| `--to-machine <machine>` | Makineden makineye yedekleme için hedef makine |
| `--dest <filename>` | Özel hedef dosya adı |
| `--checkpoint` | Göndermeden önce CRIU checkpoint oluştur (`rediacc.checkpoint=true` etiketli konteynerler için). Hedef `repo up` ile otomatik geri yüklenir |
| `--force` | Mevcut bir yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `--tag <tag>` | Yedeği etiketle |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedek Çekme / Geri Yükleme

Harici depolamadan bir depo yedeğini çekin:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull, yazmadan önce her zaman hedef deponun bağlı olup olmadığını kontrol eder. Bağlı değilse işlem iptal edilir.

| Seçenek | Açıklama |
|---------|----------|
| `--from <storage>` | Kaynak depolama konumu |
| `--from-machine <machine>` | Makineden makineye geri yükleme için kaynak makine |
| `--force` | Mevcut yerel yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedekleri Listeleme

Bir depolama konumundaki mevcut yedekleri görüntüleyin:

```bash
rdc repo backup list --from my-storage -m server-1
```

Çıktı, hem [zamanlanmış yedekleme klasörlerini](#zamanlanmis-yedeklemeler) (`hot/` ve `cold/`) birleştiren birleşik bir tablodur; böylece her yedeği tek bir görünümde görebilirsiniz:

| Sütun | Anlamı |
|---|---|
| `Mode` | `hot` veya `cold`. Bu girişin hangi zamanlanmış yedekleme klasöründe yer aldığı |
| `Name` | Yerel yapılandırmanızdan çözümlenen depo adı (yapılandırmada olmayan depolar için GUID'e geri döner) |
| `GUID` | Disk üzerindeki depo GUID'i |
| `Size` | Yedekleme dosyasının okunabilir boyutu |
| `Modified` | Depolama arka ucundan UTC zaman damgası |

Tek bir moda inmek için `--path` geçirin:

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

### Depolama düzeni

Zamanlanmış yedeklemeler, depolamanın yapılandırılmış klasörünün içinde mod başına alt klasörlere iner; böylece aynı depolama hem saatlik hem de haftalık akışları karıştırmadan temiz biçimde barındırır:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Bir depo hem `hot/` hem de `cold/` altında görünebilir (saatlik zamanlama anlık görüntüsünü alır; haftalık zamanlama tekrar alır). Birleşik liste her iki satırı da gösterir, böylece hangi akışların hangi depoları kapsadığı net olur.

## Toplu Senkronizasyon

Tüm depoları aynı anda gönderin veya çekin:

### Tümünü Depolamaya Gönder

```bash
rdc repo push --to my-storage -m server-1
```

### Tümünü Depolamadan Çek

```bash
rdc repo pull --from my-storage -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--to <storage>` | Hedef depolama (gönderme yönü) |
| `--from <storage>` | Kaynak depolama (çekme yönü) |
| `--repo <name>` | Belirli depoları senkronize et (tekrarlanabilir) |
| `--override` | Mevcut yedekleri geçersiz kıl |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Zamanlanmış Yedeklemeler

Rediacc, adlandırılmış yedekleme stratejileri kullanır. Her strateji bir zamanlama, yedekleme modu, isteğe bağlı bant genişliği sınırı ve dosya filtreleri tanımlar. Makineler, hangi yedeklemelerin çalıştırılacağını belirlemek için stratejileri adlarıyla referans alır.

### Yedekleme Modları

| Mod | Davranış | Kesinti Süresi |
|-----|----------|----------------|
| `hot` | Servisler çalışırken BTRFS anlık görüntüsü alınır (kilitlenme tutarlı) | Yok |
| `cold` | Servisler durdurulur, anlık görüntü alınır, servisler yeniden başlatılır, anlık görüntü yüklenir (uygulama tutarlı) | Depo başına durdur+başlat penceresi, depolar arasında paralelleştirilmiş. Aşağıdaki "Soğuk Yedekleme Kesinti Süresini Tahmin Etme" bölümüne bakın. |

Kilitlenme tutarlı anlık görüntülere izin veren servisler için `hot` kullanın. Garantili tutarlılığa ihtiyaç duyduğunuzda ve kısa yeniden başlatmayı kabul edebildiğinizde `cold` kullanın.

### Soğuk Yedekleme Semantiği

Soğuk yedekleme, dahil edilen her depo için üç aşamada çalışır: **durdur -- anlık görüntü -- başlat**. Garantilerin sınırlarını anlamak, operatörlerin kısmi arızaları erken tespit etmesine yardımcı olur.

**Soğuk yedeklemenin garantiledikleri:**

- Anlık görüntüden önce, dahil edilen her depodaki çalışan konteynerler Rediaccfile `down()` kancası aracılığıyla düzgün biçimde durdurulur ve depo başına Docker daemon sessiz hale getirilir. Anlık görüntü bu nedenle yalnızca kilitlenme tutarlı değil, uygulama tutarlıdır.
- Anlık görüntüden önce çalışan konteyner ID'lerinin kümesi `/var/run/rediacc/cold-backup-<guid>.running.json` adresinde bir sidecar dosyasına kaydedilir. Bu, "işimiz bittiğinde nelerin tekrar çalışıyor olması gerektiği" için gerçeğin kaynağıdır.
- Anlık görüntüden sonra, tam compose yığınını geri yüklemek için deponun Rediaccfile `up()` kancası çağrılır.
- `/var/run/rediacc/cold-backup-<guid>.status.json` adresindeki çalıştırma başına durum sidecar'ı her denemenin aşamasını, sonucunu ve hatalarını kaydeder.

**Soğuk yedeklemenin garanti ETMEDİKLERİ:**

- `up()` en iyi efors ile calısır. Soğuk yedeklemenin kontrolü dışındaki nedenlerle başarısız olabilir (`depends_on: service_healthy` koşulunun hala beklenmesi, compose dosyası sözdizimi hatası, görüntü çekerken geçici bir ağ arızası). Başarısız olduğunda, soğuk yedekleme hatayı hata seviyesinde günlüğe kaydeder, durum sidecar'ını yazar ve bir sonraki depoya geçer.
- `up()` başarısız olduğunda, **doğrudan yedek yeniden başlatma** devreye girer: çalışma sidecar'ı okunur ve kaydedilen her konteyner ID'si doğrudan Docker API aracılığıyla yeniden başlatılır (compose olmadan). Bu, Rediaccfile kancalarını yeniden çalıştırmadan compose akışında bir sorun olsa bile servisleri geri getirir.
- Bazı konteyner ID'leri için yedek de başarısız olursa (örneğin, Docker daemon'un kendisi çalışmıyorsa), sidecar **yerinde bırakılır**, böylece yönlendirici watchdog her tıkta yeniden denemeye devam edebilir.

**Watchdog kurtarma:** her tıkta watchdog, çalışma sidecar'ının varlığını kontrol eder. Orada listelenen ve şu anda durdurulmuş olan herhangi bir konteyner ID'si, *konteynerin kaydedilmiş `restart_policy`'sinden bağımsız olarak* yeniden başlatılır. Bu, `restart: on-failure` ile yapılandırılmış servislerin (Docker'ın temiz bir durdurmanın ardından yeniden başlatmayacağı) soğuk yedeklemeden sonra geri dönmesi anlamına gelir. Listelenen tüm konteynerler çalışır duruma geldiğinde sidecar silinir.

**Operatörlerin arızaları nasıl tespit edeceği:**

- `rdc machine query --name <machine> --containers` çalışma durumunu gösterir. Beklenen kümeyle karşılaştırın.
- Makinedeki `/var/run/rediacc/cold-backup-<guid>.status.json` dosyasını kontrol edin. `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` ile inceleyebilirsiniz. Eski bir `startedAt` ile birlikte `success: false`, son yedeklemenin temiz tamamlanmadığı anlamına gelir.
- renet yedekleme çalıştırmasından gelen günlükler (`journalctl -u renet-*` veya doğrudan `rdc machine backup schedule` çağrısı) `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` biçiminde bir son özet satırı yayar. Boş olmayan `failed_repos` grep hedefidir.

### Soğuk Yedekleme Kesinti Süresini Tahmin Etme

Her depo yalnızca kendi `down()` + `up()` penceresi boyunca kapalı kalır. Sıcak durumdaki bir makinede bu süreler tipik olarak:

| Depo şekli | Tipik durdur+başlat |
|------------|---------------------|
| Küçük (1-2 konteyner, DB yok) | 5-15 s |
| Orta (web uygulaması + önbellek) | 20-45 s |
| Ağır (DB + kuyruklar + posta) | 60-120 s |

Anlık görüntü adımı (`btrfs subvolume snapshot -r`) depo boyutundan bağımsız olarak O(1)'dir: 0,1-1 s. Bir depo, diğer depoların anlık görüntüleri için kapalı tutulmaz. Yükleyici daha sonra salt okunur bir anlık görüntüye karşı çalışır ve bu sırada tüm depolar zaten yeniden çalışır durumdadır.

**Tüm çalıştırmanın toplam süresi**, kaç deponun eşzamanlı olarak yeniden başlatıldığına göre belirlenir. renet bu değeri makineden türetir:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Örnekler:

| Makine | Depolar | Eşzamanlılık | Yeniden başlatma süresi |
|--------|---------|--------------|-------------------------|
| 4 CPU VM | 5 depo, ortalama 30 s | 2 | ~75 s |
| 16 CPU sunucu | 10 depo, ortalama 40 s | 8 | ~80 s |
| 64 CPU filo düğümü | 50 depo, ortalama 40 s | 8 | ~4 dk |

**Ortam değişkeniyle geçersiz kılma:** Belirli bir değere sabitlemek için yedekleme servisinin ortamında (genellikle bir systemd drop-in ile) `REDIACC_COLD_BACKUP_CONCURRENCY=N` ayarlayın. `=1` kesinlikle seri yeniden başlatmayı zorlar; bir deponun `up()` kancasındaki bir çökme döngüsünü hata ayıklarken faydalıdır.

Gecikmeye duyarlı bir depo çalıştırıyorsanız (genel web uygulaması, posta), kesinti süresi tüm çalıştırma uzunluğuyla değil, kendi durdur+başlat süresiyle (tipik olarak 30-90 s) sınırlıdır. Depolar, keşfedildikleri sırayla eşzamanlılık slotlarına yerleştirilir; öncelik sırası yoktur. Daha ince zamanlama gerekiyorsa ağır depoları kendi `--exclude` kapsamlı stratejilerine ayırın.

### Uzun Süren Yedeklemeler ve Çakışan Zamanlamalar

Kendi zamanlama aralığından daha uzun süren bir soğuk yedekleme (örneğin, 500 GB'lık bir deponun ilk tohumlanması mütevazı bir bağlantıda meşru olarak 24 saatten fazla sürebilir ve bu sırada gecelik zamanlayıcı tekrar tetiklenir), ikinci bir çalıştırmayı kuyruğa almaz veya başlatmaz. systemd `Type=oneshot` birimi tek bir örnektir: zamanlayıcı tetiklendiğinde ve servis zaten `activating` durumundayken, systemd başlatmayı mevcut işe birleştirir. Hiçbir yeni süreç başlatılmaz, hiçbir çalıştırma sonraya ertelenmez.

Somut olarak, Pazartesi 03:00 UTC'de başlayan ve Perşembe öğle saatlerinde biten bir çalıştırma:

| Gün | 03:00 UTC tetiklemesi | Sonuç |
|-----|----------------------|-------|
| Pazartesi | İlk tetikleme | Çalıştırma başlar |
| Salı | İkinci tetikleme | Sessizce bırakıldı (önceki çalıştırma hâlâ aktif) |
| Çarşamba | Üçüncü tetikleme | Sessizce bırakıldı (önceki çalıştırma hâlâ aktif) |
| Perşembe | Çalıştırma öğlen biter | Yakalama yok; sonraki çalıştırma Cuma 03:00 UTC |

Zamanlayıcının `Persistent=true` direktifi bu tetiklemeleri **kurtarmaz**. `Persistent=true`, zamanlayıcının kendisi inaktif olduğu için (sistem kapalı, zamanlayıcı devre dışı) kaçırılan tetiklemeleri yeniden oynatır. Servis meşgul olduğu için bırakılan tetiklemeler kaybolur.

Bu varsayılan davranış kasıtlıdır. Aynı datastore'a karşı iki soğuk yedeklemeyi paralel olarak çalıştırmak, BTRFS anlık görüntü yolu, rclone uzak bağlantısı ve `/var/run/rediacc/cold-backup-<guid>.status.json` konumundaki depo başına sidecar'lar için çekişmeye yol açacaktır. Uzun süren bir örneğin arkasına serileştirmek güvenli sonuçtur.

**İzleme sonucu.** Takılı bir yedekleme (örneğin, bir ağ kara deliğine takılan rclone) sonraki her zamanlayıcı tetiklemesini sessizce bırakır. Zamanlayıcı hiçbir alarm vermez. `systemctl show <unit> -p ActiveEnterTimestamp` izleyin: servis beklenen çalışma süresinden daha uzun süre `activating` durumundaysa (örneğin, gecelik zamanlayıcıda 48 saatten fazla), araştırın.

**Her zamanlanmış tetiklemenin çalışmasını istiyorsanız**, zamanlayıcıyı `OnCalendar=<cron>` yerine `OnUnitInactiveSec=<aralık>` olarak değiştirin. Bu, sabit bir duvar saati zamanlaması yerine önceki çalıştırmanın tamamlanmasından N saat sonra tetiklenir, böylece uzun süren çalıştırmalar düşüşlere neden olmaz. Yalnızca bir sonraki çalıştırmayı ileriye iter. Takas zamanlama sapmasıdır: 03:00 gecelik «sonuncusunun bittiği saatten 24 saat sonra» olur.

### Strateji Tanımlama

Standart varsayılan, iki stratejili bir bölüştürmedir: her depoyu yakalayan hızlı bir saatlik sıcak akış ve uygulama tutarlı anlık görüntüler alan daha yavaş bir haftalık soğuk akış. İki strateji farklı depolama alt klasörlerine (`hot/` ve `cold/`) yazar, böylece yedeklemeler asla karışmaz.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Soğuk strateji üzerindeki `--exclude` filtresi, haftalık bakım pencerenize sığmayan çok büyük depolar için önerilen kaçış noktasıdır. Saatlik sıcak strateji onları yine de kapsar; soğuk yalnızca atlar. `--exclude` içindeki depo adları yerel yapılandırma depo adıyla eşleşir (`:tag` olmadan).

| Seçenek | Açıklama |
|---------|----------|
| `--name <name>` | Strateji adı (makine bağlama için kullanılır) |
| `--destination <storage>` | Yüklenecek depolama sağlayıcısı |
| `--cron <expression>` | Cron ifadesi (örn. `"0 2 * * *"` günlük saat 02:00 için) |
| `--mode <hot\|cold>` | Yedekleme modu |
| `--bwlimit <limit>` | Yüklemeler için bant genişliği sınırı (örn. `10M`) |
| `--include <pattern>` | Dahil etme filtresi (tekrarlanabilir) |
| `--exclude <pattern>` | Hariç tutma filtresi (tekrarlanabilir) |
| `--enable` / `--disable` | Stratejiyi etkinleştir veya devre dışı bırak |

### Stratejileri Görüntüleme

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Strateji Kaldırma

```bash
rdc config backup-strategy remove --name weekly-cold
```

### Stratejileri Makineye Bağlama

Yapılandırmanızda bir veya daha fazla strateji adını bir makineye bağlayın:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Bağlama yalnızca yerel yapılandırmadır.** Bir strateji tanımlamak ve makineye bağlamak makineyi etkilemez. systemd zamanlayıcılarını dağıtmak için `rdc machine backup schedule -m <machine>` komutunu çalıştırın ([Zamanlamayı Makineye Dağıtma](#zamanlamayı-makineye-dağıtma) bölümüne bakın) ve her strateji veya bağlama değişikliğinden sonra tekrar çalıştırın.

## Sıcak ve Soğuk Seçimi ve Depo Başına Filtreleme

### Sıcak ve soğuk: özet

| | Sıcak | Soğuk |
|---|-------|-------|
| **Tutarlılık** | Kilitlenme tutarlı (çalışırken BTRFS anlık görüntüsü) | Uygulama tutarlı (durdur → anlık görüntü → başlat) |
| **Kesinti** | Yok | Depo başına durdur+başlat penceresi (genellikle 5-120 s) |
| **Uygun sıklık** | Yüksek (örn. saatlik) | Düşük (örn. günlük veya haftalık) |
| **Tipik kullanım** | Sık güvenlik ağı | Zamanlanmış garantili tutarlılık yedeklemesi |

**Sıcak**, yüksek frekanslı çalıştırmalar için doğru varsayılandır. Anlık görüntü alınırken servisler çalışmaya devam eder, bu nedenle yedekleme penceresi kullanıcıları kesintiye uğratmaz. Anlık görüntü kilitlenme tutarlıdır: temiz olmayan bir kapanmanın ardından elde edeceğinize eşdeğerdir. Çoğu modern veritabanı ve mesaj kuyruğu için bu kabul edilebilir.

**Soğuk**, garantili uygulama tutarlı bir anlık görüntüye ihtiyaç duyduğunuzda ve kısa bir depo başına yeniden başlatmayı kabul edebildiğinizde uygundur. Servisler anlık görüntüden önce durdurulur ve yükleme başlamadan önce yeniden başlatılır; bu nedenle yavaş veya başarısız bir yükleme kesinti penceresini hiçbir zaman uzatmaz. Tam garanti modeli için bkz. [Soğuk Yedekleme Semantiği](#soğuk-yedekleme-semantiği).

### Strateji başına depo filtreleme

Her strateji `--include` ve `--exclude` filtreleri taşıyabilir. Bir `--exclude` kalıbıyla eşleşen depo adları o strateji için atlanır; `--include` yalnızca bu adlarla çalıştırmayı kısıtlar. Filtreler yerel yapılandırma depo adıyla eşleşir (`:tag` olmadan).

```bash
# Sıcak strateji: her şeyi saatlik olarak yedekle
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Soğuk strateji: büyük türetilmiş veri kümesi hariç her şeyi haftalık yedekle
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Bir depoyu sık çalışan sıcak stratejiden ne zaman hariç tutmalı

Yüksek frekanslı çalıştırmadan bir depoyu hariç tutun:

- Depo büyükse ve zaten birimdeki kaynak verilerden **tamamen yeniden üretilebiliyorsa**, her saatlik yedekleme anlamlı bir kurtarma değeri katmadan önemli bant genişliği harcar.
- Mevcut yükleme hızınızda yedekleme çalıştırması kendi zamanlama aralığını aşacaksa.

**Örnek.** `analytics-demo` deposu, aynı birim içinde saklanan ham CSV döküm dosyalarından tamamen yeniden oluşturulabilen yaklaşık 114 GB türetilmiş Postgres tabloları içerir. 6 MB/s yükleme sınırıyla, bu deponun tek bir sıcak yedeklemesi 5 saatten fazla sürer. Saatlik çalıştırmak, bir sonraki başlamadan her çalıştırmanın hâlâ devam ettiği anlamına gelir; bu da sonraki her çalıştırmanın sessizce bırakılmasına neden olur (bkz. [Uzun Süren Yedeklemeler ve Çakışan Zamanlamalar](#uzun-süren-yedeklemeler-ve-çakışan-zamanlamalar)). `hourly-hot` stratejisinden hariç tutmak ve `weekly-cold` stratejisinde bırakmak, hiç yapılmaması yerine haftada bir yedekleme yapılması anlamına gelir.

> **Veriler tamamen yeniden üretilebiliyorsa**, hiç yedeklemeniz gerekip gerekmediğini düşünün. Bir alternatif, yalnızca ham kaynak girdileri (bu örnekte CSV dökümleri) yedeklemek ve türetilmiş kopyayı tamamen atlamaktır. Kaynak girdilerin haftalık soğuk yedeklemesi çok daha küçük ve kurtarma için tamamen yeterlidir.

Her iki stratejiden de hariç tutulmayan depolar hem `hot/` hem de `cold/` depolama alt klasörlerinde görünür. Birleşik `rdc repo backup list` çıktısı her iki satırı da gösterir; böylece hangi akışların hangi depoları kapsadığını doğrulayabilirsiniz.

## Yedekleme İşlemleri

### Zamanlamayı Makineye Dağıtma

Bağlı stratejileri bir makineye systemd zamanlayıcıları olarak gönderin:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

Dağıtım bir durum uzlaştırıcıdır. Makinedeki mevcut birim dosyalarını ve systemd durumunu okur, yapılandırmanın üreteceği içerikle karşılaştırır (dosya başına SHA-256) ve yalnızca içeriği gerçekten değişen birimlere dokunur. Yapılandırma değişikliği olmadan yeniden çalıştırmak bir no-op'tur: yazma yok, `daemon-reload` yok, zamanlayıcı gürültüsü yok.

`--dry-run` her strateji için planı yazdırır (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) ve makineye dokunmaz. Oluşturulan birim gövdelerini de yazdırmak için `--debug` ile birlikte kullanın; rclone token'ları gizlenir.

Güncellemek veya kaldırmak üzere olduğunuz bir strateji için şu anda bir yedekleme çalışıyorsa, dağıtım hızlıca başarısız olur ve onu iptal etmeniz ya da `--force` geçirmeniz önerilir. `--force` ile, çalışan işlem belleğindeki birimini korur ve yeni yapılandırma bir sonraki zamanlayıcı tetiklemesinde geçerli olur; çalışan yedekleme asla sonlandırılmaz.

`--reset-failed` isteğe bağlıdır. Geçirildiğinde, başarılı bir dağıtımdan sonra dokunulan servislerde systemd'nin failed durumunu temizler. Varsayılan olarak kapalıdır, böylece önceki arıza sinyalleri uyarı sistemleri için görünür kalır.

### Şimdi Yedekleme Çalıştırma

Zamanlayıcıyı beklemeden hemen yedekleme başlatın. `systemd-run` kullanarak geçici yürütme ile zamanlayıcı dağıtılmamış olsa bile çalışır:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### Yedekleme Durumunu Görüntüleme

Yedekleme zamanlayıcılarının mevcut durumunu ve son iş sonuçlarını gösterir:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Çalışan Yedeklemeyi İptal Etme

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Depo Migrasyonu

Bir depoyu bir makineden diğerine taşıyın:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Seçenek | Açıklama |
|---------|----------|
| `--name <repo>` | Migrasyon yapılacak depo |
| `--from <machine>` | Kaynak makine |
| `--to <machine>` | Hedef makine |
| `--provision` | Aktarımdan önce hedefte depoyu hazırla |
| `--checkpoint` | Migrasyondan önce CRIU checkpoint oluştur |
| `--skip-dns` | Migrasyondan sonra DNS kaydı güncellemeyi atla |
| `--bwlimit <limit>` | Transfer için bant genişliği sınırı (örn. `50M`) |

Migrasyon, şifrelenmiş depo verilerini rsync aracılığıyla aktarır. Kaynak depo, siz açıkça kaldırana kadar bozulmadan kalır.

## Depolamayı Tarama

Bir depolama konumunun içeriğini tarayın:

```bash
rdc storage browse --name my-storage
```

## En İyi Uygulamalar

- Kritik veriler için uygulama tutarlı anlık görüntüler almak amacıyla günlük soğuk yedeklemeler zamanlayın
- Sıfır kesinti gerektiren yüksek frekanslı anlık görüntüler için sıcak yedeklemeleri kullanın
- Yedek bütünlüğünü doğrulamak için geri yüklemeleri periyodik olarak test edin
- Kritik veriler için birden fazla depolama sağlayıcısı kullanın (örn. S3 + B2)
- Kimlik bilgilerini güvende tutun; yedekler şifrelenmiştir ancak geri yükleme için LUKS kimlik bilgisi gereklidir
