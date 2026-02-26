---
title: "Kurulum"
description: "Rediacc CLI'ı Linux, macOS veya Windows üzerine kurun."
category: "Guides"
order: 1
language: tr
sourceHash: "2cb00a8aeec6988c"
---

# Kurulum

`rdc` CLI'ı iş istasyonunuza kurun. Manuel olarak kurmanız gereken tek araç budur -- diğer her şey uzak makineleri kurduğunuzda otomatik olarak halledilir.

## Linux ve macOS

Kurulum betiğini çalıştırın:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Bu komut `rdc` ikili dosyasını `$HOME/.local/bin/` dizinine indirir. Bu dizinin PATH değişkeninizde olduğundan emin olun:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Kalıcı hale getirmek için bu satırı kabuk profilinize (`~/.bashrc`, `~/.zshrc`, vb.) ekleyin.

## Windows

PowerShell'de kurulum betiğini çalıştırın:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Bu, `rdc.exe` dosyasını `%LOCALAPPDATA%\rediacc\bin\` dizinine indirir. Bu dizinin PATH'inizde olduğundan emin olun. Yükleyici, henüz eklenmemişse eklemenizi isteyecektir.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Not: `gcompat` paketi (glibc uyumluluk katmanı) bağımlılık olarak otomatik yüklenir.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Kurulumu Doğrulama

```bash
rdc --version
```

Kurulu sürüm numarasını görmelisiniz.

## Güncelleme

`rdc` aracını en son sürüme güncellemek için:

```bash
rdc update
```

Kurmadan güncellemeleri kontrol etmek için:

```bash
rdc update --check-only
```

Bir güncellemeden sonra önceki sürüme geri dönmek için:

```bash
rdc update rollback
```

### Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1–2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider — it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched — only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
