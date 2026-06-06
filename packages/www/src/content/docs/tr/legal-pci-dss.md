---
title: "PCI DSS Uyumluluğu"
description: "Rediacc'ın PCI DSS gereksinimlerine nasıl uyum sağladığı: alınmaz yedeklemeler, otomatik ağ izolasyonu ve altyapı düzeyinde erişim kontrolü."
category: "Legal"
order: 6
language: tr
sourceHash: "d8391036876231a0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Kısacası, kart sahibi verisi işliyorsanız PCI DSS v4.0.1 isteğe bağlı değildir. PCI DSS v4.0.1, tek bir gereksinime indirgenir: her şeyden altyapı düzeyinde izolasyon.

Referans: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Gereksinim Eşlemesi

| PCI DSS Gereksinimleri | Açıklama | Rediacc Yeteneği |
|----------------------|----------|-----------------|
| **Ger. 1**, Ağ güvenliği kontrolleri | Ağ güvenliği kontrollerini kurma ve sürdürme | Depo başına iptables kuralları depolar arası tüm trafiği engeller. Her depo kendi loopback IP alt ağını (/26) alır. |
| **Ger. 2**, Güvenli yapılandırmalar | Tüm sistem bileşenlerine güvenli yapılandırmalar uygulama | Rediaccfile yaşam döngüsü kancaları belirleyici, tekrarlanabilir yapılandırmalar dayatır. Varsayılan kimlik bilgisi yok. LUKS anahtarları operatör tarafından oluşturulur. |
| **Ger. 3**, Depolanan hesap verilerini koruma | Depolanan hesap verilerini şifreleme ile koruma | Tüm depo birimlerinde LUKS2 AES-256 şifreleme. Şifreleme zorunludur, isteğe bağlı değildir. LUKS anahtar yok etme ile kriptografik silme. |
| **Ger. 4**, Aktarım sırasında veri koruma | Kart sahibi verilerini iletim sırasında güçlü kriptografi ile koruma | Tüm uzak işlemler SSH üzerinden. Yedekleme aktarımı uçtan uca şifrelenir. Şifrelenmemiş veri yolu yok. |
| **Ger. 6**, Güvenli geliştirme | Güvenli sistemler ve yazılımlar geliştirme ve sürdürme | CoW klonlama, üretim kart verilerini geliştirme ağlarına açmadan izole test ortamları oluşturur. Fork-test-yükseltme iş akışı. |
| **Ger. 7**, Erişimi kısıtlama | İş gereksinimi temelinde sistem bileşenleri ve kart sahibi verilerine erişimi kısıtlama | Depo başına Docker daemon soketleri. Bir depoya erişim diğerine erişim sağlamaz. SSH anahtar tabanlı kimlik doğrulama. |
| **Ger. 8**, Kullanıcı tanımlama ve doğrulama | Kullanıcıları tanımlama ve sistem bileşenlerine erişimi doğrulama | SSH anahtar kimlik doğrulaması. IP bağlama ve kapsamlı izinler ile API token'ları. İki faktörlü kimlik doğrulama (TOTP). |
| **Ger. 9**, Fiziksel erişimi kısıtlama | Kart sahibi verilerine fiziksel erişimi kısıtlama | Kendi sunucunuzda barındırma: fiziksel güvenlik doğrudan sizin kontrolünüzde. LUKS şifreleme çalınan sürücüleri okunamaz hale getirir. |
| **Ger. 10**, Günlük kaydı ve izleme | Tüm sistem bileşenleri ve kart sahibi verilerine erişimi kaydetme ve izleme | 70+ olay türü (kimlik doğrulama, API token'ları, yapılandırma, lisanslama, makine işlemleri). Kullanıcı, ekip, tür ve tarih bazında filtreleme ile yönetici paneli ve portal. `rdc audit` CLI ile programatik dışa aktarım. Makine işlemleri ayrıca savunma derinliği için sistem günlüklerinde de kaydedilir. |
| **Ger. 12**, Kurumsal politikalar | Bilgi güvenliğini kurumsal politikalar ve programlarla destekleme | Kendi sunucunuzda barındırma üçüncü taraf işleyici kapsamını ortadan kaldırır (Ger. 12.8). PCI DSS uyumluluk sınırını daraltır. |

## Ağ Segmentasyonu

PCI DSS segmentasyona ağır basıyor. Yetersiz izolasyonun üzerine iptables kuralları katmanlandıran ekipler görüyorum. Böyle çalışmıyor. Başarıyı yakalayanlar segmentasyonu mimariye yerleştirmiş olanlar. Rediacc bunu varsayılan olarak sağlıyor:

- Her depo `/var/run/rediacc/docker-<networkId>.sock` adresinde kendi Docker daemon'ında çalışır
- Depolar izole loopback IP alt ağlarına sahiptir (127.0.x.x/26, ağ başına 61 kullanılabilir IP)
- renet tarafından uygulanan iptables kuralları daemon'lar arası tüm trafiği engeller
- Farklı depolardan konteynerler ağ düzeyinde iletişim kuramaz

Bir ödeme işleme deposu kendi Docker daemon'ında ve kendi loopback alt ağında çalışır; aynı makinedeki her diğer uygulamadan ağ olarak izole edilmiştir. Yazılacak ek güvenlik duvarı kuralı yoktur.

## Kapsam Azaltma

Kendi sunucunuzda barındırılan Rediacc, PCI DSS uyumluluk kapsamını daraltır. Ağ segmentasyonunu el ile yapılandırmanız gerekmez; tasarım gereği otomatiktir. Bu kısım için hala dokümantasyonumuz iyileştirilmesi gerekiyor ama izolasyon sağlam:

- Kart sahibi veri akışında üçüncü taraf bulut sağlayıcı yok
- Ger. 12.8 kapsamında değerlendirilecek SaaS sağlayıcısı yok (üçüncü taraf hizmet sağlayıcılar)
- Fiziksel güvenlik kontrolleri doğrudan sizin yönetiminizde
- Şifreleme anahtarları yalnızca operatörün yerel yapılandırmasında saklanır

## Uygulama Vakaları

En çok PCI denetim başarısızlığı iki şeyden birine indirgenir: asla düzgün şekilde izole edilmemiş segmentasyon ya da gerçek saldırılara karşı hiçbir zaman test edilmemiş şifreleme.

- Heartland Payment Systems (2008): saldırganlar zayıf ağ segmentasyonu nedeniyle 48 veritabanında yanal hareket ederek 130 milyon kart numarasını açığa çıkardı. [Toplam maliyet 200 milyon doları aştı.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): saldırganlar düz ağ mimarisi nedeniyle HVAC tedarikçisinin ağ erişiminden satış noktası sistemlerine geçerek 40 milyon ödeme kartını ele geçirdi. [47 eyalet başsavcısı ile 18,5 milyon dolarlık uzlaşma.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
