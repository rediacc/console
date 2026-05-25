---
title: "GDPR Uyumluluğu"
description: "Rediacc'ın kendi sunucunuzda barındırma mimarisi GDPR veri koruma ve gizlilik gereksinimlerine nasıl uyum sağlar."
category: "Legal"
order: 1
language: tr
sourceHash: "36a776d87c6294ff"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Genel Veri Koruma Yönetmeliği (GDPR), Mayıs 2018'den bu yana yürürlükte olan Avrupa Birliği'nin veri koruma yasasıdır. Kuruluşların AB'deki bireylerin kişisel verilerini nasıl topladığını, işlediğini ve sakladığını düzenler.

Tam metin: [Yönetmelik (AB) 2016/679](https://gdpr-info.eu/)

## Madde Eşlemesi

Aşağıdaki tablo, belirli GDPR maddelerini Rediacc'ın teknik yetenekleriyle eşleştirir.

| Madde | Gereksinim | Rediacc Yeteneği |
|-------|-----------|-----------------|
| [Md. 5](https://gdpr-info.eu/art-5-gdpr/), İlkeler | Veri minimizasyonu, bütünlük, gizlilik | CoW klonları (`cp --reflink=always`) verileri ağ transferi olmadan aynı makinede çoğaltır. LUKS2 AES-256 durağan haldeki tüm verileri şifreler. |
| [Md. 17](https://gdpr-info.eu/art-17-gdpr/), Silme hakkı | Talep üzerine kişisel verileri silme | `rdc repo delete` LUKS birimini kriptografik olarak siler. Bir fork'un silinmesi klonlanmış kopyayı tamamen kaldırır. |
| [Md. 25](https://gdpr-info.eu/art-25-gdpr/), Tasarım yoluyla veri koruma | Varsayılan olarak gizlilik | Şifreleme zorunludur, isteğe bağlı değildir. Her depo izole bir Docker daemon ve özel ağ alır. Depolar arasında veri paylaşımı yoktur. Yapılandırma deposu sıfır bilgi şifrelemesi kullanır: yapılandırmalar yüklenmeden önce istemci tarafında AES-256-GCM ile şifrelenir, böylece sunucu düz metin veri okuyamaz. |
| [Md. 28](https://gdpr-info.eu/art-28-gdpr/), İşleyici | Üçüncü taraf veri işleme yükümlülükleri | Kendi sunucunuzda barındırma: Rediacc sizin altyapınızda çalışır. Fork, klonlama veya yedekleme işlemleri sırasında hiçbir veri makinenizi terk etmez. Hiçbir SaaS bileşeni kişisel verileri işlemez. |
| [Md. 30](https://gdpr-info.eu/art-30-gdpr/), İşleme kayıtları | İşleme faaliyetlerinin kayıtlarını tutma | Denetim günlüğü hesap düzeyinde 40'tan fazla olay türünü takip eder: kimlik doğrulama, API token'ları, yapılandırma deposu işlemleri ve lisanslama. `rdc audit` CLI veya yönetici paneli üzerinden dışa aktarım. |
| [Md. 32](https://gdpr-info.eu/art-32-gdpr/), İşleme güvenliği | Uygun teknik önlemler | Durağan halde LUKS2 AES-256 şifreleme, iptables ve ayrı Docker daemon'ları ile ağ izolasyonu, depo başına loopback IP alt ağları (/26). Yapılandırma deposu üç katmanlı şifreleme kullanır: zaman pencereli SDK anahtarları, bölünmüş anahtar CEK türetme (passkey + sunucu sırrı) ve kuruluş parola ifadesi şifrelemesi. |
| [Md. 33](https://gdpr-info.eu/art-33-gdpr/), İhlal bildirimi | Adli iz ile 72 saat bildirim | Denetim günlükleri tüm işlemlerin adli izini sağlar. Kendi sunucunuzda barındırma mimarisi etki alanını bireysel depolarla sınırlar. |

## Veri Yerleşimi

CoW klonları kaynak makineyi asla terk etmez. `rdc repo fork` komutu reflink'ler kullanarak dosya sistemi düzeyinde bir kopya oluşturur. Ağ üzerinden hiçbir veri aktarılmaz.

Makineler arası işlemler için `rdc repo push/pull` verileri SSH üzerinden aktarır. Yedekleme hedefi, operatörün kimlik bilgileri olmadan okunamayan LUKS ile şifrelenmiş birimler alır.

## Ortam Klonlama ve Veri Maskeleme

Üretim ortamlarını geliştirme veya test için klonlarken, Rediaccfile `up()` yaşam döngüsü kancası fork oluşturulduktan sonra temizlik betiklerini çalıştırır: veritabanlarından kişisel verileri kaldırma, gerçek e-posta adreslerini test adresleriyle değiştirme, API token'larını ve oturum verilerini kaldırma, günlük dosyalarını anonimleştirme. Geliştirme ortamı üretim kimlikleri olmadan üretim yapısını alır ve veri minimizasyonu ilkesini karşılar ([Md. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Sıfır Bilgi Yapılandırma Deposu

İsteğe bağlı yapılandırma deposu, CLI yapılandırmalarının cihazlar arasında senkronizasyonuna olanak tanır. Sunucunun yapılandırma içerikleri hakkında sıfır bilgiye sahip olacak şekilde tasarlanmıştır:

- **İstemci tarafı şifreleme**: Yapılandırmalar yüklenmeden önce AES-256-GCM ile şifrelenir. Şifreleme anahtarı (CEK), passkey PRF sırrı ve sunucu tarafında tutulan sırdan HKDF ile alan ayırma kullanılarak türetilir. Hiçbir taraf anahtarı tek başına türetemez.
- **Sunucu yalnızca opak blob'lar görür**: SSH anahtarları, kimlik bilgileri, IP adresleri, ağ topolojisi. Bunların hiçbiri sunucuya görünmez. Yalnızca meta veriler (yapılandırma kimlikleri, sürümler, zaman damgaları) düz metin olarak saklanır.
- **X25519 ile üye erişimi**: Bir ekip üyesi eklendiğinde, CEK onun X25519 genel anahtarıyla şifrelenir ve sunucu aracılığıyla iletilir. Sunucu CEK'i asla düz metin olarak görmez.
- **Anında iptal**: Bir üyeyi kaldırmak, onun sarmalanmış CEK'ini siler ve token'larını iptal eder. Gelecekteki yapılandırmalar, kaldırılan üyenin erişemeyeceği yeni SDK dönemlerini kullanır.
- **Dönen token'lar**: CLI kimlik doğrulaması, ilk kullanımda IP'ye bağlanan, 24 saatlik otomatik süre sona erme ile tek kullanımlık dönen token'lar (3 isteklik tolerans penceresi) kullanır.

Sunucunun tamamen ele geçirilmesi bile yapılandırma içeriklerini açığa çıkaramaz. Sunucu anahtara asla sahip değildir.

Ayrıntılar için [Yapılandırma Depolama](/tr/docs/config-storage) sayfasına bakın.

## Veri Sorumlusu ve İşleyici

Rediacc kendi sunucunuzda barındırılan bir yazılım olduğundan, kuruluşunuz hem veri sorumlusu hem de veri işleyicidir. Rediacc (şirket) verilerinize erişmez, işlemez veya depolamaz. Kendi sunucunuzda barındırılan ürün için Rediacc ile veri işleme sözleşmesi gerekmez, çünkü hiçbir kişisel veri Rediacc'ın altyapısına akmaz.

Yapılandırma deposu, Rediacc'ın sunucularına dokunan tek bileşendir (senkronizasyon için), ancak sıfır bilgi tasarımı, sunucunun yalnızca çözemediği şifreli blob'ları sakladığı anlamına gelir.
