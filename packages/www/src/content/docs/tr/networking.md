---
title: Ağ
description: >-
  Ters proxy, Docker etiketleri, TLS sertifikaları, DNS ve TCP/UDP port
  yönlendirme ile servisleri dışarıya açın.
category: Guides
order: 6
language: tr
sourceHash: "536db0c93646cad6"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Ağ

Bu sayfa, izole Docker daemon'larında çalışan servislerin internetten nasıl erişilebilir hale geldiğini açıklar. Ters proxy sistemi, yönlendirme için Docker etiketleri, TLS sertifikaları, DNS ve TCP/UDP port yönlendirmeyi kapsar.

Servislerin geri döngü IP'lerini nasıl aldığı ve `.rediacc.json` slot sistemi hakkında bilgi için [Servisler](/tr/docs/services#service-networking-rediaccjson) bölümüne bakın.

## Ağ Yalıtımı

Her depo, ağ kancaları kullanılarak çekirdek düzeyinde otomatik olarak yalıtılır. Bu, Linux kernel 6.1 veya üzerini gerektirir. Herhangi bir yapılandırma gerekmez.

- **Otomatik bind yeniden yazma**: Servisler her zamanki gibi `0.0.0.0` veya `127.0.0.1`'e bağlanabilir. Çekirdek, adresi servisin atanmış geri döngü IP'sine şeffaf olarak yeniden yazar. `${SERVICE_IP}`'ye açıkça bağlanmaya gerek yoktur.
- **Depolar arası bağlantı engelleme**: Bir servis, deposunun `/26` alt ağı dışındaki bir geri döngü IP'sine bağlanmaya çalışırsa, çekirdek bunu engeller. Depo A'daki bir işlem, Depo B'deki servislere erişemez.
- **Uygulama değişikliği gerekmez**: Servisler bağlama için `0.0.0.0` veya `localhost` kullanır ve çekirdek, yalnızca doğru geri döngü IP'lerinde dinlemelerini sağlar. Yalıtım tamamen şeffaftır.

## Nasıl Çalışır

Rediacc, harici trafiği konteynerlere yönlendirmek için iki bileşenli bir proxy sistemi kullanır:

1. **Route server**, tüm depo Docker daemon'larındaki çalışan konteynerleri keşfeden bir systemd servisi. Konteyner etiketlerini inceler ve YAML uç noktası olarak sunulan yönlendirme yapılandırması oluşturur.
2. **Traefik**, route server'ı her 5 saniyede sorgulayan ve keşfedilen yönlendirmeleri uygulayan ters proxy. HTTP/HTTPS yönlendirme, TLS sonlandırma ve TCP/UDP yönlendirme işlemlerini yönetir.

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

Bir konteynere doğru etiketleri ekleyip `renet compose` ile başlattığınızda, otomatik olarak yönlendirilebilir hale gelir, manuel proxy yapılandırması gerekmez.

> Route server binary'si CLI sürümünüzle senkronize tutulur. CLI bir makinede renet binary'sini güncellediğinde, route server otomatik olarak yeniden başlatılır (~1-2 saniye). Bu herhangi bir kesintiye neden olmaz, Traefik yeniden başlatma sırasında son bilinen yapılandırmasıyla trafik sunmaya devam eder ve sonraki sorguda yeni yapılandırmayı alır. Mevcut istemci bağlantıları etkilenmez. Uygulama konteynerlerinize dokunulmaz.

## Docker Etiketleri

Yönlendirme, Docker konteyner etiketleri ile kontrol edilir. İki seviye vardır:

### Seviye 1: `rediacc.*` Etiketleri (Otomatik)

Bu etiketler, servisler başlatılırken `renet compose` tarafından **otomatik olarak enjekte edilir**. Manuel olarak eklemenize gerek yoktur.

| Etiket | Açıklama | Örnek |
|--------|----------|-------|
| `rediacc.service_name` | Servis kimliği | `myapp` |
| `rediacc.service_ip` | Atanmış geri döngü IP'si | `127.0.11.2` |
| `rediacc.network_id` | Deponun daemon ID'si | `2816` |
| `rediacc.repo_name` | Depo adı | `marketing` |
| `rediacc.tcp_ports` | Servisin dinlediği TCP portları | `8080,8443` |
| `rediacc.udp_ports` | Servisin dinlediği UDP portları | `53` |

Bir konteyner yalnızca `rediacc.*` etiketlerine sahipken (`traefik.enable=true` yokken), route server depo adını ve makinenin alt alan adını kullanarak bir **otomatik yönlendirme** oluşturur:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Örneğin, `server-1` makinesinde `marketing` adlı bir depodaki `myapp` adlı servis, temel alan adı `example.com` ile şunu alır:

```
myapp.marketing.server-1.example.com
```

Çatalmalar için, servis adı `fork` ayrılmış kelimesi ve etiketle birleştirilir:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Örneğin, `staging` etiketli `marketing` çatallaması şunu alır:

```
myapp-fork-staging.marketing.server-1.example.com
```

Her çatallanma URL'si üst deponun alt alan adının altında yer alır ve mevcut joker sertifika tarafından kapsanır, dolayısıyla yeni bir sertifikaya gerek yoktur. `-fork-` ayırıcısı, üretim deposundaki gerçek servis adlarıyla çakışmaları önler. Özel alan adlarına sahip servisler için Seviye 2 etiketlerini veya `rediacc.domain` etiketini kullanın.

#### `rediacc.domain` ile Özel Alan Adı

`docker-compose.yml` dosyanızdaki `rediacc.domain` etiketini kullanarak bir servis için özel alan adı belirleyebilirsiniz. Hem kısa adlar hem de tam alan adları desteklenir:

```yaml
labels:
  # Kısa ad, makinenin baseDomain'i kullanılarak cloud.example.com olarak çözümlenir
  - "rediacc.domain=cloud"

  # Tam alan adı, olduğu gibi kullanılır
  - "rediacc.domain=cloud.example.com"
```

Nokta içermeyen değer kısa ad olarak değerlendirilir ve makinenin `baseDomain`'i otomatik olarak eklenir. Nokta içeren değer tam alan adı olarak kullanılır.

`machineName` yapılandırıldığında, özel alan adlı servisler **iki yönlendirme** alır: biri temel alan adında (`cloud.example.com`) ve biri makine alt alan adında (`cloud.server-1.example.com`).

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

1. Makinede yapılandırılmış altyapı ([Makine Kurulumu, Altyapı Yapılandırması](/tr/docs/setup#infrastructure-configuration)):

   ```bash
   # Paylaşılan kimlik bilgileri (yapılandırma başına bir kez, tüm makinelere uygulanır)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Makineye özel ayarlar
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. Alan adınızı sunucunun genel IP'sine yönlendiren DNS kayıtları (aşağıdaki [DNS Yapılandırması](#dns-yapılandırması) bölümüne bakın).

### Etiket Ekleme

Dışarıya açmak istediğiniz servislere `docker-compose.yml` dosyanızda `traefik.*` etiketleri ekleyin:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # Traefik etiketi yok, veritabanı yalnızca dahili
```

| Etiket | Amaç |
|--------|------|
| `traefik.enable=true` | Bu konteyner için özel Traefik yönlendirmesini etkinleştirir |
| `traefik.http.routers.{name}.rule` | Yönlendirme kuralı, genellikle `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Hangi portlarda dinleneceği: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Sertifika çözümleyici, otomatik Let's Encrypt için `letsencrypt` kullanın |
| `traefik.http.services.{name}.loadbalancer.server.port` | Uygulamanızın konteyner içinde dinlediği port |

Etiketlerdeki `{name}` rastgele bir tanımlayıcıdır, sadece ilgili router/service/middleware etiketleri arasında tutarlı olması yeterlidir.

> **Not:** `rediacc.*` etiketleri (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) `renet compose` tarafından otomatik olarak enjekte edilir. Compose dosyanıza eklemenize gerek yoktur.

## TLS Sertifikaları

TLS sertifikaları, Cloudflare DNS-01 doğrulaması kullanılarak Let's Encrypt aracılığıyla otomatik olarak alınır. Kimlik bilgileri yapılandırma başına bir kez ayarlanır (tüm makineler arasında paylaşılır):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Otomatik yönlendirmeler, servis başına sertifika yerine depo alt alan adı seviyesinde **joker sertifikalar** (`*.marketing.server-1.example.com`) kullanır. Sertifika, ilk `repo up` sırasında Traefik tarafından otomatik olarak sağlanır; manuel adım gerekmez. Çatallanmalar üst deponun mevcut jokerini yeniden kullanır, bu nedenle asla yeni bir sertifika isteği tetiklemez. Özel alan adlı yönlendirmeler makine seviyesi joker sertifikalar (`*.server-1.example.com`) kullanır.

> **Cloudflare kimlik bilgileri gereklidir.** Joker sertifikalar DNS-01 doğrulaması kullanır. `--cf-dns-token` (ve isteğe bağlı `--cert-email`) olmadan, Traefik doğrulamayı tamamlayamaz ve HTTPS çalışmaz. HTTP işlevsel kalır. İlk dağıtımdan önce `rdc config infra set` ile kimlik bilgilerini yapılandırın.

`traefik.http.routers.{name}.tls.certresolver=letsencrypt` içeren Seviye 2 yönlendirmeler için, joker alan adı SAN'ları yönlendirmenin ana bilgisayar adına göre otomatik olarak enjekte edilir.

Cloudflare DNS API token'ının, güvence altına almak istediğiniz alan adları için `Zone:DNS:Edit` iznine sahip olması gerekir.

### TLS Sertifikası Yaşam Döngüsü

Let's Encrypt sertifikasının verilmesinden her deponun konteynerlerine ulaşmasına kadar geçen tam yol:

1. **Konakta verilme.** Makine seviyesinde bir Traefik konteyneri (`rediacc-proxy`, `/opt/rediacc/proxy/`'ye dağıtılmış) ACME yenilemeye sahiptir. Tüm durumu konaktaki `/opt/rediacc/proxy/letsencrypt/acme.json`'da saklar. Yenileme, sona ermeden yaklaşık 30 gün önce otomatik olarak tetiklenir; `--cf-dns-token` yapılandırıldığı sürece operatör eylemi gerekmez.

2. **Depo başına dökme (isteğe bağlı).** Kendi konteyneri içinde sertifika dosyalarına ihtiyaç duyan servisler (örneğin, doğrudan bir `.pem` okuyan bir posta sunucusu), yanlarına küçük bir `traefik-certs-dumper` konteyneri dağıtır. Dökücü `/opt/rediacc/proxy/letsencrypt`'i salt okunur olarak bağlar ve çıkarılan sertifika ile anahtarı deponun veri birimine `cert.pem` / `key.pem` olarak yazar. Bunun çalışması için, depo başına Docker daemon'ının bağlama ad alanı izin listesinde `/opt/rediacc/proxy` bulunmalıdır. Bu varsayılan olarak zaten dahildir.

3. **İstemci tarafı önbellek (`rediacc.json`).** CLI, yapılandırma dosyanızda `acmeCertCache` altında `acme.json`'ın sıkıştırılmış bir kopyasını `baseDomain`'e göre anahtarlanmış olarak önbelleğe alır. Bu, birden fazla makinenin sertifikaları paylaşmasına olanak tanır (`rdc config cert-cache push <machine>` aracılığıyla) ve çevrimdışı envanter olarak işlev görür.

**İstemci önbelleği için eşitleme tetikleyicileri:**

- `rdc repo up` sonrasında otomatik olarak, ancak yalnızca makinenin `baseDomain`'i için yerel önbellek 6 saatten eskiyse. Taze önbellekler, arka arkaya dağıtımların SSH'yi zorlamamaması için olduğu gibi bırakılır.
- İsteğe bağlı: `rdc config cert-cache pull -m <machine>` (zorla çekme) veya `rdc machine query --name <machine> --sync-certs` (durum sorgusunun yan etkisi olarak çekme).
- `rdc config infra push` sırasında önbellek makineye itilir (daha uzun son kullanma tarihine sahip yerel sertifikalar uzak olanları geçer).

**Önbellek bakımı:**

- Eski otomatik yönlendirme girdileri (`service-3200.rediacc.io` gibi eski ağ ID'li etiketli alanlar) her çekmede temizlenir.
- `notAfter`'ı 7 günden fazla geçmişte olan sertifikalar tamamen kaldırılır. Bunlar etkisizdir ve yalnızca önbelleği şişirir.
- `rdc config cert-cache clear` her şeyi siler; `rdc config cert-cache status` envanteri gösterir.

**Sorun giderme:** `traefik-certs-dumper` `/traefik/acme.json: no such file or directory` ile çöküyor ise, depo başına daemon konağın letsencrypt deposunu göremiyordur. (a) `/opt/rediacc/proxy/letsencrypt/acme.json`'ın konakta mevcut olduğunu doğrulayın (bu, konak seviyesindeki `rediacc-proxy`'nin sorumluluğudur), ve (b) depo başına daemon'ın `/opt/rediacc/proxy`'yi izin listesine alan yeterince yeni bir renet ile başlatıldığını doğrulayın. renet'i yükselttikten sonra uygulamak için `rdc repo up` ile depoyu yeniden dağıtın.

> **Deneysel:** Otomatik eşitleme sıklığı ve son kullanma tarihine dayalı temizlik renet 0.9+'da gelmiştir. Eski CLI/renet sürümleri yalnızca `rdc config cert-cache pull` aracılığıyla manuel eşitleme kullanır.

## TCP/UDP Port Yönlendirme

HTTP dışı protokoller (posta sunucuları, DNS, dışarıya açılan veritabanları) için TCP/UDP port yönlendirme kullanın.

### Adım 1: Portları Kaydetme

Altyapı yapılandırması sırasında gerekli portları ekleyin:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Bu, `tcp-{port}` ve `udp-{port}` adlı Traefik giriş noktaları oluşturur.

> Port ekledikten veya kaldırdıktan sonra, proxy yapılandırmasını güncellemek için her zaman `rdc config infra push` komutunu yeniden çalıştırın.

### Adım 2: TCP/UDP Etiketleri Ekleme

Compose dosyanızda `traefik.tcp.*` veya `traefik.udp.*` etiketlerini kullanın:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS geçişi
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Temel kavramlar:
- **`HostSNI(\`*\`)`** herhangi bir ana bilgisayar adıyla eşleşir (düz SMTP gibi SNI göndermeyen protokoller için)
- **`tls.passthrough=true`** Traefik'in ham TLS bağlantısını şifresini çözmeden ilettiği anlamına gelir, uygulama TLS'yi kendisi yönetir
- Giriş noktası adları `tcp-{port}` veya `udp-{port}` kuralını takip eder

### Sade TCP Örneği (Veritabanı)

TLS geçişi olmadan bir veritabanını dışarıya açmak için (Traefik ham TCP'yi iletir):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 önceden yapılandırılmıştır (aşağıya bakın), bu nedenle `--tcp-ports` kurulumu gerekmez.

> **Güvenlik notu:** Bir veritabanını internete açmak risk teşkil eder. Bunu yalnızca uzak istemcilerin doğrudan erişime ihtiyaç duyduğu durumlarda kullanın. Çoğu kurulumda veritabanını dahili tutun ve uygulamanız aracılığıyla bağlanın.

### Önceden Yapılandırılmış Portlar

Aşağıdaki TCP/UDP portları varsayılan olarak giriş noktalarına sahiptir (`--tcp-ports` ile eklemeye gerek yoktur). Giriş noktaları yalnızca yapılandırılmış adres aileleri için oluşturulur, IPv4 giriş noktaları `--public-ipv4`, IPv6 giriş noktaları `--public-ipv6` gerektirir:

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
| 10000-10010 | TCP | Dinamik aralık (otomatik atama) |

## DNS Yapılandırması

### Otomatik DNS (Cloudflare)

`--cf-dns-token` yapılandırıldığında, `rdc config infra push` gerekli DNS kayıtlarını Cloudflare'de otomatik olarak oluşturur:

| Kayıt | Tür | İçerik | Oluşturan |
|-------|-----|--------|-----------|
| `server-1.example.com` | A / AAAA | Makinenin genel IP'si | `push-infra` |
| `*.server-1.example.com` | A / AAAA | Makinenin genel IP'si | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | Makinenin genel IP'si | `repo up` |

Makine seviyesi kayıtlar `push-infra` tarafından oluşturulur ve özel alan adlı yönlendirmeleri (`rediacc.domain`) kapsar. Depo başına joker kayıtlar `repo up` tarafından otomatik olarak oluşturulur ve o deponun otomatik yönlendirmelerini kapsar.

Bu idempotent bir işlemdir, IP değişirse mevcut kayıtlar güncellenir, zaten doğruysa değiştirilmez.

Temel alan adı joker kaydı (`*.example.com`), `rediacc.domain=erp` gibi özel alan adı etiketleri kullanıyorsanız manuel olarak oluşturulmalıdır.

### Manuel DNS

Cloudflare kullanmıyorsanız veya DNS'i manuel yönetiyorsanız, A (IPv4) ve/veya AAAA (IPv6) kayıtları oluşturun:

```
# Makine alt alan adı (rediacc.domain=erp gibi özel alan adlı yönlendirmeler için)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Depo başına joker kayıtlar (myapp.marketing.server-1.example.com gibi otomatik yönlendirmeler için)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Temel alan adı joker kaydı (rediacc.domain=erp gibi özel alan adlı servisler için)
*.example.com                  A     203.0.113.50
```

Cloudflare DNS yapılandırıldığında, depo başına joker kayıtlar `repo up` tarafından otomatik olarak oluşturulur. Birden fazla makine ile her makine kendi IP'sine işaret eden kendi DNS kayıtlarını alır.

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
| 502 Bad Gateway | Uygulama belirtilen portta dinlemiyor | Uygulamanın çalıştığını ve portun `loadbalancer.server.port` ile eşleştiğini doğrulayın |
| TCP portu erişilemiyor | Port altyapıda kayıtlı değil | `rdc config infra set --tcp-ports ...` ve `push-infra` çalıştırın |
| Route server eski sürümde çalışıyor | Binary güncellendi ancak servis yeniden başlatılmadı | Sağlama sırasında otomatik olarak gerçekleşir; manuel: `sudo systemctl restart rediacc-router` |
| STUN/TURN relay erişilemiyor | Relay adresleri başlangıçta önbelleğe alındı | DNS veya IP değişikliklerinden sonra yeni ağ yapılandırmasını alması için servisi yeniden oluşturun |

## Tam Örnek

Bu, PostgreSQL veritabanı ile bir web uygulamasını dağıtır. Uygulama `app.example.com` adresinde TLS ile herkese açıktır; veritabanı yalnızca dahilidir.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
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
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Traefik etiketi yok, yalnızca dahili
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
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
rdc repo up --name my-app -m server-1
```

Birkaç saniye içinde route server konteyneri keşfeder, Traefik yönlendirmeyi alır, TLS sertifikası talep eder ve `https://app.example.com` yayında olur.
