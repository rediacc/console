---
title: "Uyumluluk Genel Bakışı"
description: "Rediacc'ın kendi sunucunuzda barındırma mimarisi veri koruma, gizlilik ve güvenlik uyumluluk gereksinimlerini nasıl karşılar."
category: "Legal"
order: 0
language: tr
sourceHash: "e20385eb9adfe180"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Rediacc tamamen sizin altyapınızda çalışır. Ortam klonlama, yedekleme ve dağıtım işlemleri sırasında veriler makinenizi asla terk etmez. Hem veri sorumlusu hem de veri işleyen siz olmaya devam edersiniz. Hiçbir üçüncü taraf SaaS verilerinizi işlemez.

Bu bölüm, Rediacc'ın teknik yeteneklerini başlıca uyumluluk çerçevelerinin gereksinimleriyle eşleştirir. Her sayfa, resmi yasal metinlere madde düzeyinde referanslarla belirli bir düzenlemeyi kapsar.

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

Bu bölümdeki her uyumluluk çerçevesi aynı teknik özelliklere dayanır:

- **Durağan halde şifreleme**: Her depo LUKS2 AES-256 ile şifrelenir. Kimlik bilgileri yalnızca operatörün yerel yapılandırmasında saklanır, asla sunucuda değil.
- **Ağ izolasyonu**: Her depo kendi Docker daemon'ına, loopback IP alt ağına (/26) ve iptables kurallarına sahiptir. Farklı depolardan konteynerler birbirleriyle iletişim kuramaz.
- **Copy-on-write klonlama**: `rdc repo fork` dosya sistemi reflink'lerini (`cp --reflink=always`) kullanır. Veriler herhangi bir ağ transferi olmadan aynı makinede çoğaltılır.
- **Denetim günlüğü**: Kimlik doğrulama (giriş, 2FA, parola değişiklikleri, oturum iptali), API token yaşam döngüsü, yapılandırma deposu işlemleri ve abonelik/lisans etkinliğini kapsayan 40'tan fazla olay türü. Yönetici paneli ve `rdc audit` CLI üzerinden erişilebilir. Makine düzeyindeki işlemler (fork, yedekleme, dağıtım) makinenin kendisinde SSH ve sistem günlükleri aracılığıyla gerçekleştirilir.
- **Şifreli yedekleme**: `rdc repo push/pull` verileri SSH üzerinden aktarır. Yedekleme hedefi LUKS ile şifrelenmiş birimler alır.
- **Sıfır bilgi yapılandırma deposu**: Cihazlar arası isteğe bağlı şifreli yapılandırma senkronizasyonu. Yapılandırmalar yüklenmeden önce istemci tarafında AES-256-GCM ile şifrelenir. Sunucu yalnızca opak blob'lar saklar. Sunucu SSH anahtarlarını, kimlik bilgilerini, IP adreslerini veya herhangi bir düz metin yapılandırma verisini okuyamaz. Anahtar türetme passkey PRF extension + HKDF ile alan ayırma kullanır. Üye erişimi X25519 anahtar değişimi ile yönetilir ve iptal anında gerçekleşir.

Bu yetenekler hakkında ayrıntılı bilgi için [Mimari](/tr/docs/architecture), [Depolar](/tr/docs/repositories), [Yapılandırma Depolama](/tr/docs/config-storage) ve [Hesap Güvenliği](/tr/docs/account-security) sayfalarına bakın.

## Neden Önemli

Uyumluluk başarısızlıkları maliyetlidir. Bu uygulama vakaları, Rediacc'ın mimarisinin yapısal olarak önlediği sorunları içeriyordu:

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

Bu sayfalar, Rediacc'ın teknik yeteneklerini uyumluluk gereksinimleriyle ilişkili olarak açıklar. Herhangi bir düzenlemeye uyum, tek bir aracın kapsamının ötesinde kurumsal politikalar, prosedürler, personel eğitimi ve potansiyel olarak üçüncü taraf denetimleri gerektirir. Kuruluşunuza özel rehberlik için hukuk ve uyumluluk ekibinize danışın.
