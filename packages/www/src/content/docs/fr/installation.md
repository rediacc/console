---
title: "Installation"
description: "Installez la CLI Rediacc sur Linux, macOS ou Windows."
category: "Guides"
order: 1
language: fr
---

# Installation

Installez la CLI `rdc` sur votre poste de travail. C'est le seul outil que vous devez installer manuellement -- tout le reste est gere automatiquement lors de la configuration des machines distantes.

## Installation rapide

### Linux et macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Cette commande telecharge le binaire `rdc` dans `$HOME/.local/bin/`. Assurez-vous que ce repertoire est dans votre PATH :

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Ajoutez cette ligne a votre profil shell (`~/.bashrc`, `~/.zshrc`, etc.) pour la rendre permanente.

### Windows

Executez dans PowerShell :

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Cette commande telecharge `rdc.exe` dans `%LOCALAPPDATA%\rediacc\bin\`. L'installateur vous proposera de l'ajouter a votre PATH si necessaire.

## Gestionnaires de paquets

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

Remarque : Le paquet `gcompat` (couche de compatibilite glibc) est installe automatiquement en tant que dependance.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

Telechargez et executez la CLI en tant que conteneur :

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Creez un alias pour plus de commodite :

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Tags Docker disponibles :

| Tag | Description |
|-----|-------------|
| `:stable` | Derniere version stable (recommandee) |
| `:edge` | Derniere version edge |
| `:0.8.4` | Version epinglee (immuable) |
| `:latest` | Alias pour `:stable` |

## Verifier l'installation

```bash
rdc --version
```

## Mise a jour

Mettre a jour vers la derniere version :

```bash
rdc update
```

Verifier les mises a jour sans installer :

```bash
rdc update --check-only
```

Afficher l'etat actuel des mises a jour :

```bash
rdc update --status
```

Revenir a la version precedente :

```bash
rdc update rollback
```

## Canaux de publication

Rediacc utilise un systeme de publication base sur des canaux. Le canal determine quelle version vous recevez pour les mises a jour CLI, les installations via gestionnaire de paquets et les telechargements Docker.

| Canal | Description | Quand mis a jour |
|-------|-------------|------------------|
| `stable` | Versions pretes pour la production | Promues depuis edge apres 7 jours de test |
| `edge` | Dernieres fonctionnalites et corrections | A chaque merge dans main |
| `pr-N` | Builds de previsualisation PR | Automatiquement par pull request |

### Changer de canal

```bash
rdc update --channel edge      # Passer au canal edge
rdc update --channel stable    # Revenir au canal stable
```

Installer directement depuis le canal edge :

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Pour les gestionnaires de paquets, remplacez `stable` par `edge` dans l'URL du depot :

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Comment fonctionnent les canaux

Le canal s'applique uniformement a toutes les methodes de distribution :

- **Scripts d'installation** : La variable d'environnement `REDIACC_CHANNEL` selectionne le canal
- **Depots de paquets** : `releases.rediacc.com/{format}/{canal}/`
- **Tags Docker** : `ghcr.io/rediacc/elite/cli:{canal}`
- **Mises a jour CLI** : `rdc update` verifie le canal configure lors de l'installation

### Configuration automatique de previsualisation PR

Lorsque vous installez depuis un deploiement de previsualisation PR (par exemple, `pr-420.rediacc.workers.dev`), le canal et le serveur de compte sont configures automatiquement :

- Le binaire CLI est telecharge depuis le canal `pr-420`
- `rdc update` verifie le canal `pr-420` pour les mises a jour
- Toutes les commandes compte/abonnement se connectent au serveur de previsualisation PR
- Les commandes Docker sur le site de previsualisation affichent `cli:pr-420`

Aucune configuration manuelle necessaire. Le script d'installation detecte le contexte de deploiement a partir de l'URL.

## Mises a jour de binaires distants

Lorsque vous executez des commandes sur une machine distante, la CLI provisionne automatiquement le binaire `renet` correspondant. Si le binaire est mis a jour, le serveur de routes (`rediacc-router`) est redemarre automatiquement pour prendre en charge la nouvelle version.

Le redemarrage est transparent et ne cause **aucune interruption** :

- Le serveur de routes redemarre en ~1-2 secondes.
- Pendant cette fenetre, Traefik continue de servir le trafic en utilisant sa derniere configuration de routage connue. Aucune route n'est perdue.
- Traefik recupere la nouvelle configuration lors de son prochain cycle de sondage (dans les 5 secondes).
- **Les connexions client existantes (HTTP, TCP, UDP) ne sont pas affectees.** Le serveur de routes est un fournisseur de configuration -- il n'est pas dans le chemin de donnees. Traefik gere tout le trafic directement.
- Vos conteneurs d'application ne sont pas touches -- seul le processus du serveur de routes au niveau systeme est redemarre.

Pour ignorer le redemarrage automatique, passez `--skip-router-restart` a n'importe quelle commande, ou definissez la variable d'environnement `RDC_SKIP_ROUTER_RESTART=1`.
