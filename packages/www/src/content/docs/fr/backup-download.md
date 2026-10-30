---
title: "Téléchargement de sauvegarde"
description: "Copier l'image chiffrée d'un dépôt vers un répertoire local ou un disque externe, la mettre à jour sur place aux exécutions suivantes, ou la reconstruire directement depuis le magasin de sauvegarde, sans machine."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: fr
sourceHash: "c52e6a0471befc30"
---

# Téléchargement de sauvegarde

`rdc backup download` conserve une copie de l'image chiffrée d'un dépôt dans un répertoire local ou sur un disque externe. La copie est le même texte chiffré que celui qui se trouve sur la machine, donc rien n'est déchiffré en chemin. L'identifiant qui l'ouvre reste dans la configuration, ce qui fait de l'inscription à [config storage](/fr/docs/config-storage) le moyen de le garder en sûreté. Sans cet identifiant, l'image ne peut pas être ouverte.

Il y a deux sources. Une machine en fonctionnement est la source par défaut. Le magasin de sauvegarde est l'autre, sélectionné avec `--store`.

## Téléchargement depuis une machine

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` désigne un répertoire existant et accessible en écriture. Il n'est jamais créé, le disque doit donc être monté au préalable. L'image est placée dans `<machine>/<name>.<tag>.img`, avec un fichier `.state.json` à côté.

Chaque exécution prend un instantané neuf du dépôt, conservé uniquement pendant la durée du transfert, envoie les différences avec rsync et compare un sha256 du résultat à l'instantané de la machine.

| Flag | Effet |
|------|--------|
| `--all -m <machine>` | Copier tous les dépôts grand placés sur la machine |
| `--include-forks` | Avec `--all`, copier aussi les forks |
| `--bwlimit <rate>` | Plafonner la bande passante réseau, par exemple `100Mbps` ou `12.5M` |
| `--checkpoint` | Faire un checkpoint et geler le dépôt avant l'instantané (sauvegarde à chaud) |
| `--retries <n>` | Nouvelles tentatives dans l'exécution après un échec réseau (3 par défaut) |
| `--skip-verify` | Ignorer la comparaison sha256 ; la somme de contrôle propre à rsync s'exécute toujours |
| `--skip-space-check` | Avertir au lieu de refuser lorsque la cible risque de manquer d'espace libre |

### Mise à jour de la copie

Une deuxième exécution met à jour l'image existante sur place par delta rsync. Une exécution hebdomadaire n'envoie que ce qui a changé, et la cible a besoin de place pour une seule copie de l'image, pas pour deux. Avant le début d'une exécution, l'espace libre est comparé à la taille de l'image, et `--skip-space-check` transforme un refus en avertissement.

### Exécutions interrompues et reprise

Le fichier d'état enregistre `status`. Il vaut `incomplete` dès avant l'écriture du premier octet et jusqu'à la vérification d'une exécution, et une image `incomplete` est inutilisable. Ctrl-C, une connexion perdue ou un processus tué la laissent dans cet état. Relancer la même commande reprend le transfert, et seules les différences sont envoyées. La commande se termine avec le code 0 une fois le statut passé à `complete`.

### Prérequis

Le transfert exige rsync 3.1.3 ou plus récent sur cet ordinateur et n'offre aucun repli SFTP. Les distributions Linux le fournissent. Sous macOS, `brew install rsync` remplace openrsync, fourni avec le système, qui ne peut pas exécuter le transfert. Sous Windows, installer MSYS2 avec le paquet rsync, ou utiliser l'application de bureau.

### Disques externes

Le système de fichiers de la cible décide de ce qui tient.

- **FAT32** ne peut pas contenir un fichier de plus de 4 GiB, et la commande refuse l'exécution.
- **exFAT** sans prise en charge des fichiers creux stocke l'image à sa taille apparente complète, si bien que la vérification de l'espace libre compte cette taille.
- Un **instantané copy-on-write** pris localement de la cible (btrfs, ZFS, APFS) conserve les versions antérieures de l'image. Chaque mise à jour sur place coûte alors les blocs modifiés en plus des anciens.

## Téléchargement depuis le magasin de sauvegarde

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` reconstruit l'image directement depuis le magasin de chunks, sans aucune machine. Le jeton de `REDIACC_TOKEN` a besoin des scopes `backup:read` et `backup:restore`. Une connexion CLI ne porte jamais `backup:restore` : le jeton se crée donc sur la page API Tokens du portail. Il doit appartenir à une équipe et avoir été créé par un propriétaire ou un administrateur actuel de l'organisation.

`--store` prend exactement un nom de dépôt. Il n'accepte ni `-m`, ni `--checkpoint`, ni `--all`, ni `--include-forks`, ni `--bwlimit`, ni `--retries`, ni `--skip-verify`, ni `--skip-space-check` : la récupération depuis le magasin a sa propre reprise et vérifie chaque chunk.

L'image est écrite dans `<dir>/<name>.<tag>.img`. Une récupération interrompue conserve la copie partielle, et la même commande reprend à partir de celle-ci.

### Choisir un instantané avec `--at`

Par défaut, l'instantané le plus récent est récupéré. `--at <time|snapshot>` en sélectionne un autre, soit une date en ISO 8601, soit un identifiant d'instantané. L'option ne s'applique qu'avec `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Sur une plateforme autre que Linux, l'image récupérée est chiffrée et ne peut pas être ouverte localement. Elle s'envoie vers une machine Linux avec `rdc backup upload`.

## Renvoyer une copie

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` envoie une image téléchargée vers une machine et l'enregistre comme nouveau dépôt. Le transfert reprend après une interruption, et la machine vérifie le sha256 et l'en-tête LUKS avant de placer l'image. Le fichier d'état situé à côté de l'image fournit l'identifiant. Lorsque ce fichier est perdu, `--from-repo <name>` désigne le dépôt qui le fournit.

| Flag | Effet |
|------|--------|
| `--as <name>` | Nom du nouveau dépôt (par défaut : le nom de l'image) |
| `--datastore <name>` | Placer l'image sur un datastore nommé |
| `--from-repo <name>` | Fournir l'identifiant et la lignée lorsque le fichier d'état est inutilisable |
| `--bwlimit <rate>`, `--retries <n>` | Identiques au téléchargement |
| `--up` | Démarrer le dépôt une fois enregistré |
| `--skip-verify` | Ignorer la comparaison avec le sha256 enregistré au téléchargement |

## Instantanés de transfert obsolètes

Un transfert tué brutalement peut laisser son instantané sur la machine. `rdc machine status` compte les instantanés de transfert obsolètes dans le résumé du pool, et `rdc machine prune <machine> --dry-run` les liste. Exécuter `rdc machine prune <machine>` les supprime.

Voir [Sauvegarde et restauration](/fr/docs/backup-restore) pour les instantanés vers le stockage de chunks.
