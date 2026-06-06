---
title: "Sorun Giderme"
description: "SSH, kurulum, depo, hizmet ve Docker sorunlarının yaygın çözümleri."
category: "Guides"
order: 10
language: tr
sourceHash: "17dc03eb0589d606"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Sorun Giderme

Yaygın sorunlar ve bunları nasıl düzeltileceği. Emin olmadığınız durumlarda, tam bir tanı kontrolü çalıştırmak için `rdc doctor` komutuyla başlayın.

## SSH Bağlantısı Başarısız Oluyor

- Manuel olarak bağlanabildiğinizi doğrulayın: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Ana bilgisayar anahtarlarını yenilemek için `rdc config machine scan-keys -m server-1` komutunu çalıştırın
- SSH bağlantı noktasının eşleşip eşleşmediğini kontrol edin: `--port 22`
- Basit bir komutla test edin: `rdc term connect -m server-1 -c "hostname"`

## Ana Bilgisayar Anahtarı Uyuşmuyor

Bir sunucu yeniden yüklenirse veya SSH anahtarları değişirse, "host key verification failed" (ana bilgisayar anahtarı doğrulaması başarısız) hatası görürsünüz:

```bash
rdc config machine scan-keys -m server-1
```

Bu, yeni ana bilgisayar anahtarlarını alır ve yapılandırmanızı günceller.

## Makine Kurulumu Başarısız Oluyor

- SSH kullanıcısının parola olmaksızın sudo erişimine sahip olduğundan emin olun veya gerekli komutlar için `NOPASSWD` yapılandırın
- Sunucuda kullanılabilir disk alanını kontrol edin
- Ayrıntılı çıktı için `--debug` ile çalıştırın: `rdc config machine setup --name server-1 --debug`

## Dağıtıma Özgü Kurulum Sorunları

Resmi olarak desteklenen beş sunucu işletim sistemi (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) farklı güvenlik politikaları ve paket yöneticileriyle gelir. Çoğu kurulum sorunsuz işler; aşağıdaki durumlar çalışmayanları kapsar.

### SELinux İhlalleri (Fedora 43, Oracle Linux 10)

Her ikisi de SELinux'u zorla uygulama modunda çalıştırır. rdc setup özel bir SELinux politikası yüklemez; depo başına docker daemon standart `container_t` bağlamı altında çalışır. Kurulum AVC ihlalleriyle başarısız olursa, denetim günlüğünü kontrol edin ve etki alanını tanımlayın:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Veya:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Bir reddedilme renet ikilisini veya belirli bir dosya yolunu gösterirse, düzeltme neredeyse her zaman SELinux'u devre dışı bırakmak yerine yeniden etiketlemektir (`restorecon -v /path`). Araştırma yaparken geçici bir çözüm olarak, `sudo setenforce 0` sistemi izin verici moda taşır. Yeniden etiketlemenin işe yaradığını doğruladıktan sonra `sudo setenforce 1` ile yeniden etkinleştirin.

### AppArmor İhlalleri (Ubuntu 24.04, openSUSE Leap 16.0)

Her ikisi de varsayılan olarak AppArmor çalıştırır; depo başına docker daemon varsayılan kapsayıcı profilini kullanır. Bir depodaki bir kapsayıcı engelleniyorsa:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU, AppArmor'u vuran bilinen bir durumdur. renet, `rediacc.checkpoint=true` etiketli kapsayıcılarda otomatik olarak `security_opt: apparmor=unconfined` ayarını yapar. Başka bir şey için AppArmor profillerini kendiniz yapılandırmanız gerekmez. [Rediacc Kuralları](/en/docs/rules-of-rediacc) bölümündeki CRIU notlarına bakın.

### Paket Yöneticisi Hata İmzaları

| İşletim Sistemi | Paket Yöneticisi | Tipik Hata | Çözüm |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Köken arkasında Cloudflare edge cache. ~15s sonra `apt-get update`'i yeniden deneyin; bütünlük kontrolü sonraki ankette geçer. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Diskte önbelleğe alınan RPM depo meta verileri eski. `sudo dnf clean all && sudo dnf makecache` komutunu çalıştırın. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | `sudo zypper refresh rediacc` komutunu bir kez çalıştırın; sonraki yüklemeler başarılı olmalıdır. |

### btrfs Modülü Eksik (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

`rdc config machine setup` veya `renet system check-btrfs` şu hatalarla başarısız olursa:

```
Module btrfs not found
```

...sunucu RHEL 10'un standart çekirdeğini çalıştırıyor; bu, ağaçta btrfs modülü olmadan gelir. Bu bir Rediacc hatası değildir; RHEL 10 btrfs'i kasıtlı olarak bıraktı. Düzeltme **bunun yerine Oracle Linux 10 çalıştırmaktır**. Oracle 10, btrfs'i koruyan Unbreakable Enterprise Kernel (UEK) varsayılanlarına sahiptir. Tam hikaye için [Gereksinimler: Neden UEK?](/en/docs/requirements) bölümüne bakın.

## Depo Oluşturma Başarısız Oluyor

- Kurulumun tamamlandığını doğrulayın: datastore dizini var olmalıdır
- Sunucuda disk alanını kontrol edin
- renet ikilisinin yüklendiğinden emin olun (gerekirse kurulumu tekrar çalıştırın)

## Hizmetler Başlamıyor

- Rediaccfile söz dizimini kontrol edin: geçerli Bash olmalıdır
- Rediaccfile'ınızın `renet compose --` (değil `docker compose`) kullandığından emin olun
- Docker görüntülerinin erişilebilir olduğunu doğrulayın (`up()` içinde `renet compose -- pull` kullanmayı düşünün)
- Deponun Docker soketi kullanarak kapsayıcı günlüklerini kontrol edin:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Veya tüm kapsayıcıları görüntüleyin:

```bash
rdc machine containers --name server-1
```

## İzin Reddedildi Hataları

- Depo işlemleri sunucuda kök gerektirir (renet `sudo` aracılığıyla çalışır)
- SSH kullanıcınızın `sudo` grubunda olduğunu doğrulayın
- Datastore dizininin doğru izinlere sahip olduğunu kontrol edin

## Docker Soketi Sorunları

Her depo kendi Docker daemon'unu vardır. Docker komutlarını manuel olarak çalıştırırken, doğru soketi belirtmeniz gerekir:

```bash
# rdc term (otomatik yapılandırma) kullanarak:
rdc term connect -m server-1 -r my-app -c "docker ps"

# Veya soketi manual olarak belirterek:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816` öğesini depo ağ kimliğinizle değiştirin (`rediacc.json` veya `rdc repo status` içinde bulunur).

## `docker run` ağa sahip değil, `apt update` başarısız, `curl` askıda kalıyor

Bir depo kabuğu içinde, `--network host` olmadan bir kapsayıcı çalıştırmak yalnızca bir loopback arabirimi, DNS yok ve giden bağlantı olmayan izole bir kapsayıcı verir. `apt update`, `pip install`, `curl https://...` veya herhangi bir ağ getirme gibi komutlar DNS hataları ile hemen başarısız olur.

Bu kasıtlıdır. Rediacc'ın ağ modeli `renet compose` tarafından zorlanan **her hizmet için ana bilgisayar ağlarıdır**. NAT ile varsayılan bir Docker köprüsü, bir depoyu başka bir deponun hizmetlerine ulaşmasını engelleyen çekirdek düzeyinde loopback yalıtımını atlatacaktır, bu nedenle depo başına Docker daemon (`FlavorRediacc`) `"bridge": "none"` ve `"iptables": false` ile yapılandırılmıştır. Düz bir `docker run` kapsayıcısının bağlanması için yönlendirilebilir bir köprü yoktur. (Geliştirme ortamları tarafından kullanılan kullanıcı başına Hub daemon'ları (`FlavorHub`) istisnadır: kullanıcı tarafından çalıştırılan kapsayıcıların giden ağa sahip olması için köprü ve iptables'ı etkinleştirirler.)

**Geçici bir kapsayıcıda ağ erişimi sağlamak için ana bilgisayar ağını kullanın:**

```bash
# Bir depo kabuğu içinde (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Şimdi apt update, curl, pip install hepsi çalışır.
```

**Üretim hizmetleri için, ham `docker run` yerine `renet compose` ile bir Rediaccfile kullanın**. `renet compose` otomatik olarak `network_mode: host`, hizmet IP etiketleri ve Traefik yönlendirme etiketlerini enjekte eder. Ayrıntılar için [Hizmetler](/en/docs/services) bölümüne bakın.

## VS Code Sandbox Dosyalarında İzin Reddedildi

`rdc vscode connect -m <machine> -r <repo>` ile önceki bir VS Code oturumundan sonra bağlantı kurarken, eski renet sürümleri `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` gibi hatalar üretti. Neden: sandbox dizini içinde karışık dosya sahipliği, burada SSH kullanıcınız ve dahili `rediacc` kullanıcısı dosya yazmışlardır.

Renet'in modern sürümleri bunu şu şekilde düzeltir:

- Depo başına sandbox çalışma alanı (`/mnt/rediacc/.interim/sandbox/<repo>/`) `rediacc` grubu ve set-group-ID biti (mod `2775`) ile oluşturma, böylece altında yazılan her dosya doğru grubu devralır.
- Sandbox çalışma zamanı içinde umask `002` uygulama, böylece yeni dosyalar grup yazılabilir (`0664`/`0775`) oluşturulur.
- Başlangıçta mevcut `.vscode-server/` alt ağacını normalleştirme, böylece düzeltmeden önceki eski dosyalar otomatik olarak onarılır.

Yine de izin hataları görürseniz, normalleştirme geçişinin çalışması için makinede bir kabuktan bir kez `sudo systemctl restart rediacc-docker-<network-id>` ile deponun Docker daemon'ını yeniden başlatın, ardından `rdc vscode connect`'i yeniden deneyin.

## Renet Yükseltmesinden Sonra Daemon Başlamıyor

Her başlangıçtan önce, `renet daemon start-foreground` geçerli şablonlardan depo yapılandırma dizinindeki `daemon.json` ve `containerd.toml`'yi yeniden yazar, böylece yapılandırması eski bir renet sürümü tarafından oluşturulan bir depo otomatik olarak yeni biçimi alır. Herhangi bir göç komutu çalıştırmanız gerekmez ve systemd birimini manuel olarak yeniden oluşturmanız gerekmez. Hizmeti yeniden başlatmanız yeterli:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Birim hâlâ başarısız oluyorsa, belirli bir hata için günlüğü kontrol edin:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Yanlış Docker Daemon'unda Oluşturulan Kapsayıcılar

Kapsayıcılarınız depo'nun izole daemon'u yerine ana bilgisayar sisteminin Docker daemon'unda görülürse, en yaygın neden Rediaccfile içinde `sudo docker` kullanmaktır.

`sudo` ortam değişkenlerini sıfırlar, bu nedenle `DOCKER_HOST` kaybolur ve Docker sistem soketine varsayılan olur (`/var/run/docker.sock`). Rediacc bunu otomatik olarak engeller, ancak bununla karşılaşırsanız:

- **`docker`'ı doğrudan kullanın**, Rediaccfile işlevleri zaten yeterli ayrıcalıklarla çalışır
- Sudo kullanmanız gerekiyorsa, ortam değişkenlerini korumak için `sudo -E docker` kullanın
- Rediaccfile'ınızda herhangi bir `sudo docker` komutu olup olmadığını kontrol edin ve `sudo`'yu kaldırın

## Terminal Çalışmıyor

`rdc term` terminal penceresi açılamadığında:

- Komutları doğrudan çalıştırmak için `-c` ile satır içi modu kullanın:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Satır içi mod sorunları varsa `--external` ile harici terminali zorlayın
- Linux'ta, `gnome-terminal`, `xterm` veya başka bir terminal emulatörünün yüklü olduğundan emin olun

## Tanı Çalıştırın

```bash
rdc doctor
```

Bu, ortamınız, renet kurulumu, yapılandırması ve kimlik doğrulama durumunu kontrol eder. Her kontrol kısa bir açıklama ile OK, Uyarı veya Hata rapor eder.
