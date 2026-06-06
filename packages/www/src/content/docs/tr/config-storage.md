---
title: Yapılandırma Depolama
description: Passkey tabanlı şifreleme ile sıfır bilgi şifreli yapılandırma senkronizasyonu
category: Guides
order: 8
language: tr
sourceHash: "daf79946b8925246"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Yapılandırma Depolama

Yapılandırma depolama, CLI yapılandırmanızın cihazlar arasında sıfır bilgi şifreli senkronizasyonunu sağlar. Yapılandırmalarınız passkey'inizden türetilen anahtarlarla şifrelenir, sunucu düz metin verileri asla görmez.

## Ön Koşullar

- **İki faktörlü kimlik doğrulama** hesabınızda etkinleştirilmiş olmalıdır
- **PRF desteğine sahip passkey sağlayıcısı**: FIDO2 güvenlik anahtarı (örn. YubiKey), iCloud Keychain, Google Password Manager, 1Password veya Dashlane
- **Tarayıcı**: Chrome 133+, Edge 133+, Firefox 130+ veya Safari 17+

## Kurulum

1. Kenar çubuğunda **Yapılandırma Depolama**'ya gidin, ardından **Yapılandırma Depolamayı Kur**'a tıklayın
2. Gereksinimler kontrol listesi tarayıcınızı, 2FA'yı ve oturum durumunu doğrular
3. **Kurulumu Başlat**'a tıklayın, güvenlik anahtarınıza iki kez dokunmanız gerekecek:
   - İlk dokunuş: passkey'i kaydeder
   - İkinci dokunuş: PRF aracılığıyla şifreleme anahtarlarını türetir
4. Kurulum tamamlandı, passkey sırrınız işletim sisteminizin anahtar zincirinde saklanır

Kurulumdan sonra, günlük CLI işlemleri (push/pull) passkey olmadan çalışır. Uyarı: kurulum, PRF uzantısı desteğine sahip bir passkey gerektirir. Her donanım belirteci veya platform kimlik doğrulayıcısı bunu desteklemez.

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

## Üye Yönetimi

Yapılandırma depolama, organizasyon bazında kapsamlıdır. Üyeler web portalı üzerinden yönetilir:

- **Üyeleri görüntüle**: Yapılandırma Depolama → Üyeler
- **Üye ekle**: Şu anda yalnızca CLI üzerinden (web arayüzü planlanıyor)
- **Üye kaldır**: Üyeler sayfasındaki kaldır düğmesine tıklayın (2FA + yeniden kimlik doğrulama gerektirir)

Güvenlik korumaları, son aktif üyeyi kaldırmayı veya kendinizi kaldırmayı engeller.

## Güvenlik

- **Sıfır bilgi**: Sunucu, çözemeyeceği üçlü şifreli verileri depolar
- **Bölünmüş anahtar**: Şifre çözme, hem passkey sırrınızı (istemci) hem de sunucu sırrını (sunucu) gerektirir
- **Dönen tokenlar**: Her API çağrısı yeni bir token kullanır; eski tokenlar kendini yok eder
- **IP bağlama**: Tokenlar ilk kullanımda IP'nize bağlanır
- **Anında iptal**: Kaldırılan üyeler 30 saniye içinde erişimi kaybeder

## Sorun Giderme

| Hata | Neden | Çözüm |
|-------|-------|-----|
| PRF not supported | Kimlik doğrulayıcı PRF uzantısından yoksun | YubiKey, iCloud Keychain, 1Password veya Dashlane kullanın |
| X25519 not supported | Tarayıcı sürümü çok eski | Chrome 133+, Edge 133+, Firefox 130+ veya Safari 17+'ye güncelleyin |
| Already configured | Organizasyonunuz için depo zaten mevcut | Yönetmek için /account/config-storage adresini ziyaret edin |
| Config storage not configured | Sunucuda blob depolama eksik | R2/RustFS yapılandırması için yöneticinize başvurun |
| Token expired | 24 saattir etkinlik yok | Yenilemek için herhangi bir yapılandırma depolama komutu çalıştırın |
| Cannot remove last member | Depoyu kalıcı olarak kilitler | Önce başka bir üye ekleyin |
