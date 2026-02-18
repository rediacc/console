---
title: "Hızlı Başlangıç"
description: "5 dakikada sunucunuzda konteynerize bir servis çalıştırın."
category: "Guides"
order: -1
language: tr
---

# Hızlı Başlangıç

Kendi sunucunuzda şifrelenmiş, izole bir konteyner ortamını 5 dakikada dağıtın. Bu rehber **yerel modu** kullanır — bulut hesabı veya SaaS bağımlılığı gerekmez.

## Ön Koşullar

- Linux veya macOS iş istasyonu
- SSH erişimi ve sudo yetkilerine sahip uzak sunucu (Ubuntu 24.04+, Debian 12+ veya Fedora 43+)
- Bir SSH anahtar çifti (örn. `~/.ssh/id_ed25519`)

## 1. CLI Kurulumu

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Bağlam Oluşturma

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. Sunucu Ekleme

```bash
rdc context add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. Sunucuyu Hazırlama

```bash
rdc context setup-machine server-1
```

Bu komut sunucunuza Docker, cryptsetup ve renet ikili dosyasını kurar.

## 5. Şifrelenmiş Depo Oluşturma

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. Servisleri Dağıtma

Depoyu bağlayın, içinde `docker-compose.yml` ve `Rediaccfile` dosyalarınızı oluşturun, ardından başlatın:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. Doğrulama

```bash
rdc machine containers server-1
```

Konteynerlerinizin çalıştığını görmelisiniz.

## Rediacc Nedir?

Rediacc, kontrol ettiğiniz uzak sunuculara konteynerize servisleri dağıtır. Her şey LUKS kullanılarak durağan halde şifrelenir, her depo kendi izole Docker daemon'una sahiptir ve tüm orkestrasyon iş istasyonunuzdan SSH üzerinden gerçekleşir.

Bulut hesabı gerekmez. SaaS bağımlılığı yoktur. Verileriniz kendi sunucularınızda kalır.

## Sonraki Adımlar

- **[Mimari](/tr/docs/architecture)** — Rediacc'ın nasıl çalıştığını anlayın: modlar, güvenlik modeli, Docker izolasyonu
- **[Makine Kurulumu](/tr/docs/setup)** — Ayrıntılı kurulum rehberi: bağlamlar, makineler, altyapı yapılandırması
- **[Depolar](/tr/docs/repositories)** — Depo oluşturma, yönetme, yeniden boyutlandırma, çatallama ve doğrulama
- **[Servisler](/tr/docs/services)** — Rediaccfile, servis ağları, dağıtım, otomatik başlatma
- **[Yedekleme ve Geri Yükleme](/tr/docs/backup-restore)** — Harici depolamaya yedekleme ve otomatik yedeklemeleri zamanlama
- **[İzleme](/tr/docs/monitoring)** — Makine sağlığı, konteynerler, servisler, tanılamalar
- **[Araçlar](/tr/docs/tools)** — Dosya senkronizasyonu, SSH terminali, VS Code entegrasyonu
- **[Geçiş Rehberi](/tr/docs/migration)** — Mevcut projeleri Rediacc depolarına taşıma
- **[Sorun Giderme](/tr/docs/troubleshooting)** — Yaygın sorunların çözümleri
- **[CLI Referansı](/tr/docs/cli-application)** — Eksiksiz komut referansı
