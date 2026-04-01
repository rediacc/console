---
title: "Kurulum"
description: "Rediacc CLI'yi Linux, macOS veya Windows'a kurun."
category: "Guides"
order: 1
language: tr
---

# Kurulum

`rdc` CLI'yi is istasyonunuza kurun. Manuel olarak kurmaniz gereken tek arac budur -- geri kalan her sey uzak makineleri yapilandirirken otomatik olarak halledilir.

## Hizli Kurulum

### Linux ve macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Bu komut `rdc` ikili dosyasini `$HOME/.local/bin/` dizinine indirir. Bu dizinin PATH'inizde oldugundan emin olun:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Kalici hale getirmek icin bu satiri kabuk profilinize (`~/.bashrc`, `~/.zshrc`, vb.) ekleyin.

### Windows

PowerShell'de calistirin:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Bu komut `rdc.exe` dosyasini `%LOCALAPPDATA%\rediacc\bin\` dizinine indirir. Gerekirse yukleyici, dosyayi PATH'inize eklemenizi isteyecektir.

## Paket Yoneticileri

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

Not: `gcompat` paketi (glibc uyumluluk katmani) bagimlilik olarak otomatik kurulur.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

CLI'yi bir konteyner olarak cekin ve calistirin:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Kolaylik icin bir takma ad olusturun:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Mevcut Docker etiketleri:

| Etiket | Aciklama |
|--------|----------|
| `:stable` | En son kararli surum (onerilen) |
| `:edge` | En son edge surumu |
| `:0.8.4` | Sabitlenmis surum (degistirilemez) |
| `:latest` | `:stable` icin takma ad |

## Kurulumu Dogrulama

```bash
rdc --version
```

## Guncelleme

En son surume guncelleyin:

```bash
rdc update
```

Kurulum yapmadan guncellemeleri kontrol edin:

```bash
rdc update --check-only
```

Mevcut guncelleme durumunu goruntuleyin:

```bash
rdc update --status
```

Onceki surume geri donun:

```bash
rdc update rollback
```

## Yayin Kanallari

Rediacc, kanal tabanli bir yayin sistemi kullanir. Kanal, CLI guncellemeleri, paket yoneticisi kurulumlari ve Docker cekme islemleri icin hangi surumu alacaginizi belirler.

| Kanal | Aciklama | Ne zaman guncellenir |
|-------|----------|----------------------|
| `stable` | Uretime hazir surumler | 7 gunluk deneme suresinden sonra edge'den yukseltilir |
| `edge` | En son ozellikler ve duzeltmeler | Main dalina her birlestirmede |
| `pr-N` | PR onizleme derlemeleri | Her pull request icin otomatik |

### Kanal degistirme

```bash
rdc update --channel edge      # Edge kanalina gec
rdc update --channel stable    # Stable kanalina geri don
```

Dogrudan edge kanalindan kurulum yapin:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Paket yoneticileri icin depo URL'sindeki `stable` ifadesini `edge` ile degistirin:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Kanallar nasil calisir

Kanal, tum dagitim yontemlerinde ayni sekilde uygulanir:

- **Kurulum betikleri**: `REDIACC_CHANNEL` ortam degiskeni kanali secer
- **Paket depolari**: `releases.rediacc.com/{format}/{kanal}/`
- **Docker etiketleri**: `ghcr.io/rediacc/elite/cli:{kanal}`
- **CLI guncellemeleri**: `rdc update` kurulum sirasinda yapilandirilan kanali kontrol eder

### PR onizleme otomatik yapilandirmasi

Bir PR onizleme dagitiminden (orn. `pr-420.rediacc.workers.dev`) kurulum yaptiginizda, kanal ve hesap sunucusu otomatik olarak yapilandirilir:

- CLI ikili dosyasi `pr-420` kanalindan indirilir
- `rdc update` guncellemeler icin `pr-420` kanalini kontrol eder
- Tum hesap/abonelik komutlari PR onizleme sunucusuna baglanir
- Onizleme sitesindeki Docker komutlari `cli:pr-420` gosterir

Manuel yapilandirma gerekmez. Kurulum betigi, dagitim baglamini URL'den algilar.

## Uzak Ikili Guncellemeler

Uzak bir makineye karsi komut calistirdiginizda, CLI otomatik olarak eslesen `renet` ikili dosyasini saglar. Ikili dosya guncellenirse, yeni surumu almasi icin yol sunucusu (`rediacc-router`) otomatik olarak yeniden baslatilir.

Yeniden baslatma seffaftir ve **kesinti yaratmaz**:

- Yol sunucusu ~1-2 saniyede yeniden baslar.
- Bu sure zarfinda Traefik, bilinen son yonlendirme yapilandirmasini kullanarak trafige hizmet etmeye devam eder. Hicbir yol dusmez.
- Traefik, bir sonraki yoklama dongusunde (5 saniye icinde) yeni yapilandirmayi alir.
- **Mevcut istemci baglantilari (HTTP, TCP, UDP) etkilenmez.** Yol sunucusu bir yapilandirma saglayicisidir -- veri yolunda degildir. Traefik tum trafigi dogrudan yonetir.
- Uygulama konteynerlerinize dokunulmaz -- yalnizca sistem duzeyindeki yol sunucusu sureci yeniden baslatilir.

Otomatik yeniden baslatmayi atlamak icin herhangi bir komuta `--skip-router-restart` parametresini ekleyin veya `RDC_SKIP_ROUTER_RESTART=1` ortam degiskenini ayarlayin.
