---
title: "rdc vs renet"
description: "rdc ne zaman, renet ne zaman kullanılır."
category: "Concepts"
order: 1
language: tr
sourceHash: "2ccc8590bc6f67c6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc vs renet

Rediacc iki ikili dosyası ile gelir. İki iş, iki yer. Hangisini ne zaman kullanacağınız aşağıda açıklanmıştır.

| | rdc | renet |
|---|-----|-------|
| **Çalıştığı yer** | İş istasyonunuz | Uzak sunucu |
| **Bağlantı şekli** | SSH | Root yetkileriyle yerel olarak çalışır |
| **Kullanan** | Herkes | Yalnızca ileri düzey hata ayıklama |
| **Kurulum** | Siz kurarsınız | `rdc` otomatik olarak kurar |

> Günlük işler için `rdc` kullanın. `renet`'e doğrudan ihtiyaç duymanız nadirdir.

## Birlikte Nasıl Çalışırlar

İş istasyonunuzda `rdc` çalıştırırsınız. Sunucunuza SSH bağlantısı açar ve eşleşen `renet` komutunu orada çalıştırır. Tek komut, tek yer:

1. Yerel yapılandırmanızı okur (`~/.config/rediacc/rediacc.json`)
2. Sunucuya SSH üzerinden bağlanır
3. Gerekirse `renet` ikili dosyasını günceller
4. Sunucuda eşleşen `renet` işlemini çalıştırır
5. Sonucu terminalinize döndürür

## Normal İşler İçin `rdc` Kullanın

Tüm yaygın görevler iş istasyonunuzdaki `rdc` üzerinden gerçekleştirilir:

```bash
# Yeni bir sunucu kur
rdc config machine setup --name server-1

# Depo oluştur ve başlat
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# Depoyu durdur
rdc repo down --name my-app -m server-1

# Makine sağlığını kontrol et
rdc machine health --name server-1
```

Tam bir yol haritası için [Hızlı Başlangıç](/tr/docs/quick-start) sayfasına bakın.

## Sunucu Tarafı Hata Ayıklama İçin `renet` Kullanın

`renet`'e doğrudan yalnızca sunucuya SSH ile bağlandığınızda ihtiyaç duyarsınız:

- `rdc` bağlanamadığında acil durum hata ayıklama
- `rdc` üzerinden erişilemeyen sistem iç bilgilerini kontrol etme
- Düşük seviye kurtarma işlemleri

Tüm `renet` komutları root yetkisi (`sudo`) gerektirir. `rdc` `renet` alt komutlarının tamamını sarmalamaz; ele alınmayan herhangi bir şey için SSH ile bağlanın ve doğrudan `renet` çağırın. Tüm `renet` komutlarının listesi için [Sunucu Referansı](/tr/docs/server-reference) sayfasına bakın.

## Deneysel: `rdc ops` (Yerel VM'ler)

`rdc ops`, iş istasyonunuzdaki yerel VM kümelerini yönetmek için `renet ops`'u sarar:

```bash
rdc ops setup              # Ön koşulları kur (KVM veya QEMU)
rdc ops up --basic         # Minimal küme başlat
rdc ops status             # VM durumunu kontrol et
rdc ops ssh --vm-id 1  # Bridge VM'ye SSH ile bağlan
rdc ops ssh --vm-id 1 -c hostname  # Bridge VM'de komut çalıştır
rdc ops down               # Kümeyi yok et
```

> Yerel adaptör gerektirir. Bulut adaptörüyle kullanılamaz.

Bu komutlar `renet`'i yerel olarak çalıştırır (SSH üzerinden değil). Tam belgeler için [Deneysel VM'ler](/tr/docs/experimental-vms) sayfasına bakın.

## Rediaccfile Notu

Bir `Rediaccfile` içinde `renet compose -- ...` göreceksiniz. Endişelenmeyin. Rediaccfile fonksiyonları sunucuda çalışır; `renet` zaten orada kurulu.

İş istasyonunuzdan iş yüklerini `rdc repo up` ve `rdc repo down` ile başlatın ve durdurun.
