---
title: "Hesap Yönetimi"
description: "Rediacc'ta organizasyonlar, ekipler, üyeler ve abonelikler."
category: Guides
order: 12
language: tr
sourceHash: "831d135df1656850"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

### Organizasyonlar

Kayıt olduğunuzda, Rediacc sizin için otomatik olarak bir organizasyon oluşturur. Organizasyonunuz tüm kaynaklar için üst düzey kapsayıcıdır -- makineler, depolar, abonelikler ve ekip üyeleri.

![Registration Flow](/img/account-registration-flow.svg)

Her organizasyonun sahip olduğu özellikler:
- Benzersiz bir ad (varsayılan olarak e-posta adresiniz)
- Bir abonelik planı (COMMUNITY ile başlar)
- Varsayılan bir ekip (tüm üyeler otomatik olarak katılır)

### Üyeler ve Roller

Organizasyonlar üç rolü destekler:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rol | Yetenekler |
|-----|-----------|
| **Owner** | Tam kontrol: faturalama, sahiplik aktarımı, tüm üyeleri ve ekipleri yönetme |
| **Admin** | Üyeleri davet etme ve kaldırma, ekip oluşturma ve yönetme, API tokenlerini iptal etme |
| **Member** | Organizasyon verilerini görüntüleme, API tokenleri oluşturma, atanan ekiplere erişim |

Üye davet etme:
```bash
# Portal üzerinden: Organizasyon > Üyeler > Davet Et
# Veya API aracılığıyla
```

Bir üye kaldırıldığında, API tokenleri ve config storage tokenleri otomatik olarak iptal edilir.

### Ekipler

Ekipler, bir organizasyon içinde kaynakları sınırlandırmanıza olanak tanır. Her organizasyon varsayılan bir ekiple başlar.

![Team Structure](/img/account-team-structure.svg)

Ekip rolleri:
- **Team Admin**: Ekip içinde üye ekleyebilir/kaldırabilir
- **Member**: Ekip kapsamındaki kaynaklara erişebilir

Organizasyon sahipleri ve yöneticileri, açık üyelik olmadan tüm ekiplere otomatik olarak erişebilir.

### Abonelikler ve Planlar

Rediacc dört plan sunar:

| Plan | Makineler | Depo Lisansı/ay | Delegasyon sertifikası varsayılan / maks | Özellikler |
|------|-----------|-----------------|----------------------------------------|------------|
| COMMUNITY | 2 | 500 | 15g / 30g | Temel |
| PROFESSIONAL | 5 | 5.000 | 60g / 120g | İzin grupları, denetim günlüğü, özel marka, öncelikli destek |
| BUSINESS | 20 | 20.000 | 90g / 180g | Ceph, gelişmiş analitik, kuyruk önceliği, gelişmiş kuyruk |
| ENTERPRISE | 50 | 100.000 | 120g / 365g | Özel hesap yöneticisi |

![Subscription Flow](/img/account-subscription-flow.svg)

Tüm planlar 3 günlük bir ek süre ile başlar. Makine aktivasyonları ekip bazında izlenir ve hareketsizlik sonrası otomatik olarak serbest bırakılır. Makine lisansı ile depo lisansı modeli hakkında ayrıntılı bilgi için [Abonelik ve Lisanslama](/tr/docs/subscription-licensing) sayfasına bakın.

### Faturalama

Yalnızca organizasyonun **sahibi** faturlamayı yönetebilir:
- Plan yükseltmeleri için Stripe ödeme oturumu oluşturma
- Ödeme yöntemi değişiklikleri için Stripe faturalama portalına erişim
- Self-servis geri ödeme talep etme (14 gün içinde, 30 günlük bekleme süresiyle)

### Veri Bölgesi

Hesabınız, kayıt sırasında seçtiğiniz veri bölgesinde depolanır (AB, ABD veya Asya Pasifik). Bu tercih kalıcıdır. Portaldaki bölge rozeti, verilerinizin hangi bölgede bulunduğunu gösterir. Ayrıntılar için [Veri Bölgeleri](/en/docs/data-regions) sayfasına bakın.

### Edge Kanalı

Hesabınız Edge kanalındaysa, portal kenar çubuğunda "Edge" rozeti görünür. Edge hesapları 2X Community sınırlarına sahiptir ancak ücretli planlara erişim yoktur. Edge ile Stable arasındaki farklar için [Yayın Kanalları](/en/docs/release-channels) sayfasına bakın.

### Delegasyon Sertifikaları

Şirket içi ve hava boşluklu dağıtımlar için müşteri portalındaki **/account/delegation-certs** sayfasından kendi delegasyon sertifikalarınızı yönetebilirsiniz. Bu sayfa, plan düzeyinden bağımsız olarak tüm müşterilere görünür; yalnızca katman başına geçerlilik varsayılanları farklılık gösterir.

#### Rol Kısıtlamaları

| Eylem | Org Owner | Org Admin | Member |
|-------|-----------|-----------|--------|
| Sertifikaları listeleme / görüntüleme / indirme | ✓ | ✓ | ✓ |
| Yeni sertifika oluşturma | ✓ | ✓ | ✗ |
| Sertifika iptal etme | ✓ | ✓ | ✗ |
| Otomatik yenileme tokeni oluşturma | ✓ | ✓ | ✗ |
| Hava boşluklu yenileme isteğini işleme | ✓ | ✓ | ✗ |

Üyeler listeyi görebilir ve mevcut sertifikaları indirebilir (sertifikayı bir makine filosuna dağıtmak için kullanışlıdır), ancak yalnızca sahipler ve yöneticiler sertifika oluşturabilir veya iptal edebilir.

#### Tek Aktif Sertifika Zorunluluğu

Bir abonelikte **aynı anda yalnızca bir aktif delegasyon sertifikası** bulunabilir. Her şirket içi kurulum, aylık ve makine başına kotaları kendi yerel defterine göre uygular; birden fazla aktif sertifika, uzlaştırma imkansız şekilde efektif kotayı çoğaltır.

Bir tane zaten aktifken ikinci sertifika oluşturmaya çalışırsanız, portal iki seçenekli bir iletişim kutusu gösterir:

- **Yenile (önerilen)** - mevcut zinciri uzatır. Daha önce düzenlenmiş tüm depo lisansları yenilenen sertifika altında çalışmaya devam eder. Aynı şirket içi kurulumda süresi dolmak üzere olan bir sertifikayı döndürürken bu seçeneği kullanın.
- **İptal Et ve Yeni Oluştur** - mevcut zinciri atar ve baştan başlar. ESKİ sertifikanın validUntil tarihi geçtikten sonra daha önce düzenlenmiş depo lisansları doğrulanamaz hale gelir. Yalnızca farklı bir imzalama anahtarıyla yeni bir şirket içi kuruluma geçiş yaptığınızda veya ele geçirilmiş bir anahtardan kurtarırken kullanın.

Ayrı ortamlara (üretim + hazırlık + DR + çok bölgeli) ihtiyaç duyuyorsanız, her kurulum için ayrı bir abonelik satın alın.

#### Otomatik Yenileme Başlangıcı

Şirket içi otomatik yenilemeyi etkinleştirmek için Delegasyon Sertifikaları sayfasındaki **Otomatik yenileme tokeni al** düğmesine tıklayın. Bu, `delegation:renew` kapsamlı bir api tokeni (kalıcı, süre sonu yok) oluşturur ve şirket içi `.env` dosyanıza yapıştırmanız gereken değerleri gösterir:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

Token **yalnızca** delegasyon sertifikası yenilemesine izin verir; başka hiçbir kaynağı okuyamaz veya değiştiremez. Bu, `delegation:renew` tokeni oluşturmanın tek yoludur; normal `/portal/api-tokens` akışı bu kapsamı içermez.

#### Hava Boşluklu Yenileme

Şirket içi kurulumunuzun giden HTTPS erişimi yoksa çevrimdışı manifest akışını kullanın:

1. Şirket içi yönetici sayfasında **Yenileme isteğini indir** düğmesine tıklayın. Şirket içi sistem, yerel zincir başını içeren imzalı bir manifest oluşturur.
2. Manifesti yukarı akış sistemine aktarın (USB, şifreli e-posta veya herhangi bir kanal).
3. Yukarı akış portalında **Yenileme isteğini yükle** seçeneğine tıklayın ve manifesti seçin. Yukarı akış, manifest imzasını doğrular, yeni bir sertifika düzenler ve bunu indirilebilir bir `.json` olarak döndürür.
4. Yeni sertifikayı şirket içi ortama geri aktarın ve şirket içi yönetici sayfası aracılığıyla yükleyin.

Yukarı akış, 7 günden eski manifestleri reddeder. Adım adım kurulum için [Şirket İçi Kurulum](/en/docs/on-premise) sayfasına, kriptografik tasarım için [Lisans Zinciri ve Delegasyon](/en/docs/license-chain) sayfasına bakın.

#### Hız Sınırı

Sertifika oluşturma, başarısız girişimler dahil (çakışma spam'i, geçersiz giriş) abonelik başına **24 saatlik yuvarlanan periyotta 10 girişim** ile sınırlandırılmıştır. Limite ulaşırsanız portal, tekrar deneyebileceğiniz zamanı belirten bir `Retry-After` değeri gösterir.
