---
title: "Config Storage (Rediacc Provider)"
description: "Sıfır bilgi şifrelemesi ile CLI yapılandırmasını cihazlar ve ekipler arasında güvenli bir şekilde senkronize edin."
category: "Guides"
order: 9
language: tr
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

Rediacc yapılandırma depolama sağlayıcısı, sıfır bilgi şifrelemesi ile CLI yapılandırmanızı cihazlar ve ekipler arasında senkronize eder. SSH anahtarlarınız, makine IP'leriniz ve kimlik bilgileriniz makinenizden ayrılmadan önce istemci tarafında şifrelenir -- Rediacc operatörleri bile verilerinizi okuyamaz.

## Ön Koşullar

- **PRF destekli passkey sağlayıcısı**: bir FIDO2 güvenlik anahtarı (ör. YubiKey), iCloud Keychain, Google Password Manager, 1Password veya Dashlane
- **2FA etkinleştirilmiş** organizasyon sahipleri/yöneticiler için (store kurulumu ve üye yönetimi için gerekli)
- **Hesap aboneliği** config storage etkinleştirilmiş olarak

## Hızlı Başlangıç

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Kurulum

### Masaüstü (Tarayıcı Mevcut)

```bash
rdc store add my-config --type rediacc
```

1. Rediacc hesap portalına bir tarayıcı penceresi açılır
2. Bir passkey kaydedin (YubiKey/iCloud Keychain/1Password açılan penceresi)
3. Passkey'in PRF uzantısı şifreleme anahtarlarınızı türetir
4. Anahtarlar işletim sisteminizin yerel güvenli depolamasında saklanır (Keychain/keyctl/DPAPI)
5. Tamam -- hatırlanacak şifre yok

### Başsız Sunucular (Tarayıcı Yok)

```bash
rdc store add my-config --type rediacc --headless
```

1. CLI bir cihaz kodu ile bir URL gösterir
2. URL'yi telefonunuzda veya dizüstü bilgisayarınızda açın
3. Tarayıcıda passkey kaydını tamamlayın
4. CLI güvenli bir relay aracılığıyla şifreli anahtarlarınızı otomatik olarak alır
5. Sıfır bilgi korunur -- sunucu yalnızca opak şifreli bir blob iletir

### Özel Sunucu URL'si

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

Kurulumdan sonra push ve pull herhangi bir şifre veya istem olmadan çalışır:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Her işlem, tek kullanımdan sonra kendini yok eden dönen bir token kullanır. Statik kimlik bilgisi yoktur.

## Takım Yönetimi

Takım üyeleri `/account/config-storage/members` adresindeki web portalı üzerinden yönetilir.

### Üye Ekleme

1. Yönetici config storage üye sayfasını açar
2. "Add Member"a tıklar (2FA gerektirir)
3. Yöneticinin tarayıcısı yeni üye için takım şifreleme anahtarını şifreler
4. Yeni üye giriş yapar ve daveti kabul eder
5. Her ikisi de artık aynı yapılandırmaları push/pull yapabilir

### Üye Kaldırma

1. Yönetici üyenin yanındaki "Remove"a tıklar (2FA gerektirir)
2. Üyenin şifreleme anahtarları hemen silinir
3. 30 saniye içinde üye şifreli yapılandırmalara tüm erişimini kaybeder

Anahtar rotasyonu gerekmez -- sunucu kaldırılan üyeye şifre çözme anahtarlarını sunmayı durdurur.

## Güvenlik Özellikleri

| Özellik | Nasıl |
|---------|-------|
| **Sıfır bilgi** | İstemci göndermeden önce şifreler; sunucu yalnızca opak blob'ları görür |
| **Ana şifre yok** | Passkey biyometrisi şifreleri tamamen değiştirir |
| **Bölünmüş anahtar türetimi** | CEK hem passkey_secret (istemci) + server_secret (sunucu) gerektirir |
| **Dönen tokenlar** | Her API çağrısı yeni bir token oluşturur; eskileri geçersiz olur |
| **IP bağlama** | Tokenlar ilk kullanımda istemci IP'sine bağlanır |
| **Üçlü şifreleme** | SDK (zaman pencereli) + CEK (istemci) + organizasyon parolası (sunucu) |
| **Anında iptal** | Kaldırılan üyelere SDK sunumunu durdurma; maksimum 30 saniye gecikme |
| **Tahrifat tespiti** | Şifreli blob'lar üzerinde HMAC; her pull'da doğrulanır |

Tam güvenlik mimarisi için [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md) sayfasına bakın.

## Sorun Giderme

### "Passkey must support PRF extension"

Passkey sağlayıcınız PRF uzantısını desteklemiyor. Şunları kullanın:
- Bir FIDO2 güvenlik anahtarı (ör. YubiKey)
- iCloud Keychain (macOS/iOS'ta Safari)
- Google Password Manager (Android/ChromeOS'ta Chrome)
- 1Password
- Dashlane

### "Two-factor authentication required"

Organizasyon sahipleri ve yöneticileri config storage kurmadan önce 2FA'yı etkinleştirmelidir. Account Settings -> Security -> Enable 2FA'ya gidin.

### "Version conflict"

Başka bir takım üyesi daha yeni bir sürüm gönderdi. Önce çekin:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Tokenlar 24 saat etkinlik olmadıktan sonra sona erer. Yenilemek için herhangi bir komut çalıştırın:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

Şifreleme anahtarı işletim sisteminizin güvenli depolamasından kayboldu (Linux'ta yeniden başlatma, keychain sıfırlama). Kurulumu yeniden çalıştırın:
```bash
rdc store add my-config --type rediacc
```
