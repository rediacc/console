---
title: "Deneysel VM'ler"
description: "rdc ops ile geliştirme ve test için yerel VM kümeleri oluşturma."
category: "Concepts"
order: 2
language: tr
sourceHash: "fa4069c48c650a79"
---

# Deneysel VM'ler

İş istasyonunuzda geliştirme ve test için yerel VM kümeleri oluşturun — harici bulut sağlayıcılarına gerek yok.

## Gereksinimler

`rdc ops` **yerel adaptör** gerektirir. Bulut adaptörüyle kullanılamaz.

```bash
rdc ops check
```

## Genel Bakış

`rdc ops` komutları, deneysel VM kümelerini yerel olarak oluşturmanıza ve yönetmenize olanak tanır. Bu, CI hattı tarafından entegrasyon testleri için kullanılan altyapının aynısıdır ve artık uygulamalı deneyler için kullanılabilir.

Kullanım senaryoları:
- Harici VM sağlayıcıları olmadan Rediacc dağıtımlarını test edin (Linode, Vultr, vb.)
- Depo yapılandırmalarını yerel olarak geliştirin ve hata ayıklayın
- Tamamen izole bir ortamda platformu öğrenin
- İş istasyonunuzda entegrasyon testleri çalıştırın

## Platform Desteği

| Platform | Mimari | Arka Uç | Durum |
|----------|--------|---------|-------|
| Linux | x86_64 | KVM (libvirt) | CI'da test edildi |
| macOS | Intel | QEMU + HVF | CI'da test edildi |
| Linux | ARM64 | KVM (libvirt) | Destekleniyor (CI testi yok) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Destekleniyor (CI testi yok) |
| Windows | x86_64 / ARM64 | Hyper-V | Planlandı |

**Linux (KVM)**, köprülü ağ ile yerel donanım sanallaştırması için libvirt kullanır.

**macOS (QEMU)**, kullanıcı modu ağ ve SSH port yönlendirmesiyle neredeyse yerel performans için Apple'ın Hypervisor Framework (HVF) ile QEMU kullanır.

**Windows (Hyper-V)** desteği planlanmaktadır. Ayrıntılar için [issue #380](https://github.com/rediacc/console/issues/380) sayfasına bakın. Windows Pro/Enterprise gerektirir.

## Ön Koşullar ve Kurulum

### Linux

```bash
# Ön koşulları otomatik kur
rdc ops setup

# Veya manuel olarak:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Ön koşulları otomatik kur
rdc ops setup

# Veya manuel olarak:
brew install qemu cdrtools
```

### Kurulumu Doğrulama

```bash
rdc ops check
```

Bu komut platforma özgü kontroller çalıştırır ve her ön koşul için başarı/başarısızlık raporlar.

## Hızlı Başlangıç

```bash
# 1. Ön koşulları kontrol et
rdc ops check

# 2. Minimal küme hazırla (köprü + 1 çalışan)
rdc ops up --basic

# 3. VM durumunu kontrol et
rdc ops status

# 4. Köprü VM'ye SSH ile bağlan
rdc ops ssh 1

# 4b. Veya doğrudan bir komut çalıştır
rdc ops ssh 1 hostname

# 5. Kapat
rdc ops down
```

## Küme Bileşimi

Varsayılan olarak `rdc ops up` şunları hazırlar:

| VM | Kimlik | Rol |
|----|--------|-----|
| Köprü | 1 | Birincil düğüm — Rediacc köprü servisini çalıştırır |
| Çalışan 1 | 11 | Depo dağıtımları için çalışan düğüm |
| Çalışan 2 | 12 | Depo dağıtımları için çalışan düğüm |

Yalnızca köprüyü ve ilk çalışanı hazırlamak için `--basic` bayrağını kullanın (kimlik 1 ve 11).

Rediacc servislerini başlatmadan VM'leri hazırlamak için `--skip-orchestration` kullanın — VM katmanını izole test etmek için kullanışlıdır.

## Yapılandırma

Köprü VM, çalışan VM'lerden daha küçük varsayılanlar kullanır:

| VM Rolü | CPU | RAM | Disk |
|---------|-----|-----|------|
| Köprü | 1 | 1024 MB | 8 GB |
| Çalışan | 2 | 4096 MB | 16 GB |

Ortam değişkenleri çalışan VM kaynaklarını geçersiz kılar:

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `VM_CPU` | 2 | Çalışan VM başına CPU çekirdeği |
| `VM_RAM` | 4096 | Çalışan VM başına MB cinsinden RAM |
| `VM_DSK` | 16 | Çalışan VM başına GB cinsinden disk boyutu |
| `VM_NET_BASE` | 192.168.111 | Ağ tabanı (yalnızca KVM) |
| `RENET_DATA_DIR` | ~/.renet | VM diskleri ve yapılandırma için veri dizini |

## Komut Referansı

| Komut | Açıklama |
|-------|----------|
| `rdc ops setup` | Platform ön koşullarını kur (KVM veya QEMU) |
| `rdc ops check` | Ön koşulların kurulu ve çalışır durumda olduğunu doğrula |
| `rdc ops up [seçenekler]` | VM kümesi hazırla |
| `rdc ops down` | Tüm VM'leri yok et ve temizle |
| `rdc ops status` | Tüm VM'lerin durumunu göster |
| `rdc ops ssh <vm-id> [komut...]` | Bir VM'ye SSH ile bağlan veya üzerinde komut çalıştır |

### `rdc ops up` Seçenekleri

| Seçenek | Açıklama |
|---------|----------|
| `--basic` | Minimal küme (köprü + 1 çalışan) |
| `--lite` | VM hazırlamayı atla (yalnızca SSH anahtarları) |
| `--force` | Mevcut VM'leri yeniden oluşturmaya zorla |
| `--parallel` | VM'leri paralel olarak hazırla |
| `--skip-orchestration` | Yalnızca VM'ler, Rediacc servisleri yok |
| `--backend <kvm\|qemu>` | Otomatik algılanan arka ucu geçersiz kıl |
| `--os <ad>` | İşletim sistemi imajı (varsayılan: ubuntu-24.04) |
| `--debug` | Ayrıntılı çıktı |

## Platform Farklılıkları

### Linux (KVM)
- VM yaşam döngüsü yönetimi için libvirt kullanır
- Köprülü ağ — VM'ler sanal ağda IP alır (192.168.111.x)
- VM IP'lerine doğrudan SSH
- `/dev/kvm` ve libvirtd servisi gerektirir

### macOS (QEMU + HVF)
- PID dosyaları aracılığıyla yönetilen QEMU süreçleri kullanır
- SSH port yönlendirmeli kullanıcı modu ağ (localhost:222XX)
- Doğrudan IP değil, yönlendirilen portlar üzerinden SSH
- `mkisofs` ile oluşturulan Cloud-init ISO'ları

## Sorun Giderme

### Hata ayıklama modu

Ayrıntılı çıktı için herhangi bir komuta `--debug` ekleyin:

```bash
rdc ops up --basic --debug
```

### Yaygın sorunlar

**KVM mevcut değil (Linux)**
- `/dev/kvm` dosyasının var olduğunu kontrol edin: `ls -la /dev/kvm`
- BIOS/UEFI'de sanallaştırmayı etkinleştirin
- Çekirdek modülünü yükleyin: `sudo modprobe kvm_intel` veya `sudo modprobe kvm_amd`

**libvirtd çalışmıyor (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU bulunamadı (macOS)**
```bash
brew install qemu cdrtools
```

**VM'ler başlamıyor**
- `~/.renet/disks/` dizinindeki disk alanını kontrol edin
- Tüm ön koşulları doğrulamak için `rdc ops check` çalıştırın
- `rdc ops down` ardından `rdc ops up --force` deneyin
