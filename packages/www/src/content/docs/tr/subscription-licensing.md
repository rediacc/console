---
title: "Abonelik ve Lisanslama"
description: "account, rdc ve renet'in makine slotlarını, depo lisanslarını ve plan limitlerini nasıl yönettiğini anlayın."
category: "Guides"
order: 7
language: tr
sourceHash: "ed0aef562aad7367"
sourceCommit: "68c6d120013af4c092bcfd997ed8e9b47101be34"
---

# Abonelik ve Lisanslama

Rediacc lisanslaması üç hareketli parçadan oluşur:

- `account` hakları imzalar ve kullanımı takip eder
- `rdc` kimlik doğrular, lisans talep eder, makinelere iletir ve çalışma zamanında uygular
- `renet` (makine üzerindeki çalışma zamanı) hesap sunucusuna başvurmadan yüklü lisansları yerel olarak doğrular

Bu sayfa, bu parçaların yerel dağıtımlarda nasıl bir araya geldiğini açıklar.

## Lisanslama Ne Yapar

Lisanslama iki farklı şeyi kontrol eder:

- **Yüzen Lisanslar** aracılığıyla **makine erişim muhasebesi**
- **depo lisansları** aracılığıyla **depo çalışma zamanı yetkilendirmesi**

Bunlar ilişkilidir, ancak aynı artefakt değildir.

## Lisanslama Nasıl Çalışır

`account`, planlar, sözleşme geçersiz kılmaları, makine slot durumu ve aylık depo lisansı düzenlemeleri için gerçeğin kaynağıdır.

`rdc` iş istasyonunuzda çalışır. Hesap sunucusuna giriş yapmanızı sağlar, ihtiyaç duyduğu lisansları talep eder ve SSH üzerinden uzak makinelere yükler. Bir depo komutu çalıştırdığınızda, `rdc` gerekli lisansların yerinde olduğundan emin olur ve çalışma zamanında makine üzerinde doğrular.

Normal akış şöyle görünür:

1. `rdc subscription login` ile kimlik doğrularsınız
2. `rdc repo create`, `rdc repo up` veya `rdc repo down` gibi bir depo komutu çalıştırırsınız
3. Gerekli lisans eksik veya süresi dolmuşsa, `rdc` bunu `account`'tan talep eder
4. `rdc` imzalı lisansı makineye yazar
5. Lisans makine üzerinde yerel olarak doğrulanır ve işlem devam eder

İş istasyonu ile sunucu ayrımı için [rdc vs renet](/tr/docs/rdc-vs-renet) sayfasına, depo yaşam döngüsü için [Depolar](/tr/docs/repositories) sayfasına bakın.

Otomasyon ve yapay zeka ajanları için tarayıcı girişi yerine kapsamlı bir abonelik tokeni kullanın:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

CLI'ın herhangi bir etkileşimli giriş adımı olmadan depo lisansları düzenleyip yenileyebilmesi için tokeni doğrudan ortam üzerinden de enjekte edebilirsiniz:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Makine Slotları ve Depo Lisansları

### Makine slotları (sunucu tarafı)

Makine slot takibi sunucu tarafında uygulanır. CLI bir depo lisansı düzenlediğinde, hesap sunucusu aboneliğin makine slot kotasını kontrol eder (örneğin, Community için 2 makine, Professional için 3). Bir slot, o makinedeki son depo lisansı düzenlemesinden itibaren 5 saat süresince tutulur ve inaktiviteden sonra otomatik olarak serbest bırakılır. Slotlar yalnızca aktif olarak sağlama yaparken tutulduğundan, 10 slotlu Business plan zaman içinde düzinelerce makineyi kapsayabilir.

Makinede hiçbir makine lisans dosyası depolanmaz. Slot uygulaması, sunucuda düzenleme zamanında gerçekleşir.

### Depo lisansı

Depo lisansı, bir makinedeki bir depo için imzalı bir lisanstır. Makinede depolanan tek lisans dosyasıdır (`/var/lib/rediacc/license/repos/{guid}.json`).

Şunlar için kullanılır:

- `rdc repo create` ve `rdc repo fork`, sağlamadan önce doğrulanır (kimlik kanıtı olmadan önceden düzenlenir, oluşturulduktan sonra kimlik kanıtlarıyla yeniden düzenlenir)
- `rdc repo resize` ve `rdc repo expand`, son kullanma tarihi dahil tam doğrulama
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, **son kullanma tarihi atlanarak** doğrulanır
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, **son kullanma tarihi atlanarak** doğrulanır
- makine yeniden başlatılırken depo otomatik başlatma, **son kullanma tarihi atlanarak** doğrulanır

Depo lisansları makineye ve hedef depoya bağlıdır. Her lisans, makine kimliği, depo GUID'i, abonelik kimliği, plan limitleri ve son kullanma tarihini içerir. Şifrelenmiş depolar için Rediacc, altta yatan birimin LUKS kimliğini de doğrular.

Aynı makinede birden fazla abonelik birlikte var olabilir. Her depo, kendi abonelik bağlamıyla birlikte kendi lisansını taşır.

## Varsayılan Limitler

Depo boyutu hak düzeyine bağlıdır:

- Community: `10 GB`'a kadar
- ücretli planlar: plan veya sözleşme limiti

Ücretli plan varsayılan limitleri:

| Plan | Değişken Lisanslar | Depo Boyutu | Aylık depo lisansı düzenlemeleri | Delegasyon sertifikası varsayılan / maks |
|------|---------------------|-------------|----------------------------------|----------------------------------------|
| Community | 2 | 10 GB | 100 | 15g / 30g |
| Professional | 3 | 50 GB | 1.000 | 60g / 120g |
| Business | 10 | 200 GB | 10.000 | 90g / 180g |
| Enterprise | 25+ | 1 TB+ | 25.000+ | 120g / 365g |

Sözleşmeye özgü limitler, belirli bir müşteri için bu değerleri artırabilir veya azaltabilir. Delegasyon sertifikası geçerliliği aynı zamanda `subscription.expiresAt + 3 günlük ek süre` ile kesin olarak sınırlandırılmıştır; dolayısıyla aylık faturalandırılan abonelikler doğal olarak faturalama döngüleriyle uyumlu sertifikalar alır. Tam kurallar için [Lisans Zinciri ve Delegasyon - Geçerlilik Politikası](/tr/docs/license-chain) sayfasına bakın.

## Makine Geçişi Uyum Dönemi

Bir barındırma sağlayıcısı VM'yi farklı fiziksel donanıma taşıdığında, makine kimliği değişir (DMI UUID, `/etc/machine-id` ve NIC MAC adresleri gibi donanım tanımlayıcılarından türetilir). Depo lisansları makine kimliğine bağlıdır, bu nedenle bir geçiş normalde tüm lisansları geçersiz kılarsa.

Bunu şeffaf bir şekilde işlemek için, depo lisansları **40 günlük makine kimliği uyum dönemini** içerir. Makine kimliği eşleşmese bile lisans 40 günden az zaman önce düzenlenmiş ise, lisans yine de kabul edilir. Lisanslar her 30 günde bir yenilendiğinden, sonraki yenileme otomatik olarak yeni makine kimliğine bağlanır.

Pratikte:
- VM taşındı, makine kimliği değişti: depolar çalışmaya devam eder (40 günlük pencere içinde)
- Sonraki `rdc` işlemi lisansı yeni makine kimliğiyle yeniler
- El ile müdahale gerekli değil
- `rdc machine query --system --licenses --name <machine>` ile makine kimliği ve lisans durumunu kontrol edin

**Edge kanalı kullanıcıları** 2X Community limitlerini ücretsiz alır (20 GB depolar, ayda 1.000 düzenleme, 4 makine). Ücretli planlar yalnızca Stable kanalında mevcuttur. Ayrıntılar için [Yayın Kanalları](/tr/docs/release-channels) sayfasına bakın.

## Depo Oluşturma, Başlatma, Durdurma ve Yeniden Başlatma Sırasında Ne Olur

### Depo Oluşturma ve Çatallaştırma

Bir depo oluşturduğunuzda veya çatalladığınızda:

1. `rdc` abonelik tokeninizin mevcut olduğundan emin olur (gerekirse cihaz kodu kimlik doğrulamasını tetikler)
2. `rdc` hesap sunucusundan bir depo lisansı önceden düzenler (sunucu bu noktada makine slot kotasını ve aylık düzenleme limitlerini kontrol eder)
3. Önceden düzenlenen depo lisansı makineye yazılır ve yerel olarak doğrulanır (imza, makine kimliği, depo GUID'i, son kullanma tarihi ve boyut limiti)
4. Başarılı oluşturmanın ardından `rdc`, depo lisansını depo kimlik kanıtlarıyla (LUKS UUID veya depolama parmak izi) yeniden düzenler

Bu hesap destekli düzenleme, aylık **depo lisansı düzenlemeleri** kullanımınıza sayılır. Her lisans, renet lisansı doğrularken günlüğe kaydedilen hesap sahibinin e-posta adresini ve şirket adını içerir.

### Depo Başlatma, Durdurma ve Silme

`rdc` makine üzerinde yüklü depo lisansını doğrular, ancak **son kullanma tarihi kontrolünü atlar**. İmza, makine kimliği, depo GUID'i ve kimlik doğrulanmaya devam eder. Kullanıcılar, süresi dolmuş bir abonelikle bile depolarını işletmekten hiçbir zaman engellenmez.

### Depo Yeniden Boyutlandırma ve Genişletme

`rdc`, son kullanma tarihi ve boyut limitleri dahil tam depo lisansı doğrulaması gerçekleştirir.

### Makine Yeniden Başlatma ve Otomatik Başlatma

Otomatik başlatma, `rdc repo up` ile aynı kuralları kullanır: son kullanma tarihi atlanır, dolayısıyla depolar her zaman serbestçe yeniden başlar.

Depo lisansları uzun süreli geçerlilik modeli kullanır:

- `refreshRecommendedAt` yumuşak yenileme noktasıdır
- `hardExpiresAt` engelleme noktasıdır

Depo lisansı eski olsa da kesin son kullanma tarihinden önce ise çalışma zamanı devam edebilir. Kesin son kullanma tarihine ulaşıldığında, `rdc`'nin resize/expand işlemleri için onu yenilemesi gerekir.

### Diğer Depo İşlemleri

Depoları listeleme, depo bilgilerini inceleme ve bağlama gibi işlemler herhangi bir lisans doğrulaması gerektirmez.

## Durumu Kontrol Etme ve Lisansları Yenileme

İnsan girişi:

```bash
rdc subscription login
```

Otomasyon veya yapay zeka ajanı girişi:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Etkileşimli olmayan ortamlar için `REDIACC_SUBSCRIPTION_TOKEN` ayarlamak en basit seçenektir. Token, ajanın ihtiyaç duyduğu abonelik ve depo lisansı işlemleriyle sınırlı kapsamda olmalıdır.

Hesap destekli abonelik durumunu göster:

```bash
rdc subscription status
```

Bir makine için makine aktivasyon ayrıntılarını göster:

```bash
rdc subscription activation status -m hostinger
```

Bir makinede yüklü depo lisansı ayrıntılarını göster:

```bash
rdc subscription repo status -m hostinger
```

Bir makinedeki depo lisanslarını toplu olarak yenile:

```bash
rdc subscription refresh repos -m hostinger
```

Makinede keşfedilen ancak yerel `rdc` yapılandırmasında bulunmayan depolar toplu yenileme sırasında reddedilir. Bunlar başarısızlık olarak raporlanır ve otomatik olarak sınıflandırılmaz.

Mevcut bir depo için depo lisansı yenilemesini zorla:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

İlk kullanımda, kullanılabilir depo lisansı bulamayan lisanslı bir depo veya yedekleme işlemi otomatik olarak hesap yetkilendirme aktarımını tetikleyebilir. CLI bir yetkilendirme URL'si yazdırır, etkileşimli terminallerde tarayıcıyı açmaya çalışır ve yetkilendirme ile düzenleme başarılı olduktan sonra işlemi bir kez yeniden dener.

Etkileşimli olmayan ortamlarda CLI, tarayıcı onayını beklemez. Bunun yerine, `rdc subscription login --token ...` veya `REDIACC_SUBSCRIPTION_TOKEN` ile kapsamlı bir token sağlamanızı ister.

İlk makine kurulumu için [Makine Kurulumu](/tr/docs/setup) sayfasına bakın.

## Çevrimdışı Davranış ve Sona Erme

Lisans doğrulaması makine üzerinde yerel olarak gerçekleşir. Hesap sunucusuna canlı bağlantı gerektirmez.

Bu şu anlama gelir:

- çalışan bir ortam her komutta hesaba canlı bağlantı gerektirmez
- tüm depolar süresi dolmuş lisanslarla bile her zaman başlatılabilir, durdurulabilir ve silinebilir; kullanıcılar kendi depolarını işletmekten hiçbir zaman engellenmez
- sağlama işlemleri (`create`, `fork`) önceden düzenlenen bir depo lisansı gerektirir ve büyüme işlemleri (`resize`, `expand`) geçerli bir depo lisansı gerektirir
- gerçekten süresi dolmuş depo lisansları, resize/expand öncesinde `rdc` aracılığıyla yenilenmelidir
- lisans imzaları gömülü bir ortak anahtar ile doğrulanır; imza doğrulama devre dışı bırakılamaz

## Kurtarma Davranışı

Otomatik kurtarma kasıtlı olarak dar tutulmuştur:

- `missing`: `rdc` gerektiğinde hesap erişimini yetkilendirebilir, depo lisanslarını toplu olarak yenileyebilir ve bir kez yeniden deneyebilir
- `expired`: `rdc` depo lisanslarını toplu olarak yenileyebilir ve bir kez yeniden deneyebilir
- `machine_mismatch`: hızla başarısız olur ve mevcut makine bağlamından yeniden düzenlemenizi ister
- `repository_mismatch`: hızla başarısız olur ve depo lisanslarını açıkça yenilemenizi ister
- `sequence_regression`: depo lisansı bütünlüğü/durum sorunu olarak hızla başarısız olur
- `invalid_signature`: depo lisansı bütünlüğü/durum sorunu olarak hızla başarısız olur
- `identity_mismatch`: hızla başarısız olur, depo kimliği yüklü lisansla eşleşmiyor

Bu hızlı başarısızlık durumları otomatik olarak hesap destekli yenileme veya düzenleme çağrısı tüketmez.

## Şirket İçi Kurulum için Delegasyon Sertifikaları

Şirket içi ve hava boşluklu dağıtımlar için, yukarı akış hesap sunucusu, şirket içi kurulumunuzun kendi Ed25519 anahtarıyla lisans imzalamasına izin veren bir **delegasyon sertifikası** düzenler. Sertifika, şirket içi kurulumu plan limitleriyle kısıtlar ve kurcalamaya karşı kanıt niteliğinde bir zincir oluşturur.

Abonelik sahipleri için temel noktalar:

- **Abonelik başına bir aktif sertifika.** Her şirket içi kurulum, aylık ve makine başına kotaları kendi yerel defterine göre uygular; çoklu kurulum, uzlaştırma imkansız şekilde efektif kotayı çoğaltır. Üretim + hazırlık + DR gerektiren müşteriler her kurulum için ayrı abonelik satın almalıdır.
- **Katman bazlı varsayılan geçerlilik** (15g / 60g / 90g / 120g) ve tavanlar (30g / 120g / 180g / 365g) - yukarıdaki limitler tablosuna bakın.
- **Müşteri portalından self-servis.** Org sahipleri ve yöneticileri `/account/delegation-certs` adresinden delegasyon sertifikası oluşturabilir, yenileyebilir ve iptal edebilir. Bu sayfa plan düzeyinden bağımsız olarak tüm müşterilere görünür; yalnızca limitler farklılık gösterir.
- **Otomatik yenileme**, şirket içi kurulumun yukarı akış yenileme çağrıları için kullanacağı `delegation:renew` kapsamlı bir api tokeni oluşturan tek tıklamalı başlangıç aracılığıyla desteklenir.
- **Hava boşluklu yenileme**, şirket içi yöneticinin indirdiği, çevrimdışı olarak yukarı akışa aktardığı ve yukarı akışın yeni sertifika düzenlemek için işlediği imzalı bir yenileme isteği manifesti aracılığıyla desteklenir.

Operasyonel kurulum için [Şirket İçi Kurulum - Hava Boşluklu Dağıtımlar için Lisanslama](/tr/docs/on-premise) sayfasına, kriptografik tasarım için [Lisans Zinciri ve Delegasyon](/tr/docs/license-chain) sayfasına bakın.

## Aylık Depo Lisansı Düzenlemeleri

Bu metrik, mevcut UTC takvim ayında başarılı hesap destekli depo lisansı düzenleme etkinliğini sayar.

Şunları içerir:

- ilk kez depo lisansı düzenleme
- yeni imzalanmış lisans döndüren başarılı depo lisansı yenileme

Şunları içermez:

- değişmemiş toplu girişler
- başarısız düzenleme girişimleri
- düzenlemeden önce reddedilen izlenmeyen depolar

Kullanım ve son depo lisansı düzenleme geçmişinin müşteri görünümüne ihtiyaç duyuyorsanız hesap portalını kullanın. Makine tarafında incelemeye ihtiyaç duyuyorsanız `rdc subscription activation status -m` ve `rdc subscription repo status -m` komutlarını kullanın.
