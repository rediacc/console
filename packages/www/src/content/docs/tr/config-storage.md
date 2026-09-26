---
title: Yapılandırma Depolama
description: Cihaz tarafında şifrelenen, passkey, ana parola veya kurtarma koduyla açılabilen yapılandırma senkronizasyonu
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: tr
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Yapılandırma Depolama

Yapılandırma depolama, bir CLI yapılandırmasını cihazlar arasında senkronize eder. Yapılandırmalar, sunucunun asla elinde tutmadığı bir içerik şifreleme anahtarıyla (CEK) cihazda şifrelenir. [Güvenlik](#security) bölümü bunun tam olarak neye karşı koruma sağladığını ve neye karşı sağlamadığını belirtir.

## Kilit açma yöntemleri (anahtar yuvaları)

Her depo için tek bir CEK vardır ve bu anahtar, LUKS'un anahtar yuvalarına benzer şekilde her kilit açma yöntemi için ayrı ayrı sarmalanır. Yuvalardan herhangi biri aynı anahtarı açar, yuvalar ise verilerinizi yeniden şifrelemeden eklenebilir veya kaldırılabilir:

| Yöntem | Nedir | Notlar |
|--------|-----------|-------|
| **Passkey** | PRF uzantılı WebAuthn passkey | En güçlü seçenek; donanım destekli |
| **Ana parola** | Seçtiğiniz, PBKDF2-SHA256 ile (600.000 yineleme) güçlendirilmiş bir parola | PRF destekli donanım gerektirmez; CLI'ı başsız (headless) olarak kaydetmeyi de mümkün kılar |
| **Kurtarma kodu** | Oluşturulan bir `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` kodu | Oluşturulduğunda yalnızca bir kez gösterilir; güvenli bir yerde saklayın |

Her yöntem aynı süreçten geçer: yuva, CEK'in kilidini açmak için sunucudaki bir sırla birleşen bir sır üretir. Bu yarımlardan hiçbiri tek başına yeterli değildir, ve yuva sırrı sunucuya asla ulaşmaz. Ana parola yuvası üçü arasında en zayıf olanıdır: sunucu, parola tahminlerini çevrimdışı denemek için gereken her şeye sahiptir, bu yüzden parolanın güçlü olması gerekir. Passkey ve kurtarma kodu yuvalarında böyle bir zayıflık yoktur.

Yuvalar, portaldaki Yapılandırma Depolama sayfasından yönetilir. Yalnızca donanımla kilit açılmasını isteyen organizasyonlar, tüm depo için passkey dışındaki yuvaları reddeden ve iptal eden **passkey zorunlu kıl** politikasını etkinleştirebilir.

Kilit açma cihaz bazlıdır: yeni bir cihazda bir kez kilidi açarsınız, sonrasında günlük CLI işlemleri (push/pull) passkey'e dokunmadan veya parola girmeden çalışır.

## Ön Koşullar

- **İki faktörlü kimlik doğrulama** hesabınızda etkinleştirilmiş olmalıdır
- **Passkey** yöntemi için: FIDO2 güvenlik anahtarı (örn. YubiKey), iCloud Keychain, Google Password Manager, 1Password veya Dashlane gibi PRF destekli bir passkey sağlayıcısı
- **Tarayıcı**: Chrome 133+, Edge 133+, Firefox 130+ veya Safari 17+

PRF gereksinimi yalnızca passkey yuvası için geçerlidir. Ana parola ve kurtarma kodu yöntemleri desteklenen her tarayıcıda çalışır.

## Kurulum

1. Kenar çubuğunda **Yapılandırma Depolama**'ya gidin, ardından **Yapılandırma Depolamayı Kur**'a tıklayın
2. Gereksinimler kontrol listesi tarayıcınızı, 2FA'yı ve oturum durumunu doğrular
3. İlk kilit açma yöntemini seçin ve **Yapılandırma deposu oluştur**'a tıklayın:
   - **Passkey**, sağlayıcınız PRF destekliyorsa: güvenlik anahtarınıza iki kez dokunursunuz; biri kaydetmek, diğeri şifreleme anahtarlarını türetmek için.
   - **Ana parola**, her tarayıcıyla çalışır; Bitwarden gibi PRF desteklemeyen passkey sağlayıcılarıyla da.
   - İsteğe bağlı olarak bir **kurtarma kodu**: yalnızca bir kez gösterilir ve depo oluşturulmadan önce saklanmalıdır.
4. Kurulum tamamlandı. CLI kilit açma sırrını işletim sisteminizin anahtar zincirinde tutar.

Passkey daha sonra Config Storage sayfasından eklenebilir. Kaybolan ya da desteklenmeyen bir doğrulayıcı sizi dışarıda bırakmasın diye en az iki kilit açma yöntemi tutun.

## PRF Sağlayıcı Uyumluluğu

| Sağlayıcı | PRF Desteği | Platformlar |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 güvenlik anahtarları | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Çapraz platform |
| Bitwarden eklentisi | ❌ | Bunun yerine ana parola kullanın |
| Windows Hello | ❌ | Desteklenmiyor |

## Başsız (Headless) CLI Kaydı

Tarayıcısı olmayan bir makine (bir sunucu, bir CI çalıştırıcısı, bir executor daemon'u) ana parola yöntemiyle mevcut bir depoya kaydolabilir:

```bash
rdc config remote enable --password
```

Gereksinimler:

- Portal üzerinden önceden sağlanmış bir **ana parola yuvası** (sağlama sırasında anahtarı tarayıcı tuttuğu için bu adımın kendisi başsız olamaz)
- Çağrıyı doğrulamak için `config:enroll` kapsamına sahip bir **API token'ı**

Kayıt işlemi bir okumadır: CLI, yuvanın herkese açık KDF parametrelerini ve sarmalanmış anahtarı getirir, parola sırrını yerel olarak türetir ve CEK'in kilidini cihazda açar. Bu işlem cihaza yapılandırmayı çözme ve senkronize etme yetkisi verir; depoda herhangi bir değişiklik yapmaz.

## Etkinleştirme ve Çevrimdışı Okumalar

`rdc config remote enable`, etkin yapılandırmayı depoya bağlar. Depo boşsa, etkinleştirme işlemi **depoyu mevcut yerel yapılandırmanızdan tohumlar**: yerel kaynaklar deponun ilk sürümü olarak gönderilir, ardından geri çekilerek gidiş-dönüşün doğru çalıştığı kanıtlanır. Depoda zaten içerik varsa, etkinleştirme üzerine yazmak yerine mevcut içerikle uzlaştırılır (gerçek bir sapma olduğunda `--force` geçirilmediği sürece işlem iptal edilir).

Etkinleştirildikten sonra yapılandırma, herhangi bir yerel yapılandırmayla aynı mekanizmayla durağan halde şifrelenmiş tam bir **okuma önbelleği** tutar; böylece hesap sunucusuna ulaşılamadığında bile depo kullanılabilir kalır:

- **Okumalar çevrimdışı çalışır.** Önbelleğe alınmış içerik, önbellek sürümü ve zaman damgasıyla (`cachedVersion` / `cachedAt`) etiketlenmiş bir bayatlık uyarısıyla birlikte stderr'e yazdırılır.
- **Yazmalar sunucu gerektirir ve kapalı biçimde başarısız olur.** Çevrimdışı bir yazma kuyruğu yoktur: sunucuya ulaşamayan bir yazma işlemi, sunucunun adını belirterek hata verir. Bir yazma komutu başarılı olduysa, değişiklik sunucudadır.
- **İki makineden gelen eşzamanlı düzenlemeler**, çek-yeniden oynat-yeniden gönder (pull-replay-repush) ile çözülür: sunucu bir gönderimi yalnızca değiştirdiği sürümün üzerine kabul eder ve kaybeden gönderim güncel kopya üzerinde yeniden oynatılır; böylece başka bir yerdeki eşzamanlı bir düzenleme geçersiz kılınmaz.
- **Yerel bir yapılandırma** (bir `remote` bloğu olmayan) bundan hiç etkilenmez ve tamamen çevrimdışı çalışır.

## Neler senkronize edilir

`schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier` ile oturum açma alanları `account.accountServer` ve `account.e2ePublicKey` dışında, her deponun ağ kimliği dahil olmak üzere bir yapılandırmadaki her şey senkronize edilir. Oturum açma ve kapatma cihaz bazlıdır.

## Sürümler ve geri yükleme

Sunucu her yapılandırmanın son 50 sürümünü tutar.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Bir geri yükleme, eski içeriği mevcut sürümün üzerine yeni bir sürüm olarak yayımlar; sürüm numarasını asla geriye almaz. Her cihaz, bir sonraki pull işleminde geri yüklenen içeriği alır ve geri yükleme denetim günlüğüne kaydedilir.

## Anahtar Rotasyonu

Deponun CEK'ini rotasyona sokmak, anahtarı yeni bir nesil altında yeniden sarmalar:

- **Kurtarma kodları rotasyonla her zaman geçersiz kılınır**, ardından yeni bir kod oluşturup saklayın
- Bir **ana parola yuvası** yalnızca rotasyon sihirbazı sırasında parola yeniden girilirse hayatta kalır
- Eski bir nesilde kalan bir yuva, anlaşılmaz bir şifre çözme hatası vermek yerine bayat (stale) olarak raporlanır
- Diğer üyelerin yapılandırma token'ları iptal edilir ve eski anahtarı hâlâ tutan bir cihaza `rdc config remote enable` ile yeniden etkinleştirmesi söylenir

## Üye Yönetimi

Yapılandırma depolama, organizasyon bazında kapsamlıdır. Üyeler web portalı üzerinden yönetilir:

- **Üyeleri görüntüle**: Yapılandırma Depolama → Üyeler
- **Üye ekle**: Şu anda yalnızca CLI üzerinden (web arayüzü planlanıyor)
- **Üye kaldır**: Üyeler sayfasındaki kaldır düğmesine tıklayın (2FA + yeniden kimlik doğrulama gerektirir)

Güvenlik korumaları, son aktif üyeyi kaldırmayı veya kendinizi kaldırmayı engeller.

Depodaki yapılandırmalar ayrıca ekip bazında da kapsamlıdır, ancak bu kapsam **sunucu tarafı erişim denetimidir, kriptografik izolasyon değildir**: organizasyon genelinde tek bir CEK tüm ekiplerin yapılandırmalarını şifreler ve bir üyenin hangi ekipleri okuyabileceğini sunucu belirler.

## Güvenlik

**Neyin korunduğu.** Depolanan yapılandırmalar, sunucunun depolamasının ele geçirilmesine ve pasif bir operatöre karşı gizlidir. Her blob kendi deposuna, yapılandırmasına, ekibine ve sürümüne bağlıdır; bu yüzden sunucu bir yapılandırmanın blob'unu başka birininkiyle değiştiremez veya fark edilmeden değiştiremez.

**Neyin korunmadığı.** Kötü amaçlı portal kodu sunan bir operatör, anahtarı tarayıcıda okuyabilir. Bir operatör, en yeni sürümü onu hiç görmemiş bir cihazdan da alıkoyabilir.

| Sunucunun yapabildiği | Sunucunun yapamadığı |
|---|---|
| Yapılandırma kimliklerini, ekipleri, sürüm numaralarını, zaman damgalarını, blob boyutlarını, bir yapılandırmanın kaç alan içerdiğini ve her alanın türünü, ve istemci IP adreslerini görmek | Makine, depo veya depolama adlarını (körleştirilmiştir) ya da herhangi bir yapılandırma değerini görmek |
| Yapılandırmaları ve geçmişlerini reddetmek, geciktirmek veya silmek | Bir yapılandırmanın içeriğini başka birininki gibi sunmak veya cihaz fark etmeden düzenlemek |
| Daha yeni bir sürüm hiç görmemiş bir cihaza eski bir sürüm sunmak | CLI'a zaten gördüğü bir sürümden daha eskisini sunmak: CLI bunu reddeder |
| Ana parolayı çevrimdışı tahmin etmeye çalışmak | Bir passkey ya da kurtarma kodu yuvasını açmak |

Diğer korumalar:

- **Bölünmüş anahtar**: şifre çözme hem yuva sırrını (cihazda) hem de sunucu sırrını gerektirir
- **Silme bilgi gerektirir**: bir yapılandırmadan onaylanmış bir değeri kaldırmak, değerin bilindiğinin kanıtlanmasını gerektirir; böylece kısmi erişimi olan bir aracı alanları sessizce silemez
- **Dönen token'lar**: her istek yapılandırma token'ını döndürür; bir token ilk kullanıldığı IP adresine bağlıdır ve 7 gün sonra sona erer
- **İptal**: bir üyeyi kaldırmak, o üyenin anahtar yuvalarını ve token'larını aynı anda siler; üyenin daha önce çektiği içerik kendi cihazında kalır, ve bir CEK rotasyonu üyenin sakladığı bir anahtarın sonraki sürümleri açmasını engeller

## Sorun Giderme

| Hata | Neden | Çözüm |
|-------|-------|-----|
| PRF not supported | Kimlik doğrulayıcı PRF uzantısından yoksun | YubiKey, iCloud Keychain, 1Password veya Dashlane kullanın, ya da bir ana parola yuvası ekleyin |
| X25519 not supported | Tarayıcı sürümü çok eski | Chrome 133+, Edge 133+, Firefox 130+ veya Safari 17+'ye güncelleyin |
| Already configured | Organizasyonunuz için depo zaten mevcut | Yönetmek için /account/config-storage adresini ziyaret edin |
| Config storage not configured | Sunucuda blob depolama eksik | R2/RustFS yapılandırması için yöneticinize başvurun |
| Token expired | 7 gündür etkinlik yok, ya da makine ağ değiştirdi | Girişten (login) otomatik olarak yenilenir; kayıtlı bir giriş yoksa `rdc subscription login` veya `rdc config remote enable` çalıştırın |
| Yapılandırma daha eski bir sürümle döndü | Sunucu, bu cihazın zaten gördüğünden daha eski bir kopya döndürdü | Yerelde bir şey değişmedi; tekrar deneyin, sürerse bildirin |
| Cannot remove last member | Depoyu kalıcı olarak kilitler | Önce başka bir üye ekleyin |
| Stale slot | Yuva, son anahtar rotasyonundan öncesine ait | Yuvayı yeniden ekleyin (kurtarma kodları her rotasyondan sonra yeniden oluşturulmalıdır) |

## İlgili

- [Web Konsolu](/tr/docs/web-console), depoyu tarayıcıda açarak komut çalıştırma
- [Proxy ve Executor](/tr/docs/proxy-and-executor), açılmış anahtarın bir executor'a nasıl verildiği
