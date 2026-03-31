---
title: "Installation"
description: "Installieren Sie die Rediacc-CLI für Linux, macOS oder Windows."
category: "Guides"
order: 1
language: de
sourceHash: "f4d35bb8c2447783"
---

# Installation

Installieren Sie die `rdc`-CLI auf Ihrer Workstation. Dies ist das einzige Tool, das Sie manuell installieren müssen -- alles andere wird automatisch erledigt, wenn Sie entfernte Maschinen einrichten.

## Linux und macOS

Führen Sie das Installationsskript aus:

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
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
echo "https://releases.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

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
Server = https://releases.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

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

### Update-Kanale

Die CLI unterstutzt zwei Release-Kanale:
- **stable** (Standard): Grundlich getestete Versionen, empfohlen fur den Produktivbetrieb
- **edge**: Neueste Funktionen und Fehlerbehebungen, bei jedem Release aktualisiert

```bash
rdc update --channel edge      # Zum Edge-Kanal wechseln
rdc update --channel stable    # Zuruck zum Stable-Kanal
rdc update --status            # Aktuellen Kanal und Version anzeigen
```

Um direkt vom Edge-Kanal zu installieren:
```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
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
