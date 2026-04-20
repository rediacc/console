---
title: Sorun Giderme
description: >-
  SSH, kurulum, depolar, servisler ve Docker ile ilgili yaygın sorunların
  çözümleri.
category: Guides
order: 10
language: tr
sourceHash: 54e552831b2b125c
sourceCommit: d5c06171af0ef58b551a9682905d98af81e496cd
---

# Sorun Giderme

Yaygın sorunlar ve çözümleri. Şüphe durumunda, kapsamlı bir tanılama kontrolü yapmak için `rdc doctor` ile başlayın.

## SSH Bağlantısı Başarısız

- Manuel olarak bağlanabildiğinizi doğrulayın: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Host anahtarlarını yenilemek için `rdc config machine scan-keys --name server-1` komutunu çalıştırın
- SSH portunun eşleştiğini kontrol edin: `--port 22`
- Basit bir komutla test edin: `rdc term connect -m server-1 -c "hostname"`

## Host Anahtarı Uyuşmazlığı

Bir sunucu yeniden kurulduysa veya SSH anahtarları değiştiyse, "host key verification failed" hatası görürsünüz:

```bash
rdc config machine scan-keys -m server-1
```

Bu komut yeni host anahtarlarını alır ve yapılandırmanızı günceller.

## Makine Kurulumu Başarısız

- SSH kullanıcısının şifresiz sudo erişimine sahip olduğundan emin olun veya gerekli komutlar için `NOPASSWD` yapılandırın
- Sunucudaki kullanılabilir disk alanını kontrol edin
- Ayrıntılı çıktı için `--debug` ile çalıştırın: `rdc config machine setup --name server-1 --debug`

## Dağıtıma Özgü Kurulum Sorunları

Resmi olarak desteklenen beş sunucu işletim sistemi (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) farklı güvenlik politikaları ve paket yöneticileriyle gelir. Kurulumların büyük çoğunluğu sorunsuz çalışır; aşağıdaki durumlar çalışmayan durumları kapsar.

### SELinux Redleri (Fedora 43, Oracle Linux 10)

Her ikisi de SELinux'u zorlayıcı (enforcing) modda çalıştırır. rdc setup özel bir SELinux politikası yüklemez; depo başına docker daemon standart `container_t` bağlamında çalışır. Kurulum AVC redleriyle başarısız olursa, audit günlüğünü kontrol edin ve etki alanını belirleyin:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Veya:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Bir red renet ikili dosyasına veya belirli bir dosya yoluna işaret ediyorsa, çözüm neredeyse her zaman SELinux'u devre dışı bırakmak yerine yeniden etiketlemektir (`restorecon -v /path`). Araştırma sırasında geçici bir çözüm olarak `sudo setenforce 0` sistemi izinli moda alır. Yeniden etiketlemenin kalıcı olduğunu doğruladıktan sonra `sudo setenforce 1` ile yeniden etkinleştirin.

### AppArmor Redleri (Ubuntu 24.04, openSUSE Leap 16.0)

Her ikisi de varsayılan olarak AppArmor kullanır; depo başına docker daemon varsayılan konteyner profilini kullanır. Bir depodaki konteyner engelleniyorsa:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU, AppArmor ile karşılaşan bilinen durumdur. Renet, `rediacc.checkpoint=true` etiketli konteynerlere otomatik olarak `security_opt: apparmor=unconfined` ayarlar. Bunun dışında herhangi bir şey için AppArmor profillerini kendiniz yapılandırmanıza gerek yoktur. CRIU notları için [Rediacc Kuralları](/en/docs/rules-of-rediacc) sayfasına bakın.

### Paket Yöneticisi Hata İmzaları

| İşletim Sistemi | Paket Yöneticisi | Tipik Hata | Çözüm |
|---|---|---|---|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare edge cache kaynağın gerisinde. `apt-get update` komutunu ~15 saniye sonra yeniden deneyin; bütünlük denetimi bir sonraki sorguda geçer. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Diskte önbelleğe alınmış RPM depo meta verileri güncel değil. `sudo dnf clean all && sudo dnf makecache` komutunu çalıştırın. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | `sudo zypper refresh rediacc` komutunu bir kez çalıştırın; sonraki kurulumlar başarılı olacaktır. |

### btrfs Modülü Eksik (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

`rdc config machine setup` veya `renet system check-btrfs` aşağıdaki hatayla başarısız olursa:

```
Module btrfs not found
```

...sunucu, yerleşik btrfs modülü olmadan gelen RHEL 10'un stok çekirdeğini çalıştırıyordur. Bu bir Rediacc hatası değildir; RHEL 10 btrfs'i kasıtlı olarak kaldırdı. Çözüm, **bunun yerine Oracle Linux 10 kullanmaktır**. Oracle 10 varsayılan olarak btrfs'i koruyan Unbreakable Enterprise Kernel (UEK) kullanır. Tam hikaye için [Gereksinimler -- Neden UEK?](/en/docs/requirements) sayfasına bakın.

## Depo Oluşturma Başarısız

- Kurulumun tamamlandığını doğrulayın: veri deposu dizini mevcut olmalıdır
- Sunucudaki disk alanını kontrol edin
- renet ikili dosyasının yüklü olduğundan emin olun (gerekirse kurulumu yeniden çalıştırın)

## Servisler Başlatılamıyor

- Rediaccfile sözdizimini kontrol edin: geçerli Bash olmalıdır
- Rediaccfile'ınızın `renet compose --` kullandığından emin olun (`docker compose` değil)
- Docker imajlarının erişilebilir olduğunu doğrulayın (`up()` içinde `renet compose -- pull` kullanmayı düşünün)
- Deponun Docker soketi üzerinden konteyner günlüklerini kontrol edin:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Veya tüm konteynerleri görüntüleyin:

```bash
rdc machine containers --name server-1
```

## İzin Reddedildi Hataları

- Depo işlemleri sunucuda root gerektirir (renet `sudo` ile çalışır)
- SSH kullanıcınızın `sudo` grubunda olduğunu doğrulayın
- Veri deposu dizininin doğru izinlere sahip olduğunu kontrol edin

## Docker Soket Sorunları

Her deponun kendi Docker daemon'u vardır. Docker komutlarını manuel olarak çalıştırırken doğru soketi belirtmeniz gerekir:

```bash
# rdc term kullanarak (otomatik yapılandırılmış):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Veya soket ile manuel olarak:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816` değerini deponuzun ağ kimliği ile değiştirin (`rediacc.json` veya `rdc repo status` içinde bulunabilir).

## `docker run` ağı yok, `apt update` başarısız, `curl` yanıt vermiyor

Bir depo kabuğu içinde, bir konteyneri `--network host` olmadan çalıştırmak, yalnızca loopback arayüzü olan, DNS içermeyen ve dışa doğru bağlantısı olmayan izole bir konteyner verir. `apt update`, `pip install`, `curl https://...` gibi komutlar ya da herhangi bir ağ isteği DNS hatalarıyla anında başarısız olur.

Bu kasıtlıdır. Rediacc'in ağ modeli, `renet compose` tarafından zorunlu kılınan **her servis için host ağı**dır. NAT'lı varsayılan bir Docker bridge'i, bir deponun başka bir deponun servislerine ulaşmasını engelleyen çekirdek düzeyindeki loopback izolasyonunu atlayacağı için, depo başına Docker daemon'u `"bridge": "none"` ve `"iptables": false` ile yapılandırılır. Düz bir `docker run` konteynerinin bağlanabileceği yönlendirilebilir bir bridge yoktur.

**Geçici bir konteynerde ağ erişimi elde etmek için host ağını kullanın:**

```bash
# Bir depo kabuğunda (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Artık apt update, curl, pip install komutlarının tamamı çalışır.
```

**Üretim servisleri için ham `docker run` yerine `renet compose` ile bir Rediaccfile kullanın.** `renet compose`, `network_mode: host`, servis IP etiketleri ve Traefik yönlendirme etiketlerini otomatik olarak enjekte eder. Ayrıntılar için [Servisler](/tr/docs/services) sayfasına bakın.

## VS Code sandbox dosyalarında İzin Reddedildi

`rdc vscode connect -m <machine> -r <repo>` ile bağlanırken, önceki bir VS Code oturumundan sonra `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` gibi hatalar görmüş olabilirsiniz. Bu, sandbox dizini içinde hem SSH kullanıcınız hem de dahili `rediacc` kullanıcısı tarafından yazılmış dosyaların karışık sahipliğinden kaynaklanıyordu.

Renet'in modern sürümleri bunu şu şekilde düzeltir:

- Depo başına sandbox çalışma alanını (`/mnt/rediacc/.interim/sandbox/<repo>/`) `rediacc` grubu ve set-group-ID biti (mod `2775`) ile oluşturur, böylece altına yazılan her dosya doğru grubu devralır.
- Sandbox çalışma zamanı içinde `002` umask'ini uygular, böylece yeni dosyalar grup yazılabilir (`0664`/`0775`) olarak oluşturulur.
- Başlatmada mevcut bir `.vscode-server/` alt ağacını normalize eder, böylece düzeltmeden önceki eski dosyalar otomatik olarak onarılır.

Yine de izin hatalarıyla karşılaşırsanız, normalize işleminin çalışması için makinedeki bir kabuktan `sudo systemctl restart rediacc-docker-<network-id>` komutuyla deponun Docker daemon'unu bir kez yeniden başlatın, ardından `rdc vscode connect` komutunu tekrar deneyin.

## Renet yükseltmesinden sonra daemon başlatılamıyor

Her başlatmadan önce `renet daemon start-foreground`, deponun yapılandırma dizinindeki `daemon.json` ve `containerd.toml` dosyalarını mevcut şablonlardan yeniden yazar, bu nedenle yapılandırması daha eski bir renet sürümüyle oluşturulmuş bir depo, yeni formatı otomatik olarak alır. Herhangi bir göç komutu çalıştırmanıza gerek yoktur ve systemd birimini manuel olarak yeniden oluşturmanız gerekmez. Yalnızca servisi yeniden başlatın:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Birim hâlâ başarısız oluyorsa, belirli bir hata için günlüğü kontrol edin:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Konteynerler Yanlış Docker Daemon'da Oluşturulmuş

Konteynerleriniz deponun izole daemon'u yerine ana sistemin Docker daemon'unda görünüyorsa, en yaygın neden Rediaccfile içinde `sudo docker` kullanımıdır.

`sudo` ortam değişkenlerini sıfırlar, bu nedenle `DOCKER_HOST` kaybolur ve Docker varsayılan olarak sistem soketini (`/var/run/docker.sock`) kullanır. Rediacc bunu otomatik olarak engeller, ancak karşılaşırsanız:

- **`docker` komutunu doğrudan kullanın**, Rediaccfile fonksiyonları zaten yeterli yetkilerle çalışır
- sudo kullanmanız gerekiyorsa, ortam değişkenlerini korumak için `sudo -E docker` kullanın
- Rediaccfile dosyanızı `sudo docker` komutları için kontrol edin ve `sudo` kısmını kaldırın

## Terminal Çalışmıyor

`rdc term` bir terminal penceresi açamıyorsa:

- Komutları doğrudan çalıştırmak için `-c` ile satır içi modu kullanın:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Satır içi modda sorun varsa `--external` ile harici terminali zorlayın
- Linux'ta `gnome-terminal`, `xterm` veya başka bir terminal emülatörünün yüklü olduğundan emin olun

## Tanılama Çalıştırma

```bash
rdc doctor
```

Bu komut ortamınızı, renet kurulumunu, yapılandırmayı ve kimlik doğrulama durumunu kontrol eder. Her kontrol OK, Warning veya Error durumunu kısa bir açıklama ile bildirir.
