---
title: "PCI DSS Uyumluluğu"
description: "Rediacc'ın şifreleme, ağ segmentasyonu ve erişim kontrolü ile ödeme kartı verilerini korumaya yönelik PCI DSS gereksinimlerine nasıl uyum sağladığı."
category: "Legal"
order: 6
language: tr
sourceHash: "06528e1f28fc2764"
---

Ödeme Kartı Endüstrisi Veri Güvenliği Standardı (PCI DSS), kart sahibi verilerini saklayan, işleyen veya ileten her kuruluş için gereklidir. Mevcut sürüm PCI DSS v4.0.1'dir.

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
| **Ger. 10**, Günlük kaydı ve izleme | Tüm erişimleri kaydetme ve izleme | Hesap düzeyinde 40'tan fazla olay türü (kimlik doğrulama, API token'ları, yapılandırma, lisanslama). Kullanıcı, ekip ve tarih bazında filtreleme ile yönetici paneli. `rdc audit` CLI ile programatik dışa aktarım. Makine düzeyindeki işlemler SSH ve sistem günlükleri ile denetlenebilir. |
| **Ger. 12**, Kurumsal politikalar | Bilgi güvenliğini kurumsal politikalar ve programlarla destekleme | Kendi sunucunuzda barındırma üçüncü taraf işleyici kapsamını ortadan kaldırır (Ger. 12.8). PCI DSS uyumluluk sınırını daraltır. |

## Ağ Segmentasyonu

PCI DSS, kart sahibi veri ortamını (CDE) izole etmek için ağ segmentasyonuna büyük önem verir. Rediacc bunu mimari olarak sağlar:

- Her depo `/var/run/rediacc/docker-<networkId>.sock` adresinde kendi Docker daemon'ında çalışır
- Depolar izole loopback IP alt ağlarına sahiptir (127.0.x.x/26, ağ başına 61 kullanılabilir IP)
- renet tarafından uygulanan iptables kuralları daemon'lar arası tüm trafiği engeller
- Farklı depolardan konteynerler ağ düzeyinde iletişim kuramaz

Bir ödeme işleme deposu, aynı makinedeki diğer tüm uygulamalardan ağ olarak izole edilmiştir. Ek güvenlik duvarı yapılandırması gerekmez.

## Kapsam Azaltma

Kendi sunucunuzda barındırılan Rediacc, PCI DSS uyumluluk kapsamını daraltır:

- Kart sahibi veri akışında üçüncü taraf bulut sağlayıcı yok
- Ger. 12.8 kapsamında değerlendirilecek SaaS sağlayıcısı yok (üçüncü taraf hizmet sağlayıcılar)
- Fiziksel güvenlik kontrolleri doğrudan sizin yönetiminizde
- Şifreleme anahtarları yalnızca operatörün yerel yapılandırmasında saklanır

## Uygulama Vakaları

Zayıf ağ segmentasyonu ve eksik şifreleme, maliyetli PCI DSS uygulama işlemlerine yol açmıştır:

- Heartland Payment Systems (2008): saldırganlar zayıf ağ segmentasyonu nedeniyle 48 veritabanında yanal hareket ederek 130 milyon kart numarasını açığa çıkardı. [Toplam maliyet 200 milyon doları aştı.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): saldırganlar düz ağ mimarisi nedeniyle HVAC tedarikçisinin ağ erişiminden satış noktası sistemlerine geçerek 40 milyon ödeme kartını ele geçirdi. [47 eyalet başsavcısı ile 18,5 milyon dolarlık uzlaşma.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
