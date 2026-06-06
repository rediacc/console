---
title: Mimari
description: >-
  Rediacc nasıl çalışır: iki araçlı mimari, adaptör algılama, güvenlik modeli ve
  yapılandırma yapısı.
category: Concepts
order: 0
language: tr
sourceHash: "6763cd925791d474"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Mimari

Özetle: iş istasyonunuzda rdc, sunucularınızda renet, SSH üzerinden iletişim. Rediacc'ın tüm mimarisi bu ayrımı temel alır. Bu sayfa, iki aracın sorumlulukları nasıl bölüştüğünü, adaptör algılamasının durumu nasıl yönlendirdiğini, güvenlik modelinin nasıl çalıştığını ve yapılandırmanın nasıl yapılandırıldığını açıklar.

## Tam Yığın Genel Bakışı

Trafik internetten ters proxy üzerinden, her biri şifreli depolama ile desteklenen izole Docker daemon'larına akar:

![Tam Yığın Mimarisi](/img/arch-full-stack.svg)

Her depo kendi Docker daemon'una, geri döngü IP alt ağına (/26 = 64 IP) ve LUKS ile şifrelenmiş BTRFS birimine sahip olur. Yönlendirme sunucusu tüm daemon'lar arasında çalışan konteynerleri keşfeder ve yönlendirme yapılandırmasını Traefik'e gönderir.

## İki Araçlı Mimari

Rediacc, SSH üzerinden birlikte çalışan iki ikili dosyadan yararlanır:

![İki Araçlı Mimari](/img/arch-two-tool.svg)

- **rdc** iş istasyonunuzda (macOS, Linux veya Windows) çalışır. Yerel yapılandırmanızı okur, uzak makinelere SSH üzerinden bağlanır ve renet komutlarını çalıştırır.
- **renet** uzak sunucuda root yetkileriyle çalışır. LUKS ile şifrelenmiş disk imajlarını, izole Docker daemon'larını, hizmet orkestrasyonunu ve ters proxy yapılandırmasını yönetir.

Yerel olarak yazdığınız her komut, uzak makinede renet'i çalıştıran bir SSH çağrısına çevrilir. Sunuculara el ile SSH bağlantısı yapmak gerekmez.

İşletmen odaklı bir pratik kural için [rdc vs renet](/en/docs/rdc-vs-renet) sayfasına bakın. Ayrıca sınama için yerel bir VM kümesi çalıştırmak üzere `rdc ops` kullanabilirsiniz; bkz. [Deneysel VM'ler](/en/docs/experimental-vms).

## Yapılandırma

Tüm CLI durumu `~/.config/rediacc/` altındaki düz JSON yapılandırma dosyalarında saklanır.

### Yerel Adaptör (Varsayılan)

Kendi sunucunuzda barındırma için varsayılandır. Tüm durum bilgisi iş istasyonunuzdaki bir yapılandırma dosyasında saklanır (örneğin `~/.config/rediacc/rediacc.json`).

- Makinelere doğrudan SSH bağlantısı
- Harici hizmet gerekmez
- Tek kullanıcı, tek iş istasyonu
- Varsayılan yapılandırma ilk CLI kullanımında otomatik oluşturulur. Adlandırılmış yapılandırmalar `rdc config init --name <name>` ile oluşturulur

### Bulut Adaptörü (Deneysel)

Bir yapılandırma `apiUrl` ve `token` alanları içerdiğinde otomatik olarak etkinleşir. Durum yönetimi ve ekip işbirliği için Rediacc API'sini kullanır.

- Durum bulut API'sinde saklanır
- Rol tabanlı erişimle çok kullanıcılı ekipler
- Görsel yönetim için web konsolu
- `rdc auth login` ile kurulur

> **Not:** Bulut adaptörü komutları deneyseldir. `REDIACC_EXPERIMENTAL=1` ayarlayarak etkinleştirin.

Her iki adaptör de aynı CLI komutlarını kullanır. Adaptör yalnızca durumun nerede saklandığını ve kimlik doğrulamanın nasıl çalıştığını etkiler.

## rediacc Kullanıcısı

`rdc config machine setup` komutunu çalıştırdığınızda, renet uzak sunucuda `rediacc` adında bir sistem kullanıcısı oluşturur:

- **UID**: 7111
- **Kabuk**: `/sbin/nologin` (SSH üzerinden oturum açılamaz)
- **Amaç**: Depo dosyalarının sahibidir ve Rediaccfile işlevlerini çalıştırır

`rediacc` kullanıcısına doğrudan SSH üzerinden erişilemez. Bunun yerine rdc, yapılandırdığınız SSH kullanıcısı (örneğin `deploy`) olarak bağlanır ve renet depo işlemlerini `sudo -u rediacc /bin/sh -c '...'` aracılığıyla yürütür. Bu şu anlama gelir:

1. SSH kullanıcınızın `sudo` yetkisine sahip olması gerekir
2. Tüm depo verileri SSH kullanıcınız değil, `rediacc` kullanıcısına aittir
3. Rediaccfile işlevleri (`up()`, `down()`) `rediacc` olarak çalışır

Bu ayrım, depo verilerinin hangi SSH kullanıcısı tarafından yönetilirse yönetilsin tutarlı sahipliğe sahip olmasını sağlar.

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

Rediaccfile işlevleri otomatik olarak `DOCKER_HOST` değerini doğru sokete ayarlar.

Bir yapay zeka ajanı `rdc term connect -r <repo>` aracılığıyla bir depoya girdiğinde, aynı izolasyon geçerli olur: oturum, ayrıcalıksız `rediacc` kullanıcısı (UID 7111) olarak, ayrı bir bağlama ad alanında, `DOCKER_HOST` yalnızca o deponun daemon soketine kapsanmış şekilde çalışır. Önce-fork iş akışı bu çalışma zamanı izolasyonunu CoW klon ilkelleştirilmesiyle birleştirir: ajan, asla ana (üretim) depolar üzerinde değil, görev başına bir fork üzerinde işlem yapar. Tam sandbox modeli, geçersiz kılma anlamı ve harici hizmet kimlik bilgileri için geliştirici sorumluluğu sınırı için [AI Ajan Güvenliği ve Koruma](/en/docs/ai-agents-safety) sayfasına bakın.

### Daemon Yol Düzeni

Docker verileri ve yapılandırması deponun bağlama noktasının içinde saklanır; bu sayede her daemon ana bilgisayardan ve diğer depolardan tamamen izole kalır.

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

Bu birleşik düzen, daemon yolları ana bilgisayar dosya sistemi ile şifreli birim arasında bölündüğünde oluşan salt okunur ve okuma yazma bağlama çatışmalarını ortadan kaldırır. Hem depo başına hem de bağımsız daemon'lar aynı dizin yapısını izler; bu nedenle araçlar ve tanılama her iki durumda da aynı şekilde çalışır.

## LUKS Şifreleme

Depolar, sunucunun veri deposunda (varsayılan: `/mnt/rediacc`) saklanan LUKS ile şifrelenmiş disk imajlarıdır. Her depo:

1. Rastgele oluşturulmuş bir şifreleme parolasına ("kimlik bilgisi") sahiptir
2. Bir dosya olarak saklanır: `{datastore}/repos/{guid}.img`
3. Erişildiğinde `cryptsetup` ile bağlanır

Kimlik bilgisi yapılandırma dosyanızda saklanır ancak sunucuda **hiçbir zaman** saklanmaz. Kimlik bilgisi olmadan depo verilerine erişilemez. Otomatik başlatma etkinleştirildiğinde, önyüklemede otomatik bağlama için sunucuda ikincil bir LUKS anahtar dosyası saklanır.

## Yapılandırma Yapısı

Her yapılandırma `~/.config/rediacc/` içinde saklanan düz bir JSON dosyasıdır. Varsayılan yapılandırma `rediacc.json`'dır; adlandırılmış yapılandırmalar ad'ı dosya adı olarak kullanır (örneğin `production.json`). Alanlar amaç açısından gruplandırılır: `resources` dağıtımları barındırır, `credentials` sırları barındırır, `account` bulut varsayılanlarını barındırır, `infra` TLS/DNS'i barındırır ve `encryption` alan başına şifreleme durumunu barındırır. Üst düzey `schemaVersion: 2` ayırıcısı ileri uyumluluğu garanti eder.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
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
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Ana kutular:**

| Kutu | İçerik |
|---|---|
| `schemaVersion` | Ayırıcı (şu anda `2`). Yükleyiciler bilinmeyen sürümleri reddeder. |
| `id` / `version` | Değişmez UUID + monotonik sayaç; uzak yapılandırma deposunda iyimser kilitleme için kullanılır. |
| `defaults.*` | Hassas olmayan çalışma zamanı varsayılanları (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Satır içi SSH anahtar çifti + `knownHosts`. Eski `ssh.privateKeyPath` yerini alır (dosya yolu indirektion yok; içerik yükleme zamanında çözümlenir ve satır içinde saklanır). |
| `credentials.cfDnsApiToken` | Cloudflare DNS-01 ACME jetonu. |
| `credentials.masterPasswordVerifier` | Yalnızca `encryption.mode === "master-password"` olduğunda mevcuttur. |
| `resources.machines.*` | Makine başına SSH bağlantı detayları. |
| `resources.storages.*` | rclone uyumlu site dışı yedekleme kimlik bilgileri. |
| `resources.repositories.*` | Depo başına GUID + LUKS kimlik bilgisi + sandbox izole ajan erişimi için SSH anahtarı. |
| `infra.acmeCertCache.*` | Cached Traefik acme.json, gzip+base64, alan adı ile anahtarlanmıştır. |
| `encryption.mode` | `"plaintext"` (varsayılan) veya `"master-password"`. |
| `encryption.encryptedFields` | Şifreli olduğunda, işaretçi başına AES-GCM blob haritası (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Oturum başına bir kilit açma istemi alanlar okunurken şifresini çözer. |
| `remote` | Yapılandırma şifreli yapılandırma deposu ile senkronize edildiğinde yalnızca mevcuttur; bkz. [Şifreli yapılandırma deposu](/en/docs/config-storage). |

**CLI ile güvenli bir şekilde düzenleyin, vim kullanmayın:**

```bash
# İşaretçi adresli tek alan düzenlemeleri (hassas yollar için bilgi kapısı)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Redakte edilmiş JSONC projeksiyonlu tam düzenleyici (yalnızca insanlar)
rdc config edit

# Salt okunur JSONC dökümü, komut dosyaları ve ajanlar için güvenli
rdc config edit --dump

# Denetim günlüğünde her mutasyon + reddetme + açıklama kontrol edin
rdc config audit log --since 24h
rdc config audit verify
```

> Bu dosya hassas veriler (SSH özel anahtarları, LUKS kimlik bilgileri, Cloudflare jetonları) içerir. `0600` izinleriyle (yalnızca sahip okuma/yazma) saklanır. Paylaşmayın veya sürüm denetimine eklemeyin. Herhangi bir `rdc` komutu onu okuduğunda, hassas alanlar varsayılan olarak [redakte edilir](/en/docs/ai-agents-safety): düz metin yalnızca etkileşimli insan TTY'de `--reveal` ile görünür.

### Envelope v2 ve sunucu tarafında zorlama

Yapılandırma [şifreli yapılandırma deposu](/en/docs/config-storage) ile senkronize edildiğinde, CLI her hassas alanı işaretçi başına HMAC taahhüdüyle sarar ve bu taahhütleri düz metin zarf içinde taşır. Sunucu yalnızca onaltılık özetleri görür: asla değerleri değil; ancak yine de her yazma işleminde bilgi kapılarını zorlayabilir:

- **Ön koşul kontrolü**: `PUT /configs/<id>` üzerinde istemci, bildiğini iddia ettiği yollar için özetleri gönderir. Sunucu bunları saklanan zarfın taahhütlerine karşı karşılaştırır. Uyuşmazlık → `409 precondition_failed` ile `mismatchedPaths`. Sıfır bilgi: sunucu asla düz metin görmez.
- **İndir karşıtı**: yeni zarfın önceki zarfın taahhüt ettiği her hassas yolu taahhüt etmesi gerekir. Bir ajan bir yolu taahhütlerden bırakarak gelecekteki bir ön koşulu atlamak için yapamaz.
- **Zarif sürüm sabitleme**: sunucu `envelopeVersion: 2` olmayan zarfları `400 unsupported_envelope_version` ile reddeder. Çift kabul penceresi yok.
- **Alan başına dinlenme durumunda şifreleme** (CLI tarafı): `encryption.mode === "master-password"` olduğunda, her sır ana şifreyle anahtarlanmış bireysel bir AES-GCM blob olur. Okumalar, komut gerçekten bir sırra dokunana kadar istemi tetiklemez (bu nedenle `rdc machine list` istem içermez).

Taahhüt anahtarı (FCK) istemci tarafında CEK'den `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` ile yapılandırma başına bir tuzla türetilir. `fckSalt` döndürümü tüm önceki taahhütleri geçersiz kılar ve tam yeniden hesaplamaya zorlar: CEK döndürülürken kullanışlıdır.
