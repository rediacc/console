---
title: "HIPAA Uyumluluğu"
description: "Rediacc'ın şifreleme ve izolasyon mimarisi, sağlık bilgilerini korumaya yönelik HIPAA güvence gereksinimlerine nasıl uyum sağlar."
category: "Legal"
order: 3
language: tr
sourceHash: "f5fbdaa4a00491ea"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Sağlık Sigortası Taşınabilirlik ve Hesap Verebilirlik Yasası (HIPAA), hassas hasta sağlık bilgilerinin (PHI) korunması için standartlar belirleyen bir ABD federal yasasıdır. Kapsanan kuruluşlar (sağlık hizmeti sağlayıcıları, sağlık planları, sağlık takas odaları) ve iş ortakları için geçerlidir.

Tam metin: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Güvence Eşlemesi

HIPAA idari, teknik ve fiziksel güvenceler gerektirir. Aşağıdaki tablo bunları Rediacc'ın yetenekleriyle eşleştirir.

### Teknik Güvenceler

| Gereksinim | HIPAA Referansı | Rediacc Yeteneği |
|-----------|----------------|-----------------|
| Erişim kontrolü | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | SSH anahtar tabanlı kimlik doğrulama. IP bağlama ve kapsam kısıtlamaları ile API token'ları. Depo başına Docker daemon izolasyonu depolar arası erişimi önler. |
| Denetim kontrolleri | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Kimlik doğrulama, API token'ları, yapılandırma işlemleri ve lisanslama dahil hesap düzeyinde 40'tan fazla olay türü. Kullanıcı ve ekip bazında izleme. Yönetici paneli veya `rdc audit` CLI üzerinden dışa aktarım. |
| Bütünlük kontrolleri | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | CoW anlık görüntüleri değişikliklerden önce orijinal verileri korur. `rdc repo validate` depo bütünlüğünü ve yedekleme sağlığını doğrular (LUKS konteyneri, dosya sistemi tutarlılığı, yapılandırma). |
| Durağan halde şifreleme | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Tüm depo birimlerinde LUKS2 AES-256 şifreleme. Kimlik bilgileri yalnızca operatörün yerel yapılandırmasında saklanır, asla sunucuda değil. Yapılandırma deposu bölünmüş anahtar türetme ile sıfır bilgi AES-256-GCM şifrelemesi kullanır. Sunucu bile depolanan yapılandırmaları çözemez. |
| İletim güvenliği | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Tüm uzak işlemler SSH kullanır. Yedekleme aktarımı uçtan uca şifrelenir. Şifrelenmemiş veri aktarımı yoktur. |

### İdari Güvenceler

| Gereksinim | Rediacc Yeteneği |
|-----------|-----------------|
| İş gücü erişim yönetimi | Kapsamlı izinlerle API token'ları. Ekip tabanlı erişim kontrolü. Ekipten çıkarılma durumunda otomatik token iptali. |
| Güvenlik olayı prosedürleri | Denetim günlükleri tüm işlemlerin adli izini sağlar. Depo başına izolasyon etki alanını sınırlar. |
| Acil durum planlaması | `rdc repo push/pull` çoklu hedefli şifreli yedeklemeyi destekler. CoW anlık görüntüleri anlık kurtarmayı sağlar. |

### Fiziksel Güvenceler

| Gereksinim | Rediacc Yeteneği |
|-----------|-----------------|
| Tesis erişim kontrolleri | Kendi sunucunuzda barındırma: kuruluşunuz sunucularınızın fiziksel güvenliğini kontrol eder. Temel işlemler için üçüncü taraf veri merkezlerine bağımlılık yok. |
| İş istasyonu güvenliği | LUKS durağan haldeki tüm verileri şifreler. Bağlanmamış depolar diskte şifreli blob'lardır, operatörün kimlik bilgileri olmadan okunamaz. |

## İş Ortağı Sözleşmesi (BAA)

Rediacc altyapınızda çalışan, kendi sunucunuzda barındırılan bir yazılım olduğundan, Rediacc'ın (şirketin) sistemleri aracılığıyla PHI işlemez, depolamaz veya iletmez. Tipik BAA gereksinimleri altyapı sağlayıcınız (bulut sağlayıcı veya ortak yerleşim tesisi) için geçerlidir, Rediacc için değil.

Rediacc sunucularınızda bir yazılım aracı olarak çalışır, bir işletim sistemi veya veritabanı motoru gibi. Verilerinize erişimi yoktur. İsteğe bağlı yapılandırma deposu Rediacc'ın sunucuları aracılığıyla şifreli blob'ları senkronize eder, ancak sıfır bilgi tasarımı sunucunun içerikleri çözemeyeceği anlamına gelir. Yalnızca opak şifreli metin saklar.

## PHI İçeren Geliştirme Ortamları

PHI içeren üretim ortamlarını geliştirme amacıyla klonlarken, Rediaccfile `up()` yaşam döngüsü kancasını kullanarak şu temizlik betiklerini çalıştırın:

- Veritabanı tablolarından PHI kaldırma
- Hasta tanımlayıcılarını sentetik verilerle değiştirme
- Oturum token'larını ve API anahtarlarını kaldırma

Geliştiriciler kimliği gizlenmiş verilerle üretime benzer altyapı elde eder ve HIPAA'nın minimum gereklilik standardını karşılar.
