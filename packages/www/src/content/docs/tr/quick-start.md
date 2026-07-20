---
title: Hızlı Başlangıç
description: Birkaç dakika içinde sunucunuzda konteynerize bir servis çalıştırın.
category: Guides
order: -1
language: tr
sourceHash: "6e81b15303ed64f9"
sourceCommit: "e4a4e0de5"
---

# Hızlı Başlangıç

Kendi sunucunuzda şifrelenmiş, izole bir konteyner ortamı dağıtın. Bulut hesabı veya SaaS bağımlılığı gerekmez. Her şey sizin kontrol ettiğiniz donanım üzerinde çalışır.

---

## Giriş

### Temel Kavramlar

Bir repo, disk üzerinde tek bir şifrelenmiş dosyadır. Taşıyabilir, yedekleyebilir, çatallayabilirsiniz. Sadece bir dosyadır. Bağlandığında, içinde özel bir Docker daemon'u ve uygulama verileriniz bulunan bir klasöre dönüşür.

Bir repoyu USB bellek gibi düşünün: herhangi bir makineye takın; uygulamalar ve veriler bağlanır, çalışmaya hazır. Hiçbir şeyi yeniden oluşturmadan makineler veya bulut sağlayıcıları arasında taşıyın.

**İki araç, iki rol:**

- **rdc** = Dizüstü bilgisayarınızdaki CLI (TypeScript, global olarak kurulur)
- **renet** = Sunucudaki orkestratör (Go ikili dosyası, daemon/ağ/izolasyon yönetimi)
- RDC, `config machine setup` sırasında renet'i otomatik olarak kurar. Sunucuda elle kurulum gerekmez.

> [Mimari](/en/docs/architecture) güvenlik modelini açıklar. [rdc vs renet](/en/docs/rdc-vs-renet) hangi aracı ne zaman kullanacağınızı açıklar.

### 1. CLI Kurulumu

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Doğrulama: Node, SSH anahtarı, renet, Docker
```

> Windows, Alpine, Arch: bkz. [Kurulum](/en/docs/installation). Tam sistem gereksinimleri: [Gereksinimler](/en/docs/requirements).

### 2. SSH Anahtar Kurulumu

rdc, SSH üzerinden bağlanır. rdc sunucuya ulaşabilmesi için sunucunun ortak anahtarınıza güvenmesi gerekir.

```bash
# Anahtar oluşturun (zaten varsa atlayın)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Ortak anahtarı sunucuya kopyalayın (parola isteyecektir)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# rdc'ye hangi anahtarı kullanacağını belirtin
rdc config ssh set --key ~/.ssh/id_ed25519
```

Artık her rdc komutu bu anahtarla kimlik doğrulaması yapar. Parola gerekmez.

### 3. Sunucunuzu Ekleyin

```bash
rdc machine add my-server --ip 192.168.1.100 --user admin
rdc machine setup my-server  # renet kurulumu + veri deposu oluşturma
```

**Ne olur:** SSH host anahtarı taranır, renet ikili dosyası yüklenir, sunucuda şifrelenmiş veri deposu başlatılır. Repolar için hazır.

> Veri deposu boyutlandırma, Ceph RBD, bulut sağlayıcıları: [Makine Kurulumu](/en/docs/setup). SSH hataları: [Sorun Giderme](/en/docs/troubleshooting).

### 4. Yapılandırma Dosyası

```bash
rdc config show                            # Okunabilir özet
cat ~/.config/rediacc/rediacc.json         # Ham JSON: makineler, repolar, depolar, SSH anahtarı
```

**Tek dosya = tek ortam.** Başka bir dizüstü bilgisayara kopyalayın ve hazırsınız.

---

## Repo ile Çalışma

### 1. Repo Oluşturma

```bash
rdc repo create my-app -m my-server --size 2G  # 2 GB şifrelenmiş repo oluştur
```

Şifrelenmiş birimi oluşturur, bağlar ve Docker daemon'unu başlatır. Repo yapılandırmanıza kaydedilir ve kullanıma hazırdır.

> Yeniden boyutlandırma, silme, doğrulama: [Depolar](/en/docs/repositories).

### 2. Şablon Uygulama

```bash
rdc repo admin template list                                        # Gömülü şablonları göster
rdc repo admin template apply my-app --template app-postgres  # docker-compose.yml + Rediaccfile dağıt
```

Şablonlar bir `docker-compose.yml`, `Rediaccfile` ve destekleyici dosyalar sağlar. Bir şablon (veya kendi compose dosyanız) olmadan başlatılacak bir şey yoktur. İlk reponuz için yerleşik şablonu kullanın. Tüm iş akışını baştan sona görmek için en hızlı yoldur.

### 3. Repoyu Başlatma

```bash
rdc repo up my-app  # Rediaccfile up() çalıştır
rdc repo list -m my-server                           # Makinedeki tüm repoları gör
rdc repo status my-app  # Bağlama durumu, Docker, boyut, şifreleme
```

`repo up` gerektiğinde otomatik bağlama yapar. Ek bayrak gerekmez.

### 4. VS Code

```bash
rdc vscode connect my-app              # VS Code SSH açar, repo sandbox'una iner
```

Şifrelenmiş birim *içinde* dosyaları düzenliyorsunuz. `docker ps` yalnızca bu reponun konteynerlerini gösterir. Kaydedin, compose up yapın, tekrarlayın.

### 5. `rdc repo up` ile `renet dev up` Karşılaştırması

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Nerede çalıştırırsınız** | Dizüstü bilgisayarınız (CLI) | VS Code sandbox içinde |
| **Ne yapar** | SSH → otomatik bağlama → Rediaccfile `up()` çalıştırır | Rediaccfile `up()` doğrudan çalıştırır |
| **Kullanım senaryosu** | CI/CD, otomasyon, uzaktan işlemler | Geliştirici iç döngüsü |
| **İzolasyon** | Dışarıdan yönetir | Zaten sandbox içindedir |

**Demo akışı:** `rdc repo admin template apply` → `rdc vscode connect my-app` → `docker-compose.yml` düzenle → `renet dev up` → uygulamanın çalıştığını gör → tekrarla.

> Rediaccfile yapısı: [Servisler](/en/docs/services). Hangi aracı ne zaman kullanmalı: [rdc vs renet](/en/docs/rdc-vs-renet).

### 6. İzolasyon Modeli

- **Evrensel kullanıcı** (`rediacc`): Her makinede aynı UID. Bir repoyu başka bir sunucuya taşıdığınızda dosya sahipliği sorunsuz çalışır. `chown` sorunları olmaz.
- **Repo başına Docker daemon**: Her repo kendi izole Docker daemon'una sahiptir. `docker ps` yalnızca BU reponun konteynerlerini gösterir.
- **Landlock + OverlayFS sandbox**: VS Code kabuğu dosya sistemiyle sınırlıdır. Diğer repoları okuyamazsınız. `$HOME` dizinine yapılan yazmalar repo bazında katmanlardır.

> İzolasyonun çalışma prensibi: [Mimari](/en/docs/architecture). Rediaccfile yaşam döngüsü: [Servisler](/en/docs/services).

### 7. Terminal, Senkronizasyon ve Tünel

**Terminal:**
```bash
rdc term connect my-app                            # Repo sandbox'una SSH bağlantısı
rdc term connect my-app -c "curl localhost:3000"   # Komut çalıştır ve çık
rdc term connect my-server                                   # Makineye SSH (sandbox yok)
```

**Dosya Senkronizasyonu (SSH üzerinden rsync):**
```bash
rdc repo sync upload my-app --local ./src                                   # Bir dizin yükle
rdc repo sync upload my-app --local ./config.yml --remote conf              # Tek bir dosya yükle
rdc repo sync download my-app --local ./backup                              # Bir dizin indir
rdc repo sync download my-app --remote-file conf/config.yml --local ./dl    # Tek bir dosya indir
rdc repo sync download my-app --local ./backup --dry-run                    # Önce önizleme yap
```

**Tünel (Konteynere SSH port yönlendirme):**
```bash
rdc repo tunnel my-app -c app  # app konteynerinin portunu otomatik algıla
rdc repo tunnel my-app -c db --port 5432  # Postgres tüneli
rdc repo tunnel my-app -c db --port 5432 --local 15432  # Özel yerel port
```

Tünel çalıştırın → tarayıcıda `localhost:3000` açın → uzak sunucudan canlı uygulama.

> Senkronizasyon, terminal, VS Code detayları: [Araçlar](/en/docs/tools).

---

## Çatallama ve Yedekleme

### 1. Grand ve Fork Repoları

```bash
rdc repo fork my-app --tag experiment --up  # Anında CoW klonu + başlat
rdc repo list -m my-server                                  # Gösterir: my-app (grand) + my-app:experiment (fork)
rdc repo delete my-app:experiment  # Fork'u sil, grand'a dokunulmaz
```

**Anında, sıfır kopya klonlama.** CoW (copy-on-write). Mikrosaniyeler, veri kopyalanmaz. Bir taraf yazana kadar bloklar paylaşılır.

**Kullanım senaryoları:**
- **AI / ML:** Üretim veri setini çatalla, deney yap, at veya terfi ettir
- **DevOps:** Çatalla → geçişi test et → kötüyse sil, iyiyse terfi ettir
- **Yedekleme:** Fork = anlık görüntü, uzak konuma gönder

> Fork yaşam döngüsü, makineler arası fork: [Depolar](/en/docs/repositories).

### 2. Başka Bir Makineye Gönderme

```bash
# Repoyu başka bir makineye gönder
rdc repo push my-app --to backup-server

# Gönder ve hedefte otomatik dağıt
rdc backup restore my-app --as my-app -m backup-server --up

# CRIU kontrol noktası ile gönder (canlı geçiş, bellek durumunu korur)
rdc repo push my-app --to new-server --checkpoint

# Yeni bir makineye gönder (bulut sağlayıcı ile otomatik kurulum)
rdc repo push my-app --to new-server --provision linode
```

### 3. Bulut Depolamaya Gönderme (OneDrive, Google Drive, S3)

```bash
# rclone yapılandırmanızı depolama arka ucu olarak içe aktarın
rdc storage import ~/rclone.conf

# Kullanılabilir depolamaları listeleyin
rdc storage list

# Repoyu bulut depolamaya gönderin
rdc repo push my-app --to my-s3-backup

# Depolamadaki yedekleri listeleyin
rdc backup list --storage my-s3-backup
```

`--to` hedefin bir makine mi yoksa depolama arka ucu mu olduğunu otomatik algılar. rclone destekli tüm sağlayıcılarla çalışır: S3, R2, B2, OneDrive, Google Drive, SFTP, vb.

### 4. Uzaktan Çekme

```bash
# Bir bulut makinesinden yerel sunucunuza repo çekin
rdc repo pull my-app@my-local-server --from cloud-server

# Bulut depolamadan çekin
rdc repo pull my-app@my-local-server --from my-s3-backup

# Çek ve hemen başlat
rdc repo pull my-app@my-local-server --from my-s3-backup --up
```

**Neden pull?** Yerel makineniz NAT arkasındadır. Bulut size push yapamaz. Ama siz buluta ulaşabilirsiniz. Pull, repoyu eve getirir.

**Tam döngü:** Geliştirmede oluştur → buluta gönder → üretimde çek → `--up`. Tek repo, herhangi bir makine, herhangi bir bulut.

> Zamanlama, otomatik yedekleme, geri yükleme: [Yedekleme ve Geri Yükleme](/en/docs/backup-restore).

---

## Proxy ve SSL

### 1. Altyapı Yapılandırması

```bash
rdc machine infra set my-server  # Yapılandır: temel alan adı, genel IP'ler, port aralıkları
rdc machine infra show my-server  # Yapılandırmayı incele
rdc machine infra push my-server  # Proxy yapılandırmasını uzak sunucuya gönder
```

**Yönlendirme nasıl çalışır:**
- Traefik, `rediacc.service_name` ve `rediacc.service_port` etiketleri aracılığıyla konteynerleri otomatik keşfeder
- Yönlendirme: `{service}-{networkId}.{baseDomain}` → konteyner IP:port
- SSL: Cloudflare DNS-01 doğrulaması ile Let's Encrypt (otomatik yenileme, wildcard sertifikaları)

### 2. Proxy Şablonu

```bash
rdc repo admin template apply infra --template proxy  # Proxy'yi bir repoya dağıt
rdc repo up infra  # Traefik'i başlat
```

Traefik artık bu makinedeki tüm repolara gelen dış trafiği yönlendirir. Her konteyner otomatik olarak bir HTTPS uç noktası alır.

```bash
# https://my-app.example.com adresine gidin → konteynere yönlendirilir
# Veritabanları için TCP/UDP yönlendirme:
#   rediacc.tcp_ports=3306,5432 → otomatik atanan harici portlar
```

> Yönlendirme kuralları, DNS, TLS yapılandırması: [Ağ](/en/docs/networking).

---

## Sonraki Adımlar

- **[Geçiş Rehberi](/en/docs/migration)** - Mevcut projeleri Rediacc depolarına taşıma
- **[İzleme](/en/docs/monitoring)** - Makine sağlığı, konteynerler, servisler, tanılamalar
- **[CLI Referansı](/en/docs/cli-application)** - Eksiksiz komut referansı
- **[Hızlı Referans Kartı](/en/docs/rdc-cheat-sheet)** - Hızlı komut arama
- **[Sorun Giderme](/en/docs/troubleshooting)** - Yaygın sorunların çözümleri
- **[Rediacc Kuralları](/en/docs/rules-of-rediacc)** - Rediaccfile en iyi uygulamaları ve dağıtım kontrol listesi
