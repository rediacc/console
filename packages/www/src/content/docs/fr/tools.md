---
title: Outils
description: "Synchronisation de fichiers, accès terminal, intégration VS Code et mises à jour du CLI."
category: Guides
order: 9
language: fr
sourceHash: "2b8afb656455d6ec"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Outils

Rediacc propose quatre outils pour travailler quotidiennement avec vos machines et dépôts : synchronisation de fichiers via SSH, terminal SSH, intégration VS Code et mises à jour automatiques du CLI. Les quatre outils fonctionnent sur SSH. Aucun agent ni daemon n'est requis côté distant. Si vous avez besoin d'une interface graphique pour cela, vous êtes sur la mauvaise page.

## Synchronisation de fichiers (sync)

Transférez des fichiers entre votre poste de travail et un dépôt distant via rsync sur SSH.

### Envoyer des fichiers

`--local` accepte un ou plusieurs chemins. Chaque chemin peut être un fichier ou un répertoire. Les fichiers sont placés à `<remote>/<basename>`; les contenus des répertoires fusionnent dans `<remote>/`. Pour un seul fichier, préférez `--remote-file` pour spécifier explicitement le chemin de destination.

```bash
# Répertoire (contents merged into remote)
rdc repo sync upload my-app --local ./src --remote /app/src

# Single file dropped into a remote directory (basename preserved)
rdc repo sync upload my-app --local ./config.yml --remote /app/conf

# Single file, explicit destination path
rdc repo sync upload my-app --local ./config.yml --remote-file /app/conf/config.yml

# Multiple sources in one call
rdc repo sync upload my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` et `--remote-file` s'excluent mutuellement. `--remote-file` requiert exactement un seul chemin `--local` qui pointe vers un fichier.

`--mirror` ne peut pas être combiné avec une source fichier; cela supprimerait les fichiers frères dans le répertoire distant.

### Télécharger des fichiers

Utilisez `--remote` pour un répertoire (par défaut) ou `--remote-file` pour un seul fichier. Les deux options s'excluent mutuellement.

```bash
# Répertoire
rdc repo sync download my-app --remote /app/data --local ./data

# Single file: --local must be an existing directory
rdc repo sync download my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Vérifier l'état de la synchronisation

```bash
rdc repo sync status my-app
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Machine cible |
| `--local <paths...>` | Un ou plusieurs chemins locaux de fichier/répertoire (envoi) ou répertoire local de destination (téléchargement) |
| `--remote <path>` | Répertoire distant (relatif au point de montage du dépôt) |
| `--remote-file <path>` | Chemin du fichier distant pour les envois ou téléchargements de fichier unique (alternative à `--remote`) |
| `--dry-run` | Prévisualiser les changements sans transférer |
| `--mirror` | Miroir de la source vers la destination, supprimer les fichiers en trop (sources répertoires uniquement) |
| `--verify` | Vérifier les sommes de contrôle après le transfert |
| `--confirm` | Confirmation interactive avec vue détaillée |
| `--exclude <patterns...>` | Exclure des motifs de fichiers |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routage après l'opération |

## Terminal SSH (term)

Ouvrez une session SSH interactive vers une machine ou dans l'environnement d'un dépôt.

### Syntaxe abrégée

La manière la plus rapide de se connecter :

```bash
rdc term connect server-1                    # Se connecter à une machine
rdc term connect my-app             # Se connecter à un dépôt
```

### Exécuter une commande

Exécutez une commande sans ouvrir de session interactive :

```bash
rdc term connect server-1 -c "uptime"
rdc term connect my-app -c "docker ps"
```

Lors de la connexion à un dépôt, `DOCKER_HOST` est automatiquement configuré vers le socket Docker isolé du dépôt, de sorte que `docker ps` n'affiche que les conteneurs de ce dépôt.

### Sous-commande connect

Ou utilisez la sous-commande `connect` pour le même résultat, avec des options explicites :

```bash
rdc term connect server-1
rdc term connect my-app
```

### Actions sur les conteneurs

Interagissez directement avec un conteneur en cours d'exécution :

```bash
# Ouvrir un shell dans un conteneur
rdc repo exec my-app -c <container> -i -- bash

# Afficher les journaux d'un conteneur
rdc repo logs my-app -c <container>

# Suivre les journaux en temps réel
rdc repo logs my-app -c <container> --follow

# Afficher les statistiques d'un conteneur
rdc repo exec my-app -c <container> -i -- bash --container-action stats

# Exécuter une commande dans un conteneur
rdc repo exec my-app -c <container> -- ls -la
```

| Option | Description |
|--------|-------------|

## Intégration VS Code (vscode)

Ouvrez une session SSH distante dans VS Code, préconfigurée avec les bons paramètres SSH.

### Se connecter à un dépôt

```bash
rdc vscode connect my-app
```

Cette commande :
1. Détecte votre installation de VS Code
2. Configure la connexion SSH dans `~/.ssh/config`
3. Persiste la clé SSH pour la session
4. Ouvre VS Code avec une connexion Remote SSH vers le chemin du dépôt

### Lister les connexions configurées

```bash
rdc vscode list
```

### Nettoyer les connexions

```bash
rdc vscode cleanup
```

Supprime les configurations SSH de VS Code qui ne sont plus nécessaires.

### Vérifier la configuration

```bash
rdc vscode check
```

Vérifie l'installation de VS Code, l'extension Remote SSH et les connexions actives.

> **Prérequis :** Installez l'extension [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) dans VS Code.

### VS Code dans le navigateur

Pas de VS Code local ? Servez l'éditeur depuis l'intérieur du sandbox du dépôt et ouvrez-le dans n'importe quel navigateur :

```bash
rdc vscode connect my-app --browser
```

Cette commande :
1. Installe le serveur d'éditeur open-source sur la machine une seule fois (chemin partagé en lecture seule, vérification de somme de contrôle)
2. Le démarre à l'intérieur du sandbox du dépôt, de sorte que l'arborescence de fichiers, le terminal intégré et chaque processus enfant voient exactement ce que voit le dépôt
3. Ouvre un tunnel SSH vers un port local et lance votre navigateur avec une URL à jeton de session

Le serveur continue de tourner après que vous fermez le tunnel ; la reconnexion le réutilise. Gérez-le avec :

```bash
rdc vscode serve status my-app
rdc vscode serve stop my-app
```

| Option | Description |
|--------|-------------|
| `--no-open` | Afficher l'URL au lieu de lancer le navigateur |
| `--url-only` | Afficher exactement une ligne d'URL sur stdout (pour les scripts) et maintenir le tunnel |
| `--local <port>` | Choisir le port local du tunnel |
| `--server-provider <id>` | Implémentation du serveur d'éditeur : `openvscode` (par défaut) ou `code-server` |
| `--server-archive <file>` | Installer depuis une archive pré-préparée sur la machine (pas d'internet nécessaire) |

Fonctionne depuis Linux, macOS, Windows ou une tablette. La seule exigence locale est un navigateur.

## Mises à jour du CLI (update)

Maintenez le CLI `rdc` à jour.

### Vérifier les mises à jour

```bash
rdc update --check-only
```

### Appliquer une mise à jour

```bash
rdc update
```

Les mises à jour sont téléchargées et appliquées sur place. Le CLI sélectionne automatiquement le bon binaire pour votre plateforme (Linux, macOS ou Windows). La nouvelle version prend effet au prochain lancement.

### Restaurer la version précédente

```bash
rdc update --rollback
```

Revient à la version précédemment installée. Disponible uniquement après l'application d'une mise à jour.

### État des mises à jour

```bash
rdc update --status
```

Affiche la version actuelle, le canal de mise à jour et la configuration de la mise à jour automatique.

#### Canaux de publication

```bash
rdc update --channel edge      # Mises à jour continuelles en production
rdc update --channel stable    # Promu à partir d'edge après 7 jours de test (par défaut)
rdc update --status            # Afficher le canal actuel et les informations de version
```
