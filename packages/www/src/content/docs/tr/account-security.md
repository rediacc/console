---
title: Hesap Güvenliği ve API
description: Kimlik doğrulama, API tokenleri, oturum yönetimi ve izin modeli.
category: Guides
order: 13
language: tr
---

### Kimlik Doğrulama

Rediacc birden fazla kimlik doğrulama yöntemini destekler:

![Auth Flow](/img/account-auth-flow.svg)

- **Parola**: Geleneksel e-posta + parola ile giriş
- **Magic Link**: E-posta bağlantısı ile parolasız giriş (15 dakika geçerlilik)
- **İki Faktörlü Kimlik Doğrulama (2FA)**: Yedek kodlarla TOTP tabanlı

2FA etkinleştirildiğinde, giriş için hem parolanız (veya Magic Link) hem de 6 haneli bir TOTP kodu gerekir.

### API Tokenleri

API tokenleri makineler arası işlemleri doğrular (CLI lisans aktivasyonu, durum kontrolleri).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Kapsamlar:**
- `license:read` -- Abonelik ve lisans durumunu sorgulama
- `license:activate` -- Makineleri etkinleştirme ve depo lisansları verme
- `subscription:read` -- Abonelik detaylarını okuma

**Güvenlik özellikleri:**
- IP bağlama: ilk istek tokeni o IP adresine kilitler
- Ekip kapsamlandırma: tokenler belirli bir ekiple sınırlandırılabilir
- Otomatik iptal: oluşturucu organizasyondan kaldırıldığında tokenler iptal edilir

Token oluşturma:
```bash
# Portal üzerinden: API Tokens > Create
# Token değeri yalnızca bir kez gösterilir -- güvenli şekilde saklayın
```

### Cihaz Kodu Akışı

CLI, cihaz kodu akışını kullanarak ekransız makinelerde kimlik doğrulaması yapabilir:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Gösterir: XXXX-XXXX-XX kodunu https://www.rediacc.com/account/authorize adresine girin
# Onaydan sonra CLI otomatik olarak kimlik bilgilerini alır
```

### Config Storage

Şifrelenmiş, sunucu ile senkronize yapılandırma için tam kılavuza [Config Storage](/tr/docs/config-storage) bakınız. Config Storage şunları kullanır:
- Sıfır bilgi şifreleme (sunucu düz metni asla görmez)
- Passkey tabanlı anahtar türetme (WebAuthn + PRF)
- İstek başına rotasyonlu döndürmeli tokenler

### Oturum Güvenliği

| Token Türü | Geçerlilik Süresi | Depolama | Yenileme |
|-----------|-------------------|----------|----------|
| Access Token (JWT) | 15 dakika | HttpOnly cookie | Refresh token ile otomatik |
| Refresh Token | 7 gün | HttpOnly cookie | Her kullanımda döndürülür |
| Yükseltilmiş Oturum | 10 dakika | Sunucu tarafı | Yeniden kimlik doğrulama ile tetiklenir |

Yükseltilmiş oturumlar hassas işlemler için gereklidir: parola değişiklikleri, e-posta değişiklikleri, 2FA kurulumu, sahiplik aktarımları ve yıkıcı yönetici eylemleri.

### İzin Modeli

Rediacc üç bağımsız izin katmanı kullanır:

![Permission Flow](/img/account-permission-flow.svg)

**Katman 1: Sistem Rolü** -- Sistem yönetimi uç noktalarına erişimi belirler.

**Katman 2: Organizasyon Rolü** -- Bir kullanıcının organizasyonu içinde neler yapabileceğini kontrol eder (owner, admin, member).

**Katman 3: Ekip Rolü** -- Belirli ekip kaynaklarına erişimi sınırlar (team_admin, member). Organizasyon sahipleri ve yöneticileri ekip rolü kontrollerini atlar.

Her API isteği tüm geçerli katmanlardan sırasıyla geçer. Ekip kapsamlı bir uç noktaya yapılan istek, oturum doğrulaması, organizasyon üyeliği ve ekip erişimini karşılamalıdır.

### Güncelleme Kanalları

CLI iki yayın kanalını destekler:
- **stable** (varsayılan): Kapsamlı test edilmiş, üretim için önerilir
- **edge**: En son özellikler, her sürümde güncellenir

```bash
rdc update --channel edge      # Edge'e geç
rdc update --channel stable    # Stable'a geri dön
rdc update --status            # Geçerli kanalı göster
```
