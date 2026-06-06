---
title: "Sunucu Referansı"
description: "Dizin yapısı, renet komutları, systemd servisleri ve uzak sunucu iş akışları."
category: "Concepts"
order: 3
language: tr
sourceHash: "4fb53bb4cb1512f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Sunucu Referansı

SSH ile bir Rediacc sunucusuna bağlandığınızda karşılaşacaklarınız: dizin yapısı, `renet` komutları, systemd servisleri ve ihtiyaç duyacağınız iş akışları.

Kullanıcıların büyük çoğunluğu sunucuları iş istasyonlarından `rdc` aracılığıyla yönetir ve bu sayfaya ihtiyaç duymaz. Bu sayfa, gelişmiş hata ayıklama veya doğrudan sunucu üzerinde çalışmanız gerektiğinde başvurmanız içindir.

Üst düzey mimari için bkz. [Mimari](/tr/docs/architecture). `rdc` ile `renet` arasındaki fark için bkz. [rdc vs renet](/tr/docs/rdc-vs-renet).

## Dizin Yapısı

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## renet Komutları

`renet`, sunucu tarafındaki ikili dosyadır. Tüm komutlar root yetkisi (`sudo`) gerektirir.

### Depo Yaşam Döngüsü

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Belirli bir deponun Docker daemon'una karşı compose komutlarını çalıştırın:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Docker komutlarını doğrudan çalıştırın:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Docker soketini doğrudan da kullanabilirsiniz:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Compose'u her zaman `docker-compose.yml` dosyasının bulunduğu dizinden çalıştırın; aksi takdirde Docker dosyayı bulamaz.

### Dosya Sistemi Korumalı Alanı

```bash
# Landlock desteğini kontrol et
renet sandbox-exec --detect

# Landlock korumalı alanında komut çalıştır (dahili olarak kullanılır)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec`, Landlock LSM dosya sistemi kısıtlamalarını uygular ve ardından belirtilen komutu çalıştırır. Tüm depo düzeyindeki bağlantılar için `sandbox-gateway` (SSH ForceCommand işleyicisi) tarafından otomatik olarak çağrılır.

### Kullanıcı Başına Hub (geliştirme ortamları)

Hub, her kullanıcıya geliştirme ortamları için kendi Docker daemon'ını verir; bu daemon, depo başına `FlavorRediacc` daemon'larından bağımsızdır.

```bash
# Kullanıcı başına Hub systemd birimlerini kur / kaldır
sudo renet hub install
sudo renet hub uninstall

# Boşta kalan kullanıcı başına Hub daemon'larını temizle
sudo renet hub gc
```

Daemon'lar, `--flavor` ile seçilen iki flavor'dan biri altında çalışır:

```bash
# Depo başına izole daemon (bridge=none, iptables=false) — varsayılan
sudo renet daemon start-foreground --flavor=rediacc ...

# Kullanıcı başına Hub daemon'u (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

`hub` flavor'ı, kullanıcı tarafından çalıştırılan konteynerlerin dışarıya bağlantısı olması için normal bridge ağını etkinleştirir; `rediacc` flavor'ı ise depolar arasında loopback yalıtımını zorunlu kılar. Hub denetim günlükleri `/var/log/rediacc/hub/<user>.log` konumuna yazılır.

**Bayraklar:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: Landlock yol kuralları
- `--home-overlay`: Depo başına yazma yalıtımı için home dizininin üzerine OverlayFS bağlar
- `--sandbox-dir`: Depo başına çalışma alanı (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: Çalışma dizinini ayarlar ve depo ortamı için `.envrc` yükler
- `--run-as`: Kurulumdan sonra hedef kullanıcıya yetki düşürür
- `--reset-home`: Temiz bir başlangıç için depo başına home katmanını temizler

**`sandbox-gateway`**, `authorized_keys` içindeki `command=` aracılığıyla ayarlanan SSH ForceCommand işleyicisidir. Her deponun SSH anahtarı, istemcinin taklit edemeyeceği depo adı gömülü olarak gateway'i tetikler. Gateway, sandbox-exec argümanlarını oluşturur ve sudo aracılığıyla çalıştırır.

### Proxy ve Yönlendirme

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Rotalar, konteyner etiketlerinden otomatik olarak keşfedilir. Traefik etiketlerinin nasıl yapılandırılacağı için bkz. [Ağ](/tr/docs/networking).

### Sistem Durumu

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Daemon Yönetimi

Her depo kendi Docker daemon'ını çalıştırır. Bunları ayrı ayrı yönetebilirsiniz:

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Yedekleme ve Geri Yükleme

Yedekleri başka bir makineye veya bulut depolama alanına gönderin:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> Kullanıcıların büyük çoğunluğu bunun yerine `rdc repo push/pull` kullanmalıdır. `rdc` komutları kimlik bilgilerini ve makine çözümlemesini otomatik olarak yönetir.

### Kontrol Noktaları (CRIU)

Kontrol noktaları, çalışan konteynerlerin durumunu kaydederek daha sonra geri yüklenmesini sağlar:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Bakım

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Systemd Servisleri

Her depo şu systemd birimlerini oluşturur:

| Birim | Amaç |
|-------|------|
| `rediacc-docker-{id}.service` | Yalıtılmış Docker daemon'u |
| `rediacc-docker-{id}.socket` | Docker API soket aktivasyonu |
| `rediacc-loopback-{id}.service` | Loopback IP takma adı kurulumu |

Tüm depolar arasında paylaşılan global servisler:

| Birim | Amaç |
|-------|------|
| `rediacc-router.service` | Rota keşfi (port 7111) |
| `rediacc-autostart.service` | Önyükleme zamanı depo bağlama |
| `rediacc-autostart-reconcile.service` | Periyodik otomatik başlatma uzlaştırıcısı (aşağıdaki zamanlayıcı tarafından çalıştırılır) |
| `rediacc-autostart-reconcile.timer` | Önyüklemeden sonra duran otomatik başlatma depolarını kurtarmak için yaklaşık her 3 dakikada bir `renet repository reconcile` komutunu çalıştırır |

## Yaygın İş Akışları

### Yeni Bir Servis Dağıtma

1. Şifrelenmiş bir depo oluşturun:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Bağlayın ve `docker-compose.yml`, `Rediaccfile` ve `.rediacc.json` dosyalarını ekleyin.
3. Başlatın:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Çalışan Bir Konteynere Erişim

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Hangi Docker Soketinin Konteyneri Çalıştırdığını Bulma

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Yapılandırma Değişikliklerinden Sonra Servis Yeniden Oluşturma

```bash
sudo renet compose -- up -d
```

Bunu `docker-compose.yml` içeren dizinden çalıştırın. Değiştirilen konteynerler otomatik olarak yeniden oluşturulur.

### Tüm Daemon'lardaki Tüm Konteynerleri Kontrol Etme

```bash
renet list containers
```

## İpuçları

- `renet compose`, `renet repository` ve `renet docker` komutları için her zaman `sudo` kullanın; LUKS ve Docker işlemleri için root yetkisi gerekir
- `renet compose` ve `renet docker`'a argüman geçirmeden önce `--` ayracı zorunludur
- Compose'u `docker-compose.yml` içeren dizinden çalıştırın
- `.rediacc.json` slot atamaları sabittir, dağıtımdan sonra değiştirmeyin
- `/run/rediacc/docker-{id}.sock` yollarını kullanın (systemd eski `/var/run/` yollarını değiştirebilir)
- Sahipsiz kaynakları bulmak için zaman zaman `renet prune --dry-run` çalıştırın
- BTRFS anlık görüntüleri (`renet backup`) hızlı ve ucuzdur; riskli değişiklikler yapmadan önce kullanın
- Depolar LUKS ile şifrelenmiştir; parolayı kaybetmek verileri kaybetmek anlamına gelir
