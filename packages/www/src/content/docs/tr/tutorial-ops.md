---
title: "Yerel VM Hazırlama"
description: "CLI kullanarak yerel bir VM kümesi hazırlayın, SSH üzerinden komut çalıştırın ve her şeyi kaldırın."
category: "Tutorials"
order: 1
language: tr
sourceHash: "2fdc49f796b03e18"
---

# Rediacc ile Yerel VM'leri Nasıl Hazırlarsınız

Üretime dağıtmadan önce altyapıyı yerel olarak test etmek zaman kazandırır ve yapılandırma hatalarını önler. Bu öğreticide, iş istasyonunuzda minimal bir VM kümesi hazırlayacak, bağlantıyı doğrulayacak, SSH üzerinden komut çalıştıracak ve her şeyi kaldıracaksınız. Bitirdiğinizde, tekrarlanabilir bir yerel geliştirme ortamına sahip olacaksınız.

## Ön Koşullar

- Donanım sanallaştırması etkinleştirilmiş bir Linux veya macOS iş istasyonu
- `rdc` CLI kurulu ve yerel adaptör ile yapılandırma başlatılmış olmalı
- KVM/libvirt (Linux) veya QEMU (macOS) kurulu olmalı — kurulum talimatları için [Deneysel VM'ler](/tr/docs/experimental-vms) sayfasına bakın

## Etkileşimli Kayıt

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### Adım 1: Sistem gereksinimlerini doğrulayın

Hazırlamadan önce, iş istasyonunuzun sanallaştırma desteğine sahip olduğunu ve gerekli paketlerin kurulu olduğunu doğrulayın.

```bash
rdc ops check
```

Rediacc donanım sanallaştırmasını (VT-x/AMD-V), gerekli paketleri (libvirt, QEMU) ve ağ yapılandırmasını kontrol eder. VM oluşturabilmeniz için tüm kontrollerin geçmesi gerekir.

### Adım 2: Minimal bir VM kümesi hazırlayın

```bash
rdc ops up --basic --skip-orchestration
```

İki VM'lik bir küme oluşturur: bir **köprü** VM (1 CPU, 1024 MB RAM, 8 GB disk) ve bir **işçi** VM (2 CPU, 4096 MB RAM, 16 GB disk). `--skip-orchestration` bayrağı Rediacc platform hazırlamasını atlar ve size yalnızca SSH erişimi olan çıplak VM'ler verir.

> **Not:** İlk hazırlama temel imajları indirir, bu nedenle daha uzun sürer. Sonraki çalıştırmalar önbelleğe alınmış imajları yeniden kullanır.

### Adım 3: Küme durumunu kontrol edin

```bash
rdc ops status
```

Kümedeki her VM'nin durumunu görüntüler — IP adresleri, kaynak tahsisi ve çalışma durumu. Her iki VM de çalışıyor olarak görünmelidir.

### Adım 4: VM üzerinde komut çalıştırın

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Köprü VM'de (ID `1`) SSH üzerinden komut çalıştırır. VM ID'sinden sonra herhangi bir komut geçirebilirsiniz. Etkileşimli bir kabuk için komutu atlayın: `rdc ops ssh 1`.

### Adım 5: Kümeyi kaldırın

İşiniz bittiğinde, tüm VM'leri yok edin ve kaynakları serbest bırakın.

```bash
rdc ops down
```

Tüm VM'leri kaldırır ve ağı temizler. Küme, `rdc ops up` ile istediğiniz zaman yeniden hazırlanabilir.

## Sorun Giderme

**"KVM not available" veya "hardware virtualization not supported"**
BIOS/UEFI ayarlarınızda sanallaştırmanın etkin olduğunu doğrulayın. Linux'ta `lscpu | grep Virtualization` ile kontrol edin. WSL2'de iç içe sanallaştırma belirli çekirdek bayrakları gerektirir.

**"libvirt daemon not running"**
libvirt hizmetini başlatın: `sudo systemctl start libvirtd`. macOS'ta QEMU'nun Homebrew ile kurulu olduğunu doğrulayın: `brew install qemu`.

**"Insufficient memory for VM allocation"**
Temel küme en az 6 GB boş RAM gerektirir (1 GB köprü + 4 GB işçi + ek yük). Diğer kaynak yoğun uygulamaları kapatın veya VM özelliklerini azaltın.

## Sonraki Adımlar

Yerel bir VM kümesi hazırladınız, SSH üzerinden komut çalıştırdınız ve kaldırdınız. Gerçek altyapı dağıtmak için:

- [Deneysel VM'ler](/tr/docs/experimental-vms) — `rdc ops` komutları, VM yapılandırması ve platform desteği için tam referans
- [Öğretici: Makine Kurulumu](/tr/docs/tutorial-setup) — uzak makineleri kaydedin ve altyapıyı yapılandırın
- [Hızlı Başlangıç](/tr/docs/quick-start) — konteynerize bir servisi uçtan uca dağıtın
