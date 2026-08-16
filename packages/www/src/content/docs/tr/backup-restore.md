---
title: "Yedekleme ve Geri Yükleme"
description: "Şifrelenmiş depoları iki şekilde yedekleyin: yalnızca değişen hücreleri yükleyen içerik adresli parça depolama veya herhangi bir rclone uyumlu depolamaya tam gönderim. Herhangi bir makinede geri yükleyin ve adlandırılmış stratejiler ile systemd zamanlayıcıları aracılığıyla otomatikleştirin."
category: "Guides"
order: 7
language: tr
sourceHash: "df8a9d53f6991817"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Yedekleme ve Geri Yükleme

Rediacc, şifrelenmiş depoları harici depolama sağlayıcılarına yedekleyebilir ve aynı veya farklı makinelerde geri yükleyebilir. Yedekler şifrelenmiştir; geri yükleme için deponun LUKS kimlik bilgisi gereklidir.

## İki yedekleme yolu

Rediacc'ın iki bağımsız yedekleme yolu vardır ve bu kılavuz ikisini de ele alır. Farklı depolama ve farklı komutlar kullanırlar; bu yüzden biriyle yedeklenen bir depo, diğeriyle yedeklenmiş sayılmaz.

**Parça depolama** (`rdc backup snapshot`) depo imajını içeriğe göre adreslenen sabit boyutlu hücreler halinde yükler. İlk çalıştırma sıfır olmayan tüm envanteri yükler; sonraki her çalıştırma, imajın tamamını okumak yerine dosya sistemi ayırma meta verilerinden belirlenen yalnızca değişen hücreleri yükler. Aynı hücreler, anlık görüntüler arasında ve bir fork ailesinin tamamında yalnızca bir kez saklanır; kullanım da depolama kotanıza (`rdc backup usage`) göre ölçülür.

**Depolama gönderimi kullanımdan kaldırıldı.** `rdc repo push --to <storage>`, kendinizin kaydettiği rclone uyumlu bir sağlayıcıya tam bir yedek dosyası kopyalıyordu. rclone tarafı tamamen kaldırıldı; push, pull, list ve restore artık bir depolama hedefini reddedip sizi buraya yönlendiriyor. Makineden makineye aktarım etkilenmedi: zaten hiç rclone üzerinden geçmiyordu.

Parça depolamadan geri yükleme çalışır: `rdc backup restore <repo> --at <snapshot-id>` saklanan bir anlık görüntüyü somutlaştırır ve `--at` RFC 3339 zaman damgasını da kabul eder; bu, anlık görüntü envanterine göre çözümlenir. Farklı bir ad altında geri yüklemek için `--as <name>` ekleyin ve sonra depoyu ayağa kaldırmak için `--up` ekleyin. Parça depolama ayrıca yükleme (`rdc backup snapshot`), doğrulama (`rdc backup verify` ve `--deep` kullanarak her hücreyi örnekle değil yeniden karma), anlık görüntü envanteri (`rdc backup manifests`) ve kota muhasebesi (`rdc backup usage`) sağlar.

### Parça depolama komutları

```bash
# Bir anlık görüntü yükle. İlk çalıştırma tohumlar, sonrakiler yalnızca değişen hücreleri gönderir.
rdc backup snapshot my-app

# Yüklemeden planla: nelerin taşınacağını bildirir.
rdc backup snapshot my-app --dry-run

# Yerel çıpaya güvenme ve tüm envanteri yeniden yükle.
# Bu her şeyi yeniden yükler ve kotayı yeniden düşer; yalnızca çıpanın
# bozuk olduğu bilindiğinde kullanın.
rdc backup snapshot my-app --reseed

# Saklanan envanteri ve kotanızı kontrol edin.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

## Soğuk Anlık Görüntüler (`--cold`)

Soğuk anlık görüntü, depoyu dondurmadan önce durdurur; böylece saklanan imaj yalnızca kilitlenme tutarlı değil, uygulama tutarlı olur. Komut makinenin kendisinde çalışır:

```bash
# Varsayılan datastore üzerindeki her depo.
sudo renet backup snapshot --cold

# Yalnızca adını verdiğiniz depolar. --repo bir depo GUID'i alır ve tekrarlanabilir.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` ile `--dry-run` birlikte kullanılamaz. Konteynerleri durduran bir prova çalıştırması prova sayılmaz, durdurmayan bir çalıştırma da soğuk sayılmaz; bu yüzden renet sizin yerinize bir anlam seçmek yerine ikiliyi reddeder.

### Soğuk çalıştırma ne yapar

Seçilen her depo için, şu sırayla:

1. Deponun konteynerlerini durdurur.
2. Depo bağlama noktasını ve datastore'u diske yazar.
3. Konteynerlerin gerçekten durduğunu doğrular.
4. Depo imajının yaz-kopyala (reflink) kopyasını alır.
5. Konteynerleri yeniden başlatır.

Yükleme ancak bundan sonra başlar; o sırada bütün depolar çoktan ayaktadır.

Kesinti dondurma süresidir, aktarım süresi değil. Reflink yalnızca meta veridir; depo 1 GB da tutsa 100 GB da tutsa aynı sürer. Yükleme öyle değildir: değişen bayt sayısıyla birlikte büyür ve ilk anlık görüntü sıfır olmayan envanterin tamamını yükler. Konteynerleri yükleme bitene kadar kapalı tutmak kesintiyi veri boyutuna bağlardı; ilk yedeklemede bu, milisaniyeler yerine saatler demektir.

Seçilen depoların hepsi tek tek değil, tek bir pencerede durdurulur. Bu, depo başına biraz daha uzun kesinti demektir ve karşılığında tüm depo grubu için tek bir tutarlılık noktası verir.

Çalışan konteyneri olmayan bir depo zaten sessizdir. Hiç kesinti olmadan yedeklenir; bu bir hata değil, olağan bir sonuçtur.

### Kesintinin maliyeti

Gerçek bir makinede ölçüldüğünde toplam kesinti **222 ms** oldu:

| Aşama | Ölçülen | Ne olur |
|-------|---------|---------|
| `cold_down` | 64 ms | Konteynerler durur |
| `cold_sync` | 26 ms | Depo bağlama noktaları ve datastore diske yazılır |
| `cold_verify` | 31 ms | Konteynerlerin durduğu doğrulanır |
| `cold_stage` | 0 ms | Depo imajının reflink kopyası |
| `cold_up` | 99 ms | Konteynerler yeniden başlar |

Baskın olan, konteynerlerin yeniden başlaması; hazırlama aşaması ise neredeyse bedava: reflink milisaniye çözünürlüğünde görünmüyor bile. Yine de bu sıfırı tek başına değil, depo başına kayıtlarla birlikte okuyun. Her depoyu reddeden bir çalıştırma da `cold_stage=0ms` bildirir; hangisiyle karşı karşıya olduğunuzu yalnızca kayıtlar söyler.

Bu döküm süs değil, kanıttır. Bu beş aşamanın hiçbiri depo verisi okumaz ya da göndermez; dolayısıyla yedek büyüdükçe hiçbiri büyümez. Büyüyen tek kısım olan yükleme ise kesinti bittikten sonra çalışır.

renet, çalıştırma bitince aynı sayıları yazdırır; böylece bizim ölçümümüze güvenmek yerine kendi makinelerinizi ölçebilirsiniz:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Her deponun JSON kaydı da aynı kesintiyi ve aynı aşamaları taşır; böylece bir anlık görüntünün soğuk mu sıcak mı olduğu sürelerden tahmin edilmeden anlaşılır.

### Soğuğu ne zaman seçmeli

Varsayılan sıcaktır ve depoların çoğu için doğru seçim de odur. Sıcak anlık görüntü kilitlenme tutarlıdır; yani deponun elektrik kesintisinden sonraki hâline denktir ve hiç kesinti maliyeti yoktur. Veritabanlarının ve kuyrukların çoğu bu durumdan kendi kendine toparlanır.

Soğuğu, yazılırken güvenle yakalanamayacak veriler için seçin. Kendi write-ahead log'unu ve bellekteki durumunu tutan bir veritabanı en tipik örnektir. Kısa ve ölçülmüş bir kesintiyi, uygulamanın önce kendini onarmadan açabileceği bir anlık görüntüyle takas etmiş olursunuz.

### Soğuk çalıştırmanın reddettikleri

Reddetmek burada bir özelliktir. Hiçbir şeyi durdurmamış ama soğuk etiketi taşıyan bir yedek, ancak geri yükleme sırasında fark edeceğiniz bir yalandır; bu yüzden renet soğuk bir çalıştırmayı sessizce sıcağa düşürmez:

- **Durmayan konteynerler.** Durdurmanın ardından renet, deponun kendi Docker soketine hâlâ çalışan bir şey olup olmadığını sorar. Varsa o depo yedeklenmez, reddedilir. Denetim güvenli tarafta kalır: sokete ulaşılamıyorsa ya da konteyner listesi okunamıyorsa durdurma doğrulanmamış sayılır ve doğrulanmamış olan reddedilir.
- **Okunamayan lisans.** Lisanslar kesintiden sonra değil, önce denetlenir; çünkü lisansı okunamayan bir depo zaten hiçbir şey yükleyemezdi. Böyle bir depo durdurulmadan atlanır. Seçilen depoların hiçbirinin okunabilir lisansı yoksa, tek bir konteyner bile inmeden çalıştırmanın tamamı reddedilir.
- **Aynı datastore üzerinde ikinci bir soğuk çalıştırma.** Kilit datastore'un tamamını kapsar ve dolu bir kilit, hiçbir şeyi durdurmamış olarak anında reddedilir. Üst üste binen iki çalıştırmadan her biri, diğerinin kendisine ait saydığı konteynerleri durdururdu; ikincisi de birincisinin hâlâ dondurmakta olduğu depoları başlatırdı. Çalıştırmayı atlayıp bir sonrakini beklemek bundan iyidir.

Konteynerler kapalıyken bir çalıştırma `systemctl stop` ya da yeniden başlatma yüzünden kesilirse, renet çıkmadan önce onları yeniden başlatır. Makinedeki kurtarma da ağ görevi görür: sahibi ortadan kaybolmuş bir soğuk yedeği fark eder ve o depoları yeniden ayağa kaldırır.

## Depolamayı Yapılandırma

Yedekleri göndermeden önce bir depolama sağlayıcısı kaydedin. Rediacc, rclone uyumlu tüm depolamaları destekler: S3, B2, Google Drive ve daha fazlası.

### rclone'dan İçe Aktarma

Zaten yapılandırılmış bir rclone uzak bağlantınız varsa:

```bash
rdc storage import rclone.conf
```

Bu, bir rclone yapılandırma dosyasındaki depolama yapılandırmalarını mevcut yapılandırmaya aktarır. Desteklenen türler: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ve Swift.

### Depolamaları Görüntüleme

```bash
rdc storage list
```

## Yedeği Başka Bir Makineye Gönderme

Bir depoyu SSH üzerinden ikinci bir makineye kopyalayın:

```bash
rdc repo push my-app --to-machine server-1
```

Şifreli imaj AYNI GUID ile kopyalanır; dolayısıyla bu bir fork değil, bir yedekleme veya taşımadır. Bağımsız bir kopya elde etmek için önce `rdc repo fork` çalıştırıp forku gönderin.

Belirli bir ana ait yedek için bunun yerine parça depolamayı kullanın: `rdc backup snapshot my-app` yalnızca değişen hücreleri yükler, `rdc backup restore my-app --at <snapshot>` ise bunlardan herhangi birini geri getirir.

| Seçenek | Açıklama |
|---------|----------|
| `--to-machine <machine>` | Makineden makineye yedekleme için hedef makine |
| `--dest <filename>` | Özel hedef dosya adı |
| `--checkpoint` | Göndermeden önce CRIU checkpoint oluştur (`rediacc.checkpoint=true` etiketli konteynerler için). Hedef `repo up` ile otomatik geri yüklenir |
| `--force` | Mevcut bir yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `--tag <tag>` | Yedeği etiketle |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedeği Başka Bir Makineden Çekme

Depoyu, üzerinde bulunduğu makineden geri getirin:

```bash
rdc repo pull my-app --from-machine server-1
```

Bunun yerine parça depolamadan geri yüklemek için
`rdc backup restore my-app --at <snapshot-id>` kullanın.

Pull, o an **bağlı** olan bir deponun üzerine yazmayı reddeder. Önce bağlantısını keyin, pull işlemini yapın, ardından `rdc repo up` ile tekrar ayağa kaldırın. Dizin tabanlı depolar istisnadır: bağlıyken bile yerinde senkronize olurlar.

| Seçenek | Açıklama |
|---------|----------|
| `--from-machine <machine>` | Makineden makineye geri yükleme için kaynak makine |
| `--force` | Mevcut yerel yedeği geçersiz kıl |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`, `500K`) |
| `-w, --watch` | İşlem ilerlemesini izle |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Yedekleri Listeleme

Parça depolamadaki anlık görüntüleri listeleyin:

```bash
rdc backup manifests my-app
```

Bir makinede duran yedek dosyalarını görmek için:

```bash
rdc backup list -m server-1
```

Çıktı, parça depolamanın bu depo için sakladığı anlık görüntüleri listeler:

| Sütun | Anlamı |
|---|---|
| `Mode` | `hot` veya `cold`. Bu girişin hangi zamanlanmış yedekleme klasöründe yer aldığı |
| `Name` | Yerel yapılandırmanızdan çözümlenen depo adı (yapılandırmada olmayan depolar için GUID'e geri döner) |
| `GUID` | Disk üzerindeki depo GUID'i |
| `Size` | Yedekleme dosyasının okunabilir boyutu |
| `Modified` | Depolama arka ucundan UTC zaman damgası |

Bir depolama arka ucunu listelemek, rclone tarafıyla birlikte kullanımdan kaldırıldı; komut reddedilir ve şu iki yerine geçen komutu belirtir.

### Sıcak ve soğuk gerçekte ne anlama gelir

`--mode hot` ve `--mode cold`, verinin nereye yazıldığını değil, yedek alınırken deponun nasıl ele alındığını tanımlar.

**Sıcak**, çalışan bir deponun anlık görüntüsünü alır. Konteynerler hizmet vermeye devam eder ve imaj yazma işleminin ortasında yakalanır; bu yüzden yedek kilitlenme tutarlıdır: makinenin tam o anda elektriğinin kesilmesiyle elde edeceğiniz durumun aynısı. Bu, kendi jurnalinden kurtarabilen her şey için, yani çoğu veritabanı için sorun teşkil etmez.

**Soğuk**, önce konteynerleri durdurur, diske yazar, gerçekten durduklarını doğrular, imajı dondurur ve ancak ondan sonra yeniden başlatır. Gerçek bir kesinti maliyeti vardır, ama bu kesinti aktarım değil, sabit süreli dondurma işlemidir ve sonuç uygulama tutarlıdır.

Her ikisi de aynı parça depolamaya yazar. Hücreler içeriğe göre adreslenir; bu yüzden hem saatlik sıcak hem de haftalık soğuk zamanlamayla yedeklenen bir depo, paylaşılan blokları iki kez değil bir kez saklar, ve bir fork ailesi de bunları paylaşır. Kullanım, `rdc backup usage` ile kotanıza göre ölçülür.

## Repoları Teker Teker Senkronize Etme

Push ve pull tek bir depo üzerinde çalışır; depo ref ile adreslenir (`name`, `name:tag` veya `name@machine`). "Tüm depolar aynı anda" biçimi yoktur: komutu her depo için bir kez çalıştırın.

### Başka Bir Makineye Gönder

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### Başka Bir Makineden Çek

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| Seçenek | Açıklama |
|--------|----------|
| `--to-machine <machine>` | Makineden makineye gönderme için hedef makine |
| `--from-machine <machine>` | Makineden makineye çekme için kaynak makine |
| `--force` | Mevcut bir yedeği veya depoyu geçersiz kıl |
| `--checkpoint` | Göndermeden önce CRIU checkpoint oluştur (yalnızca gönderme) |
| `--up` | Çektikten sonra depoyu bağla ve dağıt (yalnızca çekme) |
| `--bwlimit <limit>` | rsync transferi için bant genişliği sınırı (örn. `10M`) |
| `--delta-base <guid>` | Değişmez bir temel GUID'e göre yalnızca değişen blokları aktar |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlem sonrası yönlendirici sunucusunun yeniden başlatılmasını atla |

## Zamanlanmış Yedeklemeler

Rediacc, adlandırılmış yedekleme stratejileri kullanır. Her strateji bir zamanlama, yedekleme modu, isteğe bağlı bant genişliği sınırı ve dosya filtreleri tanımlar. Stratejiler, hangi yedeklemelerin çalıştırılacağını belirlemek için makinelere adıyla bağlanır.

### Yedekleme Modları

| Mod | Davranış | Kesinti Süresi |
|-----|----------|----------------|
| `hot` | Servisler çalışırken BTRFS anlık görüntüsü alınır (kilitlenme tutarlı) | Yok |
| `cold` | Servisler durdurulur, anlık görüntü alınır, servisler yeniden başlatılır, anlık görüntü yüklenir (uygulama tutarlı) | Depo başına durdur+başlat penceresi, depolar arasında paralelleştirilmiş. Aşağıdaki "Soğuk Yedekleme Kesinti Süresini Tahmin Etme" bölümüne bakın. |

Kilitlenme tutarlı anlık görüntülere izin veren servisler için `hot` kullanın. Garantili tutarlılığa ihtiyaç duyduğunuzda ve kısa yeniden başlatmayı kabul edebildiğinizde `cold` kullanın.

### Soğuk Yedekleme Semantiği

Soğuk yedekleme, dahil edilen her depo için üç aşamada çalışır: **durdur – anlık görüntü – başlat**. Garantilerin sınırlarını anlamak, operatörlerin kısmi arızaları erken tespit etmesine yardımcı olur.

**Soğuk yedeklemenin garantiledikleri:**

- Anlık görüntüden önce, dahil edilen her depodaki çalışan konteynerler Rediaccfile `down()` kancası aracılığıyla düzgün biçimde durdurulur ve depo başına Docker daemon sessiz hale getirilir. Anlık görüntü bu nedenle yalnızca kilitlenme tutarlı değil, uygulama tutarlıdır.
- Anlık görüntüden önce çalışan konteyner ID'lerinin kümesi `/var/run/rediacc/cold-backup-<guid>.running.json` adresinde bir sidecar dosyasına kaydedilir. Bu, "işimiz bittiğinde nelerin tekrar çalışıyor olması gerektiği" için gerçeğin kaynağıdır.
- Anlık görüntüden sonra, tam compose yığınını geri yüklemek için deponun Rediaccfile `up()` kancası çağrılır.
- `/var/run/rediacc/cold-backup-<guid>.status.json` adresindeki çalıştırma başına durum sidecar'ı her denemenin aşamasını, sonucunu ve hatalarını kaydeder.

**Soğuk yedeklemenin garanti ETMEDİKLERİ:**

- `up()` en iyi efors ile çalışır. Soğuk yedeklemenin kontrolü dışındaki nedenlerle başarısız olabilir (`depends_on: service_healthy` koşulunun hala beklenmesi, compose dosyası sözdizimi hatası, görüntü çekerken geçici bir ağ arızası). Başarısız olduğunda, soğuk yedekleme hatayı hata seviyesinde günlüğe kaydeder, durum sidecar'ını yazar ve bir sonraki depoya geçer.
- `up()` başarısız olduğunda, **doğrudan yedek yeniden başlatma** devreye girer: çalışma sidecar'ı okunur ve kaydedilen her konteyner ID'si doğrudan Docker API aracılığıyla yeniden başlatılır (compose olmadan). Bu, Rediaccfile kancalarını yeniden çalıştırmadan compose akışında bir sorun olsa bile servisleri geri getirir.
- Bazı konteyner ID'leri için yedek de başarısız olursa (örneğin, Docker daemon'un kendisi çalışmıyorsa), sidecar **yerinde bırakılır**, böylece yönlendirici watchdog her tıkta yeniden denemeye devam edebilir.

**Watchdog kurtarma:** her tıkta watchdog, çalışma sidecar'ının varlığını kontrol eder. Orada listelenen ve şu anda durdurulmuş olan herhangi bir konteyner ID'si, *konteynerin kaydedilmiş `restart_policy`'sinden bağımsız olarak* yeniden başlatılır. Bu, `restart: on-failure` ile yapılandırılmış servislerin (Docker'ın temiz bir durdurmanın ardından yeniden başlatmayacağı) soğuk yedeklemeden sonra geri dönmesi anlamına gelir. Listelenen tüm konteynerler çalışır duruma geldiğinde sidecar silinir.

**Operatörlerin arızaları nasıl tespit edeceği:**

- `rdc machine status <machine> --containers` çalışma durumunu gösterir. Beklenen kümeyle karşılaştırın.
- Makinedeki `/var/run/rediacc/cold-backup-<guid>.status.json` dosyasını kontrol edin. `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` ile inceleyebilirsiniz. Eski bir `startedAt` ile birlikte `success: false`, son yedeklemenin temiz tamamlanmadığı anlamına gelir.
- renet yedekleme çalıştırmasından gelen günlükler (`journalctl -u renet-*` veya doğrudan `rdc backup schedule` çağrısı) `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` biçiminde bir son özet satırı yayar. Boş olmayan `failed_repos` grep hedefidir.

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

**Her zamanlanmış tetiklemenin çalışmasını istiyorsanız**, zamanlayıcıyı `OnCalendar=<cron>` yerine `OnUnitInactiveSec=<aralık>` olarak değiştirin. Bu, sabit bir duvar saati zamanlaması yerine önceki çalıştırmanın tamamlanmasından N saat sonra tetiklenir, böylece uzun süren çalıştırmalar düşüşlere neden olmaz. Yalnızca bir sonraki çalıştırmayı ileriye iter. Takas zamanlama sapmasıdır: 03:00 gecelik "sonuncusunun bittiği saatten 24 saat sonra" olur.

### Anlık Görüntüler, Kesintiler ve Havuz Alanı

Her push anlık bir datastore anlık görüntüsü üzerinden çalışır; bu sayede depolar yazmaya devam ederken yüklenen veri tutarlı kalır. Yedekleme çalışırken bu anlık görüntü, canlı depolarla paylaştığı her bloğu referans almaya devam eder: döngü tamamlanıp anlık görüntü silinene kadar silmeler ve [trim'ler](/tr/docs/repositories#alan-kazanma-trim) daha az havuz alanı serbest bırakır. [Depolama sağlığı raporu](/tr/docs/monitoring#depolama-sagligi), yedekleme anlık görüntülerinin şu anda ne kadar alan kilitlediğini gösterir.

Kesintiler güvenlidir. Servisi durdurmak (veya makineyi yeniden başlatmak) yedeğin transferi iptal etmesine ve anlık görüntüyü çıkmadan önce silmesine neden olur; sonraki zamanlanmış çalıştırma kaldığı yerden devam eder; çünkü değişmeyen dosyalar sağlama toplamıyla atlanır. İşlem temizlik yapamayacak kadar sert biçimde sonlandırılırsa (güç kaybı), yetim kalan anlık görüntü depolama bakıcısı tarafından dakikalar içinde otomatik olarak tespit edilip kaldırılır.

### Strateji Tanımlama

Standart varsayılan, iki stratejili bir bölüştürmedir: her depoyu yakalayan hızlı bir saatlik sıcak akış ve uygulama tutarlı anlık görüntüler için konteynerleri durduran daha yavaş bir haftalık soğuk akış. İkisi de aynı parça depolamaya yazar; paylaşılan bloklar akış başına değil, bir kez saklanır.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Soğuk strateji üzerindeki `--exclude` filtresi, haftalık bakım pencerenize sığmayan çok büyük depolar için önerilen kaçış noktasıdır. Saatlik sıcak strateji onları yine de kapsar; soğuk yalnızca atlar. `--exclude` içindeki depo adları yerel yapılandırma depo adıyla eşleşir (`:tag` olmadan).

| Seçenek | Açıklama |
|---------|----------|
| `<strategy>` (konumsal) | Strateji adı (makineye bağlamak için kullanılır) |
| `--destination <storage>` | Yüklenecek depolama sağlayıcısı |
| `--cron <expression>` | Cron ifadesi (örn. `"0 2 * * *"` günlük saat 02:00 için) |
| `--mode <hot\|cold>` | Yedekleme modu |
| `--bwlimit <limit>` | Yüklemeler için bant genişliği sınırı (örn. `10M`) |
| `--include <pattern>` | Dahil etme filtresi (tekrarlanabilir) |
| `--exclude <pattern>` | Hariç tutma filtresi (tekrarlanabilir) |
| `--enable` / `--disable` | Stratejiyi etkinleştir veya devre dışı bırak |

### Stratejileri Görüntüleme

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Strateji Kaldırma

```bash
rdc backup strategy remove weekly-cold
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

> **Bağlama yalnızca yerel yapılandırmadır.** Bir strateji tanımlamak ve makineye bağlamak makineyi etkilemez. systemd zamanlayıcılarını dağıtmak için `rdc backup schedule -m <machine>` komutunu çalıştırın ([Zamanlamayı Makineye Dağıtma](#zamanlamayı-makineye-dağıtma) bölümüne bakın) ve her strateji veya bağlama değişikliğinden sonra tekrar çalıştırın.

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
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Soğuk strateji: büyük türetilmiş veri kümesi hariç her şeyi haftalık yedekle
rdc backup strategy set weekly-cold \
  --destination rediacc \
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

İki stratejiden hiçbirinin dışlamadığı bir depo her ikisi tarafından da yakalanır; böylece hem saatlik kilitlenme tutarlı anlık görüntülere hem de haftalık uygulama tutarlı bir anlık görüntüye sahip olur. `rdc backup manifests <repo>` bunları birlikte gösterir ve paylaştıkları bloklar bir kez saklanır.

## Yedekleme İşlemleri

### Zamanlamayı Makineye Dağıtma

Bağlı stratejileri bir makineye systemd zamanlayıcıları olarak gönderin:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Dağıtım bir durum uzlaştırıcıdır. Makinedeki mevcut birim dosyalarını ve systemd durumunu okur, yapılandırmanın üreteceği içerikle karşılaştırır (dosya başına SHA-256) ve yalnızca içeriği gerçekten değişen birimlere dokunur. Yapılandırma değişikliği olmadan yeniden çalıştırmak bir no-op'tur: yazma yok, `daemon-reload` yok, zamanlayıcı gürültüsü yok.

`--dry-run` her strateji için planı yazdırır (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) ve makineye dokunmaz. Oluşturulan birim gövdelerini de yazdırmak için `--debug` ile birlikte kullanın; rclone token'ları gizlenir.

Güncellemek veya kaldırmak üzere olduğunuz bir strateji için şu anda bir yedekleme çalışıyorsa, dağıtım hızlıca başarısız olur ve onu iptal etmeniz ya da `--force` geçirmeniz önerilir. `--force` ile, çalışan işlem belleğindeki birimini korur ve yeni yapılandırma bir sonraki zamanlayıcı tetiklemesinde geçerli olur; çalışan yedekleme asla sonlandırılmaz.

`--reset-failed` isteğe bağlıdır. Geçirildiğinde, başarılı bir dağıtımdan sonra dokunulan servislerde systemd'nin failed durumunu temizler. Varsayılan olarak kapalıdır, böylece önceki arıza sinyalleri uyarı sistemleri için görünür kalır.

### Şimdi Yedekleme Çalıştırma

Zamanlayıcıyı beklemeden hemen yedekleme başlatın. `systemd-run` kullanarak geçici yürütme ile zamanlayıcı dağıtılmamış olsa bile çalışır:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Yedekleme Durumunu Görüntüleme

Yedekleme zamanlayıcılarının mevcut durumunu ve son iş sonuçlarını gösterir:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Çalışan Yedeklemeyi İptal Etme

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Depo Migrasyonu

Bir depoyu bir makineden diğerine taşıyın:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Seçenek | Açıklama |
|---------|----------|
| `<ref>` (konumsal) | Taşınacak depo referansı; içindeki `@machine` kaynağı belirtir |
| `--to <place>` | Hedef makine veya küme |
| `--provision` | Aktarımdan önce hedefte depoyu hazırla |
| `--checkpoint` | Migrasyondan önce CRIU checkpoint oluştur |
| `--skip-dns` | Migrasyondan sonra DNS kaydı güncellemeyi atla |
| `--bwlimit <limit>` | Transfer için bant genişliği sınırı (örn. `50M`) |

Migrasyon, şifrelenmiş depo verilerini rsync aracılığıyla aktarır. Kaynak depo, siz açıkça kaldırana kadar bozulmadan kalır.

## Depolamayı Tarama

`rdc storage browse` ve `rdc storage import`, bu kullanımdan kaldırmanın istisnasıdır: gömülü bir kopya yerine PATH'teki kendi rclone'unuzu başlatırlar ve değişiklikten önce yazılmış bir arşivi okumanın yolu olarak kalırlar.

```bash
rdc storage browse my-storage
```

Tarama yalnızca okunabilir. Bir depolama arka ucuna gönderme, ondan çekme ve onu listeleme kullanımdan kaldırıldı; her biri reddedilir ve yerine geçen parça depolama komutunu belirtir.

## En İyi Uygulamalar

- Kritik veriler için uygulama tutarlı anlık görüntüler almak amacıyla günlük soğuk yedeklemeler zamanlayın
- Sıfır kesinti gerektiren yüksek frekanslı anlık görüntüler için sıcak yedeklemeleri kullanın
- Yedek bütünlüğünü doğrulamak için geri yüklemeleri periyodik olarak test edin
- Kritik veriler için birden fazla depolama sağlayıcısı kullanın (örn. S3 + B2)
- Kimlik bilgilerini güvende tutun; yedekler şifrelenmiştir ancak geri yükleme için LUKS kimlik bilgisi gereklidir
