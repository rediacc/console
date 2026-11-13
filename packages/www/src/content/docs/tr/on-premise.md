---
title: "Yerinde (On-Premise) Kurulum"
description: "Hesap sunucusunu ve CLI dağıtımını kendi altyapınızda çalıştırma."
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: tr
sourceHash: "7216d032580dd4e1"
sourceCommit: "48fd8400c9f2754ab1653f0247fb0d77a1835c5b"
---

Rediacc tamamen kendi altyapınızda çalışabilir. Bağımsız Docker imajı hesap sunucusunu, web portalını, pazarlama sitesini ve CLI dağıtım uç noktasını içerir. Rediacc'ın barındırılan servislerine harici bağımlılık gerekmez.

## rdc ile kurulum

`rdc server install`, hesap sunucusunu CLI'ın SSH ile eriştiği bir makineye depo olarak kurar. Tek komut makine denetimini, renet kurulumunu, DNS'i, TLS'i, anahtar üretimini, lisanslamayı, başlatmayı ve sahip hesabını kapsar. Her değerin bir bayrağı vardır. Terminalde eksik değer sorulur; `--yes` ile hiçbir şey sorulmaz ve eksik değer reddedilir. Her adım kaydedilir, bu yüzden yeniden çalıştırma yapılmış olanı atlar.

Adımlar sırasıyla: `preflight` (parolasız sudo, mimari, 80 ve 443 numaralı portlar, disk alanı, saat sapması), `setup` (`rdc machine setup`, yalnızca renet yoksa), `dns`, `tls`, `repo`, `keys`, `licence`, `image`, `up` ve `owner`.

### Önce mevcut makineler

Kurulum, zaten var olan bir makineyi hedefler: veri merkezindeki bir sunucuyu ya da yerel ağdaki bir cihazı. Yapılandırılmış makine argüman olarak verilir. Henüz kayıtlı olmayan makine adresiyle eklenir:

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` ve `--name`, SSH portunu ve makinenin kaydedileceği adı belirler. Bulut VM'i önce `rdc machine provision` ile oluşturulur; kurulum hiçbir zaman VM oluşturmaz.

### DNS

Kurulum, sunucu alan adı ile yedekleme deposunun alan adı için A ve AAAA kayıtlarını yazdırır (`--store-domain`, varsayılan `<ad>-store.<alan adının geri kalanı>`) ve ikisi de makineye çözülene kadar bekler. Hiçbir kayıt bir bölgeye yazılmaz. `--no-dns-wait` kayıtları yazdırıp devam eder; yerel bir çözümleyicinin sunduğu LAN adları için uygundur.

### TLS

`--tls` üç yöntemden birini seçer:

| Yöntem | Gereken | Notlar |
|---|---|---|
| `letsencrypt` | 80 ve 443 numaralı portların internetten erişilebilir olması | HTTP-01 doğrulaması. `--cert-email` süre sonu bildirimlerini alır; varsayılan sahiptir. |
| `cloudflare` | `--cf-token` | Cloudflare API belirteci ile DNS-01 doğrulaması. |
| `byo` | `--tls-cert` ve `--tls-key` | Her iki alan adını kapsayan mevcut bir PEM sertifikası. `--tls-ca`, sağlık denetiminin güvendiği CA'yı belirtir. |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### İmaj

İmaj adımı varsayılan olarak `ghcr.io/rediacc/server:latest` imajını makinede çeker. `--image` başka bir referans seçer. `--image-file`, `docker save` ile yazılmış bir tar'ı gönderir; `--local-image` ise `--image`'ı yerel Docker'dan kaydedip gönderir. İkisi de makinenin bir kayıt defterine erişmesini gerektirmez.

### Lisanslama ve ücretsiz katman

`--licence auto` (varsayılan), oturum açmış hesabın yetki devri sertifikasını kullanır; yoksa ücretsiz katmanda başlar. `--licence free` her zaman ücretsiz katmanda başlar. Kurulum komutu var olmadan önce oturum açmış bir hesap, doğru kapsamı alması için `rdc subscription login` komutunu yeniden çalıştırmalıdır.

Hesap sunucusuna yolu olmayan bir makine için `--cert <file>`, başka yerden alınmış bir yetki devri sertifikasını kabul eder. Sertifika makinede üretilen anahtarı adlandırmalıdır; bu yüzden olağan sıra önce ücretsiz katmanda kurulum, ardından sertifikadır:

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence`, ücretsiz katmandaki bir sunucuyu oturum açmış hesabın ya da `--cert` ile verilen sertifikaya geçirir. Sunucunun neyi denetlediğini aşağıdaki lisanslama bölümünün 3. adımı anlatır.

### Kurtarma paketi

Tüm anahtarlar makinede üretilir ve yalnızca deponun `secrets.env` dosyasına yazılır. Terminalde kurulum, tek seferlik bir kurtarma paketi yazdırarak biter: yetki devredilen anahtar çifti, hesap yapılandırma sunucusu anahtarı ve nesne depolama kimlik bilgileri. Paket hiçbir zaman günlüğe yazılmaz ve `--output json` çıktısına girmez. Terminal yoksa yazdırılmaz ve kapanış satırı `rdc server backup` komutunu anar.

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` dosyayı 0600 kipiyle yazar; verilmezse paket stdout'a gider. Kurulumdaki `--bws-project <id>` anahtarları ayrıca bir Bitwarden Secrets Manager projesine kopyalar, `--rotate` ise farklı olan kayıtlı bir değerin yerini alır. `--bws-project` olmadan hiçbir anahtar makineden çıkmaz.

### Durum

```bash
rdc server status accounts.example.com
```

Durum, sunucunun sağlığını, katmanını, sertifikasını ve imajını gösterir. Cihazda alan adı için kurulum kaydı yoksa `--machine` ve `--repo` hedefi belirtir.

### Güncellemeler

| Bileşen | Komut |
|---|---|
| CLI | `rdc update` |
| Makinedeki renet | `rdc machine setup <machine>` |
| Sunucu imajı ve şablonu | `rdc server upgrade <domain>` |

`rdc server upgrade`, depoyu geri dönüş noktası olarak çatallar, yeni imajı yerleştirir, yerleşik şablon daha yeniyse onu yeniden uygular ve yeniden başlatır. Kurulum gibi `--image`, `--image-file` ve `--local-image` kabul eder; böylece hava boşluklu bir makine kaydedilmiş bir imaj tar'ından güncellenir.

## Docker İmajı

Bağımsız imajı çekin:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Varsayılan ayarlarla çalıştırın:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

İmaj şunları sunar:
- `/account/api/v1/` adresinde Account API
- `/account/` adresinde web portalı
- `/` adresinde pazarlama sitesi
- `/releases/` adresinde CLI artefaktları
- `/bin/` adresinde Renet ikili dosyaları

## CLI'ı Sunucunuzdan Kurma

CLI'ı doğrudan yerinde sunucunuzdan kurun. Kurulum betiği güncelleme kanalını otomatik algılar ve CLI'ı güncellemeler için sunucunuzu kontrol edecek şekilde yapılandırır.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Bu tek komut:
1. CLI ikili dosyasını sunucunuzun `/releases/` uç noktasından indirir
2. Güncelleme kanalını keşfetmek için `/account/api/v1/.well-known/server-info` adresini sorgular
3. Sunucu URL'nizi, güncelleme kanalınızı ve şifreleme anahtarlarınızı `account.*` alanları altında içeren varsayılan yapılandırmayı (`rediacc.json`) yazar
4. Gelecekteki güncellemeler için `rdc update` komutunu sunucunuzu kontrol edecek şekilde yapılandırır

`REDIACC_CHANNEL` değişkenine gerek yoktur. Kurulum betiği kanalı sunucunuzun yapılandırmasından otomatik olarak okur.

## Adlandırılmış Yapılandırmalarla CLI Ayarları

Birden fazla sunucuya (yerinde, üretim, edge) bağlanan kullanıcılar için adlandırılmış yapılandırmalar her ortamı izole tutar:

```bash
# Yerinde sunucunuz için bir yapılandırma oluşturun
rdc config init myserver --server https://account.example.com

# Bu yapılandırmayı kullanarak giriş yapın
rdc --config myserver subscription login

# --config ile tüm komutlar yerinde sunucuyu kullanır
rdc --config myserver machine status prod-1
```

Her adlandırılmış yapılandırma kendi hesap sunucusu URL'sini (`account.*` altında) ve kendi hesap API tokenini saklar; token, yapılandırmanın yanında `api-token-<name>.json` olarak tutulur. Yapılandırma değiştirmek tüm sunucu bağlamını değiştirir.

## İnternet Erişimi Olmayan Ortamlar

İnternet erişimi olmayan ortamlar için hem sunucu URL'sini hem de özel bir sürüm URL'sini ayarlayın:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

CLI, güncellemeler için genel sürümler CDN yerine `account.example.com/releases/cli/stable/manifest.json` adresini kontrol eder.

Sunucu tamamen çevrimdışıysa, paketlenmiş tarball'dan npm aracılığıyla CLI'ı kurun:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Ortam Değişkenleri Referansı

| Değişken | Kullanan | Amaç |
|---|---|---|
| `REDIACC_SERVER_URL` | Kurulum betiği | Hesap sunucusu URL'si. Kanalı ve şifreleme anahtarlarını otomatik keşfeder. |
| `REDIACC_RELEASES_URL` | Kurulum betiği, CLI güncelleyici | CLI ikili dosyaları için özel sürüm uç noktası. Varsayılan: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Kurulum betiği | Güncelleme kanalını geçersiz kılar. Ayarlanmamışsa sunucudan otomatik algılanır. |
| `REDIACC_ACCOUNT_SERVER` | CLI çalışma zamanı | Tüm CLI komutları için hesap sunucusu URL'sini geçersiz kılar. |
| `REDIACC_UPDATE_CHANNEL` | CLI çalışma zamanı | `rdc update` için güncelleme kanalını geçersiz kılar. |

## Sunucu Yapılandırması

Yerinde Docker imajı, barındırılan servisle aynı `ENVIRONMENT` değişkenini kullanır. Bunu Docker ortamınızda veya orkestrasyon yapılandırmanızda ayarlayın:

- `ENVIRONMENT=production` (varsayılan): standart kaynak limitleri; bu sunucuya bağlanan CLI'lar varsayılan olarak **stable** güncelleme kanalını kullanır. Değer adı `production`, eski bir dağıtım tanımlayıcısıdır. Hem `production` hem `edge` modları üretim kalitesindedir.
- `ENVIRONMENT=edge`: 2X Community limitleri; CLI'lar varsayılan olarak **edge** güncelleme kanalını kullanır

Her ortamın sağladıkları hakkında ayrıntılar için [Sürüm Kanalları](/tr/docs/release-channels) sayfasına bakın.

## Sunucunun CLI'a Söyledikleri

CLI sunucunuza bağlandığında, şunları keşfetmek için `/.well-known/server-info` adresini sorgular:

- **E2E şifreleme genel anahtarı**: sıfır bilgi yapılandırma depolama için
- **Minimum CLI sürümü**: güncel olmayan CLI'ların bağlanmasını engeller
- **Güncelleme kanalı**: CLI'a güncellemeler için hangi sürüm kanalını kullanacağını söyler
- **Ortam**: sunucunun çalıştırdığı dağıtım profili (standart limitler mi yoksa 2X limitli edge mi)

Bu otomatik yapılandırma, kullanıcıların yalnızca sunucu URL'sine ihtiyaç duyduğu anlamına gelir. Diğer her şey otomatik olarak keşfedilir.

## Hava Boşluklu Dağıtımlar için Lisanslama

Hava boşluklu ve kendi kendine barındırılan yerinde sunucular, yukarı akış ana anahtarı tarafından imzalanmış bir **yetkilendirme sertifikası** kullanarak lisansları yerel olarak düzenler. Sertifika, yerinde sunucuyu plan limitleriyle kısıtlar ve kurcalamaya karşı kanıt zinciri oluşturur. Kriptografik tasarım (zincir bütünlüğü, çatal algılama, denetim kanıtları) için [Lisans Zinciri ve Yetkilendirme](/tr/docs/license-chain) sayfasına bakın.

Bu bölüm operasyonel kurulumu kapsar: anahtar oluşturma, sertifika talep etme, otomatik yenileme yapılandırması ve çevrimdışı (hava boşluklu) yenileme akışı.

### Bir abonelik, bir yerinde kurulum

Bir aboneliğin **aynı anda en fazla bir etkin yetkilendirme sertifikası** olabilir. Her yerinde kurulum aylık ve makine başına limitleri kendi yerel düzenleme defterine karşı uygular; dolayısıyla birden fazla etkin sertifika, olası uzlaştırma olmaksızın fiili kotayı çarpar.

Ayrı ortamlara (üretim, hazırlama, DR, çok bölgeli) ihtiyaç duyuyorsanız, kurulum başına bir abonelik satın alın. Tek etkin uygulama bu sözleşmeyi kodlar: ikinci etkin sertifika oluşturma girişimi, mevcut sertifika kimliği ve yenileme (tercih edilen, zinciri korur) veya iptal-ve-oluşturma (zinciri sıfırlar) talimatlarıyla birlikte `409 DELEGATION_CERT_ALREADY_ACTIVE` döndürür.

### 1. Yerinde Ed25519 anahtar çifti oluşturma

Yerinde sunucu lisansları imzalamak için ayrı bir Ed25519 anahtar çifti kullanır. Yukarı akışın yetkilendirme sertifikası bu belirli genel anahtarı yetkilendirir.

```bash
# Yeni bir anahtar çifti oluşturun
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# base64'e dönüştürün (yerinde ortamın env var'larında beklediği format)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Özel anahtarı diğer sırlarınızın yanında saklayın (örneğin, Docker sırrı veya Kubernetes Secret). Asla yerinde kutunun dışına çıkmaz.

### 2. Yukarı akıştan yetkilendirme sertifikası talep etme

Yukarı akış hesap portalından sertifikayı üç yolla talep edebilirsiniz:

**Seçenek A: Müşteri self-servis (önerilen).** Yukarı akış portalına org sahibi veya yönetici olarak giriş yapın ve **/account/delegation-certs** sayfasına gidin. **Yeni Oluştur**'a tıklayın, yerinde genel anahtarı (base64 SPKI) yapıştırın, bir geçerlilik süresi seçin (veya plan başına varsayılanı kabul edin) ve sonuçta elde edilen `.json` dosyasını indirin.

**Seçenek B: Yönetici (müşteriler arası).** Rediacc desteği veya yukarı akış sistem yöneticisi aynı parametrelerle `POST /admin/delegation-certs` çağırabilir.

**Seçenek C: `rdc` CLI (planlanmış).** Gelecekteki bir CLI komutu portal akışını saracaktır.

Döndürülen `.json` şöyle görünür:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

Sertifikanın geçerliliği, geçerlilik politikası tarafından yönetilir (plan başına varsayılanlar ve tavanlar, abonelik başına geçersiz kılma, abonelik sonu + 3 günlük yetkisiz kullanım süresiyle sınırlandırılmış). Yanıt ayrıca hangi değerin seçildiğini görebilmeniz için `effectiveDays` ve `reason` içerir. Tam kurallar için [Lisans Zinciri - Geçerlilik Politikası](/tr/docs/license-chain) sayfasına bakın.

### 3. Sertifikayı yerinde sunucuya kurma

Sunucu, devretme sertifikasını veri biriminin üzerindeki tek bir dosyadan okur: `/data/delegation-cert.json` (`DELEGATION_CERT_PATH`). Sertifikayı başka hiçbir şey taşımaz: bunun için bir ortam değişkeni yoktur. `rdc server install` indirilen sertifikayı oraya bırakır, `rdc server licence` ise sonradan değiştirir:

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

Her iki komut da sertifikayı çalışan sunucuya sertifika gelen kutusu (`data/web/cert-inbox/new.json`) üzerinden iletir. Sunucu sertifikayı doğrular ve `applied.json` veya `rejected.json` ile yanıt verir; komut yeni sertifika kimliğini `rdc server status` ile doğrular (6. adımdaki `cert-status` verisinin aynısı). `rdc server upgrade` aynı gelen kutusunu kullanır. Yükseltmenin bir adımı, `secrets.env` içinde kalmış bir `DELEGATION_CERT_BASE64` değerini gelen kutusuna taşır; böylece gelen kutusundan önce kurulmuş bir makine sertifikasını korur.

Sunucu sertifikayı açılışta yükler ve lisansları imzaladığı anahtarla karşılaştırır: imzalama anahtarının parmak izi, sertifikanın `delegatedPublicKey` parmak izine eşit olmalıdır; çünkü sertifikanın yetkilendirmediği bir anahtarla imzalanan lisanslar hiçbir makinede doğrulanamaz. İmzalama anahtar çiftini ve sertifikanın `delegatedPublicKey` değerini uyumlu tutun.

Sunucunun açılışta reddettiği bir sertifika (geçersiz imza, yanlış anahtar, eksik `UPSTREAM_PUBLIC_KEY` veya bozuk dosya) sunucuyu durdurmaz. Sunucu ücretsiz katmanda başlar ve hatalı dosyayı orijinalin yanına `delegation-cert.rejected.json` olarak taşır. Geçerli bir sertifika yerine konana kadar depo lisans imzalama `503 DELEGATION_CERT_REFUSED` yanıtı verir ve `rdc server status` `cert REFUSED (reason)` gösterir. Onarmak için geçerli bir sertifikayla `rdc server licence` çalıştırın. Süresi dolmuş bir sertifika yine yüklenir: reddedilmek yerine yumuşak biçimde düşürülür.

### 4. Yukarı akış doğrulaması ve otomatik yenileme yapılandırması (isteğe bağlı ancak önerilir)

Yerinde sunucunuzun yukarı akışa giden HTTPS erişimi varsa, sertifikanın manuel müdahale olmaksızın son kullanma tarihinden önce yenilenmesi için otomatik yenileme ayarlayın:

```bash
# /onprem/cert-upload'ın yüklenen sertifikaları yukarı akış ana anahtarına karşı doğrulaması için gereklidir.
# UPSTREAM_API_KEY bu olmadan ayarlanırsa önyüklemede hızla başarısız olur.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# Otomatik yenileme döngüsü için gereklidir. Portal aracılığıyla oluşturun:
#   Org sahibi/yönetici -> /account/delegation-certs -> "Otomatik yenileme tokeni al"
# Bu, delegation:renew kapsamlı api tokeni edinmenin TEK yoludur.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# İsteğe bağlı ayar (varsayılanlar gösterilmiştir).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

Yerinde otomatik yenileme döngüsü önyüklemede bir kez ve ardından yapılandırılan aralıkta çalışır. **Uyarlanabilir bir eşik** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) kullanır; böylece 15 günlük COMMUNITY sertifikası 1. günde yenilemeyi tetiklemek yerine 5 gün kala yenilenir. 90 günlük BUSINESS sertifikası 14 gün kala yenilenir (env tarafından yapılandırılan tavan devreye girer).

Yenileme başarısız olursa, sertifika doğal son kullanma tarihine kadar kullanımda kalır. Başarısızlık 1 saat geri çekilir ve `${DELEGATION_CERT_PATH}.status.json` dosyasına kaydedilerek `GET /onprem/cert-status` aracılığıyla gösterilir.

### 5. Hava boşluklu yenileme (giden HTTPS yok)

Yerinde sunucunuz yukarı akışa ulaşamıyorsa, manuel transfer akışını kullanın:

1. **Yerinde yönetici portalından yenileme isteği indirin.** Yerinde sistem kökü olarak `GET /onprem/renewal-request` adresine gidin. Bu, yerel zincir başını, yetkilendirilmiş genel anahtarı ve yerinde özel anahtarınızdan alınan kurcalamaya karşı kanıt Ed25519 imzasını içeren bir JSON manifestosu döndürür.
2. **Manifestoyu yukarı akışa** USB, şifreli e-posta veya herhangi bir bant dışı kanal aracılığıyla aktarın. Manifesto küçüktür (birkaç KB) ve sır içermez.
3. **Manifestoyu yukarı akışta işleyin.** Org sahibi/yönetici **/account/delegation-certs** sayfasını açar, **Yenileme isteği yükle**'yi seçer ve manifesto dosyasını seçer. Yukarı akış, manifesto imzasını etkin sertifikanın `delegatedPublicKey`'ine karşı doğrular (yerinde özel anahtarın sahibinden geldiğini kanıtlar), tekrar oynatmayı kontrol eder (7 günden eski manifestolar reddedilir) ve ardından yeni bir sertifika düzenler.
4. **Yeni sertifikayı** yukarı akış portalından `.json` dosyası olarak indirin.
5. **Sertifikayı** yerinde sunucuya geri aktarın.
6. **Yerel yönetici portalı aracılığıyla yerinde sunucuya yükleyin** (`POST /onprem/cert-upload`). Yerinde sunucu, yeni sertifikayı `UPSTREAM_PUBLIC_KEY`'e karşı doğrular ve sertifikanın `genesisSequence`'ının yerel düzenleme defterindeki bir zincir girdisine hala bağlandığını doğrular (transit sırasında sıralı ilerleme desteklenir - zincir doğal olarak genişler).

Bu akış hiçbir zaman yerinde sunucudan ağ çıkışı gerektirmez.

#### Manifesto hata modları

| Kod | Neden | Düzeltme |
|---|---|---|
| `NO_ACTIVE_CERT` | Yukarı akışın bu abonelik için aktif sertifikası yok | Yenileme yerine oluşturma akışı ile yeni sertifika düzenleyin |
| `DELEGATED_KEY_MISMATCH` | Manifestonun `delegatedPublicKey`'i etkin sertifikadan farklı | Manifesto farklı bir yerinde kurulumdan tekrar oynatılmış olabilir |
| `MANIFEST_SIGNATURE_INVALID` | İmza yetkilendirilmiş genel anahtara karşı doğrulanamıyor | Manifesto transit sırasında kurcalandı veya farklı bir yerinde sunucuda oluşturuldu |
| `MANIFEST_EXPIRED` | Manifesto 7 günden daha eski | Yerinde sunucudan yeni yenileme isteği oluşturun |

#### Sertifika yükleme hata modları

`POST /onprem/cert-upload` başarılı olursa `{uploaded: true, bootstrap, certId}` döndürür. Reddedilen bir sertifika için `{error, code}` döner: `error` ayrıntıyı taşır, `code` ise aşağıdaki nedenlerden biridir. Uygulanan veya reddedilen her sertifika günlüğe yazılır ve kutunun sahibine e-postayla gönderilir.

`rdc server licence` sertifikayı SSH ile kutunun gelen kutusuna (`data/web/cert-inbox`) bırakır ve `applied.json` ya da `rejected.json` dosyasını geri okur. Ardından yeni sertifika kimliğini `cert-status` ile doğrular. Ret nedenleri aynıdır; ayrıca gelen kutusunun kendisinden gelen `not-a-regular-file` ve `too-large` da görülebilir.

| Kod | HTTP | Neden |
|---|---|---|
| `malformed` | 400 | Yüklenen dosya geçerli bir sertifika değil |
| `bad-signature` | 400 | Sertifika, yapılandırılmış `UPSTREAM_PUBLIC_KEY` ile imzalanmamış |
| `wrong-key` | 400 | Sertifika bu şirket içi kurulumdan farklı bir anahtar için düzenlenmiş |
| `expired` | 400 | Sertifikanın `validUntil` tarihi geçmiş |
| `not-newer` | 409 | Sertifika, yürürlükteki sertifikadan daha yeni değil |
| `other-subscription` | 409 | Sertifika başka bir aboneliğe ait |
| `chain-ahead` | 409 | Sertifikanın `genesisSequence` değeri yerel zincir başının önünde |
| `chain-fork` | 409 | Sertifikanın `genesisSequence` değerindeki zincir hash'i yerel deftere uymuyor |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY` yapılandırılmamış |
| `write-failed` | 500 | Sertifika diske yazılamadı |
| `adoption-failed` | 500 | Sunucu yazılan sertifikayı yükleyemedi |

### 6. Durum ve izleme

Yerinde yerel sertifika durumunu istediğiniz zaman sorgulayın:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Yüklenen sertifikanın `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` bilgilerini ve `autoRenew` bloğunu (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`) döndürür. Eski `lastSuccessAt` veya null olmayan `lastError` için uyarı vermek üzere bunu izleme yığınınıza bağlayın.

Yedekleme ve denetim için, yerinde yönetici `GET /onprem/cert-current` aracılığıyla şu anda yüklü olan imzalı sertifikayı da indirebilir (yükseltilmiş oturum gerektirir).

### Yetkilendirme sertifikası env var referansı

| Değişken | Zorunlu? | Amaç |
|---|---|---|
| `ON_PREMISE_MODE` | Evet | Yerinde rota alt kümesini etkinleştirmek için `true` olarak ayarlayın |
| `ON_PREMISE_PRIVATE_KEY` | Evet | Yetkilendirilmiş imzalama için Base64 PKCS8 Ed25519 özel anahtarı |
| `ON_PREMISE_PUBLIC_KEY` | Evet | Base64 SPKI Ed25519 genel anahtarı (sertifikanın `delegatedPublicKey`'iyle eşleşmeli) |
| `DELEGATION_CERT_PATH` | İsteğe bağlı | İmzalı sertifika JSON'una dosya sistemi yolu. Varsayılan: veri biriminde `/data/delegation-cert.json`. Sertifikayı elle değil, `rdc server licence` ile değiştirin. |
| `UPSTREAM_PUBLIC_KEY` | `UPSTREAM_API_KEY` ayarlanmışsa veya `/onprem/cert-upload`'ın çalışması için gerekli | Yukarı akış ana genel anahtarının Base64 SPKI'si. Eksikse önyüklemede hızla başarısız olur. |
| `UPSTREAM_URL` | Otomatik yenileme için | Yukarı akış hesap sunucusu temel URL'si, örn. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Otomatik yenileme için | `delegation:renew` kapsamlı api tokeni. Portal aracılığıyla oluşturun - bkz. Adım 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | İsteğe bağlı | Varsayılan 24. Sertifikanın yenilenmesi gerekip gerekmediğini ne sıklıkla kontrol edeceği. |
| `RENEW_THRESHOLD_DAYS` | İsteğe bağlı | Varsayılan 14. Uyarlanabilir 1/3 geçerlilik eşiği için tavan görevi görür. |

### Tehdit modeli özeti

Yetkilendirme sertifikası modeli şunlara karşı koruma sağlar:

- **Sahte lisanslar**: yerinde sunucu yalnızca plan limitleri dahilinde imzalayabilir; renet sertifikanın sınırları dışındaki her şeyi reddeder.
- **Dağıtımlar arası sertifika paylaşımı**: zincir ayrışması yenilemede tespit edilir (`CHAIN_FORK_DETECTED` döndürür).
- **Çoklu kurulum yoluyla kota aşımı**: yukarı akışta tek etkin (abonelik başına bir sertifika) ile uygulanır.
- **Zincir geri alımı**: renet abonelik başına görülen en yüksek sırayı saklar ve daha düşük sıralı herhangi bir blobu reddeder.
- **Ele geçirilmiş yukarı akış kimlik bilgileri**: başlangıç `delegation:renew` tokeni yalnızca özel portal uç noktası aracılığıyla oluşturulabilir ve yönetici onayı gerektirir. Token yalnızca yenileme izni verir - başka hiçbir kaynağı okuyamaz veya değiştiremez.
- **Manifestolara tekrar oynatma saldırıları**: 7 günden eski manifestolar reddedilir.

Şunlara karşı **koruma sağlamaz**:

- **Ele geçirilmiş yerinde özel anahtar**: sızdırılan özel anahtar, sertifikanın `validUntil` tarihine kadar bir saldırganın lisans imzalamasına olanak tanır. Azaltma: anahtar çiftini döndürün (eski sertifikayı iptal edin ve yeni anahtarla yeni sertifika oluşturun) ve eski anahtarla imzalanan tüm lisansları şüpheli olarak değerlendirin.
- **Ele geçirilmiş yukarı akış ana anahtarı**: bu güven köküdür. Rotasyon prosedürleri burada kapsam dışıdır.
