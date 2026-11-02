---
title: "Nettoyage"
description: "Supprimer les sauvegardes orphelines, les snapshots obsolètes, les images de dépôt et les résidus de configuration locale pour récupérer de l'espace disque et garder un état cohérent."
category: "Guides"
tags:
  - storage
  - operations
subcategory: data-protection
order: 12
language: fr
sourceHash: "7f1821cd35a53d7b"
sourceCommit: "3bd4b6e7faf8cd6cb396d19e31b222cbc97d1ff4"
---

# Nettoyage

Le nettoyage balaie les états qui ne correspondent plus à une ressource vivante. Deux commandes couvrent deux portées différentes. Les instantanés du stockage fragmenté n'en font pas partie : le serveur les élague selon une [politique de rétention](#backup-snapshots), par lignée et par flux de sauvegarde.

| Commande | Ce qu'elle nettoie | Où vit la source de vérité |
|---|---|---|
| `rdc machine prune <machine>` | Artefacts du datastore sur la machine (toujours) ; images de dépôt orphelines ou inconnues (opt-in) | Configuration CLI locale + le miroir `.interim/state` de la machine |
| `rdc config prune` | Résidus de la configuration locale (cache de certificats, archives expirées, références croisées orphelines) | Configuration CLI locale uniquement |

Les deux sont indépendantes. Vous pouvez exécuter l'une sans l'autre. Elles partagent un modèle de sécurité commun décrit sous [Sécurité](#safety-model) ci-dessous.

Le nettoyage supprime l'état laissé par des ressources supprimées. Pour récupérer l'espace occupé par les dépôts *actifs* (des blocs que leurs systèmes de fichiers ont libérés mais que le pool retient encore), utilisez [`rdc repo trim`](/fr/docs/repositories#reclaim-space-trim) à la place ; les deux sont complémentaires.

## Préflight de sécurité de montage

`machine prune --prune-unknown` exécute un **préflight de sécurité de montage** avant toute suppression : il interroge la machine pour connaître les dépôts actuellement montés ou en cours d'exécution, intersecte avec les candidats à la suppression, et **refuse de supprimer un candidat encore vivant sur la machine**. Supprimer une image de dépôt vivante est un véritable piège à perte de données. Le préflight rend cela impossible par accident.

Pour outrepasser (rare ; uniquement quand vous savez avec certitude que l'état vivant est faux), passez `--force-delete-mounted`. Il s'agit d'un flag distinct de `--force` (qui contrôle la période de grâce des archives) afin que les deux échappatoires restent distinctes.

## Instantanés de sauvegarde

Les instantanés envoyés avec `rdc backup snapshot` vivent dans le stockage fragmenté, et le serveur les élague. Il n'existe pas de commande de nettoyage côté client : déclarez combien d'historique conserver, et le serveur supprime le reste.

Une politique appartient à la lignée d'un dépôt, si bien qu'un dépôt et ses forks la partagent, et elle peut être remplacée pour un flux de sauvegarde (un dépôt sur une machine). Chaque flux conserve en outre ses instantanés les plus récents et son ancre actuelle quelle que soit la politique, si bien qu'un passage ne laisse jamais un flux à l'abandon.

```bash
# Afficher la politique actuelle et d'où elle vient
rdc backup retention my-app

# Voir ce que le prochain passage supprimerait et l'espace libéré, sans rien supprimer
rdc backup retention preview my-app

# Conserver 7 instantanés quotidiens, 4 hebdomadaires et 6 mensuels
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Remplacer la politique d'un seul flux
rdc backup retention set my-app --stream <stream-id> --keep-last 3

# Conserver de nouveau tous les instantanés
rdc backup retention clear my-app

# Supprimer un seul instantané maintenant ; le prochain ramasse-miettes libère ses données exclusives
rdc backup snapshots delete my-app <snapshot-id>
```

Les règles de la politique sont décrites dans [Sauvegarde et restauration](/fr/docs/backup-restore#retention) ; `rdc backup usage` indique ce que le stockage contient actuellement.

## Machine Prune

Nettoie les ressources sur la machine en trois phases. La phase 1 s'exécute toujours ; les phases 2 et 3 sont opt-in et peuvent être combinées.

### Phase 1 : Nettoyage du datastore (s'exécute toujours)

Supprime tout ce qui subsiste lorsqu'un dépôt est supprimé ou une convention de nommage mise à la retraite. Chaque catégorie est analysée indépendamment. L'exécution répétée de prune est sûre : c'est une seule passe idempotente, donc les orphelins manqués lors de la dernière exécution sont rattrapés par la suivante.

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
# Dry-run, affiche ce qui serait supprimé (aucune modification appliquée)
rdc machine prune server-1 --dry-run

# Exécuter le nettoyage
rdc machine prune server-1
```

> **Nettoyage en cascade.** Certaines catégories dépendent des précédentes. Par exemple, la suppression de répertoires de montage vides peut faire apparaître des sandboxes orphelines supplémentaires dont le montage associé vient de disparaître. Réexécuter `rdc machine prune` une seconde fois rattrape la cascade et termine le nettoyage. Le dry-run final se conclut par `No orphaned resources found. Datastore is clean.` lorsqu'il ne reste plus rien à faire.

### Phase 2 : `--orphaned-repos` (large)

Avec `--orphaned-repos`, la CLI supprime également les images de dépôt sur la machine qui n'apparaissent dans **aucun** fichier de configuration locale.

```bash
rdc machine prune server-1 --orphaned-repos --dry-run
rdc machine prune server-1 --orphaned-repos
```

C'est un nettoyage **large**. Il supprime tout ce qui n'est pas dans votre configuration locale, y compris les forks légitimes gérés par d'autres outils ou par le checkout CLI d'un autre opérateur. Si le miroir renet `.interim/state` identifie correctement un dépôt comme un fork mais que la configuration locale ne l'a jamais vu, cette phase le supprime quand même. Préférez la phase 3 (`--prune-unknown`) si vous voulez être conservateur.

### Phase 3 : `--prune-unknown` (chirurgical)

Avec `--prune-unknown`, la CLI ne supprime que les dépôts que **les deux** signaux échouent à classer : absents de toute configuration locale **et** sans entrée fork-marquée dans le miroir `.interim/state` de la machine (voir [Dépôts. Colonne `Type`](/fr/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune server-1 --prune-unknown --dry-run
rdc machine prune server-1 --prune-unknown
```

En pratique, `--prune-unknown` est ce que vous voulez pour le nettoyage de routine ; `--orphaned-repos` n'est correct que lorsque vous êtes certain que votre configuration locale est l'inventaire complet et faisant autorité de chaque dépôt sur la machine. Les orphelins hérités pré-miroir et les dépôts dont l'entrée de configuration a été supprimée par erreur tombent tous deux dans le seau « unknown ». Ils sont véritablement incertains, et le flag chirurgical demande à l'opérateur de l'acquitter explicitement.

Le préflight de sécurité de montage s'exécute également sur cette phase : un dépôt actuellement monté sur `--machine` est signalé et ignoré sauf si `--force-delete-mounted` est passé.

```bash
# Combiné : nettoyage complet de la machine avec le chemin chirurgical conscient des forks
rdc machine prune server-1 --prune-unknown
```

## Config Prune

Balaie les résidus obsolètes **à l'intérieur du fichier de configuration local** dans `~/.config/rediacc/<config>.json`. Purement local. Pas de SSH, pas d'appels renet. Trois seaux sont nettoyés :

1. **Entrées du cache de certificats ACME** dont l'ancrage (GUID, nom de dépôt ou nom de machine) n'est plus dans la configuration active. Les wildcards de certificats ne peuvent plus router nulle part, ce ne sont que des poids morts.
2. **Dépôts archivés expirés** dans `resources.deletedRepositories[]`. Entrées dont `deletedAt` est plus ancien que `defaults.pruneGraceDays` (par défaut 7 jours). Les entrées encore en grâce sont signalées (avec les jours restants) et conservées.
3. **Références croisées orphelines** entre seaux de configuration :
   - Entrées `resources.machines.<m>.backupStrategies[]` nommant une stratégie qui n'existe plus.
   - Entrées `resources.backupStrategies.<s>.exclude[]` et `include[]` nommant un dépôt qui n'existe plus.

```bash
# Aperçu uniquement
rdc config prune --dry-run

# Appliquer (comportement par défaut)
rdc config prune

# Restreindre à un seul seau
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Supprimer TOUS les dépôts archivés indépendamment de la grâce
rdc config prune --purge-archived

# Outrepasser la fenêtre de grâce d'archive pour cette invocation
rdc config prune --grace-days 30
```

### Ce que ça ne touche PAS

- Les ressources actives (machines, dépôts, stratégies de sauvegarde, fournisseurs cloud).
- Les identifiants, le bloc account, le bloc encryption, les defaults.
- Les entrées `knownHosts` (le chemin de rafraîchissement automatique est `rdc machine scan-keys`).
- Le tableau de blob de certificat compressé (`infra.acmeCertCache.<base>.data[]`) est reconstruit automatiquement à partir de la liste de certificats nettoyée ; vous ne perdez aucune chaîne qui couvre encore un nom conservé.

### Exemple concret

Sortie d'une exécution réelle sur une machine avec quatre wildcards à GUID orphelin et deux wildcards à nom de machine obsolète :

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Les noms de certificats dont l'ancrage est une machine, un dépôt ou un GUID vivant sont laissés intacts, de même que tout wildcard `<service>.<base>` à étiquette unique ou racine `*.<base>`.

## Migration : backfill du miroir d'état

Le miroir `.interim/state/<guid>/.rediacc.json` qui alimente `--prune-unknown` et la colonne `Type` dans `rdc repo list -m` est écrit :

- **Au moment du fork** (`rdc repo fork`). Immédiatement, avant même que le fork ne soit jamais monté.
- **À chaque enregistrement d'état** (`rdc repo up` et toute opération qui met à jour l'état du dépôt). Pour les dépôts créés avant le déploiement du code de miroir.

Les dépôts qui ont été créés **avant l'existence du miroir et qui n'ont pas été remontés depuis la mise à niveau** n'ont pas de fichier miroir. Ils apparaissent comme `unknown` dans `rdc repo list -m` même si certains sont légitimement des forks. Pour corriger cela pour les orphelins hérités, exécutez le backfill ponctuel sur la machine :

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

Le backfill copie l'état vivant interne au volume vers le miroir pour les dépôts actuellement montés et écrit un miroir synthétique fork-marqué pour les GUIDs listés sous `--mark-as-fork`. Après le backfill, les sauvegardes planifiées cessent de téléverser les forks listés (le pipeline de téléversement vérifie le miroir pour `is_fork: true`).

## Modèle de sécurité

Le nettoyage est conçu pour être sûr par défaut dans les configurations multiples.

### Prise en compte des configurations multiples

`machine prune --orphaned-repos` analyse **tous** les fichiers de configuration dans `~/.config/rediacc/`, pas seulement le fichier actif. Un dépôt référencé par `production.json` ne sera pas supprimé même s'il est absent de `staging.json`. Cela empêche les suppressions accidentelles lorsque les configurations sont destinées à différents environnements.

### Période de grâce

Lorsqu'un dépôt est retiré d'une configuration avec `--archive-config`, son entrée d'identifiant est déplacée vers `resources.deletedRepositories[]` avec un horodatage `deletedAt`. Les commandes de nettoyage respectent une période de grâce (par défaut 7 jours) pendant laquelle les dépôts récemment archivés sont protégés contre la suppression. Cela vous laisse le temps de restaurer un dépôt (`rdc repo admin archive restore <guid>`) s'il a été retiré accidentellement. Une fois la grâce expirée, `machine prune` et `config prune` purgent tous deux automatiquement l'entrée.

### Préflight de sécurité de montage

Couvert ci-dessus. `machine prune --prune-unknown` refuse de supprimer les dépôts actuellement montés ou en cours d'exécution sur la machine. Outrepasser uniquement avec `--force-delete-mounted`.

### Application par défaut ; `--dry-run` pour prévisualiser

Les deux commandes prune **appliquent** les modifications par défaut. Passez `--dry-run` pour prévisualiser sans écrire. Cela correspond au verbe : « prune » est destructif en soi, et un flag dry-run est l'opt-out explicite.

## Configuration

### `pruneGraceDays`

Définissez une période de grâce par défaut personnalisée dans votre fichier de configuration pour ne pas avoir à passer `--grace-days` à chaque fois :

```bash
# Définir la période de grâce à 14 jours dans la configuration active
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

Le flag CLI `--grace-days` remplace cette valeur lorsqu'il est fourni.

### Ordre de priorité

1. Flag `--grace-days <N>` (priorité la plus élevée)
2. `pruneGraceDays` dans le fichier de configuration
3. Valeur par défaut intégrée : 7 jours

## Bonnes pratiques

- **Exécutez d'abord le dry-run en production.** Prévisualisez toujours avant d'exécuter un nettoyage destructif.
- **Gardez les configurations multiples à jour.** Machine prune vérifie toutes les configurations dans le répertoire de configuration. Si un fichier de configuration est obsolète ou supprimé, ses dépôts perdent leur protection. Gardez les fichiers de configuration à jour.
- **Préférez `--prune-unknown` à `--orphaned-repos`.** Le flag chirurgical respecte le miroir renet ; le flag large supprimera volontiers les forks que d'autres outils ont créés.
- **Utilisez des périodes de grâce généreuses pour la production.** La période de grâce par défaut de 7 jours convient à la plupart des workflows. Pour les environnements de production avec des fenêtres de maintenance peu fréquentes, envisagez 14 ou 30 jours.
- **Déclarez une politique de rétention.** `rdc backup retention set` maîtrise le coût de stockage des instantanés sans intervention manuelle.
- **Combinez machine prune avec backup schedule.** Après avoir déployé les planifications de sauvegarde (`rdc backup schedule`), ajoutez un nettoyage périodique de la machine pour supprimer les snapshots obsolètes et les artefacts de datastore orphelins.
- **Exécutez `config prune` périodiquement.** Le ballonnement de la configuration locale (en particulier le cache de certificats) s'accumule silencieusement ; un `config prune --dry-run` trimestriel suffit à le détecter.
- **Vérifiez avant d'utiliser `--force` ou `--force-delete-mounted`.** Les deux flags contournent les vérifications de sécurité. N'utilisez `--force` que lorsque vous êtes certain qu'aucune autre configuration ne référence les dépôts concernés ; n'utilisez `--force-delete-mounted` que lorsque vous êtes certain que l'état vivant sur la machine est faux.
