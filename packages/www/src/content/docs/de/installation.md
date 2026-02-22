---
title: "Installation"
description: "Installieren Sie die Rediacc-CLI für Linux, macOS oder Windows."
category: "Guides"
order: 1
language: de
---

# Installation

Installieren Sie die `rdc`-CLI auf Ihrer Workstation. Dies ist das einzige Tool, das Sie manuell installieren müssen -- alles andere wird automatisch erledigt, wenn Sie entfernte Maschinen einrichten.

## Linux und macOS

Führen Sie das Installationsskript aus:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Dies lädt die `rdc`-Binary nach `$HOME/.local/bin/` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Fügen Sie diese Zeile Ihrem Shell-Profil (`~/.bashrc`, `~/.zshrc` usw.) hinzu, um sie dauerhaft zu machen.

## Windows

Führen Sie das Installationsskript in PowerShell aus:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Dies lädt die `rdc.exe`-Datei nach `%LOCALAPPDATA%\rediacc\bin\` herunter. Stellen Sie sicher, dass dieses Verzeichnis in Ihrem PATH enthalten ist. Das Installationsprogramm fordert Sie auf, es hinzuzufügen, falls es noch nicht vorhanden ist.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Hinweis: Das `gcompat`-Paket (glibc-Kompatibilitätsschicht) wird automatisch als Abhängigkeit installiert.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Installation überprüfen

```bash
rdc --version
```

Sie sollten die installierte Versionsnummer sehen.

## Aktualisieren

Um `rdc` auf die neueste Version zu aktualisieren:

```bash
rdc update
```

Um nach Updates zu suchen, ohne sie zu installieren:

```bash
rdc update --check-only
```

Um nach einem Update zur vorherigen Version zurückzukehren:

```bash
rdc update rollback
```
