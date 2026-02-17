---
title: "Adım Adım Rehber"
description: "Rediacc'i yerel modda kullanarak kendi sunuculariniza sifrelenmis, izole altyapi dagitin."
category: "Guides"
order: 2
language: tr
---

# Adım Adım Rehber

Bu rehber, Rediacc'ı **yerel modda** kullanarak kendi sunucularınıza şifrelenmiş, izole altyapı dağıtma sürecini anlatır. Rehberin sonunda, uzak bir makinede konteynerleştirilmiş servisler çalıştıran, tamamen işlevsel bir depo (repository) elde edeceksiniz. Tüm yönetim iş istasyonunuzdan gerçekleştirilir.

Yerel mod, her şeyin sizin kontrol ettiğiniz altyapı üzerinde çalışması anlamına gelir. Bulut hesabı gerekmez, SaaS bağımlılığı yoktur. İş istasyonunuz, uzak sunucuları SSH üzerinden yönetir ve tüm durum bilgisi yerel makinenizde ve sunucuların kendisinde saklanır.

## Mimari Genel Bakış

Rediacc iki araçlı bir mimari kullanır:

```
İş İstasyonunuz                     Uzak Sunucu
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** iş istasyonunuzda (macOS veya Linux) çalışır. Yerel yapılandırmanızı okur, uzak makinelere SSH üzerinden bağlanır ve renet komutlarını çalıştırır.
- **renet** uzak sunucuda root yetkileriyle çalışır. LUKS ile şifrelenmiş disk imajlarını, izole Docker daemon'larını, servis orkestrasyonunu ve ters proxy yapılandırmasını yönetir.

Yerel olarak yazdığınız her komut, uzak makinede renet'i çalıştıran bir SSH çağrısına dönüştürülür. Sunuculara manuel olarak SSH bağlantısı yapmanız gerekmez.

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

> Birden fazla bağlamınız olabilir (örn., `production`, `staging`, `dev`). Herhangi bir komutta `--context` bayrağıyla bunlar arasında geçiş yapabilirsiniz.

## Adım 2: Makine Ekleme

Uzak sunucunuzu bağlama makine olarak kaydedin:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Seçenek | Gerekli | Varsayılan | Açıklama |
|---------|---------|------------|----------|
| `--ip <address>` | Evet | - | Uzak sunucunun IP adresi veya ana bilgisayar adı. |
| `--user <username>` | Evet | - | Uzak sunucudaki SSH kullanıcı adı. |
| `--port <port>` | Hayır | `22` | SSH portu. |
| `--datastore <path>` | Hayır | `/mnt/rediacc` | Rediacc'ın şifrelenmiş depoları sakladığı sunucu üzerindeki dizin yolu. |

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
3. Veri deposu dizinini oluşturur ve şifrelenmiş depolar için hazırlar

| Seçenek | Gerekli | Varsayılan | Açıklama |
|---------|---------|------------|----------|
| `--datastore <path>` | Hayır | `/mnt/rediacc` | Sunucudaki veri deposu dizini. |
| `--datastore-size <size>` | Hayır | `95%` | Veri deposu için ayrılacak disk alanı miktarı. |
| `--debug` | Hayır | `false` | Sorun giderme için ayrıntılı çıktıyı etkinleştirir. |

> Hazırlık her makine için yalnızca bir kez çalıştırılmalıdır. Gerektiğinde tekrar çalıştırmak güvenlidir.

## Adım 4: Depo Oluşturma

Bir **depo** (repository), uzak sunucudaki LUKS ile şifrelenmiş bir disk imajıdır. Bağlandığında şunları sağlar:
- Uygulama verileriniz için izole bir dosya sistemi
- Özel bir Docker daemon'u (ana bilgisayarın Docker'ından ayrı)
- /26 alt ağı içinde her servis için benzersiz loopback IP'leri

Bir depo oluşturun:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `-m, --machine <name>` | Evet | Deponun oluşturulacağı hedef makine. |
| `--size <size>` | Evet | Şifrelenmiş disk imajının boyutu (örn., `5G`, `10G`, `50G`). |

Çıktıda otomatik olarak oluşturulan üç değer gösterilir:

- **Depo GUID'i** -- Sunucudaki şifrelenmiş disk imajını tanımlayan bir UUID.
- **Kimlik Bilgisi** (Credential) -- LUKS birimini şifrelemek/çözmek için kullanılan rastgele bir parola.
- **Ağ Kimliği** (Network ID) -- Bu deponun servislerinin IP alt ağını belirleyen bir tamsayı (2816'dan başlar, 64'er artar).

> **Kimlik bilgisini güvenli bir şekilde saklayın.** Bu, deponuzun şifreleme anahtarıdır. Kaybedilmesi durumunda veriler kurtarılamaz. Kimlik bilgisi yerel `config.json` dosyanızda saklanır ancak sunucuda saklanmaz.

## Adım 5: Rediaccfile

**Rediaccfile**, servislerinizin nasıl hazırlandığını, başlatıldığını ve durdurulduğunu tanımlayan bir Bash betiğidir. Servis yaşam döngüsü yönetiminin temel mekanizmasıdır.

### Rediaccfile Nedir?

Rediaccfile, en fazla üç fonksiyon içeren düz bir Bash betiğidir: `prep()`, `up()` ve `down()`. Dosya adı `Rediaccfile` veya `rediaccfile` (büyük/küçük harf duyarsız) olmalı ve deponun bağlı dosya sistemi içine yerleştirilmelidir.

Rediaccfile'lar iki konumda aranır:
1. Depo bağlama yolunun **kök dizini**
2. Bağlama yolunun **birinci seviye alt dizinleri** (özyinelemeli değil)

Gizli dizinler (`.` ile başlayan adlar) atlanır.

### Yaşam Döngüsü Fonksiyonları

| Fonksiyon | Ne zaman çalışır | Amacı | Hata davranışı |
|-----------|-------------------|-------|----------------|
| `prep()` | `up()` öncesinde | Bağımlılıkları yükleme, imajları çekme, migrasyonları çalıştırma | **Hızlı başarısızlık** -- herhangi bir `prep()` başarısız olursa, tüm süreç derhal durur. |
| `up()` | Tüm `prep()` tamamlandıktan sonra | Servisleri başlatma (örn., `docker compose up -d`) | Kök Rediaccfile hatası **kritiktir** (her şeyi durdurur). Alt dizin hataları **kritik değildir** (günlüğe kaydedilir, sonrakine devam eder). |
| `down()` | Durdurma sırasında | Servisleri durdurma (örn., `docker compose down`) | **En iyi çaba** -- hatalar günlüğe kaydedilir ancak tüm Rediaccfile'lar her zaman denenir. |

Her üç fonksiyon da isteğe bağlıdır. Bir Rediaccfile'da tanımlanmamış fonksiyonlar sessizce atlanır.

### Çalıştırma Sırası

- **Başlatma (`up`):** Önce kök Rediaccfile, ardından alt dizinler **alfabetik sıraya** göre (A'dan Z'ye).
- **Durdurma (`down`):** Alt dizinler **ters alfabetik sıraya** göre (Z'den A'ya), ardından en son kök dizin.

### Ortam Değişkenleri

Bir Rediaccfile fonksiyonu çalıştığında, aşağıdaki ortam değişkenleri kullanılabilir:

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `REPOSITORY_PATH` | Deponun bağlama yolu | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | Depo GUID'i | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | Ağ Kimliği (tamsayı) | `2816` |
| `DOCKER_HOST` | Bu deponun izole daemon'u için Docker soketi | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json` dosyasında tanımlanan her servis için loopback IP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP` değişkenleri `.rediacc.json` dosyasından otomatik olarak oluşturulur (bkz. Adım 6). Adlandırma kuralı, servis adını büyük harfe çevirir, tireleri alt çizgi ile değiştirir ve sonuna `_IP` ekler. Örneğin, `listmonk-app` servisi `LISTMONK_APP_IP` olur.

### Örnek Rediaccfile

Bir web uygulaması için basit bir Rediaccfile:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### Çoklu Servis Örneği

Birden fazla bağımsız servis grubu olan projeler için alt dizinler kullanın:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Kök: paylaşılan kurulum (örn., Docker ağları oluşturma)
├── docker-compose.yml       # Kök compose dosyası
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

## Adım 6: Servis Ağ Yapılandırması (.rediacc.json)

Her depo, `127.x.x.x` loopback aralığında bir /26 alt ağı (64 IP) alır. Servisler benzersiz loopback IP'lerine bağlanır, böylece çakışma olmadan aynı portlarda çalışabilirler. Örneğin, iki PostgreSQL örneği her biri farklı bir IP üzerinde port 5432'yi dinleyebilir.

### .rediacc.json Dosyası

`.rediacc.json` dosyası, servis adlarını **slot** numaralarıyla eşler. Her slot, deponun alt ağı içinde benzersiz bir IP adresine karşılık gelir.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Servisler alfabetik sıraya göre yazılır.

### Docker Compose'dan Otomatik Oluşturma

`.rediacc.json` dosyasını manuel olarak oluşturmanız gerekmez. `rdc repo up` komutunu çalıştırdığınızda Rediacc otomatik olarak:

1. Rediaccfile içeren tüm dizinleri compose dosyaları (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` veya `compose.yaml`) için tarar.
2. Her compose dosyasının `services:` bölümünden servis adlarını çıkarır.
3. Yeni servislere bir sonraki kullanılabilir slotu atar.
4. Sonucu `{repository}/.rediacc.json` dosyasına kaydeder.

### IP Hesaplama

Bir servisin IP'si, deponun ağ kimliğinden ve servisin slotundan hesaplanır. Ağ kimliği, `127.x.y.z` loopback adresinin ikinci, üçüncü ve dördüncü oktetlerine dağıtılır. Her servis, ağ kimliğine `slot + 2` ofseti eklenerek bir adres alır (ofset 0 ve 1, ağ adresi ve ağ geçidi için ayrılmıştır).

Örneğin, ağ kimliği `2816` (`0x0B00`) ile temel adres `127.0.11.0` olur ve servisler `127.0.11.2`'den başlar.

**Örnek**: Ağ kimliği `2816` için:

| Servis | Slot | IP Adresi |
|--------|------|-----------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Her depo en fazla **61 servisi** destekler (slot 0'dan 60'a kadar).

### Docker Compose'da Servis IP'lerini Kullanma

Her depo izole bir Docker daemon'u çalıştırdığından, servisler `network_mode: host` kullanır ve atanan loopback IP'lerine bağlanır:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

`${POSTGRES_IP}` ve `${API_IP}` değişkenleri, Rediaccfile çalıştığında `.rediacc.json` dosyasından otomatik olarak dışa aktarılır.

## Adım 7: Servisleri Başlatma

Depoyu bağlayın ve tüm servisleri başlatın:

```bash
rdc repo up my-app -m server-1 --mount
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `-m, --machine <name>` | Evet | Hedef makine. |
| `--mount` | Hayır | Henüz bağlanmamışsa önce depoyu bağla. Bu bayrak olmadan deponun zaten bağlı olması gerekir. |
| `--prep-only` | Hayır | Yalnızca `prep()` fonksiyonlarını çalıştır, `up()` atla. İmajları önceden çekmek veya migrasyonları çalıştırmak için kullanışlıdır. |

Çalıştırma sırası:

1. LUKS ile şifrelenmiş depoyu bağla (`--mount` belirtilmişse)
2. Bu depo için izole Docker daemon'unu başlat
3. Compose dosyalarından `.rediacc.json` dosyasını otomatik oluştur
4. Tüm Rediaccfile'larda `prep()` çalıştır (A-Z sırası, hızlı başarısızlık)
5. Tüm Rediaccfile'larda `up()` çalıştır (A-Z sırası)

## Adım 8: Servisleri Durdurma

Bir depodaki tüm servisleri durdurun:

```bash
rdc repo down my-app -m server-1
```

| Seçenek | Gerekli | Açıklama |
|---------|---------|----------|
| `-m, --machine <name>` | Evet | Hedef makine. |
| `--unmount` | Hayır | Servisleri durdurduktan sonra şifrelenmiş depoyu ayır. Bu aynı zamanda izole Docker daemon'unu da durdurur ve LUKS birimini kapatır. |

Çalıştırma sırası:

1. Tüm Rediaccfile'larda `down()` çalıştır (Z-A ters sıra, en iyi çaba)
2. İzole Docker daemon'unu durdur (`--unmount` ise)
3. LUKS ile şifrelenmiş birimi ayır ve kapat (`--unmount` ise)

## Diğer Yaygın İşlemler

### Bağlama ve Ayırma (servisleri başlatmadan)

```bash
rdc repo mount my-app -m server-1     # Şifresini çöz ve bağla
rdc repo unmount my-app -m server-1   # Ayır ve tekrar şifrele
```

### Depo Durumunu Kontrol Etme

```bash
rdc repo status my-app -m server-1
```

### Tüm Depoları Listeleme

```bash
rdc repo list -m server-1
```

### Depoyu Yeniden Boyutlandırma

```bash
rdc repo resize my-app -m server-1 --size 20G    # Tam boyutu ayarla
rdc repo expand my-app -m server-1 --size 5G      # Mevcut boyuta 5G ekle
```

### Depoyu Silme

```bash
rdc repo delete my-app -m server-1
```

> Bu, şifrelenmiş disk imajını ve içindeki tüm verileri kalıcı olarak yok eder.

### Depoyu Çatallama (Fork)

Mevcut bir deponun güncel durumunun bir kopyasını oluşturun:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Bu, kendi GUID'i ve ağ kimliğine sahip yeni bir şifrelenmiş kopya oluşturur. Çatal (fork), üst depo ile aynı LUKS kimlik bilgisini paylaşır.

### Depoyu Doğrulama

Bir deponun dosya sistemi bütünlüğünü kontrol edin:

```bash
rdc repo validate my-app -m server-1
```

## Tam Örnek: Bir Web Uygulaması Dağıtma

Bu uçtan uca örnek, PostgreSQL, Redis ve bir API sunucusu içeren bir web uygulamasını dağıtır.

### 1. Ortamı Hazırlama

```bash
# rdc kurulumu
curl -fsSL https://get.rediacc.com | sh

# Yerel bağlam oluşturma
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Sunucunuzu kaydetme
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Sunucuyu hazırlama
rdc context setup-machine prod-1

# Şifrelenmiş bir depo oluşturma (10 GB)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Depoyu Bağlama ve Hazırlama

```bash
rdc repo mount webapp -m prod-1
```

SSH ile sunucuya bağlanın ve bağlanmış depo içinde uygulama dosyalarını oluşturun. Bağlama yolu çıktıda gösterilir (genellikle `/mnt/rediacc/repos/{guid}`).

### 3. Uygulama Dosyalarını Oluşturma

Depo içinde aşağıdaki dosyaları oluşturun:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. Her Şeyi Başlatma

```bash
rdc repo up webapp -m prod-1
```

Bu komut:
1. `api`, `postgres` ve `redis` için slotlarla `.rediacc.json` dosyasını otomatik oluşturur
2. Dizinleri oluşturmak ve imajları çekmek için `prep()` çalıştırır
3. Tüm konteynerleri başlatmak için `up()` çalıştırır

### 5. Otomatik Başlatmayı Etkinleştirme

```bash
rdc repo autostart enable webapp -m prod-1
```

Sunucu yeniden başlatıldıktan sonra depo otomatik olarak bağlanır ve tüm servisler başlatılır.
