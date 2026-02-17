---
title: "Outils"
description: "Synchronisation de fichiers, accès terminal, intégration VS Code, mises à jour et diagnostics."
category: "Getting Started"
order: 4
language: fr
---

# Outils

Rediacc inclut plusieurs outils de productivité pour travailler avec des dépôts distants. Ces outils s'appuient sur la connexion SSH établie par la configuration de votre contexte.

## Synchronisation de fichiers (sync)

Transférez des fichiers entre votre poste de travail et un dépôt distant en utilisant rsync via SSH.

### Téléverser des fichiers

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### Télécharger des fichiers

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Machine cible |
| `--local <path>` | Chemin du répertoire local |
| `--remote <path>` | Chemin distant (relatif au point de montage du dépôt) |
| `--dry-run` | Prévisualiser les modifications sans effectuer le transfert |
| `--delete` | Supprimer les fichiers à la destination qui n'existent pas à la source |

Le drapeau `--dry-run` est utile pour prévisualiser ce qui sera transféré avant de lancer la synchronisation.

## Terminal SSH (term)

Ouvrez une session SSH interactive vers une machine ou directement dans le chemin de montage d'un dépôt.

### Se connecter à une machine

```bash
rdc term connect server-1
```

### Se connecter à un dépôt

```bash
rdc term connect my-app -m server-1
```

Lors de la connexion à un dépôt, la session terminal démarre dans le répertoire de montage du dépôt avec le socket Docker du dépôt configuré.

## Intégration VS Code (vscode)

Ouvrez une session SSH distante dans VS Code, préconfigurée avec les paramètres SSH corrects et l'extension Remote SSH.

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

Affiche toutes les connexions SSH qui ont été configurées pour VS Code.

### Nettoyer les connexions

```bash
rdc vscode clean
```

Supprime les configurations SSH de VS Code qui ne sont plus nécessaires.

> **Prérequis :** Installez l'extension [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) dans VS Code.

## Mises à jour du CLI (update)

Maintenez le CLI `rdc` à jour avec les dernières fonctionnalités et corrections de bogues.

### Vérifier les mises à jour

```bash
rdc update --check-only
```

### Appliquer la mise à jour

```bash
rdc update
```

Les mises à jour sont téléchargées et appliquées sur place. La nouvelle version prend effet au prochain lancement.

### Retour en arrière

```bash
rdc update rollback
```

Revient à la version précédemment installée. Disponible uniquement après qu'une mise à jour ait été appliquée.

### Statut de mise à jour automatique

```bash
rdc update status
```

Affiche la version actuelle, le canal de mise à jour et la configuration de mise à jour automatique.

## Diagnostics système (doctor)

Exécutez une vérification diagnostique complète de votre environnement Rediacc.

```bash
rdc doctor
```

La commande doctor vérifie :

| Catégorie | Vérifications |
|----------|--------|
| **Environnement** | Version de Node.js, version du CLI, mode SEA |
| **Renet** | Présence du binaire, version, CRIU et rsync intégrés |
| **Configuration** | Contexte actif, mode, machines, clé SSH |
| **Authentification** | Statut de connexion |

Chaque vérification indique **OK**, **Avertissement** ou **Erreur** avec une brève explication. Utilisez cette commande comme première étape lors du dépannage de tout problème.
