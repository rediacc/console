---
title: Sauvegarde et restauration
description: >-
  Sauvegardez des dépôts chiffrés vers un stockage externe, restaurez à partir
  de sauvegardes et planifiez des sauvegardes automatisées.
category: Guides
order: 7
language: fr
sourceHash: 3d127a0a186d7487
---

# Sauvegarde et restauration

Rediacc peut sauvegarder des dépôts chiffrés vers des fournisseurs de stockage externes et les restaurer sur la même machine ou sur une machine différente. Les sauvegardes sont chiffrées — l'identifiant LUKS du dépôt est nécessaire pour la restauration.

## Configurer le stockage

Avant d'envoyer des sauvegardes, enregistrez un fournisseur de stockage. Rediacc prend en charge tout stockage compatible rclone : S3, B2, Google Drive et bien d'autres.

### Importer depuis rclone

Si vous avez déjà un remote rclone configuré :

```bash
rdc context import-storage my-storage
```

Ceci importe la configuration de stockage depuis votre configuration rclone dans le contexte actuel.

### Afficher les stockages

```bash
rdc context storages
```

## Envoyer une sauvegarde

Envoyez une sauvegarde de dépôt vers un stockage externe :

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| Option | Description |
|--------|-------------|
| `--to <storage>` | Emplacement de stockage cible |
| `--to-machine <machine>` | Machine cible pour la sauvegarde de machine à machine |
| `--dest <filename>` | Nom de fichier de destination personnalisé |
| `--checkpoint` | Créer un point de contrôle avant l'envoi |
| `--force` | Écraser une sauvegarde existante |
| `--tag <tag>` | Étiqueter la sauvegarde |
| `-w, --watch` | Suivre la progression de l'opération |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Récupérer / Restaurer une sauvegarde

Récupérez une sauvegarde de dépôt depuis un stockage externe :

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Option | Description |
|--------|-------------|
| `--from <storage>` | Emplacement de stockage source |
| `--from-machine <machine>` | Machine source pour la restauration de machine à machine |
| `--force` | Écraser la sauvegarde locale existante |
| `-w, --watch` | Suivre la progression de l'opération |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Lister les sauvegardes

Affichez les sauvegardes disponibles dans un emplacement de stockage :

```bash
rdc backup list --from my-storage -m server-1
```

## Synchronisation en masse

Envoyez ou récupérez tous les dépôts en une seule fois :

### Envoyer tout vers le stockage

```bash
rdc backup sync --to my-storage -m server-1
```

### Récupérer tout depuis le stockage

```bash
rdc backup sync --from my-storage -m server-1
```

| Option | Description |
|--------|-------------|
| `--to <storage>` | Stockage cible (direction envoi) |
| `--from <storage>` | Stockage source (direction récupération) |
| `--repo <name>` | Synchroniser des dépôts spécifiques (répétable) |
| `--override` | Écraser les sauvegardes existantes |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Sauvegardes planifiées

Automatisez les sauvegardes avec une planification cron qui s'exécute comme un timer systemd sur la machine distante.

### Définir la planification

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Option | Description |
|--------|-------------|
| `--destination <storage>` | Destination de sauvegarde par défaut |
| `--cron <expression>` | Expression cron (par ex., `"0 2 * * *"` pour tous les jours à 2h du matin) |
| `--enable` | Activer la planification |
| `--disable` | Désactiver la planification |

### Déployer la planification sur une machine

Déployez la configuration de planification sur une machine en tant que timer systemd :

```bash
rdc backup schedule push server-1
```

### Afficher la planification

```bash
rdc backup schedule show
```

## Parcourir le stockage

Parcourez le contenu d'un emplacement de stockage :

```bash
rdc storage browse my-storage -m server-1
```

## Bonnes pratiques

- **Planifiez des sauvegardes quotidiennes** vers au moins un fournisseur de stockage
- **Testez les restaurations** périodiquement pour vérifier l'intégrité des sauvegardes
- **Utilisez plusieurs fournisseurs de stockage** pour les données critiques (par ex., S3 + B2)
- **Gardez les identifiants en sécurité** — les sauvegardes sont chiffrées mais l'identifiant LUKS est nécessaire pour la restauration
