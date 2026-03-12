---
title: Abonelik ve Lisanslama
description: Yerel dağıtımlar için abonelikleri ve makine lisanslarını yönetin.
category: Guides
order: 7
language: tr
sourceHash: 58873ba427babd61
---

# Abonelik ve Lisanslama

Yerel dağıtımlarda çalışan makineler, plana dayalı kaynak sınırlarını uygulamak için bir abonelik lisansına ihtiyaç duyar. CLI, imzalı lisans bloblarını SSH aracılığıyla uzak makinelere otomatik olarak iletir — sunucu tarafında manuel aktivasyon veya bulut bağlantısı gerekmez.

## Genel Bakış

1. `rdc subscription login` ile giriş yapın (kimlik doğrulama için tarayıcı açılır)
2. Herhangi bir makine komutunu kullanın — lisanslar otomatik olarak yönetilir

Bir makineyi hedefleyen bir komut çalıştırdığınızda (`rdc machine info`, `rdc repo up` vb.), CLI makinede geçerli bir lisans olup olmadığını otomatik olarak kontrol eder. Yoksa, hesap sunucusundan bir tane alır ve SSH aracılığıyla iletir.

## Giriş

```bash
rdc subscription login
```

Cihaz kodu akışı ile kimlik doğrulama için tarayıcı açar. Onaydan sonra CLI, API belirtecini `~/.config/rediacc/api-token.json` konumuna yerel olarak kaydeder.

| Seçenek | Gerekli | Varsayılan | Açıklama |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | API belirteci (tarayıcı akışını atlar) |
| `--server <url>` | No | `https://www.rediacc.com/account/` | Hesap sunucusu URL'si |

## Durum Kontrolü

```bash
# Hesap düzeyinde durum (plan, makineler)
rdc subscription status

# Belirli bir makinenin aktivasyon ayrıntılarını göster

rdc subscription activation-status -m hostinger
```

Hesap sunucusundan abonelik ayrıntılarını gösterir. Makineye özel aktivasyon ayrıntıları için `rdc subscription activation-status -m` kullanın.

## Lisansı Zorla Yenileme

```bash
rdc subscription refresh -m <machine>
```

Belirtilen makineye lisansı zorla yeniden verir ve iletir. Bu normalde gerekli değildir — lisanslar normal CLI kullanımı sırasında her 50 dakikada otomatik olarak yenilenir.

## Nasıl Çalışır

1. **Giriş**, iş istasyonunuza bir API belirteci kaydeder
2. **Herhangi bir makine komutu**, SSH aracılığıyla otomatik lisans kontrolünü tetikler
3. Uzak lisans eksikse veya 50 dakikadan eskiyse, CLI:
   - SSH aracılığıyla uzak makinenin donanım kimliğini okur
   - Yeni bir lisans vermek için hesap API'sini çağırır
   - Hem makine lisansını hem de abonelik blobunu SSH aracılığıyla uzak makineye iletir
4. 50 dakikalık bellek içi önbellek, aynı oturum içinde gereksiz SSH gidiş-dönüşlerini önler

Her makine aktivasyonu aboneliğinizdeki bir slotu kullanır. Bir slotu serbest bırakmak için hesap portalından bir makineyi devre dışı bırakın.

## Ek Süre ve Düşürme

Bir lisansın süresi dolduğunda ve 3 günlük ek süre içinde yenilenemediğinde, makinenin kaynak sınırları Community planı varsayılanlarına düşürülür. Lisans yenilendiğinde (bağlantıyı geri yükleyip herhangi bir `rdc` komutu çalıştırarak), orijinal plan sınırları hemen geri yüklenir.

## Plan Sınırları

### Yüzen Lisans Sınırları

| Plan | Yüzen lisanslar |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### Kaynak Sınırları

| Kaynak | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|

### Özellik Kullanılabilirliği

| Özellik | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| İzin grupları | - | Evet | Evet | Evet |
| Kuyruk önceliği | - | - | Evet | Evet |
| Gelişmiş analizler | - | - | Evet | Evet |
| Öncelikli destek | - | Evet | Evet | Evet |
| Denetim günlüğü | - | Evet | Evet | Evet |
| Gelişmiş kuyruk | - | - | Evet | Evet |
| Özel markalama | - | Evet | Evet | Evet |
| Adanmış hesap | - | - | - | Evet |
