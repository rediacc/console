---
title: "SOC 2 Uyumluluğu"
description: "Rediacc'ın SOC 2 kanıtı nerede sunduğu: günlükler, değişiklik yönetimi izi ve denetçilerin sorduğu kontroller."
category: "Legal"
order: 2
language: tr
sourceHash: "29b0c745e631e4f8"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

SOC 2, denetçilerin kontrollerinizin gerçekten çalıştığına dair kanıt istediklerinde başvurdukları AICPA çerçevesidir. Beş Güven Hizmeti Kriterini kapsar: güvenlik, kullanılabilirlik, işleme bütünlüğü, gizlilik ve mahremiyet.

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

Rediacc hesap düzeyinde 40'tan fazla olay türünü kaydeder:

- **Kimlik doğrulama**: giriş, çıkış, parola değişiklikleri, 2FA etkinleştirme/devre dışı bırakma, oturum iptali
- **Yetkilendirme**: API token oluşturma/iptali, rol değişiklikleri, ekip üyeliği
- **Yapılandırma**: yapılandırma deposu push/pull, üye yönetimi, erişim hataları (IP uyuşmazlığı, SDK reddi)
- **Lisanslama**: makine aktivasyonu, lisans yayınlama, abonelik değişiklikleri

Bu günlükler yönetici paneli (kullanıcı, ekip ve tarih bazında filtreleme ile) ve programatik dışa aktarım için `rdc audit` CLI üzerinden erişilebilir. Makine düzeyindeki işlemler (fork, yedekleme, dağıtım) altyapınızda SSH üzerinden yürütülür, dolayısıyla bu denetim izleri sistem günlüklerinizde bulunur.

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
