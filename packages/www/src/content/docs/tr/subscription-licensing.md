---
title: Abonelik ve Lisanslama
description: >-
  account, rdc ve renet'in makine slotlarını, depo lisanslarını ve plan
  limitlerini nasıl yönettiğini anlayın.
category: Guides
tags:
  - account
subcategory: account
order: 7
language: tr
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
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
rdc subscription login --token "$REDIACC_TOKEN"
```

CLI'ın herhangi bir etkileşimli giriş adımı olmadan depo lisansları düzenleyip yenileyebilmesi için tokeni doğrudan ortam üzerinden de enjekte edebilirsiniz:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Makine Slotları ve Depo Lisansları

### Makine slotları (sunucu tarafı)

Makine slot takibi sunucu tarafında uygulanır. CLI bir depo lisansı düzenlediğinde, hesap sunucusu aboneliğin makine slot kotasını kontrol eder. Her self-servis plan (Community, Professional, Business) bir makine slotu içerir; çok makineli dağıtımlar ortaklarımızla birlikte boyutlandırılan bir Enterprise kurulumudur. Bir slot, o makinedeki son depo lisansı düzenlemesinden itibaren 5 saat süresince tutulur ve inaktiviteden sonra otomatik olarak serbest bırakılır. Bir slot yalnızca aktif olarak sağlama yaparken tutulduğundan, tek bir slot bir ay boyunca yine de birden fazla makineyi kapsayabilir.

Tavan, sabit kodlanmış bir plan sabitinden değil aboneliğinizin kaydından okunur; dolayısıyla pazarlıkla belirlenmiş bir etkinleştirme sayısı, abonelikte tanımlandığı anda geçerli olur. Plan seviyesi yalnızca başlangıç değerini belirler.

Düzenleme ile yenileme farklı şekilde uygulanır ve bu fark önemlidir:

- **Yeni bir lisans düzenlemek tavanda engellenir.** Tüm slotlar doluysa istek `MAX_MACHINES_REACHED` ile başarısız olur ve hiçbir şey sağlanmaz.
- **Mevcut bir lisansı yenilemek asla engellenmez.** Tüm slotlar doluyken yenileme yapan bir makine çalışmaya devam eder ve slotu limit aşımı olarak kaydedilir. Bunu portalda Makineler sayfasında, `rdc subscription status` çıktısında ve lisans durumu API'sinin `overLimitCount` alanında görebilirsiniz. Makine yeniden limitin içine girdiğinde işaret kendiliğinden kalkar.

Yenilemenin daha yumuşak yol olması bilinçlidir. Zaten elinde tuttuğu bir lisansı yenileyen bir makine yeni kapasite anlamına gelmez ve onu reddetmek, bedeli çoktan ödenmiş bir altyapıda yedeklemeleri durdururdu. Engellenmeye devam eden şey kapasite eklemektir.

Makinede hiçbir makine lisans dosyası depolanmaz. Slot uygulaması, sunucuda düzenleme zamanında gerçekleşir.

### Depo lisansı

Depo lisansı, bir makinedeki bir depo için imzalı bir lisanstır. Makinede depolanan tek lisans dosyasıdır ve datastore başına ve imzalama anahtarı başına şu şekilde düzenlenir:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Makinenin varsayılan depolamasındaki depolar ilk yolu kullanır. Adlandırılmış bir datastore içindeki depolar ise ikincisini kullanır; burada `{datastoreId}`, o datastore oluşturulurken ona verilen kimliktir. Bir datastore çatalının dürüstçe ölçülmesini sağlayan şey tam olarak bu kapsamlandırmadır: çatallanan datastore bambaşka bir kimlik alır, dolayısıyla içindeki depolar hiç lisansı olmadan yola çıkar, ilk lisanslı işlemlerinde `missing` bildirir ve kendi lisanslarını alır. Lisansında, içinde bulunduğundan başka bir datastore adı geçen bir depo, otomatik yeniden düzenleme yerine `identity_mismatch` ile hızlıca başarısız olur; bir lisans dosyasının yan tarafa kopyalanmasını engelleyen de budur.

`{keyId}`, 16 haneli onaltılık bir parmak izidir (imzalayan sunucunun Ed25519 genel anahtarının `SHA-256` değerinin ilk 8 baytı). Birden fazla hesap evreni tarafından yönetilen bir depo (örneğin, aynı makineye dağıtım yapan üretim ve bench), `{guid}` dizini altında imzalama anahtarı başına bir dosya tutar. Makinenin renet derlemesi yalnızca kendi gömülü anahtarının, veya ona zincirlenmiş bir yetkilendirme sertifikasının doğrulayabileceği dosyayı doğrular; diğer evrenlerin dosyaları etkisizdir. Evren değiştirmek lisansları asla geçersiz kılmaz: yeni bir evrendeki ilk işlem, o evrenin lisansını bir kez düzenler (bir `missing` sonucu otomatik olarak düzenlemeyi tetikler) ve ardından ikisi birlikte var olur.

Şunlar için kullanılır:

- `rdc repo create`, `rdc repo fork` ve `rdc repo commit`, sağlamadan önce doğrulanır (kimlik kanıtı olmadan önceden düzenlenir, kontrol anında depo henüz var olmadığı için oluşturulduktan sonra kimlik kanıtlarıyla yeniden düzenlenir)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` ve `rdc repo promote`, **son kullanma tarihi dahil tam olarak doğrulanır**
- yedekleme aktarımı, **son kullanma tarihi dahil tam olarak doğrulanır**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` ve zamanlanmış yedeklemeler
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` ve makine yeniden başlatılırken depo otomatik başlatma, **hem son kullanma tarihi hem de yetkilendirme sertifikası penceresi atlanarak** doğrulanır
- `rdc repo down`, `rdc repo delete` ve depoları listelemek gibi salt okunur komutlar hiçbir lisans gerektirmez

İmzalar, anahtar bağlama, makine bağlama, depo bağlama ve her yetkilendirme sertifikası kısıtlaması bunların hepsinde uygulanır. Son grubun gevşettiği tek şey iki zaman penceresidir; böylece süresi dolmuş bir lisans ya da geçerliliğini yitirmiş bir sertifika, kendi verinizi çalıştırmanızı veya kapatmanızı asla engelleyemez.

Depo lisansları makineye ve hedef depoya bağlıdır. Her lisans, makine kimliği, depo GUID'i, abonelik kimliği, plan limitleri ve son kullanma tarihini içerir. Şifrelenmiş depolar için Rediacc, altta yatan birimin LUKS kimliğini de doğrular.

Aynı makinede birden fazla abonelik birlikte var olabilir. Her depo, kendi abonelik bağlamıyla birlikte kendi lisansını taşır.

## Kümeler

Kümeleme, iş ortaklarımız aracılığıyla bir Enterprise anlaşmasının parçası olarak satılır. Self-servis bir plan seçeneği değildir ve aşağıdaki bölümler onun nasıl satın alınacağını değil nasıl ölçüldüğünü anlatır.

**Bir düğüm bir makinedir.** Bir Kümenin kendine ait bir lisans kimliği yoktur. İçindeki her düğüm, Renet Agent kurulu sıradan bir makinedir ve tıpkı tek başına duran bir makine gibi sayılır.

**Havuzlama yoktur.** Beş düğümlü bir küme tek bir ortak küme slotundan beslenmez. Her düğüm, üzerine ilk kez bir depo yerleştirildiğinde kendi slotunu alır ve bu slot diğerleriyle aynı 5 saatlik akışa tabidir: o düğümdeki son depo lisansı düzenlemesinden itibaren 5 saat tutulur ve sonrasında kendiliğinden serbest kalır.

**Kümeyi kurmak ücretsizdir. Ölçülen şey depoları yerleştirmektir.** Kümeyi oluşturmak, düğümleri katmak, dağıtık depolama katmanını kurmak ve Kubernetes kontrol düzlemini ayağa kaldırmak hiçbir slota mal olmaz. Ölçüm, bir depo bir düğüme indiğinde başlar.

**Bir küme çatalı her depo için yeniden ölçülür.** Bir kümenin tamamını çatallamak, çatallanan datastore'a yeni bir kimlik verir; dolayısıyla çataldaki her depo, hangi düğümde çalışıyorsa orada ilk dokunulduğunda kendi lisansını alır. Düz geçiş bunun tam tersidir: bir depoyu makineler arasında taşımak lisansını da beraberinde götürür ve doğrulanmaya devam eder, çünkü depolama kimliğiyle ilgili hiçbir şey değişmemiştir.

**Bir kümede yenileme, yukarıdaki yumuşak talep kuralına uyar.** Düğümler kendi lisanslarını insan müdahalesi olmadan yeniler; böylece etkinleştirme sayısını aşmış bir küme, gecenin bir yarısı yedeklemeleri düşürmek yerine çalışmaya devam eder ve limiti aşan düğümlerini raporlar. Yeni bir düğüm eklemek ise tavanda hâlâ engellenir.

Bir kümeyi boyutlandırmak bir sohbettir, bir onay kutusu değil. Kümeler için etkinleştirme sayıları siparişte kararlaştırılır ve iş ortağınız bunları doğrudan aboneliğe işler. Bu sohbeti başlatmak için [İletişim](/tr/contact) sayfasına bakın.

## Varsayılan Limitler

Depo boyutu hak düzeyine bağlıdır:

- Community: `10 GB`'a kadar
- ücretli planlar: plan veya sözleşme limiti

Ücretli plan varsayılan limitleri:

| Plan | Değişken Lisanslar | Depo Boyutu | Aylık depo lisansı düzenlemeleri | Delegasyon sertifikası varsayılan / maks |
|------|---------------------|-------------|----------------------------------|----------------------------------------|
| Community | 1 | 10 GB | 100 | 15g / 30g |
| Professional | 1 | 100 GB | 2.000+ | 60g / 120g |
| Business | 1 | 500 GB | 5.000+ | 90g / 180g |
| Enterprise | Özel | 1 TB+ | 15.000+ | 120g / 365g |

Sözleşmeye özgü limitler, belirli bir müşteri için bu değerleri artırabilir veya azaltabilir. Delegasyon sertifikası geçerliliği aynı zamanda `subscription.expiresAt + 3 günlük ek süre` ile kesin olarak sınırlandırılmıştır; dolayısıyla aylık faturalandırılan abonelikler doğal olarak faturalama döngüleriyle uyumlu sertifikalar alır. Tam kurallar için [Lisans Zinciri ve Delegasyon - Geçerlilik Politikası](/tr/docs/license-chain) sayfasına bakın.

## Ücretsiz Deneme ve Community'ye Geri Dönüş

Yeni kayıtlar Professional veya Business planında 14 günlük ücretsiz denemeyle başlar. Kayıt sırasında bir kredi kartı alınır; ilk ücretlendirme yalnızca deneme süresi bittiğinde yapılır, dolayısıyla deneme bitmeden iptal etmenin hiçbir maliyeti yoktur. Müşteri başına bir deneme hakkı vardır.

Community, kalıcı ücretsiz tabandır. Artık yeni hesaplar için doğrudan kayıt seçeneği değildir; bunun yerine bir abonelik sona erdiğinde (deneme sırasında iptal, ücretli bir planın sonradan iptali veya başarısız bir ödeme) hesap Community'ye düşer. Community geri dönüşünde bir makine, depo başına 10 GB ve ayda 100 kurulum hakkınız kalır. Deneme tabanlı model başlamadan önce oluşturulmuş hesaplar mevcut Community erişimlerini korur.

Uygulama en çok önem taşıdığı yerde yumuşak kalmaya devam eder: çalışan depolar (`up`, `down`, `delete`, otomatik başlatma) abonelik sona erse bile çalışmaya devam eder. Bunun ötesinde iki ayrı kural geçerlidir ve 60 günlük ek süreyi tutarsız gösteren şey, bu ikisinin birbirine karıştırılmasıdır:

- **Hesap sunucusuna ihtiyaç duyan işlemler** aktif bir abonelik olmadan gerçekleşemez, çünkü sunucu imzalamayı reddeder. Bunlar `create`, `fork` ve her türlü lisans yenileme veya tazelemedir. Abonelik sona erdiğinde yeni hiçbir şey sağlanmaz.
- **Yalnızca geçerli bir yüklü lisansa ihtiyaç duyan işlemler**, o lisans kesin olarak sona erene kadar sunucuya hiç uğramadan çalışmaya devam eder. Bunlar, halihazırda sahip olduğunuz depolarda `resize` ve `expand` ile yedekleme aktarımıdır (`push`, `pull`, zamanlanmış yedeklemeler). Bir deponun birincil lisansı, abonelik bitiş tarihinden 60 gün sonra kesin olarak sona erer; 60 günlük ek süre buradan gelir. Bir çatalın lisansı ise çok daha kısa ömürlüdür, en fazla 7 gündür; çatal ağırlıklı makinelerin aşağıda anlatılan kendi kendine yenilemeye bağımlı olmasının nedeni budur.

Yani sona ermiş bir abonelik filonuzu büyütmenizi hemen, o filodaki depoları büyütmenizi ise 60 gün sonra durdurur.

## Makine Geçişi Uyum Dönemi

Bir barındırma sağlayıcısı VM'yi farklı fiziksel donanıma taşıdığında, makine kimliği değişir (DMI UUID, `/etc/machine-id` ve NIC MAC adresleri gibi donanım tanımlayıcılarından türetilir). Depo lisansları makine kimliğine bağlıdır, bu nedenle bir geçiş normalde tüm lisansları geçersiz kılarsa.

Bunu şeffaf bir şekilde işlemek için, depo lisansları **40 günlük makine kimliği uyum dönemini** içerir. Makine kimliği eşleşmese bile lisans 40 günden az zaman önce düzenlenmiş ise, lisans yine de kabul edilir. Lisanslar her 30 günde bir yenilendiğinden, sonraki yenileme otomatik olarak yeni makine kimliğine bağlanır.

Pratikte:
- VM taşındı, makine kimliği değişti: depolar çalışmaya devam eder (40 günlük pencere içinde)
- Sonraki `rdc` işlemi lisansı yeni makine kimliğiyle yeniler
- El ile müdahale gerekli değil
- `rdc machine status <machine> --system --licenses` ile makine kimliği ve lisans durumunu kontrol edin

**Edge kanalı hesapları**, 2 katına çıkarılmış limitlerle Community planında çalışır (20 GB depolar, ayda 200 kurulum, 2 makine). Ücretli planlar yalnızca Stable kanalında mevcuttur. Ayrıntılar için [Yayın Kanalları](/tr/docs/release-channels) sayfasına bakın.

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
rdc subscription login --token "$REDIACC_TOKEN"
```

Etkileşimli olmayan ortamlar için `REDIACC_TOKEN` ayarlamak en basit seçenektir. Token, ajanın ihtiyaç duyduğu abonelik ve depo lisansı işlemleriyle sınırlı kapsamda olmalıdır.

Hesap destekli abonelik durumunu göster:

```bash
rdc subscription status
```

Bir makine için makine aktivasyon ayrıntılarını göster:

```bash
rdc subscription status -m hostinger
```

Bir makinede yüklü depo lisansı ayrıntılarını göster:

```bash
rdc subscription status -m hostinger
```

Bir makinede bir deponun lisansını yenile:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

`--repo` ref'i yerel `rdc` yapılandırmanızda çözümlenebilmelidir. Makinede keşfedilen ancak yerel yapılandırmada bulunmayan bir depo reddedilir: başarısızlık olarak raporlanır ve otomatik olarak sınıflandırılmaz.

İlk kullanımda, kullanılabilir depo lisansı bulamayan lisanslı bir depo veya yedekleme işlemi otomatik olarak hesap yetkilendirme aktarımını tetikleyebilir. CLI bir yetkilendirme URL'si yazdırır, etkileşimli terminallerde tarayıcıyı açmaya çalışır ve yetkilendirme ile düzenleme başarılı olduktan sonra işlemi bir kez yeniden dener.

Etkileşimli olmayan ortamlarda CLI, tarayıcı onayını beklemez. Bunun yerine, `rdc subscription login --token ...` veya `REDIACC_TOKEN` ile kapsamlı bir token sağlamanızı ister.

İlk makine kurulumu için [Makine Kurulumu](/tr/docs/setup) sayfasına bakın.

## Lisansların Kendi Kendini Yenilemesi

Buraya kadar anlatılan her şey, klavye başında olduğunuzu varsayar. Zamanlanmış yedeklemeler ise değildir; kendi kendine yenilemenin var olma sebebi tam olarak bu durumdur.

Zamanlanmış bir yedekleme katı katmanda doğrulanır, dolayısıyla süresi dolmamış bir lisansa ihtiyaç duyar. Bir çatalın lisansı en fazla 7 gündür. Makineleriniz tasarım gereği hiçbir hesap kimlik bilgisi tutmaz; bu yüzden kendi kendine yenilemeden önce bir çatalın yedeklemesi, oluşturulmasından bir hafta sonra, sessizce, gecenin üçünde duruverirdi.

### Bir makine token tutmadan nasıl yeniler

Rediacc'in düzenlediği veya yenilediği her lisans, kendisini imzalayan hesap sunucusundaki yenileme uç noktasının tam adresini `renewalUrl` alanında taşır. Makine bu adresi kendi yüklü lisansından okur; dolayısıyla hesap sunucusunun nerede olduğunun ona ayrıca söylenmesi hiç gerekmez.

Ardından makine, yüklü lisansı o uç noktaya geri sunar. Lisansın kendisi kimlik bilgisidir: imzalıdır, sunucu bu imzayı doğrular ve hiçbir yerde API tokeni devreye girmez. Sunucu, yeni geçerlilik pencereleriyle taze bir lisans döndürür; makine de yenilemeyi tamamlanmış saymadan önce lisansı kurar ve yeniden doğrular.

Yenileme makine genelinde bir işlemdir:

```bash
sudo renet license renew
```

Depolar, kendilerini imzalayan sunucuya göre gruplanır; böylece iki hesap evrenine hizmet eden bir makine her birine yalnızca bir kez başvurur. Bir kilit dosyası, iki yenilemenin aynı anda çalışmasını önler ve `--jitter`, aksi hâlde hepsi saat başında uyanacak bir makine filosunu zamana yayar.

Sunucu bir yenilemeyi üç durumda reddeder ve her biri farklı bir anlama gelir:

| Ret | Ne anlama gelir |
|---|---|
| Abonelik sona ermiş, askıya alınmış veya ek süresi geçmiş | Faturalandırma konusu. Abonelik yeniden aktif olduğunda yenileme kendiliğinden devam eder |
| Yetkilendirme sertifikasının süresi dolmuş veya sertifika iptal edilmiş | Yerinde kurulum konusu. Sertifikayı yerinde sunucunuzda yenileyin, makineler ardından normal şekilde yenilenir |
| Makine kimliği artık eşleşmiyor ve 40 günlük ek süre dolmuş | Lisans, bu makine olmayan başka bir makineye ait. Mevcut makine bağlamından yeniden düzenleyin |

Bir ret, çalışmanın tamamını durdurmaz. Süresi geçmiş tek bir depo, aynı makinedeki diğerlerinin yenilenmesini engellemez.

### Zamanlanmış yedeklemeler kendini yeniler

Rediacc'in yazdığı her yedekleme birimi önce bir yenileme çalıştırır:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

Baştaki `-` işareti, bu adımı bilerek elden geldiğince yapılacak bir iş olarak işaretler. Reddedilen bir yenileme, bir ağ kesintisi ya da komutu henüz bilmeyen eski bir Renet Agent, yedeklemenin kendisini asla düşürmemelidir. Yedekleme çalışır, lisans da mümkün olduğunda yol üstünde yenilenir.

### Bir yedekleme engellendiğinde

Lisanslama bir yedeklemeyi gerçekten reddederse makine bunu kaydeder. Bu işaret, gözetimsiz yedeklemelerin veri kopyalamayı bıraktığının tek sinyalidir; bu yüzden yüksek sesle gösterilir:

```bash
rdc machine status <machine> --licenses
```

`backups` sütunu, nedeniyle birlikte `BLOCKED` gösterir; aynı bilgi, otuz depo arasında kaybolmasın diye tablonun altında bir hata olarak da yazdırılır. `renewed` sütunu, son gözetimsiz yenilemenin nasıl geçtiğini, varsa sunucunun ret kodunu da içerecek şekilde gösterir; çözümün bir faturalandırma sorusu mu yoksa bir yerinde sertifika sorusu mu olduğunu size söyleyen budur.

Başarılı bir yenileme işareti kaldırır; lisans kontrolünü geçen bir yedekleme de aynısını yapar. Elle onaylanacak veya sıfırlanacak bir şey yoktur.

## Çevrimdışı Davranış ve Sona Erme

Lisans doğrulaması makine üzerinde yerel olarak gerçekleşir. Hesap sunucusuna canlı bağlantı gerektirmez.

Bu şu anlama gelir:

- çalışan bir ortam her komutta hesaba canlı bağlantı gerektirmez
- tüm depolar süresi dolmuş lisanslarla bile her zaman başlatılabilir, durdurulabilir ve silinebilir; kullanıcılar kendi depolarını işletmekten hiçbir zaman engellenmez
- sağlama işlemleri (`create`, `fork`) önceden düzenlenen bir depo lisansı gerektirir ve büyüme işlemleri (`resize`, `expand`) geçerli bir depo lisansı gerektirir
- gerçekten süresi dolmuş depo lisansları, resize/expand öncesinde ya iş istasyonunuzdan `rdc` ile ya da makinenin kendini yenilemesiyle değiştirilmelidir
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
- `cert_expired`: büyüme işlemlerinde (`create`, `fork`, `resize`) ve yedekleme aktarımında (`push`, `pull`) hızla başarısız olur; `repo up` ve otomatik başlatma çalışmaya devam eder, bu da yumuşak lisans süresi dolumu modeliyle örtüşür. Yetkilendirme sertifikasını yenileyin
- `cert_invalid`: hızla başarısız olur, yetkilendirme sertifikası bir kısıtlamayı karşılamadı (geçersiz ana anahtar imzası, abonelik/plan uyuşmazlığı, boyut sınırı veya `maxTotalIssuances` üzerinde bir sıra numarası). Altta yatan sınırı düzelttikten sonra sertifikayı yeniden düzenleyin

Bu hızlı başarısızlık durumları otomatik olarak hesap destekli yenileme veya düzenleme çağrısı tüketmez.

Bu listeyi okurken iki not:

- `missing` her zaman bir sorun değildir. Yeni çatallanmış bir datastore içindeki bir depoya ilk kez dokunulduğunda alınan normal sonuç da budur ve o çatalın ölçülmesini sağlayan tam olarak odur: lisans düzenlenir, bir slot alınır ve işlem devam eder. `identity_mismatch` ise bunun bilinçli tersidir; başka bir datastore'dan kopyalanmış bir lisans dosyası sessizce yeniden düzenlenmek yerine hızlıca başarısız olur.
- Bu liste, iş istasyonunuzdan yapılan kurtarmayı anlatır. Kendi kendini yenileyen bir makinenin kendi sonuçları vardır; bunlar bir komut hatası olarak yükseltilmek yerine `rdc machine status <machine> --licenses` ile raporlanır, çünkü zamanlanmış bir yedeklemenin durumu anlatabileceği kimse yoktur.

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

Kullanım ve son depo lisansı düzenleme geçmişinin müşteri görünümüne ihtiyaç duyuyorsanız hesap portalını kullanın. Makine tarafında incelemeye ihtiyaç duyuyorsanız `rdc subscription status -m` ve `rdc subscription status -m` komutlarını kullanın.
