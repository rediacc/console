---
title: "Geçiş Rehberi"
description: "Mevcut projeleri şifrelenmiş Rediacc depolarına taşıyın."
category: "Guides"
order: 11
language: tr
---

# Geçiş Rehberi

Mevcut bir projeyi — dosyalar, Docker servisleri, veritabanları — geleneksel bir sunucudan veya yerel geliştirme ortamından şifrelenmiş bir Rediacc deposuna taşıyın.

## Ön Koşullar

- `rdc` CLI kurulu ([Kurulum](/tr/docs/installation))
- Bir makine eklenmiş ve hazırlanmış ([Kurulum](/tr/docs/setup))
- Sunucuda projeniz için yeterli disk alanı (`rdc machine status` ile kontrol edin)

## Adım 1: Depo Oluşturma

Projenize uygun boyutta şifrelenmiş bir depo oluşturun. Docker imajları ve konteyner verileri için ek alan ayırın.

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **İpucu:** Daha sonra `rdc repo resize` ile yeniden boyutlandırabilirsiniz, ancak deponun önce bağlantısının kesilmesi gerekir. Yeterli alanla başlamak daha kolaydır.

## Adım 2: Dosyalarınızı Yükleme

Proje dosyalarınızı depoya aktarmak için `rdc sync upload` kullanın.

```bash
# Ne aktarılacağını önizleyin (değişiklik yapılmaz)
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Dosyaları yükleyin
rdc sync upload -m server-1 -r my-project --local ./my-project
```

Yüklemeden önce depo bağlı olmalıdır. Henüz bağlı değilse:

```bash
rdc repo mount my-project -m server-1
```

Uzak dizinin yerel dizininizle tam olarak eşleşmesini istediğiniz sonraki senkronizasyonlar için:

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> `--mirror` bayrağı, yerel olarak bulunmayan uzak dosyaları siler. Doğrulamak için önce `--dry-run` kullanın.

## Adım 3: Dosya Sahipliğini Düzeltme

Yüklenen dosyalar yerel kullanıcınızın UID'si ile gelir (örn. 1000). Rediacc, VS Code, terminal oturumları ve araçların tutarlı erişime sahip olması için evrensel bir kullanıcı (UID 7111) kullanır. Dönüştürmek için sahiplik komutunu çalıştırın:

```bash
rdc repo ownership my-project -m server-1
```

### Docker-Duyarlı İstisna

Docker konteynerleri çalışıyorsa (veya çalıştıysa), sahiplik komutu otomatik olarak yazılabilir veri dizinlerini algılar ve **atlar**. Bu, dosyalarını farklı UID'lerle yöneten konteynerlerin bozulmasını önler (örn. MariaDB UID 999, Nextcloud UID 33 kullanır).

Komut ne yaptığını raporlar:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Ne Zaman Çalıştırılmalı

- **Dosyaları yükledikten sonra** — yerel UID'nizi 7111'e dönüştürmek için
- **Konteynerleri başlattıktan sonra** — Docker birim dizinlerinin otomatik olarak hariç tutulmasını istiyorsanız. Konteynerler henüz başlatılmadıysa, hariç tutulacak birim yoktur ve tüm dizinler değiştirilir (bu normaldir — konteynerler ilk başlatmada verilerini yeniden oluşturur)

### Zorunlu Mod

Docker birim algılamasını atlayıp konteyner veri dizinleri dahil her şeyi değiştirmek için:

```bash
rdc repo ownership my-project -m server-1 --force
```

> **Uyarı:** Bu, çalışan konteynerleri bozabilir. Gerekirse önce `rdc repo down` ile durdurun.

### Özel UID

Varsayılan 7111 dışında bir UID ayarlamak için:

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## Adım 4: Rediaccfile Kurulumu

Proje kök dizininizde bir `Rediaccfile` oluşturun. Bu Bash betiği, servislerinizin nasıl hazırlanacağını, başlatılacağını ve durdurulacağını tanımlar.

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

Üç yaşam döngüsü fonksiyonu:

| Fonksiyon | Amaç | Hata Davranışı |
|-----------|------|----------------|
| `prep()` | İmajları çekme, migrasyon çalıştırma, bağımlılıkları yükleme | Hızlı başarısızlık: herhangi bir hata her şeyi durdurur |
| `up()` | Servisleri başlatma | Kök başarısızlığı kritiktir; alt dizin başarısızlıkları günlüğe kaydedilir ve devam eder |
| `down()` | Servisleri durdurma | En iyi çaba: her zaman hepsini dener |

> **Önemli:** Rediaccfile'ınızda `docker` komutunu doğrudan kullanın — asla `sudo docker` kullanmayın. `sudo` komutu ortam değişkenlerini sıfırlar, bu da `DOCKER_HOST`'un kaybolmasına ve konteynerlerin deponun izole daemon'u yerine sistem Docker daemon'unda oluşturulmasına neden olur. Rediaccfile fonksiyonları zaten yeterli ayrıcalıklarla çalışır. Ayrıntılar için [Servisler](/tr/docs/services#environment-variables) bölümüne bakın.

Rediaccfile'lar, çoklu servis düzenleri ve yürütme sırası hakkında tam ayrıntılar için [Servisler](/tr/docs/services) bölümüne bakın.

## Adım 5: Servis Ağını Yapılandırma

Rediacc, depo başına izole bir Docker daemon'u çalıştırır. Servisler `network_mode: host` kullanır ve benzersiz geri döngü IP'lerine bağlanır, böylece depolar arasında çakışma olmadan standart portları kullanabilirler.

### docker-compose.yml Dosyanızı Uyarlama

**Önce (geleneksel):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Sonra (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

Temel değişiklikler:

1. **Her servise `network_mode: host` ekleyin**
2. **`ports:` eşlemelerini kaldırın** (host ağında gerekli değil)
3. **Servisleri `${SERVICE_IP}` ortam değişkenlerine bağlayın** (Rediacc tarafından otomatik enjekte edilir)
4. **Diğer servislere Docker DNS adları yerine IP'leriyle başvurun** (örn. `postgres` yerine `${POSTGRES_IP}`)

`{SERVICE}_IP` değişkenleri compose dosyanızdaki servis adlarından otomatik olarak oluşturulur. Adlandırma kuralı: büyük harf, tireler alt çizgiyle değiştirilir, `_IP` son eki. Örneğin, `listmonk-app` `LISTMONK_APP_IP` olur.

IP ataması ve `.rediacc.json` hakkında ayrıntılar için [Servis Ağı](/tr/docs/services#service-networking-rediaccjson) bölümüne bakın.

## Adım 6: Servisleri Başlatma

Depoyu bağlayın (henüz bağlı değilse) ve tüm servisleri başlatın:

```bash
rdc repo up my-project -m server-1 --mount
```

Bu işlem:
1. Şifrelenmiş depoyu bağlar
2. İzole Docker daemon'unu başlatır
3. Servis IP atamalarıyla `.rediacc.json` dosyasını otomatik oluşturur
4. Tüm Rediaccfile'lardan `prep()` fonksiyonunu çalıştırır
5. Tüm Rediaccfile'lardan `up()` fonksiyonunu çalıştırır

Konteynerlerinizin çalıştığını doğrulayın:

```bash
rdc machine containers server-1
```

## Adım 7: Otomatik Başlatmayı Etkinleştirme (İsteğe Bağlı)

Varsayılan olarak, sunucu yeniden başlatıldıktan sonra depolar manuel olarak bağlanmalı ve başlatılmalıdır. Servislerinizin otomatik olarak başlaması için otomatik başlatmayı etkinleştirin:

```bash
rdc repo autostart enable my-project -m server-1
```

Depo parolası sorulacaktır.

> **Güvenlik notu:** Otomatik başlatma, sunucuda bir LUKS anahtar dosyası depolar. Root erişimi olan herkes depoyu parola olmadan bağlayabilir. Ayrıntılar için [Otomatik Başlatma](/tr/docs/services#autostart-on-boot) bölümüne bakın.

## Yaygın Geçiş Senaryoları

### WordPress / PHP ve Veritabanı

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress dosyaları (çalışırken UID 33)
├── database/data/          # MariaDB verileri (çalışırken UID 999)
└── wp-content/uploads/     # Kullanıcı yüklemeleri
```

1. Proje dosyalarınızı yükleyin
2. Önce servisleri başlatın (`rdc repo up`) böylece konteynerler veri dizinlerini oluştursun
3. Sahiplik düzeltmesini çalıştırın — MariaDB ve uygulama veri dizinleri otomatik olarak hariç tutulur

### Node.js / Python ve Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Uygulama kaynak kodu
├── node_modules/           # Bağımlılıklar
└── redis-data/             # Redis kalıcılığı (çalışırken UID 999)
```

1. Projenizi yükleyin (`node_modules` hariç tutmayı ve `prep()` içinde çekmeyi düşünün)
2. Konteynerler başladıktan sonra sahiplik düzeltmesini çalıştırın

### Özel Docker Projesi

Docker servisleri olan herhangi bir proje için:

1. Proje dosyalarını yükleyin
2. `docker-compose.yml` dosyasını uyarlayın (Adım 5'e bakın)
3. Yaşam döngüsü fonksiyonlarıyla bir `Rediaccfile` oluşturun
4. Sahiplik düzeltmesini çalıştırın
5. Servisleri başlatın

## Sorun Giderme

### Yüklemeden Sonra Erişim Reddedildi

Dosyalar hâlâ yerel UID'nize sahip. Sahiplik komutunu çalıştırın:

```bash
rdc repo ownership my-project -m server-1
```

### Konteyner Başlamıyor

Servislerin `0.0.0.0` veya `localhost` yerine atanmış IP'lerine bağlandığını kontrol edin:

```bash
# Atanmış IP'leri kontrol edin
rdc term server-1 my-project -c "cat .rediacc.json"

# Konteyner günlüklerini kontrol edin
rdc term server-1 my-project -c "docker logs <container-name>"
```

### Depolar Arasında Port Çakışması

Her depo benzersiz geri döngü IP'leri alır. Port çakışmaları görüyorsanız, `docker-compose.yml` dosyanızın bağlama için `0.0.0.0` yerine `${SERVICE_IP}` kullandığını doğrulayın. `0.0.0.0`'a bağlı servisler tüm arayüzlerde dinler ve diğer depolarla çakışır.

### Sahiplik Düzeltmesi Konteynerleri Bozuyor

`rdc repo ownership --force` çalıştırdıysanız ve bir konteyner çalışmayı durdurduysa, konteynerin veri dosyaları değiştirilmiştir. Konteyneri durdurun, veri dizinini silin ve yeniden başlatın — konteyner onu yeniden oluşturacaktır:

```bash
rdc repo down my-project -m server-1
# Konteynerin veri dizinini silin (örn. database/data)
rdc repo up my-project -m server-1
```
