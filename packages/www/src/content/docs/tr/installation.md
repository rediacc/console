---
title: "Kurulum"
description: "Rediacc CLI'yı Linux, macOS veya Windows üzerine yükleyin."
category: "Guides"
order: 1
language: tr
---

# Kurulum

`rdc` CLI'yi iş istasyonunuza kurun. Manuel olarak kurmanız gereken tek araç budur -- geri kalan her şey uzak makineleri yapılandırırken otomatik olarak halledilir.

## Hızlı Kurulum

### Linux ve macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Bu komut `rdc` ikili dosyasını `$HOME/.local/bin/` dizinine indirir. Bu dizinin PATH'inizde olduğundan emin olun:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Kalıcı hale getirmek için bu satırı kabuk profilinize (`~/.bashrc`, `~/.zshrc`, vb.) ekleyin.

### Windows

PowerShell'de çalıştırın:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Bu komut `rdc.exe` dosyasını `%LOCALAPPDATA%\rediacc\bin\` dizinine indirir. Gerekirse yükleyici, dosyayı PATH'inize eklemenizi isteyecektir.

## Paket Yöneticileri

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Not: `gcompat` paketi (glibc uyumluluk katmanı) bağımlılık olarak otomatik kurulur.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

CLI'yi bir konteyner olarak çekin ve çalıştırın:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Kolaylık için bir takma ad oluşturun:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Mevcut Docker etiketleri:

| Etiket | Açıklama |
|--------|----------|
| `:stable` | En son kararlı sürüm (önerilen) |
| `:edge` | En son edge sürümü |
| `:0.8.4` | Sabitlenmiş sürüm (değiştirilemez) |
| `:latest` | `:stable` için takma ad |

## Kurulumu Doğrulama

```bash
rdc --version
```

## Güncelleme

En son sürüme güncelleyin:

```bash
rdc update
```

Kurulum yapmadan güncellemeleri kontrol edin:

```bash
rdc update --check-only
```

Mevcut güncelleme durumunu görüntüleyin:

```bash
rdc update --status
```

Önceki sürüme geri dönün:

```bash
rdc update rollback
```

## Yayın Kanalları

Rediacc, kanal tabanlı bir yayın sistemi kullanır. Kanal, CLI güncellemeleri, paket yöneticisi kurulumları ve Docker çekme işlemleri için hangi sürümü alacağınızı belirler.

| Kanal | Açıklama | Ne zaman güncellenir |
|-------|----------|----------------------|
| `stable` | Üretime hazır sürümler | 7 günlük deneme süresinden sonra edge'den yükseltilir |
| `edge` | En son özellikler ve düzeltmeler | Main dalına her birleştirmede |
| `pr-N` | PR önizleme derlemeleri | Her pull request için otomatik |

### Kanal değiştirme

```bash
rdc update --channel edge      # Edge kanalına geç
rdc update --channel stable    # Stable kanalına geri dön
```

Doğrudan edge kanalından kurulum yapın:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Paket yöneticileri için depo URL'sindeki `stable` ifadesini `edge` ile değiştirin:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Kanallar nasıl çalışır

Kanal, tüm dağıtım yöntemlerinde aynı şekilde uygulanır:

- **Kurulum betikleri**: `REDIACC_CHANNEL` ortam değişkeni kanalı seçer
- **Paket depoları**: `releases.rediacc.com/{format}/{kanal}/`
- **Docker etiketleri**: `ghcr.io/rediacc/elite/cli:{kanal}`
- **CLI güncellemeleri**: `rdc update` kurulum sırasında yapılandırılan kanalı kontrol eder

### PR önizleme otomatik yapılandırması

Bir PR önizleme dağıtımından (örn. `pr-420.rediacc.workers.dev`) kurulum yaptığınızda, kanal ve hesap sunucusu otomatik olarak yapılandırılır:

- CLI ikili dosyası `pr-420` kanalından indirilir
- `rdc update` güncellemeler için `pr-420` kanalını kontrol eder
- Tüm hesap/abonelik komutları PR önizleme sunucusuna bağlanır
- Önizleme sitesindeki Docker komutları `cli:pr-420` gösterir

Manuel yapılandırma gerekmez. Kurulum betiği, dağıtım bağlamını URL'den algılar.

## Uzak İkili Güncellemeler

Uzak bir makineye karşı komut çalıştırdığınızda, CLI otomatik olarak eşleşen `renet` ikili dosyasını sağlar. İkili dosya güncellenirse, yeni sürümü alması için yol sunucusu (`rediacc-router`) otomatik olarak yeniden başlatılır.

Yeniden başlatma şeffaftır ve **kesinti yaratmaz**:

- Yol sunucusu ~1-2 saniyede yeniden başlar.
- Bu süre zarfında Traefik, bilinen son yönlendirme yapılandırmasını kullanarak trafiğe hizmet etmeye devam eder. Hiçbir yol düşmez.
- Traefik, bir sonraki yoklama döngüsünde (5 saniye içinde) yeni yapılandırmayı alır.
- **Mevcut istemci bağlantıları (HTTP, TCP, UDP) etkilenmez.** Yol sunucusu bir yapılandırma sağlayıcısıdır -- veri yolunda değildir. Traefik tüm trafiği doğrudan yönetir.
- Uygulama konteynerlerinize dokunulmaz -- yalnızca sistem düzeyindeki yol sunucusu süreci yeniden başlatılır.

Otomatik yeniden başlatmayı atlamak için herhangi bir komuta `--skip-router-restart` parametresini ekleyin veya `RDC_SKIP_ROUTER_RESTART=1` ortam değişkenini ayarlayın.
