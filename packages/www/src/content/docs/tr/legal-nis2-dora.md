---
title: "NIS2 ve DORA"
description: "Rediacc'ın AB NIS2 siber güvenlik direktifi ve DORA dijital operasyonel dayanıklılık gereksinimlerini nasıl karşıladığı."
category: "Legal"
order: 8
language: tr
sourceHash: "72a61496d38955d3"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

NIS2 ve DORA, kritik altyapı ve finans sektörü kuruluşlarına siber güvenlik ve operasyonel dayanıklılık gereksinimleri dayatan AB düzenlemeleridir. Her ikisi de 2025'te yürürlüğe girmiş ve AB endüstrileri genelinde geniş olarak uygulanmaktadır.

## NIS2 Direktifi

Ağ ve Bilgi Güvenliği Direktifi 2 (NIS2), enerji, ulaşım, sağlık, dijital altyapı ve kamu yönetimi dahil sektörlerdeki "temel" ve "önemli" kuruluşlar için siber güvenlik gereksinimleri belirler.

Tam metin: [Direktif (AB) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### NIS2 Gereksinim Eşlemesi

| NIS2 Gereksinimi | Rediacc Yeteneği |
|-----------------|-----------------|
| Risk yönetimi önlemleri (Md. 21) | Durağan halde LUKS2 şifreleme, depo başına ağ izolasyonu, yalnızca SSH erişimi, denetim günlüğü (70+ olay türü makine işlemleri dahil) |
| Olay işleme (Md. 21(2)(b)) | 70+ olay türü (kimlik doğrulama, token'lar, yapılandırma, lisanslama, makine işlemleri) adli iz sağlar. Depo başına izolasyon etki alanını sınırlar. |
| İş sürekliliği (Md. 21(2)(c)) | `rdc repo push/pull` ile çoklu hedefli şifreli yedekleme. Anlık geri alma için CoW anlık görüntüler. |
| Tedarik zinciri güvenliği (Md. 21(2)(d)) | Kendi sunucunuzda barındırma SaaS tedarik zinciri riskini ortadan kaldırır. Hiçbir üçüncü taraf bulut sağlayıcı verilerinizi işlemez. |
| Ağ güvenliği (Md. 21(2)(e)) | Depo başına Docker daemon'ları, iptables kuralları, loopback IP izolasyonu (/26 alt ağları). |
| Şifreleme (Md. 21(2)(h)) | Zorunlu LUKS2 AES-256 şifreleme. AES-256-GCM ile sıfır bilgi yapılandırma deposu. |
| Erişim kontrolü (Md. 21(2)(i)) | SSH anahtar kimlik doğrulaması, IP bağlama ile kapsamlı API token'ları, iki faktörlü kimlik doğrulama (TOTP). |
| Olay raporlama, 24 saat erken uyarı (Md. 23) | Denetim günlüğü hızlı olay tespiti ve kapsamlandırmasını sağlar. |

### Tedarik Zinciri Riski

Tedarik zinciri güvenliği NIS2'nin merkezi bir endişesidir (Md. 21(2)(d)). Kuruluşlar BİT hizmet sağlayıcıları ve tedarikçilerinden kaynaklanan riskleri değerlendirmeli ve yönetmelidir.

Kendi sunucunuzda barındırılan Rediacc en büyük tedarik zinciri saldırı yüzeyini kaldırır ve evet, bunun açık olduğunu biliyorum. Neden önemli olduğu şu: hiçbir üçüncü taraf SaaS verilerinizi işlemez, hiçbir bulut sağlayıcı altyapınıza mantıksal erişime sahip değildir ve hiçbir çoklu kiracılık ortamı diğer müşterilerin güvenlik durumuna maruz kalma oluşturmaz. [Blackbaud'un 2020 fidye yazılımı saldırısı 13.000'den fazla müşteri kuruluşunun verilerini açığa çıkardı ve uzlaşmalarda 49,5 milyon dolara mal oldu.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Dijital Operasyonel Dayanıklılık Yasası)

DORA, AB finans sektörü için BİT risk yönetimi, olay raporlama, dayanıklılık testi ve üçüncü taraf risk yönetimi gereksinimlerini belirler. Bankalar, sigorta şirketleri, yatırım şirketleri, kripto varlık hizmet sağlayıcıları ve bunların kritik üçüncü taraf BİT sağlayıcıları için geçerlidir.

Tam metin: [Tüzük (AB) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### DORA Gereksinim Eşlemesi

| DORA Gereksinimi | Rediacc Yeteneği |
|-----------------|-----------------|
| BİT risk yönetimi çerçevesi (Md. 6) | Şifreleme, izolasyon, denetim günlüğü ve yedekleme teknik kontrol katmanını oluşturur. |
| Koruma ve önleme (Md. 9) | Durağan halde LUKS2 AES-256 şifreleme. Ağ izolasyonu yanal hareketi önler. Yalnızca SSH erişimi. |
| Tespit (Md. 10) | 70+ olay türü (depo yaşam döngüsü, yedekleme, senkronizasyon, terminal dahil). Kullanıcı ve ekip bazında filtreleme ile yönetici paneli ve portal. Makine işlemleri savunmada derinlik için sistem günlüklerinde de yer alır. |
| Müdahale ve kurtarma (Md. 11) | Anlık geri alma için CoW anlık görüntüler. `rdc repo push/pull` ile çoklu hedefli kurtarma. Fork tabanlı felaket kurtarma testi. |
| Üçüncü taraf BİT riski (Md. 28-30) | Kendi sunucunuzda barındırma "kritik üçüncü taraf BİT sağlayıcı" sınıflandırmasını tamamen ortadan kaldırır. |
| Dijital operasyonel dayanıklılık testi (Md. 24-27) | CoW klonlama, veri açığa çıkmadan üretim benzeri ortamlarda tehdit yönelimli penetrasyon testini mümkün kılar. Klonla, test et, yok et. |

### Üçüncü Taraf BİT Sağlayıcı Riski

DORA'nın en ağır gereksinimleri kritik üçüncü taraf BİT sağlayıcılarının yönetimi ile ilgilidir (Md. 28-30). Finansal kuruluşlar BİT sağlayıcı kayıtları tutmalı, risk değerlendirmeleri yapmalı, belirli sözleşme hükümleri müzakere etmeli ve çıkış stratejileri planlamalıdır.

Kendi sunucunuzda barındırılan Rediacc bunu tamamen önler. Kaydedilecek, değerlendirilecek veya izlenecek üçüncü taraf BİT sağlayıcı yoktur. Finansal kuruluş kendi altyapısını doğrudan kontrol eder.

### Dayanıklılık Testi

DORA, büyük kurumlar için tehdit yönelimli penetrasyon testi (TLPT) dahil dijital operasyonel dayanıklılık testini zorunlu kılar (Md. 26). CoW klonlama bunu doğrudan karşılar:

1. Üretim ortamını fork'lama (anlık, aynı makine, veri aktarımı yok)
2. Fork'a karşı penetrasyon testleri çalıştırma
3. Tamamlandığında fork'u yok etme

Üretim asla dokunulmaz, ancak test ortamı tam bir replikadır. Hiçbir veri makineyi terk etmez.
