---
title: "SOC 2 Uyumluluğu"
description: "SOC 2'nin özü: denetçiler kontrollerinizin çalıştığına dair kanıt isterler. Rediacc size günlükleri, değişiklik yönetimi izini ve denetçilerin talep edecekleri her şeyi sağlar."
category: "Legal"
order: 2
language: tr
sourceHash: "27d2366f84e21d8c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

SOC 2'yi biliyorum çünkü denetim toplantılarında bulundum. Denetçiler, kontrollerinizin gerçekten çalıştığını kontrol etmek için AICPA çerçevesini kullanırlar; sadece söze inanmak değil. Beş Güven Hizmeti Kriterleri: güvenlik, kullanılabilirlik, işleme bütünlüğü, gizlilik ve mahremiyet.

Referans: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Güven Hizmeti Kriterleri Eşlemesi

| Güven ilkesi | Kriter | Rediacc Yeteneği |
|-------------|--------|-----------------|
| **Güvenlik** (CC6) | Mantıksal erişim kontrolleri, şifreleme | Durağan halde LUKS2 AES-256 şifreleme. Kimlik bilgileri yalnızca operatörün yerel yapılandırmasında (`~/.config/rediacc/`) saklanır, asla sunucuda değil. SSH anahtar tabanlı erişim. Depo başına izole Docker daemon'ları. |
| **Kullanılabilirlik** (A1) | Sistem kurtarma ve dayanıklılık | `rdc repo push/pull` ile SSH, S3, B2, Azure veya GDrive'a şifreli uzak site kopyaları. Anlık geri alma için CoW anlık görüntüleri. Kesintisiz değişiklikler için fork tabanlı yükseltmeler. |
| **İşleme bütünlüğü** (PI1) | Doğru ve eksiksiz işleme | Belirleyici Rediaccfile yaşam döngüsü kancaları (`up`/`down`) tutarlı dağıtımlar sağlar. `rdc repo validate` beklenmedik kapanmalar veya yedekleme işlemlerinden sonra depo bütünlüğünü ve yedekleme sağlığını doğrular. |
| **Gizlilik** (C1) | Yetkisiz erişime karşı veri koruması | Benzersiz LUKS kimlik bilgileri ile depo başına şifreleme. iptables, ayrı Docker daemon'ları ve loopback IP alt ağları ile ağ izolasyonu. Farklı depolardan konteynerler birbirini göremez. Sıfır bilgi yapılandırma deposu yapılandırmaları yüklenmeden önce istemci tarafında şifreler. Sunucu yalnızca çözemediği opak blob'lar saklar. |
| **Mahremiyet** (P1-P8) | Kişisel veri işleme | Kendi sunucunuzda barındırma: işlemler sırasında veri çıkışı yok. Tüm veri erişimi için denetim izi. Şifreleme anahtar yönetimi müşteri kontrolünde. Yapılandırma deposu bölünmüş anahtar türetme (passkey PRF + sunucu sırrı) kullanır, böylece hiçbir taraf tek başına verilere erişemez. |

## Denetim İzi

Rediacc 70+ farklı olay türünü kaydeder. Kullanıcı işlemleri, sistem değişiklikleri, yapılandırma güncellemeleri, erişim kontrolü değişiklikleri, güvenlik olayları, fork işlemleri, denetim izleri. Çok gibi gelebilir, ama denetçiler gerçekten bunu görmek isterler.

- **Kimlik doğrulama**: giriş, çıkış, parola değişiklikleri, 2FA etkinleştirme/devre dışı bırakma, oturum iptali
- **Yetkilendirme**: API token oluşturma/iptali, rol değişiklikleri, ekip üyeliği
- **Yapılandırma**: yapılandırma deposu push/pull, üye yönetimi, erişim hataları (IP uyuşmazlığı, SDK reddi)
- **Lisanslama**: depo lisans verilişi, makine yuvası izleme, abonelik değişiklikleri
- **Makine işlemleri**: depo oluştur/başlat/durdur/sil, fork, yedekleme push/pull, dosya senkronizasyonu, terminal oturumları

Bu günlüklere ulaşmanın üç yolu var. Yönetici panosu kullanıcı, ekip ve tarih filtrelemesi ile. Org yöneticileri için portal aktivite sayfası tür ve tarih filtrelemesi ile. Ya da `rdc audit` CLI programatik dışa aktarım için. Günlükleri kendi araçlarınıza aktarabilir, istediğiniz yerde entegre edebilirsiniz. Makine işlemleri sistem günlüklerinize de kaydedilir, böylece çok katmanlı korumaya sahip olursunuz.

## Değişiklik Yönetimi

Fork'lar değişiklik yönetimini denetlenebilir hale getirir: her fork, test edebileceğiniz, gözden geçirebileceğiniz ve tanıtabileceğiniz ya da silebileceğiniz canlı durum kopyasıdır; her adım bir aktöre zaman damgasıyla kaydedilmiştir.

1. Üretim deposunu fork'lama (`rdc repo fork`)
2. Fork üzerinde değişiklikleri uygulama ve test etme
3. Fork'u bağımsız olarak doğrulama
4. Fork'u üretime yükseltme (`rdc repo takeover`)

Her adım zaman damgaları ve aktör kimliği ile kaydedilir.

## Erişim Kontrolü

- **Makine erişimi**: Yalnızca SSH anahtar kimlik doğrulaması. Parola tabanlı SSH yok.
- **API token'ları**: Kapsamlı izinler, isteğe bağlı IP bağlama, ekipten çıkarılma durumunda otomatik iptal.
- **Depo izolasyonu**: Her depo kendi Docker daemon soketine sahiptir. Bir depoya erişim, aynı makinedeki diğerine erişim sağlamaz.
- **Yapılandırma deposu token'ları**: İlk kullanımda IP bağlama, 24 saatlik otomatik süre sona erme ve eşzamanlılık için 3 isteklik tolerans penceresi ile tek kullanımlık dönen token'lar. X25519 anahtar değişimi ile anında iptal özellikli üye erişim yönetimi.
