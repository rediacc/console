---
title: "İlk NIS2 Denetim Döngüsünde Alıcıların Bize Söyledikleri"
description: "Orta ölçekli temel kuruluşların 2026'da sessiz sedasız bir araya getirdiği beş araçlık uyum yığını, kendi altyapınızı barındırmanın hangi kalemleri ortadan kaldırdığı ve hangi kalemlerin her halükarda sizde kaldığı."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - buyer-guide
  - compliance
  - cost
  - mid-market
featured: false
language: tr
sourceHash: "95f07c80c1d91055"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

**Özet:** Alman dalgası için ilk dönem NIS2 denetimleri artık geride kaldı. Aralık ayından bu yana görüştüğümüz alıcıların tamamı aynı yığının bir versiyonunu anlatıyor: beş araç, üç sözleşme, iki örtüşen denetim günlüğü ve kapatamadıkları bir boşluk. Bu yazı, o konuşmanın yapısal versiyonu. Kendi altyapınızı barındırmanın hangi kalemleri ortadan kaldırdığı, hangilerinin bütçenizde her koşulda kaldığı ve 2026 yenileme döngüsünde doğru çerçevenin "Veeam'dan ucuz" değil "daha az kayıt girişi, daha az örtüşme, aynı boşluklar dürüstçe adlandırılmış" olduğu.

- Frontier Economics, AB genelinde yıllık NIS2 uyum maliyetini EUR 31,2 milyar olarak hesapladı. Orta ölçekli kuruluşlardaki bireysel gerçeklik ise şu: "Zaten bir güvenlik yığınımız vardı; NIS2 eksik olanı gün yüzüne çıkardı."
- Beş araçlık yığın: yedekleme, DR, maskeleme veya test verisi, sızma testi sözleşmesi, GRC. Her biri işin bir bölümünü yapıyor. Hiçbiri tamamını kapsıyor.
- Rediacc, yedekleme, DR, test verisi olarak fork ve anlık geri yüklemeyi tek bir kontrol düzlemi ve tek bir denetim günlüğüyle birleştiriyor. GRC'yi, sertifikaları, eğitimi, kurumsal MFA'yı, sızma testini veya SIEM ve SOC'u birleştirmiyor.
- "Sizde kalan" tablosu bu yazının yapısal çıktısı. Bunu okuyup "Rediacc, Drata'nın yerini alır" sonucuna varan bir alıcı denetçisini hayal kırıklığına uğratacak.

Aralık 2025'te Almanya'daki BSI, NIS2 kapsamında olduğunu düşündüğü ancak kayıt yaptırmamış kuruluşlara 47 resmi uyarı gönderdi. Fransa'daki ANSSI paralel bir çalışma başlattı. İtalya'daki ACN, kayıt dışı olduğunu düşündüğü yaklaşık 2.000 kuruluşun peşine düştü. Orta ölçekli temel ve önemli kuruluşların ilk dalgası, ilk NIS2 denetim döngüsüne girdi.

O tarihten bu yana bunlardan yaklaşık otuzuyla görüştük. Farklı sektörler, farklı ölçekler; çoğunlukla Almanya ve İtalya, bir kısmı Hollanda ve Estonya. Konuşmalar birbirine benziyor. Her ekibin bir yedekleme satıcısı, test edilmiş olup olmadığı belirsiz bir DR planı, yarısı doğru bir test ortamı hikayesi ve NIS2 henüz kimsenin gündeminde yokken onaylanmış bir satın alma bütçesi var.

Bu yazı, o konuşmaların yapısal versiyonu. Bir CFO veya alıcının 2026'da gerçekte neye imza attığı, kendi altyapınızı barındırmanın faturayı nasıl değiştirdiği ve dürüst artık maliyetin nasıl göründüğü. Kasıtlı olarak bir TCO hesap makinesi değil. Konuştuğumuz alıcıların başka bir tabloya ihtiyacı yok; paranın nereye gittiğinin ve hangi kalemlerin örtüştüğünün yapısal haritasına ihtiyaçları var.

"Kendi altyapınızı barındırmak önemlidir" iddiasının arkasındaki tedarik zinciri risk argümanını görmek istiyorsanız bkz. [Article 21(2)(d) üzerine eşlik yazısı](/tr/blog/nis2-supply-chain-self-hosted). Yıllık sızma testlerinin neden artık yeterli olmadığına ilişkin SRE düzeyindeki argümanı görmek istiyorsanız bkz. [sürekli etkinlik üzerine eşlik yazısı](/tr/blog/nis2-effectiveness-without-theatre). Bu yazı ikisi arasında, bütçe konuşmasında duruyor.

## Makro rakam ve ne anlama gelip gelmediği

Frontier Economics'in 2024 yılında Avrupa Komisyonu için hazırladığı çalışma, AB genelinde NIS2 uyumunun doğrudan yıllık maliyetini EUR 31,2 milyar olarak tespit etti. Bu rakam sıkça alıntılanıyor; aynı zamanda sıkça yanlış yorumlanıyor.

EUR 31,2 milyar, yaklaşık 160.000 temel ve önemli kuruluşu kapsıyor. Kuruluş başına ortalama EUR 150.000 ile 250.000 arasında gerçekleşiyor; sektör ve ölçek bu aralığın büyük bölümünü belirliyor. İmalat veya sağlık sektöründe 250 çalışanlı orta ölçekli bir temel kuruluş bu aralığın üst ucunda. Veriye daha az bağımlı bir sektörde 60 çalışanlı önemli bir kuruluş ise alt ucunda.

ENISA'nın kendi uygulama maliyeti rehberi (Uygulama Yönetmeliği (EU) 2024/2690'ın Ek IV'ü), Frontier rakamıyla örtüşüyor ancak farklı biçimde kırıyor: araçlara yaklaşık yüzde 35-45, personel ve eğitime yüzde 30-40, sertifikasyon ve denetime yüzde 15-20, olay müdahale taahhütleri ve yönetilen hizmetlere yüzde 5-10.

2026 bütçesini imzalayan bir CFO için bu ne anlama geliyor: araç katmanı, mevcut duruma bağlı olarak orta ölçekli kuruluşlar için yılda yaklaşık EUR 50.000 ile EUR 120.000 arasında. Yürüyeceğimiz yer burası.

Bu ne anlama gelmiyor: NIS2'ye hazır bir paket satın almak sorunu çözmüyor. Personel eğitimi ve sertifikasyon bütçeleri, çoğu ekip için araç bütçesinden büyük; hiçbir araç satıcısı bunları düşürmüyor. Yüzde 50 NIS2 maliyet indirimi iddia eden bir satıcı sunumu neredeyse her zaman hesabı yalnızca araç kalemine karşı yapıyor, tam program maliyetine karşı değil.

## Orta ölçekli ekiplerin sessizce bir araya getirdiği beş araçlık yığın

Otuz alıcı görüşmesinde yığın, vakaların yüzde 90'ında aynı görünüyor. Her kategoride bir ya da iki adlandırılmış satıcıyla birlikte beş kategori. Kategori etiketleri sabit; satıcı tercihleri değişiyor.

**1. Yedekleme satıcısı.** En yaygın yanıt Veeam Data Platform Foundation veya Premium. Daha küçük ölçekte Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect. Orta ölçekli kuruluşlar için yıllık maliyet EUR 15.000 ile EUR 60.000 arasında. Genellikle bütçedeki en eski kalem; NIS2'den yıllarca önce var.

**2. DR merkezi veya DR hizmet olarak.** Ya ikincil bir bulut bölgesi ve bir çalışma kitabı, ya Veeam Cloud Connect veya Rubrik Cloud Vault kiracılığı, ya da yönetilen bir DR sağlayıcısıyla sözleşme. Yıllık maliyet EUR 8.000 ile EUR 35.000. Pratikte nadiren test ediliyor; çalışma kitabı genellikle operasyonellikten çok isteksel.

**3. Test verisi veya veri maskeleme aracı.** Kurumsal varsayılan Delphix (şimdi Perforce DevOps Data). Tonic.ai, Redgate Test Data Manager, zaman zaman özel yapım bir rsync-ve-maskeleme betiği. Lisanslı seçenekler için yıllık maliyet EUR 25.000 ile EUR 90.000. Görüşmelerimizde ekiplerin büyük çoğunluğu bu kaleme sahip değil; yeterince iyi olduğunu umdukları bir test ortamına sahipler. Onu bütçeye sokan şey Article 21(2)(e) denetim konuşması oluyor.

**4. Sızma testi sözleşmesi.** Bir güvenlik test firmasıyla tutucu anlaşma veya Pentera ya da Horizon3.ai gibi otonom bir platform. Otonom araçlar için yıllık maliyet EUR 15.000 ile EUR 50.000, insan odaklı çalışmalar için EUR 20.000 ile EUR 80.000. Çoğu ekipte bu var. Çoğu ekip yılda bir ya da iki kez yapıyor.

**5. GRC platformu.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. En küçük ekiplerde zaman zaman evde yapılmış bir tablo. Yıllık maliyet EUR 12.000 ile EUR 60.000. Tedarikçi kaydı, kontrol çerçevesi tasdiki, kanıt toplama ve (giderek daha fazla) SOC 2 veya ISO 27001 denetim desteği için kullanılıyor.

Personel ve eğitim öncesinde beş kalem, üçten beşe adlandırılmış satıcı; tipik olarak yılda EUR 75.000 ile EUR 295.000. Varyans geniş ama yapı tutarlı.

Beş sözleşme genellikle birbirleriyle konuşmuyor. Denetim günlükleri birleştirilmiş değil. Çıkış planları ayrı yazılıyor. Satıcı incelemeleri ayrı yapılıyor, bazen farklı satın alma liderleri tarafından. NIS2'nin rahatsız edici kıldığı yapısal şekil bu.

## Örtüşmeler nerede

Yığındaki her kategori en az bir diğeriyle örtüşüyor.

**Yedekleme DR ile örtüşüyor.** Modern yedekleme satıcılarının tamamı DR yetenekli olduklarını iddia ediyor. Cloud Connect ile Veeam Data Platform bir DR ürünü. Cloud Vault ile Rubrik bir DR ürünü. İki kalem çoğunlukla aynı satıcıda bitişik yetenekler için ödeme yapıyor. Kalemleri tarihsel olarak birleştirmemiş alıcıların operasyonel nedenleri vardı (ayrı ekipler, ayrı SLA'lar); NIS2'nin "kurtarma için tek doğruluk kaynağı" beklentisi altında bu gerekçe zayıflıyor.

**Yedekleme test verisiyle örtüşüyor.** Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles hepsinin test için bir tür monte edilebilir yedekleme sunuyor. Tam Delphix alternatifleri değiller (maskeleme katmanı ayrı, veritabanı entegrasyonu daha yüzeysel) ama pek çok test verisi kullanım senaryosunda yedekleme aracı cevabın yarısı. Çoğu ekip bunu fark etmiyor.

**Sızma testi otonom test ile örtüşüyor.** Tutucu tabanlı insan sızma testi ile Pentera tarzı sürekli test bazen alternatif, bazen tamamlayıcı olarak sunuluyor. Pratikte her ikisine sahip bir alıcı bitişik yetenek için iki kez ödüyor. Hiçbirine sahip olmayan bir alıcının Article 21(2)(f) boşluğu var.

**GRC her şeyle örtüşüyor.** Drata yedekleme, DR, kimlik, güvenlik açığı yönetimi, eğitim ve olay müdahalesiyle entegrasyon iddia ediyor. Entegrasyonların derinliği değişiyor. Bir yedekleme aracına yüzeysel entegrasyonu olan bir GRC platformunun ürettiği uyum kanıtı, yedekleme aracının kendi kanıtıyla aynı şey değil; denetçiler hangisinin kanonik olduğunu sormaya başlıyor.

Örtüşmeler israf değil. Bunlar NIS2 birleştirme sorusunu yapısal hale getirmeden önce on yılda bir araya getirilen bir yığının sonucu.

## Boşluklar nerede

Boşluklar örtüşmelerden daha ilginç, çünkü boşluklar NIS2'nin gün yüzüne çıkardığı şey.

**Gerçek üretim verilerine karşı yama doğrulaması.** Beş kategorinin hiçbiri bunu iyi yapmıyor. Yedekleme araçları yedeği monte ediyor; monte edilen ortam kurtarılmış yedek, mevcut üretim değil. Test verisi araçları üretim verilerini maskeliyor; maskelenmiş ortam şekil olarak gerçekçi ama yapılandırma deltalarını yitiriyor. Sızma testi sözleşmeleri işaret edilen yeri test ediyor, ki bu vakaların yüzde 90'ında test ortamı. "Araçlarımız var" ile "bir CVE yamasını mevcut üretim eşdeğeri ortamda bir saatten kısa sürede test edebiliyoruz" arasındaki boşluk gerçek ve yapısal.

**Sürekli etkinlik değerlendirmesi.** Çoğu ekibin yaptığı yıllık kadans. Article 21(2)(f) daha sık bir şey istiyor. Beş kategorinin hiçbiri varsayılan olarak haftalık veya iki haftada bir kanıt üretmiyor. Alıcı ya özel tatbikatlar yapıyor (nadir, pahalı) ya da yıllık kadansı kabul edip denetçinin bunu kabul etmesini umuyor (giderek etmiyor).

**Tedarik zinciri kaydının yığışması.** Beş satıcının her biri kendi kayıt girişi. Her biri kendi DPA'sını, SCC'sini, alt işlemci listesini ve çıkış planını taşıyor. Kayıt, personel eğitim araçları, kimlik araçları, gözlemlenebilirlik araçları ve IaaS eklenmeden önce beş birinci katman girişi içeriyor. NIS2 açısından tedarik zinciri konuşması, güvenlik konuşması kadar kayıt yönetimi konuşması. (Yapısal argüman için bkz. [tedarik zinciri yazısı](/tr/blog/nis2-supply-chain-self-hosted).)

**Article 23 raporlama iş akışı.** 24 saatlik erken uyarı, 72 saatlik bildirim ve bir aylık rapor, beş kategorinin hiçbiri tarafından otomatik olarak üretilmiyor. Bunlar için bir SIEM, bir SOC (dahili veya dış kaynaklı) ve ulusal CSIRT'e nasıl dosyalanacağını bilen bir kişi gerekiyor. Küçük ekiplerin çoğu buna sahip değil. İlk olay acı öğrenme deneyimi oluyor.

## Rediacc'ın birleştirdiği şeyler

Rediacc, kendi altyapısını barındıran yapılar için beş kategorinin dördünün temel kapasitesini tek bir denetim günlüğüyle tek bir kontrol düzlemine indirgiyor.

**Yedekleme:** sistemd zamanlayıcılarıyla planlanan, rclone üzerinden çoklu hedefli sıcak (çökme tutarlı BTRFS anlık görüntüsü, kesinti yok) ve soğuk (uygulama tutarlı durdur-anlık görüntüle-başlat) yedekleme stratejileri. LUKS şifreli birimler; kimlik bilgisi operatörde; Rediacc şirketi hiçbir zaman düz metin veri görmüyor. Operasyonel şekil için bkz. [Backup & Restore](/tr/docs/backup-restore) ve [Cross Backup Strategy](/tr/docs/cross-backup).

**DR:** yedeklemeyle aynı ilkel, artı makineler arası veri taşımak için `rdc repo migrate`, artı paralel bir makinede kurtarılmış durumun hızla ayağa kaldırılması için fork ilkeli. DR merkezi başka bir Hetzner makinesi, bir OVH makinesi, bir yerel raf; SSH'ın ulaştığı her yer olabilir. Veri yolunda DR satıcısı bulutu yok.

**Test verisi ve tam yığın klonlama:** BTRFS reflink tabanlı fork, depo boyutundan bağımsız sabit süre, tam yığın (veri, yapılandırmalar, konteyner durumu, servisler). [PocketOS testimizde](/tr/blog/i-tested-rediacc-against-the-pocketos-incident) 128 GB deposunu fork etmek 7,2 saniye. Fork mevcut üretim; sadeleştirilmiş bir test ortamı değil. Bkz. [Risk-Free Upgrades](/tr/docs/risk-free-upgrades).

**Anlık geri yükleme:** herhangi bir rclone hedefinden `rdc repo backup pull` ile yeni bir fork'a; üst deponun wildcard sertifikasıyla kapsanan fork'a özgü bir alt alan adı altında ayağa kaldırılır. DNS karmaşası yok, sertifika dansı yok.

**Birleşik denetim günlüğü:** kontrol düzleminin tamamını kapsayan 70'ten fazla olay türü (kimlik doğrulama, API token'ları, yapılandırma yazmaları, depo yaşam döngüsü, yedekleme, senkronizasyon, terminal oturumları, makine operasyonları). Operatörün iş istasyonunda hash zinciriyle bağlı; `rdc audit verify` uçtan uca bütünlüğü doğruluyor.

250 çalışanlı orta ölçekli bir temel kuruluş için birleştirme, dört adlandırılmış satıcıdan (yedekleme, DR, test verisi, anlık geri yükleme) bire iniyor. Tek lisans, tek denetim günlüğü, tek yükseltme kararı seti, tek kayıt girişi.

Beşinci kategori GRC birleştirilmiyor. Oraya geri döneceğiz.

## Bütçenizde her koşulda kalan kalemler

Bu bölüm, yazının geri kalanının dürüst olup olmadığını belirliyor. İki sütunlu tablo:

| Rediacc'ın Kaldırdığı | Sizde Kalan, Kalem Kalem |
|---|---|
| Yedekleme satıcısı lisansı | GRC platformu (Drata, Vanta, OneTrust, AuditBoard, DataGuard) tedarikçi kaydı, kontrol çerçevesi tasdiki, kanıt toplama ve SOC 2 veya ISO 27001 denetim desteği için |
| DR merkezi sözleşmesi veya DR hizmet olarak kiracılığı | Sertifikasyon denetim maliyetleri (ISO 27001, SOC 2, gerekiyorsa BSI C5; Rediacc henüz sertifikalı değil, bu nedenle o maliyeti siz taşıyorsunuz) |
| Test verisi veya maskeleme aracı lisansı | Personel eğitimi ve güvenlik farkındalığı bütçesi (NIS2 Article 21(2)(g)) |
| Yedekleme satıcısında anlık kurtarma lisansı | Daha geniş kurumsal MFA çözümü; Rediacc portalda TOTP'ye sahip, kurumsal MFA platformuna değil |
| | Sızma testi sözleşmesi veya otonom test platformu; Rediacc hedef ortamı sağlıyor, test yetkinliğini değil |
| | Article 23 tespiti ve raporlaması için SIEM ve SOC; Rediacc adli kalitede artefaktlar sağlıyor, operasyonel raporlama katmanını değil |
| | IaaS sağlayıcısı (Hetzner, OVH, kolosyonunuz, bare metal'ınız); Rediacc altyapının üzerinde çalışıyor, yerine geçmiyor |
| | Programı yürüten personel. Rediacc bir araç katmanı, güvenlik ekibi değil |

Tablonun sağ tarafı sol tarafından uzun. NIS2'nin gerçek maliyetinin dürüst şekli bu. Yedekleme-DR-test verisi örtüşmesini kaldırmak gerçek para ve gerçek kayıt girişleri tasarrufu sağlıyor; bir güvenlik programını SaaS aboneliğine dönüştürmüyor.

Bunu okuyup "Drata'nın yerini Rediacc alabilir" sonucuna varan bir alıcı denetçisini hayal kırıklığına uğratacak. Doğru okuma şu: Rediacc'ın mümkün kıldığı veri düzlemi satıcısı birleştirmesi, GRC araçlarının yapamadığı şey; GRC araçlarının yaptığı kayıt ve kanıt çalışması ise Rediacc'ın yapmadığı şey. İkisi tamamlayıcı.

Kapasitelerin NIS2 maddelerine genel haritalanması için bkz. [NIS2 and DORA](/tr/docs/legal-nis2-dora). Daha geniş mimari çerçeve için bkz. [Compliance Overview](/tr/docs/legal-overview). Rediacc tarafındaki ticari ayrıntılar için bkz. [Subscription & Licensing](/tr/docs/subscription-licensing).

## Yapısal bir referans senaryo, sayısal değil

250 çalışanlı bir Alman imalat şirketini ele alalım. Ek II kapsamında "önemli kuruluş" sınıflandırması. Üretim verisi 4 ila 6 sunucuda, büyük ölçüde kendi barındırdığı, bir iki SaaS araçla (CRM, bordro). Yıllık EUR 80 milyon gelir. Mevcut 3 kişilik güvenlik ekibi.

**Önce**, veri düzlemi yığınları:

- Veeam Data Platform Foundation, EUR 24.000/yıl
- DR için Veeam Cloud Connect, EUR 12.000/yıl
- Test verisi için evde yapılmış bir rsync-artı-pg_dump düzeni; lisansta ücretsiz ama her iki haftada bir SRE'ye yarım güne mal oluyor
- Yıllık sızma testi, EUR 22.000
- GRC için Drata, EUR 18.000/yıl

Beş sözleşme. İkisi (Veeam, Veeam Cloud Connect) aynı satıcıyla ama farklı SKU'larla. Sızma testi veya GRC sayılmadan veri düzlemi kalemleri yılda EUR 36.000. Ekip yıllık bir kurtarma testi üretiyor, sürekli etkinlik kanıtı yok, yalnızca veri düzleminde beş girişli bir tedarikçi kaydı.

**Sonra**, kendi barındırılan iş yükleri için Hetzner üzerinde Rediacc ile:

- Rediacc Business katmanı, EUR 8.400/yıl (depo boyutlarını karşılıyor)
- Birincil ve ikincil için Hetzner IaaS, toplam EUR 9.600/yıl (zaten bütçede; yeni kalem yok)
- Sızma testi sözleşmesi kalıyor (EUR 22.000)
- Drata kalıyor (EUR 18.000)
- Evde yapılmış test verisi düzeni emekliye ayrılıyor; her iki haftada bir yarım SRE günü bunun yerine haftalık etkinlik rutinini çalıştırmaya gidiyor

Veri düzlemi birleştirmesi: 5 kalemden 1'e (Rediacc) artı mevcut IaaS kalemi. Tedarikçi kaydının veri düzlemi bölümü 5 girişten 2'ye düşüyor. Sürekli etkinlik hikayesi artık hash zincirli denetim günlüğü kanıtıyla haftalık tatbikatlar; kurtarma testi hikayesi artık `rdc machine backup status` çıktısı ve haftada bir geri yükleme tatbikatıyla desteklenmiş.

Rakamlar gösterge niteliğinde, vaat değil. Sizin yığınınız farklı. Şekil (dört-beş kalemin tek artı mevcut IaaS'a indirgenmesi), gerçek bir alıcı görüşmesinin nasıl göründüğü.

## Bu ne değil: bir not

Bu yazı Veeam'ı çökertme veya TCO hesaplaması değil. Veeam, Avrupa'daki en büyük VM yedekleme pazar payını iyi nedenlerle yönetiyor; ürünleri olgun, iş ortağı ağı geniş, NIS2 pazarlaması güçlü ve 2026'da Veeam seçen bir alıcı hata yapmıyor. Referans senaryodaki rakamlar, kıyaslamalar değil gerçek alıcı görüşmelerinden alınmış gösterge niteliğinde. Yapısal analizi kendi sözleşmelerinize karşı çalıştırın.

Bu ne: önümüzdeki on iki ayda bir yedekleme, DR veya uyum sözleşmesini yeniden müzakere eden ve kendi altyapınızı barındırmanın kalemleri nasıl değiştirdiğini merak eden bir CFO için alıcı tarafı çerçevesi.

## Sonraki adımlar

Yenileme döngüsüne girecekseniz ve bütçe açıksa, üç somut hamle:

1. **Geçen yılın en büyük üç güvenlik ve altyapı kalemini çıkarın.** DPO'nuza, CISO'nuza ve denetçinize gönderin. Hangilerinin NIS2 görünür kılmadan önce zaten fazla olduğunu sorun. Çoğu ekip, ödemeye devam ettikleri en az bir örtüşme buluyor.
2. **Mevcut veri düzlemi yığınınızı yukarıdaki beş kategorili listeyle eşleştirin.** Hangi kategoriler için bir satıcınız var, hangileri için iki, hangileri için hiç yok. "Hiç yok" hücreleri NIS2'nin gün yüzüne çıkaracağı boşluklar.
3. **Her veri düzlemi satıcısı için [tedarik zinciri yazısındaki](/tr/blog/nis2-supply-chain-self-hosted) tedarikçi kaydı egzersizini çalıştırın.** Kayıt girişlerini sayın. Sayı genellikle ekibin beklediğinden yüksek çıkıyor.

Kısa listendeysek, teklif somut. Geçen yılın güvenlik ve altyapı bütçesinden en büyük üç kalemi gönderin. Size bir hafta içinde hangilerinin birleştirilebileceğini ve hangilerinin birleştirilemeyeceğini yazılı olarak söyleriz. Yanıt boşlukları da içerecek; çünkü boşlukları adlandırmak, yanıtın geri kalanını güvenilir kılan şey.

Depolama tarafında neden rakiplerden daha hafif çalıştığımıza ilişkin mimari argüman için [zero-cost backup](/tr/docs/zero-cost-backup), kıtalararası DR için [Cross Backup Strategy](/tr/docs/cross-backup) ve ticari taraf için [Subscription & Licensing](/tr/docs/subscription-licensing) belgelerine bakın.
