---
title: Mimari
description: >-
  Rediacc nasıl çalışır: iki araçlı mimari, çalışma modları, güvenlik modeli ve
  yapılandırma yapısı.
category: Concepts
order: 0
language: tr
sourceHash: 58ba0da9645bb9dd
---

# Mimari

Hangi aracı kullanacağınızdan emin değilseniz [rdc vs renet](/tr/docs/rdc-vs-renet) sayfasına bakın.

Bu sayfa, Rediacc'ın altyapısını açıklar: iki araçlı mimari, çalışma modları, güvenlik modeli ve yapılandırma yapısı.

## Full Stack Overview

Traffic flows from the internet through a reverse proxy, into isolated Docker daemons, each backed by encrypted storage:

![Full Stack Architecture](/img/arch-full-stack.svg)

Each repository gets its own Docker daemon, loopback IP subnet (/26 = 64 IPs), and LUKS-encrypted BTRFS volume. The route server discovers running containers across all daemons and feeds routing configuration to Traefik.

## İki Araçlı Mimari

Rediacc, SSH üzerinden birlikte çalışan iki ikili dosya kullanır:

![İki Araçlı Mimari](/img/arch-two-tool.svg)

- **rdc** iş istasyonunuzda (macOS, Linux veya Windows) çalışır. Yerel yapılandırmanızı okur, uzak makinelere SSH üzerinden bağlanır ve renet komutlarını çalıştırır.
- **renet** uzak sunucuda root yetkileriyle çalışır. LUKS ile şifrelenmiş disk imajlarını, izole Docker daemon'larını, servis orkestrasyonunu ve ters proxy yapılandırmasını yönetir.

Yerel olarak yazdığınız her komut, uzak makinede renet'i çalıştıran bir SSH çağrısına dönüştürülür. Sunuculara manuel olarak SSH bağlantısı yapmanız gerekmez.

## Çalışma Modları

Rediacc, durumun nerede saklandığını ve komutların nasıl çalıştırıldığını belirleyen üç modu destekler.

![Çalışma Modları](/img/arch-operating-modes.svg)

### Yerel Mod

Kendi sunucunuzda barındırma için varsayılan moddur. Tüm durum bilgisi iş istasyonunuzdaki `~/.rediacc/config.json` dosyasında saklanır.

- Makinelere doğrudan SSH bağlantısı
- Harici servis gerekmez
- Tek kullanıcı, tek iş istasyonu
- Bağlam `rdc context create-local` ile oluşturulur

### Bulut Modu (Deneysel)

Durum yönetimi ve ekip iş birliği için Rediacc API'sini kullanır.

- Durum bilgisi bulut API'sinde saklanır
- Rol tabanlı erişimle çok kullanıcılı ekipler
- Görsel yönetim için web konsolu
- Bağlam `rdc context create` ile oluşturulur

> **Not:** Bulut modu komutları deneyseldir. `rdc --experimental <komut>` ile veya `REDIACC_EXPERIMENTAL=1` ortam değişkenini ayarlayarak etkinleştirin.

### S3 Modu

Şifrelenmiş durum bilgisini S3 uyumlu bir kovada (bucket) saklar. Yerel modun kendi sunucusunda barındırma özelliğini iş istasyonları arasında taşınabilirlikle birleştirir.

- Durum bilgisi S3/R2 kovasında `state.json` olarak saklanır
- Ana parola ile AES-256-GCM şifreleme
- Taşınabilir: kova kimlik bilgilerine sahip herhangi bir iş istasyonu altyapıyı yönetebilir
- Bağlam `rdc context create-s3` ile oluşturulur

Her üç mod da aynı CLI komutlarını kullanır. Mod yalnızca durumun nerede saklandığını ve kimlik doğrulamanın nasıl çalıştığını etkiler.

## rediacc Kullanıcısı

`rdc context setup-machine` komutunu çalıştırdığınızda, renet uzak sunucuda `rediacc` adında bir sistem kullanıcısı oluşturur:

- **UID**: 7111
- **Kabuk**: `/sbin/nologin` (SSH ile giriş yapılamaz)
- **Amacı**: Depo dosyalarının sahibidir ve Rediaccfile fonksiyonlarını çalıştırır

`rediacc` kullanıcısına doğrudan SSH ile erişilemez. Bunun yerine rdc, yapılandırdığınız SSH kullanıcısı (ör. `deploy`) olarak bağlanır ve renet depo işlemlerini `sudo -u rediacc /bin/sh -c '...'` aracılığıyla çalıştırır. Bu şu anlama gelir:

1. SSH kullanıcınızın `sudo` yetkisine sahip olması gerekir
2. Tüm depo verileri SSH kullanıcınız değil, `rediacc` kullanıcısına aittir
3. Rediaccfile fonksiyonları (`prep()`, `up()`, `down()`) `rediacc` olarak çalışır

Bu ayrım, depo verilerinin hangi SSH kullanıcısı yönetirse yönetsin tutarlı sahipliğe sahip olmasını sağlar.

## Docker İzolasyonu

Her depo kendi izole Docker daemon'una sahiptir. Bir depo bağlandığında, renet benzersiz bir soketle özel bir `dockerd` işlemi başlatır:

![Docker İzolasyonu](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Örneğin, ağ kimliği `2816` olan bir depo şunu kullanır:
```
/var/run/rediacc/docker-2816.sock
```

Bu şu anlama gelir:
- Farklı depolardan konteynerler birbirini göremez
- Her deponun kendi imaj önbelleği, ağları ve birimleri vardır
- Ana bilgisayarın Docker daemon'u (varsa) tamamen ayrıdır

Rediaccfile fonksiyonlarında `DOCKER_HOST` otomatik olarak doğru sokete ayarlanır.

## LUKS Şifreleme

Depolar, sunucunun veri deposunda (varsayılan: `/mnt/rediacc`) saklanan LUKS ile şifrelenmiş disk imajlarıdır. Her depo:

1. Rastgele oluşturulmuş bir şifreleme parolasına ("kimlik bilgisi") sahiptir
2. Bir dosya olarak saklanır: `{datastore}/repos/{guid}.img`
3. Erişildiğinde `cryptsetup` ile bağlanır

Kimlik bilgisi yerel `config.json` dosyanızda saklanır ancak **asla** sunucuda saklanmaz. Kimlik bilgisi olmadan depo verileri okunamaz. Otomatik başlatma etkinleştirildiğinde, açılışta otomatik bağlama için sunucuda ikincil bir LUKS anahtar dosyası saklanır.

## Yapılandırma Yapısı

Tüm yapılandırma `~/.rediacc/config.json` dosyasında saklanır. Açıklamalı bir örnek:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "storages": {
        "backblaze": {
          "provider": "b2",
          "vaultContent": { "...": "..." }
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Temel alanlar:**

| Alan | Açıklama |
|------|----------|
| `mode` | Yerel mod için `"local"`, S3 modu için `"s3"`, bulut modu için belirtilmez |
| `apiUrl` | Yerel mod için `"local://"`, bulut modu için API URL'si |
| `ssh.privateKeyPath` | Tüm makine bağlantıları için kullanılan SSH özel anahtarının yolu |
| `machines.<name>.user` | Makineye bağlanmak için SSH kullanıcı adı |
| `machines.<name>.knownHosts` | `ssh-keyscan`'den alınan SSH host anahtarları |
| `repositories.<name>.repositoryGuid` | Sunucudaki şifrelenmiş disk imajını tanımlayan UUID |
| `repositories.<name>.credential` | LUKS şifreleme parolası (**sunucuda saklanmaz**) |
| `repositories.<name>.networkId` | IP alt ağını belirleyen ağ kimliği (2816 + n*64), otomatik atanır |
| `nextNetworkId` | Ağ kimliklerini atamak için genel sayaç |
| `universalUser` | Varsayılan sistem kullanıcısını (`rediacc`) geçersiz kılar |

> Bu dosya hassas veriler (SSH anahtar yolları, LUKS kimlik bilgileri) içerir. `0600` izinleriyle (yalnızca sahip okuma/yazma) saklanır. Paylaşmayın veya sürüm kontrolüne eklemeyin.
