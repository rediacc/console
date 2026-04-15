---
title: Gereksinimler
description: Rediacc'ı çalıştırmak için sistem gereksinimleri ve desteklenen platformlar.
category: Guides
order: 0
language: tr
sourceHash: "eb237c7beb1bb942"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Gereksinimler

Rediacc ile dağıtım yapmadan önce, iş istasyonunuzun ve uzak sunucularınızın aşağıdaki gereksinimleri karşıladığından emin olun.

## İş İstasyonu (Kontrol Düzlemi)

`rdc` CLI iş istasyonunuzda çalışır ve uzak sunucuları SSH üzerinden yönetir.

| Platform | Minimum Sürüm | Notlar |
|----------|---------------|--------|
| macOS | 12 (Monterey)+ | Intel ve Apple Silicon desteklenir |
| Linux (x86_64) | Herhangi bir modern dağıtım | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | PowerShell yükleyici ile yerel destek |

**Ek gereksinimler:**
- Bir SSH anahtar çifti (örn., `~/.ssh/id_ed25519` veya `~/.ssh/id_rsa`)
- Uzak sunucularınıza SSH portu üzerinden ağ erişimi (varsayılan: 22)

## Uzak Sunucu (Veri Düzlemi)

`renet` ikili dosyası uzak sunucularda root yetkileriyle çalışır. Şifrelenmiş disk imajlarını, izole Docker daemon'larını ve servis orkestrasyonunu yönetir.

Hangi aracı kullanacağınızdan emin değilseniz [rdc vs renet](/en/docs/rdc-vs-renet) sayfasına bakın. Kısaca: normal işlemler için `rdc` kullanın, `renet`'i ise yalnızca sunucu tarafındaki gelişmiş görevler için doğrudan kullanın.

### Desteklenen İşletim Sistemleri

Uzak sunucular `renet` ikili dosyasını çalıştırır ve her repo için şifrelenmiş ve izole edilmiş Docker daemon'larını barındırır. Aşağıdaki beş dağıtım, her pull request'te CI'daki Bridge Workers matrisi tarafından test edilmekte olup resmi olarak desteklenen tek dağıtımlardır:

| İS | Sürüm | Varsayılan Çekirdek | Notlar |
|----|-------|---------------------|--------|
| Ubuntu | 24.04 LTS | 6.8 | Önerilen. AppArmor varsayılan olarak etkin. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 de çalışır (minimum çekirdek 6.1). |
| Fedora | 43 | 6.12 | SELinux varsayılan olarak enforcing modunda. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor varsayılan olarak etkin. |
| Oracle Linux | 10 | UEK 7+ | btrfs modülünü koruyan UEK kullanır. SELinux varsayılan olarak enforcing modunda. Aşağıdaki "Neden UEK?" bölümüne bakın. |

Tüm satırlar `x86_64` içindir. `arm64` derlenmektedir ancak her sunucu işletim sistemi için sürekli test edilmemektedir; belirli bir dağıtımda ihtiyaç duyarsanız bir issue açın. systemd, Docker desteği ve cryptsetup bulunan diğer Linux dağıtımları çalışabilir, ancak resmi olarak desteklenmez ve yükseltmelerde önceden haber verilmeksizin bozulabilir.

#### Neden UEK? (ve Rocky 10 / standart RHEL 10 neden desteklenmiyor)

Rediacc'ın şifrelenmiş depolama arka ucu, ağaç içi `btrfs` çekirdek modülünü gerektirir. **RHEL 10'un standart çekirdeği bu modül olmadan gönderilmektedir**: `modprobe btrfs`, "Module btrfs not found" hatasıyla başarısız olur ve `dnf search btrfs` hiçbir şey döndürmez. Rocky Linux 10 ve AlmaLinux 10 aynı çekirdeği devraldığından Rediacc sunucusu olarak çalışamazlar.

Oracle Linux 10 varsayılan olarak **Unbreakable Enterprise Kernel (UEK)** kullanır ve bu çekirdek btrfs'i yerleşik olarak korur. Bu, desteklenen listede yer alan tek RHEL uyumlu hedeftir. Mutlaka bir RHEL ailesi sunucu kullanmanız gerekiyorsa UEK ile Oracle Linux 10 kullanın. (Bu kararın gerçek kaynağı `.github/workflows/ct-tests.yml` dosyasında CI Bridge Workers matrisi olarak yer almaktadır.)

#### Yalnızca İş İstasyonu (CLI kurulum hedefleri)

`rdc` CLI ayrıca Alpine 3.19+ (otomatik olarak kurulan `gcompat` uyumluluk katmanıyla APK) ve Arch Linux'ta (rolling, pacman aracılığıyla) temiz bir şekilde kurulur. Bunlar yalnızca istemci tarafı kurulum yollarıdır ([Kurulum](/en/docs/installation) sayfasına bakın) ve `renet` sunucu hedefi olarak desteklenmez.

### İşletim Sistemine Göre Güvenlik Politikaları

Her repo için Docker daemon'u ve repo konteynerlerinin kendisi, desteklenen tüm işletim sistemlerinde **varsayılan konteyner etiketleriyle** çalışır. `rdc config machine setup`, özel SELinux politikaları veya AppArmor profilleri kurmaz. İşletim sistemine göre davranış:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor varsayılan olarak etkindir. Varsayılan docker-container profili uygulanır; ek kurulum gerekmez.
- **Fedora 43, Oracle Linux 10**: SELinux enforcing modunda çalışır. Her repo için daemon, konteynerleri standart `container_t` bağlamıyla etiketler. Özel SELinux politikasına gerek yoktur.
- **CRIU** (checkpoint/restore), `apparmor=unconfined` ile AppArmor profilini atlayan tek durumdur; çünkü upstream CRIU'nun AppArmor desteği henüz kararlı değildir. [Rediacc Kuralları](/en/docs/rules-of-rediacc)'ndaki CRIU notlarına bakın.

Bir kurulum adımı SELinux AVC reddi veya AppArmor reddiyle başarısız olursa [Sorun Giderme](/en/docs/troubleshooting) sayfasının "Dağıtıma Özgü Kurulum Sorunları" bölümüne bakın.

### Sunucu Ön Koşulları

- `sudo` yetkisine sahip bir kullanıcı hesabı (parolasız sudo önerilir)
- SSH genel anahtarınızın `~/.ssh/authorized_keys` dosyasına eklenmiş olması
- En az 20 GB boş disk alanı (iş yüklerinize bağlı olarak daha fazla gerekebilir)
- Docker imajlarını çekmek için internet erişimi (veya özel bir registry)

### Otomatik Olarak Kurulanlar

`rdc config machine setup` komutu aşağıdakileri uzak sunucuya kurar:

- **Docker** ve **containerd** (konteyner çalışma zamanı)
- **cryptsetup** (LUKS disk şifreleme)
- **renet** ikili dosyası (SFTP aracılığıyla yüklenir)

Bunları manuel olarak kurmanıza gerek yoktur.

## Yerel Sanal Makineler (İsteğe Bağlı)

`rdc ops` kullanarak dağıtımları yerel olarak test etmek istiyorsanız, iş istasyonunuzun sanallaştırma desteğine ihtiyacı vardır: Linux'ta KVM veya macOS'ta QEMU. Kurulum adımları ve platform ayrıntıları için [Deneysel VM'ler](/en/docs/experimental-vms) kılavuzuna bakın.
