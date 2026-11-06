---
title: Supervision
description: >-
  Supervisez la santé des machines, les conteneurs, les services, les dépôts et
  exécutez des diagnostics.
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: fr
sourceHash: "6e4968522e118c98"
sourceCommit: "9b8aa220de6eb4f7c7b7783456af6871202c8305"
---

# Supervision

Rediacc fournit des commandes de supervision intégrées pour inspecter la santé des machines, les conteneurs en cours d'exécution, les services, le statut des dépôts et les diagnostics système.

## Santé de la machine

Obtenez un rapport de santé détaillé pour une machine :

```bash
rdc machine health server-1
```

Ce rapport inclut :
- **Système** : temps de fonctionnement, mémoire (avertissement au-delà de 80 %, erreur au-delà de 90 %), utilisation du disque et du datastore (avertissement au-delà de 85 %, erreur au-delà de 95 %)
- **Conteneurs** : nombre en cours d'exécution, sains, défaillants ; un conteneur en boucle `Restarting` est critique
- **Services** : unités systemd en échec (une erreur) et unités qui redémarrent sans cesse (critique)
- **Stockage** : santé SMART (un disque défaillant est critique) et température des disques
- **Dépôts** : dépôts à démarrage automatique qui ne sont pas montés, et utilisation du système de fichiers de chaque dépôt (avertissement au-delà de 85 %, erreur au-delà de 95 %)
- **Sauvegardes** : dépôts non sauvegardés depuis plus de 10 jours, en retard sur leur planification ou leur cible, ou dont la dernière vérification a échoué
- **Licences** : licences de dépôt expirées, absentes, non concordantes ou invalides, et licences à renouveler
- **Processus renet** : démons qui exécutent encore un binaire renet remplacé
- **Santé des dépôts** : le résultat de `health()` de chaque dépôt monté (voir ci-dessous)
- **Certificats** : certificats du proxy proches de l'expiration, et CNAME de défi ACME partagés
- **Problèmes** : problèmes identifiés

Le code de sortie donne le verdict : `0` sain, `1` avertissement, `2` erreur, `3` critique (un disque défaillant, ou un conteneur ou un service en boucle de redémarrage). Utilisez `--output json` pour une sortie lisible par les machines ; elle contient `repo_health` (un rapport par dépôt) et `findings`, chacun avec un code, une gravité (`info`, `warning`, `error` ou `critical`), un sujet, un détail et, lorsqu'un correctif existe, `fix` (voir [Réparation](#repair)).

## Santé des dépôts

Un Rediaccfile peut définir une fonction `health()` qui vérifie les services du dépôt lui-même ([Services](/fr/docs/services)) : code `0` ok, `1` avertissement, `2` erreur. Pour l'exécuter sur un dépôt :

```bash
rdc repo health my-app@server-1
```

La commande se termine avec le niveau le plus grave parmi les Rediaccfiles du dépôt. Un dépôt dont aucun Rediaccfile ne définit `health()` affiche **aucun contrôle** et se termine avec `0` ; il n'est jamais signalé comme sain. Un `health()` qui dépasse son délai, est tué ou se termine avec un autre code est une erreur, tout comme l'impossibilité de joindre la machine (code `2`).

`rdc machine health` exécute le `health()` de chaque dépôt monté en un seul appel et reporte le niveau le plus grave dans son propre code de sortie, avec un constat par dépôt en avertissement (`repo.health.warning`) ou en erreur (`repo.health.error`). Les dépôts sans contrôle sont listés, pas signalés. Quand le renet de la machine est antérieur aux contrôles de santé des dépôts, le résultat est un avertissement, `renet.repo-health.unsupported`, jusqu'à ce que `rdc machine setup` le mette à jour.

## Expiration des certificats et défis ACME

`rdc machine health` lit les certificats ACME du proxy et signale `cert.expiry.near` pour chacun de ceux qui expirent dans moins de 21 jours (un avertissement) ou moins de 7 jours (une erreur). Le proxy renouvelle 30 jours à l'avance : un certificat à moins de 21 jours signifie donc que son renouvellement échoue depuis au moins neuf jours.

Il signale aussi `acme.challenge.cname-shared` lorsque l'enregistrement `_acme-challenge.<name>` d'un nom de certificat suit un CNAME vers un nom qui n'est pas lui-même un nom `_acme-challenge.`, ou lorsque deux noms aboutissent au même nom. Un enregistrement générique qui est un CNAME produit cette configuration : tous les défis atterrissent sur un seul nom et les renouvellements entrent en collision. Une délégation volontaire (par exemple `_acme-challenge.mail.example.com` pointant vers `_acme-challenge.mail.example.io`) n'est pas signalée ; ajoutez toute autre délégation voulue à `ACME_DELEGATED_NAMES` (une liste de noms de certificats séparés par des virgules) dans le `config.env` du proxy. Un nom dont la chaîne de défi n'a pas pu être résolue (erreur DNS ou délai dépassé) est signalé comme `acme.challenge.unknown`, un avertissement, car le contrôle n'a pas pu s'exécuter pour ce nom.

## Réparation

Chaque constat porte un code et, lorsqu'un correctif sûr existe, un `fix` avec une `action`, une `class` de sécurité et `window_only`. `rdc machine health` reste en lecture seule ; `rdc machine repair` est la commande qui agit :

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Classe | Signification |
|---|---|
| `auto-safe` | S'exécute par défaut : redémarrer un conteneur ou Traefik, faire un trim et un nettoyage, écrire l'ancre ACME |
| `auto-with-backup` | S'exécute uniquement avec `--with-backup`, après un instantané réussi du dépôt ; un instantané en échec annule le correctif |
| `operator-only` | Ne s'exécute jamais. La commande affiche la commande exacte à lancer à la main. Tout ce qui supprime des données nommées ou engage de l'argent relève de cette classe |

`window_only` est une condition ajoutée à la classe : le correctif ne s'exécute que dans la fenêtre de maintenance de la machine, `HH:MM-HH:MM` en UTC (elle peut franchir minuit). Une machine sans fenêtre n'exécute jamais ces correctifs d'elle-même ; `--window-override` les exécute à la main. Définissez ou effacez la fenêtre avec :

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Chaque correctif vérifie d'abord que son constat est toujours présent : une seconde exécution n'a donc rien à faire. Les correctifs qui agissent sur la même chose ne s'exécutent qu'une fois (un seul redémarrage de Traefik couvre tous les certificats). Chaque correctif est consigné dans le journal de la machine avec l'étiquette `rediacc-repair` et dans le JSON `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`), et l'exécution se termine par une revérification complète. Le code de sortie est `0` quand il ne reste rien, `1` quand il reste des avertissements ou des éléments operator-only, et `2` quand il reste une erreur ou qu'un correctif a échoué.

| Constat | Correctif | Classe |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim, puis nettoyage des conteneurs arrêtés, des volumes anonymes orphelins et des images inutilisées | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Redémarrer le conteneur | auto-safe |
| `renet.binary.replaced` | Redémarrer les superviseurs de dépôt concernés (`rdc machine restart-services --include-docker`, limité à eux) | auto-safe, fenêtre uniquement |
| `cert.expiry.near` | Redémarrer Traefik pour qu'il retente le renouvellement | auto-safe |
| `acme.challenge.cname-shared` | Écrire l'ancre ACME (ci-dessous) | auto-safe |
| `repo.health.warning`, `repo.health.error` | Exécuter le `repair()` du dépôt ([Services](/fr/docs/services)) | la classe que déclare le Rediaccfile |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Affiché comme la commande à lancer | operator-only |

Les constats sans correctif (échecs SMART, température, mémoire, disque système, vérification échouée) sont signalés et laissés à l'opérateur.

Le nettoyage ne touche jamais le hub : les conteneurs portant le label `rediacc.hub.*` et les volumes portant le label `rediacc.hub.user` ou nommés `rediacc-hub-home-*` sont exclus, si bien que le répertoire personnel d'un utilisateur du hub survit à chaque récupération d'espace. Un résidu que le trim et le nettoyage ne peuvent pas libérer (volumes nommés, grosses données d'application) reste une décision de l'opérateur.

### Réparation d'un dépôt

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` exécute les fonctions `repair()` du dépôt avec les mêmes classes : `auto-safe` s'exécute, `auto-with-backup` exige `--with-backup`, et un `repair()` non déclaré (`operator-only`) ne s'exécute qu'après une réponse à sa confirmation ou avec `--yes`. `health()` s'exécute de nouveau ensuite et le code de sortie suit le niveau final : `0` ok ou aucun contrôle, `1` avertissement, `2` erreur ou un `repair()` en échec.

### L'ancre ACME

Un enregistrement DNS générique qui est un CNAME fait que chaque nom `_acme-challenge.<host>` le suit : tous les défis atterrissent alors sur un seul nom et les renouvellements entrent en collision (`acme.challenge.cname-shared`). Le correctif écrit un enregistrement TXT de valeur `rediacc-acme-anchor` sur chaque `_acme-challenge.<name>` en collision, via le jeton Cloudflare du proxy, puis redémarre Traefik. Un enregistrement explicite soustrait le nom à la portée du générique, et le défi atterrit donc au bon endroit. Le correctif ne fait qu'ajouter des enregistrements, et une ancre existante est laissée telle quelle.

Les noms listés dans `ACME_DELEGATED_NAMES` (une liste de noms de certificats séparés par des virgules dans le `config.env` du proxy) sont des délégations volontaires : ils ne sont jamais ancrés ni signalés. Quand le proxy n'a pas de jeton Cloudflare utilisable, le correctif se replie sur `LEGO_DISABLE_CNAME_SUPPORT=true` dans `config.env`, mais seulement si aucun nom délégué n'est déclaré, car cette variable désactive le suivi des CNAME pour tous les noms ; avec une délégation déclarée, le constat reste operator-only. Le même correctif s'exécute à chaque installation du proxy (`rdc machine infra push`), et seul avec `renet proxy acme-fix` sur la machine.

## Lister les conteneurs

Affichez tous les conteneurs en cours d'exécution sur tous les dépôts d'une machine :

```bash
rdc machine status server-1 --containers
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du conteneur |
| Status | Temps de fonctionnement ou raison de l'arrêt |
| State | En cours d'exécution, arrêté, etc. |
| Health | Sain, défaillant, aucun |
| CPU | Pourcentage d'utilisation du processeur |
| Memory | Utilisation de la mémoire / limite |
| Repository | Dépôt propriétaire du conteneur |

Options :
- `--health-check`, Effectuer des vérifications de santé actives sur les conteneurs
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut les détails complets des conteneurs (`labels`, `port_mappings`, `image`, `id`) ainsi que `repository` (nom résolu), `repository_guid` (GUID d'origine), `domain` et `autoRoute`.

## Lister les services

Affichez les services systemd liés à Rediacc sur une machine :

```bash
rdc machine status server-1 --services
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du service |
| State | Actif, inactif, en échec |
| Sub-state | En cours d'exécution, arrêté, etc. |
| Restarts | Nombre de redémarrages |
| Memory | Utilisation de la mémoire du service |
| Repository | Dépôt associé |

Options :
- `--stability-check`, Signaler les services instables (en échec, >3 redémarrages, redémarrage automatique)
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut les détails complets des services avec `repository` (nom résolu) et `repository_guid` (GUID d'origine).

## Lister les dépôts

Affichez les dépôts sur une machine avec des statistiques détaillées :

```bash
rdc machine status server-1 --repositories
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du dépôt |
| Size | Taille de l'image disque |
| Mount | Monté ou démonté |
| Docker | Démon Docker en cours d'exécution ou arrêté |
| Containers | Nombre de conteneurs |
| Disk Usage | Utilisation réelle du disque au sein du dépôt |
| Modified | Date de dernière modification |

Options :
- `--search <text>`, Filtrer par nom ou chemin de montage
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut `name` (résolu) et `guid` (GUID d'origine), et imbrique pour chaque dépôt les tableaux `containers` (avec `domain`, `autoRoute`, `repository`/`repository_guid`) et `services`.

## Santé du stockage

Inspectez la fragmentation BTRFS et le partage de reflinks sur tous les dépôts d'une machine :

```bash
rdc machine status server-1 --storage-health
```

| Colonne | Description |
|---------|-------------|
| Quota | La taille maximale du dépôt (son plafond de croissance, défini à la création ou via resize/auto-grow) |
| Allocated | Ce que l'image éparse occupe réellement dans le pool en ce moment |
| Unique | Données uniques réelles appartenant uniquement à ce dépôt |
| Shared | Blocs de données réutilisés entre dépôts via les reflinks BTRFS (copies gratuites) |
| Reclaimable | L'écart entre la quantité allouée et la quantité utilisée que [`repo trim`](/fr/docs/repositories#reclaim-space-trim) peut restituer au pool. Affiche `-` pour les dépôts non montés |
| Discards | Si le volume chiffré propage les discards (`on` pour tout dépôt monté par une version actuelle) |
| Divergence | Pourcentage de l'image propre à ce dépôt plutôt que partagé (plus élevé = davantage récupérable en cas de suppression) |
| Frag | Nombre d'extents par Go dans l'image copy-on-write (informatif uniquement) |

Le quota et l'allocation sont intentionnellement deux chiffres distincts : un dépôt avec un quota de 20 Go qui stocke 6 Go de données ne coûte au pool que ce qu'il a alloué. Le pool peut donc promettre plus de quota total qu'il n'en a physiquement, et la colonne Reclaimable indique combien de l'allocation de chaque dépôt n'est plus utilisée et peut être restituée par trim.

En dessous du tableau, un résumé du pool indique le niveau de remplissage du datastore et l'espace que les snapshots de sauvegarde immobilisent en ce moment :

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Pendant l'exécution d'une sauvegarde, son snapshot continue de référencer chaque bloc qu'il partage avec les dépôts actifs : les suppressions et les trims libèrent moins d'espace dans le pool jusqu'à la fin de ce cycle de sauvegarde et la suppression du snapshot. Les snapshots orphelins issus de sauvegardes interrompues sont détectés et supprimés automatiquement par le mainteneur de stockage en quelques minutes.

Le résumé affiche les économies totales réalisées grâce aux reflinks BTRFS :

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Taille virtuelle** est la somme de toutes les tailles d'image de dépôt. C'est ce à quoi ressemblent les dépôts, mais cela compte double les blocs partagés via les reflinks.
- **Données uniques** correspond au stockage réellement consommé par les données d'un dépôt n'existant que dans un seul dépôt. C'est ce qui serait libéré en supprimant un dépôt.
- **Partagé** désigne les données réutilisées entre dépôts via les reflinks BTRFS. La bifurcation d'un dépôt crée des copies reflink qui partagent des blocs jusqu'à ce que l'un ou l'autre côté écrive de nouvelles données, moment auquel les blocs divergent.
- **Efficacité** est le pourcentage de données réutilisées via les reflinks. Plus élevé est mieux. Une machine avec de nombreuses bifurcations depuis le même dépôt parent affichera une efficacité proche de 100%.

La colonne Frag est informative. Elle compte les extents du fichier image copy-on-write, pas les fichiers que votre application lit à l'intérieur, donc elle affiche des valeurs élevées sous des charges d'écriture aléatoires normales (bases de données, couches de conteneurs) et ne prédit pas les performances de lecture sur un stockage SSD. Rediacc ne propose délibérément aucune commande de défragmentation : `btrfs filesystem defragment` dé-partage les forks et snapshots avec reflinks, ce qui sur un pool presque plein peut faire exploser l'utilisation de l'espace alors que les benchmarks ne montrent aucun gain de lecture mesurable. Pour les mesures complètes et le raisonnement, voir [Votre chiffre de fragmentation semble terrifiant. J'ai mesuré ce qu'il coûte.](/fr/blog/i-benchmarked-btrfs-fragmentation).

Le scan s'exécute en parallèle et prend 5 à 15 secondes selon le nombre et la taille des dépôts. Quand `--storage-health` n'est pas spécifié, une indication d'une ligne apparaît après la sortie de la requête comme rappel.

## Scrub BTRFS

Rediacc planifie automatiquement un scrub BTRFS hebdomadaire sur chaque machine. Le scrub lit chaque bloc de données du datastore, vérifie les sommes de contrôle et signale toute corruption. Cela détecte la corruption silencieuse des données (bitrot) avant qu'elle ne se propage aux sauvegardes et aux bifurcations.

Le scrub s'exécute chaque dimanche à 02h00 heure locale (fuseau horaire de la machine) avec un délai aléatoire pouvant aller jusqu'à 1 heure. Il s'exécute avec la priorité d'E/S la plus basse (`ionice idle`, `nice 19`) afin de ne pas interférer avec les services en cours. Sur les machines avec SSD, comptez environ 8 minutes par 100 Go de datastore.

Le minuteur de scrub est installé automatiquement au premier démarrage du daemon après une mise à niveau de renet. Lorsque la politique de scrub change dans une future version de renet, elle se met à jour au prochain démarrage du daemon sans intervention de l'utilisateur.

### Statut du scrub

Le résultat du dernier scrub est sauvegardé hors du volume BTRFS (dans `/var/lib/rediacc/scrub-last-result.json`) afin qu'il reste lisible même si le volume rencontre des problèmes. La sortie de `rdc machine status --system` inclut un champ `scrub_status` :

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Statut | Signification |
|--------|---------------|
| `ok` | Le dernier scrub s'est terminé sans erreur |
| `never_run` | Le scrub n'a pas encore été exécuté (le minuteur vient d'être installé) |
| `overdue` | Le dernier scrub date de plus de 14 jours |
| `errors_found` | Le scrub a trouvé des erreurs de somme de contrôle (vérifiez les compteurs `total_errors` et `uncorrectable`) |
| `failed` | Le processus de scrub s'est terminé avec un code non nul |

Si `uncorrectable` est supérieur à zéro, les blocs affectés ne peuvent pas être réparés automatiquement (BTRFS sur un seul disque n'a pas de copie redondante). Restaurez le dépôt affecté depuis la sauvegarde la plus récente.

### Scrub manuel

Pour lancer un scrub immédiatement (par exemple après une coupure de courant ou une migration de disque) :

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Le résultat est sauvegardé dans le même fichier JSON et est immédiatement visible dans le prochain `rdc machine status --system`.

## Aperçu de la machine

Obtenez un aperçu complet d'une machine incluant les informations de déploiement :

```bash
rdc machine status server-1
```

Ceci fournit :
- Nom d'hôte et temps de fonctionnement
- Utilisation de la mémoire, du disque et du datastore
- Nombre total de dépôts, nombre de montés, nombre de dépôts dont le démon Docker répond
- Informations détaillées par dépôt

Utilisez `--output json` pour une sortie lisible par les machines.

## Tester la connexion

Vérifiez la connectivité SSH vers une machine :

```bash
rdc term connect server-1 -c "hostname"
```

La commande affiche le nom d'hôte distant en cas de succès et une erreur de
connexion sinon, ce qui vérifie en une seule étape le DNS, le port SSH et
l'authentification par clé.

## Diagnostics (doctor)

Exécutez une vérification diagnostique de votre environnement Rediacc :

```bash
rdc doctor
```

| Catégorie | Vérifications |
|-----------|---------------|
| **Environnement** | Version de Node.js, version du CLI, mode SEA, installation de Go, disponibilité de Docker |
| **Renet** | Emplacement du binaire, version, CRIU, rsync, ressources SEA embarquées |
| **Paramètres** | Profil actif, adaptateur, machines, clé SSH |
| **Virtualisation** | Vérifie si votre système peut exécuter des machines virtuelles locales (`rdc ops`) |

Chaque vérification indique **OK**, **Avertissement** ou **Erreur**. Utilisez cette commande comme première étape lors du dépannage de tout problème.

Codes de sortie : `0` = tout réussi, `1` = avertissements, `2` = erreurs.

## Vérifications de disponibilité des services

Lors d'un `repo up`, renet attend que les services HTTP acceptent les connexions avant de les déclarer prêts. Cette attente tient compte des vérifications de santé Docker :

- Les conteneurs que Docker signale comme **sains** sont considérés comme immédiatement disponibles, sans sonde TCP.
- Les conteneurs encore dans la `start_period` de leur vérification de santé génèrent une note informative, non un avertissement ; le proxy continue de réessayer jusqu'à ce qu'ils soient liés.
- Les services Compose sans conteneur en cours d'exécution (par exemple, derrière un profil inactif) sont ignorés.
- Tout le reste est sondé en TCP pendant 15 secondes au maximum (définissez `REDIACC_READINESS_TIMEOUT`, en secondes, pour modifier cette valeur).

Définir un [health check Docker](https://docs.docker.com/reference/dockerfile/#healthcheck) sur les services à démarrage lent donne à renet un signal de disponibilité fiable et supprime le bruit des sondes dans la sortie de déploiement.
