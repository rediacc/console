---
title: Ağ
description: >-
  Ters proxy, Docker etiketleri, TLS sertifikaları, DNS ve TCP/UDP port
  yönlendirme ile servisleri dışarıya açın.
category: Guides
order: 6
language: tr
sourceHash: 47ee41d44be935a8
---

# Ağ

Bu sayfa, izole Docker daemon'larında çalışan servislerin internetten nasıl erişilebilir hale geldiğini açıklar. Ters proxy sistemi, yönlendirme için Docker etiketleri, TLS sertifikaları, DNS ve TCP/UDP port yönlendirmeyi kapsar.

Servislerin geri döngü IP'lerini nasıl aldığı ve `.rediacc.json` slot sistemi hakkında bilgi için [Servisler](/tr/docs/services#service-networking-rediaccjson) bölümüne bakın.

## Nasıl Çalışır

Rediacc, harici trafiği konteynerlere yönlendirmek için iki bileşenli bir proxy sistemi kullanır:

1. **Route server** — tüm depo Docker daemon'larındaki çalışan konteynerleri keşfeden bir systemd servisi. Konteyner etiketlerini inceler ve YAML uç noktası olarak sunulan yönlendirme yapılandırması oluşturur.
2. **Traefik** — route server'ı her 5 saniyede sorgulayan ve keşfedilen yönlendirmeleri uygulayan ters proxy. HTTP/HTTPS yönlendirme, TLS sonlandırma ve TCP/UDP yönlendirme işlemlerini yönetir.

Akış şu şekildedir:

```
İnternet → Traefik (portlar 80/443/TCP/UDP)
               ↓ her 5 saniyede sorgular
           Route Server (konteynerleri keşfeder)
               ↓ etiketleri inceler
           Docker Daemon'ları (/var/run/rediacc/docker-*.sock)
               ↓
           Konteynerler (127.x.x.x geri döngü IP'lerine bağlı)
```

Bir konteynere doğru etiketleri ekleyip `renet compose` ile başlattığınızda, otomatik olarak yönlendirilebilir hale gelir — manuel proxy yapılandırması gerekmez.

> The route server binary is kept in sync with your CLI version. When the CLI updates the renet binary on a machine, the route server is automatically restarted (~1–2 seconds). This causes no downtime — Traefik continues serving traffic with its last known configuration during the restart and picks up the new config on the next poll. Existing client connections are not affected. Your application containers are not touched.

## Docker Etiketleri

Yönlendirme, Docker konteyner etiketleri ile kontrol edilir. İki seviye vardır:

### Seviye 1: `rediacc.*` Etiketleri (Otomatik)

Bu etiketler, servisler başlatılırken `renet compose` tarafından **otomatik olarak enjekte edilir**. Manuel olarak eklemenize gerek yoktur.

| Etiket | Açıklama | Örnek |
|--------|----------|-------|
| `rediacc.service_name` | Servis kimliği | `myapp` |
| `rediacc.service_ip` | Atanmış geri döngü IP'si | `127.0.11.2` |
| `rediacc.network_id` | Deponun daemon ID'si | `2816` |
| `rediacc.tcp_ports` | TCP ports the service listens on | `8080,8443` |
| `rediacc.udp_ports` | UDP ports the service listens on | `53` |

Bir konteyner yalnızca `rediacc.*` etiketlerine sahipken (`traefik.enable=true` yokken), route server bir **otomatik yönlendirme** oluşturur:

```
{service}-{networkID}.{baseDomain}
```

Örneğin, ağ ID'si `2816` ve temel alan adı `example.com` olan bir depodaki `myapp` adlı servis şunu alır:

```
myapp-2816.example.com
```

Otomatik yönlendirmeler geliştirme ve dahili erişim için kullanışlıdır. Özel alan adlarına sahip üretim servisleri için Seviye 2 etiketlerini kullanın.

### Seviye 2: `traefik.*` Etiketleri (Kullanıcı Tanımlı)

Özel alan adı yönlendirmesi, TLS veya belirli giriş noktaları istediğinizde bu etiketleri `docker-compose.yml` dosyanıza ekleyin. `traefik.enable=true` ayarlamak, route server'a otomatik yönlendirme oluşturmak yerine özel kurallarınızı kullanmasını söyler.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Bunlar standart [Traefik v3 etiket sözdizimini](https://doc.traefik.io/traefik/routing/providers/docker/) kullanır.

> **İpucu:** Yalnızca dahili servisler (veritabanları, önbellekler, mesaj kuyrukları) `traefik.enable=true` **içermemelidir**. Yalnızca otomatik olarak enjekte edilen `rediacc.*` etiketlerine ihtiyaç duyarlar.

## HTTP/HTTPS Servislerini Dışarıya Açma

### Ön Koşullar

1. Makinede yapılandırılmış altyapı ([Makine Kurulumu — Altyapı Yapılandırması](/tr/docs/setup#infrastructure-configuration)):

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. Alan adınızı sunucunun genel IP'sine yönlendiren DNS kayıtları (aşağıdaki [DNS Yapılandırması](#dns-yapılandırması) bölümüne bakın).

### Etiket Ekleme

Dışarıya açmak istediğiniz servislere `docker-compose.yml` dosyanızda `traefik.*` etiketleri ekleyin:

```yaml
services:
  myapp:
    image: myapp:latest
    network_mode: host
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    network_mode: host
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # Traefik etiketi yok — veritabanı yalnızca dahili
```

| Etiket | Amaç |
|--------|------|
| `traefik.enable=true` | Bu konteyner için özel Traefik yönlendirmesini etkinleştirir |
| `traefik.http.routers.{name}.rule` | Yönlendirme kuralı — genellikle `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Hangi portlarda dinleneceği: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Sertifika çözümleyici — otomatik Let's Encrypt için `letsencrypt` kullanın |
| `traefik.http.services.{name}.loadbalancer.server.port` | Uygulamanızın konteyner içinde dinlediği port |

Etiketlerdeki `{name}` rastgele bir tanımlayıcıdır — sadece ilgili router/service/middleware etiketleri arasında tutarlı olması yeterlidir.

> **Not:** `rediacc.*` etiketleri (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) `renet compose` tarafından otomatik olarak enjekte edilir. Compose dosyanıza eklemenize gerek yoktur.

## TLS Sertifikaları

TLS sertifikaları, Cloudflare DNS-01 doğrulaması kullanılarak Let's Encrypt aracılığıyla otomatik olarak alınır. Bu, altyapı kurulumu sırasında bir kez yapılandırılır:

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Bir servis `traefik.http.routers.{name}.tls.certresolver=letsencrypt` etiketine sahip olduğunda, Traefik otomatik olarak:
1. Let's Encrypt'ten bir sertifika talep eder
2. Cloudflare DNS üzerinden alan adı sahipliğini doğrular
3. Sertifikayı yerel olarak saklar
4. Süresi dolmadan yeniler

Cloudflare DNS API token'ının, güvence altına almak istediğiniz alan adları için `Zone:DNS:Edit` iznine sahip olması gerekir. Bu yaklaşım, joker sertifikalar dahil Cloudflare tarafından yönetilen herhangi bir alan adı için çalışır.

## TCP/UDP Port Yönlendirme

HTTP dışı protokoller (posta sunucuları, DNS, dışarıya açılan veritabanları) için TCP/UDP port yönlendirme kullanın.

### Adım 1: Portları Kaydetme

Altyapı yapılandırması sırasında gerekli portları ekleyin:

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

Bu, `tcp-{port}` ve `udp-{port}` adlı Traefik giriş noktaları oluşturur.

### Plain TCP Example (Database)

To expose a database externally without TLS passthrough (Traefik forwards raw TCP):

```yaml
services:
  postgres:
    image: postgres:17
    network_mode: host
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 is pre-configured (see below), so no `--tcp-ports` setup is needed.

> **Security note:** Exposing a database to the internet is a risk. Use this only when remote clients need direct access. For most setups, keep the database internal and connect through your application.

> Port ekledikten veya kaldırdıktan sonra, proxy yapılandırmasını güncellemek için her zaman `rdc context push-infra` komutunu yeniden çalıştırın.

### Adım 2: TCP/UDP Etiketleri Ekleme

Compose dosyanızda `traefik.tcp.*` veya `traefik.udp.*` etiketlerini kullanın:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993) — TLS geçişi
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Temel kavramlar:
- **`HostSNI(\`*\`)`** herhangi bir ana bilgisayar adıyla eşleşir (düz SMTP gibi SNI göndermeyen protokoller için)
- **`tls.passthrough=true`** Traefik'in ham TLS bağlantısını şifresini çözmeden ilettiği anlamına gelir — uygulama TLS'yi kendisi yönetir
- Giriş noktası adları `tcp-{port}` veya `udp-{port}` kuralını takip eder

### Önceden Yapılandırılmış Portlar

Aşağıdaki TCP/UDP portları varsayılan olarak giriş noktalarına sahiptir (`--tcp-ports` ile eklemeye gerek yoktur):

| Port | Protokol | Yaygın Kullanım |
|------|----------|-----------------|
| 80 | HTTP | Web (HTTPS'ye otomatik yönlendirme) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000–10010 | TCP | Dinamik aralık (otomatik atama) |

## DNS Yapılandırması

Alan adlarınızı `set-infra` ile yapılandırılan sunucunun genel IP adreslerine yönlendirin:

### Bireysel Servis Alan Adları

Her servis için A (IPv4) ve/veya AAAA (IPv6) kayıtları oluşturun:

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### Otomatik Yönlendirmeler İçin Joker

Otomatik yönlendirmeleri (Seviye 1) kullanıyorsanız, bir joker DNS kaydı oluşturun:

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

Bu, tüm alt alan adlarını sunucunuza yönlendirir ve Traefik bunları `Host()` kuralına veya otomatik yönlendirme ana bilgisayar adına göre doğru servisle eşleştirir.

## Ara Yazılımlar

Traefik ara yazılımları istekleri ve yanıtları değiştirir. Etiketler aracılığıyla uygulayın.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Büyük Dosya Yükleme Tamponlama

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Birden Fazla Ara Yazılım

Ara yazılımları virgülle ayırarak zincirleyin:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Kullanılabilir ara yazılımların tam listesi için [Traefik ara yazılım belgelerine](https://doc.traefik.io/traefik/middlewares/overview/) bakın.

## Tanılama

Bir servis erişilebilir değilse, sunucuya SSH ile bağlanın ve route server uç noktalarını kontrol edin:

### Sağlık Kontrolü

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Genel durumu, keşfedilen yönlendirici ve servis sayısını ve otomatik yönlendirmelerin etkin olup olmadığını gösterir.

### Keşfedilen Yönlendirmeler

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Kuralları, giriş noktaları ve arka uç servisleriyle birlikte tüm HTTP, TCP ve UDP yönlendiricileri listeler.

### Port Atamaları

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Dinamik olarak atanan portlar için TCP ve UDP port eşlemelerini gösterir.

### Yaygın Sorunlar

| Sorun | Neden | Çözüm |
|-------|-------|-------|
| Servis yönlendirmelerde yok | Konteyner çalışmıyor veya etiketler eksik | Deponun daemon'unda `docker ps` ile doğrulayın; etiketleri kontrol edin |
| Sertifika verilmedi | DNS sunucuya yönlenmiyor veya geçersiz Cloudflare token'ı | DNS çözümlemesini doğrulayın; Cloudflare API token izinlerini kontrol edin |
| 502 Bad Gateway | Uygulama belirtilen portta dinlemiyor | Uygulamanın `{SERVICE}_IP`'sine bağlı olduğunu ve portun `loadbalancer.server.port` ile eşleştiğini doğrulayın |
| TCP portu erişilemiyor | Port altyapıda kayıtlı değil | `rdc context set-infra --tcp-ports ...` ve `push-infra` çalıştırın |
| Route server running old version | Binary was updated but service not restarted | Happens automatically on provisioning; manual: `sudo systemctl restart rediacc-router` |
| STUN/TURN relay not reachable | Relay addresses cached at startup | Recreate the service after DNS or IP changes so it picks up the new network config |

## Tam Örnek

Bu, PostgreSQL veritabanı ile bir web uygulamasını dağıtır. Uygulama `app.example.com` adresinde TLS ile herkese açıktır; veritabanı yalnızca dahilidir.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    network_mode: host
    restart: unless-stopped
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Traefik etiketi yok — yalnızca dahili
```

### Rediaccfile

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

`app.example.com` adresini sunucunuzun genel IP'sine yönlendiren bir A kaydı oluşturun:

```
app.example.com   A   203.0.113.50
```

### Dağıtım

```bash
rdc repo up my-app -m server-1 --mount
```

Birkaç saniye içinde route server konteyneri keşfeder, Traefik yönlendirmeyi alır, TLS sertifikası talep eder ve `https://app.example.com` yayında olur.
