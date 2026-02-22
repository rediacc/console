---
title: Outils
description: >-
  Synchronisation de fichiers, accès terminal, intégration VS Code, mises à jour
  et diagnostics.
category: Guides
order: 8
language: fr
sourceHash: 80ca3cd3e1a55d4b
---

# Outils

Rediacc inclut des outils de productivité pour travailler avec les dépôts distants : synchronisation de fichiers, terminal SSH, intégration VS Code et mises à jour du CLI.

## Synchronisation de fichiers (sync)

Transférez des fichiers entre votre poste de travail et un dépôt distant via rsync sur SSH.

### Envoyer des fichiers

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### Télécharger des fichiers

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### Vérifier l'état de la synchronisation

```bash
rdc sync status -m server-1 -r my-app
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Machine cible |
| `-r, --repository <name>` | Dépôt cible |
| `--local <path>` | Chemin du répertoire local |
| `--remote <path>` | Chemin distant (relatif au point de montage du dépôt) |
| `--dry-run` | Prévisualiser les changements sans transférer |
| `--mirror` | Miroir de la source vers la destination (supprimer les fichiers en trop) |
| `--verify` | Vérifier les sommes de contrôle après le transfert |
| `--confirm` | Confirmation interactive avec vue détaillée |
| `--exclude <patterns...>` | Exclure des motifs de fichiers |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routage après l'opération |

## Terminal SSH (term)

Ouvrez une session SSH interactive vers une machine ou dans l'environnement d'un dépôt.

### Syntaxe abrégée

La manière la plus rapide de se connecter :

```bash
rdc term server-1                    # Se connecter à une machine
rdc term server-1 my-app             # Se connecter à un dépôt
```

### Exécuter une commande

Exécutez une commande sans ouvrir de session interactive :

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

Lors de la connexion à un dépôt, `DOCKER_HOST` est automatiquement configuré vers le socket Docker isolé du dépôt, de sorte que `docker ps` n'affiche que les conteneurs de ce dépôt.

### Sous-commande connect

La sous-commande `connect` offre la même fonctionnalité avec des options explicites :

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Actions sur les conteneurs

Interagissez directement avec un conteneur en cours d'exécution :

```bash
# Ouvrir un shell dans un conteneur
rdc term server-1 my-app --container <container-id>

# Afficher les journaux d'un conteneur
rdc term server-1 my-app --container <container-id> --container-action logs

# Suivre les journaux en temps réel
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# Afficher les statistiques d'un conteneur
rdc term server-1 my-app --container <container-id> --container-action stats

# Exécuter une commande dans un conteneur
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
```

| Option | Description |
|--------|-------------|
| `--container <id>` | ID du conteneur Docker cible |
| `--container-action <action>` | Action : `terminal` (par défaut), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Nombre de lignes de journaux à afficher (par défaut : 50) |
| `--follow` | Suivre les journaux en continu |
| `--external` | Utiliser un terminal externe au lieu du SSH intégré |

## Intégration VS Code (vscode)

Ouvrez une session SSH distante dans VS Code, préconfigurée avec les bons paramètres SSH.

### Se connecter à un dépôt

```bash
rdc vscode connect my-app -m server-1
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
rdc vscode clean
```

Supprime les configurations SSH de VS Code qui ne sont plus nécessaires.

### Vérifier la configuration

```bash
rdc vscode check
```

Vérifie l'installation de VS Code, l'extension Remote SSH et les connexions actives.

> **Prérequis :** Installez l'extension [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) dans VS Code.

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
rdc update rollback
```

Revient à la version précédemment installée. Disponible uniquement après l'application d'une mise à jour.

### État des mises à jour

```bash
rdc update status
```

Affiche la version actuelle, le canal de mise à jour et la configuration de la mise à jour automatique.
