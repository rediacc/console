---
title: Güvenlik Modeli
description: Yapılandırma depolamada kimin neyi görebildiği, anahtarların nasıl kapsamlandırıldığı, ajanların ve uzak MCP'nin nelere erişebildiği ve nelerin kurtarılabildiği.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: tr
sourceHash: "dd01eccb85dd4e7c"
sourceCommit: "467795d4f62f378389037e0027cac2676125b437"
---

# Güvenlik Modeli

Bu sayfa, yapılandırma depolamanın neyi koruduğunu, hangi anahtarın neyi açtığını ve her çağıran türünün nelere erişebildiğini anlatır. Kurulum adımları için [Yapılandırma Depolama](/tr/docs/config-storage), oturumlar ve token'lar için [Hesap Güvenliği ve API](/tr/docs/account-security) sayfalarına bakın.

## Kim neyi görebilir

![Anahtar hiyerarşisi](/img/security-key-hierarchy.svg)

*Sunucu SDK katmanının ve kuruluş parolası katmanının anahtarlarını tutar; CEK'i yalnızca anahtar yuvası sahipleri açar.*

![Yapılandırma içeriğini kimler görebilir](/img/security-who-can-see.svg)

*Her saldırgan türünün okuyabildikleri.*

Depolanan bir yapılandırma üç katmanda şifrelenir. SDK katmanı ile kuruluş parolası katmanı sunucu tarafından yönetilir. Ortadaki katman, yalnızca anahtar yuvası sahiplerinin açabildiği içerik şifreleme anahtarıdır (CEK): cihazda tutulan bir yuva sırrı, sunucuda tutulan bir sırla birleşir ve iki yarıdan hiçbiri tek başına onu açmaz.

| Saldırganın elinde | Yapılandırma içeriğini görür mü | Neden |
|---|---|---|
| Yalnızca bir veritabanı kopyası | Hayır | Yapılandırma blob'ları veritabanında değil, nesne depolamada durur |
| Veritabanı ve nesne depolama | Hayır | Kuruluş parolası katmanı Worker sırrını, CEK katmanı ise bir yuva sırrını gerektirir |
| Tam bir sunucu ihlali | Yuva sırrı olmadan hayır | Sunucu katmanları düşer, ancak CEK, passkey PRF çıktısının veya 160 bitlik kurtarma kitinin arkasında kalır ve ikisi de tahmin edilemez |
| Çıkarılmış bir üyenin cihazı | Önceden çekilmiş olanlar | CEK rotasyonundan sonra sonraki sürümler kapalı kalır |
| Sızdırılmış bir ajan URL'si | Tek bir yapılandırma, o kullanıcı olarak | Bkz. [Ajanlar ve uzak MCP](#agents-and-remote-mcp) |

Sunucu meta verileri (yapılandırma kimlikleri, ekipler, sürümler, zaman damgaları, blob boyutları) görmeye devam eder ve istekleri reddedebilir, geciktirebilir veya silebilir. Kötü amaçlı portal kodu sunan bir operatör, tarayıcıdaki anahtarları okuyabilir. Her blob kendi deposuna, yapılandırmasına, ekibine ve sürümüne bağlıdır; bu yüzden sunucu bir blob'u fark edilmeden değiştiremez ya da düzenleyemez, CLI de daha önce gördüğünden eski bir sürümü reddeder.

## Anahtar kapsamı

![Anahtar kapsamı](/img/security-key-scope.svg)

*Kuruluş başına bir depo ve bir CEK; ekipler erişim denetimidir, ayrı anahtarlar değildir.*

- Kuruluş başına bir yapılandırma deposu ve depo başına bir CEK. Ekipler sunucu tarafı erişim denetimidir, kriptografik yalıtım değildir: bir kurtarma kiti veya anahtar yuvası, tüm kuruluşun CEK'ini açar.
- Anahtar yuvaları depo, kullanıcı ve yöntem başına benzersizdir; dolayısıyla kurtarma kiti kullanıcı ve kuruluş başına birdir. İki kuruluştaki bir kullanıcı iki kit taşır, ekip kiti yoktur.
- Makine sırrı, kuruluştaki makine başına birdir ve başsız bir makineyi kaydeder.
- Her yapılandırmanın CEK altında kendi içerik anahtarı vardır. Bir ajan yetkisi tek bir yapılandırmanın içerik anahtarını taşır; bu nedenle kuruluşun başka hiçbir yapılandırması onunla açılmaz.
- Her yapılandırmanın yetkilendirme ilkesi, CEK'ten ve kaydın işaretçisinden türetilen bir anahtar altında ayrı bir kayıttır. Tek bir ilke anahtarının sahibi yalnızca o işaretçinin kayıtlarını açar.

## Ajanlar ve uzak MCP

![Uzak MCP akışı](/img/security-remote-mcp-flow.svg)

*İstemci çağrısı MCP Worker üzerinden kuruluşun yürütücüsüne ulaşır; süresi dolan yetki istemciyi yeniden yetkilendirmeye gönderir.*

Ajan yetkisi, uzak bir MCP URL'sinin arkasındaki anahtar sahibi türüdür. Bir yapılandırmanın içerik anahtarını, yetkinin kendi ekip yapılandırmasının ve kuruluş düzeyi yapılandırmanın ilke anahtarlarını taşır, CEK'i asla taşımaz; böylece bir ajan, bağlı olduğu kişinin okuduğunun tam olarak aynısını okur.

- **Ömür.** Bir URL varsayılan olarak 7 gün, en fazla 30 gün yaşar; sonra süresi dolar veya iptal edilir. Süresi dolmuş bir yetki reddedilir ve istemci yeniden yetkilendirir.
- **Kapsam.** Bir yetki tek bir yapılandırmaya erişir ve tek bir bölgeye (eu, us veya asia) aittir. Başka bir bölgeye sunulan URL, doğru bölge belirtilerek reddedilir ve asla iletilmez. Şirket içi (on-premise) kurulumlar tek bölgelidir.
- **İlke.** Bir ajan yalnızca bir insanın açık onayının ve ilke tavanının ikisinin de izin verdiği yerde işlem yapar. Tavan, ekip ilkesiyle daraltılmış kuruluş ilkesidir. Ajan ilkeyi düzenleyemez, gizli değerleri okuyamaz ve kendi yetkisini genişletemez.
- **Etki alanı.** Sızdırılmış bir URL, süresi dolana veya iptal edilene kadar tek yapılandırmasında o kullanıcı gibi işlem yapar. Bölgesinin barındırılan executor'ı dışında hiçbir şeyi açmaz.

Araç çıktısı, kullanıcının bağladığı ve Rediacc'in seçmediği model sağlayıcısına ulaşır.

### Şirket içi (on-premise)

Yolda Cloudflare yoktur. Bulutun Worker sırları, müşteri ana makinesinde ortam değişkenlerine veya yapılandırmaya dönüşür; bu yüzden ana makineye erişim, yukarıdaki tablodaki Worker sırrı sınırının yerini alır ve araç çağrıları müşterinin kendi daemon executor'ında çalışır.

## İlke

![İlke tavanı](/img/security-policy-ceiling.svg)

*Aracı yalnızca insan onayının ve kuruluş ile ekip ilkelerinin kesişiminin birlikte izin verdiği yerde işlem yapar.*

İlke, her yapılandırma girdisi için mühürlenmiş ayrı bir kayıttır; kimlik doğrulamalı verisi depoyu, yapılandırmayı, ekibi, sürümü ve anahtar neslini bağlar. Sunucu onu okuyamaz, yeniden oynatılan veya değiştirilen bir kayıt bütünlük etiketinde başarısız olur. Sürüm 1 ilke kayıtları reddedilir.

Kuruluş ilkesini yalnızca bir kuruluş sahibi veya yöneticisi, bir ekibin ilkesini ise yalnızca o ekibin yöneticisi (veya bir sahip ya da yönetici) yazar. Yazma için 2FA ve yükseltilmiş bir oturum gerekir; depo passkey zorunlu kılıyorsa bağlı bir passkey de gerekir. Her üye ve onlara hizmet eden her executor ilkeyi okur. Kuruluşun kilitlediği bir anahtar, ekip ilkesinde yok sayılır.

## Nelerin kurtarılabildiği

![Kilit açma ve kurtarma yolları](/img/security-unlock-recovery.svg)

*Her kilit açma yöntemi CEK'te biter ve kurtarma kiti zorunludur.*

| Durum | Kurtarma |
|---|---|
| Passkey kaybı | Kurtarma kitiyle kilidi açın, ardından yeni bir passkey kaydedin |
| Kit kaybı | Çalışan bir passkey ile yeniden oluşturun; eski çıktı geçersiz olur |
| İkisi de kayıp | Bir sahip veya yönetici, üyeyi üye devri üzerinden yeniden ekler |
| Son anahtar sahibi ikisini de kaybederse | Kurtarılamaz; bu yüzden ikinci bir anahtar sahibi önerilir |
| Üye çıkarıldı | Yuvaları ve token'ları hemen düşer; CEK rotasyonu, üyenin sakladığı bir anahtara karşı sonraki sürümleri kapatır |
| CEK rotasyonu | CEK'i yeni bir nesil altında yeniden sarar ve her kurtarma kitini geçersiz kılar |

Sunucu, ikiden az anahtar sahibi ve hiç kurtarma yuvası bırakacak olan her yuva silmeyi, üye çıkarmayı ve üye ayrılmasını reddeder. Her üye kayıt sırasında zorunlu bir kurtarma kiti alır ve onu saklamak üyenin sorumluluğundadır.
