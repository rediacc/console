---
title: Dépôts
description: 'Créez, gérez et opérez des dépôts chiffrés LUKS sur des machines distantes.'
category: Guides
order: 4
language: fr
sourceHash: 04fe287348176b64
---

# Dépôts

Un **dépôt** est une image disque chiffrée LUKS sur un serveur distant. Une fois monté, il fournit :
- Un système de fichiers isolé pour les données de votre application
- Un démon Docker dédié (séparé du Docker de l'hôte)
- Des adresses IP de bouclage uniques pour chaque service au sein d'un sous-réseau /26

## Créer un dépôt

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Requis | Description |
|--------|--------|-------------|
| `-m, --machine <name>` | Oui | Machine cible où le dépôt sera créé |
| `--size <size>` | Oui | Taille de l'image disque chiffrée (par ex., `5G`, `10G`, `50G`) |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

La sortie affichera trois valeurs générées automatiquement :

- **GUID du dépôt** -- Un UUID qui identifie l'image disque chiffrée sur le serveur.
- **Identifiant (Credential)** -- Une phrase secrète aléatoire utilisée pour chiffrer/déchiffrer le volume LUKS.
- **ID réseau** -- Un entier (commençant à 2816, incrémenté de 64) qui détermine le sous-réseau IP pour les services de ce dépôt.

> **Conservez l'identifiant en lieu sûr.** C'est la clé de chiffrement de votre dépôt. En cas de perte, les données ne pourront pas être récupérées. L'identifiant est stocké dans votre fichier local `config.json` mais n'est pas stocké sur le serveur.

## Monter et démonter

Le montage déchiffre et rend le système de fichiers du dépôt accessible. Le démontage ferme le volume chiffré.

```bash
rdc repo mount my-app -m server-1       # Déchiffrer et monter
rdc repo unmount my-app -m server-1     # Démonter et re-chiffrer
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Créer un point de contrôle avant le montage/démontage |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Vérifier le statut

```bash
rdc repo status my-app -m server-1
```

## Lister les dépôts

```bash
rdc repo list -m server-1
```

## Redimensionner

Définissez une taille exacte pour le dépôt ou ajoutez un montant donné :

```bash
rdc repo resize my-app -m server-1 --size 20G    # Définir une taille exacte
rdc repo expand my-app -m server-1 --size 5G      # Ajouter 5 Go à la taille actuelle
```

> Le dépôt doit être démonté avant le redimensionnement.

## Dupliquer (fork)

Créez une copie d'un dépôt existant dans son état actuel :

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Ceci crée une nouvelle copie chiffrée avec son propre GUID et ID réseau. La copie partage le même identifiant LUKS que le parent.

## Valider

Vérifiez l'intégrité du système de fichiers d'un dépôt :

```bash
rdc repo validate my-app -m server-1
```

## Propriété

Définissez la propriété des fichiers au sein d'un dépôt sur l'utilisateur universel (UID 7111). Ceci est généralement nécessaire après le téléversement de fichiers depuis votre poste de travail, qui arrivent avec votre UID local.

```bash
rdc repo ownership my-app -m server-1
```

La commande détecte automatiquement les répertoires de données des conteneurs Docker (montages bind en écriture) et les exclut. Cela évite de casser les conteneurs qui gèrent des fichiers avec leurs propres UID (par ex., MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Définir un UID personnalisé au lieu de 7111 |
| `--force` | Ignorer la détection des volumes Docker et changer la propriété de tout |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Pour forcer la propriété sur tous les fichiers, y compris les données des conteneurs :

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Attention :** L'utilisation de `--force` sur des conteneurs en cours d'exécution peut les casser. Arrêtez d'abord les services avec `rdc repo down` si nécessaire.

Consultez le [Guide de migration](/fr/docs/migration) pour un guide complet sur quand et comment utiliser la propriété lors de la migration de projets.

## Modèle (template)

Appliquez un modèle pour initialiser un dépôt avec des fichiers :

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Supprimer

Détruisez définitivement un dépôt et toutes les données qu'il contient :

```bash
rdc repo delete my-app -m server-1
```

> Ceci détruit définitivement l'image disque chiffrée. Cette action est irréversible.
