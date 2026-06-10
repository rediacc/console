---
title: "Sauvegarde et restauration"
description: "Sauvegardez des dépôts chiffrés vers n'importe quel stockage compatible rclone, restaurez-les sur n'importe quelle machine, et automatisez avec des stratégies de sauvegarde nommées et des timers systemd."
category: Guides
order: 7
language: fr
sourceHash: "e241aa122868e629"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Sauvegarde et restauration

Rediacc sauvegarde des dépôts chiffrés vers un stockage externe et les restaure sur la même machine ou sur une machine différente. Les sauvegardes sont chiffrées ; l'identifiant LUKS du dépôt est nécessaire pour la restauration.

## Configurer le stockage

Avant d'envoyer des sauvegardes, enregistrez un fournisseur de stockage. Rediacc prend en charge tout stockage compatible rclone : S3, B2, Google Drive et bien d'autres.

### Importer depuis rclone

Si vous avez déjà un remote rclone configuré :

```bash
rdc config storage import --file rclone.conf
```

Ceci importe des configurations de stockage depuis un fichier de configuration rclone dans la configuration actuelle. Types pris en charge : S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob et Swift.

### Afficher les stockages

```bash
rdc config storage list
```

## Envoyer une sauvegarde

Envoyez une sauvegarde de dépôt vers un stockage externe :

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

Push vérifie toujours que le dépôt cible est monté avant d'écrire. S'il ne l'est pas, l'opération est annulée.

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
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull vérifie toujours que le dépôt cible est monté avant d'écrire. S'il ne l'est pas, l'opération est annulée.

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
rdc repo backup list --from my-storage -m server-1
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
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
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

Un dépôt peut apparaître dans `hot/` et dans `cold/` (la planification horaire le capture ; la planification hebdomadaire le capture également). Le listing fusionné fait remonter les deux lignes pour qu'il soit clair quels flux couvrent quels dépôts.

## Synchronisation en masse

Envoyez ou récupérez tous les dépôts en une seule fois :

### Envoyer tout vers le stockage

```bash
rdc repo push --to my-storage -m server-1
```

### Récupérer tout depuis le stockage

```bash
rdc repo pull --from my-storage -m server-1
```

| Option | Description |
|--------|-------------|
| `--to <storage>` | Stockage cible (direction envoi) |
| `--from <storage>` | Stockage source (direction récupération) |
| `--repo <name>` | Synchroniser des dépôts spécifiques (répétable) |
| `--override` | Écraser les sauvegardes existantes |
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

Une sauvegarde froide s'exécute en trois phases par dépôt inclus : **arrêt -- snapshot -- démarrage**. Comprendre les limites des garanties aide les opérateurs à détecter les défaillances partielles rapidement.

**Ce que la sauvegarde froide garantit :**

- Avant le snapshot, chaque conteneur en cours d'exécution dans chaque dépôt inclus est arrêté gracieusement via le hook `down()` du Rediaccfile, et le Docker daemon par dépôt est mis en veille. Le snapshot est donc cohérent au niveau applicatif, et pas seulement cohérent en cas de crash.
- L'ensemble des IDs de conteneur qui étaient en cours d'exécution avant le snapshot est persisté dans un fichier sidecar à `/var/run/rediacc/cold-backup-<guid>.running.json`. C'est la source de vérité pour "ce qui doit être de nouveau actif une fois terminé."
- Après le snapshot, le hook `up()` du Rediaccfile du dépôt est invoqué pour restaurer le stack compose complet.
- Un fichier sidecar de statut par exécution à `/var/run/rediacc/cold-backup-<guid>.status.json` enregistre la phase, le résultat et toute erreur de chaque tentative.

**Ce que la sauvegarde froide ne garantit PAS :**

- `up()` est au mieux-effort. Il peut échouer pour des raisons hors du contrôle de la sauvegarde froide (une condition `depends_on: service_healthy` encore en attente, une erreur de syntaxe dans le fichier compose, une défaillance réseau transitoire lors du pull d'une image). En cas d'échec, la sauvegarde froide journalise l'erreur au niveau erreur, écrit le sidecar de statut, et passe au dépôt suivant.
- Quand `up()` échoue, un **redémarrage direct de secours** se déclenche : le sidecar d'exécution est lu et chaque ID de conteneur enregistré est redémarré directement via l'API Docker (sans compose). Cela remet les services en marche même si le flux compose rencontre un problème, mais sans ré-exécuter les hooks Rediaccfile.
- Si même le secours échoue pour certains IDs de conteneur (par exemple, le Docker daemon lui-même est hors service), le sidecar est **laissé en place** pour que le watchdog du routeur puisse continuer à réessayer à chaque tick.

**Récupération par le watchdog :** à chaque tick, le watchdog vérifie la présence d'un sidecar d'exécution. Tout ID de conteneur listé là qui est actuellement arrêté est redémarré, *indépendamment de la `restart_policy` sauvegardée du conteneur*. Cela signifie que les services avec `restart: on-failure` (que Docker ne redémarrerait PAS après un arrêt propre) reviennent quand même après une sauvegarde froide. Une fois que tous les conteneurs listés sont en cours d'exécution, le sidecar est supprimé.

**Comment les opérateurs détectent les défaillances :**

- `rdc machine query --name <machine> --containers` affiche l'état d'exécution. Comparez avec l'ensemble attendu.
- `/var/run/rediacc/cold-backup-<guid>.status.json` sur la machine. Inspectez via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` avec un `startedAt` obsolète signifie que la dernière sauvegarde ne s'est pas terminée proprement.
- Les journaux du run de sauvegarde renet (`journalctl -u renet-*` ou l'invocation directe `rdc machine backup schedule`) émettent une ligne de résumé finale de la forme `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` non vide est la cible de grep.

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

Ce comportement par défaut est délibéré. Exécuter deux sauvegardes froides en parallèle sur le même datastore entrerait en conflit sur le chemin du snapshot BTRFS, le remote rclone et les sidecars par dépôt à `/var/run/rediacc/cold-backup-<guid>.status.json`. La sérialisation derrière une instance de longue durée est le résultat sûr.

**Implication pour la surveillance.** Une sauvegarde bloquée (par exemple, rclone coincé sur un trou noir réseau) abandonne silencieusement chaque déclenchement de minuteur suivant. Le planificateur n'émet aucune alarme. Surveillez `systemctl show <unit> -p ActiveEnterTimestamp` : si le service est `activating` depuis plus longtemps que votre durée d'exécution attendue (par exemple, plus de 48 h sur un minuteur nocturne), investiguez.

**Si vous avez besoin que chaque déclenchement planifié s'exécute**, passez le minuteur de `OnCalendar=<cron>` à `OnUnitInactiveSec=<intervalle>`. Cela déclenche N heures après la fin de l'exécution précédente plutôt que sur un calendrier mural fixe, donc les exécutions longues ne causent pas d'abandons. Elles repoussent simplement l'exécution suivante. Le compromis est la dérive de calendrier : votre nocturne à 03:00 devient « 24 h après la fin du dernier ».

### Snapshots, interruptions et espace dans le pool

Chaque push fonctionne à partir d'un snapshot momentané du datastore, de sorte que les données chargées sont cohérentes même pendant que les dépôts continuent d'écrire. Pendant l'exécution de la sauvegarde, ce snapshot continue de référencer chaque bloc qu'il partage avec les dépôts actifs : les suppressions et les [trims](/fr/docs/repositories#récupérer-de-lespace-trim) libèrent moins d'espace dans le pool jusqu'à la fin du cycle et la suppression du snapshot. Le [rapport de santé du stockage](/fr/docs/monitoring#santé-du-stockage) indique l'espace que les snapshots de sauvegarde immobilisent actuellement.

Les interruptions sont sans danger. Arrêter le service (ou redémarrer la machine) provoque l'abandon du transfert et la suppression du snapshot avant la sortie ; l'exécution planifiée suivante reprend là où elle s'était arrêtée, car les fichiers inchangés sont ignorés par somme de contrôle. Si le processus est tué trop brutalement pour nettoyer (coupure de courant), le snapshot orphelin est détecté et supprimé automatiquement par le mainteneur de stockage en quelques minutes.

### Définir une stratégie

Le défaut canonique est un partage en deux stratégies : un flux hot horaire rapide qui capture chaque dépôt, et un flux cold hebdomadaire plus lent qui prend des snapshots cohérents au niveau applicatif. Les deux stratégies écrivent dans des sous-dossiers de stockage différents (`hot/` et `cold/`) afin que les sauvegardes ne se mélangent jamais.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Le filtre `--exclude` sur la stratégie cold est l'échappatoire recommandée pour les dépôts très volumineux qui n'entrent pas dans votre fenêtre de maintenance hebdomadaire. La stratégie hot horaire les couvre toujours ; cold les ignore simplement. Les noms de dépôt dans `--exclude` correspondent au nom de dépôt de la configuration locale (sans `:tag`).

| Option | Description |
|--------|-------------|
| `--name <name>` | Nom de la stratégie (utilisé pour la liaison avec la machine) |
| `--destination <storage>` | Fournisseur de stockage vers lequel charger |
| `--cron <expression>` | Expression cron (p. ex. `"0 2 * * *"` pour tous les jours à 2h du matin) |
| `--mode <hot\|cold>` | Mode de sauvegarde |
| `--bwlimit <limit>` | Limite de bande passante pour les chargements (p. ex. `10M`) |
| `--include <pattern>` | Filtre d'inclusion (répétable) |
| `--exclude <pattern>` | Filtre d'exclusion (répétable) |
| `--enable` / `--disable` | Activer ou désactiver la stratégie |

### Afficher les stratégies

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Supprimer une stratégie

```bash
rdc config backup-strategy remove --name weekly-cold
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

> **La liaison ne concerne que la configuration locale.** Définir une stratégie et la lier à une machine n'agit pas sur la machine. Exécutez `rdc machine backup schedule -m <machine>` (voir [Déployer le calendrier sur une machine](#déployer-le-calendrier-sur-une-machine)) pour déployer les minuteurs systemd, et relancez-le après tout changement de stratégie ou de liaison.

## Choisir entre hot et cold et filtrage par dépôt

### Hot vs cold en un coup d'œil

| | Hot | Cold |
|---|-----|------|
| **Cohérence** | Cohérent en cas de crash (snapshot BTRFS pendant l'exécution) | Cohérent au niveau applicatif (arrêt → snapshot → démarrage) |
| **Temps d'arrêt** | Aucun | Fenêtre stop+start par dépôt (typiquement 5-120 s) |
| **Fréquence adaptée** | Élevée (p. ex. horaire) | Faible (p. ex. quotidienne ou hebdomadaire) |
| **Usage typique** | Filet de sécurité fréquent | Sauvegarde planifiée avec cohérence garantie |

**Hot** est le bon choix par défaut pour les exécutions à haute fréquence. Les services continuent de fonctionner pendant la prise du snapshot, la fenêtre de sauvegarde n'interrompt donc pas les utilisateurs. Le snapshot est cohérent en cas de crash : il équivaut à ce que vous obtiendriez après un arrêt incorrect. Pour la plupart des bases de données modernes et des files de messages, c'est acceptable.

**Cold** est approprié quand vous avez besoin d'un snapshot applicatif garanti et que vous pouvez accepter un bref redémarrage par dépôt. Les services sont arrêtés avant le snapshot et redémarrés avant le début du chargement, de sorte qu'un chargement lent ou échoué ne prolonge jamais la fenêtre de temps d'arrêt. Consultez [Sémantique de la sauvegarde froide](#sémantique-de-la-sauvegarde-froide) pour le modèle de garantie complet.

### Filtrer les dépôts par stratégie

Chaque stratégie peut porter des filtres `--include` et `--exclude`. Les noms de dépôts correspondant à un motif `--exclude` sont ignorés pour cette stratégie ; `--include` restreint l'exécution aux seuls noms correspondants. Les filtres correspondent au nom de dépôt de la configuration locale (sans `:tag`).

```bash
# Stratégie hot : sauvegarder tout toutes les heures
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Stratégie cold : sauvegarder tout chaque semaine, sauf le grand jeu de données dérivé
rdc config backup-strategy set \
  --name weekly-cold \
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

Les dépôts non exclus d'aucune des deux stratégies apparaissent dans les sous-dossiers `hot/` et `cold/` du stockage. La sortie fusionnée de `rdc repo backup list` affiche les deux lignes pour vérifier quels flux couvrent quels dépôts.

## Opérations de sauvegarde

### Déployer le calendrier sur une machine

Envoyez les stratégies associées vers une machine en tant que timers systemd :

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

Le déploiement est un réconciliateur d'état. Il lit les fichiers d'unité actuels et l'état de systemd sur la machine, les compare à ce que la configuration produirait (SHA-256 par fichier) et ne touche que les unités dont le contenu a réellement changé. Relancer sans changement de configuration est un no-op : pas d'écritures, pas de `daemon-reload`, pas d'agitation des minuteurs.

`--dry-run` affiche le plan pour chaque stratégie (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sans toucher à la machine. Combinez avec `--debug` pour afficher également les corps d'unités générés ; les tokens rclone sont masqués.

Si une sauvegarde est en cours d'exécution pour une stratégie que vous êtes sur le point de mettre à jour ou de supprimer, le déploiement échoue rapidement avec une indication pour l'annuler ou passer `--force`. Avec `--force`, l'invocation en cours conserve son unité en mémoire et la nouvelle configuration s'applique au prochain tick du minuteur, de sorte que la sauvegarde en cours n'est jamais interrompue.

`--reset-failed` est opt-in. Lorsqu'il est passé, il efface l'état d'échec de systemd sur les services modifiés après un déploiement réussi. Désactivé par défaut pour que les signaux d'échec précédents restent visibles pour les alertes.

### Exécuter une sauvegarde maintenant

Déclenchez une sauvegarde immédiatement sans attendre le timer. Fonctionne même sans timers déployés, en utilisant `systemd-run` pour une exécution ad hoc :

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### Voir le statut de la sauvegarde

Affiche le statut actuel des timers de sauvegarde et les résultats récents des tâches :

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Annuler une sauvegarde en cours

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Migration de dépôt

Déplacer un dépôt d'une machine à une autre :

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--name <repo>` | Dépôt à migrer |
| `--from <machine>` | Machine source |
| `--to <machine>` | Machine de destination |
| `--provision` | Provisionner le dépôt sur la destination avant le transfert |
| `--checkpoint` | Créer un checkpoint CRIU avant la migration |
| `--skip-dns` | Ignorer la mise à jour des enregistrements DNS après la migration |
| `--bwlimit <limit>` | Limite de bande passante pour le transfert (p. ex. `50M`) |

La migration transfère les données du dépôt chiffré via rsync. Le dépôt source reste intact jusqu'à ce que vous le supprimiez explicitement.

## Parcourir le stockage

Parcourez le contenu d'un emplacement de stockage :

```bash
rdc storage browse --name my-storage
```

## Bonnes pratiques

- Planifier des sauvegardes froides quotidiennes pour des snapshots cohérents au niveau applicatif des données critiques
- Utiliser les sauvegardes chaudes pour des snapshots haute fréquence où aucune interruption n'est acceptable
- Tester les restaurations périodiquement pour vérifier l'intégrité des sauvegardes
- Utiliser plusieurs fournisseurs de stockage pour les données critiques (p. ex. S3 + B2)
- Garder les identifiants en sécurité ; les sauvegardes sont chiffrées mais l'identifiant LUKS est nécessaire pour la restauration
