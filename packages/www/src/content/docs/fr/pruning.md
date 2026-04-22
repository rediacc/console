---
title: "Nettoyage"
description: "Supprimer les sauvegardes orphelines, les snapshots obsolètes et les images de dépôt inutilisées pour récupérer de l'espace disque."
category: "Guides"
order: 12
language: fr
sourceHash: "f355a0921afb72e9"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# Nettoyage

Le nettoyage supprime les ressources qui ne sont plus référencées par aucun fichier de configuration. Il existe deux commandes de nettoyage ciblant différents types de ressources :

- **`rdc storage prune`** -- supprime les fichiers de sauvegarde orphelins du stockage cloud/externe
- **`rdc machine prune`** -- nettoie les artefacts du datastore et (optionnellement) les images de dépôts orphelins sur une machine

## Storage Prune

Analyse un fournisseur de stockage et supprime les sauvegardes dont les GUIDs n'apparaissent plus dans aucun fichier de configuration.

```bash
# Dry-run (default), shows what would be deleted
rdc storage prune --name my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune --name my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune --name my-s3 -m server-1 --grace-days 14
```

### Ce qui est vérifié

1. Liste tous les GUIDs de sauvegarde dans le stockage nommé.
2. Analyse tous les fichiers de configuration sur le disque (`~/.config/rediacc/*.json`).
3. Une sauvegarde est **orpheline** si son GUID n'est référencé dans la section des dépôts d'aucune configuration.
4. Les dépôts récemment archivés dans la période de grâce sont **protégés** même s'ils ont été retirés de la configuration active.

## Machine Prune

Nettoie les ressources sur la machine en deux phases.

### Phase 1 : Nettoyage du datastore (s'exécute toujours)

Supprime toute catégorie de ressource pouvant subsister lorsqu'un dépôt est supprimé ou lorsqu'un refactoring au niveau de la machine met à la retraite une convention de nommage. Chaque catégorie est analysée indépendamment, et le nettoyage est une passe idempotente unique, de sorte qu'exécuter prune plusieurs fois est sûr et converge vers un datastore propre.

| Catégorie | Ce qui est supprimé |
|---------|-----------------|
| Répertoires de montage vides | Répertoires `mounts/<guid>/` sans image de dépôt associée |
| Répertoires immovable orphelins | Répertoires `immovable/<guid>/` sans image de dépôt associée |
| Fichiers de verrouillage obsolètes | `repositories/.lock-<guid>` pour des dépôts supprimés |
| Snapshots de sauvegarde obsolètes | `.snapshot-*` et `.backup-*` laissés par des exécutions de sauvegarde interrompues |
| Répertoires de sandbox VS Code orphelins | `.interim/sandbox/<name>` pour des dépôts qui ne sont plus actifs sur la machine |
| Chaînes iptables orphelines | Chaînes `REDIACC_WILDCARD_<N>` et `DOCKER_ISOLATED_NET_<N>` pour des réseaux supprimés |
| Entrées authorized_keys orphelines | Lignes `sandbox-gateway <repo> --guid <uuid>` dont le `--guid` ne correspond plus à un répertoire de montage actif |

L'analyse de `authorized_keys` parcourt `/home/*/.ssh/authorized_keys` et `/root/.ssh/authorized_keys`. Une entrée n'est conservée que si son marqueur `--guid` correspond au GUID d'un répertoire de montage vivant, de sorte que les dépôts actuellement déployés sur la machine sont toujours préservés, indépendamment du fait que leur nom apparaisse ou non ailleurs sur le disque. Les entrées héritées écrites avant que renet ne commence à ajouter le marqueur `--guid` ne peuvent pas être validées et sont toujours signalées comme orphelines.

```bash
# Dry-run, shows what would be removed (no changes applied)
rdc machine prune --name server-1 --dry-run

# Execute cleanup
rdc machine prune --name server-1
```

> **Nettoyage en cascade.** Certaines catégories dépendent des précédentes. Par exemple, la suppression de répertoires de montage vides peut faire apparaître des sandboxes orphelines supplémentaires dont le montage associé vient de disparaître. Réexécuter `rdc machine prune` une seconde fois rattrape la cascade et termine le nettoyage. Le dry-run final se conclut par `No orphaned resources found. Datastore is clean.` lorsqu'il ne reste plus rien à faire.

### Phase 2 : Images de dépôts orphelins (optionnel)

Avec `--orphaned-repos`, la CLI identifie également les images de dépôts LUKS sur la machine qui n'apparaissent dans aucun fichier de configuration et les supprime.

```bash
# Dry-run (default behavior when is set)
rdc machine prune --name server-1

# Actually delete orphaned repos
rdc machine prune --name server-1

# Custom grace period
rdc machine prune --name server-1 --grace-days 30
```

## Modèle de sécurité

Le nettoyage est conçu pour être sûr par défaut dans les configurations multiples.

### Prise en compte des configurations multiples

Les deux commandes de nettoyage analysent **tous** les fichiers de configuration dans `~/.config/rediacc/`, pas seulement celui qui est actif. Un dépôt référencé par `production.json` ne sera pas supprimé même s'il est absent de `staging.json`. Cela empêche les suppressions accidentelles lorsque les configurations sont destinées à différents environnements.

### Période de grâce

Lorsqu'un dépôt est retiré d'une configuration, il peut être archivé avec un horodatage. Les commandes de nettoyage respectent une période de grâce (7 jours par défaut) pendant laquelle les dépôts récemment archivés sont protégés contre la suppression. Cela vous laisse le temps de restaurer un dépôt s'il a été retiré accidentellement.

### Dry-run par défaut

`storage prune` et `machine prune` utilisent le mode dry-run par défaut. Ils affichent ce qui serait supprimé sans effectuer de modifications. Passez `--no-dry-run` ou `--force` pour exécuter la suppression effective.

## Configuration

### `pruneGraceDays`

Définissez une période de grâce par défaut personnalisée dans votre fichier de configuration pour ne pas avoir à passer `--grace-days` à chaque fois :

```bash
# Set grace period to 14 days in the active config
rdc config set --key pruneGraceDays --value 14
```

Le flag CLI `--grace-days` remplace cette valeur lorsqu'il est fourni.

### Ordre de priorité

1. Flag `--grace-days <N>` (priorité la plus élevée)
2. `pruneGraceDays` dans le fichier de configuration
3. Valeur par défaut intégrée : 7 jours

## Bonnes pratiques

- **Exécutez d'abord le dry-run.** Prévisualisez toujours avant d'exécuter un nettoyage destructif, surtout sur le stockage de production.
- **Gardez les configurations multiples à jour.** Le nettoyage vérifie toutes les configurations dans le répertoire de configuration. Si un fichier de configuration est obsolète ou supprimé, ses dépôts perdent leur protection. Gardez les fichiers de configuration à jour.
- **Utilisez des périodes de grâce généreuses pour la production.** La période de grâce par défaut de 7 jours convient à la plupart des workflows. Pour les environnements de production avec des fenêtres de maintenance peu fréquentes, envisagez 14 ou 30 jours.
- **Planifiez le storage prune après les exécutions de sauvegarde.** Associez `storage prune` à votre planification de sauvegarde pour maîtriser les coûts de stockage sans intervention manuelle.
- **Combinez machine prune avec backup schedule.** Après avoir déployé les planifications de sauvegarde (`rdc machine backup schedule`), ajoutez un nettoyage périodique de la machine pour supprimer les snapshots obsolètes et les artefacts de datastore orphelins.
- **Vérifiez avant d'utiliser `--force`.** Le flag `--force` contourne la période de grâce. Ne l'utilisez que lorsque vous êtes certain qu'aucune autre configuration ne référence les dépôts concernés.
