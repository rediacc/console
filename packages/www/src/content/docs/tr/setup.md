---
title: "Makine Kurulumu"
description: "Yapılandırma oluşturma, makine ekleme, sunucuları hazırlama ve altyapı yapılandırması."
category: "Guides"
order: 3
language: tr
sourceHash: "b3c8c42db1b8d99b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Makine Kurulumu

İlk makinenizi çalışmaya hazır hale getirmek için dört adım gerekir: yapılandırma oluşturma, sunucuyu kaydetme, hazırlama ve isteğe bağlı olarak genel erişim için altyapı kurulumu.

## Adım 1: Yapılandırma Oluşturma

Bir **yapılandırma** (config), SSH kimlik bilgilerinizi, makine tanımlarınızı ve depo eşlemelerinizi saklayan adlandırılmış bir yapılandırma dosyasıdır. Bunu bir proje çalışma alanı olarak düşünebilirsiniz.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `--ssh-key <path>` | Evet | SSH özel anahtarınızın yolu. Tilde (`~`) otomatik olarak genişletilir. |
| `--renet-path <path>` | Hayır | Uzak makinelerdeki renet ikili dosyasının özel yolu. Varsayılan olarak standart kurulum konumunu kullanır. |

Bu komut `my-infra` adında bir yapılandırma oluşturur ve `~/.config/rediacc/my-infra.json` dosyasında saklar. Varsayılan yapılandırma (ad verilmediğinde) `~/.config/rediacc/rediacc.json` olarak saklanır.

> Birden fazla yapılandırmanız olabilir (ör. `production`, `staging`, `dev`). Herhangi bir komutta `--config` bayrağıyla bunlar arasında geçiş yapabilirsiniz.

## Adım 2: Makine Ekleme

Uzak sunucunuzu yapılandırmaya makine olarak kaydedin:

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Seçenek | Gerekli | Varsayılan | Açıklama |
|---------|---------|------------|----------|
| `--ip <address>` | Evet | - | Uzak sunucunun IP adresi veya ana bilgisayar adı |
| `--user <username>` | Evet | - | Uzak sunucudaki SSH kullanıcı adı |
| `--port <port>` | Hayır | `22` | SSH portu |
| `--datastore <path>` | Hayır | `/mnt/rediacc` | Rediacc'ın şifrelenmiş depoları sakladığı sunucu üzerindeki dizin yolu |

Makine eklendikten sonra rdc, sunucunun host anahtarlarını almak için otomatik olarak `ssh-keyscan` çalıştırır. Bunu manuel olarak da çalıştırabilirsiniz:

```bash
rdc config machine scan-keys -m server-1
```

Kayıtlı tüm makineleri görüntülemek için:

```bash
rdc config machine list
```

## Adım 3: Makineyi Hazırlama

Uzak sunucuyu gerekli tüm bağımlılıklarla hazırlayın:

```bash
rdc config machine setup --name server-1
```

Bu komut:
1. renet ikili dosyasını SFTP aracılığıyla sunucuya yükler
2. Docker, containerd ve cryptsetup'ı kurar (yüklü değilse)
3. `rediacc` sistem kullanıcısını (UID 7111) oluşturur
4. Veri deposu dizinini oluşturur ve şifrelenmiş depolar için hazırlar

| Seçenek | Gerekli | Varsayılan | Açıklama |
|---------|---------|------------|----------|
| `--datastore <path>` | Hayır | `/mnt/rediacc` | Sunucudaki veri deposu dizini |
| `--datastore-size <size>` | Hayır | `95%` | Veri deposu için ayrılacak disk alanı miktarı |
| `--debug` | Hayır | `false` | Sorun giderme için ayrıntılı çıktıyı etkinleştirir |

> Hazırlık her makine için yalnızca bir kez çalıştırılmalıdır. Gerektiğinde tekrar çalıştırmak güvenlidir.

## Host Anahtarı Yönetimi

Bir sunucunun SSH host anahtarı değiştiyse (ör. yeniden kurulum sonrası), saklanan anahtarları yenileyin:

```bash
rdc config machine scan-keys -m server-1
```

Bu komut, yapılandırmanızdaki ilgili makinenin `knownHosts` alanını günceller.

## SSH Bağlantısını Test Etme

Makine ekledikten sonra erişilebilir olduğunu doğrulayın:

```bash
rdc term connect -m server-1 -c "hostname"
```

Bu komut makineye SSH bağlantısı açar ve komutu çalıştırır. Başarılı olursa SSH yapılandırmanız doğrudur.

Daha ayrıntılı tanılama için şunu çalıştırın:

```bash
rdc doctor
```

> **Yalnızca bulut adaptörü**: `rdc machine test-connection` komutu ayrıntılı SSH tanılaması sağlar ancak bulut adaptörü gerektirir. Yerel adaptör için `rdc term` veya doğrudan `ssh` kullanın.

## Altyapı Yapılandırması

Trafiği herkese açık olarak sunması gereken makineler için altyapı ayarlarını yapılandırın:

### Altyapıyı Ayarlama

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Seçenek | Kapsam | Açıklama |
|---------|--------|----------|
| `--public-ipv4 <ip>` | Machine | Genel IPv4 adresi, proxy giriş noktaları yalnızca yapılandırılmış adres aileleri için oluşturulur |
| `--public-ipv6 <ip>` | Machine | Genel IPv6 adresi, proxy giriş noktaları yalnızca yapılandırılmış adres aileleri için oluşturulur |
| `--base-domain <domain>` | Machine | Uygulamalar için temel alan adı (ör. `example.com`) |
| `--cert-email <email>` | Config | Let's Encrypt TLS sertifikaları için e-posta (makineler arasında paylaşılır) |
| `--cf-dns-token <token>` | Config | ACME DNS-01 doğrulamaları için Cloudflare DNS API anahtarı (makineler arasında paylaşılır) |
| `--tcp-ports <ports>` | Machine | Virgülle ayrılmış ek TCP portları (ör. `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Virgülle ayrılmış ek UDP portları (ör. `53`) |

Machine kapsamlı seçenekler makine başına saklanır. Config kapsamlı seçenekler (`--cert-email`, `--cf-dns-token`) yapılandırmadaki her makinede paylaşılır. Bir kez ayarlayın ve her yerde geçerli olsun.

### Altyapıyı Görüntüleme

```bash
rdc config infra show -m server-1
```

### Sunucuya Gönderme

Traefik ters proxy yapılandırmasını oluşturun ve sunucuya dağıtın:

```bash
rdc config infra push -m server-1
```

Bu komut:
1. renet ikili dosyasını uzak makineye dağıtır
2. Traefik ters proxy, yönlendirici ve systemd hizmetlerini yapılandırır
3. `--cf-dns-token` ayarlanmışsa makine alt alan adı için Cloudflare DNS kayıtları oluşturur (`server-1.example.com` ve `*.server-1.example.com`)

DNS adımı otomatik ve idempotent'dir: eksik kayıtları oluşturur, IP'leri değişen kayıtları günceller ve zaten doğru olan kayıtları atlar. Cloudflare anahtarı yapılandırılmamışsa DNS bir uyarıyla atlanır. Her depo için wildcard DNS kayıtları (`rdc repo up`'ı çalıştırdığınızda otomatik olarak oluşturulur) otomatik olarak oluşturulur.

## Bulut Hazırlama

VM'leri manuel olarak oluşturmak yerine, bir bulut sağlayıcı yapılandırabilir ve `rdc`'nin [OpenTofu](https://opentofu.org/) kullanarak makineleri otomatik olarak hazırlamasını sağlayabilirsiniz.

### Ön Koşullar

OpenTofu'yu kurun: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

SSH yapılandırmanızda `rdc` ile kayıtlı bir anahtar bulunduğundan emin olun:

```bash
# Anahtar dosyasını okur ve içeriğini /credentials/ssh altında satır içine alır.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Bulut Sağlayıcı Ekleme

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `--provider <source>` | Evet* | Bilinen sağlayıcı kaynağı (ör. `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Evet* | Özel OpenTofu sağlayıcı kaynağı (bilinmeyen sağlayıcılar için) |
| `--token <token>` | Evet | Bulut sağlayıcının API anahtarı |
| `--region <region>` | Hayır | Yeni makineler için varsayılan bölge |
| `--type <type>` | Hayır | Varsayılan örnek türü/boyutu |
| `--image <image>` | Hayır | Varsayılan işletim sistemi imajı |
| `--ssh-user <user>` | Hayır | SSH kullanıcı adı (varsayılan: `root`) |

\* `--provider` veya `--source` gereklidir. Bilinen sağlayıcılar için `--provider` kullanın (yerleşik varsayılanlar). Özel sağlayıcılar için `--source` ile ek `--resource`, `--ipv4-output`, `--ssh-key-attr` bayraklarını kullanın.

### Makine Hazırlama

```bash
rdc machine provision --name prod-2 --provider my-linode
```

Bu tek komut:
1. OpenTofu aracılığıyla bulut sağlayıcıda bir VM oluşturur
2. SSH bağlantısını bekler
3. Makineyi yapılandırmanıza kaydeder
4. renet ve tüm bağımlılıkları kurar
5. Traefik proxy'si ve Cloudflare DNS'i yapılandırır (kardeş makinelerden temel alan adını otomatik olarak algılar veya `--base-domain`'i açıkça iletir)

| Seçenek | Açıklama |
|---------|----------|
| `--provider <name>` | Bulut sağlayıcı adı (`add-provider`'dan) |
| `--region <region>` | Sağlayıcının varsayılan bölgesini geçersiz kılar |
| `--type <type>` | Varsayılan örnek türünü geçersiz kılar |
| `--image <image>` | Varsayılan işletim sistemi imajını geçersiz kılar |
| `--base-domain <domain>` | Altyapı için temel alan adı. Belirtilmediği takdirde kardeş makinelerden otomatik olarak algılanır |
| `--no-infra` | Altyapı yapılandırmasını (proxy + DNS) tamamen atla |
| `--debug` | Ayrıntılı hazırlama çıktısını gösterir |

### Makine Kaldırma

```bash
rdc machine deprovision --name prod-2
```

VM'yi OpenTofu aracılığıyla yok eder ve yapılandırmanızdan kaldırır. `--force` kullanılmadıkça onay gerektirir. Yalnızca `machine provision` ile oluşturulan makineler için çalışır.

### Sağlayıcıları Listeleme

```bash
rdc config provider list
```

## Varsayılanları Ayarlama

Her komutta belirtmek zorunda kalmamak için varsayılan değerler ayarlayın:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Varsayılan makine
rdc config set --key team --value my-team                   # Varsayılan ekip (bulut adaptörü, deneysel)
```

Varsayılan makineyi ayarladıktan sonra komutlardan `-m server-1` ifadesini çıkarabilirsiniz:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Birden Fazla Yapılandırma

Adlandırılmış yapılandırmalarla birden fazla ortamı yönetin:

```bash
# Ayrı yapılandırmalar oluşturun
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# Belirli bir yapılandırmayı kullanın
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Tüm yapılandırmaları görüntüleyin:

```bash
rdc config list
```

Mevcut yapılandırma ayrıntılarını gösterin:

```bash
rdc config show
```
