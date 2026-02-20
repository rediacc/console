---
title: Servisler
description: >-
  Rediaccfile, servis agi, baslatma/durdurma ve otomatik baslatma ile
  konteynerlestirilmis servisleri dagitin ve yonetin.
category: Guides
order: 5
language: tr
sourceHash: 8add6342eea14e41
---

# Servisler

Hangi araci kullanacaginizdan emin degilseniz [rdc vs renet](/tr/docs/rdc-vs-renet) sayfasina bakin.

Bu sayfa, konteynerleştirilmiş servislerin nasıl dağıtılacağını ve yönetileceğini kapsar: Rediaccfile'lar, servis ağı, başlatma/durdurma, toplu işlemler ve otomatik başlatma.

## Rediaccfile

**Rediaccfile**, servislerinizin nasıl hazırlandığını, başlatıldığını ve durdurulduğunu tanımlayan bir Bash betiğidir. Dosya adı `Rediaccfile` veya `rediaccfile` (büyük/küçük harf duyarsız) olmalı ve deponun bağlı dosya sistemi içine yerleştirilmelidir.

Rediaccfile'lar iki konumda aranır:
1. Depo bağlama yolunun **kök dizini**
2. Bağlama yolunun **birinci seviye alt dizinleri** (özyinelemeli değil)

Gizli dizinler (`.` ile başlayan adlar) atlanır.

### Yaşam Döngüsü Fonksiyonları

Bir Rediaccfile en fazla üç fonksiyon içerir:

| Fonksiyon | Ne zaman çalışır | Amacı | Hata davranışı |
|-----------|-------------------|-------|----------------|
| `prep()` | `up()` öncesinde | Bağımlılıkları yükleme, imajları çekme, migrasyonları çalıştırma | **Hızlı başarısızlık** -- herhangi bir `prep()` başarısız olursa, tüm süreç derhal durur |
| `up()` | Tüm `prep()` tamamlandıktan sonra | Servisleri başlatma (ör. `docker compose up -d`) | Kök hatası **kritiktir** (her şeyi durdurur). Alt dizin hataları **kritik değildir** (günlüğe kaydedilir, devam eder) |
| `down()` | Durdurma sırasında | Servisleri durdurma (ör. `docker compose down`) | **En iyi çaba** -- hatalar günlüğe kaydedilir ancak tüm Rediaccfile'lar her zaman denenir |

Her üç fonksiyon da isteğe bağlıdır. Tanımlanmamış fonksiyonlar sessizce atlanır.

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

`{SERVICE}_IP` değişkenleri `.rediacc.json` dosyasından otomatik olarak oluşturulur. Adlandırma kuralı, servis adını büyük harfe çevirir, tireleri alt çizgi ile değiştirir ve sonuna `_IP` ekler. Örneğin, `listmonk-app` servisi `LISTMONK_APP_IP` olur.

> **Uyarı: Rediaccfile'larda `sudo docker` kullanmayın.** `sudo` komutu ortam değişkenlerini sıfırlar, bu da `DOCKER_HOST` değişkeninin kaybolmasına ve Docker komutlarının deponun izole daemon'u yerine sistem daemon'unu hedeflemesine neden olur. Bu, konteyner izolasyonunu bozar ve port çakışmalarına yol açabilir. Rediacc, `-E` olmadan `sudo docker` algılarsa çalıştırmayı engeller.
>
> Rediaccfile'larınızda `renet compose` kullanın -- bu, `DOCKER_HOST` değişkenini otomatik olarak yönetir, yönlendirme keşfi için ağ etiketlerini enjekte eder ve servis ağını yapılandırır. Servislerin ters proxy aracılığıyla nasıl sunulduğuna dair ayrıntılar için [Ağ Yapılandırması](/tr/docs/networking) sayfasına bakın. Docker'ı doğrudan çağırıyorsanız, `sudo` olmadan `docker` kullanın -- Rediaccfile fonksiyonları zaten yeterli yetkiyle çalışır. sudo kullanmanız gerekiyorsa, ortam değişkenlerini korumak için `sudo -E docker` kullanın.

### Örnek

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `DOCKER_HOST` otomatik olarak ayarlandığı için `docker compose` de çalışır, ancak `renet compose` ters proxy yönlendirme keşfi için gereken `rediacc.*` etiketlerini de enjekte ettiği için tercih edilir. Ayrıntılar için [Ağ Yapılandırması](/tr/docs/networking) sayfasına bakın.

### Çoklu Servis Düzeni

Birden fazla bağımsız servis grubu olan projeler için alt dizinler kullanın:

```
/mnt/rediacc/repos/my-app/
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

**Örnek**: Ağ kimliği `2816` (`0x0B00`) için, temel adres `127.0.11.0`:

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

## Servisleri Başlatma

Depoyu bağlayın ve tüm servisleri başlatın:

```bash
rdc repo up my-app -m server-1 --mount
```

| Seçenek | Açıklama |
|---------|----------|
| `--mount` | Henüz bağlanmamışsa önce depoyu bağla |
| `--prep-only` | Yalnızca `prep()` fonksiyonlarını çalıştır, `up()` atla |

Çalıştırma sırası:
1. LUKS ile şifrelenmiş depoyu bağla (`--mount` belirtilmişse)
2. İzole Docker daemon'unu başlat
3. Compose dosyalarından `.rediacc.json` dosyasını otomatik oluştur
4. Tüm Rediaccfile'larda `prep()` çalıştır (A-Z sırası, hızlı başarısızlık)
5. Tüm Rediaccfile'larda `up()` çalıştır (A-Z sırası)

## Servisleri Durdurma

```bash
rdc repo down my-app -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--unmount` | Durdurduktan sonra şifrelenmiş depoyu ayır |

Çalıştırma sırası:
1. Tüm Rediaccfile'larda `down()` çalıştır (Z-A ters sıra, en iyi çaba)
2. İzole Docker daemon'unu durdur (`--unmount` ise)
3. LUKS ile şifrelenmiş birimi ayır ve kapat (`--unmount` ise)

## Toplu İşlemler

Bir makinedeki tüm depoları aynı anda başlatın veya durdurun:

```bash
rdc repo up-all -m server-1
```

| Seçenek | Açıklama |
|---------|----------|
| `--include-forks` | Çatallanmış depoları dahil et |
| `--mount-only` | Yalnızca bağla, konteynerleri başlatma |
| `--dry-run` | Ne yapılacağını göster |
| `--parallel` | İşlemleri paralel çalıştır |
| `--concurrency <n>` | Maksimum eşzamanlı işlem sayısı (varsayılan: 3) |

## Önyükleme Sırasında Otomatik Başlatma

Varsayılan olarak, bir sunucu yeniden başlatıldıktan sonra depoların manuel olarak bağlanması ve başlatılması gerekir. **Otomatik başlatma**, depoların sunucu açılışında otomatik olarak bağlanmasını, Docker'ın başlatılmasını ve Rediaccfile `up()` fonksiyonunun çalıştırılmasını yapılandırır.

### Nasıl Çalışır

Bir depo için otomatik başlatmayı etkinleştirdiğinizde:

1. 256 baytlık rastgele bir LUKS anahtar dosyası oluşturulur ve deponun LUKS slot 1'ine eklenir (slot 0, kullanıcı parolası olarak kalır)
2. Anahtar dosyası, `{datastore}/.credentials/keys/{guid}.key` konumunda `0600` izinleriyle (yalnızca root) saklanır
3. Açılışta tüm etkinleştirilmiş depoları bağlayan ve servislerini başlatan bir systemd servisi (`rediacc-autostart`) kurulur

Sistem kapatma veya yeniden başlatma sırasında, servis tüm servisleri düzgün bir şekilde durdurur (Rediaccfile `down()`), Docker daemon'larını kapatır ve LUKS birimlerini kapatır.

> **Güvenlik notu:** Otomatik başlatmayı etkinleştirmek, sunucu diskinde bir LUKS anahtar dosyası saklar. Sunucuya root erişimi olan herkes, parola girmeden depoyu bağlayabilir. Bu, kolaylık (otomatik açılış) ve güvenlik (manuel parola girişi gerektirme) arasında bir ödünleşimdir. Bunu kendi tehdit modelinize göre değerlendirin.

### Etkinleştirme

```bash
rdc repo autostart enable my-app -m server-1
```

Depo parolası sorulacaktır.

### Tümünü Etkinleştirme

```bash
rdc repo autostart enable-all -m server-1
```

### Devre Dışı Bırakma

```bash
rdc repo autostart disable my-app -m server-1
```

Bu, anahtar dosyasını kaldırır ve LUKS slot 1'i siler.

### Durumu Listeleme

```bash
rdc repo autostart list -m server-1
```

## Tam Örnek

Bu örnek, PostgreSQL, Redis ve bir API sunucusu içeren bir web uygulamasını dağıtır.

### 1. Ortamı Hazırlama

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Depoyu Bağlama ve Hazırlama

```bash
rdc repo mount webapp -m prod-1
```

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
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
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
    renet compose -- down
}
```

### 4. Başlatma

```bash
rdc repo up webapp -m prod-1
```

### 5. Otomatik Başlatmayı Etkinleştirme

```bash
rdc repo autostart enable webapp -m prod-1
```
