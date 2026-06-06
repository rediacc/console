---
title: "Rediacc Kuralları"
description: "Rediacc platformunda uygulama geliştirmek için temel kurallar ve konvansiyonlar. Rediaccfile, compose, ağ, depolama, CRIU ve dağıtım konularını kapsar."
category: Guides
order: 5
language: tr
sourceHash: "74803e91ef07b03c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Rediacc Kuralları

Her Rediacc deposu, kendi Docker daemon'ı, şifreli LUKS birimi ve ayrılmış IP aralığına sahip izole bir ortamda çalışır. Bu kurallar, uygulamanızın bu mimari içinde doğru şekilde çalışmasını sağlar.

## Rediaccfile

- **Her depo bir Rediaccfile'a ihtiyaç duyar**, yaşam döngüsü fonksiyonlarına sahip bir bash betiği.
- **Yaşam döngüsü fonksiyonları**: `up()`, `down()`. İsteğe bağlı: `info()`.
- `up()` servislerinizi başlatır. `down()` onları durdurur.
- `info()` durum bilgisi sağlar (konteyner durumu, son günlükler, sağlık).
- Rediaccfile, renet tarafından source edilir, sadece ortam değişkenlerine değil, kabuk değişkenlerine de erişimi vardır.

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

- **`renet compose` kullanın, asla `docker compose` kullanmayın**, renet ağ izolasyonu, host ağı, loopback IP'leri ve servis etiketlerini enjekte eder.
- **Compose dosyanızda `network_mode` ayarlamayın**, renet tüm servislere `network_mode: host` zorlar. Belirlediğiniz her değer üzerine yazılır.
- **`rediacc.*` etiketleri ayarlamayın**, renet otomatik olarak `rediacc.network_id`, `rediacc.service_ip` ve `rediacc.service_name` enjekte eder.
- **`ports:` eşlemeleri** host ağ modunda yok sayılır. HTTP yönlendirmesi için `rediacc.service_port` etiketini ekleyin (bu etikete sahip olmayan servisler HTTP rotaları almaz). TCP/UDP yönlendirme için `rediacc.tcp_ports`/`rediacc.udp_ports` etiketlerini kullanın.
- **Yeniden başlatma politikaları (`restart: always`, `on-failure`, vb.) kullanmak güvenlidir**, renet bunları CRIU uyumluluğu için otomatik olarak kaldırır. Router watchdog, `.rediacc.json` içinde kaydedilen orijinal politikaya göre durmuş konteynerleri otomatik olarak kurtarır.
- **Tehlikeli ayarlar varsayılan olarak engellenir**, `privileged: true`, `pid: host`, `ipc: host` ve sistem yollarına host bind mount'ları reddedilir. Kendi sorumluluğunuzda geçersiz kılmak için `renet compose --unsafe` kullanın.

### Konteyner içindeki ortam değişkenleri

Renet bunları her konteynere otomatik olarak enjekte eder:

| Değişken | Açıklama |
|----------|----------|
| `SERVICE_IP` | Bu konteynerin ayrılmış loopback IP'si |
| `REDIACC_NETWORK_ID` | Ağ izolasyon ID'si |

### Servis adlandırma ve yönlendirme

- Compose'daki **servis adı**, otomatik rota URL önekine dönüşür.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (ör.: `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (ör.: `https://myapp-fork-staging.marketing.server-1.example.com`). `-fork-` ayırıcısı, grand repo servis adlarıyla URL çakışmalarını önler. Fork URL'si her zaman üst deponun mevcut wildcard sertifikasını kullanır, bu nedenle yeni sertifika gerekmez.
- Özel alan adları için Traefik etiketlerini kullanın (not: özel alan adları fork ile uyumlu DEĞİLDİR, alan adı grand repo'ya aittir).

## Ağ

- **Her depo kendi Docker daemon'ını alır**, `/var/run/rediacc/docker-<networkId>.sock` konumunda.
- **Her servis bir /26 alt ağ içinde benzersiz bir loopback IP alır** (örn. `127.0.24.192/26`).
- **Bağlama otomatiktir**: Servisler `0.0.0.0` veya `localhost`'a bağlanabilir, çekirdek adresi şeffaf olarak servisin atanmış loopback IP'sine yeniden yazar. `${SERVICE_IP}`'ye açık bağlama hala çalışır ancak artık gerekli değildir.
- **Health check'ler `localhost`** veya `${SERVICE_IP}` kullanabilir. Örnek: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Depolar arası bağlantılar çekirdek tarafından engellenir**: Çekirdek, depo için `/26` alt ağının dışındaki loopback IP'lerine yapılan bağlantıları otomatik olarak engeller. Bir depodaki servis başka bir depodaki servislere erişemez.
- **Servisler arası iletişim**: **Servis adlarını** kullanın (ör. `db`, `redis`), renet her servis adını otomatik olarak doğru IP'ye çözümlenen bir ana bilgisayar adı olarak enjekte eder. Docker DNS adları host modunda ÇALIŞMAZ, ancak `/etc/hosts` üzerinden servis adları çalışır. Kalıcı yapılandırma dosyalarına (ör. bir veritabanında saklanan bağlantı dizeleri) `${DB_IP}` veya benzerini gömmekten kaçının, fork yapıldığında ham IP taşınır ve yanlış depoya işaret eder. Servis adları her zaman depo başına doğru şekilde çözümlenir.
- **Depolar arasında port çakışmaları imkansızdır**, her birinin kendi Docker daemon'ı ve IP aralığı vardır.
- **TCP/UDP port yönlendirme**: HTTP dışı portları açmak için etiketler ekleyin:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Depolama

- **Tüm Docker verileri şifreli depo içinde saklanır**, Docker'ın `data-root`'u LUKS birimi içindeki `{mount}/.rediacc/docker/data` konumundadır. Adlandırılmış birimler, görüntüler ve konteyner katmanlarının tamamı şifrelenir, yedeklenir ve otomatik olarak fork'lanır.
- **`${REDIACC_WORKING_DIR}/...` bind mount'ları anlaşılırlık açısından önerilir**, ancak adlandırılmış birimler de güvenle çalışır.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (önerilen)
    - pgdata:/var/lib/postgresql/data      # named volume (aynı zamanda güvenli)
  ```
- LUKS birimi `/mnt/rediacc/mounts/<guid>/` konumuna bağlanır.
- BTRFS anlık görüntüleri, tüm bind mount verileri dahil olmak üzere LUKS destek dosyasının tamamını yakalar.
- Veri deposu, sistem diskindeki sabit boyutlu bir BTRFS havuz dosyasıdır. Etkin boş alanı görmek için `rdc machine query --name <name> --system` kullanın. `rdc datastore resize` ile genişletin.

## CRIU (Canlı Geçiş)

- **Etiketle etkinleştirme**: Checkpoint almak istediğiniz konteynerlere `rediacc.checkpoint=true` ekleyin. Bu etiketi olmayan konteynerler (veritabanları, önbellekler) temiz başlar ve kendi mekanizmalarıyla (WAL, LDF, AOF) kurtarılır.
- **`repo down --checkpoint`** durdurmadan önce süreç durumunu kaydeder, sonraki `repo up` otomatik geri yükler. **Bu, aynı makinedeki birincil akıştır** ve çalıştığı doğrulanmıştır.
- **`backup push --checkpoint`** etiketli konteynerler için çalışan süreçlerin bellek durumunu + disk durumunu yakalar, ardından birimi başka bir makineye aktarır. Hedef makinede `repo up` ile geri yüklenir.
- **`repo fork --checkpoint`** fork öncesi süreç durumunu yakalar ve checkpoint'i fork ile birlikte CoW-klonlar. ⚠️ Aynı makinede, ebeveyn hala çalışırken fork üzerindeki sonraki `repo up` **şu anda** `criu failed: type RESTORE errno 0` ile **başarısız olur**. Upstream CRIU hataları [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Yerinde kayıt/geri yükleme için `repo down --checkpoint`, makineler arası geçiş için `backup push --checkpoint` kullanın.
- **`repo up`** checkpoint verilerini otomatik algılar ve bulunursa geri yükler. Temiz başlatma için `--skip-checkpoint` kullanın.
- **Bağımlılık farkındalıklı geri yükleme**: Compose `depends_on` kullanarak veritabanlarını önce başlatır (healthy bekler), ardından uygulama konteynerlerini CRIU ile geri yükler.
- **TCP bağlantıları geri yüklemeden sonra eski olur**, uygulamalar `ECONNRESET` hatasını ele almalı ve yeniden bağlanmalıdır. CRIU, desteklenen hiçbir akışta geri yükleme boyunca aktif TCP bağlantı durumunu korumaz.
- **Docker deneysel modu** repo başına daemonlarda otomatik olarak etkinleştirilir.
- **CRIU yüklenir** `rdc config machine setup` sırasında.
- **`/etc/criu/runc.conf`** varsayılan olarak `tcp-established` ile yapılandırılır.
- **Konteyner güvenlik ayarları etiketli konteynerler için otomatik enjekte edilir**, `renet compose`, `rediacc.checkpoint=true` etiketli konteynerlere şunları ekler:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (çekirdek 5.9+ için minimum CRIU seti)
  - `security_opt`: `apparmor=unconfined` (CRIU'nun AppArmor desteği henüz kararlı değil)
  - `userns_mode: host` (CRIU, `/proc/pid/map_files` için init namespace erişimi gerektirir)
- Etiketi olmayan konteynerler daha temiz bir güvenlik profiliyle çalışır (ek capability yok).
- Docker'ın varsayılan seccomp profili korunur, CRIU, checkpoint/restore sırasında filtreleri geçici olarak askıya almak için `PTRACE_O_SUSPEND_SECCOMP` (çekirdek 4.3+) kullanır.
- **CRIU capability'lerini compose dosyanızda manuel olarak ayarlamayın**, renet etikete göre bununla ilgilenir.
- CRIU uyumlu referans uygulama için [heartbeat sablonuna](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) bakın.

### CRIU uyumlu uygulama kalıpları

- Tüm kalıcı bağlantılarda (veritabanı havuzları, websocket'ler, mesaj kuyrukları) `ECONNRESET`'i işleyin.
- Otomatik yeniden bağlanmayı destekleyen bağlantı havuzu kütüphaneleri kullanın.
- Dahili kütüphane nesnelerinden gelen eski soket hataları için güvenlik ağı olarak `process.on("uncaughtException")` ekleyin.
- Yeniden başlatma politikaları renet tarafından otomatik yönetilir (CRIU için kaldırılır, watchdog kurtarmayı üstlenir).
- Docker DNS'ine güvenmeyin, servisler arası iletişim için loopback IP'leri kullanın.

### İsletim sistemine göre host güvenlik politikaları

Resmi olarak desteklenen beş sunucu isletim sisteminde (bkz. [Gereksinimler](/en/docs/requirements)), her deponun Docker daemon'ı ve çalıştırdığı konteynerler **varsayılan konteyner etiketleri** kullanır. `rdc config machine setup`, özel bir SELinux politikası veya AppArmor profili yüklemez. Bu bilinçli bir tercihdir: ödünleşim, konteyner proseslerinin Rediacc'a özgü bir sınırlama profili değil, host işletim sisteminin varsayılan etiket politikası altında çalışmasıdır. Tehdit modeliniz konteyner katmanında zorunlu erişim kontrolleri gerektiriyorsa, bunları dağıtmadan önce host seviyesinde yapılandırın.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor varsayılan olarak etkindir. Konteynerler varsayılan docker-container profili altında çalışır. Tek istisna CRIU'dur (`rediacc.checkpoint=true` etiketli konteynerler için `apparmor=unconfined` eklenir, yukarıdaki nota bakın).
- **Fedora 43 / Oracle Linux 10**: SELinux varsayılan olarak enforcing modda çalışır. Konteynerler standart `container_t` bağlamını alır. Ek politika yüklenmesi gerekmez. Bir kurulum adımı AVC reddiyle başarısız olursa, bkz. [Sorun giderme: SELinux redleri](/en/docs/troubleshooting).
- **Debian 13**: AppArmor mevcut ancak tüm alanlarda varsayılan olarak uygulanmaz. Konteynerler yine de docker-container profilini kullanır.

Sonuç: `rdc` ve `renet` çalışan işletim sistemini otomatik algılar ve beş desteklenen dağıtımın tamamında aynı depo başına izolasyonu sağlar. İsletim sistemine özgü bir güvenlik duruş bayrağı gerekli değildir.

## Güvenlik

- **LUKS şifreleme** standart depolar için zorunludur. Her deponun kendi şifreleme anahtarı vardır.
- **Kimlik bilgileri CLI yapılandırmasında saklanır** (`~/.config/rediacc/rediacc.json`). Yapılandırmayı kaybetmek, şifreli birimlere erişimi kaybetmek anlamına gelir.
- **Kimlik bilgilerini asla** sürüm kontrolüne commit etmeyin. `env_file` kullanın ve sırları `up()` içinde oluşturun.
- **Depo izolasyonu**: Her deponun Docker daemon'ı, ağı ve depolaması aynı makinedeki diğer depolardan tamamen izole edilmiştir.
- **Ajan izolasyonu**: Yapay zeka ajanları varsayılan olarak yalnızca fork modunda çalışır. Her deponun, sunucu tarafında sandbox uygulaması (`sandbox-gateway` ForceCommand) olan kendi SSH anahtarı vardır. Tüm bağlantılar Landlock LSM, OverlayFS home overlay ve depo başına TMPDIR ile sandbox içine alınır. Depolar arası dosya sistemi erişimi çekirdek tarafından engellenir.
- **Bir depo sandbox'ı içinde `sudo` tasarım gereği devre dışıdır.** Landlock dosya sistemi izolasyonu `NoNewPrivs` gerektirir ve bu, herhangi bir yetki yükseltmesini engeller, bu nedenle `sudo` komutu `no new privileges flag is set` hatasıyla başarısız olur. Deponun sahip kullanıcısı, deponun bağlama noktası ve Docker soketi içindeki her şey için zaten gerekli izinlere sahiptir. Gerçekten ayrıcalıklı işlemler (host paketleri yükleme, çekirdek ayarlama) için bunları sandbox dışında ya da altyapı yolu tarafından çalıştırılan bir Rediaccfile `up()` fonksiyonundan çalıştırın.
- **Docker bridge ağı depo başına daemonlarda devre dışıdır.** Her deponun `daemon.json` (`FlavorRediacc`) dosyası `"bridge": "none"` ve `"iptables": false` içerir, bu nedenle düz bir `docker run <image>` komutu yalnızca loopback arayüzü olan ve dışa doğru bağlantısı olmayan bir konteyner oluşturur. Bu bir hata değil, depolar arası izolasyonun uygulanma biçimidir: bir deponun başka bir deponun loopback IP'lerine ulaşmasını engelleyen çekirdek düzeyindeki eBPF kancaları yalnızca host ağ ad alanında yaşayan konteynerlere uygulanır. Üretim servisleri için otomatik olarak `network_mode: host` enjekte eden `renet compose` kullanın. Bir kabukta tek seferlik, geçici konteynerler için `--network host` parametresini açıkça geçin. (Kullanıcı başına Hub daemonları (`FlavorHub`, geliştirme ortamları) istisnadır: `bridge="docker0"` ve `iptables=true` etkinleştirerek kullanıcı tarafından çalıştırılan konteynerlerin normal dışa bağlantı almasını sağlar.)

## Dağıtım

- **`rdc repo up`** LUKS birimi bağlı değilse otomatik olarak bağlar, ardından tüm Rediaccfile'larda `up()` çalıştırır.
- **`rdc repo down`** `down()` çalıştırır ve Docker daemon'ını durdurur.
- **`rdc repo down --unmount`** ayrıca LUKS birimini kapatır (şifreli depolamayı kilitler).
- **Fork'lar** (`rdc repo fork`) yeni GUID ve networkId ile bir CoW (copy-on-write) klon oluşturur ve bunu **depo boyutundan bağımsız olarak sabit sürede** yapar. BTRFS reflink veriyi değil görüntü meta verilerini çoğaltır, bu nedenle 100 GB'lık bir depo 1 GB'lık bir depo ile aynı birkaç saniyede fork edilir. Fork, üst öğenin şifreleme anahtarını paylaşır.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) grand deponun verilerini bir fork'un verileriyle değiştirir. Grand kimliğini korur (GUID, networkId, alan adları, otomatik başlatma, yedekleme zinciri). Eski üretim verileri yedekleme fork'u olarak korunur. Kullanım: fork üzerinde yükseltmeyi test edin, doğrulayın, ardından üretime takeover yapın. `rdc repo takeover --name <backup-fork> -m <machine>` ile geri alın.
- **Proxy yolları** dağıtımdan sonra yaklaşık 3 saniyede aktif olur. `repo up` sırasında "Proxy is not running" uyarısı ops/dev ortamlarında bilgilendirme amaçlıdır.
- **`rdc repo up` ve `rdc repo fork --up`, dağıtımın sonunda** `rediacc.service_port` ile etiketlenmiş servisler için URL kalıbını yazdırır. `{service}` yerine açığa çıkarılan servis adınızı yazarak tam URL'yi elde edin. `rediacc.service_port` olmayan servisler (veritabanları, işçiler) rota almaz ve gösterilmez.

## Yaygın hatalar

- `renet compose` yerine `docker compose` kullanmak, konteynerler ağ izolasyonu alamaz.
- Yeniden başlatma politikaları güvenlidir, renet bunları otomatik olarak kaldırır ve watchdog kurtarmayı üstlenir.
- `privileged: true` kullanmak, gerekli değildir, renet bunun yerine belirli CRIU capability'lerini enjekte eder.
- Ham IP'leri kalıcı yapılandırma dosyalarına sabit kodlamak, fork izolasyonunu sağlam tutmak için bağlantılarda servis adlarını kullanın.
- Başarısız komutlar için geçici çözüm olarak `rdc term connect -c` kullanmak, bunun yerine hataları bildirin.
- `repo delete` loopback IP'leri ve systemd birimlerini de dahil ederek tam temizlik yapar. Eski silmelerden kalan artıkları temizlemek için `rdc machine prune --name <name>` çalıştırın.
