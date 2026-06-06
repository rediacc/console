---
title: "Nettoyage"
description: "Supprimer les sauvegardes orphelines, les snapshots obsolètes, les images de dépôt et les résidus de configuration locale pour récupérer de l'espace disque et garder un état cohérent."
category: "Guides"
order: 12
language: fr
sourceHash: "9b74e1ea24b9735f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Nettoyage

Le nettoyage balaie les états qui ne correspondent plus à une ressource vivante. Trois commandes couvrent trois portées différentes :

| Commande | Ce qu'elle nettoie | Où vit la source de vérité |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Sauvegardes orphelines dans le stockage cloud | Configuration CLI locale (recoupée avec la machine d'exécution pour la sécurité de montage) |
| `rdc machine prune --name <machine>` | Artefacts du datastore sur la machine (toujours) ; images de dépôt orphelines ou inconnues (opt-in) | Configuration CLI locale + le miroir `.interim/state` de la machine |
| `rdc config prune` | Résidus de la configuration locale (cache de certificats, archives expirées, références croisées orphelines) | Configuration CLI locale uniquement |

Les trois sont indépendantes. Vous pouvez exécuter n'importe laquelle sans les autres. Elles partagent un modèle de sécurité commun décrit sous [Sécurité](#modèle-de-sécurité) ci-dessous.

## Préflight de sécurité de montage

`storage prune` et `machine prune --prune-unknown` exécutent tous deux un **préflight de sécurité de montage** avant toute suppression : ils interrogent la machine d'exécution pour connaître les dépôts actuellement montés ou en cours d'exécution, intersectent avec les candidats à la suppression, et **refusent de supprimer un candidat encore vivant sur la machine**. Supprimer la sauvegarde hors machine d'un dépôt monté, ou supprimer une image de dépôt vivante, est un véritable piège à perte de données. Le préflight rend cela impossible par accident.

Pour outrepasser (rare ; uniquement quand vous savez avec certitude que l'état vivant est faux), passez `--force-delete-mounted`. Il s'agit d'un flag distinct de `--force` (qui contrôle la période de grâce des archives) afin que les deux échappatoires restent distinctes.

## Storage Prune

Analyse un fournisseur de stockage et supprime les sauvegardes dont les GUIDs n'apparaissent plus dans aucun fichier de configuration locale.

```bash
# Aperçu uniquement — affiche ce qui serait supprimé
rdc storage prune --name my-s3 -m server-1 --dry-run

# Supprime réellement les sauvegardes orphelines (comportement par défaut)
rdc storage prune --name my-s3 -m server-1

# Outrepasser la période de grâce (par défaut 7 jours)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Outrepasser la vérification de sécurité de montage (à utiliser avec précaution)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` est requis car les appels rclone s'exécutent sur la machine d'exécution, pas sur votre poste. Les clients ne sont pas censés avoir rclone installé localement. Les identifiants de stockage proviennent toujours de votre configuration locale ; la machine n'est qu'un exécuteur rclone.

### Ce qui est vérifié

1. Liste tous les GUIDs de sauvegarde dans le stockage nommé (à travers les sous-répertoires `hot/` et `cold/`. Voir [Sauvegarde et restauration](/fr/docs/backup-restore#sauvegardes-planifiées)).
2. Analyse tous les fichiers de configuration sur le disque (`~/.config/rediacc/*.json`).
3. Une sauvegarde est **orpheline** si son GUID n'est référencé dans la section repositories d'aucune configuration.
4. Les dépôts récemment archivés dans la période de grâce sont **protégés** même s'ils ont été retirés de la configuration active.
5. Préflight de sécurité de montage : les GUIDs actuellement montés sur `--machine` sont ignorés et signalés, jamais supprimés.

### Performance

Les suppressions sont regroupées par sous-chemin de stockage : un appel rclone par répertoire `hot/` ou `cold/` quel que soit le nombre de GUIDs supprimés. Un retard de 11 orphelins passe de ~50 s de surcharge SSH à un seul aller-retour par sous-chemin.

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
rdc machine prune --name server-1 --dry-run

# Exécuter le nettoyage
rdc machine prune --name server-1
```

> **Nettoyage en cascade.** Certaines catégories dépendent des précédentes. Par exemple, la suppression de répertoires de montage vides peut faire apparaître des sandboxes orphelines supplémentaires dont le montage associé vient de disparaître. Réexécuter `rdc machine prune` une seconde fois rattrape la cascade et termine le nettoyage. Le dry-run final se conclut par `No orphaned resources found. Datastore is clean.` lorsqu'il ne reste plus rien à faire.

### Phase 2 : `--orphaned-repos` (large)

Avec `--orphaned-repos`, la CLI supprime également les images de dépôt sur la machine qui n'apparaissent dans **aucun** fichier de configuration locale.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

C'est un nettoyage **large**. Il supprime tout ce qui n'est pas dans votre configuration locale, y compris les forks légitimes gérés par d'autres outils ou par le checkout CLI d'un autre opérateur. Si le miroir renet `.interim/state` identifie correctement un dépôt comme un fork mais que la configuration locale ne l'a jamais vu, cette phase le supprime quand même. Préférez la phase 3 (`--prune-unknown`) si vous voulez être conservateur.

### Phase 3 : `--prune-unknown` (chirurgical)

Avec `--prune-unknown`, la CLI ne supprime que les dépôts que **les deux** signaux échouent à classer : absents de toute configuration locale **et** sans entrée fork-marquée dans le miroir `.interim/state` de la machine (voir [Dépôts. Colonne `Type`](/fr/docs/repositories#colonne-type-et-le-miroir-detat)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

En pratique, `--prune-unknown` est ce que vous voulez pour le nettoyage de routine ; `--orphaned-repos` n'est correct que lorsque vous êtes certain que votre configuration locale est l'inventaire complet et faisant autorité de chaque dépôt sur la machine. Les orphelins hérités pré-miroir et les dépôts dont l'entrée de configuration a été supprimée par erreur tombent tous deux dans le seau « unknown ». Ils sont véritablement incertains, et le flag chirurgical demande à l'opérateur de l'acquitter explicitement.

Le préflight de sécurité de montage s'exécute également sur cette phase : un dépôt actuellement monté sur `--machine` est signalé et ignoré sauf si `--force-delete-mounted` est passé.

```bash
# Combiné : nettoyage complet de la machine avec le chemin chirurgical conscient des forks
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Balaie les résidus obsolètes **à l'intérieur du fichier de configuration local** dans `~/.config/rediacc/<config>.json`. Purement local. Pas de SSH, pas d'appels renet. Trois seaux sont nettoyés :

1. **Entrées du cache de certificats ACME** dont l'ancrage (GUID, nom de dépôt ou nom de machine) n'est plus dans la configuration active. Les wildcards de certificats ne peuvent plus router nulle part, ce ne sont que des poids morts.
2. **Dépôts archivés expirés** dans `resources.deletedRepositories[]`. Entrées dont `deletedAt` est plus ancien que `defaults.pruneGraceDays` (par défaut 7 jours). Les entrées encore en grâce sont signalées (avec les jours restants) et conservées.
3. **Références croisées orphelines** entre seaux de configuration :
   - Entrées `resources.machines.<m>.backupStrategies[]` nommant une stratégie qui n'existe plus.
   - Entrées `resources.backupStrategies.<s>.exclude[]` et `include[]` nommant un dépôt qui n'existe plus.
   - Destinations de stockage dont le stockage cible est manquant. Signalées en avertissement, pas auto-supprimées (la suppression automatique changerait la sémantique de la stratégie).

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

- Les ressources actives (machines, stockages, dépôts, stratégies de sauvegarde, fournisseurs cloud).
- Les identifiants, le bloc account, le bloc encryption, les defaults.
- Le `vaultContent` du stockage (y compris les `access_token` OneDrive expirés. Le refresh_token continue à en émettre de nouveaux ; nettoyer forcerait une ré-authentification).
- Les entrées `knownHosts` (le chemin de rafraîchissement automatique est `rdc config machine scan-keys`).
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
- **À chaque enregistrement d'état** (`rdc repo mount` et toute opération qui met à jour l'état du dépôt). Pour les dépôts créés avant le déploiement du code de miroir.

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

`storage prune` et `machine prune --orphaned-repos` analysent **tous** les fichiers de configuration dans `~/.config/rediacc/`, pas seulement le fichier actif. Un dépôt référencé par `production.json` ne sera pas supprimé même s'il est absent de `staging.json`. Cela empêche les suppressions accidentelles lorsque les configurations sont destinées à différents environnements.

### Période de grâce

Lorsqu'un dépôt est retiré d'une configuration avec `--archive-config`, son entrée d'identifiant est déplacée vers `resources.deletedRepositories[]` avec un horodatage `deletedAt`. Les commandes de nettoyage respectent une période de grâce (par défaut 7 jours) pendant laquelle les dépôts récemment archivés sont protégés contre la suppression. Cela vous laisse le temps de restaurer un dépôt (`rdc config repository restore-archived --name <guid>`) s'il a été retiré accidentellement. Une fois la grâce expirée, `storage prune`, `machine prune` et `config prune` purgent tous automatiquement l'entrée.

### Préflight de sécurité de montage

Couvert ci-dessus. `storage prune` et `machine prune --prune-unknown` refusent de supprimer les dépôts actuellement montés ou en cours d'exécution sur la machine d'exécution. Outrepasser uniquement avec `--force-delete-mounted`.

### Application par défaut ; `--dry-run` pour prévisualiser

Les trois commandes prune **appliquent** les modifications par défaut. Passez `--dry-run` pour prévisualiser sans écrire. Cela correspond au verbe : « prune » est destructif en soi, et un flag dry-run est l'opt-out explicite.

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

- **Exécutez d'abord le dry-run en production.** Prévisualisez toujours avant d'exécuter un nettoyage destructif, surtout sur le stockage de production.
- **Gardez les configurations multiples à jour.** Storage et machine prune vérifient toutes les configurations dans le répertoire de configuration. Si un fichier de configuration est obsolète ou supprimé, ses dépôts perdent leur protection. Gardez les fichiers de configuration à jour.
- **Préférez `--prune-unknown` à `--orphaned-repos`.** Le flag chirurgical respecte le miroir renet ; le flag large supprimera volontiers les forks que d'autres outils ont créés.
- **Utilisez des périodes de grâce généreuses pour la production.** La période de grâce par défaut de 7 jours convient à la plupart des workflows. Pour les environnements de production avec des fenêtres de maintenance peu fréquentes, envisagez 14 ou 30 jours.
- **Planifiez le storage prune après les exécutions de sauvegarde.** Associez `storage prune` à votre planification de sauvegarde pour maîtriser les coûts de stockage sans intervention manuelle.
- **Combinez machine prune avec backup schedule.** Après avoir déployé les planifications de sauvegarde (`rdc machine backup schedule`), ajoutez un nettoyage périodique de la machine pour supprimer les snapshots obsolètes et les artefacts de datastore orphelins.
- **Exécutez `config prune` périodiquement.** Le ballonnement de la configuration locale (en particulier le cache de certificats) s'accumule silencieusement ; un `config prune --dry-run` trimestriel suffit à le détecter.
- **Vérifiez avant d'utiliser `--force` ou `--force-delete-mounted`.** Les deux flags contournent les vérifications de sécurité. N'utilisez `--force` que lorsque vous êtes certain qu'aucune autre configuration ne référence les dépôts concernés ; n'utilisez `--force-delete-mounted` que lorsque vous êtes certain que l'état vivant sur la machine est faux.
