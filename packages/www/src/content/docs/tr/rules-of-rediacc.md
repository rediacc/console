---
title: "Rediacc Kuralları"
description: "Rediacc platformunda uygulama geliştirmek için temel kurallar ve konvansiyonlar. Rediaccfile, compose, ağ, depolama, CRIU ve dağıtım konularını kapsar."
category: "Guides"
order: 5
language: tr
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
---

# Rediacc Kuralları

Her Rediacc deposu, kendi Docker daemon'ı, şifrelenmiş LUKS birimi ve ayrılmış IP aralığına sahip izole bir ortamda çalışır. Bu kurallar, uygulamanızın bu mimari içinde doğru şekilde çalışmasını sağlar.

## Rediaccfile

- **Her depo bir Rediaccfile'a ihtiyaç duyar** — yaşam döngüsü fonksiyonlarına sahip bir bash betiği.
- **Yaşam döngüsü fonksiyonları**: `up()`, `down()`. İsteğe bağlı: `info()`.
- `up()` servislerinizi başlatır. `down()` onları durdurur.
- `info()` durum bilgisi sağlar (konteyner durumu, son günlükler, sağlık).
- Rediaccfile, renet tarafından source edilir — sadece ortam değişkenlerine değil, kabuk değişkenlerine de erişimi vardır.

### Rediaccfile'da kullanılabilir ortam değişkenleri

| Değişken | Örnek | Açıklama |
|----------|-------|----------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Bağlanmış deponun kök yolu |
| `REDIACC_NETWORK_ID` | `6336` | Ağ izolasyon tanımlayıcısı |
| `REDIACC_REPOSITORY` | `abc123-...` | Depo GUID'i |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | Servis başına loopback IP (servis adı büyük harfle) |

### Minimal Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **`renet compose` kullanın, asla `docker compose` kullanmayın** — renet ağ izolasyonu, host ağı, loopback IP'leri ve servis etiketlerini enjekte eder.
- **Compose dosyanızda `network_mode` ayarlamayın** — renet tüm servislere `network_mode: host` zorlar. Belirlediğiniz her değer üzerine yazılır.
- **`rediacc.*` etiketleri ayarlamayın** — renet otomatik olarak `rediacc.network_id`, `rediacc.service_ip` ve `rediacc.service_name` enjekte eder.
- **`ports:` eşlemeleri** host ağ modunda yok sayılır. 80 dışındaki portlara proxy yönlendirmesi için `rediacc.service_port` etiketini kullanın.
- **Yeniden başlatma politikaları (`restart: always`, `on-failure`, vb.) kullanmak güvenlidir** — renet bunları CRIU uyumluluğu için otomatik olarak kaldırır. Router watchdog, `.rediacc.json` içinde kaydedilen orijinal politikaya göre durmuş konteynerleri otomatik olarak kurtarır.
- **Tehlikeli ayarlar varsayılan olarak engellenir** — `privileged: true`, `pid: host`, `ipc: host` ve sistem yollarına bind mount'lar reddedilir. Kendi sorumluluğunuzda geçersiz kılmak için `renet compose --unsafe` kullanın.

### Konteyner içindeki ortam değişkenleri

Renet bunları her konteynere otomatik olarak enjekte eder:

| Değişken | Açıklama |
|----------|----------|
| `SERVICE_IP` | Bu konteynerin ayrılmış loopback IP'si |
| `REDIACC_NETWORK_ID` | Ağ izolasyon ID'si |

### Servis adlandırma ve yönlendirme

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-{tag}.{machine}.{baseDomain}` — uses the machine wildcard cert to avoid Let's Encrypt rate limits.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly — the domain belongs to the grand repo).

## Ağ

- **Her depo kendi Docker daemon'ını alır** — `/var/run/rediacc/docker-<networkId>.sock` konumunda.
- **Her servis bir /26 alt ağ içinde benzersiz bir loopback IP alır** (örn. `127.0.24.192/26`).
- **`SERVICE_IP`'ye bağlanın** — her servis benzersiz bir loopback IP alır.
- **Health check'ler `${SERVICE_IP}` kullanmalıdır**, `localhost` değil. Örnek: `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **Servisler arası iletişim**: Loopback IP'leri veya `SERVICE_IP` ortam değişkenini kullanın. Docker DNS adları host modunda ÇALIŞMAZ.
- **Depolar arasında port çakışmaları imkansızdır** — her birinin kendi Docker daemon'ı ve IP aralığı vardır.
- **TCP/UDP port yönlendirme**: HTTP dışı portları açmak için etiketler ekleyin:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Depolama

- **Tüm Docker verileri şifreli depo içinde saklanır** — Docker'ın `data-root`'u LUKS birimi içindeki `{mount}/.rediacc/docker/data` konumundadır. Adlandırılmış birimler, görüntüler ve konteyner katmanlarının tamamı şifrelenir, yedeklenir ve otomatik olarak fork'lanır.
- **`${REDIACC_WORKING_DIR}/...` bind mount'ları anlaşılırlık açısından önerilir**, ancak adlandırılmış birimler de güvenle çalışır.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (önerilen)
    - pgdata:/var/lib/postgresql/data      # named volume (aynı zamanda güvenli)
  ```
- LUKS birimi `/mnt/rediacc/mounts/<guid>/` konumuna bağlanır.
- BTRFS anlık görüntüleri, tüm bind mount verileri dahil olmak üzere LUKS destek dosyasının tamamını yakalar.
- Veri deposu, sistem diskindeki sabit boyutlu bir BTRFS havuz dosyasıdır. Etkin boş alanı görmek için `rdc machine query <name> --system` kullanın. `rdc datastore resize` ile genişletin.

## CRIU (Canlı Geçiş)

- **`backup push --checkpoint`** çalışan işlem belleğini + disk durumunu yakalar.
- **`repo up --mount --checkpoint`** konteynerleri checkpoint'ten geri yükler (temiz başlatma yok).
- **TCP bağlantıları geri yüklemeden sonra geçersiz olur** — uygulamalar `ECONNRESET`'i işlemeli ve yeniden bağlanmalıdır.
- **Docker deneysel modu** depo başına daemon'larda otomatik olarak etkinleştirilir.
- **CRIU**, `rdc config machine setup` sırasında kurulur.
- **`/etc/criu/runc.conf`** TCP bağlantı koruması için `tcp-established` ile yapılandırılır.
- **Konteyner güvenlik ayarları renet tarafından otomatik enjekte edilir** — `renet compose` CRIU uyumluluğu için her konteynere otomatik olarak şunları ekler:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (çekirdek 5.9+ üzerinde CRIU için minimum set)
  - `security_opt`: `apparmor=unconfined` (CRIU'nun AppArmor desteği upstream'de henüz kararlı değil)
  - `userns_mode: host` (CRIU, `/proc/pid/map_files` için init namespace erişimi gerektirir)
- Docker'ın varsayılan seccomp profili korunur — CRIU, checkpoint/restore sırasında filtreleri geçici olarak askıya almak için `PTRACE_O_SUSPEND_SECCOMP` (çekirdek 4.3+) kullanır.
- **Bunları compose dosyanızda manuel olarak ayarlamayın** — renet bunu halleder. Kendiniz ayarlamak tekrarlama veya çakışma riski oluşturur.
- CRIU uyumlu referans uygulama için [heartbeat şablonuna](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) bakın.

### CRIU uyumlu uygulama kalıpları

- Tüm kalıcı bağlantılarda (veritabanı havuzları, websocket'ler, mesaj kuyrukları) `ECONNRESET`'i işleyin.
- Otomatik yeniden bağlanmayı destekleyen bağlantı havuzu kütüphaneleri kullanın.
- Dahili kütüphane nesnelerinden gelen eski soket hataları için güvenlik ağı olarak `process.on("uncaughtException")` ekleyin.
- Yeniden başlatma politikaları renet tarafından otomatik yönetilir (CRIU için kaldırılır, watchdog kurtarmayı üstlenir).
- Docker DNS'ine güvenmeyin — servisler arası iletişim için loopback IP'leri kullanın.

## Güvenlik

- **LUKS şifreleme** standart depolar için zorunludur. Her deponun kendi şifreleme anahtarı vardır.
- **Kimlik bilgileri CLI yapılandırmasında saklanır** (`~/.config/rediacc/rediacc.json`). Yapılandırmayı kaybetmek, şifreli birimlere erişimi kaybetmek anlamına gelir.
- **Kimlik bilgilerini asla** sürüm kontrolüne commit etmeyin. `env_file` kullanın ve sırları `up()` içinde oluşturun.
- **Depo izolasyonu**: Her deponun Docker daemon'ı, ağı ve depolaması aynı makinedeki diğer depolardan tamamen izole edilmiştir.
- **Ajan izolasyonu**: Yapay zeka ajanları varsayılan olarak yalnızca fork modunda çalışır. Her deponun, sunucu tarafında sandbox uygulaması (ForceCommand `sandbox-gateway`) olan kendi SSH anahtarı vardır. Tüm bağlantılar Landlock LSM, OverlayFS home overlay ve depo başına TMPDIR ile sandbox içine alınır. Depolar arası dosya sistemi erişimi çekirdek tarafından engellenir.

## Dağıtım

- **`rdc repo up`** tüm Rediaccfile'larda `up()` çalıştırır.
- **`rdc repo up --mount`** önce LUKS birimini açar, sonra yaşam döngüsünü çalıştırır. Yeni bir makineye `backup push` sonrasında gereklidir.
- **`rdc repo down`** `down()` çalıştırır ve Docker daemon'ını durdurur.
- **`rdc repo down --unmount`** ayrıca LUKS birimini kapatır (şifreli depolamayı kilitler).
- **Fork'lar** (`rdc repo fork`) yeni GUID ve networkId ile bir CoW (copy-on-write) klon oluşturur. Fork, üst öğenin şifreleme anahtarını paylaşır.
- **Takeover** (`rdc repo takeover <fork> -m <machine>`) grand deponun verilerini bir fork'un verileriyle değiştirir. Grand kimliğini korur (GUID, networkId, alan adları, otomatik başlatma, yedekleme zinciri). Eski üretim verileri yedekleme fork'u olarak korunur. Kullanım: fork üzerinde yükseltmeyi test edin, doğrulayın, ardından üretime takeover yapın. `rdc repo takeover <backup-fork> -m <machine>` ile geri alın.
- **Proxy yolları** dağıtımdan sonra yaklaşık 3 saniyede aktif olur. `repo up` sırasında "Proxy is not running" uyarısı ops/dev ortamlarında bilgilendirme amaçlıdır.

## Yaygın hatalar

- `renet compose` yerine `docker compose` kullanmak — konteynerler ağ izolasyonu alamaz.
- Yeniden başlatma politikaları güvenlidir — renet bunları otomatik olarak kaldırır ve watchdog kurtarmayı üstlenir.
- `privileged: true` kullanmak — gerekli değildir, renet bunun yerine belirli CRIU capability'lerini enjekte eder.
- `SERVICE_IP`'ye bağlanmamak — depolar arasında port çakışmalarına neden olur.
- IP'leri sabit kodlamak — `SERVICE_IP` ortam değişkenini kullanın; IP'ler networkId başına dinamik olarak atanır.
- `backup push` sonrası ilk dağıtımda `--mount`'u unutmak — LUKS birimi açık bir şekilde açılmalıdır.
- Başarısız komutlar için geçici çözüm olarak `rdc term -c` kullanmak — bunun yerine hataları bildirin.
- `repo delete` loopback IP'leri ve systemd birimlerini de dahil ederek tam temizlik yapar. Eski silmelerden kalan artıkları temizlemek için `rdc machine prune <name>` çalıştırın.
