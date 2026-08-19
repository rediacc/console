---
title: "Yedekleme ve Geri Yükleme"
description: "Şifreli depoların anlık görüntüsünü, yalnızca değişen hücrelerin yüklendiği ve her anlık görüntünün doğrudan geri yüklenebildiği içerik adresli chunk depolamaya alın. Ya da başka bir makinede bir kopya tutun. Her yere geri yükleyin, adlandırılmış stratejiler ve systemd zamanlayıcılarıyla otomatikleştirin."
category: "Guides"
tags:
  - backup
  - storage
order: 7
language: tr
sourceHash: "c35328105c2f3e8c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Yedekleme ve Geri Yükleme

Rediacc, şifreli depoları yedekler ve aynı makinede ya da başka bir makinede geri yükler. Yedeklerin şifreli olmasının nedeni, deponun kendisinin şifreli olmasıdır: makineden dışarı çıkan yalnızca şifreli metindir ve geri yüklemek için deponuzun LUKS kimlik bilgisi gerekir.

Yedeklemenin iki yolu vardır ve bunlar farklı sorulara cevap verir.

- **Chunk depolamaya anlık görüntü** (`rdc backup snapshot`) geriye gidebileceğiniz bir geçmiş tutar. Bu ana yoldur.
- **Başka bir makinede kopya** (`rdc repo push`, `rdc repo pull`), depoyu şu anki haliyle, kontrolünüzdeki donanımda tutar. Herhangi bir bulut hesabı devreye girmez.

Bu ikisi birbirinden bağımsızdır. Bir yolla yedeklenen bir depo, diğer yolla yedeklenmiş sayılmaz.

## Anlık görüntülerin çalışma şekli

Depo imajı, sabit bir ızgara üzerinde sabit boyutlu hücrelere kesilir. Her hücre ya bir boşluktur, yani oraya hiç yazılmamıştır, ya da o hücrenin şifreli metninin SHA-256'sı **olan** bir anahtarın altında saklanır.

Tüm özellikler bu tek karardan doğar.

**Yalnızca gerçek değişikliklerin bir bedeli vardır.** İlk anlık görüntü, yazılmış her hücreyi yükler. Ondan sonraki her çalıştırma, hangi extent'lerin dokunulduğunu dosya sistemine sorar, yalnızca onları okuyup hash'ler ve deponun henüz sahip olmadığı hücreleri yükler. Verisi neredeyse hiç değişmemiş bir depo neredeyse hiçbir şey yüklemez ve çalıştırma, imajın büyüklüğüyle orantılı bir süre yerine dakikalar sürer.

**Aynı veri yalnızca bir kez saklanır.** Anahtar içerik hash'i olduğundan, bir hücreyi paylaşan iki anlık görüntü aynı nesneyi paylaşır; bir depo ve onun [fork'ları](/tr/docs/tutorial-forking) için de aynısı geçerlidir: bir fork ailesi ebeveyni tekrarlamak yerine tek bir soy hattına karşı yedeklenir.

**Eski bir anlık görüntüyü geri yüklemek, yeni birini geri yüklemekten daha yavaş değildir.** Sırayla oynatılması gereken bir artımlı zincir yoktur. Geri yükleme, anlık görüntüyü tam bir hücre listesine çözer ve o hücreleri doğrudan getirir; bu yüzden geri yükleme süresi, yedekleri ne zamandır aldığınıza değil, imajın boyutuna ve bant genişliğinize bağlıdır. Boşluklar boşluk olarak kalır, bu yüzden seyrek bir imaj seyrek olarak geri yüklenir; imaj içinde birden çok yerde görünen bir hücre de yalnızca bir kez indirilir.

**Her anlık görüntü kendi başına yeterlidir.** Kaybetmemeniz gereken bir "tam yedek" ya da bozuk bir artımın sonrakilerin tümünü geçersiz kıldığı bir pencere yoktur. Listedeki herhangi bir anlık görüntü doğrudan geri yüklenebilir.

**Doğrulama güvene değil, yeniden hash'lemeye dayanır.** Anahtar içeriğin hash'i olduğundan, bir yedeği kontrol etmek hücreleri getirip hash'lemek demektir. `rdc backup verify` örnekleme yapar; `rdc backup verify --deep` kayıtlı her hücreyi yeniden hash'ler.

**Kesintiye uğrayan bir çalıştırma boşa gitmez.** Yükleme, zaten ulaşmış hücreleri yeniden göndermeden devam eder; yarım kalmış bir geri yüklemeyi yeniden başlatmak, diskte zaten olanı yeniden hash'leyip yeniden kullanır, tekrar indirmez.

### Size neye mal olur

Kota, **fiziksel olarak benzersiz depolanan bayt sayısı** üzerinden hesaplanır: bu, tekilleştirme sonrasında gerçekte tutulan miktardır, anlık görüntülerinizin mantıksal olarak temsil ettiği toplam değil. Yavaş değişen bir deponun otuz anlık görüntüsü, bir taneye yakın bir maliyete mal olur.
`rdc backup usage`, depolanan baytları kotanıza karşı gösterir; bu, Community planında 10 GB'tan başlayan, abonelik başına bir sayıdır.

### Anlık görüntülerin ihtiyaç duyduğu şey

Anlık görüntü yükleme, hesap sunucusundan geçer; hesap sunucusu her çalıştırmayı deponun yüklü lisansına göre yetkilendirir ve makineye yazmak için kısa ömürlü bir izin verir. Bu yüzden bu yol, makinenin erişebildiği bir hesap sunucusuna ve lisanslı bir depoya ihtiyaç duyar. Bunlar olmadan, anlık görüntü sessizce atlanmaz, reddedilir; `rdc backup manifests`, `rdc backup usage` ve `rdc backup retention`'ın okuyacak hiçbir şeyi kalmaz.

Bu, `--dry-run` için de geçerlidir. Çalıştırma planlama mı yoksa yükleme mi yaptığına karar vermeden önce lisans okunur; bu yüzden bir dry run, komutu kimlik bilgisi olmadan denemenin bir yolu değil, gerçek işin bir önizlemesidir.

Makineler arası push ve pull, ikisine de ihtiyaç duymaz. Zaten yapılandırmanızda bulunan iki makine arasındaki doğrudan bir aktarımdır.

### Bir anlık görüntünün vaat etmediği şeyler

- **Bir anlık görüntü tek bir depoyu kapsar, makinenin tamamını bir kerede kapsamaz.** Her depo kendi anında yakalanır. İki depo birbirine bağımlıysa, anlık görüntüleri birbiriyle eşgüdümlü bir çift değildir.
- **Sürekli çoğaltma değildir.** Bir anlık görüntü, aldığınız bir andır ve son anlık görüntüden bu yana yazılmış her şeyi kaybedebilirsiniz. Bunun ne kadar olduğu, ne sıklıkla çalıştırdığınıza bağlıdır.
- **Depolanan nesneler bir kez yazılır, sertifikalı WORM değildir.** Hücreler yalnızca oluşturmaya izin veren koşullu bir şekilde yazılır, bir makinenin aldığı izin hiçbir şeyi silemez ve silmeler saklama politikasına göre sunucu tarafında gerçekleşir. Bu, ele geçirilmiş bir makinenin kendi yedeklerini yok etmesine karşı gerçek bir engeldir. Bir uyumluluk sertifikası değildir ve öyle denetlenmez.

### rclone depolama yolu ortadan kalktı

`rdc repo push --to <storage>` ve ilgili komutları, eskiden kendi kaydettiğiniz bir bulut sağlayıcısına tüm yedek dosyasını kopyalardı. Artık bir depolama hedefini reddediyor ve yerine geçeni adlandırıyorlar. Makineler arası aktarım hiçbir zaman rclone'dan geçmedi ve bundan etkilenmez. O yöntemle yazılmış bir arşivi hâlâ okumanız gerekiyorsa, [Kaldırılmadan Önce Yazılmış Bir Arşivi Okuma](#reading-an-archive-written-before-the-retirement) bölümüne bakın.

### Chunk depolama komutları

```bash
# Bir anlık görüntü yükle. İlk çalıştırma tohumlar, sonrakiler yalnızca değişen hücreleri gönderir.
rdc backup snapshot my-app

# Yüklemeden planla: nelerin taşınacağını bildirir.
rdc backup snapshot my-app --dry-run

# Konteynerleri durdur, dondur, yeniden başlat, sonra yükle.
rdc backup snapshot my-app --cold

# Yerel çıpaya güvenme ve tüm envanteri yeniden yükle.
# Bu her şeyi yeniden yükler ve kotayı yeniden tüketir; yalnızca
# çıpanın bozuk olduğu bilindiğinde kullanın.
rdc backup snapshot my-app --reseed

# Depolanan envanteri ve kotanızı kontrol edin.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Seçenek | Açıklama |
|--------|-------------|
| `<repo-ref>` (konumsal) | Anlık görüntüsü alınacak depo |
| `--dry-run` | Yalnızca planlama: yükleme yok. Nelerin taşınacağını bildirir |
| `--cold` | Konteynerleri durdur, dondur, yeniden başlat, sonra yükle. `--dry-run` ile birlikte kullanılamaz |
| `--reseed` | Yerel çıpaya güvenme ve tüm envanteri yükle. Her şeyi yeniden yükler ve kotayı yeniden tüketir |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |

## Soğuk Anlık Görüntüler (`--cold`)

Soğuk bir anlık görüntü, dondurmadan önce depoyu durdurur; böylece saklanan imaj çökme tutarlılığı yerine uygulama tutarlılığına sahip olur. Makinenin kendisinde doğrudan çalışır:

```bash
# Varsayılan veri deposundaki her depo.
sudo renet backup snapshot --cold

# Yalnızca adlandırdığınız depolar. --repo bir depo GUID'i alır ve tekrarlanabilir.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold`, `--dry-run` ile birlikte kullanılamaz. Konteynerleri durduran bir dry run kuru değildir, durdurmayan bir çalıştırma da soğuk değildir; bu yüzden renet, sizin adınıza bir anlam seçmek yerine bu kombinasyonu reddeder.

### Soğuk bir çalıştırmanın yaptığı

Seçilen her depo için, şu sırayla:

1. Konteynerlerini durdurur.
2. Depo bağlama noktasını ve veri deposunu diske yazar.
3. Konteynerlerin gerçekten durduğunu doğrular.
4. Depo imajının copy-on-write reflink'ini alır.
5. Konteynerleri yeniden başlatır.

Yükleme yalnızca bundan sonra başlar; o noktada tüm depolar zaten tekrar ayakta olur.

Kesinti, aktarım değil dondurmadır. Reflink yalnızca meta veridir, bu yüzden depo 1 GB da olsa 100 GB da olsa geçen süre değişmez. Yükleme öyle değildir: değişen bayt sayısıyla büyür ve ilk anlık görüntü sıfır olmayan envanterin tamamını yükler. Konteynerleri yükleme bitene kadar kapalı tutmak, kesintiyi veri miktarına bağlardı; bu da ilk tohumlamada milisaniyeler yerine saatler anlamına gelirdi.

Seçilen depolar tek tek değil, tek bir pencere içinde birlikte durdurulur. Bu, depo başına biraz daha uzun bir kesintiye mal olur, karşılığında tüm küme için tek bir tutarlılık noktası kazandırır.

Hiç konteyneri çalışmayan bir depo zaten sessizdir. Hiçbir kesinti olmadan anlık görüntüsü alınır ve bu bir başarısızlık değil, normal bir sonuçtur.

### Kesintinin bedeli

Gerçek bir makinede ölçüldüğünde, toplam kesinti **222 ms** oldu:

| Aşama | Ölçülen | Ne olur |
|-------|----------|--------------|
| `cold_down` | 64 ms | Konteynerler durur |
| `cold_sync` | 26 ms | Depo bağlama noktaları ve veri deposu diske yazılır |
| `cold_verify` | 31 ms | Konteynerlerin durduğu doğrulanır |
| `cold_stage` | 0 ms | Depo imajının reflink'i |
| `cold_up` | 99 ms | Konteynerler yeniden başlar |

Büyük kısmı konteynerlerin yeniden başlaması oluşturur ve staging fiilen bedavadır: reflink milisaniye çözünürlüğünde kaydedilmez. Yine de bu sıfırı tek başına değil, depo başına kayıtlarla birlikte okuyun. Her depoyu reddeden bir çalıştırma da `cold_stage=0ms` bildirir; hangisine baktığınızı yalnızca kayıtlar söyler.

Bu döküm bir süs değil, kanıttır. Bu beş aşamadan hiçbiri depo verisini okumaz ya da göndermez, bu yüzden hiçbiri yedek büyüdükçe büyümez. Büyüyen tek kısım yüklemedir ve o, kesinti zaten bittikten sonra çalışır.

renet, çalıştırma bittiğinde aynı rakamları yazdırır; böylece bizim ölçümlerimize güvenmek yerine kendi makinelerinizi ölçebilirsiniz.

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Her deponun JSON kaydı aynı kesinti ve aşamaları taşır; böylece sonraki bir okuyucu, zamana bakarak tahmin etmeden soğuk bir anlık görüntüyü sıcaktan ayırt edebilir.

### Soğuk ne zaman seçilmeli

Varsayılan sıcaktır ve çoğu depo için doğru seçim budur. Sıcak bir anlık görüntü çökme tutarlıdır; bu, bir elektrik kesintisinden sonra bir deponun bulunacağı durumla aynıdır ve hiç kesinti süresi gerektirmez. Çoğu veritabanı ve kuyruk bu durumdan kendi kendine kurtulur.

Soğuk, yazılırken güvenle yakalanamayan veriler için seçilir. Kendi ileri yazma günlüğüne ve bellek içi duruma sahip bir veritabanı bunun en belirgin örneğidir. Kısa, ölçülmüş bir kesinti karşılığında, uygulamanın kurtarma yapmadan açabileceği bir anlık görüntü elde edersiniz.

### Soğuk bir çalıştırmanın reddettiği şeyler

Reddetmek, bu özelliğin ta kendisidir. Hiçbir şeyi durgunlaştırmamış ama soğuk diye adlandırılan bir yedek, ancak geri yükleme anında ortaya çıkacak bir yalandır; bu yüzden renet, soğuk bir çalıştırmayı asla sessizce sıcağa düşürmez:

- **Durmayan konteynerler.** Durdurmadan sonra renet, deponun kendi Docker soketine hâlâ çalışan bir şey olup olmadığını sorar. Varsa, o depo anlık görüntüsü alınmadan reddedilir. Bu kontrol güvenli tarafa doğru başarısız olur: soket erişilemezse veya konteyner listesi okunamazsa, durgunlaşma doğrulanmamış sayılır ve doğrulanmamış olan reddedilir.
- **Okunamayan bir lisans.** Lisanslar kesintiden sonra değil önce kontrol edilir, çünkü lisansı okunamayan bir depo zaten hiçbir şey yükleyemezdi. Böyle bir depo durdurulmadan atlanır. Seçilen depolardan hiçbirinde okunabilir bir lisans yoksa, tek bir konteyner bile inmeden önce tüm çalıştırma reddedilir.
- **Aynı veri deposunda ikinci bir soğuk çalıştırma.** Kilit tüm veri deposunu kapsar ve meşgul bir kilit, hiçbir şeyi durdurmadan hemen reddedilir. Çakışan iki çalıştırma, her biri kendisine ait sandığı konteynerleri durdururdu ve ikincisi, birincisinin hâlâ dondurmakta olduğu depoları yeniden başlatırdı. Çalıştırmayı atlayıp bir sonrakini beklemek bundan daha iyidir.

Konteynerler kapalıyken bir çalıştırma `systemctl stop` veya yeniden başlatmayla kesintiye uğrarsa, renet çıkmadan önce onları yeniden başlatır. Makine tarafındaki kurtarma son güvencedir: sahibi kaybolmuş bir soğuk yedeği tespit eder ve o depoları yeniden ayağa kaldırır.

## Bir Yedeği Başka Bir Makineye Gönderme

Bir depoyu SSH üzerinden ikinci bir makineye kopyalayın:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>`, hedefi yapılandırmanızdan çözer; `--to-machine <machine>` aynı şeyi açıkça belirtir. Bir depolama adı reddedilir: o yol kaldırılmıştır.

Şifreli imaj **AYNI GUID** ile kopyalanır; bu yüzden bu bir fork değil, bir yedekleme veya taşımadır. Bağımsız bir kopya elde etmek için önce `rdc repo fork` yapın, sonra fork'u gönderin.

İlk gönderim imajın tamamını taşır. Ondan sonraki her gönderim, her iki makinede de tutulan değişmez bir temel imaja göre yalnızca değişen blokları, hiçbir bayrak ayarlamadan gönderir. `--delta-base <guid>`, gerekirse o temeli sizin adlandırmanızı sağlar.

Gönderilen kopya, hedefte çalışan bir depo olarak değil, bir yedek yapı öğesi olarak yer alır. `rdc backup restore` ile bunu bir depoya dönüştürün:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Belirli bir zaman noktasındaki yedek için, bunun yerine chunk depolamayı kullanın: `rdc backup snapshot my-app` yalnızca değişen hücreleri yükler ve `rdc backup restore my-app --at <snapshot>` bunlardan herhangi birini geri getirir.

| Seçenek | Açıklama |
|--------|-------------|
| `<ref>` (konumsal) | Gönderilecek deponun referansı |
| `--to <remote>` | Hedef makine veya küme |
| `--to-machine <machine>` | Hedef makine, açıkça belirtilmiş |
| `--provision <provider>` | Hedef makine yoksa, bu bulut sağlayıcısı üzerinden sağlayın |
| `--checkpoint` | Göndermeden önce bir CRIU kontrol noktası oluştur (`rediacc.checkpoint=true` etiketli konteynerler için). Hedef, `repo up` sırasında otomatik olarak geri yüklenir |
| `--force` | Mevcut bir yedeğin üzerine yaz |
| `--bwlimit <limit>` | rsync aktarımı için bant genişliği sınırı (örn. `10M`, `500K`) |
| `--delta-base <guid>` | Yalnızca bu değişmez temel GUID'e göre değişen blokları aktar. Otomatik temel için atlayın |
| `--strategy <strategy>` | Bir delta temeli kullanırken blok delta stratejisi: `auto`, `physical` veya `shared` |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlemden sonra rota sunucusunun yeniden başlatılmasını atla |

## Başka Bir Makineden Yedek Çekme

Bir depoyu tutan makineden geri getirin:

```bash
rdc repo pull my-app --from server-1
```

Aynı komutta bağlamak ve dağıtmak için `--up` ekleyin. Bunun yerine chunk depolamadan geri yüklemek için `rdc backup restore my-app --at <snapshot-id>` kullanın.

Pull, şu anda **bağlı** olan bir deponun üzerine yazmayı reddeder. Önce bağlantısını kaldırın, pull'u çalıştırın, sonra `rdc repo up` ile tekrar ayağa kaldırın. Dizin tabanlı depolar bir istisnadır: bağlıyken yerinde eşitlenirler.

| Seçenek | Açıklama |
|--------|-------------|
| `<ref>` (konumsal) | Çekilecek deponun referansı |
| `--from <remote>` | Kaynak makine veya küme |
| `--from-machine <machine>` | Kaynak makine, açıkça belirtilmiş |
| `--force` | Mevcut yerel yedeğin üzerine yaz |
| `--up` | Çekmeden sonra depoyu bağla ve dağıt |
| `--bwlimit <limit>` | rsync aktarımı için bant genişliği sınırı (örn. `10M`, `500K`) |
| `--delta-base <guid>` | Yalnızca bu değişmez temel GUID'e göre değişen blokları al |
| `--strategy <strategy>` | Bir delta temeli kullanırken blok delta stratejisi: `auto`, `physical` veya `shared` |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |
| `--skip-router-restart` | İşlemden sonra rota sunucusunun yeniden başlatılmasını atla |

## Yedekleri Listeleme

Chunk depolamadaki anlık görüntüleri listeleyin:

```bash
rdc backup manifests my-app
```

Her satır, saklanan bir zaman noktasıdır:

| Sütun | Anlamı |
|---|---|
| `Repo` | Yerel yapılandırmanızdan çözülen depo adı (yapılandırmada olmayan depolar için GUID'e döner) |
| `Snapshot` | Anlık görüntü kimliği. `rdc backup restore --at`'in aldığı değer budur |
| `Created` | Anlık görüntünün alındığı UTC zamanı |
| `Total` | Bu anlık görüntünün temsil ettiği depo imajının boyutu |
| `Added` | Bu anlık görüntünün öncekilerin üzerine fiilen yüklediği bayt sayısı |
| `Chunks` | Kaç hücre eklediği |

Bir `rdc repo push --to <machine>`'in hedefte ne bıraktığını görmek için, o makineye ne tuttuğunu sorun:

```bash
rdc repo list --machine server-1
```

Gönderilen kopya kendi adıyla görünür. Yanında ham bir GUID taşıyan ikinci bir satır, tutulan delta temelidir; bu, o makineye yapılacak bir sonraki gönderimi tam bir aktarım yerine artımlı hale getiren şeydir.

`rdc backup list --machine <machine>`, zamanlanmış çalıştırmaların yazdığı `hot/` ve `cold/` klasörlerini okur; bu yüzden bir push'un bıraktığı bir kopya için yanlış araçtır ve size hiçbir şey göstermez.

| Sütun | Anlamı |
|---|---|
| `Mode` | `hot` veya `cold`. Bu girdinin ait olduğu zamanlanmış yedek klasörü |
| `Name` | Yerel yapılandırmanızdan çözülen depo adı (yapılandırmada olmayan depolar için GUID'e döner) |
| `GUID` | Diskteki depo GUID'i |
| `Size` | Yedek dosyasının insan tarafından okunabilir boyutu |
| `Modified` | Makinedeki dosyanın UTC zaman damgası |

Bir depolama arka ucunu listelemek, rclone koluyla birlikte kaldırılmıştır; komut reddedilir ve yerine geçen şu ikisini adlandırır.

## Saklama

Sunucu, chunk deposunun tamamı üzerinde depo başına bir saklama politikası uygular; bu yüzden eski anlık görüntüler, siz elle hiçbir şey silmeden budanır. Hiçbir politika bildirilmemişse, her anlık görüntü saklanır.

```bash
# Şu anda uygulanan politika.
rdc backup retention my-app

# Kayan bir pencere tutun: 7 günlük, 4 haftalık, 6 aylık.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Her şeyi tutan duruma geri dönün.
rdc backup retention clear my-app
```

| Seçenek | Açıklama |
|--------|-------------|
| `--keep-last <n>` | En son bu kadar anlık görüntüyü tut |
| `--keep-hourly <n>` | Bu kadar saatin her birinden en yeni anlık görüntüyü tut |
| `--keep-daily <n>` | Bu kadar günün her birinden en yeni anlık görüntüyü tut |
| `--keep-weekly <n>` | Bu kadar haftanın her birinden en yeni anlık görüntüyü tut |
| `--keep-monthly <n>` | Bu kadar ayın her birinden en yeni anlık görüntüyü tut |
| `--keep-yearly <n>` | Bu kadar yılın her birinden en yeni anlık görüntüyü tut |

En az bir kural verin. Kuralsız `set`, "hiçbir şeyi tutma" olarak değil, reddedilerek işlenir; çünkü bir politikayı temizlemek `clear`'ın işidir.

## Geri Yükleme

`rdc backup restore`, bir yedeği canlı bir depoya dönüştürür ve her iki yol için de aynı fiili kullanır. Değişen şey, neyi hedeflediğinizdir.

```bash
# Chunk depolamadan belirli bir zaman noktası.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Bir push'un bir makinede bıraktığı bir yapı öğesi.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at`, `rdc backup manifests`'ten bir anlık görüntü kimliği ya da `2026-08-14T12:00:00Z` gibi bir RFC 3339 zamanı alır; bu, o anda veya öncesinde alınmış en yeni anlık görüntüye çözülür. O andan önce hiçbir anlık görüntü olmayan bir zaman, yuvarlanmak yerine reddedilir.

`--as` ile yeni bir ad altında geri yükleme hiçbir şeyin üzerine yazmaz; bu yüzden bir geri yükleme provası, canlı bir makinede güvenle çalıştırılabilir. Zaten var olan bir ada geri yükleme reddedilir.

| Seçenek | Açıklama |
|--------|-------------|
| `<artifact-ref>` (konumsal) | Geri yüklenecek şey. Bir chunk deposu anlık görüntüsü için `repo`, bir makinedeki yapı öğesi için `repo@place` |
| `--as <name>` | Geri yüklenen depo için ad (varsayılan yapı öğesinin adıdır) |
| `-m, --machine <machine>` | Geri yüklenecek makine |
| `--datastore <name>` | Bu adlandırılmış veri deposuna geri yükle; bağlı makinesi onu barındırır |
| `--at <time>` | Belirli bir zaman noktasını geri yükle: bir anlık görüntü kimliği veya RFC 3339 zamanı |
| `--up` | Aktarımdan sonra geri yüklenen depoyu dağıt |
| `--health-window <seconds>` | Dağıtılan deponun sağlığının izleneceği süre |
| `--health-timeout <seconds>` | Sağlıklı hale gelmesi için beklenecek süre |
| `-y, --yes` | Onayı atla |
| `--debug` | Ayrıntılı çıktıyı etkinleştir |

Bir depoyu geri yüklemek, yapılandırmanızda bulunan LUKS kimlik bilgisini gerektirir. Config storage'ı etkinleştirdiyseniz, bu kimlik bilgisi yeni bir makinede yapılandırmanızla birlikte geri gelir. Etkinleştirmediyseniz, yapılandırmanızın bir kopyasını, makinenin arızalanmasının birlikte götürmeyeceği bir yerde tutun.

### Geri yüklemeyi her makinede kanıtlayın

Hiç uçtan uca sınanmamış bir makine, yüklemeleri ne kadar sorunsuz görünürse görünsün, yedeklenmiş sayılmaz. Yükleme ve geri yükleme farklı nedenlerle başarısız olur ve ikinci tür yalnızca gerçekten denediğinizde ortaya çıkar.

Yedeklere güvenmeden önce, her makinede bunu bir kez yapın:

1. Bir anlık görüntü alın: `rdc backup snapshot my-app`.
2. Kaydedildiğini doğrulayın: `rdc backup manifests my-app`.
3. Onu geçici bir ad altında geri yükleyin: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Geri yüklenen depoyu kaynakla karşılaştırın, sonra `rdc repo delete my-app-drill --yes` ile prova kopyasını silin.

Bu dizideki hiçbir şey canlı depoya dokunmaz; bu yüzden trafik sunmakta olan bir makinede bile güvenlidir. Daha eski bir yedekleme düzeninden geçiş yapıyorsanız, bu makinede bu adımlar en az bir kez başarıyla geçene kadar eski düzeni de çalışır durumda tutun. İki yedekleme yolu depolama alanına mal olur; kanıtlanmamış tek bir yol ise verinin kendisine mal olur.

## Depoları Tek Tek Eşitleme

Push ve pull, ref (`name`, `name:tag` veya `name@machine`) ile adreslenen tek bir depo üzerinde çalışır. "Tüm depoları bir kerede" biçimi yoktur: komutu her depo için bir kez çalıştırın.

Bir fork ve bir makine belirten bir ref, sade bir adla aynı şekilde çalışır:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Tam seçenek listeleri [Bir Yedeği Başka Bir Makineye Gönderme](#push-a-backup-to-another-machine) ve [Başka Bir Makineden Yedek Çekme](#pull-a-backup-from-another-machine) bölümlerindedir.

## Zamanlanmış Yedeklemeler

Rediacc, adlandırılmış yedekleme stratejileri kullanır. Her strateji bir zamanlama, yedekleme modu, isteğe bağlı bant genişliği sınırı ve dosya filtreleri tanımlar. Hangi yedeklerin nerede çalışacağını kontrol etmek için strateji adlarını makinelere bağlarsınız.

### Yedekleme Modları

| Mod | Davranış | Kesinti |
|------|----------|--------|
| `hot` | Servisler çalışmaya devam ederken depo imajı dondurulur (çökme tutarlı) | Yok |
| `cold` | Servisler durdurulur, anlık görüntü alınır, servisler yeniden başlatılır, anlık görüntü yüklenir (uygulama tutarlı) | Depo başına durdurma+başlatma penceresi, depolar arasında paralelleştirilmiş. Aşağıdaki "Soğuk Yedekleme Kesintisini Tahmin Etme" bölümüne bakın. |

Çökme tutarlı anlık görüntülere tolerans gösteren servisler için `hot` kullanın. Garantili tutarlılığa ihtiyaç duyduğunuzda ve kısa bir yeniden başlatmayı kabul edebiliyorsanız `cold` kullanın.

### Soğuk Yedekleme Semantiği

Soğuk bir yedekleme, dahil edilen her depo için üç aşamada çalışır: **durdur → anlık görüntü al → başlat**. Garantilerin nerede bittiğini bilmek, kısmi başarısızlıkları erken yakalamanızı sağlar.

**Soğuk yedeklemenin garanti ettiği:**

- Anlık görüntüden önce, dahil edilen her depodaki çalışan her konteyner, Rediaccfile'ının `down()` kancası aracılığıyla düzgünce durdurulur ve depo başına Docker daemon'u durgunlaştırılır. Bu yüzden anlık görüntü yalnızca çökme tutarlı değil, uygulama tutarlıdır.
- Anlık görüntü öncesinde çalışmakta olan konteyner ID'leri kümesi, `/var/run/rediacc/cold-backup-<guid>.running.json` konumundaki bir sidecar'a kaydedilir. Bu, "işimiz bittiğinde tekrar ayakta olması gereken şeyin" kaynağıdır.
- Anlık görüntüden sonra, tam compose yığınını geri yüklemek için deponun Rediaccfile `up()` kancası çağrılır.
- Çalıştırma başına bir durum sidecar'ı olan `/var/run/rediacc/cold-backup-<guid>.status.json`, her denemenin aşamasını, sonucunu ve hatasını kaydeder.

**Soğuk yedeklemenin GARANTİ ETMEDİĞİ:**

- `up()` en iyi çaba temellidir. Soğuk yedeklemenin kontrolü dışındaki nedenlerle başarısız olabilir (hâlâ bekleyen bir `depends_on: service_healthy` koşulu, bir compose dosyası sözdizimi hatası, bir imaj çekerken geçici bir ağ hatası). Başarısız olduğunda, soğuk yedekleme hatayı error seviyesinde günlüğe kaydeder, durum sidecar'ını yazar ve bir sonraki depoya geçer.
- `up()` başarısız olduğunda, bir **yedek doğrudan yeniden başlatma** devreye girer: çalışan sidecar okunur ve kaydedilen her konteyner ID'si, compose kullanılmadan doğrudan Docker API üzerinden yeniden başlatılır. Bu, compose akışında bir sorun olsa bile servisleri geri getirir, ancak herhangi bir Rediaccfile kancasını yeniden çalıştırmadan.
- Bazı konteyner ID'leri için yedek bile başarısız olursa (örneğin, Docker daemon'unun kendisi çökmüşse), sidecar **olduğu yerde bırakılır**, böylece router watchdog'u her tikte yeniden deneyebilir.

**Watchdog kurtarma:** Her tikte, watchdog çalışan bir sidecar olup olmadığını kontrol eder. Orada listelenen ve şu anda durmuş olan herhangi bir konteyner ID'si, konteynerin kaydedilmiş `restart_policy`'sinden *bağımsız olarak* yeniden başlatılır. Bu, `restart: on-failure` ile ayarlanmış servislerin bile (Docker'ın temiz bir durdurmadan sonra yeniden başlatmayacağı bir politika) soğuk yedeklemeden sonra geri gelmesini sağlar. Listelenen her konteyner çalışır duruma geldiğinde, sidecar silinir.

**Operatörün başarısızlıkları tespit etme yöntemi:**

- `rdc machine status <machine> --containers`, çalışma durumunu gösterir. Beklenen kümeyle karşılaştırın.
- Makinedeki `/var/run/rediacc/cold-backup-<guid>.status.json`. `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` ile inceleyin. Eski bir `startedAt` ile birlikte `success: false`, son yedeklemenin temiz bitmediği anlamına gelir.
- renet yedekleme çalıştırmasının günlükleri (`journalctl -u renet-*` veya doğrudan `rdc backup schedule` çağrısı), `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` biçiminde bir son özet satırı yayar. Boş olmayan bir `failed_repos`, grep hedefinizdir.

### Soğuk Yedekleme Kesintisini Tahmin Etme

Her depo, yalnızca kendi `down()` + `up()` penceresi boyunca kapalı kalır. Isınmış bir sunucuda bunlar tipik olarak:

| Depo profili | Tipik durdurma+başlatma |
|------------|--------------------|
| Küçük (1-2 konteyner, DB yok) | 5-15 sn |
| Orta (web uygulaması + önbellek) | 20-45 sn |
| Ağır (DB + kuyruklar + posta) | 60-120 sn |

Dondurma adımı, depo imajının copy-on-write reflink'idir. Yalnızca meta veridir, bu yüzden depo 1 GB da olsa 100 GB da olsa geçen süre aynıdır ve ölçülen bir çalıştırmada milisaniye çözünürlüğünde kaydedilmemiştir. Bir depo, diğer depoların dondurulması yüzünden kapalı kalmaz. Yükleme daha sonra dondurulmuş kopyaya karşı çalışır; bu sırada her depo zaten tekrar ayaktadır.

**Tüm çalıştırma için toplam duvar saati süresi**, kaç deponun eş zamanlı olarak yeniden başladığına bağlıdır. renet bu değeri sunucudan türetir:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Örnekler:

| Sunucu | Depolar | Eşzamanlılık | Duvar saati yeniden başlatma |
|------|-------|-------------|--------------------|
| 4 CPU'lu VM | 5 depo, ortalama 30 sn | 2 | ~75 sn |
| 16 CPU'lu sunucu | 10 depo, ortalama 40 sn | 8 | ~80 sn |
| 64 CPU'lu filo düğümü | 50 depo, ortalama 40 sn | 8 | ~4 dk |

**Ortam değişkeniyle geçersiz kılma:** Belirli bir değeri sabitlemek için yedekleme servisinin ortamında `REDIACC_COLD_BACKUP_CONCURRENCY=N` ayarlayın (genellikle bir systemd drop-in ile). `=1`, kesinlikle sıralı yeniden başlatmaları zorunlu kılar; bir deponun `up()` kancasındaki bir çökme döngüsünü hata ayıklarken kullanışlıdır.

Gecikmeye duyarlı bir depo çalıştırıyorsanız (herkese açık web uygulaması, posta), kesintisi tüm çalıştırma süresiyle değil, kendi durdurma+başlatmasıyla (tipik olarak 30-90 sn) sınırlıdır. Depolar, keşfedildikleri sırayla eşzamanlılık yuvalarına yerleştirilir; öncelik kuyruğu yoktur. Daha ince taneli bir zamanlama gerekiyorsa, ağır depolarınıza `--include` ile kapsamlandırılmış kendi stratejilerini verin.

### Uzun Süren Yedeklemeler ve Çakışan Zamanlamalar

Kendi zamanlama aralığından daha uzun süren bir soğuk yedekleme (örneğin, 500 GB'lık bir deponun ilk tohumlaması, mütevazı bir bağlantıda meşru olarak 24 saatten fazla sürebilir ve bu sırada gece zamanlayıcısı yeniden tetiklenir), ikinci bir çalıştırmayı kuyruğa almaz veya başlatmaz. systemd'nin `Type=oneshot` birimi tek bir örnektir: zamanlayıcı tetiklendiğinde ve servis zaten `activating` durumundaysa, systemd başlatmayı mevcut işle birleştirir. Yeni bir işlem başlamaz, hiçbir çalıştırma daha sonrası için kuyruğa alınmaz.

Somut olarak, Pazartesi 03:00 UTC'de başlayıp Perşembe öğle vakti biten bir çalıştırma:

| Gün | 03:00 UTC tetiklenmesi | Sonuç |
|------|---------------|------|
| Pazartesi | İlk tetiklenme | Çalıştırma başlar |
| Salı | İkinci tetiklenme | Sessizce atlanır (önceki çalıştırma hâlâ etkin) |
| Çarşamba | Üçüncü tetiklenme | Sessizce atlanır (önceki çalıştırma hâlâ etkin) |
| Perşembe | Çalıştırma öğlen sona erer | Yakalama yok; bir sonraki çalıştırma Cuma 03:00 UTC |

Zamanlayıcının `Persistent=true` yönergesi bu tetiklenmeleri **kurtarmaz**. `Persistent=true`, zamanlayıcının kendisi etkin olmadığı için (sistem kapalı, zamanlayıcı devre dışı) kaçırılan tetiklenmeleri yeniden oynatır. Servis meşgul olduğu için atlanan tetiklenmeler kaybolur gider.

Bu varsayılan, kasıtlıdır. Aynı veri deposuna karşı iki soğuk yedeklemeyi paralel çalıştırmak, dondurma yolunda, yüklemede ve `/var/run/rediacc/cold-backup-<guid>.status.json`'daki depo başına sidecar'larda çakışmaya neden olur. Çalışmakta olan bir örneğin arkasında beklemek, aynı veriye iki yönden saldırmaktan daha iyidir. Veri deposu kilidi bunu zorunlu kılar: ikinci bir soğuk çalıştırma, kilidin meşgul olduğunu bulur ve hiçbir şeyi durdurmadan hemen reddedilir.

**İzleme açısından etkisi.** Askıda kalmış bir yedekleme (örneğin, bir ağ kara deliğinde takılıp kalan bir yükleme), sonraki tüm zamanlayıcı tetiklenmelerini sessizce atlar. Zamanlayıcı hiçbir alarm vermez. `systemctl show <unit> -p ActiveEnterTimestamp`'i izleyin: servis, beklenen çalıştırma süresinden daha uzun süredir `activating` durumundaysa (örneğin, gece zamanlayıcısında 48 saatten fazla), araştırın.

**Her zamanlanmış tetiklenmenin çalışması gerekiyorsa**, zamanlayıcıyı `OnCalendar=<cron>`'dan `OnUnitInactiveSec=<aralık>`'a geçirin. Bu, sabit bir duvar saati zamanlaması yerine önceki çalıştırma bittikten N saat sonra tetiklenir; bu yüzden uzun çalıştırmalar atlamalara neden olmaz. Yalnızca bir sonraki çalıştırmayı daha ileri iterler. Ödünleşim, zamanlama kaymasıdır: 03:00'teki geceniz "son çalıştırmanın bitmesinden 24 saat sonrası" haline gelir.

### Anlık Görüntüler, Kesintiler ve Havuz Alanı

Her push, anlık bir veri deposu anlık görüntüsünden çalışır; bu yüzden depolar yazmaya devam etse bile yüklenen veri tutarlıdır. Yedekleme çalışırken, o anlık görüntü canlı depolarla paylaştığı her bloğa referans vermeye devam eder: silmeler ve [kırpma](/tr/docs/repositories#reclaim-space-trim) döngü bitip anlık görüntü silinene kadar daha az havuz alanı serbest bırakır. [Depolama sağlığı raporu](/tr/docs/monitoring#storage-health), yedekleme anlık görüntülerinin şu anda ne kadar alan tuttuğunu gösterir.

Kesintiler güvenlidir. Servisi durdurmak (veya makineyi yeniden başlatmak), yedeklemenin aktarımını iptal etmesine ve çıkmadan önce kendi anlık görüntüsünü silmesine neden olur; bir sonraki zamanlanmış çalıştırma kaldığı yerden devam eder, çünkü zaten depolanan hücreler yeniden yüklenmez. İşlem temizlenemeyecek kadar sert bir şekilde öldürülürse (elektrik kesintisi), sahipsiz kalan anlık görüntü, depolama bakımcısı tarafından dakikalar içinde otomatik olarak tespit edilip kaldırılır.

### Bir Strateji Tanımlama

Varsayılan kurulum, iki stratejili bir bölünmedir: her depoyu yakalayan hızlı, saatlik bir sıcak akış ve uygulama tutarlı anlık görüntüler için konteynerleri durgunlaştıran daha yavaş, haftalık bir soğuk akış. Her ikisi de aynı chunk deposuna yazar ve paylaşılan bloklar akış başına değil, bir kez saklanır.

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
  --include shop --include mail \
  --enable
```

`--destination <name>`, strateji içindeki hedefi adlandırır; bu sizin seçtiğiniz bir etikettir ve chunk deposunu tanımlar. `--include`, yedeklenecek depoları listeler ve tekrarlandıkça daha fazlasını ekler. Atlanırsa, strateji veri deposundaki her depoyu kapsar. Adlar, yerel yapılandırmadaki depo adıyla (`:tag` olmadan) eşleşmelidir.

`--exclude`, chunk deposu hedefi için sessizce yok sayılmak yerine reddedilir; çünkü altta yatan `backup snapshot`, depoları adlandırarak seçer ve kendi hariç tutma mekanizması yoktur. Buna uymak, hariç tutmak istediğiniz depoları yedeklemek anlamına gelirdi. Bunun yerine bir stratejinin kapsamını `--include` ile belirleyin; böylece zamanlanmış bir çalıştırmanın neyi kapsadığı tahmin edilmez, yazılı olur.

| Seçenek | Açıklama |
|--------|-------------|
| `<strategy>` (konumsal) | Strateji adı (makine bağlaması için kullanılır) |
| `--destination <name>` | Strateji içindeki hedef adı. Varsayılan chunk deposudur |
| `--storage <name>` | Kaldırılmış rclone hedef türüne katılın. Bunu kullanan bir zamanlama dağıtılamaz |
| `--cron <expression>` | Cron ifadesi (örn. günlük saat 2'de için `"0 2 * * *"`) |
| `--mode <hot\|cold>` | Yedekleme modu |
| `--bwlimit <limit>` | Yüklemeler için bant genişliği sınırı (örn. `10M`) |
| `--include <repos>` | Bu stratejinin kapsadığı depolar (tekrarlanabilir) |
| `--exclude <repos>` | Atlanacak depolar (tekrarlanabilir). Chunk deposu hedefinde reddedilir |
| `--folder <path>` | Bir rclone bucket'ı içindeki alt klasör. Chunk deposu hedefinde reddedilir |
| `--enable` / `--disable` | Stratejiyi etkinleştir veya devre dışı bırak |

### Stratejileri Görüntüleme

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Bir Stratejiyi Kaldırma

```bash
rdc backup strategy remove weekly-cold
```

### Stratejileri Bir Makineye Bağlama

Hiçbir makineye bağlanmamış bir strateji asla dağıtılmaz. Bir veya daha fazlasını bir makineye bağlayın:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

Bağlama, yapılandırmanızda makine üzerinde bir liste olarak kaydedilir; `rdc backup schedule` hangi birimleri dağıtacağına karar vermek için bunu okur:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Bağlama yalnızca yerel yapılandırmadadır.** Bir strateji tanımlamak ve onu bir makineye bağlamak, makineye dokunmaz. systemd zamanlayıcılarını dağıtmak için `rdc backup schedule -m <machine>` çalıştırın ([Makineye Zamanlama Dağıtma](#deploy-schedule-to-machine) bölümüne bakın) ve herhangi bir strateji veya bağlama değişikliğinden sonra yeniden çalıştırın.

## Sıcak ile Soğuk Arasında Seçim Yapma ve Depo Başına Filtreleme

### Bir bakışta sıcak ve soğuk

| | Sıcak | Soğuk |
|---|-----|------|
| **Tutarlılık** | Çökme tutarlı (çalışırken imaj dondurulur) | Uygulama tutarlı (durdur → dondur → başlat) |
| **Kesinti** | Yok | Depo başına durdurma+başlatma penceresi (tipik olarak 5-120 sn) |
| **Uygun sıklık** | Yüksek (örn. saatlik) | Düşük (örn. günlük veya haftalık) |
| **Tipik kullanım** | Sık güvenlik ağı | Zamanlanmış, garantili tutarlılık yedeklemesi |

**Sıcak**, yüksek sıklıklı çalıştırmalar için doğru varsayılandır. Anlık görüntü alınırken servisler çalışmaya devam eder; bu yüzden uygulamalarınız için hiç kesinti yoktur. Anlık görüntü çökme tutarlıdır: temiz olmayan bir kapanmadan sonra elde edeceğinizle eşdeğerdir. Çoğu modern veritabanı ve mesaj kuyruğu için bu yeterlidir.

**Soğuk**, garantili, uygulama tutarlı bir anlık görüntüye ihtiyacınız olduğunda ve depo başına kısa bir yeniden başlatmayı kabul edebiliyorsanız uygundur. Servisler anlık görüntüden önce durdurulur ve yükleme başlamadan önce yeniden başlatılır; bu yüzden yavaş veya başarısız bir yükleme kesinti penceresini asla uzatmaz. Tam garanti modeli için [Soğuk Yedekleme Semantiği](#cold-backup-semantics) bölümüne bakın.

Her iki mod da aynı chunk deposuna yazar. Modun belirlediği şey, imaj dondurulurken deponun nasıl ele alınacağıdır, verinin nereye yerleştiği değil. Hem saatlik sıcak hem de haftalık soğuk zamanlama tarafından kapsanan bir depo, paylaştığı hücreleri iki kez değil, bir kez saklar.

### Stratejiye Göre Depo Kapsamı Belirleme

`--include`'ı olmayan bir strateji, veri deposundaki her depoyu kapsar. `--include`'ı tekrarlamak, kapsamı yalnızca adlandırdığınız, yerel yapılandırmadaki depo adıyla (`:tag` olmadan) eşleşen depolara daraltır.

```bash
# Sıcak strateji: her şeyi saatlik yedekle
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Soğuk strateji: haftalık, ve yalnızca durgunlaşması gereken depolar
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Bir Deponun Sık Sıcak Stratejinin Dışında Tutulması Gereken Durumlar

Şu durumlarda, her şeyi almasına izin vermek yerine yüksek sıklıklı çalıştırmaya dahil etmek istediğiniz depoları adlandırın:

- Bir depo büyükse ve zaten birim üzerinde bulunan kaynak veriden **tamamen yeniden üretilebiliyorsa**, her saatlik yedekleme anlamlı bir kurtarma değeri katmadan bant genişliği harcar.
- Yedekleme çalıştırması, kullanılabilir yükleme hızında kendi zamanlama aralığını aşacaksa.

**Örnek.** Bir `analytics-demo` deposu, aynı birim içinde saklanan ham CSV döküntülerinden yeniden oluşturulabilecek yaklaşık 114 GB türetilmiş Postgres tablosu tutar. 6 MB/s'lik bir yükleme sınırında, o deponun ilk anlık görüntüsü 5 saatten fazla sürer. Bunu saatlik çalıştırmak, bir sonraki tetiklenme geldiğinde her çalıştırmanın hâlâ devam ediyor olması anlamına gelir; bu yüzden sonraki her tetiklenme sessizce atlanır ([Uzun Süren Yedeklemeler ve Çakışan Zamanlamalar](#long-running-backups-and-overlapping-schedules) bölümüne bakın). Diğer depoları `hourly-hot`'ta listelemek ve `analytics-demo`'yu `weekly-cold`'a bırakmak, onun hiç yedeklenmemesi yerine haftada bir yedeklenmesi anlamına gelir.

> **Veri tamamen yeniden üretilebilirse**, onu hiç yedeklemeniz gerekip gerekmediğini düşünün. Bir alternatif, yalnızca ham kaynak girdileri (bu örnekte CSV döküntülerini) yedeklemek ve türetilmiş kopyayı tamamen atlamaktır. Kaynak girdilerin haftalık soğuk yedeklemesi çok daha küçüktür ve kurtarma için tamamen yeterlidir.

Her iki stratejinin de kapsadığı bir depo, hem saatlik çökme tutarlı anlık görüntüler hem de haftalık uygulama tutarlı bir anlık görüntü elde eder. `rdc backup manifests <repo>` bunları birlikte gösterir ve paylaşılan hücreler bir kez saklanır.

## Yedekleme İşlemleri

### Makineye Zamanlama Dağıtma

Bağlanmış stratejileri systemd zamanlayıcıları olarak bir makineye gönderir:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Dağıtım bir durum uzlaştırıcısıdır. Makinedeki mevcut birim dosyalarını ve systemd durumunu okur, yapılandırmanın üreteceği şeyle karşılaştırır (dosya başına SHA-256) ve içeriği gerçekten değişen birimlere dokunur. Yapılandırma değişikliği olmadan yeniden çalıştırmak bir no-op'tur: yazma yok, `daemon-reload` yok, zamanlayıcı çalkalanması yok.

`--dry-run`, makineye dokunmadan her strateji için planı (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) yazdırır. `--debug` ile birleştirin, kimlik bilgileri gizlenmiş olarak oluşturulan birim gövdelerini de yazdırır. Bir chunk deposu birimi zaten hiç kimlik bilgisi taşımaz: makine kendi imzalı depo lisansıyla kimlik doğrular ve sunucu kısa ömürlü bir izin döndürür; bu yüzden birim dosyasına hassas hiçbir şey yazılmaz.

Güncellemek veya kaldırmak üzere olduğunuz bir stratejinin yedeklemesi şu anda çalışıyorsa, dağıtım hemen başarısız olur ve onu iptal etmeniz veya `--force` geçmeniz için bir ipucu gösterir. `--force` ile, çalışan çağrı belleğindeki birimini korur ve yeni yapılandırma bir sonraki zamanlayıcı tikinde uygulanır; bu yüzden çalışan yedekleme asla zorla sonlandırılmaz.

`--reset-failed` isteğe bağlıdır. Geçirildiğinde, başarılı bir dağıtımdan sonra dokunulan servislerin systemd failed durumunu temizler. Varsayılan olarak kapalıdır, böylece önceki hata sinyalleri uyarılar için görünür kalır.

### Şimdi Bir Yedekleme Çalıştırma

Zamanlayıcıyı beklemeden hemen bir yedekleme başlatır. Hiçbir zamanlayıcı dağıtılmamış olsa bile, ad-hoc çalıştırma için `systemd-run` kullanarak çalışır:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Yedekleme Durumunu Görüntüleme

Yedekleme zamanlayıcılarının şu anki durumunu ve yakın zamandaki iş sonuçlarını gösterir:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Çalışan Bir Yedeklemeyi İptal Etme

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Depo Taşıma

Bir depoyu bir makineden diğerine taşıyın:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Seçenek | Açıklama |
|--------|-------------|
| `<ref>` (konumsal) | Taşınacak deponun referansı; `@machine` kısmı kaynağı adlandırır |
| `--to <place>` | Hedef makine veya küme |
| `--provision <provider>` | Hedef makineyi bu bulut sağlayıcısı üzerinden otomatik sağlayın (örn. `hetzner`, `linode`) |
| `--checkpoint` | Taşımadan önce bir CRIU kontrol noktası oluşturun; böylece işlem belleği de taşınır |
| `--delta-base <guid>` | Geçiş delta'sı için değişmez temel GUID. Varsayılan, ilk aşamanın temelidir |
| `--strategy <strategy>` | Geçiş için blok delta stratejisi: `auto`, `physical` veya `shared` |
| `--skip-dns` | Taşımadan sonra DNS kayıtlarını güncellemeyi atla |
| `--keep-source` | Başarılı bir taşımadan sonra kaynak imajları koru |
| `--bwlimit <limit>` | Aktarım için bant genişliği sınırı (örn. `50M`) |

Taşıma, şifreli depo verisini rsync üzerinden iki aşamada aktarır: depo çalışmaya devam ederken toplu bir aktarım, ardından delta için kısa bir durdurma. Taşıma depoyu **taşır**; bu yüzden taşıma başarılı olduğunda kaynak imajlar silinir. Bunları saklamak için `--keep-source` geçirin. Bu, `repo migrate` ile `repo push` arasındaki farktır: push kaynağı çalışır ve dokunulmamış bırakır.

## Kaldırılmadan Önce Yazılmış Bir Arşivi Okuma

`rdc storage`, rclone kolundan geriye kalandır ve salt okunurdur. Artık bir yedekleme hedefi olamaz, ancak buna yazılmış bir arşive hâlâ erişebilir.

```bash
# rclone için zaten yapılandırdığınız bir remote'u kaydedin.
rdc storage import rclone.conf
rdc storage list

# İçinde ne olduğuna bakın. Bu, PATH'inizdeki rclone'u çalıştırır.
rdc storage browse my-storage
```

`import`, bir rclone yapılandırma dosyasını okur ve remote'ları yapılandırmanıza kaydeder; desteklenen türler S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob ve Swift'tir.

**`browse`, PATH'inizde `rclone` gerektirir.** Komutu yazdığınız makinede kurulu rclone'u çalıştırır; artık paketlenmiş bir kopya yoktur. Yoksa, bunu size söyler ve başka bir şey yapmaz.

Bir depolama arka ucuna gönderme, çekme, listeleme ve geri yükleme kaldırılmıştır; her biri reddedilir ve yerine geçen komutu adlandırır.

## En İyi Uygulamalar

- Kritik verinin uygulama tutarlı kopyaları için günlük soğuk anlık görüntüler zamanlayın
- Sıfır kesinti gerektiren yüksek sıklıklı çalıştırmalar için sıcak anlık görüntüler kullanın
- Geri yüklemeleri düzenli olarak test edin. `rdc backup restore --as <new-name>` hiçbir şeyin üzerine yazmaz; bu yüzden bir prova, canlı bir makinede güvenlidir
- Elle budamak yerine bir saklama politikası ayarlayın; böylece tuttuğunuz pencere yazılı olsun
- Kontrolünüzdeki donanımda bir kopya istiyorsanız, anlık görüntülere ek olarak makineler arası bir kopya da tutun
- Kimlik bilgilerini güvende tutun; yedekler şifrelidir ama geri yüklemek için LUKS kimlik bilgisi gerekir
