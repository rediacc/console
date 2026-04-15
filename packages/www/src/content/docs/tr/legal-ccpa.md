---
title: "CCPA Uyumluluğu"
description: "Rediacc'ın kendi sunucunuzda barındırma modeli, tüketici verilerinin korunmasına yönelik Kaliforniya Tüketici Gizlilik Yasası gereksinimlerini nasıl karşılar."
category: "Legal"
order: 4
language: tr
sourceHash: "8d0fc1ff16c1be28"
---

Kaliforniya Tüketici Gizlilik Yasası (CCPA), Kaliforniya'daki tüketicilere kişisel bilgileri üzerinde haklar tanıyan bir eyalet yasasıdır. Bu haklar arasında hangi verilerin toplandığını bilme hakkı, silme hakkı ve satışını reddetme hakkı yer alır.

Referans: [Kaliforniya Başsavcısı, CCPA](https://oag.ca.gov/privacy/ccpa)

## Tüketici Hakları Eşlemesi

CCPA, kişisel bilgilerle ilgili tüketici haklarına odaklanır. Rediacc, sizin altyapınızda dağıtılan, kendi sunucunuzda barındırılan bir araçtır; tüketici verilerini toplayan veya satan üçüncü taraf bir hizmet değildir. Aşağıdaki tablo, Rediacc'ın kuruluşunuzun CCPA uyumluluğunu nasıl desteklediğini gösterir.

| CCPA Hakkı | Gereksinim | Rediacc Yeteneği |
|-----------|-----------|-----------------|
| Bilme hakkı (1798.100) | Toplanan verilerin kategorilerini ve amaçlarını açıklama | Denetim günlükleri tüm veri işlemlerini takip eder. Kendi sunucunuzda barındırma: kuruluşunuz her depodaki verilerin tam görünürlüğünü korur. |
| Silme hakkı (1798.105) | Talep üzerine tüketicinin kişisel bilgilerini silme | `rdc repo destroy` LUKS ile şifrelenmiş birimi kriptografik olarak siler. Fork silme işlemi klonlanmış kopyaları tamamen kaldırır. |
| Reddetme hakkı (1798.120) | Kişisel bilgileri satmama veya paylaşmama | Kendi sunucunuzda barındırma mimarisi: Rediacc'a veya herhangi bir üçüncü tarafa veri aktarımı yapılmaz. Veriler sunucularınızda kalır. Yapılandırma deposu senkronizasyonu sıfır bilgi şifrelemesi kullanır. Senkronizasyon sunucusu bile verileri okuyamaz. |
| Veri güvenliği (1798.150) | Makul güvenlik önlemlerini uygulama | LUKS2 AES-256 şifreleme, ağ izolasyonu, yalnızca SSH erişimi, izole Docker daemon'ları, denetim günlüğü. Yapılandırma deposu, bölünmüş anahtar türetme ve dönen tek kullanımlık token'lar ile üç katmanlı şifreleme kullanır. |

## Hizmet Sağlayıcı Durumu

Yazılım olarak Rediacc, tüketici verilerine erişmez, işlemez veya depolamaz. BT ekibiniz Rediacc'ı kendi altyapınızda işletir. Rediacc şirketine hiçbir veri akmaz. Sonuçları:

- Rediacc, CCPA kapsamında bir "hizmet sağlayıcı" değildir (sizin adınıza veri işlemez)
- Kendi sunucunuzda barındırılan ürün için Rediacc ile veri işleme sözleşmesi gerekmez
- CCPA yükümlülükleriniz kuruluşunuz ile tüketicileriniz arasındadır

## Veri Envanteri

Her Rediacc deposu, benzersiz bir GUID'e sahip ayrı, şifrelenmiş bir veri birimidir. Hangi verilerin nerede olduğunu tam olarak envantere alabilirsiniz:

- `rdc machine query <machine> --repositories` bir makinedeki tüm depoları boyut ve bağlama durumu ile listeler
- Her depo dosya sistemi, ağ ve konteyner düzeyinde izole edilmiştir
- Fork ilişkileri takip edilir, böylece bir veri setinin tüm kopyalarını tanımlayabilirsiniz

CCPA veri haritalama gerektirir. Rediacc'ın depo modeli bunu sağlar: veri seti başına bir GUID, makine başına numaralandırılabilir, fork soy ağacı takip edilir.
