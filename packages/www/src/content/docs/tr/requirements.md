---
title: Gereksinimler
description: Rediacc'ı çalıştırmak için sistem gereksinimleri ve desteklenen platformlar.
category: Guides
order: 0
language: tr
sourceHash: 40a59ab9c9625911
---

# Gereksinimler

Hangi aracı kullanacağınızdan emin değilseniz [rdc vs renet](/tr/docs/rdc-vs-renet) sayfasına bakın.

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

### Desteklenen İşletim Sistemleri

| İS | Sürüm | Mimari |
|----|-------|--------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |
| Alpine | 3.19+ | x86_64 (gcompat gerektirir) |
| Arch Linux | Rolling release | x86_64 |

Bunlar CI'da test edilen dağıtımlardır. systemd, Docker desteği ve cryptsetup bulunan diğer Linux dağıtımları çalışabilir ancak resmi olarak desteklenmez.

### Sunucu Ön Koşulları

- `sudo` yetkisine sahip bir kullanıcı hesabı (parolasız sudo önerilir)
- SSH genel anahtarınızın `~/.ssh/authorized_keys` dosyasına eklenmiş olması
- En az 20 GB boş disk alanı (iş yüklerinize bağlı olarak daha fazla gerekebilir)
- Docker imajlarını çekmek için internet erişimi (veya özel bir registry)

### Otomatik Olarak Kurulanlar

`rdc config setup-machine` komutu aşağıdakileri uzak sunucuya kurar:

- **Docker** ve **containerd** (konteyner çalışma zamanı)
- **cryptsetup** (LUKS disk şifreleme)
- **renet** ikili dosyası (SFTP aracılığıyla yüklenir)

Bunları manuel olarak kurmanıza gerek yoktur.

## Local Virtual Machines (Optional)

If you want to test deployments locally using `rdc ops`, your workstation needs virtualization support: KVM on Linux or QEMU on macOS. See the [Experimental VMs](/tr/docs/experimental-vms) guide for setup steps and platform details.
