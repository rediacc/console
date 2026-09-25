---
title: Hesap Güvenliği ve API
description: Kimlik doğrulama, API tokenleri, oturum yönetimi ve izin modeli.
category: Guides
tags:
  - account
  - security
subcategory: account
order: 13
language: tr
sourceHash: "cbfa1730b069f73c"
sourceCommit: "c707ed4d0e178e7c4cec46e5ff989a1472a8eb82"
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
- IP bağlama: bir token yalnızca ilk isteğinin geldiği IP adresinde geçerlidir; yeni bir adres için TOTP doğrulaması ya da yeniden giriş gerekir (aşağıya bakın)
- Ekip kapsamlandırma: tokenler belirli bir ekiple sınırlandırılabilir
- Otomatik iptal: oluşturucu organizasyondan kaldırıldığında tokenler iptal edilir

Token oluşturma:
```bash
# Portal üzerinden: API Tokens > Create
# Token değeri yalnızca bir kez gösterilir -- güvenli şekilde saklayın
```

#### IP adresi değiştiğinde

Bir IP adresine bağlı token başka her adresten reddedilir; örneğin internet sağlayıcısı yeni bir adres verdiğinde. Taşımayı CLI üstlenir:

- **Etkileşimli terminal, 2FA açık**: CLI kimlik doğrulama uygulamasındaki 6 haneli kodu sorar, tokeni yeni adrese taşır ve komutu yeniden çalıştırır. Taşıma için yedek kodlar kabul edilmez.
- **Betikler ve CI (terminal yok)**: komut başarısız olur ve iki çözümü de belirtir: etkileşimli bir terminalde herhangi bir `rdc` komutunu bir kez çalıştırıp (örneğin `rdc subscription status`) kodu girmek ya da `rdc subscription login` çalıştırmak.
- **2FA kapalı**: token taşınamaz. `rdc subscription login` yeni bir token verir; 2FA açıkken bir sonraki taşıma için yalnızca kod yeterlidir.
- **Yanlış kodlar**: 15 dakika içinde 5 yanlış kod taşımayı kilitler; önce 5 dakika, sonra her seferinde iki katı, en fazla 1 saat. 4 kilitten sonra o token için taşıma, bir sonraki `rdc subscription login` işlemine kadar kapatılır.
- IP bağlaması `unbound` veya `cloudflare` olan **executor tokenleri** bundan etkilenmez.

Her taşıma, eski ve yeni adresle birlikte portalın etkinlik günlüğünde görünür.

### Cihaz Kodu Akışı

CLI, cihaz kodu akışını kullanarak ekransız makinelerde kimlik doğrulaması yapabilir:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc subscription login
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
- **stable** (varsayılan): 7 günlük bekleme süresinin ardından edge'den terfi ettirilir; muhafazakar bir yükseltme temposu için bu kanalı seçin
- **edge**: En son özellikler, her sürümde güncellenir

```bash
rdc update --channel edge      # Edge'e geç
rdc update --channel stable    # Stable'a geri dön
rdc update --status            # Geçerli kanalı göster
```

### Yapay Zeka Ajanları için CLI Güvenlik Duruşu

`rdc`'yi çağıran kodlama ajanları gerçek bir tehdit yüzeyi; bu yüzden onlara ayrı bir özne gibi davranıyoruz. Her `rdc` çağrısı başlangıçta ortam sinyallerine (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) ve bir Linux `/proc` soy ağacı yürüyüşüne göre **insan** veya **ajan** olarak sınıflandırılır. Tespit yöntem olarak en iyiyi amaçlar. Kararlı bir sarmalayıcı ortam değişkenlerini sahte gösterebilir; bu yüzden soy ağacı önemlidir. Ajanlar azaltılmış bir izin kümesi alır: hassas yapılandırma mutasyonları bilgi kapısı gerektirir (`--current <eski>`), etkileşimli düzenleyici soy ağacıyla doğrulanmış `REDIACC_ALLOW_CONFIG_EDIT` geçersiz kılması olmadan reddedilir ve herhangi bir görüntüleme komutundaki `--reveal` engellenir. Her karar (izin ver, reddet veya `--reveal` ver) `~/.config/rediacc/audit.log.jsonl` dosyasına hash zincirine bağlı bir JSONL satırı yazar. Zincir bütünlüğünü kontrol etmek için `rdc config audit verify` çalıştırın.

Ajanların yapabilecekleri ve yapamadıklarının tam matrisi, bilgi kapısı örnekleri ve kapsam geçersiz kılma mekanizmaları için bkz. [Yapay Zeka Ajanı Güvenliği ve Korumalar](/tr/docs/ai-agents-safety).
