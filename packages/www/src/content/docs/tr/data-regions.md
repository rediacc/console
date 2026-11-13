---
title: "Veri Bölgeleri"
description: "Verilerinizin nerede saklandığı ve bölgesel veri yerleşiminin nasıl çalıştığı."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: tr
sourceHash: "05afa82e66e34693"
sourceCommit: "f9c980842b182e644eb84eb1d37e394baf60f7a5"
---

Bir Rediacc hesabı oluşturduğunuzda bir veri bölgesi seçersiniz. Tüm verileriniz o bölgede kalır. Bu seçim kalıcıdır ve kayıt sonrasında değiştirilemez. Geçiş yolu yoktur. Verilerinizin yasal olarak nerede bulunması gerektiğine göre seçin, bugün sunucularınızın nerede olduğuna göre değil.

## Mevcut Bölgeler

| Bölge | Konum | Alan Adı |
|---|---|---|
| **Avrupa (EU)** | Avrupa Birliği | `eu.rediacc.cloud` |
| **Amerika Birleşik Devletleri (US)** | Doğu Kuzey Amerika | `us.rediacc.cloud` |
| **Asya Pasifik** | Asya Pasifik | `asia.rediacc.cloud` |

Konum sütunu bir veri merkezi şehrini değil, bir Cloudflare bölgesini gösterir. Cloudflare herhangi bir şehir vaat etmez.

Ürün bu `rediacc.cloud` etki alanlarında çalışır. Tüm dokümantasyon ve pazarlama sitesi `www.rediacc.com` üzerindedir; site, bölge seçicisiyle sizi doğru bölgeye yönlendirir.

Kayıt sırasında seçici, konumunuza göre bir bölge önerir; onaylayabilir veya değiştirebilirsiniz. Girişte ise iptal edebileceğiniz ya da değiştirebileceğiniz kısa bir geri sayımın ardından sizi bölgenize yönlendirir. Şirketinizin kendi dağıtımı varsa seçicideki "Enterprise müşterisi misiniz?" seçeneği sizi iş e-posta adresinizden yola çıkarak oraya götürür. Bölgeyi bulmak için yalnızca etki alanı gönderilir; e-posta adresi yalnızca oturum açma sayfasını önceden doldurur.

## Bölgenizde Kalan Veriler

Bu veri türleri seçtiğiniz bölgede depolanır ve işlenir (nelerin garanti edildiği için aşağıdaki bölgesel altyapı bölümüne bakın):

- **Hesap verileri**: e-posta, ad, organizasyon, takım üyelikleri
- **Faturalama ve abonelik kayıtları**: plan, aktivasyonlar, lisans düzenlemeleri
- **Şifreli yapılandırma blob'ları**: sıfır bilgi şifrelenmiş, istemci tarafında. Sunucu bunların şifresini çözemez.
- **İşlemsel e-postalar**: parola sıfırlama, magic link'ler, bildirimler. Bölgesel e-posta uç noktasından gönderilir.

## Global Olanlar

Bunlar bölgeye özgü değildir:

- **CLI sürüm artefaktları**: global CDN üzerinde barındırılan genel ikili dosyalar
- **Pazarlama sitesi ve dokümantasyon**: `www.rediacc.com`, edge konumlarından global olarak sunulur
- **Stripe ödeme işleme**: Stripe'ın kendi veri işleme anlaşması kapsamındaki altyapısı tarafından yönetilir

## Bölgesel Altyapı

| Bileşen | EU | US | Asya |
|---|---|---|---|
| Veritabanı (D1) | Doğu Avrupa ipucu (EEUR) | Doğu Kuzey Amerika ipucu (ENAM) | Asya Pasifik ipucu (APAC) |
| Yapılandırma depolama (R2) | AB yetki alanı (garantili) | Yetki alanı yok (elinden gelenin en iyisi) | Yetki alanı yok (elinden gelenin en iyisi) |
| E-posta (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Yalnızca AB yapılandırma depolaması garanti edilen bir yetki alanına bağlıdır: Cloudflare, AB yetki alanındaki R2 nesnelerini AB içinde tutar. D1 veritabanının yerleşimi ile US ve Asya Pasifik depolaması konum ipuçlarını kullanır ve bunlar elinden gelenin en iyisi esasıyla uygulanır. Cloudflare, bunların ipucu verilen bölgede çalışacağını garanti etmez.

Her bölge bağımsız altyapı üzerinde çalışır. Bölgeler arasında çapraz bölge sorguları veya veri akışları yoktur.

## AB Veri Güvenceleri

Avrupa veri yerleşimi gereksinimlerine tabiyseniz AB bölgesi tek bir kesin güvence ve elinden gelenin en iyisi esasıyla bir yerleşim sunar:

- **D1 veritabanı**: EEUR (Doğu Avrupa) konum ipucuyla yerleştirilir; bu elinden gelenin en iyisi esasıdır, garanti değildir
- **R2 yapılandırma depolaması**: AB yetki alanına bağlıdır ve Cloudflare bunu garanti eder (yalnızca konum ipucu değil, kesin bir kısıtlama)
- **E-posta**: Frankfurt'tan gönderilir (eu-central-1)

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
- **Bölge başına ayrı depolama**: her bölgenin kendi R2 bucket'ı vardır. Yalnızca AB bucket'ı bir yetki alanına bağlıdır; US ve Asya Pasifik elinden gelenin en iyisi esasıyla yerleştirilir.
- **AWS SES aracılığıyla e-posta teslimi**: işlemsel e-postalar AWS SES aracılığıyla gönderilir. AB ve US, özel bölgesel uç noktalar kullanır; Asya Pasifik, AB uç noktası (eu-central-1) üzerinden yönlendirilir.
- **Bir kullanıcı, bir bölge**: kullanıcı hesabı tam olarak bir bölgede bulunur. Birden fazla bölgeye yayılamaz.
- **Webhook izolasyonu**: Stripe webhook olayları tüm bölgesel worker'lar tarafından alınır ancak yalnızca müşteri kaydına sahip olan bölge tarafından işlenir.
- **Sıfır bilgi yapılandırma şifreleme**: sunucu yapılandırma verilerini okuyamaz. Şifreleme anahtarları asla istemci cihazından çıkmaz.

Veri egemenliği uyumluluğuna daha geniş bir bakış için [Veri Egemenliği](/tr/docs/legal-data-sovereignty) sayfasına bakın.
