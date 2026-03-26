---
title: Hesap Guvenligi ve API
description: Kimlik dogrulama, API tokenleri, oturum yonetimi ve izin modeli.
category: Guides
order: 13
language: tr
---

### Kimlik Dogrulama

Rediacc birden fazla kimlik dogrulama yontemini destekler:

![Auth Flow](/img/account-auth-flow.svg)

- **Parola**: Geleneksel e-posta + parola ile giris
- **Magic Link**: E-posta baglantisi ile parolasiz giris (15 dakika gecerlilik)
- **Iki Faktorlu Kimlik Dogrulama (2FA)**: Yedek kodlarla TOTP tabanli

2FA etkinlestirildiginde, giris icin hem parolaniz (veya Magic Link) hem de 6 haneli bir TOTP kodu gerekir.

### API Tokenleri

API tokenleri makineler arasi islemleri dogrular (CLI lisans aktivasyonu, durum kontrolleri).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Kapsamlar:**
- `license:read` -- Abonelik ve lisans durumunu sorgulama
- `license:activate` -- Makineleri etkinlestirme ve depo lisanslari verme
- `subscription:read` -- Abonelik detaylarini okuma

**Guvenlik ozellikleri:**
- IP baglama: ilk istek tokeni o IP adresine kilitler
- Ekip kapsamlandirma: tokenler belirli bir ekiple sinirlandirabilir
- Otomatik iptal: olusturucu organizasyondan kaldirildiginda tokenler iptal edilir

Token olusturma:
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### Cihaz Kodu Akisi

CLI, cihaz kodu akisini kullanarak ekransiz makinelerde kimlik dogrulamasi yapabilir:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

Sifrelenmis, sunucu ile senkronize yapilandirma icin tam kilavuza [Config Storage](/en/docs/config-storage) bakiniz. Config Storage sunlari kullanir:
- Sifir bilgi sifreleme (sunucu duz metni asla gormez)
- Passkey tabanli anahtar turetme (WebAuthn + PRF)
- Istek basina rotasyonlu dondurmeli tokenler

### Oturum Guvenligi

| Token Turu | Gecerlilik Suresi | Depolama | Yenileme |
|-----------|-------------------|----------|----------|
| Access Token (JWT) | 15 dakika | HttpOnly cookie | Refresh token ile otomatik |
| Refresh Token | 7 gun | HttpOnly cookie | Her kullanimda dondurulur |
| Elevated Session | 10 dakika | Sunucu tarafi | Yeniden kimlik dogrulama ile tetiklenir |

Yukseltilmis oturumlar hassas islemler icin gereklidir: parola degisiklikleri, e-posta degisiklikleri, 2FA kurulumu, sahiplik aktarimlari ve yikici yonetici eylemleri.

### Izin Modeli

Rediacc uc bagimsiz izin katmani kullanir:

![Permission Flow](/img/account-permission-flow.svg)

**Katman 1: Sistem Rolu** -- Sistem yonetimi uc noktlarina erisimi belirler.

**Katman 2: Organizasyon Rolu** -- Bir kullanicinin organizasyonu icinde neler yapabilecegini kontrol eder (owner, admin, member).

**Katman 3: Ekip Rolu** -- Belirli ekip kaynaklarina erisimi sinirlar (team_admin, member). Organizasyon sahipleri ve yoneticileri ekip rolu kontrollerini atlar.

Her API istegi tum gecerli katmanlardan sirasiyla gecer. Ekip kapsamli bir uc noktaya yapilan istek, oturum dogrulamasi, organizasyon uyeligi ve ekip erisimini karsilamalidir.

### Guncelleme Kanallari

CLI iki yayin kanalini destekler:
- **stable** (varsayilan): Kapsamli test edilmis, uretim icin onerilir
- **edge**: En son ozellikler, her surumde guncellenir

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
