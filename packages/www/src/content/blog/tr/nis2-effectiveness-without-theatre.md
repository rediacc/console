---
title: "Yıllık Sızma Testiniz Uyum Tiyatrosu. NIS2 Article 21(2)(f) Bunu Sorun Haline Getirdi."
description: "Sürekli etkinlik değerlendirmesi, bunu ucuzlatan sabit-zamanlı fork ve adli kalitede kanıt olmadan karşılanamayacak Article 23 raporlama takvimi."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - sre
  - dr-testing
  - effectiveness
  - incident-reporting
featured: false
language: tr
sourceHash: "21965e5d5e9f25d5"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

> **Özet.** Çoğu güvenlik programı kurtarma testini yılda bir kez, geçen yaz üretimden alınan bir staging ortamına karşı yapar. Üretime benzemeyen bir ortamda sızma testi yaptırır, temiz bir rapor alır ve dosyaya koyar. NIS2 Article 21(2)(f), denetçilerin üzerine yoğunlaşacağı bir ifadeyi hayata geçirdi: önlemlerin "etkinliğini değerlendirmeye yönelik politikalar ve prosedürler". Yıllık, sürekli değildir. Güncelliğini yitirmiş staging, test altındaki sistem değildir.
>
> - Direktife göre: 21(2)(e) ve (f) birlikte, gerçekten işleyen, talep üzerine, güncel üretime karşı kurtarma ve güvenlik testi yapılmasını zorunlu kılar.
> - Delphix sınıfı araçlar, Veeam Instant Recovery veya Rubrik Live Mount ile doğru yapmanın maliyeti, çoğu ekibin sessizce staging'i tercih etmesinin nedenidir.
> - Üretim fork'u yedi saniye sürdüğünde ekonomi tersine döner. Haftalık tatbikatlar gerçekçi hale gelir. Sürekli etkinlik belgelenebilir.
> - Article 23 raporlaması (24 saatlik erken uyarı, 72 saatlik bildirim, bir aylık rapor), adli kalitede kanıt olmadan karşılanamaz. Kanıtlar bizde; SOC, SIEM ve ENISA başvuru iş akışı hala sizin sorumluluğunuzdadır.

Herhangi bir orta ölçekli SRE ekibine gidin ve tek bir soru sorun: son tam uçtan uca kurtarma işlemini ne zaman yaptınız; yedek dosya doğrulaması değil, kurtarılan sistemi uygulamalar, veritabanları ve yapılandırmalarla gerçekten ayağa kaldırıp çalıştığını doğruladığınız bir test? Çoğu ekipteki dürüst cevap "geçen yılki masa başı tatbikatında" olacaktır. Sonra herkes işe geri döner.

NIS2 Article 21(2)(f), denetçilerin üzerine yoğunlaşacağı bir ifadeyi hayata geçirdi:

<!-- nis2-quote-lang: en -->
> "policies and procedures to assess the effectiveness of cybersecurity risk-management measures"

"Yıllık" demiyor. "Politikalar ve prosedürler" diyor. Article 21(2)(e) ile birlikte okunduğunda, şunu zorunlu kılıyor:

<!-- nis2-quote-lang: en -->
> "security in network and information systems acquisition, development and maintenance, including vulnerability handling and disclosure"

yükümlülük süreklidir, periyodik değil. 2024 ENISA uygulama rehberi (Implementing Regulation (EU) 2024/2690'ın Ek IV'ü) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> "süregelen değerlendirme" ve "eski ya da staging anlık görüntülerini değil, güncel üretim ortamlarını kapsayan test belgesi" gibi ifadelerle bu yönü teyit ediyor.

Etkinlik hikayeniz "staging'e karşı yıllık sızma testi" ise 2026 rahatsız edici geçecek.

Bu yazı SRE liderlerine, operasyon yöneticilerine ve tatbikatları fiilen yürüten güvenlik mühendislerine yöneliktir. Aynı zamanda rakiplerin her karşı teklifte kaldıraç olarak kullanacağı noktayı da açıkça adlandıran bir yazıdır: Article 23 takvimleri için yönetilen raporlama ve SIEM bağlayıcı hizmetleri. Bunu çözmüyoruz. Kanıtları size veriyoruz. Raporlama iş akışı, SOC, ENISA başvuru motoru hala sizin sorumluluğunuzdadır.

**Türkiye bağlamı.** Türkiye AB üyesi değildir ve NIS2 doğrudan uygulanmaz. Ancak AB'ye mal veya hizmet ihraç eden Türk şirketler, Direktif'in tedarik zinciri hükümleri (Article 21(2)(d)) kapsamında AB'li müşterilerinden dolaylı baskı almaktadır. Türkiye'deki kuruluşlar için 7545 sayılı Siber Güvenlik Kanunu ve BGYS zorunlulukları benzer etkinlik kanıtı gerekliliklerini getirmektedir. Bu yazıdaki teknik yaklaşım her iki çerçeve için de geçerlidir.

## 21(2)(e) ve (f)'yi birlikte okumak

Article 21 on asgari tedbiri listeler. Bunlardan ikisi nasıl inşa ettiğinizle ve nasıl kontrol ettiğinizle ilgilidir.

(e) **Edinim, geliştirme ve bakımda güvenlik**: Bu arz tarafı tedbiridir. CVE yaması kabul ettiğinizde, yeni bir mikro hizmet yayınladığınızda, bakım penceresi çalıştırdığınızda, değişikliğin gireceği gerçek ortama karşı doğrulanması gerekir. ENISA'nın rehberi, veri şekli, ölçek, gizli bilgiler veya yapılandırma açısından üretimden farklılaşan staging ortamlarının güvenlikle ilgili değişiklikler için test yükümlülüğünü karşılamadığını açıkça belirtmektedir.

(f) **Etkinlik değerlendirmesi**: Bu doğrulama tedbiridir. Sahip olduğunuz her kontrol için, bunların gerçekten çalıştığını teyit edecek politika ve prosedürlere ihtiyaç vardır. "Etkinlik" ifadesi gerçek anlam taşır. "Yedeğimiz var" (kontrol mevcut) ile "geçen Salı ondan geri yükleme yapabildiğimizi kanıtladık ve geri yüklenen sistem duman testinden geçti" (kontrol etkin) arasındaki fark budur.

Birlikte okunduğunda, iki tedbir şunu gerektirir: güvenlikle ilgili değişiklikler güncel üretime eşdeğer ortamlarda test edilmeli ve test, değişikliğin çalıştığına dair kanıt üretmelidir. Yıllık çok seyrektir. Güncelliğini yitirmiş staging yanlış hedeftir. Doğrulanmamış geri yükleme etkin değildir.

Bu yükümlülüğe geleneksel yaklaşım, çoğu ekibin zaten yaptığı şeydir: staging'i üretime benzer ilan etmek, yıllık kadansla staging'e karşı tatbikat yürütmek, gerçek bir olayda ne olacağını açıklayan bir işletme rehberi yazmak ve denetçinin fazla soru sormamasını ummak. Denetçinin GDPR VKA'sı olduğu ve olayın gizlilik vakası olduğu dönemde bu işe yarıyordu. NIS2, koltuğa farklı bir denetçi oturtuyor (ulusal CSIRT, ya da Almanya'da BSI, Fransa'da ANSSI, İtalya'da ACN) ve bu denetçi operasyonel sorular soruyor.

## Güncelliğini yitirmiş staging tuzağı

Üç şey, çoğu ekip onlara karşı test yaparken staging'i üretim-dışı hale getirir.

**Veri şekli**: Üretim verisi uzun-kuyruk uç durumlar içerir. 8.000 karakterlik notlar alanına sahip müşteri, her diğer satırda değer varken NULL olan eski hesap, tüm CRM geçmişini içe aktaran tek kiracı için 12 milyon satır döndüren birleştirilmiş tablo. Staging, üretim hacminin yüzde birini içerir ve uzun kuyruk örnekte yoktur.

**Ölçek**: Staging'deki 10.000 satırda 50ms'de dönen sorgu, üretimdeki 12 milyonda 8 saniyede döner. Staging'de tükenme açığını bulamayan sızma testi senaryosu üretimde anında bulur. Açık şekli veri ölçeğine bağlıdır.

**Yapılandırma kayması**: Üretim, ortam değişkenlerini, IAM rollerini, ağ politikalarını, üç kez döndürülmüş gizlilikleri, geçen hafta yenilenen bir SSL sertifikasını, Mart'ta kapatılması gerekip açık kalan bir özellik bayrağını biriktirmiştir. Staging, geçen yazın yapılandırmasının temiz bir kopyasına sahiptir, üzerine en son proje için eklenenler eklenmiştir. Deltalar tam da güvenlik hatalarının gizlendiği yerdir.

Dolayısıyla yama staging'den geçtiğinde ekibin güveni yersizdir. Sızma testi staging'e karşı temiz rapor verdiğinde rapor yanıltıcıdır. Kurtarma tatbikatı staging'i başarıyla geri yüklediğinde ekip üretim kurtarmasını doğrulamamıştır.

2026'daki denetçiler staging'in yeterince iyi olup olmadığını tartışmıyor. Güncel üretime karşı test kanıtı istiyorlar. Kanıtın zaman damgası olması, testin yapıldığı sırada test altındaki sistemin üretime benzediğini göstermesi ve testin sonuç ürettiğini göstermesi gerekiyor.

Çoğu ekip bugün bu kanıtı üretemiyor; çünkü geleneksel araçlarla güncel üretime karşı tatbikat yürütmenin maliyeti çok yüksek.

## Geleneksel araçlarla doğru yapmanın maliyeti

Piyasanın yanıtları var. Yanıtlar pahalı.

**Veeam Instant Recovery**: Yedeği doğrudan bir VM olarak ayağa kaldırır, bağlar ve bir ağ arabirimiyle uçlar. Uygulama tutarlı kurtarma testi için kullanılır. Son yedeğe karşı kurtarma testi yapabilir; staging ortamı kurtarılan yedek haline gelir. Disk okumaları yedek deposundan geldiği için kapasitesi düşüktür. Maliyet: Veeam Data Platform Premium lisanslaması VM sayısına göre ölçeklenir ve kurtarma testi yine bir mühendis tarafından planlanıp işletilmek zorundadır. Çoğu ekip bunu çeyreklik yapar.

**Rubrik Live Mount**: Benzer kavram, test için bir yedek anlık görüntüsünün anında bağlanması. Bulut-native iş yükleriyle daha iyi entegrasyon. Aynı operasyonel örüntü. Aynı test başına mühendislik yükü.

**Delphix (Perforce DevOps Data)**: Geliştirme ve test için kaynak veritabanlarının neredeyse anında klonlarını oluşturan veri sanallaştırma aracı. "Dev'de üretime şekilli veri istiyoruz" sorununu çözer. Yalnızca veritabanı. Uygulama hizmetlerini, yapılandırmaları, gizlilikleri veya konteyner durumunu klonlamaz. Yıllık lisans, orta piyasa ekipleri için altı haneli rakamlara ulaşır.

**Tonic.ai, Redgate Test Data Manager**: Veri maskeleme ve sentetik veri yaklaşımları. Dev ve test ortamları için gizlilik-gerçekçilik dengelerini çözer. Veri şekli ve ölçek açısından üretime gerçekçidir. Tam yığın klon değildir. Uygulama yapılandırmasının önemli olduğu güvenlik testi senaryoları için tasarlanmamıştır.

**Özel yapı**: Sıcak yedek al, paralel bir ortama geri yükle, testi çalıştır, yıkmadan kaldır. Kavramsal olarak mümkün. Operasyonel olarak tatbikat başına birden fazla günlük mühendislik çalışması. Ekip bunu bir kez yapar, çünkü mecbur kalır, sonra bir daha yapmaz.

Yapısal sorun şudur: üretim klonlaması, tam yığın ve uygulama durumu dahil, tarihsel olarak ya (a) bayt başına veri transferi (ölçekte yavaş ve pahalı), ya (b) anlık görüntü tabanlı VM klonlaması (IaaS için işe yarar, konteynerler ve Kubernetes için bozulur), ya da (c) veri sanallaştırma (yalnızca veritabanı) gerektirmiştir. Her üç yaklaşım da ortam boyutuyla orantılı test başına maliyet taşır.

Test başına maliyet boyutla ölçeklendiğinde tatbikatlar nadir etkinliklere dönüşür. Nadir etkinlikler sürekli etkinlik değerlendirmesini karşılamaz.

## Üretim fork'u yedi saniye sürdüğünde ne değişir

Rediacc, depo fork'lama için BTRFS reflink kullanır. Mekanizma, dosya sistemi düzeyinde kopyala-yaz (copy-on-write) özelliğidir: fork, her iki taraftan biri yeni veri yazana kadar blokları üst depoyla paylaşır; bu noktada yalnızca değişen bloklar ayrışır. Fork işleminin kendisi, depo boyutundan bağımsız olarak sabit zamanlıdır.

[PocketOS test yazımızda](/tr/blog/i-tested-rediacc-against-the-pocketos-incident) 128 GB'lık bir üretim deposunu uçtan uca 7,2 saniyede fork'ladık. Reflink'in kendisi 2,3 saniyeydi. Geri kalanın çoğu yeni bir Docker daemon'ı sağlamak, LUKS ile şifrelenmiş birimi bağlamak ve yeni bir loopback IP alt ağında hizmet yığınını ayağa kaldırmaktır.

Fork'un şekli hız kadar önem taşır. Rediacc fork'u tam yığındır. Fork'lanan depo şunları içerir:

- Tüm veri dosyaları ve veritabanı durumu dahil LUKS ile şifrelenmiş birim.
- Docker daemon yapılandırması ve konteyner durumu.
- Rediaccfile yaşam döngüsü kancaları (`up`, `down`, `info`).
- Deponun loopback IP alt ağı (fork için ayrılmış taze bir `/26`).
- Deponun ağ kimliği, daemon soketi ve bağlama ad alanı.

Varsayılan olarak içermediği şey, hizmetlerinizin harici SaaS ile (Stripe, posta aktarıcıları, DKIM anahtarları, webhook imzalama anahtarları) iletişim kurması için ihtiyaç duyduğu gizlilikleridir. Bunlar için `rdc repo secret`, kimlik bilgilerini fork görüntüsünden tamamen dışarıda tutar; böylece fork'tan gelen harici SaaS çağrıları açık olur, miras alınmaz. Gizlilik modeli için bkz. [Depolar](/tr/docs/repositories).

Bu şekil, açık gizlilik yönetimiyle tam yığın, fork'u güvenlik testi hedefi olarak uygun kılan şeydir. Fork, üretim sistemidir; güncel üretim verileri, güncel üretim yapılandırması, güncel konteyner durumu ile on saniye önce. Denetçinin test etmenizi istediği sistem budur.

Belgelenmiş kullanım durumları için bkz. [Risksiz Yükseltmeler](/tr/docs/risk-free-upgrades) ve [Eğitim: Fork'lama](/tr/docs/tutorial-forking).

## Haftalık çalıştırabileceğiniz sürekli etkinlik rutini

Tek bir SRE tarafından haftalık kadansla çalıştırılabilen, bir üretim deposu için Article 21(2)(e) ve (f)'yi karşılayan somut bir rutin:

**Adım 1**: Üretimi fork'la.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

Fork, denetim günlüğünün kendi kendini açıklar olması için ISO haftasıyla adlandırılır. Depo, fork'a özgü bir alt alan adı altında çalışır (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`) ve üst deponun wildcard sertifikası bunu kapsar. Yeni TLS el sıkışması gerekmez.

**Adım 2**: Test altındaki yamayı fork üzerine uygula.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

Term oturumu, fork'un daemon soketiyle sınırlandırılmış `DOCKER_HOST` ile ayrı bir bağlama ad alanında ayrıcalıksız `rediacc` kullanıcısı (UID 7111) olarak çalışır. Depo-çapraz erişim, çekirdek düzeyinde engellenir (fork, üretimin loopback alt ağına ulaşamaz). Yalıtım modeli için bkz. [Mimari § Docker Yalıtımı](/tr/docs/architecture).

**Adım 3**: Fork'a karşı duman testini çalıştır.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (proje özgü duman testiniz buraya gelir)
```

**Adım 4**: Geri yükleme tatbikatını çalıştır. Fork'la hizalanmış bir hedefe çekilen en son sıcak üretim yedeğini kullan.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# geri yüklenen fork'un aynı duman testine yanıt verdiğini doğrula
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

Bu, 21(2)(c) ve (f)'nin istediği kurtarma testidir: "yedek dosya bütünlüğü doğrulandı" değil, "kurtarılan sistem duman testine yanıt veriyor."

**Adım 5**: Denetim günlüğünü kaydet, ardından yık.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

Denetim günlüğü her adımı yakalar (fork oluşturma, repo up, term oturumları, yedek çekme, repo yıkma). Hash zincirine bağlıdır. Operatörün iş istasyonundaki `rdc audit verify`, olaylar yazıldığından bu yana zincirin değiştirilmediğini doğrular. Denetim modeli için bkz. [Hesap Güvenliği § Yapay Zeka Ajanları için CLI Güvenlik Duruşu](/tr/docs/account-security).

Rutinin 128 GB'lık bir depo için toplam gerçek zamanlı süresi 15 dakikanın altındadır. Bunun büyük çoğunluğu duman testi ve yedek çekme için ağ gidiş-dönüş süresidir. Fork işlemlerinin kendisi saniyeler alır.

Haftada bir kez bu rutini çalıştıran tek bir SRE, yılda 52 zaman damgalı, denetim günlüğüne kaydedilmiş etkinlik kaydı üretir. Bu, denetçinin aradığı kanıt şeklidir.

Makineler arası ve kıtalararası tatbikatlar dahil daha geniş kurtarma hikayesi için bkz. [Çapraz Yedekleme Stratejisi](/tr/docs/cross-backup) ve [Yedekleme ve Geri Yükleme](/tr/docs/backup-restore). Kısmi bozulma olaylarında anlık nokta semantiği için bkz. [Zaman Yolculuğu Kurtarma](/tr/docs/time-travel-recovery).

## Article 23: Kanıt olmadan karşılanamayacak raporlama takvimi

NIS2 Article 23, olay raporlama saatidir. Üç son tarih:

- **24 saat**: Önemli bir olayın farkına varılmasından itibaren, ulusal CSIRT'e veya yetkili makama erken uyarı. Olayın devam ettiğini bildirir ve sınır ötesi etki hakkında ilk bilgiyi verir.
- **72 saat**: Farkına varılmasından itibaren tam olay bildirimi. Önem değerlendirmesi, ilk uzlaşma göstergeleri, tehdit türü ve bilinen etki dahildir.
- **Bildirimden bir ay sonra**: Nihai rapor. Ayrıntılı açıklama, kök neden, uygulanan hafifletmeler, devam eden risk.

Bu sıkı bir saat. Aynı zamanda olay hala devam ederken çalışan bir saattir. Article 23'ün en acı verici versiyonu, ekibin ilk 24 saatte aynı anda hizmetleri geri yüklediği, adli kanıtları koruduğu, kolluk kuvvetleriyle koordine ettiği, yönetim ekibini bilgilendirdiği ve erken uyarıyı yazdığı versiyondur.

Standart yedekleme araçları bir ödünleşim dayatır: hizmeti geri almak için sistemi geri yükle ya da araştırmak için sistemi koru. Yedekten geri yüklediğinizde, uzlaşmanın canlı kanıtı kaybolur. Araştırmak için güvenliği ihlal edilmiş sistemi dondurduğunuzda müşterilere hizmet veremezsiniz. Her ikisi de Article 23 takviminde kötüdür.

Fork mekanizması bu ödünleşimi çözer. Güvenliği ihlal edilmiş durum fork'lanabilir (üst depo adli anlık görüntü haline gelir) ve trafiği sunmak için en son temiz yedekten paralel bir fork ayağa kaldırılabilir. Adli fork analiz için salt okunurdur. Sunum fork'u müşterilere yanıt verir. Her ikisi aynı anda aynı makinede, reflink aracılığıyla blok paylaşarak var olur; bu nedenle bu operasyonel olarak karşılanabilirdir.

Somut olarak bir olayda:

```bash
# Adli inceleme için güvenliği ihlal edilmiş durumu anlık görüntüle. Fork anlık görüntüdür.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Son temiz yedekten bir sunum fork'u ayağa kaldır. Farklı etiket.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Trafiği DNS veya rota sunucusu üzerinden yeni sunum fork'una yönlendir.
```

Adli fork, 60. saatte denetçinin sorusunu yanıtlar: "uzlaşma anındaki sistemlerinizin tam durumunu gösterin." Sunum fork'u müşterinin sorusunu yanıtlar. 70'ten fazla olay denetim günlüğü, hash zincirine bağlı, doğrulanabilir bir şekilde "kim ne yaptı, ne zaman" sorusunu yanıtlar.

Rediacc'ın operatöre verdiği budur. Vermediklerimiz:

- **SIEM**. Splunk, Datadog, Sentinel veya kendi altyapınıza yayın yapmıyoruz. Denetim günlüğü operatörün iş istasyonunda yerel JSONL'dir; bunu bir SIEM'e yönlendirmek operatörün entegrasyon işidir.
- **SOC**. 7/24 tespit kapasitesi işletmiyoruz. Uyarı üretmiyoruz. Önceliklendirme yapmıyoruz.
- **Yönetilen raporlama**. ENISA raporunu sunmuyoruz. Erken uyarı taslağı hazırlamıyoruz. Ulusal CSIRT ile sizin adınıza koordinasyon yapmıyoruz.

Rakiplerin bize karşı kullanacağı kaldıraç budur. Coveware entegrasyonlarıyla Veeam Data Platform, yönetilen hizmetler koluyla Rubrik ve birkaç özel IR-taahhüt firması (Avrupa'da Mandiant, Kroll, S-RM), tam olarak Rediacc'ın sağlamadığı operasyonel katmanı satıyor. Bunun tersini iddia etmek, bizi zor duruma düşürecek pazarlama hamlesinin ta kendisidir. Savunulabilir konum şudur: Rediacc, o hizmetlerin kendi başlarına üretemediği adli kalitede kanıtları size verir; o hizmetler, Rediacc'ın sağlayamadığı operasyonel raporlama katmanını size verir. Tamamlayıcıdırlar. Bir NIS2 programı ikisine de ihtiyaç duyar.

## Rediacc'ın sizin yerinize yapmadıkları

Bir SRE'nin, yazının geri kalanının ilginç olup olmadığına karar vermeden önce bilmesi gereken iki şey.

**Rediacc sızma testi yapmaz**. Hedef olarak fork, ortamdır; test kapasitesi değil. Gerçek bir düşmanca sızma testi hala kırmızı ekibiniz veya sözleşmeli test firmanızdır (otonom için Pentera, Horizon3.ai; insan liderliğindeki için özel danışmanlık firmaları). Rediacc, test ortamının gerçekçi olmadığına dair bahanelerini ortadan kaldırır. Testin maliyetini ortadan kaldırmaz.

**Rediacc işletme rehberlerinizi yazmaz**. Yukarıdaki CLI komutları hareketli parçalardır. Ne zaman fork yapılacağına, ne zaman yük devredeceğine, müşterilerle nasıl iletişim kurulacağına, ne zaman kolluk kuvvetlerine başvurulacağına ilişkin kararlar işletme rehberi kararlarıdır. Bunların hala ekibiniz tarafından yazılması, tatbikat edilmesi ve güncellenmesi gerekir. NIS2 Article 21(2)(b) (olay yönetimi) bir araç yükümlülüğü değil, süreç yükümlülüğüdür ve biz bunun bir bölümünü karşılıyoruz, tamamını değil.

Tedarik tarafındaki kapsam (sertifikalar, GRC, tedarikçi kaydı konsolidasyonu) için bkz. [tedarik zinciri yazısı](/tr/blog/nis2-supply-chain-self-hosted). Maliyet tarafındaki kapsam (kendi kendine barındırılan bir kontrol düzleminden sonra bütçede ne kalır) için bkz. [gerçek fatura yazısı](/tr/blog/nis2-the-real-bill).

Bunların doğru okunması şudur: Rediacc bir araç katmanıdır, güvenlik programı değildir. Bahaneleri ortadan kaldırır ve kanıt üretir. Programı sizin yerinize çalıştırmaz.

## Denetçi 2026'da ne görmek ister

Üç kanıt. Bunları üretin; Article 21(2)(e) ve (f) görüşmesi kısalır.

**Kanıt 1: fork tatbikat kadansı**. Yuvarlanan on iki ay boyunca haftalık veya iki haftada bir kadansla yürütülen etkinlik tatbikatlarının zaman damgalı günlüğü. Her giriş, üst depoyu, fork etiketini, test altındaki yamayı veya değişikliği, duman testi sonucunu ve yıkma zaman damgasını gösterir. `rdc audit log --since` tarafından üretilen denetim günlüğü bunların tümünü yakalar.

**Kanıt 2: hash zincirine bağlı denetim günlüğü**. Denetim günlüğündeki hash zinciri, "geçen yıl 47 tatbikat yaptık" iddiasını kanıta dönüştüren şeydir. `rdc audit verify`, zinciri uçtan uca doğrular. Doğrulama sonucu, bir denetçinin yeniden çalıştırabileceği tek bir komut çıktısıdır.

**Kanıt 3: yedek doğrulama izi**. Zamanlanmış her yedekleme stratejisi için systemd birimi, depo başına çalışma başına `/var/run/rediacc/cold-backup-<guid>.status.json` konumunda bir durum yan dosyası ve son bir özet günlük satırı üretir. `rdc machine backup status` her ikisini de ortaya çıkarır. Yukarıdaki rutinin 4. Adımındaki haftalık geri yükleme tatbikatıyla birleştirildiğinde, bu denetçiye yalnızca "yedek alındı" izi değil, "yedek alındı ve geri yükleme test edildi" izi sunar. Tanılama yüzeyi için bkz. [İzleme](/tr/docs/monitoring).

Kanıtlar birlikte "kontrolleriniz etkin mi" sorusunu doğrulama değil, zaman damgaları ve hash zincirine bağlı kanıtlarla yanıtlar.

## Bu, bir sonraki üç aylık planlama toplantısı için ne anlama gelir

Ekibiniz Q3 planlamasına girecekse ve Article 21(2)(f) güvenlik iş birikimine girmişse, üç somut hareket:

1. Mevcut etkinlik hikayenizi denetleyin. Son on iki ayın sızma testi raporlarını, kurtarma tatbikatlarını ve yama doğrulama biletlerini alın. Bunlardan kaçının güncel üretime yönelik olduğunu sayın. Dürüst sayım genellikle beşin altındadır.
2. Bir üretim deposu seçin ve yukarıdaki haftalık rutini bir ay boyunca çalıştırın. Rutin, programlama ek yükü olmadan tek bir SRE tarafından işletilebilecek şekilde tasarlanmıştır. Dört hafta sonra dört zaman damgalı etkinlik kaydınız olur; bu, çoğu ekibin bir yılda ürettiğinden fazladır.
3. SIEM, SOC ve Article 23 raporlama iş akışını kimin karşılayacağını konuşun. Yanıt "henüz o noktaya gelmedik" ise, başlangıç noktası Rediacc değil, 7/24 tespit kapasitesidir. Bu konuşmaya tamamlayıcıyız; başlangıç noktası değiliz.

En büyük deponuzdaki fork zamanlamasını görmek istiyorsanız teklif basit. Bizimle bir görüşmede çalıştırın. Fork on saniyeden uzun sürerse bize hiçbir şey borçlu değilsiniz. Yedi saniye sürerse, görüşmenin geri kalanını yığınınızdaki rutini adım adım inceleyerek geçiririz.

Yapısal maliyet hikayesi (güvenlik yığınının geri kalanında neler konsolide edilir ve bütçe satırında ne kalır) [gerçek fatura](/tr/blog/nis2-the-real-bill) eşlik yazısındadır. Tedarikçi kaydı ve tedarik açısı için bkz. [Article 21(2)(d) ve öz barındırma](/tr/blog/nis2-supply-chain-self-hosted).

NIS2 makalelerine yönelik kapasite eşlemesinin kamuya açık versiyonu için bkz. [NIS2 ve DORA](/tr/docs/legal-nis2-dora).
