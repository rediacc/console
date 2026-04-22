---
title: Mimari
description: >-
  Rediacc nasıl çalışır: iki araçlı mimari, adaptör algılama, güvenlik modeli ve
  yapılandırma yapısı.
category: Concepts
order: 0
language: tr
sourceHash: "b41d8631ce30c981"
sourceCommit: 5c97ef070ea0c474b03651ceea03433b3f48abcd
---

# Mimari

Bu sayfa, Rediacc'ın altyapısını açıklar: iki araçlı mimari, adaptör algılama, güvenlik modeli ve yapılandırma yapısı.

## Tam Yığın Genel Bakış

Trafik internetten ters proxy aracılığıyla, her biri şifreli depolama ile desteklenen izole Docker daemon'larına akar:

![Tam Yığın Mimarisi](/img/arch-full-stack.svg)

Her depo kendi Docker daemon'una, geri döngü IP alt ağına (/26 = 64 IP) ve LUKS ile şifrelenmiş BTRFS birimine sahip olur. Rota sunucusu tüm daemon'lardaki çalışan konteynerleri keşfeder ve yönlendirme yapılandırmasını Traefik'e aktarır.

## İki Araçlı Mimari

Rediacc, SSH üzerinden birlikte çalışan iki ikili dosya kullanır:

![İki Araçlı Mimari](/img/arch-two-tool.svg)

- **rdc** iş istasyonunuzda (macOS, Linux veya Windows) çalışır. Yerel yapılandırmanızı okur, uzak makinelere SSH üzerinden bağlanır ve renet komutlarını çalıştırır.
- **renet** uzak sunucuda root yetkileriyle çalışır. LUKS ile şifrelenmiş disk imajlarını, izole Docker daemon'larını, servis orkestrasyonunu ve ters proxy yapılandırmasını yönetir.

Yerel olarak yazdığınız her komut, uzak makinede renet'i çalıştıran bir SSH çağrısına dönüştürülür. Sunuculara manuel olarak SSH bağlantısı yapmanız gerekmez.

Operatör odaklı bir genel kural için [rdc vs renet](/en/docs/rdc-vs-renet) sayfasına bakın. Ayrıca test için yerel VM kümesi çalıştırmak amacıyla `rdc ops` kullanabilirsiniz, bkz. [Deneysel VM'ler](/en/docs/experimental-vms).

## Yapılandırma

Tüm CLI durumu `~/.config/rediacc/` altındaki düz JSON yapılandırma dosyalarında saklanır.

### Yerel Adaptör (Varsayılan)

Kendi sunucunuzda barındırma için varsayılandır. Tüm durum bilgisi iş istasyonunuzdaki bir yapılandırma dosyasında saklanır (ör. `~/.config/rediacc/rediacc.json`).

- Makinelere doğrudan SSH bağlantısı
- Harici servis gerekmez
- Tek kullanıcı, tek iş istasyonu
- Varsayılan yapılandırma ilk CLI kullanımında otomatik oluşturulur. Adlandırılmış yapılandırmalar `rdc config init --name <name>` ile oluşturulur

### Bulut Adaptörü (Deneysel)

Bir yapılandırma `apiUrl` ve `token` alanları içerdiğinde otomatik olarak etkinleşir. Durum yönetimi ve ekip iş birliği için Rediacc API'sini kullanır.

- Durum bilgisi bulut API'sinde saklanır
- Rol tabanlı erişimle çok kullanıcılı ekipler
- Görsel yönetim için web konsolu
- `rdc auth login` ile kurulur

> **Not:** Bulut adaptörü komutları deneyseldir. `REDIACC_EXPERIMENTAL=1` ayarlayarak etkinleştirin.

Her iki adaptör de aynı CLI komutlarını kullanır. Adaptör yalnızca durumun nerede saklandığını ve kimlik doğrulamanın nasıl çalıştığını etkiler.

## rediacc Kullanıcısı

`rdc config machine setup` komutunu çalıştırdığınızda, renet uzak sunucuda `rediacc` adında bir sistem kullanıcısı oluşturur:

- **UID**: 7111
- **Kabuk**: `/sbin/nologin` (SSH ile giriş yapılamaz)
- **Amacı**: Depo dosyalarının sahibidir ve Rediaccfile fonksiyonlarını çalıştırır

`rediacc` kullanıcısına doğrudan SSH ile erişilemez. Bunun yerine rdc, yapılandırdığınız SSH kullanıcısı (ör. `deploy`) olarak bağlanır ve renet depo işlemlerini `sudo -u rediacc /bin/sh -c '...'` aracılığıyla çalıştırır. Bu şu anlama gelir:

1. SSH kullanıcınızın `sudo` yetkisine sahip olması gerekir
2. Tüm depo verileri SSH kullanıcınız değil, `rediacc` kullanıcısına aittir
3. Rediaccfile fonksiyonları (`up()`, `down()`) `rediacc` olarak çalışır

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

### Daemon Yol Düzeni

Docker verileri ve yapılandırması, deponun bağlama noktasının içinde saklanır; bu sayede her daemon, ana bilgisayardan ve diğer depolardan tamamen izole kalır.

**Depo başına düzen:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker veri kökü
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker yapılandırması
```

**Bağımsız düzen** (depo bağlama noktasına bağlı olmayan daemon'lar):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Paylaşılan çalışma zamanı yolu** (değişmez):
```
/run/rediacc/docker-{N}.sock
```

Bu birleşik düzen, daemon yolları ana bilgisayar dosya sistemi ile şifreli birim arasında bölündüğünde oluşan salt okunur ve okuma-yazma bağlama çakışmalarını ortadan kaldırır. Hem depo başına hem de bağımsız daemon'lar aynı dizin yapısını izler; bu nedenle araçlar ve tanılamalar her iki durumda da aynı şekilde çalışır.

## LUKS Şifreleme

Depolar, sunucunun veri deposunda (varsayılan: `/mnt/rediacc`) saklanan LUKS ile şifrelenmiş disk imajlarıdır. Her depo:

1. Rastgele oluşturulmuş bir şifreleme parolasına ("kimlik bilgisi") sahiptir
2. Bir dosya olarak saklanır: `{datastore}/repos/{guid}.img`
3. Erişildiğinde `cryptsetup` ile bağlanır

Kimlik bilgisi yapılandırma dosyanızda saklanır ancak **asla** sunucuda saklanmaz. Kimlik bilgisi olmadan depo verileri okunamaz. Otomatik başlatma etkinleştirildiğinde, açılışta otomatik bağlama için sunucuda ikincil bir LUKS anahtar dosyası saklanır.

## Yapılandırma Yapısı

Her yapılandırma `~/.config/rediacc/` dizininde saklanan düz bir JSON dosyasıdır. Varsayılan yapılandırma `rediacc.json`'dır; adlandırılmış yapılandırmalar dosya adı olarak adı kullanır (ör. `production.json`). Açıklamalı bir örnek:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 1,
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
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Temel alanlar:**

| Alan | Açıklama |
|------|----------|
| `id` | Bu yapılandırma dosyası için benzersiz tanımlayıcı |
| `version` | Yapılandırma dosyası şema sürümü |
| `ssh.privateKeyPath` | Tüm makine bağlantıları için kullanılan SSH özel anahtarının yolu |
| `machines.<name>.user` | Makineye bağlanmak için SSH kullanıcı adı |
| `machines.<name>.knownHosts` | `ssh-keyscan`'den alınan SSH host anahtarları |
| `repositories.<name>.repositoryGuid` | Şifrelenmiş disk imajını tanımlayan UUID |
| `repositories.<name>.credential` | LUKS şifreleme parolası (**sunucuda saklanmaz**) |
| `repositories.<name>.networkId` | IP alt ağını belirleyen ağ kimliği (2816 + n*64), otomatik atanır |
| `nextNetworkId` | Ağ kimliklerini atamak için genel sayaç |
| `universalUser` | Varsayılan sistem kullanıcısını (`rediacc`) geçersiz kılar |

> Bu dosya hassas veriler (SSH anahtar yolları, LUKS kimlik bilgileri) içerir. `0600` izinleriyle (yalnızca sahip okuma/yazma) saklanır. Paylaşmayın veya sürüm kontrolüne eklemeyin.
