---
title: "Installation"
description: "Installez la CLI Rediacc sur Linux, macOS ou Windows à l'aide du script d'installation."
category: "Guides"
order: 1
language: fr
sourceHash: "5bdc0ff205ae9c73"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

# Installation

Installez la CLI `rdc` sur votre poste de travail. C'est le seul outil que vous devez installer manuellement -- tout le reste est géré automatiquement lors de la configuration des machines distantes.

## Installation rapide

### Linux et macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Cette commande télécharge le binaire `rdc` dans `$HOME/.local/bin/`. Assurez-vous que ce répertoire est dans votre PATH :

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Ajoutez cette ligne à votre profil shell (`~/.bashrc`, `~/.zshrc`, etc.) pour la rendre permanente.

### Windows

Exécutez dans PowerShell :

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Cette commande télécharge `rdc.exe` dans `%LOCALAPPDATA%\rediacc\bin\`. L'installateur vous proposera de l'ajouter à votre PATH si nécessaire.

## Gestionnaires de paquets

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / compatible RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux et Rocky Linux utilisent tous le même flux DNF ; toute distribution compatible RHEL disposant de `dnf` peut récupérer le dépôt ci-dessus. Remarque : **Oracle Linux 10 est la seule distribution de la famille RHEL officiellement prise en charge comme cible de serveur Rediacc** (voir [Prérequis](/en/docs/requirements)). Rocky/Alma 10 ne disposent pas du module noyau btrfs nécessaire au plan de données renet, bien que la CLI `rdc` s'y installe correctement.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Testé sur openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Remarque : Le paquet `gcompat` (couche de compatibilité glibc) est installé automatiquement en tant que dépendance.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

Téléchargez et exécutez la CLI en tant que conteneur :

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Créez un alias pour plus de commodité :

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Tags Docker disponibles :

| Tag | Description |
|-----|-------------|
| `:stable` | Dernière version stable (recommandée) |
| `:edge` | Dernière version edge |
| `:0.8.4` | Version épinglée (immuable) |
| `:latest` | Alias pour `:stable` |

## Vérifier l'installation

```bash
rdc --version
```

## Mise à jour

Mettre à jour vers la dernière version :

```bash
rdc update
```

Vérifier les mises à jour sans installer :

```bash
rdc update --check-only
```

Afficher l'état actuel des mises à jour :

```bash
rdc update --status
```

Revenir à la version précédente :

```bash
rdc update --rollback
```

## Canaux de publication

Rediacc utilise un système de publication basé sur des canaux. Le canal détermine quelle version vous recevez pour les mises à jour CLI, les installations via gestionnaire de paquets et les téléchargements Docker.

| Canal | Description | Quand mis à jour |
|-------|-------------|------------------|
| `stable` | Versions prêtes pour la production | Promues depuis edge après 7 jours de test |
| `edge` | Dernières fonctionnalités et corrections | À chaque merge dans main |
| `pr-N` | Builds de prévisualisation PR | Automatiquement par pull request |

### Changer de canal

```bash
rdc update --channel edge      # Passer au canal edge
rdc update --channel stable    # Revenir au canal stable
```

Installer directement depuis le canal edge :

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Pour les gestionnaires de paquets, remplacez `stable` par `edge` dans l'URL du dépôt :

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Comment fonctionnent les canaux

Le canal s'applique uniformément à toutes les méthodes de distribution :

- **Scripts d'installation** : La variable d'environnement `REDIACC_CHANNEL` sélectionne le canal
- **Dépôts de paquets** : `releases.rediacc.com/{format}/{canal}/`
- **Tags Docker** : `ghcr.io/rediacc/elite/cli:{canal}`
- **Mises à jour CLI** : `rdc update` vérifie le canal configuré lors de l'installation

### Configuration automatique de prévisualisation PR

Lorsque vous installez depuis un déploiement de prévisualisation PR (par exemple, `pr-420.rediacc.workers.dev`), le canal et le serveur de compte sont configurés automatiquement :

- Le binaire CLI est téléchargé depuis le canal `pr-420`
- `rdc update` vérifie le canal `pr-420` pour les mises à jour
- Toutes les commandes compte/abonnement se connectent au serveur de prévisualisation PR
- Les commandes Docker sur le site de prévisualisation affichent `cli:pr-420`

Aucune configuration manuelle nécessaire. Le script d'installation détecte le contexte de déploiement à partir de l'URL.

## Mises à jour de binaires distants

Lorsque vous exécutez des commandes sur une machine distante, la CLI provisionne automatiquement le binaire `renet` correspondant. Si le binaire est mis à jour, le serveur de routes (`rediacc-router`) est redémarré automatiquement pour prendre en charge la nouvelle version.

Le redémarrage est transparent et ne cause **aucune interruption** :

- Le serveur de routes redémarre en ~1-2 secondes.
- Pendant cette fenêtre, Traefik continue de servir le trafic en utilisant sa dernière configuration de routage connue. Aucune route n'est perdue.
- Traefik récupère la nouvelle configuration lors de son prochain cycle de sondage (dans les 5 secondes).
- **Les connexions client existantes (HTTP, TCP, UDP) ne sont pas affectées.** Le serveur de routes est un fournisseur de configuration -- il n'est pas dans le chemin de données. Traefik gère tout le trafic directement.
- Vos conteneurs d'application ne sont pas touchés -- seul le processus du serveur de routes au niveau système est redémarré.

Pour ignorer le redémarrage automatique, passez `--skip-router-restart` à n'importe quelle commande, ou définissez la variable d'environnement `RDC_SKIP_ROUTER_RESTART=1`.
