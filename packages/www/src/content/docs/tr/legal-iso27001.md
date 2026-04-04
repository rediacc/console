---
title: "ISO 27001 Uyumluluğu"
description: "Rediacc'ın şifreleme, erişim yönetimi ve operasyon güvenliği için ISO 27001 bilgi güvenliği kontrollerine nasıl uyum sağladığı."
category: "Legal"
order: 5
language: tr
sourceHash: "fdea800f46a7d3ec"
---

ISO/IEC 27001, Uluslararası Standardizasyon Örgütü (ISO) ve Uluslararası Elektroteknik Komisyonu (IEC) tarafından yayımlanan bilgi güvenliği yönetim sistemleri (BGYS) için uluslararası bir standarttır. Mevcut sürüm ISO/IEC 27001:2022'dir.

Referans: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc, bir BGYS içindeki teknik kontrol katmanının bir bileşenidir. Aşağıdaki tablo, Rediacc'ın yeteneklerini ilgili Ek A kontrol alanlarıyla eşleştirir.

## Ek A Kontrol Eşlemesi

| Kontrol alanı | Kontrol | Rediacc Yeteneği |
|--------------|---------|-----------------|
| **A.8**, Varlık yönetimi | A.8.1 Varlık envanteri | Her depo benzersiz bir GUID'e sahip ayrı, tanımlanabilir bir varlıktır. `rdc machine query <machine> --repositories` tüm depoları boyut, bağlama durumu ve konteyner sayısı ile listeler. |
| **A.8**, Varlık yönetimi | A.8.24 Kriptografi kullanımı | Tüm depolarda zorunlu LUKS2 AES-256 şifreleme. Anahtar yönetimi: kimlik bilgileri yalnızca operatörün yerel yapılandırmasında saklanır, asla sunucuda değil. |
| **A.9**, Erişim kontrolü | A.9.2 Kullanıcı erişim yönetimi | SSH anahtar kimlik doğrulaması. IP bağlama, ekip kapsamı ve ekipten çıkarılma durumunda otomatik iptal ile API token'ları. İki faktörlü kimlik doğrulama (TOTP). |
| **A.10**, Kriptografi | A.10.1 Kriptografik kontroller | Yapılandırılabilir anahtar parametreleri ile LUKS2. Depo başına şifreleme kimlik bilgileri. Tüm uzak aktarım SSH üzerinden. Yapılandırma deposu sıfır bilgi şifrelemesi uygular: HKDF anahtar türetme ile AES-256-GCM, üyeler için X25519 anahtar değişimi ve anında iptal için zaman pencereli SDK anahtarları. |
| **A.12**, Operasyon güvenliği | A.12.3 Yedekleme | `rdc repo backup push/pull` ile birden fazla hedefe (SSH, S3, B2, Azure, GDrive) şifreli uzak site depolama. Belirli bir zamana geri dönüş için CoW anlık görüntüleri. `rdc repo validate` yedekleme sağlığını ve depo bütünlüğünü doğrular. |
| **A.12**, Operasyon güvenliği | A.12.4 Günlük kaydı ve izleme | Hesap düzeyinde 40'tan fazla olay türü (kimlik doğrulama, API token'ları, yapılandırma, lisanslama). `rdc machine query` ile makine sağlığı izleme. Konteyner durumu ve kaynak izleme. |
| **A.13**, İletişim güvenliği | A.13.1 Ağ güvenliği yönetimi | Depo başına Docker daemon izolasyonu. iptables kuralları depolar arası trafiği engeller. Depo başına loopback IP alt ağları (/26). Dış erişim için TLS sonlandırma ile ters proxy. |
| **A.14**, Sistem geliştirme | A.14.2 Geliştirmede güvenlik | Fork tabanlı geliştirme ortamları üretim verisi açığa çıkarmadan üretim eşdeğerliği sağlar. Rediaccfile yaşam döngüsü kancaları klonlanmış ortamlarda otomatik veri temizleme sağlar. |

## Varlık Yönetimi

Rediacc'ın depo modeli varlık envanteri gereksinimlerini doğal olarak destekler:

- Her depoya oluşturulduğunda benzersiz bir GUID atanır
- Depolar makine başına numaralandırılabilir (`rdc machine query --repositories`)
- Her deponun şifreleme durumu, bağlama durumu, konteyner sayısı ve disk kullanımı görünürdür
- Fork ilişkileri klonlanmış ortamların soy ağacını takip eder

## Değişiklik Yönetimi

Fork-test-yükseltme iş akışı ISO 27001'in değişiklik yönetimi gereksinimlerine uygundur:

1. **Fork**: Üretim ortamının izole bir kopyasını oluşturma
2. **Test**: Fork üzerinde değişiklikleri uygulama ve doğrulama
3. **Yükseltme**: Fork'u üretime almak için `rdc repo takeover` kullanma
4. **Denetim**: Tüm işlemler zaman damgaları ve aktör kimliği ile kaydedilir

## Sürekli İyileştirme

- Denetim günlüğü dışa aktarımı periyodik güvenlik incelemelerini destekler
- Makine sağlık kontrolleri (`rdc machine query --system`) operasyonel izlemeyi destekler
- `rdc repo validate` her işlemden sonra yedekleme sağlığını doğrular
