---
title: "Sauvegarde et restauration"
description: "Sauvegardez des dépôts chiffrés de deux façons : un stockage fragmenté adressé par contenu qui n'envoie que les cellules modifiées, ou un push complet vers n'importe quel stockage compatible rclone. Restaurez sur n'importe quelle machine et automatisez avec des stratégies nommées et des timers systemd."
category: "Guides"
order: 7
language: fr
sourceHash: "c02ab3e78c40fa92"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Sauvegarde et restauration

Rediacc sauvegarde des dépôts chiffrés vers un stockage externe et les restaure sur la même machine ou sur une machine différente. Les sauvegardes sont chiffrées ; l'identifiant LUKS du dépôt est nécessaire pour la restauration.

## Deux voies de sauvegarde

Rediacc propose deux voies de sauvegarde indépendantes, et ce guide couvre les deux. Elles utilisent un stockage et des commandes différents, si bien qu'un dépôt sauvegardé par l'une n'est pas sauvegardé par l'autre.

**Le stockage fragmenté** (`rdc backup snapshot`) envoie l'image du dépôt sous forme de cellules de taille fixe adressées par leur contenu. La première exécution envoie tout l'inventaire non nul ; chaque exécution suivante n'envoie que les cellules modifiées, déterminées à partir des métadonnées d'allocation du système de fichiers plutôt qu'en relisant l'image entière. Les cellules identiques ne sont stockées qu'une seule fois, entre les instantanés et sur toute une famille de forks, et l'usage est mesuré par rapport à votre quota de stockage (`rdc backup usage`).

**Le push de stockage** (`rdc repo push`) copie un fichier de sauvegarde complet vers un fournisseur compatible rclone que vous enregistrez vous-même. Il est retiré au profit du stockage fragmenté, et les stratégies planifiées ne l'utilisent plus. Les sections ci-dessous qui le décrivent fonctionnent toujours aujourd'hui, mais traitez-les comme la voie héritée.

La restauration depuis le stockage fragmenté fonctionne : `rdc backup restore <repo> --at <snapshot-id>` matérialise un instantané stocké, et `--at` accepte également un horodatage RFC 3339, qui est résolu par rapport à l'inventaire des instantanés. Ajoutez `--as <name>` pour restaurer sous un nom différent et `--up` pour déployer le dépôt par la suite. Le stockage fragmenté vous offre également l'envoi (`rdc backup snapshot`), la vérification (`rdc backup verify`, avec `--deep` pour recalculer le hash de chaque cellule plutôt qu'un échantillon), l'inventaire des instantanés (`rdc backup manifests`) et la comptabilité des quotas (`rdc backup usage`).

### Commandes de stockage fragmenté

```bash
# Envoyer un instantané. La première exécution amorce, les suivantes n'envoient que les cellules modifiées.
rdc backup snapshot my-app

# Planifier sans envoyer : indique ce qui serait déplacé.
rdc backup snapshot my-app --dry-run

# Ne pas faire confiance à l'ancre locale et renvoyer tout l'inventaire.
# Ceci renvoie tout et recharge le quota ; à n'utiliser que lorsque
# l'ancre est connue pour être défaillante.
rdc backup snapshot my-app --reseed

# Vérifier l'inventaire stocké et votre quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

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

## Configurer le stockage

Avant d'envoyer des sauvegardes, enregistrez un fournisseur de stockage. Rediacc prend en charge tout stockage compatible rclone : S3, B2, Google Drive et bien d'autres.

### Importer depuis rclone

Si vous avez déjà un remote rclone configuré :

```bash
rdc storage import rclone.conf
```

Ceci importe des configurations de stockage depuis un fichier de configuration rclone dans la configuration actuelle. Types pris en charge : S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob et Swift.

### Afficher les stockages

```bash
rdc storage list
```

## Envoyer une sauvegarde

Envoyez une sauvegarde de dépôt vers un stockage externe :

```bash
rdc repo push my-app --to my-storage
```

La sauvegarde atterrit dans le dossier `hot/` du stockage quand le dépôt est monté au moment du push, et dans `cold/` quand il est démonté. C'est la même disposition qu'utilisent les sauvegardes planifiées, de sorte que `rdc backup list` affiche toutes les sauvegardes dans un seul tableau.

| Option | Description |
|--------|-------------|
| `--to <storage>` | Emplacement de stockage cible |
| `--to-machine <machine>` | Machine cible pour la sauvegarde de machine à machine |
| `--dest <filename>` | Nom de fichier de destination personnalisé |
| `--checkpoint` | Créer un checkpoint CRIU avant l'envoi (pour les conteneurs avec le label `rediacc.checkpoint=true`). La cible se restaure automatiquement lors du `repo up` |
| `--force` | Écraser une sauvegarde existante |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert rsync (p. ex. `10M`, `500K`) |
| `--tag <tag>` | Étiqueter la sauvegarde |
| `-w, --watch` | Suivre la progression de l'opération |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routes après l'opération |

## Récupérer / Restaurer une sauvegarde

Récupérez une sauvegarde de dépôt depuis un stockage externe :

```bash
rdc repo pull my-app --from my-storage
```

Pull refuse d'écraser un dépôt actuellement **monté**. Démontez-le d'abord, effectuez le pull, puis remontez-le avec `rdc repo up`. Les dépôts basés sur un répertoire font exception : ils se synchronisent sur place même montés.

| Option | Description |
|--------|-------------|
| `--from <storage>` | Emplacement de stockage source |
| `--from-machine <machine>` | Machine source pour la restauration de machine à machine |
| `--force` | Écraser la sauvegarde locale existante |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert rsync (p. ex. `10M`, `500K`) |
| `-w, --watch` | Suivre la progression de l'opération |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routes après l'opération |

## Lister les sauvegardes

Affichez les sauvegardes disponibles dans un emplacement de stockage :

```bash
rdc backup list --storage my-storage
```

La sortie est un tableau unifié qui fusionne les deux [dossiers de sauvegardes planifiées](#sauvegardes-planifiées) (`hot/` et `cold/`) afin que vous voyiez toutes les sauvegardes en une seule vue :

| Colonne | Signification |
|---|---|
| `Mode` | `hot` ou `cold`. Dans quel dossier de sauvegarde planifiée cette entrée se trouve |
| `Name` | Nom du dépôt résolu depuis votre configuration locale (retombe sur le GUID pour les dépôts absents de la configuration) |
| `GUID` | Le GUID du dépôt sur disque |
| `Size` | Taille lisible de la sauvegarde |
| `Modified` | Horodatage UTC du backend de stockage |

Pour zoomer sur un seul mode, passez `--path` :

```bash
rdc backup list --storage my-storage --path hot
rdc backup list --storage my-storage --path cold
```

### Disposition du stockage

Les sauvegardes planifiées atterrissent dans des sous-dossiers par mode à l'intérieur du dossier configuré du stockage, de sorte que le même stockage héberge proprement les flux horaires et hebdomadaires sans les mélanger :

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Un dépôt peut apparaître dans `hot/` et dans `cold/` (la planification horaire le capture ; la planification hebdomadaire le capture également). Le listing fusionné affiche les deux lignes pour qu'il soit clair quels flux couvrent quels dépôts.

## Synchroniser un dépôt à la fois

Push et pull agissent sur un seul dépôt, identifié par sa réf (`name`, `name:tag` ou `name@machine`). Il n'existe pas de forme « tous les dépôts en une fois » : exécutez la commande une fois par dépôt.

### Envoyer vers le stockage

```bash
rdc repo push shop@server-1 --to my-storage
```

### Récupérer depuis le stockage

```bash
rdc repo pull shop@server-1 --from my-storage
```

| Option | Description |
|--------|-------------|
| `--to <remote>` | Stockage ou machine de destination (envoi) |
| `--to-machine <machine>` | Machine de destination pour l'envoi de machine à machine |
| `--from <remote>` | Stockage ou machine source (récupération) |
| `--from-machine <machine>` | Machine source pour la récupération de machine à machine |
| `--force` | Écraser une sauvegarde ou un dépôt existant |
| `--checkpoint` | Créer un checkpoint CRIU avant l'envoi (envoi uniquement) |
| `--up` | Monter et déployer le dépôt après la récupération (récupération uniquement) |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert rsync (p. ex. `10M`) |
| `--delta-base <guid>` | Ne transférer que les blocs modifiés par rapport à une GUID de base immuable |
| `--debug` | Activer la sortie détaillée |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routes après l'opération |

## Sauvegardes planifiées

Rediacc utilise des stratégies de sauvegarde nommées. Chaque stratégie définit un calendrier, un mode de sauvegarde, une limite de bande passante optionnelle et des filtres de fichiers. Les machines référencent les stratégies par nom pour déterminer quelles sauvegardes s'exécutent sur elles.

### Modes de sauvegarde

| Mode | Comportement | Temps d'arrêt |
|------|-------------|---------------|
| `hot` | Snapshot BTRFS pris pendant que les services sont en cours d'exécution (cohérent en cas de crash) | Aucun |
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

L'étape de snapshot (`btrfs subvolume snapshot -r`) est O(1) quelle que soit la taille du dépôt : 0,1-1 s. Un dépôt n'est pas maintenu arrêté pendant les snapshots des autres dépôts. L'uploader s'exécute ensuite contre un snapshot en lecture seule, pendant que tous les dépôts sont déjà redémarrés.

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

Si vous exploitez un dépôt sensible à la latence (application web publique, mail), son temps d'arrêt est borné par son propre stop+start (typiquement 30-90 s), pas par la durée totale du run. Les dépôts sont planifiés dans les slots de concurrence selon leur ordre de découverte ; il n'existe pas de file de priorité. Séparez les dépôts lourds dans leurs propres stratégies délimitées par `--exclude` si vous avez besoin d'une planification plus fine.

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

Ce comportement par défaut est délibéré. Exécuter deux sauvegardes froides en parallèle sur le même datastore entrerait en conflit sur le chemin du snapshot BTRFS, le remote rclone et les sidecars par dépôt à `/var/run/rediacc/cold-backup-<guid>.status.json`. Attendre derrière une instance en cours d'exécution est plus sûr que de maltraiter les mêmes données de deux directions.

**Implication pour la surveillance.** Une sauvegarde bloquée (par exemple, rclone coincé sur un trou noir réseau) abandonne silencieusement chaque déclenchement de minuteur suivant. Le planificateur n'émet aucune alarme. Surveillez `systemctl show <unit> -p ActiveEnterTimestamp` : si le service est `activating` depuis plus longtemps que votre durée d'exécution attendue (par exemple, plus de 48 h sur un minuteur nocturne), investiguez.

**Si vous avez besoin que chaque déclenchement planifié s'exécute**, passez le minuteur de `OnCalendar=<cron>` à `OnUnitInactiveSec=<intervalle>`. Cela déclenche N heures après la fin de l'exécution précédente plutôt que sur un calendrier mural fixe, donc les exécutions longues ne causent pas d'abandons. Elles repoussent simplement l'exécution suivante. Le compromis est la dérive de calendrier : votre nocturne à 03:00 devient « 24 h après la fin du dernier ».

### Snapshots, interruptions et espace dans le pool

Chaque push fonctionne à partir d'un snapshot momentané du datastore, de sorte que les données chargées sont cohérentes même pendant que les dépôts continuent d'écrire. Pendant l'exécution de la sauvegarde, ce snapshot continue de référencer chaque bloc qu'il partage avec les dépôts actifs : les suppressions et les [trims](/fr/docs/repositories#récupérer-de-lespace-trim) libèrent moins d'espace dans le pool jusqu'à la fin du cycle et la suppression du snapshot. Le [rapport de santé du stockage](/fr/docs/monitoring#santé-du-stockage) indique l'espace que les snapshots de sauvegarde immobilisent actuellement.

Les interruptions sont sans danger. Arrêter le service (ou redémarrer la machine) provoque l'abandon du transfert et la suppression du snapshot avant la sortie ; l'exécution planifiée suivante reprend là où elle s'était arrêtée, car les fichiers inchangés sont ignorés par somme de contrôle. Si le processus est tué trop brutalement pour nettoyer (coupure de courant), le snapshot orphelin est détecté et supprimé automatiquement par le mainteneur de stockage en quelques minutes.

### Définir une stratégie

Le défaut canonique est un partage en deux stratégies : un flux hot horaire rapide qui capture chaque dépôt, et un flux cold hebdomadaire plus lent qui prend des snapshots cohérents au niveau applicatif. Les deux stratégies écrivent dans des sous-dossiers de stockage différents (`hot/` et `cold/`) afin que les sauvegardes ne se mélangent jamais.

```bash
rdc backup strategy set hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Le filtre `--exclude` sur la stratégie cold est l'échappatoire recommandée pour les dépôts très volumineux qui n'entrent pas dans votre fenêtre de maintenance hebdomadaire. La stratégie hot horaire les couvre toujours ; cold les ignore simplement. Les noms de dépôt dans `--exclude` correspondent au nom de dépôt de la configuration locale (sans `:tag`).

| Option | Description |
|--------|-------------|
| `<strategy>` (positionnel) | Nom de la stratégie (utilisé pour la liaison à la machine) |
| `--destination <storage>` | Fournisseur de stockage vers lequel charger |
| `--cron <expression>` | Expression cron (p. ex. `"0 2 * * *"` pour tous les jours à 2h du matin) |
| `--mode <hot\|cold>` | Mode de sauvegarde |
| `--bwlimit <limit>` | Limite de bande passante pour les chargements (p. ex. `10M`) |
| `--include <pattern>` | Filtre d'inclusion (répétable) |
| `--exclude <pattern>` | Filtre d'exclusion (répétable) |
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

Dans votre configuration, associez un ou plusieurs noms de stratégie à une machine :

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **La liaison ne concerne que la configuration locale.** Définir une stratégie et la lier à une machine n'agit pas sur la machine. Exécutez `rdc backup schedule -m <machine>` (voir [Déployer le calendrier sur une machine](#déployer-le-calendrier-sur-une-machine)) pour déployer les minuteurs systemd, et relancez-le après tout changement de stratégie ou de liaison.

## Choisir entre hot et cold et filtrage par dépôt

### Hot vs cold en un coup d'œil

| | Hot | Cold |
|---|-----|------|
| **Cohérence** | Cohérent en cas de crash (snapshot BTRFS pendant l'exécution) | Cohérent au niveau applicatif (arrêt, snapshot, démarrage) |
| **Temps d'arrêt** | Aucun | Fenêtre stop+start par dépôt (typiquement 5-120 s) |
| **Fréquence adaptée** | Élevée (p. ex. horaire) | Faible (p. ex. quotidienne ou hebdomadaire) |
| **Usage typique** | Filet de sécurité fréquent | Sauvegarde planifiée avec cohérence garantie |

**Hot** est le bon choix par défaut pour les exécutions à haute fréquence. Les services continuent de fonctionner pendant la prise du snapshot, de sorte qu'il n'y a pas de temps d'arrêt pour vos applications. Le snapshot est cohérent en cas de crash : il équivaut à ce que vous obtiendriez après un arrêt incorrect. Pour la plupart des bases de données modernes et des files de messages, c'est acceptable.

**Cold** est approprié quand vous avez besoin d'un snapshot applicatif garanti et que vous pouvez accepter un bref redémarrage par dépôt. Les services sont arrêtés avant le snapshot et redémarrés avant le début du chargement, de sorte qu'un chargement lent ou échoué ne prolonge jamais la fenêtre de temps d'arrêt. Consultez [Sémantique de la sauvegarde froide](#sémantique-de-la-sauvegarde-froide) pour le modèle de garantie complet.

### Filtrer les dépôts par stratégie

Chaque stratégie peut porter des filtres `--include` et `--exclude`. Les noms de dépôts correspondant à un motif `--exclude` sont ignorés pour cette stratégie ; `--include` restreint l'exécution aux seuls noms correspondants. Les filtres correspondent au nom de dépôt de la configuration locale (sans `:tag`).

```bash
# Stratégie hot : sauvegarder tout toutes les heures
rdc backup strategy set hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Stratégie cold : sauvegarder tout chaque semaine, sauf le grand jeu de données dérivé
rdc backup strategy set weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Quand exclure un dépôt de la stratégie hot haute fréquence

Excluez un dépôt de l'exécution haute fréquence quand :

- Le dépôt est volumineux et **entièrement régénérable** à partir des données sources déjà présentes sur le volume, de sorte que chaque sauvegarde horaire gaspille une bande passante significative sans apporter de valeur de récupération concrète.
- L'exécution de sauvegarde dépasserait son propre intervalle de calendrier à votre vitesse de chargement disponible.

**Exemple.** Un dépôt `analytics-demo` contient environ 114 Go de tables Postgres dérivées pouvant être entièrement reconstruites à partir des fichiers CSV bruts déjà stockés dans le même volume. Avec une limite de chargement à 6 Mo/s, une seule sauvegarde hot de ce dépôt prend plus de 5 heures. En l'exécutant toutes les heures, chaque exécution est encore en cours quand la suivante se déclenche, ce qui provoque l'abandon silencieux de chaque exécution suivante (voir [Sauvegardes longues et calendriers qui se chevauchent](#sauvegardes-longues-et-calendriers-qui-se-chevauchent)). L'exclure de `hourly-hot` et le conserver dans `weekly-cold` signifie qu'il est sauvegardé une fois par semaine plutôt que jamais.

> **Si les données sont purement régénérables**, envisagez si vous avez vraiment besoin de les sauvegarder. Une alternative est de ne sauvegarder que les entrées sources brutes (les dumps CSV dans cet exemple) et d'ignorer entièrement la copie dérivée. Une sauvegarde froide hebdomadaire des entrées sources est bien plus petite et entièrement suffisante pour la récupération.

Les dépôts non exclus d'aucune des deux stratégies apparaissent dans les sous-dossiers `hot/` et `cold/` du stockage. La sortie fusionnée de `rdc backup list` affiche les deux lignes pour vérifier quels flux couvrent quels dépôts.

## Opérations de sauvegarde

### Déployer le calendrier sur une machine

Envoyez les stratégies associées vers une machine en tant que timers systemd :

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Le déploiement est un réconciliateur d'état. Il lit les fichiers d'unité actuels et l'état de systemd sur la machine, les compare à ce que la configuration produirait (SHA-256 par fichier) et ne touche que les unités dont le contenu a réellement changé. Relancer sans changement de configuration est un no-op : pas d'écritures, pas de `daemon-reload`, pas d'agitation des minuteurs.

`--dry-run` affiche le plan pour chaque stratégie (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sans toucher à la machine. Combinez avec `--debug` pour afficher également les corps d'unités générés ; les tokens rclone sont masqués.

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
| `--provision` | Provisionner le dépôt sur la destination avant le transfert |
| `--checkpoint` | Créer un checkpoint CRIU avant la migration |
| `--skip-dns` | Ignorer la mise à jour des enregistrements DNS après la migration |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert (p. ex. `50M`) |

La migration transfère les données du dépôt chiffré via rsync. Le dépôt source reste intact jusqu'à ce que vous le supprimiez explicitement.

## Parcourir le stockage

Parcourez le contenu d'un emplacement de stockage :

```bash
rdc storage browse my-storage
```

## Bonnes pratiques

- Planifier des sauvegardes froides quotidiennes pour des snapshots cohérents au niveau applicatif des données critiques
- Utiliser les sauvegardes chaudes pour des snapshots haute fréquence où aucune interruption n'est acceptable
- Tester les restaurations périodiquement pour vérifier l'intégrité des sauvegardes
- Utiliser plusieurs fournisseurs de stockage pour les données critiques (p. ex. S3 + B2)
- Garder les identifiants en sécurité ; les sauvegardes sont chiffrées mais l'identifiant LUKS est nécessaire pour la restauration
