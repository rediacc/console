---
title: "Installation"
description: "Installer le CLI Rediacc sur Linux, macOS ou Windows."
category: "Getting Started"
order: 1
language: fr
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

## Windows (WSL2)

Rediacc s'exécute dans WSL2 sur Windows. Si WSL2 n'est pas encore configuré :

```powershell
wsl --install
```

Puis dans votre distribution Linux WSL2, exécutez le même script d'installation :

```bash
curl -fsSL https://get.rediacc.com | sh
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
