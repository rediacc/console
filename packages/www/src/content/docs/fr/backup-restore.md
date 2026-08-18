---
title: "Sauvegarde et restauration"
description: "Prenez des instantanés des dépôts chiffrés vers un stockage fragmenté adressé par contenu, où seules les cellules modifiées sont envoyées et chaque instantané se restaure directement. Ou conservez une copie sur une autre machine. Restaurez n'importe où, et automatisez avec des stratégies nommées et des timers systemd."
category: "Guides"
order: 7
language: fr
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Sauvegarde et restauration

Rediacc sauvegarde des dépôts chiffrés et les restaure sur la même machine ou sur une machine différente. Les sauvegardes sont chiffrées parce que le dépôt l'est : ce qui quitte la machine, c'est le texte chiffré, et l'identifiant LUKS de votre dépôt est nécessaire pour la restauration.

Il existe deux façons de sauvegarder, et elles répondent à des questions différentes.

- **Les instantanés vers le stockage fragmenté** (`rdc backup snapshot`) conservent un historique dans lequel vous pouvez remonter. C'est la voie principale.
- **Une copie sur une autre machine** (`rdc repo push`, `rdc repo pull`) conserve le dépôt tel qu'il est maintenant, sur du matériel que vous contrôlez. Aucun compte cloud n'est impliqué.

Elles sont indépendantes. Un dépôt sauvegardé d'une façon n'est pas sauvegardé de l'autre.

## Comment fonctionnent les instantanés

L'image du dépôt est découpée en cellules de taille fixe sur une grille fixe. Chaque cellule est soit un trou, ce qui signifie que rien n'y a jamais été écrit, soit elle est stockée sous une clé qui **est** le SHA-256 du texte chiffré de cette cellule.

C'est de cette seule décision que découlent les propriétés.

**Seuls les vrais changements coûtent quelque chose.** Le premier instantané envoie chaque cellule écrite. Chaque exécution suivante demande au système de fichiers quels extents ont été touchés, ne lit et ne hashe que ceux-là, et n'envoie que les cellules que le stockage ne possède pas encore. Un dépôt dont les données ont à peine bougé n'envoie presque rien, et l'exécution prend quelques minutes plutôt qu'un temps proportionnel à la taille de l'image.

**Les données identiques sont stockées une seule fois.** Comme la clé est le hash du contenu, deux instantanés qui partagent une cellule partagent le même objet, et il en va de même pour un dépôt et ses [forks](/fr/docs/tutorial-forking) : une famille de forks se sauvegarde contre une lignée unique plutôt que de dupliquer son parent.

**Restaurer un ancien instantané n'est pas plus lent que d'en restaurer un récent.** Il n'y a pas de chaîne d'incréments à rejouer. La restauration résout l'instantané en une liste complète de cellules et récupère ces cellules directement, si bien que le temps de restauration dépend de la taille de l'image et de votre bande passante, pas de la durée pendant laquelle vous faites des sauvegardes. Les trous restent des trous, si bien qu'une image creuse se restaure creuse, et une cellule qui apparaît à plusieurs endroits de l'image n'est téléchargée qu'une seule fois.

**Chaque instantané tient tout seul.** Il n'y a pas de « sauvegarde complète » que vous ne devez pas perdre, ni de fenêtre où un incrément défectueux invalide ceux qui suivent. Tout instantané de la liste est directement restaurable.

**La vérification, c'est du rehachage, pas de la confiance.** Comme la clé est le hash du contenu, vérifier une sauvegarde signifie récupérer des cellules et les hacher. `rdc backup verify` échantillonne ; `rdc backup verify --deep` rehache chaque cellule enregistrée.

**Une exécution interrompue n'est pas gaspillée.** L'envoi reprend sans renvoyer les cellules déjà arrivées, et le redémarrage d'une restauration partielle rehache ce qui est déjà sur le disque et le réutilise plutôt que de le retélécharger.

### Ce que cela vous coûte

Le quota est compté en **octets physiques uniques stockés** : ce qui est réellement conservé après déduplication, pas la somme de ce que vos instantanés représentent logiquement. Trente instantanés d'un dépôt qui change lentement coûtent presque comme un seul. `rdc backup usage` affiche les octets stockés par rapport à votre quota, un nombre par abonnement qui commence à 10 Go sur une offre Community.

### Ce dont les instantanés ont besoin

L'envoi d'un instantané passe par le serveur de compte, qui autorise chaque exécution par rapport à la licence installée du dépôt et remet à la machine une autorisation d'écriture de courte durée. Cette voie nécessite donc un serveur de compte que la machine peut atteindre et un dépôt sous licence. Sans eux, l'instantané est refusé plutôt que discrètement ignoré, et `rdc backup manifests`, `rdc backup usage` et `rdc backup retention` n'ont rien à lire.

Cela inclut `--dry-run`. La licence est lue avant que l'exécution ne décide si elle planifie ou envoie, si bien qu'une exécution à blanc est un aperçu du travail, pas un moyen d'essayer la commande sans identifiants.

Le push et le pull de machine à machine n'ont besoin ni de l'un ni de l'autre. Ce sont des transferts directs entre deux machines déjà présentes dans votre configuration.

### Ce qu'un instantané ne promet pas

- **Un instantané couvre un dépôt, pas toute votre machine à la fois.** Chaque dépôt est capturé à son propre instant. Si deux dépôts dépendent l'un de l'autre, leurs instantanés ne forment pas une paire coordonnée.
- **Ce n'est pas une réplication continue.** Un instantané est un point que vous avez pris, et vous pouvez perdre tout ce qui a été écrit depuis le dernier. Combien dépend de la fréquence à laquelle vous l'exécutez.
- **Les objets stockés sont en écriture unique, pas un WORM certifié.** Les cellules sont écrites avec une condition de création seule, l'autorisation qu'obtient une machine ne peut rien supprimer, et les suppressions se font côté serveur selon la politique de rétention. C'est une vraie barrière contre une machine compromise qui détruirait ses propres sauvegardes. Ce n'est pas une certification de conformité, et ce n'est pas audité comme telle.

### La voie de stockage rclone a disparu

`rdc repo push --to <storage>` et ses variantes copiaient auparavant un fichier de sauvegarde complet vers un fournisseur compatible rclone que vous enregistriez vous-même. Elles refusent maintenant une destination de stockage et nomment leur remplaçant. Le transfert de machine à machine n'est pas concerné : il n'est jamais passé par rclone. Si vous avez encore besoin de lire une archive écrite de cette façon, voir [Lire une archive écrite avant le retrait](#reading-an-archive-written-before-the-retirement).

### Commandes de stockage fragmenté

```bash
# Envoyer un instantané. La première exécution amorce, les suivantes n'envoient que les cellules modifiées.
rdc backup snapshot my-app

# Planifier sans envoyer : indique ce qui serait déplacé.
rdc backup snapshot my-app --dry-run

# Arrêter les conteneurs, geler, redémarrer, puis envoyer.
rdc backup snapshot my-app --cold

# Ne pas faire confiance à l'ancre locale et renvoyer tout l'inventaire.
# Ceci renvoie tout et recharge le quota ; à n'utiliser que lorsque
# l'ancre est connue pour être défaillante.
rdc backup snapshot my-app --reseed

# Vérifier l'inventaire stocké et votre quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Option | Description |
|--------|-------------|
| `<repo-ref>` (positionnel) | Dépôt à sauvegarder |
| `--dry-run` | Planification seule : pas d'envoi. Indique ce qui serait déplacé |
| `--cold` | Arrêter les conteneurs, geler, redémarrer, puis envoyer. Ne se combine pas avec `--dry-run` |
| `--reseed` | Ne pas faire confiance à l'ancre locale et envoyer un inventaire complet. Renvoie tout et recharge le quota |
| `--debug` | Activer la sortie détaillée |

## Instantanés à froid (`--cold`)

Un instantané à froid arrête un dépôt avant de le figer : l'image stockée est donc cohérente au niveau applicatif plutôt que cohérente en cas de crash. La commande s'exécute sur la machine elle-même :

```bash
# Tous les dépôts du datastore par défaut.
sudo renet backup snapshot --cold

# Uniquement les dépôts nommés. --repo prend un GUID de dépôt et se répète.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` ne se combine pas avec `--dry-run`. Une exécution à blanc qui arrête des conteneurs n'est pas à blanc, et une qui ne les arrête pas n'est pas à froid : renet refuse donc la combinaison au lieu de choisir un sens à votre place.

### Ce que fait une exécution à froid

Pour chaque dépôt sélectionné, dans cet ordre :

1. Arrêter ses conteneurs.
2. Écrire sur disque le montage du dépôt et le datastore.
3. Vérifier que les conteneurs se sont réellement arrêtés.
4. Prendre un reflink copie-sur-écriture de l'image du dépôt.
5. Redémarrer les conteneurs.

L'envoi ne commence qu'ensuite, alors que tous les dépôts sont déjà repartis.

Le temps d'arrêt, c'est le gel, pas le transfert. Un reflink ne touche que des métadonnées : il prend le même temps que le dépôt pèse 1 GB ou 100 GB. Un envoi, lui, grandit avec les octets modifiés, et un premier instantané envoie tout l'inventaire non nul. Garder les conteneurs arrêtés jusqu'à la fin de l'envoi lierait le temps d'arrêt au volume des données, soit des heures au lieu de quelques millisecondes lors du premier envoi.

Tous les dépôts sélectionnés sont arrêtés dans une seule fenêtre plutôt qu'un par un. Cela coûte un peu plus de temps d'arrêt par dépôt, et cela offre un point de cohérence unique sur l'ensemble.

Un dépôt sans conteneur en cours d'exécution est déjà au repos. Il est capturé sans le moindre temps d'arrêt, et c'est un résultat normal, pas un échec.

### Ce que coûte le temps d'arrêt

Mesuré sur une machine réelle, le temps d'arrêt total a été de **222 ms** :

| Phase | Mesuré | Ce qui se passe |
|-------|--------|-----------------|
| `cold_down` | 64 ms | Les conteneurs s'arrêtent |
| `cold_sync` | 26 ms | Montages du dépôt et datastore écrits sur disque |
| `cold_verify` | 31 ms | Arrêt des conteneurs confirmé |
| `cold_stage` | 0 ms | Reflink de l'image du dépôt |
| `cold_up` | 99 ms | Les conteneurs redémarrent |

Le redémarrage des conteneurs domine, et la préparation ne coûte pratiquement rien : le reflink n'apparaît même pas à la milliseconde près. Lisez tout de même ce zéro à côté des enregistrements de chaque dépôt, et non isolément. Une exécution qui a refusé tous les dépôts affiche elle aussi `cold_stage=0ms`, et seuls les enregistrements disent lequel des deux cas vous avez sous les yeux.

Ce détail est la preuve, pas de la décoration. Aucune de ces cinq phases ne lit ni n'envoie de données du dépôt, donc aucune ne grandit quand la sauvegarde grandit. La partie qui grandit, l'envoi, se déroule une fois le temps d'arrêt terminé.

renet affiche les mêmes chiffres à la fin d'une exécution, pour que vous mesuriez vos propres machines au lieu de nous croire sur parole :

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Chaque enregistrement JSON de dépôt porte le même temps d'arrêt et les mêmes phases, si bien qu'on distingue plus tard un instantané à froid d'un instantané à chaud sans le deviner d'après les durées.

### Quand choisir le froid

Le mode à chaud est celui par défaut, et c'est le bon choix pour la plupart des dépôts. Un instantané à chaud est cohérent en cas de crash, c'est-à-dire dans l'état où serait un dépôt après une coupure de courant, et il ne coûte aucun temps d'arrêt. La plupart des bases de données et des files d'attente s'en remettent toutes seules.

Choisissez le froid pour des données qu'on ne peut pas capturer sans risque pendant leur écriture. Une base de données avec son propre journal d'écriture anticipée et son état en mémoire est le cas typique. Vous échangez un court temps d'arrêt mesuré contre un instantané que l'application peut ouvrir sans devoir se réparer d'abord.

### Ce qu'une exécution à froid refuse

Le refus est la fonctionnalité. Une sauvegarde étiquetée à froid qui n'a rien mis au repos est un mensonge que vous ne découvririez qu'à la restauration : renet ne rétrograde donc jamais une exécution à froid en exécution à chaud.

- **Des conteneurs qui ne se sont pas arrêtés.** Après l'arrêt, renet demande au socket Docker du dépôt si quelque chose tourne encore. Si oui, ce dépôt est refusé au lieu d'être capturé. Le contrôle tranche du côté sûr : si le socket est injoignable ou la liste des conteneurs illisible, la mise au repos est considérée comme non vérifiée, et non vérifiée signifie refusée.
- **Une licence illisible.** Les licences sont vérifiées avant le temps d'arrêt et non après, car un dépôt dont la licence est illisible n'aurait de toute façon rien pu envoyer. Un tel dépôt est ignoré sans être arrêté. Si aucun des dépôts sélectionnés n'a de licence lisible, toute l'exécution est refusée avant qu'un seul conteneur ne s'arrête.
- **Une deuxième exécution à froid sur le même datastore.** Le verrou couvre le datastore entier, et un verrou déjà pris est refusé immédiatement, sans avoir rien arrêté. Deux exécutions qui se chevauchent arrêteraient chacune des conteneurs que l'autre croit lui appartenir, et la seconde redémarrerait des dépôts que la première est encore en train de figer. Sauter l'exécution et attendre la suivante vaut mieux que cela.

Si une exécution est interrompue alors que les conteneurs sont arrêtés, par un `systemctl stop` ou un redémarrage, renet les relance avant de quitter. La reprise sur la machine sert de filet : elle repère une sauvegarde à froid dont le propriétaire a disparu et remet ces dépôts en marche.

## Envoyer une sauvegarde vers une autre machine

Copiez un dépôt vers une seconde machine par SSH :

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` résout la destination depuis votre configuration, et `--to-machine <machine>` dit la même chose explicitement. Un nom de stockage est refusé : cette voie est retirée.

L'image chiffrée est copiée avec le MÊME GUID : il s'agit donc d'une sauvegarde ou d'une migration, pas d'un fork. Pour obtenir une copie indépendante, exécutez d'abord `rdc repo fork` puis envoyez le fork.

Le premier envoi transporte l'image entière. Chaque envoi suivant n'envoie que les blocs modifiés par rapport à une image de base immuable conservée sur les deux machines, sans aucun indicateur à définir. `--delta-base <guid>` nomme cette base vous-même si besoin.

La copie envoyée atterrit sur la cible comme un artefact de sauvegarde plutôt que comme un dépôt en cours d'exécution. Transformez-la en un dépôt avec `rdc backup restore` :

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Pour une sauvegarde à un instant donné, utilisez plutôt le stockage fragmenté : `rdc backup snapshot my-app` n'envoie que les cellules modifiées, et `rdc backup restore my-app --at <snapshot>` en récupère n'importe laquelle.

| Option | Description |
|--------|-------------|
| `<ref>` (positionnel) | Réf du dépôt à envoyer |
| `--to <remote>` | Machine ou cluster de destination |
| `--to-machine <machine>` | Machine de destination, indiquée explicitement |
| `--provision <provider>` | Provisionner la machine cible via ce fournisseur cloud si elle n'existe pas |
| `--checkpoint` | Créer un checkpoint CRIU avant l'envoi (pour les conteneurs avec le label `rediacc.checkpoint=true`). La cible se restaure automatiquement lors du `repo up` |
| `--force` | Écraser une sauvegarde existante |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert rsync (p. ex. `10M`, `500K`) |
| `--delta-base <guid>` | Ne transférer que les blocs modifiés par rapport à cette GUID de base immuable. Omettre pour une base automatique |
| `--strategy <strategy>` | Stratégie de delta de blocs lors de l'utilisation d'une base delta : `auto`, `physical` ou `shared` |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routes après l'opération |

## Récupérer une sauvegarde depuis une autre machine

Ramenez un dépôt depuis la machine qui le détient :

```bash
rdc repo pull my-app --from server-1
```

Ajoutez `--up` pour le monter et le déployer dans la même commande. Pour restaurer depuis le stockage fragmenté à la place, utilisez `rdc backup restore my-app --at <snapshot-id>`.

Pull refuse d'écraser un dépôt actuellement **monté**. Démontez-le d'abord, effectuez le pull, puis remontez-le avec `rdc repo up`. Les dépôts basés sur un répertoire font exception : ils se synchronisent sur place même montés.

| Option | Description |
|--------|-------------|
| `<ref>` (positionnel) | Réf du dépôt à récupérer |
| `--from <remote>` | Machine ou cluster source |
| `--from-machine <machine>` | Machine source, indiquée explicitement |
| `--force` | Écraser la sauvegarde locale existante |
| `--up` | Monter et déployer le dépôt après la récupération |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert rsync (p. ex. `10M`, `500K`) |
| `--delta-base <guid>` | Ne recevoir que les blocs modifiés par rapport à cette GUID de base immuable |
| `--strategy <strategy>` | Stratégie de delta de blocs lors de l'utilisation d'une base delta : `auto`, `physical` ou `shared` |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routes après l'opération |

## Lister les sauvegardes

Listez les instantanés dans le stockage fragmenté :

```bash
rdc backup manifests my-app
```

Chaque ligne est un point dans le temps stocké :

| Colonne | Signification |
|---|---|
| `Repo` | Nom du dépôt résolu depuis votre configuration locale (retombe sur le GUID pour les dépôts absents de la configuration) |
| `Snapshot` | L'id de l'instantané. C'est ce que prend `rdc backup restore --at` |
| `Created` | Heure UTC à laquelle l'instantané a été pris |
| `Total` | Taille de l'image du dépôt que cet instantané représente |
| `Added` | Octets que cet instantané a réellement envoyés en plus des précédents |
| `Chunks` | Combien de cellules il a ajoutées |

Pour voir ce qu'un `rdc repo push --to <machine>` a laissé sur la destination, demandez à cette machine ce qu'elle détient :

```bash
rdc repo list --machine server-1
```

La copie envoyée apparaît sous son propre nom. Une seconde ligne portant un GUID brut à côté est la base delta conservée, ce qui rend le prochain envoi vers cette machine incrémental plutôt qu'un transfert complet.

`rdc backup list --machine <machine>` lit les dossiers `hot/` et `cold/` dans lesquels écrivent les exécutions planifiées, ce qui en fait le mauvais outil pour une copie qu'un envoi y a placée, et il ne vous montrera rien.

| Colonne | Signification |
|---|---|
| `Mode` | `hot` ou `cold`. Dans quel dossier de sauvegarde planifiée cette entrée se trouve |
| `Name` | Nom du dépôt résolu depuis votre configuration locale (retombe sur le GUID pour les dépôts absents de la configuration) |
| `GUID` | Le GUID du dépôt sur disque |
| `Size` | Taille lisible de la sauvegarde |
| `Modified` | Horodatage UTC du fichier sur la machine |

Lister un backend de stockage est retiré avec la branche rclone ; la commande refuse et nomme ces deux remplacements.

## Rétention

Le serveur applique une politique de rétention par dépôt sur le stockage fragmenté, si bien que les anciens instantanés sont élagués sans que vous ayez à supprimer quoi que ce soit à la main. Sans politique déclarée, chaque instantané est conservé.

```bash
# Ce qui est actuellement appliqué.
rdc backup retention my-app

# Conserver une fenêtre glissante : 7 quotidiens, 4 hebdomadaires, 6 mensuels.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Revenir à tout conserver.
rdc backup retention clear my-app
```

| Option | Description |
|--------|-------------|
| `--keep-last <n>` | Conserver ce nombre d'instantanés les plus récents |
| `--keep-hourly <n>` | Conserver l'instantané le plus récent de chacune de ces heures |
| `--keep-daily <n>` | Conserver l'instantané le plus récent de chacun de ces jours |
| `--keep-weekly <n>` | Conserver l'instantané le plus récent de chacune de ces semaines |
| `--keep-monthly <n>` | Conserver l'instantané le plus récent de chacun de ces mois |
| `--keep-yearly <n>` | Conserver l'instantané le plus récent de chacune de ces années |

Donnez au moins une règle. `set` sans règles est refusé plutôt que traité comme « ne rien conserver », car vider une politique, c'est précisément à cela que sert `clear`.

## Restaurer

`rdc backup restore` transforme une sauvegarde en dépôt vivant, et c'est la même commande pour les deux voies. Ce qui diffère, c'est ce que vous lui indiquez.

```bash
# Un point dans le temps depuis le stockage fragmenté.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Un artefact laissé par un envoi sur une machine.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` prend un id d'instantané depuis `rdc backup manifests`, ou une heure RFC 3339 comme `2026-08-14T12:00:00Z`, qui se résout à l'instantané le plus récent pris à ce moment ou avant. Une heure sans instantané à ce moment ou avant est refusée plutôt qu'arrondie vers l'avant.

Restaurer sous un nouveau nom avec `--as` n'écrase rien, si bien qu'un exercice de restauration est sûr à exécuter sur une machine en direct. Restaurer sur un nom déjà existant est refusé.

| Option | Description |
|--------|-------------|
| `<artifact-ref>` (positionnel) | Ce qu'il faut restaurer. `repo` pour un instantané du stockage fragmenté, `repo@place` pour un artefact sur une machine |
| `--as <name>` | Nom pour le dépôt restauré (par défaut, le nom de l'artefact) |
| `-m, --machine <machine>` | Machine sur laquelle restaurer |
| `--datastore <name>` | Restaurer dans ce datastore nommé, dont la machine attachée l'héberge |
| `--at <time>` | Restaurer un point dans le temps : un id d'instantané ou une heure RFC 3339 |
| `--up` | Déployer le dépôt restauré après le transfert |
| `--health-window <seconds>` | Durée d'observation de la santé du dépôt déployé |
| `--health-timeout <seconds>` | Durée d'attente qu'il devienne sain |
| `-y, --yes` | Ignorer la confirmation |
| `--debug` | Activer la sortie détaillée |

Restaurer un dépôt nécessite son identifiant LUKS, qui vit dans votre configuration. Si vous avez activé le stockage de configuration, cet identifiant revient avec votre configuration sur une machine neuve. Sinon, gardez une copie de la configuration quelque part que la machine défaillante n'emportera pas avec elle.

### Prouvez la restauration sur chaque machine

Une machine qui n'a jamais bouclé le cycle complet n'est pas sauvegardée, aussi verts que paraissent ses envois. Les envois et les restaurations échouent pour des raisons différentes, et le second type ne se manifeste que lorsque vous l'essayez.

Faites-le une fois par machine, avant de compter sur les sauvegardes :

1. Prenez un instantané : `rdc backup snapshot my-app`.
2. Confirmez qu'il est enregistré : `rdc backup manifests my-app`.
3. Restaurez-le sous un nom jetable : `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Comparez le dépôt restauré à la source, puis supprimez la copie d'exercice avec `rdc repo delete my-app-drill --yes`.

Rien dans cette séquence ne touche le dépôt en direct, elle est donc sans danger sur une machine qui sert du trafic. Si vous quittez un ancien dispositif de sauvegarde, gardez-le en fonctionnement jusqu'à ce que cela ait réussi sur cette machine au moins une fois. Deux voies de sauvegarde coûtent du stockage ; une voie non prouvée coûte les données.

## Synchroniser un dépôt à la fois

Push et pull agissent sur un seul dépôt, identifié par sa réf (`name`, `name:tag` ou `name@machine`). Il n'existe pas de forme « tous les dépôts en une fois » : exécutez la commande une fois par dépôt.

Une réf nommant un fork et une machine fonctionne comme un nom simple :

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Les listes d'options complètes se trouvent sous [Envoyer une sauvegarde vers une autre machine](#push-a-backup-to-another-machine) et [Récupérer une sauvegarde depuis une autre machine](#pull-a-backup-from-another-machine).

## Sauvegardes planifiées

Rediacc utilise des stratégies de sauvegarde nommées. Chaque stratégie définit un calendrier, un mode de sauvegarde, une limite de bande passante optionnelle et des filtres de fichiers. Les machines référencent les stratégies par nom pour déterminer quelles sauvegardes s'exécutent sur elles.

### Modes de sauvegarde

| Mode | Comportement | Temps d'arrêt |
|------|-------------|---------------|
| `hot` | Image du dépôt gelée pendant que les services continuent de tourner (cohérent en cas de crash) | Aucun |
| `cold` | Services arrêtés, snapshot pris, services redémarrés, snapshot chargé (cohérent au niveau applicatif) | Fenêtre stop+start par dépôt, parallélisée entre les dépôts. Voir « Estimer le temps d'arrêt d'une sauvegarde froide » ci-dessous. |

Utilisez `hot` pour les services qui tolèrent les snapshots cohérents en cas de crash. Utilisez `cold` quand vous avez besoin d'une cohérence garantie et pouvez accepter un bref redémarrage.

### Sémantique de la sauvegarde froide

Une sauvegarde froide s'exécute en trois phases par dépôt inclus : **arrêt, snapshot, démarrage**. Comprendre où finissent les garanties permet de détecter rapidement les défaillances partielles.

**Ce que la sauvegarde froide garantit :**

- Avant le snapshot, chaque conteneur en cours d'exécution dans chaque dépôt inclus est arrêté gracieusement via le hook `down()` du Rediaccfile, et le Docker daemon par dépôt est mis en veille. Le snapshot est donc cohérent au niveau applicatif, et pas seulement cohérent en cas de crash.
- L'ensemble des IDs de conteneur qui étaient en cours d'exécution avant le snapshot est persisté dans un fichier sidecar à `/var/run/rediacc/cold-backup-<guid>.running.json`. C'est la source de vérité pour « ce qui doit être de nouveau actif une fois terminé ».
- Après le snapshot, le hook `up()` du Rediaccfile du dépôt est invoqué pour restaurer le stack compose complet.
- Un fichier sidecar de statut par exécution à `/var/run/rediacc/cold-backup-<guid>.status.json` enregistre la phase, le résultat et toute erreur de chaque tentative.

**Ce que la sauvegarde froide ne garantit PAS :**

- `up()` est au mieux-effort. Il peut échouer pour des raisons hors du contrôle de la sauvegarde froide (une condition `depends_on: service_healthy` encore en attente, une erreur de syntaxe dans le fichier compose, une défaillance réseau transitoire lors du pull d'une image). En cas d'échec, la sauvegarde froide journalise l'erreur au niveau erreur, écrit le sidecar de statut, et passe au dépôt suivant.
- Quand `up()` échoue, un **redémarrage direct de secours** se déclenche : le sidecar d'exécution est lu et chaque ID de conteneur enregistré est redémarré directement via l'API Docker (sans compose). Cela remet les services en marche même si le flux compose rencontre un problème, mais sans ré-exécuter les hooks Rediaccfile.
- Si même le secours échoue pour certains IDs de conteneur (par exemple, le Docker daemon lui-même est hors service), le sidecar est **laissé en place** pour que le watchdog du routeur puisse continuer à réessayer à chaque tick.

**Récupération par le watchdog :** à chaque tick, le watchdog vérifie la présence d'un sidecar d'exécution. Tout ID de conteneur listé là qui est actuellement arrêté est redémarré, *indépendamment de la `restart_policy` sauvegardée du conteneur*. Cela signifie que les services avec `restart: on-failure` (que Docker ne redémarrerait PAS après un arrêt propre) reviennent quand même après une sauvegarde froide. Une fois que tous les conteneurs listés sont en cours d'exécution, le sidecar est supprimé.

**Comment les opérateurs détectent les défaillances :**

- `rdc machine status <machine> --containers` affiche l'état d'exécution. Comparez avec l'ensemble attendu.
- `/var/run/rediacc/cold-backup-<guid>.status.json` sur la machine. Inspectez via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` avec un `startedAt` obsolète signifie que la dernière sauvegarde ne s'est pas terminée proprement.
- Les journaux du run de sauvegarde renet (`journalctl -u renet-*` ou l'invocation directe `rdc backup schedule`) émettent une ligne de résumé finale de la forme `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` non vide est la cible de grep.

### Estimer le temps d'arrêt d'une sauvegarde froide

Chaque dépôt n'est arrêté que pendant sa propre fenêtre `down()` + `up()`. Sur un hôte déjà en fonctionnement, ces durées sont typiquement :

| Profil du dépôt | Stop+start typique |
|-----------------|--------------------|
| Petit (1-2 conteneurs, sans DB) | 5-15 s |
| Moyen (application web + cache) | 20-45 s |
| Lourd (DB + files + mail) | 60-120 s |

L'étape de gel est un reflink copie-sur-écriture de l'image du dépôt. Elle ne touche que des métadonnées, si bien qu'elle prend le même temps que le dépôt pèse 1 GB ou 100 GB, et sur une exécution mesurée elle n'est même pas apparue à la milliseconde près. Un dépôt n'est pas maintenu arrêté pendant le gel des autres dépôts. L'envoi s'exécute ensuite contre la copie gelée, pendant que chaque dépôt est déjà redémarré.

**La durée totale d'exécution** est déterminée par le nombre de dépôts qui redémarrent en parallèle. Renet dérive cette valeur de l'hôte :

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Exemples :

| Hôte | Dépôts | Concurrence | Redémarrage wall-clock |
|------|--------|-------------|------------------------|
| VM 4 CPU | 5 dépôts, moyenne 30 s chacun | 2 | ~75 s |
| Serveur 16 CPU | 10 dépôts, moyenne 40 s chacun | 8 | ~80 s |
| Nœud de flotte 64 CPU | 50 dépôts, moyenne 40 s chacun | 8 | ~4 min |

**Surcharge via variable d'environnement :** définissez `REDIACC_COLD_BACKUP_CONCURRENCY=N` dans l'environnement du service de sauvegarde (généralement via un drop-in systemd) pour fixer une valeur précise. `=1` force des redémarrages strictement séquentiels, utile pour déboguer une boucle de crash dans le hook `up()` d'un dépôt.

Si vous exploitez un dépôt sensible à la latence (application web publique, mail), son temps d'arrêt est borné par son propre stop+start (typiquement 30-90 s), pas par la durée totale du run. Les dépôts sont planifiés dans les slots de concurrence selon leur ordre de découverte ; il n'existe pas de file de priorité. Donnez aux dépôts lourds leur propre stratégie délimitée par `--include` si vous avez besoin d'une planification plus fine.

### Sauvegardes longues et calendriers qui se chevauchent

Une sauvegarde froide qui dure plus longtemps que son propre intervalle de calendrier (par exemple, un premier seeding d'un dépôt de 500 Go sur un lien modeste peut légitimement nécessiter plus de 24 h, pendant lesquelles le minuteur nocturne se déclenche à nouveau) ne met en file d'attente ni ne lance une seconde exécution. L'unité systemd `Type=oneshot` est une instance unique : lorsque le minuteur se déclenche et que le service est déjà `activating`, systemd fusionne le démarrage dans la tâche existante. Aucun nouveau processus ne démarre, aucune exécution n'est mise en file d'attente pour plus tard.

Concrètement, une exécution qui démarre le lundi à 03:00 UTC et se termine le jeudi midi :

| Jour | Déclenchement à 03:00 UTC | Résultat |
|------|--------------------------|----------|
| Lundi | Premier déclenchement | L'exécution commence |
| Mardi | Deuxième déclenchement | Abandonné silencieusement (l'exécution précédente est toujours active) |
| Mercredi | Troisième déclenchement | Abandonné silencieusement (l'exécution précédente est toujours active) |
| Jeudi | L'exécution se termine à midi | Pas de rattrapage ; la prochaine exécution est le vendredi 03:00 UTC |

La directive `Persistent=true` du minuteur ne sauve **pas** ces déclenchements. `Persistent=true` rejoue les déclenchements qui ont été manqués parce que le minuteur lui-même était inactif (système éteint, minuteur désactivé). Les déclenchements abandonnés parce que le service était occupé sont perdus.

Ce comportement par défaut est délibéré. Exécuter deux sauvegardes froides en parallèle sur le même datastore entrerait en conflit sur le chemin de gel, l'envoi, et les sidecars par dépôt à `/var/run/rediacc/cold-backup-<guid>.status.json`. Attendre derrière une instance en cours d'exécution vaut mieux que de malmener les mêmes données depuis deux directions. Le verrou du datastore l'impose : une seconde exécution à froid trouve le verrou occupé et est refusée d'emblée, sans avoir rien arrêté.

**Implication pour la surveillance.** Une sauvegarde bloquée (par exemple, un envoi coincé sur un trou noir réseau) abandonne silencieusement chaque déclenchement de minuteur suivant. Le planificateur n'émet aucune alarme. Surveillez `systemctl show <unit> -p ActiveEnterTimestamp` : si le service est `activating` depuis plus longtemps que votre durée d'exécution attendue (par exemple, plus de 48 h sur un minuteur nocturne), investiguez.

**Si vous avez besoin que chaque déclenchement planifié s'exécute**, passez le minuteur de `OnCalendar=<cron>` à `OnUnitInactiveSec=<intervalle>`. Cela déclenche N heures après la fin de l'exécution précédente plutôt que sur un calendrier mural fixe, donc les exécutions longues ne causent pas d'abandons. Elles repoussent simplement l'exécution suivante. Le compromis est la dérive de calendrier : votre nocturne à 03:00 devient « 24 h après la fin du dernier ».

### Instantanés, interruptions et espace dans le pool

Chaque push fonctionne à partir d'un instantané momentané du datastore, de sorte que les données chargées sont cohérentes même pendant que les dépôts continuent d'écrire. Pendant l'exécution de la sauvegarde, cet instantané continue de référencer chaque bloc qu'il partage avec les dépôts actifs : les suppressions et les [trims](/fr/docs/repositories#reclaim-space-trim) libèrent moins d'espace dans le pool jusqu'à la fin du cycle et la suppression de l'instantané. Le [rapport de santé du stockage](/fr/docs/monitoring#storage-health) indique l'espace que les instantanés de sauvegarde immobilisent actuellement.

Les interruptions sont sans danger. Arrêter le service (ou redémarrer la machine) provoque l'abandon du transfert et la suppression de l'instantané avant la sortie ; l'exécution planifiée suivante reprend là où elle s'était arrêtée, car les cellules déjà stockées ne sont pas renvoyées. Si le processus est tué trop brutalement pour nettoyer (coupure de courant), l'instantané orphelin est détecté et supprimé automatiquement par le mainteneur de stockage en quelques minutes.

### Définir une stratégie

Le défaut canonique est un partage en deux stratégies : un flux hot horaire rapide qui capture chaque dépôt, et un flux cold hebdomadaire plus lent qui met les conteneurs au repos pour des snapshots cohérents au niveau applicatif. Les deux écrivent dans le même stockage fragmenté, et les blocs partagés sont stockés une seule fois plutôt que par flux.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` nomme la destination à l'intérieur de la stratégie ; c'est une étiquette que vous choisissez, et elle décrit le stockage fragmenté. `--include` liste les dépôts à sauvegarder, et le répéter en ajoute d'autres. Omettez-le et la stratégie couvre chaque dépôt du datastore. Les noms correspondent au nom de dépôt de la configuration locale (sans `:tag`).

`--exclude` est refusé pour une destination de stockage fragmenté plutôt que discrètement ignoré, parce que le `backup snapshot` sous-jacent sélectionne les dépôts en les nommant et n'a pas d'exclusion propre. Le respecter reviendrait à sauvegarder des dépôts que vous avez demandé de laisser de côté. Délimitez plutôt une stratégie avec `--include`, pour que ce que couvre une exécution planifiée soit écrit plutôt qu'inféré.

| Option | Description |
|--------|-------------|
| `<strategy>` (positionnel) | Nom de la stratégie (utilisé pour la liaison à la machine) |
| `--destination <name>` | Nom de destination à l'intérieur de la stratégie. Par défaut, le stockage fragmenté |
| `--storage <name>` | Opter pour le type de destination rclone retiré. Un calendrier qui l'utilise ne peut pas être déployé |
| `--cron <expression>` | Expression cron (p. ex. `"0 2 * * *"` pour tous les jours à 2h du matin) |
| `--mode <hot\|cold>` | Mode de sauvegarde |
| `--bwlimit <limit>` | Limite de bande passante pour les chargements (p. ex. `10M`) |
| `--include <repos>` | Dépôts couverts par cette stratégie (répétable) |
| `--exclude <repos>` | Dépôts à ignorer (répétable). Refusé sur une destination de stockage fragmenté |
| `--folder <path>` | Sous-dossier à l'intérieur d'un bucket rclone. Refusé sur une destination de stockage fragmenté |
| `--enable` / `--disable` | Activer ou désactiver la stratégie |

### Afficher les stratégies

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Supprimer une stratégie

```bash
rdc backup strategy remove weekly-cold
```

### Associer des stratégies à une machine

Une stratégie non associée à une machine n'est jamais déployée. Associez-en une ou plusieurs à une machine :

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

L'association est enregistrée dans votre configuration comme une liste sur la machine, ce que lit `rdc backup schedule` pour décider quelles unités déployer :

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **La liaison ne concerne que la configuration locale.** Définir une stratégie et la lier à une machine n'agit pas sur la machine. Exécutez `rdc backup schedule -m <machine>` (voir [Déployer le calendrier sur une machine](#deploy-schedule-to-machine)) pour déployer les minuteurs systemd, et relancez-le après tout changement de stratégie ou de liaison.

## Choisir entre hot et cold et filtrage par dépôt

### Hot vs cold en un coup d'œil

| | Hot | Cold |
|---|-----|------|
| **Cohérence** | Cohérent en cas de crash (image gelée pendant l'exécution) | Cohérent au niveau applicatif (arrêt, snapshot, démarrage) |
| **Temps d'arrêt** | Aucun | Fenêtre stop+start par dépôt (typiquement 5-120 s) |
| **Fréquence adaptée** | Élevée (p. ex. horaire) | Faible (p. ex. quotidienne ou hebdomadaire) |
| **Usage typique** | Filet de sécurité fréquent | Sauvegarde planifiée avec cohérence garantie |

**Hot** est le bon choix par défaut pour les exécutions à haute fréquence. Les services continuent de fonctionner pendant la prise du snapshot, de sorte qu'il n'y a pas de temps d'arrêt pour vos applications. Le snapshot est cohérent en cas de crash : il équivaut à ce que vous obtiendriez après un arrêt incorrect. Pour la plupart des bases de données modernes et des files de messages, c'est acceptable.

**Cold** est approprié quand vous avez besoin d'un snapshot applicatif garanti et que vous pouvez accepter un bref redémarrage par dépôt. Les services sont arrêtés avant le snapshot et redémarrés avant le début du chargement, de sorte qu'un chargement lent ou échoué ne prolonge jamais la fenêtre de temps d'arrêt. Consultez [Sémantique de la sauvegarde froide](#cold-backup-semantics) pour le modèle de garantie complet.

Les deux modes écrivent dans le même stockage fragmenté, et le mode concerne la façon dont le dépôt est traité pendant que l'image est gelée, pas l'endroit où atterrissent les données. Un dépôt couvert à la fois par un calendrier hot horaire et un calendrier cold hebdomadaire stocke les cellules qu'ils partagent une seule fois plutôt que deux.

### Délimiter les dépôts par stratégie

Une stratégie sans `--include` couvre chaque dépôt du datastore. Répéter `--include` la restreint aux dépôts que vous nommez, comparés au nom de dépôt de la configuration locale (sans `:tag`).

```bash
# Stratégie hot : sauvegarder tout toutes les heures
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Stratégie cold : hebdomadaire, et seulement les dépôts qui ont besoin d'être mis au repos
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Quand garder un dépôt hors de la stratégie hot fréquente

Nommez les dépôts que vous voulez dans l'exécution haute fréquence, plutôt que de la laisser tout prendre, quand :

- Un dépôt est volumineux et **entièrement régénérable** à partir des données sources déjà présentes sur le volume, de sorte que chaque sauvegarde horaire dépense de la bande passante sans apporter de valeur de récupération.
- L'exécution de sauvegarde dépasserait son propre intervalle de calendrier à votre vitesse de chargement disponible.

**Exemple.** Un dépôt `analytics-demo` contient environ 114 Go de tables Postgres dérivées pouvant être reconstruites à partir des fichiers CSV bruts stockés dans le même volume. Avec une limite de chargement à 6 Mo/s, un premier instantané de ce dépôt prend plus de 5 heures. En l'exécutant toutes les heures, chaque exécution est encore en cours quand la suivante se déclenche, si bien que chaque déclenchement suivant est abandonné silencieusement (voir [Sauvegardes longues et calendriers qui se chevauchent](#long-running-backups-and-overlapping-schedules)). Lister les autres dépôts dans `hourly-hot` et laisser `analytics-demo` à `weekly-cold` signifie qu'il est sauvegardé une fois par semaine plutôt que jamais.

> **Si les données sont purement régénérables**, envisagez si vous avez vraiment besoin de les sauvegarder. Une alternative est de ne sauvegarder que les entrées sources brutes (les dumps CSV dans cet exemple) et d'ignorer entièrement la copie dérivée. Une sauvegarde froide hebdomadaire des entrées sources est bien plus petite et entièrement suffisante pour la récupération.

Un dépôt que les deux stratégies couvrent obtient des instantanés horaires cohérents en cas de crash et un instantané hebdomadaire cohérent au niveau applicatif. `rdc backup manifests <repo>` les affiche ensemble, et les cellules qu'ils partagent ne sont stockées qu'une seule fois.

## Opérations de sauvegarde

### Déployer le calendrier sur une machine

Envoyez les stratégies associées vers une machine en tant que timers systemd :

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Le déploiement est un réconciliateur d'état. Il lit les fichiers d'unité actuels et l'état de systemd sur la machine, les compare à ce que la configuration produirait (SHA-256 par fichier) et ne touche que les unités dont le contenu a réellement changé. Relancer sans changement de configuration est un no-op : pas d'écritures, pas de `daemon-reload`, pas d'agitation des minuteurs.

`--dry-run` affiche le plan pour chaque stratégie (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sans toucher à la machine. Combinez avec `--debug` pour afficher également les corps d'unités générés, avec les identifiants masqués. Une unité de stockage fragmenté n'en porte de toute façon aucun : la machine s'authentifie avec sa propre licence de dépôt signée, et le serveur renvoie une autorisation de courte durée, si bien que rien de sensible n'est écrit dans le fichier d'unité.

Si une sauvegarde est en cours d'exécution pour une stratégie que vous êtes sur le point de mettre à jour ou de supprimer, le déploiement échoue rapidement avec une indication pour l'annuler ou passer `--force`. Avec `--force`, l'invocation en cours conserve son unité en mémoire et la nouvelle configuration s'applique au prochain tick du minuteur, de sorte que la sauvegarde en cours n'est jamais interrompue.

`--reset-failed` est opt-in. Lorsqu'il est passé, il efface l'état d'échec de systemd sur les services modifiés après un déploiement réussi. Désactivé par défaut pour que les signaux d'échec précédents restent visibles pour les alertes.

### Exécuter une sauvegarde maintenant

Déclenchez une sauvegarde immédiatement sans attendre le timer. Fonctionne même sans timers déployés, en utilisant `systemd-run` pour une exécution ad hoc :

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Voir le statut de la sauvegarde

Affiche le statut actuel des timers de sauvegarde et les résultats récents des tâches :

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Annuler une sauvegarde en cours

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Migration de dépôt

Déplacer un dépôt d'une machine à une autre :

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `<ref>` (positionnel) | Réf du dépôt à migrer ; son `@machine` indique la source |
| `--to <place>` | Machine ou cluster cible |
| `--provision <provider>` | Provisionner automatiquement la machine cible via ce fournisseur cloud (p. ex. `hetzner`, `linode`) |
| `--checkpoint` | Créer un checkpoint CRIU avant la migration, pour que la mémoire du processus se déplace aussi |
| `--delta-base <guid>` | GUID de base immuable pour le delta de bascule. Par défaut, la base de la première phase |
| `--strategy <strategy>` | Stratégie de delta de blocs pour la bascule : `auto`, `physical` ou `shared` |
| `--skip-dns` | Ignorer la mise à jour des enregistrements DNS après la migration |
| `--keep-source` | Conserver les images source après une migration réussie |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert (p. ex. `50M`) |

La migration transfère les données du dépôt chiffré via rsync en deux phases : un transfert en masse pendant que le dépôt continue de tourner, puis un bref arrêt pour le delta. La migration **déplace** le dépôt, si bien que les images source sont supprimées une fois le déplacement réussi. Passez `--keep-source` pour les conserver. C'est la différence entre `repo migrate` et `repo push` : push laisse la source en fonctionnement et intacte.

## Lire une archive écrite avant le retrait

`rdc storage` est ce qu'il reste de la branche rclone, et c'est en lecture seule. Il ne peut plus être une destination de sauvegarde, mais il peut toujours accéder à une archive qui y a été écrite.

```bash
# Enregistrer un remote que vous avez déjà configuré pour rclone.
rdc storage import rclone.conf
rdc storage list

# Regarder ce qu'il contient. Cela exécute le rclone de votre PATH.
rdc storage browse my-storage
```

`import` lit un fichier de configuration rclone et enregistre les remotes dans votre configuration ; les types pris en charge sont S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob et Swift.

**`browse` nécessite `rclone` sur votre PATH.** Il exécute le rclone installé sur la machine sur laquelle vous tapez ; il n'y a plus de copie embarquée. Sans cela, il vous le dit et ne fait rien d'autre.

Envoyer vers, récupérer depuis, lister et restaurer un backend de stockage sont retirés ; chacun refuse et nomme la commande qui le remplace.

## Bonnes pratiques

- Planifier des sauvegardes froides quotidiennes pour des copies cohérentes au niveau applicatif des données critiques
- Utiliser les sauvegardes chaudes pour des exécutions haute fréquence où aucune interruption n'est acceptable
- Tester les restaurations périodiquement. `rdc backup restore --as <new-name>` n'écrase rien, si bien qu'un exercice est sûr sur une machine en direct
- Définir une politique de rétention plutôt que d'élaguer à la main, pour que la fenêtre conservée soit écrite
- Garder une copie de machine à machine en plus des instantanés si vous voulez une copie sur du matériel que vous contrôlez
- Garder les identifiants en sécurité ; les sauvegardes sont chiffrées mais l'identifiant LUKS est nécessaire pour la restauration
