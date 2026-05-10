---
title: "Article 21(2)(d) Bir Tedarikçi Sorusudur. Self-Hosting ise Artık Vermek Zorunda Olmadığınız Yanıttır."
description: "Veri katmanı hiç kiracılığınızdan ayrılmadığında üçüncü taraf BİT kaydı neden küçülür. 2026'da DPA'larını yeniden müzakere eden CISO'lar ve tedarik yöneticileri için NIS2 Article 21(2)(d)'nin veri yolu okuması."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - supply-chain
  - self-hosted
  - sovereignty
  - compliance
featured: false
language: tr
sourceHash: "30fcebe300afa3f2"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

> **Özet.** NIS2 Article 21(2)(d), tedarik zinciri riskini bir satın alma dipnotu olmaktan çıkarıp yönetim kurulu düzeyinde bir soruya dönüştürüyor. Direktif, self-hosting'i fiilen zorunlu kılmıyor. Ancak veri yolunuzda nelerin bulunduğunu ve o tedarikçilerden birinin kötü bir gün geçirmesi durumunda başınıza nelerin geleceğini soruyor. Self-hosted altyapı, çoğu SaaS veri yolundaki dört katmanın üçünü çöküştürüyor. Dördünün tamamını çöküştürmüyor; bunu iddia etmek ise bir CISO'yu denetçinin karşısında zor duruma düşüren pazarlama hamlesinin ta kendisi.
>
> - Direktif metni ve ENISA rehberliği, sade bir dille.
> - Çoğu ekibin çizmediği dört katmanlı SaaS veri yolu.
> - Rediacc'ın iki araçlı modelinin tedarikçi kaydınızdan neyi çıkardığı ve neyi bıraktığı.
> - "NIS2-hazır" iddiasındaki herhangi bir tedarikçi için altı soruluk tedarik kontrol listesi.

Temmuz 2020'de Blackbaud fidye ödedi ve bunu dünyaya sonradan duyurdu. 13.000'den fazla müşteri kuruluşa olaydan sonra bildirimde bulundu, yedi yargı bölgesinde toplu davalarla uğraştı ve sonunda eyalet başsavcıları uzlaşmaları kapsamında 49,5 milyon dolar ile yanıltıcı açıklamalar nedeniyle 3 milyon dolarlık SEC cezası ödedi. Bu 13.000 kuruluşun tamamının Blackbaud ile imzalanmış bir Veri İşleme Sözleşmesi (DPA) vardı. Büyük çoğunluğu Blackbaud'un SOC 2 raporunu incelemişti. Pek çoğu Blackbaud'u tedarikçi risk kaydında tutuyordu: katman derecelendirmesiyle, yenileme tarihleriyle ve sorumlu bir isimle.

Hiçbiri bu zincirleme kırılmayı durduramadı. Veri Blackbaud tarafındaydı. Yedekleme ortamları ihlal edildiğinde, tüm müşteri kuruluşlar aynı anda ihlale uğradı.

NIS2 Article 21(2)(d), "tedarikçinizi denetlediniz mi" sorusundan çok daha zor bir soru soruyor: Veri yolunuzda ne var ve o tedarikçi kötü bir gün geçirdiğinde başınıza ne gelir? Çoğu ekip için yanıt şu: "Biz onlarız ve bunu fark etmemiştik."

Bu yazı, 2026'da DPA'larını yeniden müzakere eden CISO'lar ve tedarik yöneticileri içindir. Article 21(2)(d)'nin sertifika okuması değil, veri yolu okumasıdır. Self-hosted altyapının çözmediği şeyler konusunda da dürüsttür; çünkü boşluk bölümü denetçinin soracağı şeydir ve bir pazarlama broşürünün atlayacağı şeydir.

## Article 21(2)(d) Gerçekte Ne Yükümlüyor

Direktifin İngilizce orijinal metni aşağıdadır (Türkiye AB üyesi olmadığından direktifin resmi Türkçe çevirisi bulunmamaktadır; alıntı İngilizcede verilmektedir):

<!-- nis2-quote-lang: en -->
> "Member States shall ensure that essential and important entities take appropriate and proportionate technical, operational and organisational measures to manage the risks posed to the security of network and information systems which those entities use [...] and shall include at least the following: [...] (d) supply chain security, including security-related aspects concerning the relationships between each entity and its direct suppliers or service providers"

Bu metinde bir alıcı açısından önem taşıyan iki nokta var.

Birincisi, yükümlülük tedarikçinin değil sizin üzerinizdedir. Tedarikçinin sertifikaları, SOC 2 belgesi, ISO 27001 belgesi; risk değerlendirmenizin girdileridir, yerine geçemez. Tedarikçinizin kusursuz bir uyum profili olsa da yine de ihlale uğrarsa düzenleyicinin sorusu, tedarikçi risk yönetiminiz hakkında olacaktır; tedarikçinin yönetimi hakkında değil.

İkincisi, yükümlülük sözleşmenin ötesine geçer. ENISA'nın 2024 uygulama rehberi olan Komisyon Uygulama Yönetmeliği (EU) 2024/2690'ın Ek IV'ü beklenen pratiği şöyle ortaya koyuyor: BİT tedarikçilerinin kaydını tutun, onları kritiklik derecesine göre sınıflandırın, her birini operasyonlarınıza ve işledikleri verilere yönelik risk açısından değerlendirin ve değerlendirmeyi tanımlı bir döngüde yenileyin. Ek IV, "tedarikçilerin tedarikçilerini" açıkça kapsam dahilinde sayıyor; bu noktada çoğu ekip, tedarikçi kaydının aslında gerçek bir kayıt değil, üstüne etiket yapıştırılmış bir sözleşme listesi olduğunu fark ediyor.

Konuya tedarik tarafından bakıyorsanız pratik karşılığı şu: Üretim verilerinize mantıksal erişimi olan her tedarikçi numaralandırılmak, puanlanmak, izlenmek ve değiştirilebilir olmak zorunda. "Değiştirilebilir" kelimesi, mevcut düzenlemelerin büyük çoğunluğunu bozan kısımdır.

## Çoğu Ekibin Çizmediği Dört Katmanlı SaaS Veri Yolu

Bir tedarik yöneticisiyle oturup yedekleme tedarikçisinin ürünü tek bir kayıt yazdığında ne olduğunu adım adım gözden geçirin. Dürüst veri yolu, yukarıdan aşağıya şöyle görünür:

1. **Tedarikçi uygulaması.** Verinizi alan, yönlendirme kararları veren ve iş mantığını uygulayan kod. Tedarikçinin altyapısında çalışır. Bakımını, yamalarını ve izlemesini tedarikçi yapar.
2. **Tedarikçi bulutu.** Uygulamanın çalıştığı hiper ölçekleyici bölge veya tedarikçinin kendi veri merkezi. Depolama birimleri, ağ, IAM. Çoğunlukla tedarikçinin alt işlemci anlaşması yaptığı bir hiper ölçekleyicidir.
3. **Tedarikçinin anahtar yönetimi.** Tedarikçi bulutundaki bekleyen veriyi koruyan şifreleme anahtarları. Çoğu SaaS düzenlemesinde bunları tedarikçi tutar. "Müşteri tarafından yönetilen anahtarlar" seçeneği zaman zaman bir üst katman seçeneği olarak sunulur; bu durumda anahtarlar yine tedarikçinin IAM'ının çağırabildiği bir hiper ölçekleyici KMS'tedir.
4. **Tedarikçinin alt işlemcileri.** Tedarikçinin kullandığı ve verilerinizi ya da bu verilerden türetilen meta verileri iletebilen veya saklayabilen üçüncü taraf hizmetler (CDN, gözlemlenebilirlik, faturalama, müşteri destek araçları).

Bu dört katmanın her biri, Article 21(2)(d) tedarikçi kaydınızdaki bir girdidir. Her birinin kendine özgü olay geçmişi, kendine özgü ihlal yayılma alanı ve kendine özgü sözleşme müzakere yüzeyi vardır. SaaS tedarikçisiyle yenileme yaptığınızda dördünü de örtülü olarak yenilemiş olursunuz; çünkü müzakere edebildiğiniz tek sözleşme SaaS tedarikçisinin sözleşmesidir.

Blackbaud olayı, katman 1 (tedarikçi uygulaması) üzerinden yayılan ve katman 3 (tedarikçinin anahtar yönetimi; bu durumda etkilenen veritabanında kiracı başına ayrım olmaksızın sunucu taraflı anahtarlar) nedeniyle her müşteriye görünür hale gelen bir katman 2 ihlaliydi (tedarikçi bulutu). Blackbaud'un alt işlemcileri ihlal vektörü değildi; ancak müşteriler, kayıtlarında yer vermedikleri üç alt işlemciden haberdar oldu.

## Blackbaud, Druva Tarzı Anahtar Yönetimi ve Zincirleme Kırılma Örüntüsü

Blackbaud'un SEC dosyalarından NIS2 okuması açısından önem taşıyan üç ayrıntı var.

Birincisi, Blackbaud; ihlal hedefi olan yedekleme ortamı dahil müşteri verileri için şifreleme anahtarlarını tutuyordu. Müşteri tarafından yönetilen anahtarlar seçeneği sunulmuyordu. Olay sonrası SEC davasında bu durum, Blackbaud'un sözleşmelerinin buna izin vermesi nedeniyle bir kontrol açığı olarak nitelendirildi; ihlal sayılmadı. Aynı düzenlemeye Article 21(2)(d) çerçevesinde NIS2'nin bakışı daha serttir; çünkü müşteri, görünürlüğünün olmadığı bir kontrolün riskini anlamlı biçimde değerlendiremez.

İkincisi, ihlal canlı veritabanından daha eski yedekleme verilerini etkiledi. Canlı verileri Blackbaud'un birincil sistemlerinden silinmiş olan müşteri kuruluşlar, yedekleme ortamı üzerinden hâlâ veri açığıyla karşılaştı. Bu, zincirleme kırılma örüntüsüdür: bir tedarikçi ihlali, müşterinin kapsam dışında olduğunu düşündüğü geçmişe ait verilere ulaşır.

Üçüncüsü, 13.000'den fazla müşteri kuruluş ihlal bildirimi aldı. Bunların büyük bölümü, yanıt verecek operasyonel kapasitesi olmayan, DR planı bulunmayan, devreye alabilecekleri ikinci bir yedekleme tedarikçisi olmayan küçük sivil toplum kuruluşları ve okullardı. Tedarikçinin olayı, bu anlamda onların olayına dönüştü.

Druva tarzı modern bir SaaS yedeklemesinde mimari bazı noktalarda daha iyidir: kiracı başına anahtar ayrımı daha yaygın, BYOK üst katlarda mevcuttur. Ancak dört katmanlı veri yolu aynıdır. Tedarikçi uygulaması, tedarikçi bulutu (genellikle AWS), anahtar yönetimi (kimi zaman tedarikçide, kimi zaman müşterinin KMS'inde BYOK ile, kimi zaman hibrit), alt işlemciler. Herhangi bir katmandaki ihlal tüm müşterilere eş zamanlı ulaşır; çünkü tüm müşterilerin verisi sınırın aynı tarafındadır.

Bu yapısal bir argümandır. Druva'ya yönelik bir saldırı değil. Druva, Blackbaud'dan daha sıkı bir gemi yönetiyor. Argüman şu: SaaS tasarımlı herhangi bir yedekleme ürününün yapısı, katman 2 ve katman 3 ihlallerini müşterinin Article 21(2)(d) kapsamında anlamlı biçimde yerine getiremeyeceği bir yükümlülüğe dönüştürür.

## Self-Hosting Dört Katmanın Üçünü Çöküştürüyor

Rediacc farklı kurulmuştur. Tam mimari [Mimari sayfasında](/tr/docs/architecture) belgelenmiştir; ancak tedarik zinciri açısından ilgili biçim, SSH üzerinden konuşan iki ikili dosyadır:

- `rdc`, operatörün iş istasyonunda çalışır. `~/.config/rediacc/` altındaki düz bir JSON yapılandırma dosyasını okur, SSH üzerinden operatörün kendi makinelerine bağlanır ve komutları iletir.
- `renet`, root yetkisiyle operatörün kendi sunucusunda çalışır; LUKS2 şifreli disk imajlarını, izole Docker daemon'larını ve ters proxy'yi yönetir.

Operatör, yedekleme, geri yükleme veya fork işlemi yapmak için Rediacc şirketinin altyapısına hiçbir zaman giriş yapmaz. Veri yolunda Rediacc şirketinin bulutu yoktur. Deponun LUKS2 kimlik bilgisi, operatörün yerel yapılandırma dosyasında (mod `0600`) saklanır; sunucuda asla bulunmaz, Rediacc'a asla gönderilmez. Veri yolu şöyle görünür:

1. **Operatör iş istasyonu.** `rdc`'yi çalıştırır. LUKS2 kimlik bilgisini tutar.
2. **Operatörün kendi sunucusu.** `renet`'i çalıştırır. LUKS2 şifreli depoları tutar.
3. **Operatörün kendi yedek hedefi.** Herhangi bir rclone uyumlu depolama (S3, B2, OneDrive, şirket içi MinIO). Şifreli birimleri alır.

Katman 4 yoktur. Rediacc şirketi, deneysel [Bulut adaptörünü](/tr/docs/architecture) etkinleştirmemiş hiçbir operatör için alt işlemci değildir. Self-hosted operatörler için Rediacc şirketiyle ilişki, bir veri işleme sözleşmesi değil, bir yazılım lisansıdır.

Bu, veri yolu argümanıdır ve bir tedarikçi kaydı görüşmesinde öne çıkarılması gereken doğru argümandır. Bir SaaS rakibi müşteri tarafından yönetilen anahtarlar sunabilir (ve modern olanların çoğu sunar). Hiçbir SaaS rakibi "biz alt işlemci değiliz" diyemez.

Veri yolu argümanının ardından gelen ikinci nokta anahtar yönetimidir. Rediacc'ta LUKS2 kimlik bilgisi, operatörün yapılandırma dosyasındadır; hepsi bu. Operatörün kimlik bilgisini kaybetmesi durumunda Rediacc şirketinin çalıştırabileceği bir anahtar emanet servisi veya kurtarma servisi yoktur. Bu aynı zamanda [sıfır bilgi yapılandırma deposu](/tr/docs/config-storage) için önerilen mimaridir: şifreleme anahtarı, bir parola anahtarı PRF uzantısından istemci tarafında türetilir ve sunucu opak bloblar saklar. Sunucu SSH anahtarlarını, LUKS2 kimlik bilgilerini, IP adreslerini veya düz metin yapılandırma değerlerini okuyamaz. Erişim tokenının döndürülmesi sunucuya geriye dönük okuma yetkisi vermez.

Article 21(2)(h) (şifreleme) açısından bu önemlidir. Article 21(2)(d) (tedarik zinciri) açısından daha da önemlidir; çünkü Rediacc şirketinden operatörün verilerine giden son mantıksal erişim yolunu kaldırır.

## Self-Hosting'in Çöküştürmediği Şeyler

Self-hosting tedarikçi listesini kaydırır, silmez. Bir denetçinin hâlâ soracağı üç şey:

**1. Hâlâ tedarikçileriniz var, sadece farklı olanlar.** Donanım tedarikçisi (Hetzner, Hostinger, OVH, kendi ortak yerleşim alanınız, kendi çıplak metal sunucunuz). Hiper yönetici (KVM, VMware). İşletim sistemi (Debian, Ubuntu, RHEL). Konteyner kayıt defteri (Docker Hub, GHCR, özel kayıt defteriniz). Hizmetlerinizin çektiği temel imajlar. Bunların her biri bir Article 21(2)(d) girdisidir. Self-hosting tedarikçi listesini kaydırır, silmez.

**2. Rediacc'ın henüz ISO 27001, SOC 2 veya BSI C5 belgesi yok.** Bunlar yol haritasında yer alıyor, elde mevcut değil. Sertifikaları bir geçiş mekanizması olarak kullanan bir tedarik ekibi için bu gerçek bir sürtüşmedir. Savunulabilir karşı argüman bu yazının savunduğu argümandır: veri yolu argümanı, söz konusu sertifikaların onayladığı şeylerin büyük bölümünün (tedarikçi bulut güvenlik kontrolleri, tedarikçi personel erişim yönetimi, tedarikçi alt işlemci yönetimi) kapsam dışında olduğu anlamına gelir; çünkü Rediacc şirketi veri yolunda değildir. Bu argümanın, sertifikaların alıcının ihtiyacı olduğu durumlarda bir ikame olarak değil, dikkatli ve savunulabilir biçimde öne sürülmesi gerekir.

**3. GRC katmanı hâlâ sizin sorumluluğunuzdadır.** Rediacc, operatöre 70'ten fazla olayı kapsayan zincir hashli bir denetim günlüğü sunar (`rdc audit verify` zinciri baştan sona doğrular). Size tedarikçi kaydı, kontrol çerçevesi veya kanıt toplama iş akışı sağlamaz. Bunlar hâlâ Drata, Vanta, OneTrust veya Avrupa'dan çıkan ürünlerden gelir. Yardımcı [gerçek maliyet yazısı](/tr/blog/nis2-the-real-bill), bu tamamlayıcılığın maliyet biçimini ayrıntılı olarak ele alır.

## Artık Müzakere Etmek Zorunda Olmadığınız DPA

Bunu somutlaştırmak için, anonimleştirilmiş gerçek bir tedarik görüşmesinden "öncesi ve sonrası" kayıt satırı: Alıcı, Ek II kapsamında "önemli kuruluş" olarak sınıflandırılmış, 280 çalışanlı bir Alman üretim şirketi. Yedekleme için orijinal tedarikçi kaydı şöyle görünüyordu:

| Alan | Önce |
|---|---|
| Tedarikçi | Acme Backup SaaS |
| Katman | Kritik |
| İşlenen veri | Üretim veritabanı, müşteri KVK verileri, finansal kayıtlar |
| Alt işlemciler | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Sözleşme durumu | DPA Ocak 2023'te imzalandı, SCC'ler eklendi, önlemler takvimi en son Ocak 2025'te gözden geçirildi |
| Anahtar yönetimi | Tedarikçi yönetimli (BYOK seçeneği mevcut katmanda sunulmuyor) |
| Çıkış planı | "Tedarikçi, sözleşme feshinden itibaren 30 gün içinde CSV formatında veri dışa aktarımı sağlamayı kabul eder" |
| Son değerlendirme | 2025-Q1, anahtar yönetiminde açık not edildi, yenilemeye ertelendi |

Hetzner üzerinde Rediacc'a geçildikten sonra:

| Alan | Sonra |
|---|---|
| Tedarikçiler | (1) Rediacc OÜ, yazılım lisansı; (2) Hetzner, IaaS |
| Katman | (1) Kritik olmayan (veri katmanı yok); (2) Kritik (veri katmanı, müşteri kontrolünde) |
| İşlenen veri | (1) Hiçbiri; (2) Şifreli birimler, anahtarları müşteri tutar |
| Alt işlemciler | (1) Self-hosted için hiçbiri; (2) Yalnızca Hetzner dahili, kendi DPA'larında listelenmiş |
| Sözleşme durumu | (1) Yazılım lisansı, DPA gerekmiyor; (2) Hetzner DPA + SCC'ler zaten mevcut |
| Anahtar yönetimi | Müşteri (LUKS2 kimlik bilgisi operatör yapılandırmasında, sunucuda değil) |
| Çıkış planı | "rdc repo backup pull ile herhangi bir rclone uyumlu hedeften. Birimler LUKS2 şifreli; operatör kimlik bilgisini tutar." |
| Son değerlendirme | (2) mevcut IaaS incelemesiyle kapsanmış |

Bir yerine iki kayıt girişi. Kritik katman girişi, alıcının zaten DPA ve test edilmiş çıkış planı mevcut olan IaaS sağlayıcısı içindir; çünkü IaaS, çoğu ekibin nasıl yöneteceğini bildiği bir ilişkidir. Rediacc girişi, veri işleyici değil yazılım lisansı olduğu için kritik olmayan olarak sınıflandırılmıştır.

Bu, bir CISO'nun tedarik maliyeti elektronik tabloda benzer görünse bile veri katmanındaki SaaS bağımlılıklarını azaltmak istemesinin yapısal nedenidir. Kayıt girişi aynı biçimde değildir.

## Tedarik Kontrol Listesi

2026 satış döneminde "NIS2-hazır" iddiasındaki herhangi bir tedarikçiye altı soru:

**1. Bekleyen verilerimizin şifreleme anahtarı nerededir?** Yanıt "HSM'imizde" veya "IAM aracılığıyla çağırabildiğimiz müşterinin KMS'inde" ise tedarikçi anahtar yönetimi zincirinizin içindedir. Yanıt "yerel yapılandırma dosyanızda, altyapımızda asla değil" ise değildir.

**2. Şirketinizdeki kim, yasal koşulları göz ardı ederek verilerimizi teknik olarak okuyabilir?** "Kim yetkili" değil, "kim isteseydi okuyabilirdi, denetim günlüğü kapalıysa bile" sorusu. Yanıt sıfırdan büyükse bu, içeriden tehdit değerlendirmeniz için kitledir.

**3. Geri yükleme gerçek bir üretim kopyasına karşı mı test ediliyor, yoksa sentetik test verisine karşı mı?** Article 21(2)(c) ve (e) birlikte okunduğunda yedeklemenin gerçekten geri yükleme yapmasını gerektiriyor. Yalnızca sentetik verilere karşı doğrulayan bir tedarikçi, kurtarmayı değil yedek dosya bütünlüğünü doğruluyor. (Bu konuda daha fazla bilgi için [sürekli etkinlik değerlendirmesi](/tr/blog/nis2-effectiveness-without-theatre) üzerine yardımcı yazıya bakın.)

**4. Denetim iziniz her eylemin arkasındaki aktör türünü, insan mı ajan mı, kaydediyor mu?** AI ajan etkinliği, denetim günlüğünün en hızlı büyüyen kategorisidir. 2026'da insanı ajandan ayırt etmeyen bir denetim günlüğü, 2027'de açık olarak görünecektir.

**5. Meta veri dahil verilerimize mantıksal erişimi olan her alt işlemciyi listeleyin.** "Mantıksal erişim" doğru ifadedir. "Meta veri dahil mantıksal erişim" daha iyi ifadedir; çünkü yalnızca meta veri erişimi, faturalama, gözlemlenebilirlik ve müşteri destek alt işlemcilerinin genellikle sahip olduğu şeydir ve yük şifreli olsa bile hassas yapının sızdırılması için yeterlidir.

**6. 2027'de AB dışı bir alıcı tarafından satın alınırsanız çıkış planınız nedir?** GDPR yeterlilik çerçevesi, Cloud Act ve FISA 702 hepsi değişken hedeflerdir. Bir tedarikçinin bugünkü veri ikameti iddiası, üç yıl sonrasının garantisi değildir. Alıcının sorusu, tedarikçinin sahipliği değişirse veri yoluna ne olacağıdır.

Altının tamamını temiz yanıtlayan bir tedarikçi nadirdir. Altıdan dördünü yanıtlayan ve diğer ikisini açıkça kabul eden bir tedarikçi, altısına da güvenle yanıt verenden daha güvenilirdir. Güvenilirlik sinyali, çözülmeyeni adlandırma isteğidir.

## Sonraki Yenileme Döngüsü İçin Anlamı

Önümüzdeki on iki ay içinde bir yedekleme veya DR yenileme sürecine girecekseniz ve Article 21(2)(d) tedarik puan kartındaysa üç somut adım:

1. Mevcut tedarikçinizin dört katmanlı veri yolunu bir beyaz tahtaya çizin. Üçüncü alt işlemciyi adlandıramıyorsanız, NIS2'den önce var olan bir kayıt tamlık sorununuz var ve yenileme bunu düzeltmek için doğru andır.
2. Yukarıdaki altı soruluk kontrol listesini mevcut tedarikçinize karşı çalıştırın. Yanıtları DPO'nuza ve denetçinize gönderin ve açıkların kabul edilip edilmediğini sorun. Açıklar katman 3 (anahtar yönetimi) veya katman 4 (numaralandırmadığınız alt işlemciler) içeriyorsa bu, kaldıraç noktasıdır.
3. Self-hosted bir kontrol düzlemiyle alternatif bir tedarikçi kaydının nasıl görüneceğine bakın. Lisans maliyetlerini değil, kayıt girdilerini karşılaştırın. Lisans maliyetleri iki kat içinde benzerdir; kayıt girdileri farklı biçimdedir. ([NIS2 yığınının yapısal maliyeti](/tr/blog/nis2-the-real-bill) üzerine yardımcı yazı, neyin çöküştürüldüğünü ve neyin kaldığını ayrıntılı olarak ele alıyor.)

Kısa listenizde biz alternatifisek, teklif somuttur. Tedarikçi anketinizi bize gönderin. Dağıtılmış bir örneğe karşı, açıklar dahil sorularınızın gerçek yanıtlarıyla dolduracağız. Evrak göndermeden önce mimariyi gözden geçirmek isterseniz, kurucu ile 30 dakikalık bir mimari inceleme rezervasyonu yapabiliriz. Savunulabilir bir kayıt girdisine giden yol parlak bir broşür değildir. Rahatsız edici olanlar dahil, yanıtlardır.

Rediacc'ın NIS2 maddelerine genel olarak eşlenmesi için [NIS2 ve DORA](/tr/docs/legal-nis2-dora) sayfasına bakın. Daha geniş uyumluluk çerçevesi için [Uyumluluk Genel Bakışı](/tr/docs/legal-overview), [Veri Egemenliği](/tr/docs/legal-data-sovereignty) ve [Şirket İçi Kurulum](/tr/docs/on-premise) sayfalarına bakın.
