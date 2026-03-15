---
title: Abonelik ve Lisanslama
description: account, rdc ve renet'in makine slotlarını, depo lisanslarını ve plan limitlerini nasıl yönettiğini anlayın.
category: Guides
order: 7
language: tr
sourceHash: "fcc4e06609545bf7"
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

`account`, planlar, sözleşme geçersiz kılmaları, makine aktivasyon durumu ve aylık depo lisansı düzenlemeleri için gerçeğin kaynağıdır.

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

## Makine Lisansları vs. Depo Lisansları

### Makine Aktivasyonu

Makine aktivasyonu çift rol üstlenir:

- **Sunucu tarafında**: yüzen makine slotu muhasebesi, makine düzeyinde aktivasyon kontrolleri, hesap destekli depo düzenlemesini belirli bir makineye köprüleme
- **Diskte**: `rdc` aktivasyon sırasında `/var/lib/rediacc/license/machine.json` konumuna imzalı bir abonelik blobu yazar. Bu blob, sağlama işlemleri (`rdc repo create`, `rdc repo fork`) için yerel olarak doğrulanır. Makine lisansı, son aktivasyondan itibaren 1 saat geçerlidir.

### Depo Lisansı

Depo lisansı, bir makinedeki bir depo için imzalı bir lisanstır.

Şunlar için kullanılır:

- `rdc repo resize` ve `rdc repo expand` — son kullanma tarihi dahil tam doğrulama
- `rdc repo up`, `rdc repo down`, `rdc repo delete` — **son kullanma tarihi atlanarak** doğrulanır
- `rdc repo push`, `rdc repo pull`, `rdc repo sync` — **son kullanma tarihi atlanarak** doğrulanır
- makine yeniden başlatılırken depo otomatik başlatma — **son kullanma tarihi atlanarak** doğrulanır

Depo lisansları makineye ve hedef depoya bağlıdır; Rediacc bu bağlamayı depo kimlik meta verileriyle güçlendirir. Şifrelenmiş depolar için bu, altta yatan birimin LUKS kimliğini içerir.

Uygulamada:

- makine aktivasyonu şunu yanıtlar: "bu makine yeni depolar sağlayabilir mi?"
- depo lisansı şunu yanıtlar: "bu belirli depo bu belirli makinede çalışabilir mi?"

## Varsayılan Limitler

Depo boyutu hak düzeyine bağlıdır:

- Community: `10 GB`'a kadar
- ücretli planlar: plan veya sözleşme limiti

Ücretli plan varsayılan limitleri:

| Plan | Değişken Lisanslar | Depo Boyutu | Aylık depo lisansı düzenlemeleri |
|------|---------------------|-------------|----------------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5.000 |
| Business | 20 | 500 GB | 20.000 |
| Enterprise | 50 | 2048 GB | 100.000 |

Sözleşmeye özgü limitler, belirli bir müşteri için bu değerleri artırabilir veya azaltabilir.

## Depo Oluşturma, Başlatma, Durdurma ve Yeniden Başlatma Sırasında Ne Olur

### Depo Oluşturma ve Çatallaştırma

Bir depo oluşturduğunuzda veya çatalladığınızda:

1. `rdc` abonelik tokeninizin mevcut olduğundan emin olur (gerekirse cihaz kodu kimlik doğrulamasını tetikler)
2. `rdc` makineyi etkinleştirir ve imzalı abonelik blobunu uzak makineye yazar
3. Makine lisansı yerel olarak doğrulanır (aktivasyondan itibaren 1 saat içinde olmalıdır)
4. Başarılı oluşturmanın ardından `rdc`, yeni depo için depo lisansı düzenler

Bu hesap destekli düzenleme, aylık **depo lisansı düzenlemeleri** kullanımınıza sayılır.

### Depo Başlatma, Durdurma ve Silme

`rdc` makine üzerinde yüklü depo lisansını doğrular, ancak **son kullanma tarihi kontrolünü atlar**. İmza, makine kimliği, depo GUID'i ve kimlik doğrulanmaya devam eder. Kullanıcılar, süresi dolmuş bir abonelikle bile depolarını işletmekten hiçbir zaman engellenmez.

### Depo Yeniden Boyutlandırma ve Genişletme

`rdc`, son kullanma tarihi ve boyut limitleri dahil tam depo lisansı doğrulaması gerçekleştirir.

### Makine Yeniden Başlatma ve Otomatik Başlatma

Otomatik başlatma, `rdc repo up` ile aynı kuralları kullanır — son kullanma tarihi atlanır, böylece depolar her zaman serbestçe yeniden başlar.

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

Makine aktivasyonunu yenile ve depo lisanslarını toplu olarak yenile:

```bash
rdc subscription refresh -m hostinger
```

Makinede keşfedilen ancak yerel `rdc` yapılandırmasında bulunmayan depolar toplu yenileme sırasında reddedilir. Bunlar başarısızlık olarak raporlanır ve otomatik olarak sınıflandırılmaz.

Mevcut bir depo için depo lisansı yenilemesini zorla:

```bash
rdc subscription refresh repo my-app -m hostinger
```

İlk kullanımda, kullanılabilir depo lisansı bulamayan lisanslı bir depo veya yedekleme işlemi otomatik olarak hesap yetkilendirme aktarımını tetikleyebilir. CLI bir yetkilendirme URL'si yazdırır, etkileşimli terminallerde tarayıcıyı açmaya çalışır ve yetkilendirme ve düzenleme başarılı olduktan sonra işlemi bir kez yeniden dener.

Etkileşimli olmayan ortamlarda CLI, tarayıcı onayını beklemez. Bunun yerine, `rdc subscription login --token ...` veya `REDIACC_SUBSCRIPTION_TOKEN` ile kapsamlı bir token sağlamanızı ister.

İlk makine kurulumu için [Makine Kurulumu](/tr/docs/setup) sayfasına bakın.

## Çevrimdışı Davranış ve Sona Erme

Lisans doğrulaması makine üzerinde yerel olarak gerçekleşir — hesap sunucusuna canlı bağlantı gerektirmez.

Bu şu anlama gelir:

- çalışan bir ortam her komutta hesaba canlı bağlantı gerektirmez
- tüm depolar süresi dolmuş lisanslarla bile her zaman başlatılabilir, durdurulabilir ve silinebilir — kullanıcılar kendi depolarını işletmekten hiçbir zaman engellenmez
- sağlama işlemleri (`create`, `fork`) geçerli bir makine lisansı gerektirir ve büyüme işlemleri (`resize`, `expand`) geçerli bir depo lisansı gerektirir
- gerçekten süresi dolmuş depo lisansları, resize/expand öncesinde `rdc` aracılığıyla yenilenmelidir

Makine aktivasyonu ve depo çalışma zamanı lisansları ayrı yüzeylerdir. Bir makine hesap durumunda aktif olmayabilir, bazı depolar hâlâ geçerli yüklü depo lisanslarına sahip olabilir. Bu durumda her iki yüzeyi aynı şeyi ifade ettiğini varsaymak yerine ayrı ayrı inceleyin.

## Kurtarma Davranışı

Otomatik kurtarma kasıtlı olarak dar tutulmuştur:

- `missing`: `rdc` gerektiğinde hesap erişimini yetkilendirebilir, depo lisanslarını toplu olarak yenileyebilir ve bir kez yeniden deneyebilir
- `expired`: `rdc` depo lisanslarını toplu olarak yenileyebilir ve bir kez yeniden deneyebilir
- `machine_mismatch`: hızla başarısız olur ve mevcut makine bağlamından yeniden düzenlemenizi ister
- `repository_mismatch`: hızla başarısız olur ve depo lisanslarını açıkça yenilemenizi ister
- `sequence_regression`: depo lisansı bütünlüğü/durum sorunu olarak hızla başarısız olur
- `invalid_signature`: depo lisansı bütünlüğü/durum sorunu olarak hızla başarısız olur
- `identity_mismatch`: hızla başarısız olur — depo kimliği yüklü lisansla eşleşmiyor

Bu hızlı başarısızlık durumları otomatik olarak hesap destekli yenileme veya düzenleme çağrısı tüketmez.

## Aylık Depo Lisansı Düzenlemeleri

Bu metrik, mevcut UTC takvim ayında başarılı hesap destekli depo lisansı düzenleme etkinliğini sayar.

Şunları içerir:

- ilk kez depo lisansı düzenleme
- yeni imzalanmış lisans döndüren başarılı depo lisansı yenileme

Şunları içermez:

- değişmemiş toplu girişler
- başarısız düzenleme girişimleri
- düzenlemeden önce reddedilen izlenmeyen depolar

Kullanım ve son depo lisansı düzenleme geçmişinin müşteri görünümüne ihtiyaç duyuyorsanız hesap portalını kullanın. Makine tarafında incelemeye ihtiyaç duyuyorsanız `rdc subscription activation status -m` ve `rdc subscription repo status -m` kullanın.
