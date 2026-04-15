---
title: Dépôts
description: 'Créez, gérez et opérez des dépôts chiffrés LUKS sur des machines distantes.'
category: Guides
order: 4
language: fr
sourceHash: "83f2c9fa5ae53864"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# Dépôts

Un **dépôt** est une image disque chiffrée LUKS sur un serveur distant. Une fois monté, il fournit :
- Un système de fichiers isolé pour les données de votre application
- Un démon Docker dédié (séparé du Docker de l'hôte)
- Des adresses IP de bouclage uniques pour chaque service au sein d'un sous-réseau /26

## Créer un dépôt

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Option | Requis | Description |
|--------|--------|-------------|
| `-m, --machine <name>` | Oui | Machine cible où le dépôt sera créé |
| `--size <size>` | Oui | Taille de l'image disque chiffrée (par ex., `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Non | Ne pas redémarrer le serveur de routage après l'opération |

La sortie affichera trois valeurs générées automatiquement :

- **GUID du dépôt** -- Un UUID qui identifie l'image disque chiffrée sur le serveur.
- **Identifiant (Credential)** -- Une phrase secrète aléatoire utilisée pour chiffrer/déchiffrer le volume LUKS.
- **ID réseau** -- Un entier (commençant à 2816, incrémenté de 64) qui détermine le sous-réseau IP pour les services de ce dépôt.

> **Conservez l'identifiant en lieu sûr.** C'est la clé de chiffrement de votre dépôt. En cas de perte, les données ne pourront pas être récupérées. L'identifiant est stocké dans votre fichier local `config.json` mais n'est pas stocké sur le serveur.

## Monter et démonter

Le montage déchiffre et rend le système de fichiers du dépôt accessible. Le démontage ferme le volume chiffré.

```bash
rdc repo mount --name my-app -m server-1  # Déchiffrer et monter
rdc repo unmount --name my-app -m server-1  # Démonter et re-chiffrer
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Créer un checkpoint CRIU avant le montage/démontage (pour les conteneurs avec le label `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routage après l'opération |

## Vérifier le statut

```bash
rdc repo status --name my-app -m server-1
```

## Lister les dépôts

```bash
rdc repo list -m server-1
```

## Redimensionner

Définissez une taille exacte pour le dépôt ou ajoutez un montant donné :

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Définir une taille exacte
rdc repo expand --name my-app -m server-1 --size 5G  # Ajouter 5 Go à la taille actuelle
```

> Le dépôt doit être démonté avant le redimensionnement.

## Dupliquer (fork)

Créez une copie d'un dépôt existant dans son état actuel :

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Les forks utilisent le modèle name:tag : le fork résultant est nommé `my-app:staging`. Ceci crée une nouvelle copie chiffrée avec son propre GUID et ID réseau, tout en partageant le nom du parent. La copie partage le même identifiant LUKS que le parent.

## Valider

Vérifiez l'intégrité du système de fichiers d'un dépôt :

```bash
rdc repo validate --name my-app -m server-1
```

## Propriété

Définissez la propriété des fichiers au sein d'un dépôt sur l'utilisateur universel (UID 7111). Ceci est généralement nécessaire après le téléversement de fichiers depuis votre poste de travail, qui arrivent avec votre UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

La commande détecte automatiquement les répertoires de données des conteneurs Docker (montages bind en écriture) et les exclut. Cela évite de casser les conteneurs qui gèrent des fichiers avec leurs propres UID (par ex., MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Définir un UID personnalisé au lieu de 7111 |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routage après l'opération |

Pour forcer la propriété sur tous les fichiers, y compris les données des conteneurs :

```bash
rdc repo ownership --name my-app -m server-1
```


Consultez le [Guide de migration](/en/docs/migration) pour un guide complet sur quand et comment utiliser la propriété lors de la migration de projets.

## Modèle (template)

Appliquez un modèle pour initialiser un dépôt avec des fichiers :

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Supprimer

Détruisez définitivement un dépôt et toutes les données qu'il contient :

```bash
rdc repo delete --name my-app -m server-1
```

> Ceci détruit définitivement l'image disque chiffrée. Cette action est irréversible.

## Migrer un dépôt

Migrez en direct un dépôt d'une machine à une autre avec un temps d'arrêt minimal.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--provision` | Provisionner le dépôt sur la machine cible avant la migration (crée l'image LUKS et enregistre la configuration) |
| `--checkpoint` | Créer un checkpoint CRIU des conteneurs en cours d'exécution avant le basculement |
| `--bwlimit <kbps>` | Limiter la bande passante rsync en kilooctets par seconde |
| `--skip-dns` | Ne pas mettre à jour les enregistrements DNS après le basculement |

**Flux en trois phases :**

1. **Pré-copie à chaud** - rsync transfère les données pendant que le dépôt continue de fonctionner sur la source. Les fichiers volumineux sont transférés avant tout temps d'arrêt.
2. **Basculement** - le dépôt est arrêté sur la source, un dernier passage rsync synchronise les modifications restantes, et le dépôt démarre sur la cible.
3. **Démarrage sur la cible** - renet monte et démarre le dépôt sur la machine cible. Le DNS est mis à jour sauf si `--skip-dns` est passé.

![Migration en direct du dépôt](/img/repo-migrate-flow.svg)

**Push vs. migration :**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Opération | Copie | Déplacement |
| Source après | Inchangée | Arrêtée |
| Temps d'arrêt | Aucun (copie uniquement) | Brève fenêtre de basculement |
| Mise à jour DNS | Non | Oui (sauf avec `--skip-dns`) |
| Cas d'usage | Sauvegarde, clone de staging | Remplacement de machine, déménagement serveur |

## Nettoyer

Après la suppression de dépôts ou la récupération d'opérations échouées, des répertoires de montage orphelins, des fichiers de verrou et des marqueurs inamovibles peuvent subsister. Le nettoyage les supprime en toute sécurité :

```bash
# Aperçu de ce qui serait supprimé
rdc machine prune --name server-1 --dry-run

# Supprimer les ressources orphelines
rdc machine prune --name server-1
```

Seules les ressources sans image de dépôt correspondante sont affectées. Les répertoires de montage non vides ne sont jamais supprimés.
