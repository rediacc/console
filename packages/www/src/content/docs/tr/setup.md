---
title: "Makine Kurulumu"
description: "Baglam olusturma, makine ekleme, sunuculari hazirlama ve altyapi yapilandirmasi."
category: "Guides"
order: 3
language: tr
---

# Makine Kurulumu

Bu sayfa, ilk makinenizi kurma sürecini anlatır: bağlam oluşturma, sunucu kaydetme, hazırlama ve isteğe bağlı olarak genel erişim için altyapı yapılandırması.

## Adım 1: Yerel Bağlam Oluşturma

Bir **bağlam** (context), SSH kimlik bilgilerinizi, makine tanımlarınızı ve depo eşlemelerinizi saklayan adlandırılmış bir yapılandırmadır. Bunu bir proje çalışma alanı olarak düşünebilirsiniz.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `--ssh-key <path>` | Evet | SSH özel anahtarınızın yolu. Tilde (`~`) otomatik olarak genişletilir. |
| `--renet-path <path>` | Hayır | Uzak makinelerdeki renet ikili dosyasının özel yolu. Varsayılan olarak standart kurulum konumunu kullanır. |

Bu komut `my-infra` adında bir yerel bağlam oluşturur ve `~/.rediacc/config.json` dosyasında saklar.

> Birden fazla bağlamınız olabilir (ör. `production`, `staging`, `dev`). Herhangi bir komutta `--context` bayrağıyla bunlar arasında geçiş yapabilirsiniz.

## Adım 2: Makine Ekleme

Uzak sunucunuzu bağlama makine olarak kaydedin:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Seçenek | Gerekli | Varsayılan | Açıklama |
|---------|---------|------------|----------|
| `--ip <address>` | Evet | - | Uzak sunucunun IP adresi veya ana bilgisayar adı |
| `--user <username>` | Evet | - | Uzak sunucudaki SSH kullanıcı adı |
| `--port <port>` | Hayır | `22` | SSH portu |
| `--datastore <path>` | Hayır | `/mnt/rediacc` | Rediacc'ın şifrelenmiş depoları sakladığı sunucu üzerindeki dizin yolu |

Makine eklendikten sonra rdc, sunucunun host anahtarlarını almak için otomatik olarak `ssh-keyscan` çalıştırır. Bunu manuel olarak da çalıştırabilirsiniz:

```bash
rdc context scan-keys server-1
```

Kayıtlı tüm makineleri görüntülemek için:

```bash
rdc context machines
```

## Adım 3: Makineyi Hazırlama

Uzak sunucuyu gerekli tüm bağımlılıklarla hazırlayın:

```bash
rdc context setup-machine server-1
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
rdc context scan-keys server-1
```

Bu komut, yapılandırmanızdaki ilgili makinenin `knownHosts` alanını günceller.

## SSH Bağlantısını Test Etme

Devam etmeden önce makinenizin erişilebilir olduğunu doğrulayın:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Bu komut SSH bağlantısını test eder ve şunları bildirir:
- Bağlantı durumu
- Kullanılan kimlik doğrulama yöntemi
- SSH anahtarı yapılandırması
- Bilinen sunucular (known hosts) kaydı

Doğrulanmış host anahtarını makine yapılandırmanıza `--save -m server-1` ile kaydedebilirsiniz.

## Altyapı Yapılandırması

Trafiği herkese açık olarak sunması gereken makineler için altyapı ayarlarını yapılandırın:

### Altyapıyı Ayarlama

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Seçenek | Açıklama |
|---------|----------|
| `--public-ipv4 <ip>` | Dış erişim için genel IPv4 adresi |
| `--public-ipv6 <ip>` | Dış erişim için genel IPv6 adresi |
| `--base-domain <domain>` | Uygulamalar için temel alan adı (ör. `example.com`) |
| `--cert-email <email>` | Let's Encrypt TLS sertifikaları için e-posta |
| `--cf-dns-token <token>` | ACME DNS-01 doğrulamaları için Cloudflare DNS API anahtarı |
| `--tcp-ports <ports>` | Virgülle ayrılmış ek TCP portları (ör. `25,143,465,587,993`) |
| `--udp-ports <ports>` | Virgülle ayrılmış ek UDP portları (ör. `53`) |

### Altyapıyı Görüntüleme

```bash
rdc context show-infra server-1
```

### Sunucuya Gönderme

Traefik ters proxy yapılandırmasını oluşturun ve sunucuya dağıtın:

```bash
rdc context push-infra server-1
```

Bu komut, altyapı ayarlarınıza dayalı proxy yapılandırmasını gönderir. Traefik, TLS sonlandırmasını, yönlendirmeyi ve port yönlendirmeyi yönetir.

## Varsayılanları Ayarlama

Her komutta belirtmek zorunda kalmamak için varsayılan değerler ayarlayın:

```bash
rdc context set machine server-1    # Varsayılan makine
rdc context set team my-team        # Varsayılan ekip (bulut modu, deneysel)
```

Varsayılan makineyi ayarladıktan sonra komutlardan `-m server-1` ifadesini çıkarabilirsiniz:

```bash
rdc repo create my-app --size 10G   # Varsayılan makineyi kullanır
```

## Birden Fazla Bağlam

Adlandırılmış bağlamlarla birden fazla ortamı yönetin:

```bash
# Ayrı bağlamlar oluşturun
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# Belirli bir bağlamı kullanın
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

Tüm bağlamları görüntüleyin:

```bash
rdc context list
```

Mevcut bağlam ayrıntılarını gösterin:

```bash
rdc context show
```
