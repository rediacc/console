---
title: "Uyumluluk Gerçekte Neler Gerektirir"
description: "Rediacc sizin altyapınızda çalışır. Verilerinizi siz kontrol edersiniz. İşte bunun başlıca uyumluluk çerçeveleriyle nasıl hizalandığı."
category: "Legal"
order: 0
language: tr
sourceHash: "e6044a3b067b54d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc tamamen sizin altyapınızda çalışır. Klonlama, yedekleme ve dağıtım işlemleri sırasında verileriniz makinelerinizi asla terk etmez. Hem veri denetleyicisi hem de veri işleyeni siz olmaya devam edersiniz. Hiçbir üçüncü taraf SaaS hizmeti veya dış erişim yoktur.

Rediacc'ın teknik yeteneklerini başlıca uyumluluk gereksinimlerine eşleştiriyoruz. Her sayfa, resmi yasal metne referanslar içererek belirli bir düzenlemeyi ayrıntılarıyla açıklar.

## Uyumluluk Matrisi

| Çerçeve | Kapsam | Temel Rediacc Yetenekleri |
|---------|--------|---------------------------|
| [GDPR](/tr/docs/legal-gdpr) | AB veri koruma ve gizlilik | Aynı makinede CoW klonlama, LUKS2 şifreleme, sıfır bilgi yapılandırma deposu, denetim günlüğü, `rdc repo delete` ile silme hakkı |
| [SOC 2](/tr/docs/legal-soc2) | Hizmet kuruluşları için güven hizmeti kriterleri | Durağan halde şifreleme, sıfır bilgi yapılandırma senkronizasyonu, ağ izolasyonu, denetim izi, yedekleme ve kurtarma |
| [HIPAA](/tr/docs/legal-hipaa) | ABD sağlık bilgileri koruması | LUKS2 şifreleme, sıfır bilgi yapılandırma deposu, yalnızca SSH erişimi, izole Docker daemon'ları, iletim güvenliği |
| [CCPA](/tr/docs/legal-ccpa) | Kaliforniya tüketici gizlilik hakları | Kendi sunucunuzda barındırma (veri satışı/paylaşımı yok), sıfır bilgi şifreleme, şifreli silme, depo başına veri envanteri |
| [ISO 27001](/tr/docs/legal-iso27001) | Bilgi güvenliği yönetimi kontrolleri | Varlık yönetimi, kriptografik kontroller, sıfır bilgi yapılandırma deposu, erişim kontrolü, operasyon güvenliği |
| [PCI DSS](/tr/docs/legal-pci-dss) | Ödeme kartı verisi koruması | Mimari ile ağ segmentasyonu, zorunlu şifreleme, denetim günlüğü, kendi sunucunuzda barındırma ile kapsam azaltma |
| [NIS2 ve DORA](/tr/docs/legal-nis2-dora) | AB siber güvenlik ve finansal dayanıklılık | Tedarik zinciri riskinin ortadan kaldırılması, CoW klonlama ile dayanıklılık testi, şifreleme, olay tespiti |
| [Veri Egemenliği](/tr/docs/legal-data-sovereignty) | Küresel veri yerleşimi yasaları (PIPL, LGPD, KVKK, PIPA ve daha fazlası) | Kendi sunucunuzda barındırma = veriler yetki alanınızı asla terk etmez. Sınır ötesi transferler yok, yeterlilik değerlendirmeleri yok |

## Mimari Temeller

Hepsi bu ortak noktada birleşiyor: bu bölümdeki her uyumluluk çerçevesi aynı teknik temellere dayanır.

- **Durağan halde şifreleme**: Her depo LUKS2 AES-256 ile şifrelenir. Kimlik bilgileri yalnızca operatörün yerel yapılandırmasında saklanır, asla sunucuda değil.
- **Ağ izolasyonu**: Her depo kendi Docker daemon'ına, loopback IP alt ağına (/26) ve iptables kurallarına sahiptir. Farklı depolardan konteynerler birbirleriyle iletişim kuramaz.
- **Copy-on-write klonlama**: `rdc repo fork` dosya sistemi reflink'lerini (`cp --reflink=always`) kullanır. Veriler herhangi bir ağ transferi olmadan aynı makinede çoğaltılır.
- **Denetim günlüğü**: Kimlik doğrulama (giriş, 2FA, parola değişiklikleri, oturum iptali), API token yaşam döngüsü, yapılandırma deposu işlemleri, abonelik/lisans etkinliği ve CLI makine işlemleri (depo yaşam döngüsü, yedekleme, senkronizasyon, terminal oturumları) başta olmak üzere 70+ olay türü. Yönetici paneli ve portal aktivite sayfası aracılığıyla erişilebilir (org kapsamlı filtreleme ve JSON dışa aktarma ile). Makine işlemleri, derinlemesine savunma için sistem günlüklerinizde de kaydedilir.
- **Şifreli yedekleme**: `rdc repo push/pull` verileri SSH üzerinden aktarır. Yedekleme hedefi LUKS ile şifrelenmiş birimler alır.
- **Sıfır bilgi yapılandırma deposu**: Cihazlar arası isteğe bağlı şifreli yapılandırma senkronizasyonu. Yapılandırmalar yüklenmeden önce istemci tarafında AES-256-GCM ile şifrelenir. Sunucu yalnızca opak blob'lar saklar. Sunucu SSH anahtarlarını, kimlik bilgilerini, IP adreslerini veya herhangi bir düz metin yapılandırma verisini okuyamaz. Anahtar türetme passkey PRF extension + HKDF ile alan ayırma kullanır. Üye erişimi X25519 anahtar değişimi ile yönetilir ve iptal anında gerçekleşir.

Bu yetenekler hakkında ayrıntılı bilgi için [Mimari](/tr/docs/architecture), [Depolar](/tr/docs/repositories), [Yapılandırma Depolama](/tr/docs/config-storage) ve [Hesap Güvenliği](/tr/docs/account-security) sayfalarına bakın.

## Neden Önemli

Uyumluluk başarısızlıkları maliyetlidir. Çok maliyetlidir. Aşağıdaki vakalar, Rediacc'ın mimarisinin yapısal olarak önlediği sorunları göstermektedir:

| Olay | Ceza | Ne yanlış gitti |
|------|------|-----------------|
| [Meta: AB-ABD veri transferleri](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 milyar EUR | Kişisel veriler yeterli güvenceler olmadan sınırlar arasında aktarıldı. Kendi sunucunuzda barındırma, transfer olmaması demektir. |
| [Equifax: şifrelenmemiş veriler](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 milyon USD | 147 milyon kayıt zayıf ağ segmentasyonu ile şifrelenmeden saklandı. LUKS2 zorunludur, isteğe bağlı değil. |
| [Target: yanal hareket](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 milyon USD | Saldırganlar düz bir ağ üzerinden HVAC tedarikçisinden ödeme sistemlerine geçti. Depo başına izolasyon bunu önler. |
| [Anthem: şifrelenmemiş PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 milyon USD | 79 milyon sağlık kaydı şifrelenmeden saklandı. LUKS2 AES-256 her zaman etkindir. |
| [Blackbaud: SaaS ihlal zinciri](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 milyon USD | Bir SaaS sağlayıcısına yönelik fidye yazılımı 13.000'den fazla müşteri kuruluşunun verilerini açığa çıkardı. Kendi sunucunuzda barındırma, bir sağlayıcı ihlalinin verilerinize ulaşamayacağı anlamına gelir. |
| [British Airways: zayıf segmentasyon](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 milyon GBP | Saldırganlar yetersiz ağ kontrolleri nedeniyle kötü amaçlı kod enjekte etti. İzole Docker daemon'ları ve iptables yanal erişimi önler. |
| [Google: silme hakkı](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 milyon EUR | Dağıtık sistemlerde verileri tamamen silmenin zorluğu. LUKS yok etme ile kriptografik silme anlık ve eksiksizdir. |

## Önemli Uyarı

Bu sayfalar, Rediacc'ın mimarisinin uyumluluk gereksinimleriyle nasıl hizalandığını açıklamaktadır. Ancak gerçek şu: uyumluluk yazılımdan daha geniş bir konsepttir. Politikalar, prosedürler, eğitim ve muhtemelen üçüncü taraf denetimlerine ihtiyacınız olacak. Rediacc altyapı kısmını yönetir. Geri kalan konularda hukuk ve uyumluluk ekiplerinizle çalışın.
