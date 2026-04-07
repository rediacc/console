---
title: "Veri Bölgeleri"
description: "Verilerinizin nerede saklandığı ve bölgesel veri yerleşiminin nasıl çalıştığı."
category: "Concepts"
order: 3
language: tr
sourceHash: "613595b3941c6186"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Bir Rediacc hesabı oluşturduğunuzda bir veri bölgesi seçersiniz. Tüm verileriniz o bölgede kalır. Bu seçim kalıcıdır ve kayıt sonrasında değiştirilemez.

## Mevcut Bölgeler

| Bölge | Konum | Alan Adı |
|---|---|---|
| **Avrupa (EU)** | Frankfurt, Almanya | `eu.rediacc.com` |
| **Amerika Birleşik Devletleri (US)** | Virginia, ABD | `us.rediacc.com` |
| **Asya Pasifik** | Tokyo, Japonya | `asia.rediacc.com` |

Bölgeniz kayıt sırasında saat diliminizden otomatik olarak algılanır. Bölge seçicisinde öneriyi geçersiz kılabilirsiniz.

## Bölgenizde Kalan Veriler

Bu veri türleri yalnızca seçtiğiniz bölgede depolanır ve işlenir:

- **Hesap verileri**: e-posta, ad, organizasyon, takım üyelikleri
- **Faturalama ve abonelik kayıtları**: plan, aktivasyonlar, lisans düzenlemeleri
- **Şifreli yapılandırma blob'ları**: sıfır bilgi şifrelenmiş, istemci tarafında. Sunucu bunların şifresini çözemez.
- **İşlemsel e-postalar**: parola sıfırlama, magic link'ler, bildirimler. Bölgesel e-posta uç noktasından gönderilir.

## Global Olanlar

Bunlar bölgeye özgü değildir:

- **CLI sürüm artefaktları**: global CDN üzerinde barındırılan genel ikili dosyalar
- **Pazarlama sitesi**: edge konumlarından global olarak sunulur
- **Stripe ödeme işleme**: Stripe'ın kendi veri işleme anlaşması kapsamındaki altyapısı tarafından yönetilir

## Bölgesel Altyapı

| Bileşen | EU | US | Asya |
|---|---|---|---|
| Veritabanı (D1) | Doğu Avrupa (EEUR) | Doğu Kuzey Amerika (ENAM) | Asya Pasifik (APAC) |
| Yapılandırma depolama (R2) | AB yetki alanı | US | Asya Pasifik |
| E-posta (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Tokyo (ap-northeast-1) |

Her bölge bağımsız altyapı üzerinde çalışır. Bölgeler arasında çapraz bölge sorguları veya veri akışları yoktur.

## AB Veri Güvenceleri

AB bölgesi, Avrupa veri yerleşimi gereksinimlerine sahip organizasyonlar için ek güvenceler sağlar:

- **D1 veritabanı**: Doğu Avrupa'da çalışır (EEUR konum ipucu)
- **R2 yapılandırma depolama**: AB yetki alanı uygulaması kullanır (yalnızca konum ipucu değil, sözleşmeli güvence)
- **E-posta**: Frankfurt'tan gönderilir (eu-central-1)
- **AB-Japonya karşılıklı yeterlilik kararı (2019)**: Asya bölgesinin altyapısı için uyumlu veri akışlarını etkinleştirir

Ayrıntılı GDPR eşlemesi için [GDPR Uyumluluğu](/tr/docs/legal-gdpr) sayfasına bakın.

## Sıfır Bilgi Şifreleme

R2'de depolanan yapılandırma blob'ları, yüklenmeden önce X25519 anahtar değişimi ve AES-256-GCM kullanılarak istemci tarafında şifrelenir. Sunucu yalnızca şifreli metni tutar. Ne Rediacc ne de herhangi bir altyapı sağlayıcısı yapılandırma verilerinizi okuyabilir.

Anahtarlar, PRF uzantılı bir geçiş anahtarından türetilir. Sunucu, anahtar türetmeye katılan sunucu tarafı bir sır saklar; ancak geçiş anahtarı tek başına veya sunucu sırrı tek başına verilerin şifresini çözemez.

Şifreleme mimarisinin ayrıntıları için [Yapılandırma Depolama](/tr/docs/config-storage) sayfasına bakın.

## Nasıl Seçilir

- **En düşük gecikme için size en yakın bölgeyi seçin.**
- **Uyumluluk için organizasyonunuzun gerektirdiği bölgeyi seçin.** Şirketiniz AB veri yerleşimi zorunlu kılıyorsa, AB'yi seçin.
- **Seçim kalıcıdır.** Kayıt sonrasında hesabınızı farklı bir bölgeye taşıyamazsınız.

## Uyum Görevlileri İçin

Bölgesel mimarinin teknik özellikleri:

- **Bölge başına ayrı veritabanları**: her bölgenin kendi Cloudflare D1 veritabanı vardır. Çapraz bölge sorgusu yoktur.
- **Bölge başına ayrı depolama**: her bölgenin kendi R2 bucket'ı vardır. AB yetki alanı uygulaması kullanır.
- **Bölge başına ayrı e-posta uç noktaları**: işlemsel e-postalar bölgesel AWS SES uç noktalarından gönderilir.
- **Bir kullanıcı, bir bölge**: kullanıcı hesabı tam olarak bir bölgede bulunur. Birden fazla bölgeye yayılamaz.
- **Webhook izolasyonu**: Stripe webhook olayları tüm bölgesel worker'lar tarafından alınır ancak yalnızca müşteri kaydına sahip olan bölge tarafından işlenir.
- **Sıfır bilgi yapılandırma şifreleme**: sunucu yapılandırma verilerini okuyamaz. Şifreleme anahtarları asla istemci cihazından çıkmaz.

Veri egemenliği uyumluluğuna daha geniş bir bakış için [Veri Egemenliği](/tr/docs/legal-data-sovereignty) sayfasına bakın.
