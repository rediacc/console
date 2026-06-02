---
title: "Gestion de branches façon Git"
description: "Traiter les forks copy-on-write comme des commits git : geler un fork en commit immuable, nommer des branches, extraire des commits dans des forks modifiables, parcourir l'historique et fusionner sans jamais muter un dépôt en cours d'exécution."
category: Reference
subcategory: advanced
order: 41
language: fr
sourceHash: "6ca18986dfd6e237"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Gestion de branches façon Git

Les dépôts Rediacc prennent en charge une gestion des versions façon Git, construite sur des forks copy-on-write. Chaque fork immuable est un **commit** : une image stabilisée en octets, figée, qui refuse de monter. Les branches sont des références nommées pointant vers un commit. `rdc repo checkout` clone par reflink un commit dans un fork de travail modifiable, et `rdc repo merge` combine deux lignes d'historique sans jamais muter un dépôt en cours d'exécution.

Le modèle repose sur deux couches. La **machine est le magasin d'objets** : les commits sont des images de forks immuables résidant sur le datastore. La **config CLI est le magasin de références** : les noms de branches, le `HEAD` courant et le reflog résident dans votre configuration locale, pas sur la machine. C'est la même séparation que git utilise entre `.git/objects` et `.git/refs`.

## Quand l'utiliser

Recourez aux branches lorsqu'un fork mérite un nom. Un agent IA a tourné librement dans un fork de production, le résultat est satisfaisant, et vous voulez un point de contrôle gelé et nommé auquel vous pourrez revenir ou promouvoir plus tard : `rdc repo commit` le fige, `rdc repo branch` le nomme. Avant une migration risquée, commitez le fork de travail pour obtenir un point de restauration exact qui ne changera jamais (un commit immuable refuse de monter, rien ne peut y écrire). Pour comparer deux points de contrôle, `rdc repo diff` fonctionne entre deux commits quelconques car ils partagent un ancêtre copy-on-write. Pour ramener une ligne de travail vérifiée sur un fork cible, `rdc repo merge` construit le résultat dans un clone par reflink puis l'échange atomiquement, de sorte qu'une cible en cours d'exécution n'est jamais corrompue en milieu de fusion.

N'y recourez pas à la place de `rdc repo fork` quand vous n'avez besoin que d'une copie jetable. Un fork ordinaire est l'unité appropriée pour l'isolation éphémère par test. Les commits apportent de la valeur quand un état vaut la peine d'être conservé, nommé ou livré.

## Relation entre commits et forks

Un dépôt est un fichier image LUKS sur un pool btrfs. Un fork est un reflink en temps constant de cette image ; forker un dépôt de 1 Go et un dépôt de 100 Go coûte pareil. Un **commit** est un fork qui a été marqué immuable : renet refuse de le monter, ce qui maintient son image stable en octets pour toujours. Cette stabilité fait d'un commit un point de restauration fiable et une base déterministe pour le transfert delta entre machines.

`rdc repo commit` enregistre le message de commit, l'auteur, l'horodatage et le commit parent **à l'intérieur du volume** (les métadonnées voyagent ainsi avec l'image lors d'un push) et les met également en miroir hors volume (pour que `rdc repo log` puisse parcourir l'historique sans rien déverrouiller). Le fork de travail que vous avez commité reste inchangé, exactement comme git laisse votre arbre de travail intact après un commit.

## Commandes

### rdc repo commit

Gèle un fork de travail monté dans un nouveau commit immuable.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--name <name>` | Fork de travail à commiter. Doit être monté. Requis. | requis |
| `--message <msg>` | Message de commit. Requis. | requis |
| `--author <author>` | Auteur enregistré dans les métadonnées du commit. | non défini |
| `-m, --machine <name>` | Machine cible. Requis. | requis |
| `--debug` | Diagnostics détaillés sur stderr. | off |

Le nouveau commit est enregistré dans la configuration locale avec `immutable: true`, et le `headCommit` du fork de travail avance pour pointer vers lui. Commiter un dépôt immuable est refusé : extrayez-le d'abord dans un fork modifiable.

### rdc repo branch

Crée une référence de branche nommée pointant vers le commit courant d'un fork de travail.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--branch <branch>` | Nom de la nouvelle branche. Requis. | requis |
| `--name <name>` | Fork de travail dont le commit courant est pointé par la branche. Requis. | requis |

Il s'agit d'une opération purement côté config. Aucun travail n'est effectué sur la machine. La référence de branche associe un nom au `headCommit` du fork de travail ; le fork doit donc avoir au moins un commit au préalable.

### rdc repo checkout

Clone par reflink un commit immuable (ou la pointe d'une branche) dans un nouveau fork de travail modifiable.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--ref <commit\|branch>` | GUID de commit à extraire, ou nom de branche quand `--from` est fourni. Requis. | requis |
| `--tag <name>` | Nom du nouveau fork de travail modifiable. Requis. | requis |
| `-m, --machine <name>` | Machine cible. Requis. | requis |
| `--from <workingFork>` | Résoudre `--ref` comme nom de branche sur l'ensemble de branches de ce fork de travail. | commit direct |
| `--debug` | Diagnostics détaillés sur stderr. | off |
| `--skip-router-restart` | Ignorer le redémarrage du routeur. | off |

Le checkout réutilise le chemin reflink du fork et est donc quasi instantané, quelle que soit la taille du dépôt. Le `headCommit` du nouveau fork de travail est défini sur le commit extrait.

### rdc repo log

Parcourt l'historique des commits atteignables depuis un fork de travail ou un commit.

```bash
rdc repo log --name <fork> -m <machine>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--name <name>` | Fork de travail ou commit depuis lequel démarrer le parcours. Requis. | requis |
| `-m, --machine <name>` | Machine cible. Requis. | requis |
| `--json` | Afficher l'historique des commits en JSON. | off |
| `--debug` | Diagnostics détaillés sur stderr. | off |

`log` parcourt la chaîne de parents enregistrée par `rdc repo commit`, en lisant le miroir d'état hors volume : aucun commit n'est déverrouillé ni monté. Opération en lecture seule.

### rdc repo merge

Fusionne un commit ou un fork source dans un fork de travail cible, sans muter la cible en cours d'exécution.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--name <name>` | Fork de travail cible de la fusion. Requis. | requis |
| `--from <source>` | Commit ou fork source à fusionner. Requis. | requis |
| `-m, --machine <name>` | Machine cible. Requis. | requis |
| `--force` | Met en veille une cible montée ou en cours d'exécution, puis fusionne. Ne mute jamais un montage en cours. | off |
| `--resolve <ours\|theirs>` | Fusion à trois voies par fichier : applique les modifications par fichier de la source sur la cible, en conservant (`ours`) ou en prenant (`theirs`) la version de la source pour les fichiers modifiés des deux côtés. Omettez ce paramètre pour une prise en bloc de la source. | off |
| `--base <guid>` | Commit ancêtre commun pour la fusion à trois voies (utilisé avec `--resolve`). Par défaut, le parent du commit source ou le commit courant de la cible. | auto |
| `--debug` | Diagnostics détaillés sur stderr. | off |

Le résultat est construit dans un clone par reflink, puis échangé atomiquement derrière un marqueur de sécurité en cas de crash : une fusion interrompue laisse la cible originale intacte. Une cible montée ou en cours d'exécution est refusée sauf avec `--force`, qui arrête proprement la cible avant l'échange.

Sans `--resolve`, la fusion prend intégralement la source (la cible devient la source). Avec `--resolve`, c'est une fusion à trois voies par fichier par rapport au parent enregistré du commit source : les fichiers modifiés d'un seul côté sont pris de ce côté, et les fichiers modifiés des deux côtés sont résolus selon le flag. Les chemins en conflit sont signalés.

### rdc repo gc

Collecte les objets commits immuables sur une machine qu'aucune branche ni HEAD n'atteint.

```bash
rdc repo gc -m <machine>            # aperçu à sec (défaut)
rdc repo gc --apply -m <machine>    # supprime les commits inaccessibles
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `-m, --machine <name>` | Machine à collecter. Requis. | requis |
| `--apply` | Supprime réellement les commits inaccessibles (sinon aperçu à sec). | off |
| `--debug` | Diagnostics détaillés sur stderr. | off |

L'accessibilité est calculée depuis la configuration locale (le magasin de références) : ensemble des commits atteignables en suivant chaque pointe de branche et HEAD dans la chaîne de parents. Les commits immuables sur la machine hors de cet ensemble sont inaccessibles. Un objet monté ou un fork de travail n'est jamais collecté.

### rdc repo fsck

Valide les références de la config par rapport aux objets présents sur une machine.

```bash
rdc repo fsck -m <machine>
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `-m, --machine <name>` | Machine à vérifier. Requis. | requis |

Signale les références pendantes (une pointe de branche ou HEAD pointant vers un GUID absent de la machine) et les commits orphelins (un commit immuable sur la machine qu'aucune référence n'atteint). Opération en lecture seule ; récupérez les orphelins avec `rdc repo gc --apply`.

### Forks immuables

`rdc repo fork --immutable` marque le nouveau fork en lecture seule dès sa création, produisant une base équivalente à un commit sans étape `commit` séparée.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Un fork immuable refuse de monter, ce qui maintient son image stable en octets pour toujours. Utile comme base figée pour le transfert delta entre machines, où la base doit être identique des deux côtés. Pour y apporter des modifications, extrayez-le (ou forkez-le à nouveau) dans une copie modifiable.

## Exemples

### Commiter un fork de travail

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Commiter avec un auteur explicite

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Nommer une branche au commit courant

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Extraire un commit dans un nouveau fork modifiable

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Extraire la pointe d'une branche par son nom

Avec `--from`, la valeur de `--ref` est résolue comme un nom de branche sur le fork de travail indiqué :

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Parcourir l'historique

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Historique en JSON

`--json` produit le parcours structuré, du plus récent au plus ancien :

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Comparer deux commits

`rdc repo diff` fonctionne entre deux commits quelconques car ils partagent un ancêtre copy-on-write. Extrayez un commit, puis comparez-le à un autre :

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Consultez [rdc repo diff](/fr/docs/repo-diff) pour la référence complète du diff.

### Fusionner une ligne de travail vérifiée

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Fusionner dans une cible en cours d'exécution

Une cible montée ou en cours d'exécution est refusée sauf avec `--force`, qui la met d'abord en veille :

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Fusion à trois voies par fichier

Deux forks (`feature` et `hotfix`) extraits du même commit ont chacun modifié des fichiers. `--resolve theirs` applique la source (`hotfix`) dans la cible (`feature`) : les fichiers modifiés d'un seul côté sont pris de ce côté, et les fichiers modifiés des deux côtés sont résolus vers la source. La base est auto-détectée depuis l'ancêtre commun (ou fixée avec `--base`) :

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` a été modifié des deux côtés et résolu vers la source ; un fichier ajouté uniquement par `hotfix` est appliqué, et un fichier modifié uniquement par `feature` est conservé. Les chemins en conflit sont signalés pour vous permettre de les passer en revue.

### Créer une base immuable directement

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Transfert delta push et pull

Une image immuable et stable en octets constitue également la fondation du **transfert delta au niveau des blocs**. Quand la même base immuable existe sur deux machines, un push ou pull peut calculer les blocs modifiés par rapport à cette base et ne transférer que ceux-ci, au lieu de scanner toute l'image chiffrée. Un dépôt de 1 Go avec quelques blocs modifiés transfère alors en mégaoctets.

Vous ne passez pas normalement une base manuellement. Après un push complet, la CLI conserve l'image poussée comme base immuable sur les deux machines et l'enregistre : le **prochain** push de ce dépôt envoie automatiquement uniquement le delta, sans flag, même pour un fork qui existe déjà sur la cible. (Un re-push *complet* d'un fork existant nécessite toujours `--force`, car il remplace toute l'image plutôt qu'appliquer un delta vérifié.) Passez `--delta-base <guid>` pour épingler une base spécifique, et `--strategy <auto|physical|shared>` pour contrôler la détection des blocs modifiés (`auto` est correct dans presque tous les cas).

```bash
# Le premier push est un transfert complet ; il conserve aussi une base réutilisable des deux côtés.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Après des modifications locales, le push suivant n'envoie que les blocs modifiés, sans flag.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Épingler une base explicite (un commit immuable présent sur les deux machines).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Le delta fonctionne aussi en sens inverse, en ne tirant que les blocs modifiés depuis une machine source.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Re-tirer un dépôt local existant (le remplacer) avec --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

Le transfert delta s'applique uniquement entre machines (un distant avec la base FIEMAP). Les pushs vers le stockage objet cloud transfèrent toujours l'image complète. La base doit être identique en octets des deux côtés, ce qu'un commit immuable ou un fork `--immutable` garantit précisément.

## Schéma JSON

`rdc repo log --json` enveloppe le résultat renet dans l'enveloppe standard. L'historique parcouru se trouve dans `entries`, du plus récent au plus ancien :

| Champ | Type | Description |
|-------|------|-------------|
| `success` | boolean | Indique si le parcours s'est terminé. |
| `start` | string | GUID depuis lequel le parcours a démarré. |
| `entries` | array | Un objet par commit, du plus récent au plus ancien. |
| `entries[].guid` | string | GUID du commit. |
| `entries[].message` | string | Message de commit. Omis si vide. |
| `entries[].author` | string | Auteur du commit. Omis si vide. |
| `entries[].parent` | string | GUID du commit parent. Omis à la racine. |
| `entries[].committed_at` | string | Horodatage RFC 3339 du commit. Omis si non défini. |
| `entries[].immutable` | boolean | Indique si le commit est marqué en lecture seule (toujours vrai pour un vrai commit). |

Pour les champs de l'enveloppe et les règles d'auto-détection qui produisent du JSON dans les environnements non-TTY, consultez la [Référence de sortie JSON](/fr/docs/ai-agents-json-output).

## Limitations

- **Les références sont locales.** Les noms de branches, `HEAD` et le reflog résident dans votre configuration CLI, pas sur la machine. Pousser un commit vers une autre machine transporte l'objet commit et ses métadonnées dans le volume, mais la référence de branche est un concept côté config.
- **Un commit refuse de monter.** C'est le but : l'immuabilité est ce qui rend un commit stable en octets. Pour exécuter ou modifier un commit, extrayez-le d'abord dans un fork de travail modifiable.
- **La résolution de fusion est au niveau des fichiers, pas des lignes.** La prise en bloc de la source (sans `--resolve`) et la fusion à trois voies par fichier (`--resolve ours|theirs`) sont toutes deux prises en charge. La fusion à trois voies résout les conflits fichier entier selon le flag ; elle ne produit pas de marqueurs de fusion au niveau des lignes dans un fichier.
- **L'historique est une chaîne de parents.** `rdc repo log` parcourt le lien `parent` unique enregistré au moment du commit. Il s'arrête lorsqu'il atteint un commit dont les métadonnées ne sont pas présentes sur la machine interrogée.

## Voir aussi

- [rdc repo diff](/fr/docs/repo-diff). Diff au niveau des fichiers entre deux commits ou forks liés quelconques.
- [Dépôts](/fr/docs/repositories). Créer, forker, monter et opérer des dépôts.
