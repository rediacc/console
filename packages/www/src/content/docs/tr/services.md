---
title: Servisler
description: >-
  Rediaccfile, servis ağı, başlatma/durdurma ve otomatik başlatma ile
  konteynerleştirilmiş servisleri dağıtın ve yönetin.
category: Guides
order: 5
language: tr
sourceHash: "9a08a357e86497e3"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Servisler

Hangi aracı kullanacağınızdan emin değilseniz [rdc vs renet](/tr/docs/rdc-vs-renet) sayfasına bakın.

Bu sayfa, konteynerleştirilmiş servislerin nasıl dağıtılacağını ve yönetileceğini kapsar: Rediaccfile'lar, servis ağı, başlatma/durdurma, toplu işlemler ve otomatik başlatma.

## Rediaccfile

**Rediaccfile**, servislerinizin nasıl başlatıldığını ve durdurulduğunu tanımlayan bir Bash betiğidir. Dosya adı `Rediaccfile` veya `rediaccfile` (büyük/küçük harf duyarsız) olmalı ve deponun bağlı dosya sistemi içine yerleştirilmelidir.

Rediaccfile'lar iki konumda aranır:
1. Depo bağlama yolunun **kök dizini**
2. Bağlama yolunun **birinci seviye alt dizinleri** (özyinelemeli değil)

Gizli dizinler (`.` ile başlayan adlar) atlanır.

### Yaşam Döngüsü Fonksiyonları

Bir Rediaccfile en fazla iki fonksiyon içerir:

| Fonksiyon | Ne zaman çalışır | Amacı | Hata davranışı |
|-----------|-------------------|-------|----------------|
| `up()` | Başlatma sırasında | Servisleri başlatma (ör. `renet compose -- up -d`) | Kök hatası **kritiktir** (her şeyi durdurur). Alt dizin hataları **kritik değildir** (günlüğe kaydedilir, devam eder) |
| `down()` | Durdurma sırasında | Servisleri durdurma (ör. `renet compose -- down`) | **En iyi çaba** -- hatalar günlüğe kaydedilir ancak tüm Rediaccfile'lar her zaman denenir |

Her iki fonksiyon da isteğe bağlıdır. Tanımlanmamış fonksiyonlar sessizce atlanır.

### Çalıştırma Sırası

- **Başlatma (`up`):** Önce kök Rediaccfile, ardından alt dizinler **alfabetik sıraya** göre (A'dan Z'ye).
- **Durdurma (`down`):** Alt dizinler **ters alfabetik sıraya** göre (Z'den A'ya), ardından en son kök dizin.

### Ortam Değişkenleri

Bir Rediaccfile fonksiyonu çalıştığında, aşağıdaki ortam değişkenleri kullanılabilir:

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `REDIACC_WORKING_DIR` | Deponun bağlama yolu | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | Depo GUID'i | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | Ağ Kimliği (tamsayı) | `2816` |
| `DOCKER_HOST` | Bu deponun izole daemon'u için Docker soketi | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json` dosyasında tanımlanan her servis için loopback IP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP` değişkenleri `.rediacc.json` dosyasından otomatik olarak oluşturulur. Adlandırma kuralı, servis adını büyük harfe çevirir, tireleri alt çizgi ile değiştirir ve sonuna `_IP` ekler. Örneğin, `listmonk-app` servisi `LISTMONK_APP_IP` olur.

> **Uyarı: Rediaccfile'larda `sudo docker` kullanmayın.** `sudo` komutu ortam değişkenlerini sıfırlar, bu da `DOCKER_HOST` değişkeninin kaybolmasına ve Docker komutlarının deponun izole daemon'u yerine sistem daemon'unu hedeflemesine neden olur. Bu, konteyner izolasyonunu bozar ve port çakışmalarına yol açabilir. Rediacc, `-E` olmadan `sudo docker` algılarsa çalıştırmayı engeller.
>
> Rediaccfile'larınızda `renet compose` kullanın -- bu, `DOCKER_HOST` değişkenini otomatik olarak yönetir, yönlendirme keşfi için ağ etiketlerini enjekte eder ve servis ağını yapılandırır. Servislerin ters proxy aracılığıyla nasıl sunulduğuna dair ayrıntılar için [Ağ Yapılandırması](/tr/docs/networking) sayfasına bakın. Docker'ı doğrudan çağırıyorsanız, `sudo` olmadan `docker` kullanın -- Rediaccfile fonksiyonları zaten yeterli yetkiyle çalışır. sudo kullanmanız gerekiyorsa, ortam değişkenlerini korumak için `sudo -E docker` kullanın.

### Örnek

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Önemli:** `docker compose` yerine her zaman `renet compose --` kullanın. `renet compose` sarmalayıcısı, host ağını, IP tahsisini ve renet-proxy tarafından gerekli olan servis keşif etiketlerini zorunlu kılar. CRIU checkpoint/restore yetenekleri `rediacc.checkpoint=true` etiketli konteynerlere eklenir. Doğrudan `docker compose` kullanımı Rediaccfile doğrulaması tarafından reddedilir. Ayrıntılar için [Ağ Yapılandırması](/tr/docs/networking) sayfasına bakın.

### Çoklu Servis Düzeni

Birden fazla bağımsız servis grubu olan projeler için alt dizinler kullanın:

```
/mnt/rediacc/mounts/my-app/
├── Rediaccfile              # Kök: paylaşılan kurulum
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Veritabanı servisleri
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API sunucusu
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, vb.
    └── docker-compose.yml
```

`up` için çalıştırma sırası: kök, ardından `backend`, `database`, `monitoring` (A-Z).
`down` için çalıştırma sırası: `monitoring`, `database`, `backend`, ardından kök (Z-A).

## Servis Ağı (.rediacc.json)

Her depo, `127.x.x.x` loopback aralığında bir /26 alt ağı (64 IP) alır. Servisler benzersiz loopback IP'lerine bağlanır, böylece çakışma olmadan aynı portlarda çalışabilirler.

### .rediacc.json Dosyası

Servis adlarını **slot** numaralarıyla eşler. Her slot, deponun alt ağı içinde benzersiz bir IP adresine karşılık gelir.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Docker Compose'dan Otomatik Oluşturma

`.rediacc.json` dosyasını manuel olarak oluşturmanız gerekmez. `rdc repo up` komutunu çalıştırdığınızda Rediacc otomatik olarak:

1. Rediaccfile içeren tüm dizinleri compose dosyaları (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` veya `compose.yaml`) için tarar
2. Her compose dosyasının `services:` bölümünden servis adlarını çıkarır
3. Yeni servislere bir sonraki kullanılabilir slotu atar
4. Sonucu `{repository}/.rediacc.json` dosyasına kaydeder

### IP Hesaplama

Bir servisin IP'si, deponun ağ kimliğinden ve servisin slotundan hesaplanır. Ağ kimliği, `127.x.y.z` loopback adresinin ikinci, üçüncü ve dördüncü oktetlerine dağıtılır. Her servis, ağ kimliğine `slot + 2` ofseti eklenerek bir adres alır (ofset 0 ve 1 ayrılmıştır).

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Örnek**: Ağ kimliği `2816` (`0x0B00`) için, temel adres `127.0.11.0`:

| Servis | Slot | IP Adresi |
|--------|------|-----------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Her depo en fazla **61 servisi** destekler (slot 0'dan 60'a kadar).

### Docker Compose'da Servis IP'lerini Kullanma

Her depo izole bir Docker daemon'u çalıştırdığından, `renet compose` tüm servisler için otomatik olarak `network_mode: host` yapılandırır. Çekirdek, `bind()` çağrılarını servisin atanan loopback IP'sine şeffaf biçimde yeniden yazar; bu nedenle servisler çakışma olmadan `0.0.0.0` veya `localhost`'a bağlanabilir. **Diğer servislere bağlantı** için **servis adını** kullanın -- renet her servis adını fork'larda da her zaman doğru IP'ye çözümlenen bir hostname olarak enjekte eder:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Açık listen_addresses gerekmez -- çekirdek bind'i doğru loopback IP'ye yeniden yazar

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # servis adını kullan
      LISTEN_ADDR: 0.0.0.0:8080                                      # çekirdek servis IP'sine yeniden yazar
```

> **Bağlantılar için servis adları:** Diğer servislere **bağlanmak** için **servis adını** (örn. `postgres`, `redis`) kullanın -- renet, `/etc/hosts` aracılığıyla her servis adını otomatik olarak loopback IP'sine eşler. Veritabanlarında veya yapılandırma dosyalarında saklanan bağlantı dizelerine `${POSTGRES_IP}` gömülmesi ham IP'yi sabitler, bu fork izolasyonunu bozar ve bir **doğrulama hatasıdır**. `${SERVICE_IP}` değişkenleri açık kullanım için hâlâ mevcuttur, ancak bağlama çekirdek tarafından otomatik olarak yönetilir.

> **Not:** `network_mode: host` ifadesini manuel olarak eklemeyin, `renet compose` bunu otomatik olarak enjekte eder. Yeniden başlatma politikaları (örn., `restart: always`) güvenle kullanılabilir, renet CRIU uyumluluğu için bunları otomatik olarak kaldırır ve yönlendirici watchdog konteyner kurtarmasını yönetir.

### Konteyner Kurtarma ve Yeniden Başlatma Politikası

renet ve Docker, konteyner yeniden başlatmalarının nasıl ele alınacağı konusunda kasıtlı olarak farklı görüştedir. Bu ayrımı anlamak, bir konteynerin neden geri geldiğini veya gelmediğini araştırırken önemlidir.

**Yeniden başlatma politikasının çevirisi.** Compose dosyanıza `restart: always` (veya `unless-stopped`, ya da `on-failure`) yazdığınızda, renet gerçek compose dağıtımını sentezlerken bunu **siler** ve `restart: no` ile değiştirir. Orijinal değer, deponun `.rediacc.json` dosyasında `services.<name>.restart_policy` altına kaydedilir. Bu, Docker daemon seviyesindeki otomatik yeniden başlatmanın CRIU checkpoint/restore işlemine müdahale etmesini önler (daemon güdümlü bir yeniden başlatma, eski bir checkpoint öncesi durumdan devam ederdi).

**Watchdog uygulaması.** Yönlendirici watchdog her makinede periyodik olarak çalışır. Her döngüde:

1. Her depo için `.rediacc.json` dosyasını okur ve kurtarılabilir `restart_policy`'ye sahip servisleri bulur.
2. O deponun daemon'u için tüm konteynerleri listeler, durmuş olanları tespit eder ve kaydedilen politikaya göre yeniden başlatır. 30 saniyelik bir tolerans süresi, `docker stop` komutunu az önce çalıştırmış bir operatörle çakışmayı önler.
3. Aynı döngü aynı zamanda `/var/run/rediacc/cold-backup-<guid>.running.json` dosyasını da işler (bkz. [Soğuk Yedek Semantiği](backup-restore.md#cold-backup-semantics)). Listelenen konteynerler kaydedilen politikadan bağımsız olarak yeniden başlatılır; çünkü sidecar şu anlama gelir: "renet bunları kasıtlı olarak durdurdu ve operatöre yeniden başlatmayı borçludur."

**`on-failure` politikasının neden bozuk görünebileceği.** Docker'ın `on-failure` politikası yalnızca konteyner sıfır dışı bir kodla çıktığında yeniden başlatır. `docker stop` komutundan veya daemon kapatmasından kaynaklanan düzgün bir durdurma (exit 0) "başarısızlık" değildir ve Docker'ın yerel mantığında da watchdog'un kaydedilmiş politika yolunda da yeniden başlatmayı TETIKLEMEZ. Soğuk yedek sidecar güvenlik ağıdır: kasıtlı olarak durdurduğumuz herhangi bir konteyner, politikasından bağımsız olarak yeniden başlatılır.

**Çalışma zamanı durumunu yorumlama:**

- `docker inspect <container>` → `RestartPolicy.Name`: renet tarafından yönetilen konteynerler için her zaman `no` olur. Semantik politika için buna güvenmeyin.
- Depo bağlama kökündeki `.rediacc.json` → `services.<name>.restart_policy`: gerçek niyet.
- `docker ps --format '{{.Status}}'`: çalışma zamanı durumu.

**Sapmanın düzeltilmesi.** Bir konteynerin `.rediacc.json` dosyasındaki kaydedilmiş politika yanlışsa (örneğin compose düzenlendi ama konteyner hiç yeniden oluşturulmadı), `rdc repo up --name <repo> -m <machine>` komutunu yeniden çalıştırın. Konteyner, güncellenen politika kaydedilerek yeniden oluşturulur.

> **Deneysel:** Soğuk yedek sidecar tabanlı kurtarma ve `rdc machine query` komutundaki `--sync-certs` bayrağı renet 0.9+ ile sunuldu. Eski sürümler watchdog kurtarması için yalnızca kaydedilmiş `restart_policy`'ye güvenir; bu da soğuk yedekten sonra `on-failure` konteynerlerini mahsur bırakabilir.

> **Docker bridge ağı, rediacc tarafından yönetilen daemonlarda devre dışıdır.** Her depo başına daemon, `"bridge": "none"` ve `"iptables": false` ile yapılandırılmıştır. Bir depo kabuğunda düz bir `docker run <image>` komutu yine de başlar, ancak konteynere yalnızca bir loopback arayüzü verilir ve DNS ya da dışa doğru bağlantı bulunmaz. Bu tasarım gereğidir, çünkü depolar arası loopback izolasyonu, köprülü bir konteynerin atlayacağı eBPF cgroup kancaları tarafından zorunlu kılınır. Üretim servisleri `renet compose` kullanmalıdır (bu sizin için host ağını enjekte eder); geçici hata ayıklama için `--network host` parametresini açıkça geçin: `docker run --rm --network host -it ubuntu bash`.

> **Not:** Fork depoları üst dominin alt etki alanı altında otomatik rotalar alır: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Fork'lar için özel alan adları atlanır.

## Servisleri Başlatma

Depoyu bağlayın ve tüm servisleri başlatın:

```bash
rdc repo up --name my-app -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--skip-router-restart` | İşlem sonrasında rota sunucusunun yeniden başlatılmasını atla |

Çalıştırma sırası:
1. LUKS ile şifrelenmiş depoyu bağla (bağlı değilse otomatik bağlanır)
2. İzole Docker daemon'unu başlat
3. Compose dosyalarından `.rediacc.json` dosyasını otomatik oluştur
4. Tüm Rediaccfile'larda `up()` çalıştır (A-Z sırası)

Dağıtım sonrasında çıktıda her servisin gerçek URL'lerini gösteren bir **PROXY ROUTES** bölümü yer alır. Özel Traefik etiketlerine sahip servisler özel etki alanlarını birincil URL olarak gösterir:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

## Servisleri Durdurma

```bash
rdc repo down --name my-app -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--unmount` | Durdurduktan sonra şifrelenmiş depoyu ayır. Bu etkili olmazsa, `rdc repo unmount` komutunu ayrıca kullanın. |
| `--skip-router-restart` | İşlem sonrasında rota sunucusunun yeniden başlatılmasını atla |

Çalıştırma sırası:
1. Tüm Rediaccfile'larda `down()` çalıştır (Z-A ters sıra, en iyi çaba)
2. İzole Docker daemon'unu durdur (`--unmount` ise)
3. LUKS ile şifrelenmiş birimi ayır ve kapat (`--unmount` ise)

## Toplu İşlemler

Bir makinedeki tüm depoları aynı anda başlatın veya durdurun:

```bash
rdc repo up -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--include-forks` | Çatallanmış depoları dahil et |
| `--mount-only` | Yalnızca bağla, konteynerleri başlatma |
| `--dry-run` | Ne yapılacağını göster |
| `--parallel` | İşlemleri paralel çalıştır |
| `--concurrency <n>` | Maksimum eşzamanlı işlem sayısı (varsayılan: 3) |
| `--skip-router-restart` | İşlem sonrasında rota sunucusunun yeniden başlatılmasını atla |

## Önyükleme Sırasında Otomatik Başlatma

Varsayılan olarak, bir sunucu yeniden başlatıldıktan sonra depoların manuel olarak bağlanması ve başlatılması gerekir. **Otomatik başlatma**, depoların sunucu açılışında otomatik olarak bağlanmasını, Docker'ın başlatılmasını ve Rediaccfile `up()` fonksiyonunun çalıştırılmasını yapılandırır.

### Nasıl Çalışır

Bir depo için otomatik başlatmayı etkinleştirdiğinizde:

1. 256 baytlık rastgele bir LUKS anahtar dosyası oluşturulur ve deponun LUKS slot 1'ine eklenir (slot 0, kullanıcı parolası olarak kalır)
2. Anahtar dosyası, `{datastore}/.credentials/keys/{guid}.key` konumunda `0600` izinleriyle (yalnızca root) saklanır
3. Açılışta tüm etkinleştirilmiş depoları bağlayan ve servislerini başlatan bir systemd servisi (`rediacc-autostart`) kurulur

Sistem kapatma veya yeniden başlatma sırasında, servis tüm servisleri düzgün bir şekilde durdurur (Rediaccfile `down()`), Docker daemon'larını kapatır ve LUKS birimlerini kapatır.

> **Güvenlik notu:** Otomatik başlatmayı etkinleştirmek, sunucu diskinde bir LUKS anahtar dosyası saklar. Sunucuya root erişimi olan herkes, parola girmeden depoyu bağlayabilir. Bunu kendi tehdit modelinize göre değerlendirin.

### Etkinleştirme

```bash
rdc repo autostart enable --name my-app -m server-1
```

Depo parolası sorulacaktır.

### Tümünü Etkinleştirme

```bash
rdc repo autostart enable -m server-1
```

### Devre Dışı Bırakma

```bash
rdc repo autostart disable --name my-app -m server-1
```

Bu, anahtar dosyasını kaldırır ve LUKS slot 1'i siler.

### Dağıtımda Anahtar Dosyası Yenileme

Otomatik başlatma etkinleştirildiğinde, `rdc repo up` komutu LUKS slot 1 anahtar dosyasını doğrular.
Diskteki anahtar dosyası hâlâ LUKS slotu ile eşleşiyorsa herhangi bir değişiklik yapılmaz.

`repo push` / `repo pull` aracılığıyla depo makineler arasında aktarıldıktan sonra
yeni makinedeki anahtar dosyası eşleşmeyecektir. Bu durumda `repo up` otomatik olarak
anahtar dosyasını yeniden oluşturur ve LUKS slot 1'i günceller. Şu günlük mesajlarını görürsünüz:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

Bu güvenlidir; slot 0 (parolanız) hiçbir zaman değiştirilmez. Otomatik başlatma etkin değilse,
kontrol sessizce atlanır. Hatalar kritik değildir ve dağıtımı engellemez.

### Durumu Listeleme

```bash
rdc repo autostart list -m server-1
```

## Tam Örnek

Bu örnek, PostgreSQL, Redis ve bir API sunucusu içeren bir web uygulamasını dağıtır.

### 1. Ortamı Hazırlama

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Depoyu Bağlama ve Hazırlama

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Uygulama Dosyalarını Oluşturma

Depo içinde aşağıdaki dosyaları oluşturun:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Başlatma

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Otomatik Başlatmayı Etkinleştirme

```bash
rdc repo autostart enable --name webapp -m prod-1
```
