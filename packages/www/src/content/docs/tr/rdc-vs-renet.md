---
title: rdc vs renet
description: 'rdc ne zaman, renet ne zaman kullanılır.'
category: Concepts
order: 1
language: tr
sourceHash: 0396eec8815a0b4e
---

# rdc vs renet

Rediacc'ın iki ikili dosyası vardır. Her birinin ne zaman kullanılacağı aşağıda açıklanmıştır.

| | rdc | renet |
|---|-----|-------|
| **Çalıştığı yer** | İş istasyonunuz | Uzak sunucu |
| **Bağlantı şekli** | SSH | Root yetkileriyle yerel olarak çalışır |
| **Kullanan** | Herkes | Yalnızca ileri düzey hata ayıklama |
| **Kurulum** | Siz kurarsınız | `rdc` otomatik olarak kurar |

> Günlük işler için `rdc` kullanın. `renet`'e doğrudan ihtiyaç duymanız nadirdir.

## Birlikte Nasıl Çalışırlar

`rdc`, sunucunuza SSH üzerinden bağlanır ve sizin yerinize `renet` komutlarını çalıştırır. İş istasyonunuzda tek bir komut yazarsınız ve `rdc` gerisini halleder:

1. Yerel yapılandırmanızı okur (`~/.rediacc/config.json`)
2. Sunucuya SSH üzerinden bağlanır
3. Gerekirse `renet` ikili dosyasını günceller
4. Sunucuda eşleşen `renet` işlemini çalıştırır
5. Sonucu terminalinize döndürür

## Normal İşler İçin `rdc` Kullanın

Tüm yaygın görevler iş istasyonunuzdaki `rdc` üzerinden gerçekleştirilir:

```bash
# Yeni bir sunucu kur
rdc context setup-machine server-1

# Depo oluştur ve başlat
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Depoyu durdur
rdc repo down my-app -m server-1

# Makine sağlığını kontrol et
rdc machine health server-1
```

Tam bir yol haritası için [Hızlı Başlangıç](/tr/docs/quick-start) sayfasına bakın.

## Sunucu Tarafı Hata Ayıklama İçin `renet` Kullanın

`renet`'e doğrudan yalnızca sunucuya SSH ile bağlandığınızda ihtiyaç duyarsınız:

- `rdc` bağlanamadığında acil durum hata ayıklama
- `rdc` üzerinden erişilemeyen sistem iç bilgilerini kontrol etme
- Düşük seviye kurtarma işlemleri

Tüm `renet` komutları root yetkisi (`sudo`) gerektirir. `renet` komutlarının tam listesi için [Sunucu Referansı](/tr/docs/server-reference) sayfasına bakın.

## Deneysel: `rdc ops` (Yerel VM'ler)

`rdc ops`, iş istasyonunuzdaki yerel VM kümelerini yönetmek için `renet ops`'u sarar:

```bash
rdc ops setup       # Ön koşulları kur (KVM veya QEMU)
rdc ops up --basic  # Minimal küme başlat
rdc ops status      # VM durumunu kontrol et
rdc ops ssh 1       # Bridge VM'ye SSH ile bağlan
rdc ops down        # Kümeyi yok et
```

Bu komutlar `renet`'i yerel olarak çalıştırır (SSH üzerinden değil). Tam belgeler için [Deneysel VM'ler](/tr/docs/experimental-vms) sayfasına bakın.

## Rediaccfile Notu

Bir `Rediaccfile` içinde `renet compose -- ...` görebilirsiniz. Bu normaldir -- Rediaccfile fonksiyonları `renet`'in mevcut olduğu sunucuda çalışır.

İş istasyonunuzdan iş yüklerini `rdc repo up` ve `rdc repo down` ile başlatın ve durdurun.
