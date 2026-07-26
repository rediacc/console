---
title: Yapılandırma Depolama
description: Passkey, ana parola ve kurtarma koduyla açılabilen sıfır bilgi şifreli yapılandırma senkronizasyonu
category: Guides
order: 8
language: tr
sourceHash: "97c64241ff4c0d81"
sourceCommit: "433347c5ea4754300fe3da80c4bfcee42dd161bc"
---

# Yapılandırma Depolama

Yapılandırma depolama, CLI yapılandırmanızın cihazlar arasında sıfır bilgi şifreli senkronizasyonunu sağlar. Yapılandırmalarınız istemci tarafında bir içerik şifreleme anahtarıyla (CEK) şifrelenir, sunucu düz metin verileri asla görmez.

## Kilit açma yöntemleri (anahtar yuvaları)

Her depo için tek bir CEK vardır ve bu anahtar, LUKS'un anahtar yuvalarına benzer şekilde her kilit açma yöntemi için ayrı ayrı sarmalanır. Yuvalardan herhangi biri aynı anahtarı açar, yuvalar ise verilerinizi yeniden şifrelemeden eklenebilir veya kaldırılabilir:

| Yöntem | Nedir | Notlar |
|--------|-----------|-------|
| **Passkey** | PRF uzantılı WebAuthn passkey | En güçlü seçenek; donanım destekli |
| **Ana parola** | Seçtiğiniz, PBKDF2-SHA256 ile (600.000 yineleme) güçlendirilmiş bir parola | PRF destekli donanım gerektirmez; CLI'ı başsız (headless) olarak kaydetmeyi de mümkün kılar |
| **Kurtarma kodu** | Oluşturulan bir `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` kodu | Oluşturulduğunda yalnızca bir kez gösterilir; güvenli bir yerde saklayın |

Her yöntem aynı süreçten geçer: yuva, CEK'in kilidini açmak için sunucudaki bir sırla birleşen bir sır üretir. Bu yarımlardan hiçbiri tek başına yeterli değildir, dolayısıyla sıfır bilgi özelliği her üç yöntemde de korunur; yuva sırrı sunucuya asla ulaşmaz.

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
3. **Kurulumu Başlat**'a tıklayın. Passkey yuvası için güvenlik anahtarınıza iki kez dokunmanız gerekecek:
   - İlk dokunuş: passkey'i kaydeder
   - İkinci dokunuş: PRF aracılığıyla şifreleme anahtarlarını türetir
4. Kurulum tamamlandı, passkey sırrınız işletim sisteminizin anahtar zincirinde saklanır

Kurulumdan sonra, kayıp veya desteklenmeyen bir kimlik doğrulayıcının sizi dışarıda bırakmaması için Yapılandırma Depolama sayfasından bir ana parola veya kurtarma kodu yuvası ekleyin.

## PRF Sağlayıcı Uyumluluğu

| Sağlayıcı | PRF Desteği | Platformlar |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 güvenlik anahtarları | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Çapraz platform |
| Bitwarden eklentisi | ❌ | Geliştirme aşamasında |
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
- **İki makineden gelen eşzamanlı düzenlemeler**, kaynak-bucket düzeyinde çek-yeniden oynat-yeniden gönder (pull-replay-repush) ile çözülür; böylece başka bir yerdeki eşzamanlı bir düzenleme sizinkini geçersiz kılmaz.

## Anahtar Rotasyonu

Deponun CEK'ini rotasyona sokmak, anahtarı yeni bir nesil altında yeniden sarmalar:

- **Kurtarma kodları rotasyonla her zaman geçersiz kılınır**, ardından yeni bir kod oluşturup saklayın
- Bir **ana parola yuvası** yalnızca rotasyon sihirbazı sırasında parola yeniden girilirse hayatta kalır
- Eski bir nesilde kalan bir yuva, anlaşılmaz bir şifre çözme hatası vermek yerine bayat (stale) olarak raporlanır

## Üye Yönetimi

Yapılandırma depolama, organizasyon bazında kapsamlıdır. Üyeler web portalı üzerinden yönetilir:

- **Üyeleri görüntüle**: Yapılandırma Depolama → Üyeler
- **Üye ekle**: Şu anda yalnızca CLI üzerinden (web arayüzü planlanıyor)
- **Üye kaldır**: Üyeler sayfasındaki kaldır düğmesine tıklayın (2FA + yeniden kimlik doğrulama gerektirir)

Güvenlik korumaları, son aktif üyeyi kaldırmayı veya kendinizi kaldırmayı engeller.

Depodaki yapılandırmalar ayrıca ekip bazında da kapsamlıdır, ancak bu kapsam **sunucu tarafı erişim denetimidir, kriptografik izolasyon değildir**: organizasyon genelinde tek bir CEK tüm ekiplerin yapılandırmalarını şifreler ve bir üyenin hangi ekipleri okuyabileceğini sunucu belirler.

## Güvenlik

- **Sıfır bilgi**: Sunucu, çözemeyeceği üçlü şifreli verileri depolar
- **Bölünmüş anahtar**: Şifre çözme, hem yuva sırrınızı (istemci) hem de sunucu sırrını (sunucu) gerektirir
- **Dönen tokenlar**: Her API çağrısı yeni bir token kullanır; eski tokenlar kendini yok eder
- **IP bağlama**: Tokenlar ilk kullanımda IP'nize bağlanır
- **Anında iptal**: Kaldırılan üyeler 30 saniye içinde erişimi kaybeder

## Sorun Giderme

| Hata | Neden | Çözüm |
|-------|-------|-----|
| PRF not supported | Kimlik doğrulayıcı PRF uzantısından yoksun | YubiKey, iCloud Keychain, 1Password veya Dashlane kullanın, ya da bir ana parola yuvası ekleyin |
| X25519 not supported | Tarayıcı sürümü çok eski | Chrome 133+, Edge 133+, Firefox 130+ veya Safari 17+'ye güncelleyin |
| Already configured | Organizasyonunuz için depo zaten mevcut | Yönetmek için /account/config-storage adresini ziyaret edin |
| Config storage not configured | Sunucuda blob depolama eksik | R2/RustFS yapılandırması için yöneticinize başvurun |
| Token expired | 24 saattir etkinlik yok | Yenilemek için herhangi bir yapılandırma depolama komutu çalıştırın |
| Cannot remove last member | Depoyu kalıcı olarak kilitler | Önce başka bir üye ekleyin |
| Stale slot | Yuva, son anahtar rotasyonundan öncesine ait | Yuvayı yeniden ekleyin (kurtarma kodları her rotasyondan sonra yeniden oluşturulmalıdır) |

## İlgili

- [Web Konsolu](/tr/docs/web-console), depoyu tarayıcıda açarak komut çalıştırma
- [Proxy ve Executor](/tr/docs/proxy-and-executor), açılmış anahtarın bir executor'a nasıl verildiği
