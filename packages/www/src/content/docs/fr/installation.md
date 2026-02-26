---
title: "Installation"
description: "Procédure d'installation du CLI Rediacc sur Linux, macOS ou Windows. Prérequis et vérification."
category: "Guides"
order: 1
language: fr
sourceHash: "2cb00a8aeec6988c"
---

# Installation

Installez le CLI `rdc` sur votre poste de travail. C'est le seul outil que vous devez installer manuellement — tout le reste est géré automatiquement lors de la configuration des machines distantes.

## Linux et macOS

Exécutez le script d'installation :

```bash
curl -fsSL https://get.rediacc.com | sh
```

Ceci télécharge le binaire `rdc` dans `$HOME/.local/bin/`. Assurez-vous que ce répertoire est dans votre PATH :

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Ajoutez cette ligne à votre profil shell (`~/.bashrc`, `~/.zshrc`, etc.) pour rendre le changement permanent.

## Windows

Exécutez le script d'installation dans PowerShell :

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Cela télécharge le binaire `rdc.exe` dans `%LOCALAPPDATA%\rediacc\bin\`. Assurez-vous que ce répertoire est dans votre PATH. L'installateur vous proposera de l'ajouter s'il n'est pas déjà présent.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Note : Le paquet `gcompat` (couche de compatibilité glibc) est installé automatiquement en tant que dépendance.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Vérifier l'installation

```bash
rdc --version
```

Vous devriez voir le numéro de version installé.

## Mise à jour

Pour mettre à jour `rdc` vers la dernière version :

```bash
rdc update
```

Pour vérifier les mises à jour disponibles sans les installer :

```bash
rdc update --check-only
```

Pour revenir à la version précédente après une mise à jour :

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
