---
title: "Rediacc Kuralları"
description: "Rediacc platformunda uygulama geliştirmek için temel kurallar ve konvansiyonlar. Rediaccfile, compose, ağ, depolama, CRIU ve dağıtım konularını kapsar."
category: "Guides"
order: 5
language: tr
sourceHash: "5b62710fe6281f9d"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
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
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | Bağlanmış deponun kök yolu |
| `REPOSITORY_NETWORK_ID` | `6336` | Ağ izolasyon tanımlayıcısı |
| `REPOSITORY_NAME` | `abc123-...` | Depo GUID'i |
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
- **`restart: always` veya `restart: unless-stopped` kullanmayın** — bunlar CRIU checkpoint/restore ile çakışır. `restart: on-failure` kullanın veya belirtmeyin.
- **Docker adlandırılmış birimler kullanmayın** — bunlar şifrelenmiş deponun dışında bulunur ve yedekleme veya fork'lara dahil edilmez.

### Konteyner içindeki ortam değişkenleri

Renet bunları her konteynere otomatik olarak enjekte eder:

| Değişken | Açıklama |
|----------|----------|
| `SERVICE_IP` | Bu konteynerin ayrılmış loopback IP'si |
| `REPOSITORY_NETWORK_ID` | Ağ izolasyon ID'si |

### Servis adlandırma ve yönlendirme

- Compose **servis adı** otomatik yönlendirme URL ön eki olur.
- Örnek: temel alan adı `example.com` ve networkId 6336 olan `myapp` servisi `https://myapp-6336.example.com` olur.
- Özel alan adları için Traefik etiketleri kullanın (not: özel alan adları fork ile uyumlu DEĞİLDİR).

## Ağ

- **Her depo kendi Docker daemon'ını alır** — `/var/run/rediacc/docker-<networkId>.sock` konumunda.
- **Her servis bir /26 alt ağ içinde benzersiz bir loopback IP alır** (örn. `127.0.24.192/26`).
- **`SERVICE_IP`'ye bağlanın**, `0.0.0.0`'a değil — host ağı `0.0.0.0`'ın diğer depolarla çakışacağı anlamına gelir.
- **Servisler arası iletişim**: Loopback IP'leri veya `SERVICE_IP` ortam değişkenini kullanın. Docker DNS adları host modunda ÇALIŞMAZ.
- **Depolar arasında port çakışmaları imkansızdır** — her birinin kendi Docker daemon'ı ve IP aralığı vardır.
- **TCP/UDP port yönlendirme**: HTTP dışı portları açmak için etiketler ekleyin:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Depolama

- **Tüm kalıcı veriler `${REPOSITORY_PATH}/...` bind mount'ları kullanmalıdır.**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Docker adlandırılmış birimleri LUKS deposunun dışında bulunur — **şifrelenmemiş**, **yedeklenmemiş** ve **fork'lara dahil değildir**.
- LUKS birimi `/mnt/rediacc/mounts/<guid>/` konumuna bağlanır.
- BTRFS anlık görüntüleri, tüm bind mount verileri dahil olmak üzere LUKS destek dosyasının tamamını yakalar.

## CRIU (Canlı Geçiş)

- **`backup push --checkpoint`** çalışan işlem belleğini + disk durumunu yakalar.
- **`repo up --mount --checkpoint`** konteynerleri checkpoint'ten geri yükler (temiz başlatma yok).
- **TCP bağlantıları geri yüklemeden sonra geçersiz olur** — uygulamalar `ECONNRESET`'i işlemeli ve yeniden bağlanmalıdır.
- **Docker deneysel modu** depo başına daemon'larda otomatik olarak etkinleştirilir.
- **CRIU**, `rdc config setup-machine` sırasında kurulur.
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
- `restart: always`'den kaçının — CRIU geri yüklemeyi engeller.
- Docker DNS'ine güvenmeyin — servisler arası iletişim için loopback IP'leri kullanın.

## Güvenlik

- **LUKS şifreleme** standart depolar için zorunludur. Her deponun kendi şifreleme anahtarı vardır.
- **Kimlik bilgileri CLI yapılandırmasında saklanır** (`~/.config/rediacc/rediacc.json`). Yapılandırmayı kaybetmek, şifreli birimlere erişimi kaybetmek anlamına gelir.
- **Kimlik bilgilerini asla** sürüm kontrolüne commit etmeyin. `env_file` kullanın ve sırları `up()` içinde oluşturun.
- **Depo izolasyonu**: Her deponun Docker daemon'ı, ağı ve depolaması aynı makinedeki diğer depolardan tamamen izole edilmiştir.
- **Ajan izolasyonu**: Yapay zeka ajanları varsayılan olarak yalnızca fork modunda çalışır; grand (orijinal) depoları değil, sadece fork depoları değiştirebilirler. `term_exec` veya depo bağlamıyla `rdc term` üzerinden çalıştırılan komutlar Landlock LSM ile çekirdek düzeyinde sandbox içine alınır ve depolar arası dosya sistemi erişimi engellenir.

## Dağıtım

- **`rdc repo up`** tüm Rediaccfile'larda `up()` çalıştırır.
- **`rdc repo up --mount`** önce LUKS birimini açar, sonra yaşam döngüsünü çalıştırır. Yeni bir makineye `backup push` sonrasında gereklidir.
- **`rdc repo down`** `down()` çalıştırır ve Docker daemon'ını durdurur.
- **`rdc repo down --unmount`** ayrıca LUKS birimini kapatır (şifreli depolamayı kilitler).
- **Fork'lar** (`rdc repo fork`) yeni GUID ve networkId ile bir CoW (copy-on-write) klon oluşturur. Fork, üst öğenin şifreleme anahtarını paylaşır.
- **Proxy yolları** dağıtımdan sonra yaklaşık 3 saniyede aktif olur. `repo up` sırasında "Proxy is not running" uyarısı ops/dev ortamlarında bilgilendirme amaçlıdır.

## Yaygın hatalar

- `renet compose` yerine `docker compose` kullanmak — konteynerler ağ izolasyonu alamaz.
- `restart: always` kullanmak — CRIU geri yüklemeyi engeller ve `repo down` ile çakışır.
- Docker adlandırılmış birimleri kullanmak — veriler şifrelenmez, yedeklenmez, fork'lanmaz.
- `0.0.0.0`'a bağlanmak — host ağ modunda depolar arasında port çakışmalarına neden olur.
- IP'leri sabit kodlamak — `SERVICE_IP` ortam değişkenini kullanın; IP'ler networkId başına dinamik olarak atanır.
- `backup push` sonrası ilk dağıtımda `--mount`'u unutmak — LUKS birimi açık bir şekilde açılmalıdır.
- Başarısız komutlar için geçici çözüm olarak `rdc term -c` kullanmak — bunun yerine hataları bildirin.
