---
title: "rdc repo diff"
description: "Affiche une comparaison au niveau des fichiers, de style git, entre deux référentiels dupliqués par copie à l'écriture en comparant leurs images chiffrées au niveau des blocs, sans déchiffrement."
category: Reference
subcategory: advanced
order: 40
language: fr
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` rapporte les fichiers qui ont changé entre deux référentiels associés : un fork et son parent, ou n'importe quel couple de référentiels qui partagent un ancêtre en copie à l'écriture. Passez `--name <fork>` pour comparer un fork par rapport au parent enregistré dans la configuration locale, ou ajoutez `--base <repo>` pour comparer un référentiel connexe arbitraire, où `--base` est le côté de base (ancien) et `--name` est le côté cible (nouveau). La commande est en lecture seule et ne déchiffre jamais les images. Elle les compare au niveau des blocs sur la machine distante, donc le coût suit le nombre de blocs modifiés, pas la taille du référentiel : un repo de 1 Go et un repo de 100 Go avec les mêmes modifications prennent le même temps. Si l'intégralité du référentiel a changé, le nombre de blocs s'échelonne avec la taille et le coût aussi.

## Quand l'utiliser

Donc : privilégiez `repo diff` avant de promouvoir un fork. Un agent IA s'est déchaîné dans une copie forkée de la production et vous voulez voir exactement les fichiers qu'il a touchés avant de fusionner la modification : `repo diff --name <fork> -m <machine>` vous donne cette liste de fichiers en secondes. Secondes. Après une restauration de récupération après sinistre, comparez le fork restauré par rapport à l'instantané qu'il était censé reproduire pour confirmer que l'ensemble de fichiers attendu a bien été restauré et que rien d'autre n'a dérivé. Pour un fork de longue durée qui a fonctionné aux côtés de son parent pendant des semaines, la comparaison montre la divergence accumulée (éditions de configuration, accrétion des journaux, migrations de schéma) sans monter et parcourir manuellement les deux arbres.

Ne l'utilisez pas entre des référentiels non associés. Les deux côtés doivent partager un ancêtre en copie à l'écriture, car la comparaison fonctionne sur l'historique des blocs partagés. Ce n'est pas non plus un outil de comparaison binaire : `--content` produit une sortie au niveau des lignes uniquement pour les fichiers texte, et les fichiers binaires signalent `Binary files differ`.

## Référence des commandes

### Résumé

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Options

| Option | Description | Par défaut |
|--------|-------------|---------|
| `--name <name>` | Référentiel à inspecter (la cible, côté nouveau). Obligatoire. | obligatoire |
| `--base <name>` | Référentiel pour comparer avec (la base, côté ancien). Prend par défaut le parent de `--name`, résolu à partir de la configuration locale. | parent de `--name` |
| (no format flag) | Sortie du statut du nom : une lettre colorée `A`/`M`/`D`/`R` par fichier modifié plus un résumé d'une ligne. | activé |
| `--name-only` | Un chemin modifié par ligne, sans lettre de statut. Convivial pour les tuyaux. | désactivé |
| `--stat` | Magnitude du changement par fichier (delta en octets et en blocs) avec un pied de page de totaux. | désactivé |
| `--content <path>` | Comparaison textuelle unifiée d'un seul fichier. Texte uniquement ; les fichiers binaires signalent `Binary files differ`. | désactivé |
| `--json` | Sortie structurée pour les agents et scripts. | désactivé |
| `--fast` | Ignorez l'étape de confirmation de hachage de contenu et faites confiance au filtre de bloc. Plus rapide, mais peut signaler excessivement des fichiers comme Modifiés. | désactivé |
| `-m, --machine <name>` | Machine cible. Obligatoire. | obligatoire |
| `--debug` | Diagnostiques détaillés sur stderr. | désactivé |
| `--skip-router-restart` | Ignorez l'étape de redémarrage du routeur. | désactivé |

## Exemples

### Statut du nom par défaut par rapport au parent

Avec seulement `--name`, le fork est comparé au parent enregistré dans la configuration locale. Ici, le fork `test-1gb:fork1` a un fichier modifié :

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Comparaison par rapport à une base explicite

Passez `--base` pour comparer un référentiel connexe arbitraire. `--base` est le côté de base (ancien), `--name` est le côté cible (nouveau) :

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Magnitude du changement avec `--stat`

`--stat` ajoute le delta en octets et le delta en blocs par fichier et un pied de page de totaux :

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Chemins uniquement, alimentés dans un outil

`--name-only` imprime un chemin par ligne sans lettre de statut, prêt à être alimenté dans une autre commande :

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Comparaison au niveau des lignes d'un fichier

`--content` produit une comparaison unifiée d'un seul fichier texte :

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### Filtrage JSON avec jq

`--json` émet l'enveloppe structurée sur stdout, donc elle se branche facilement dans `jq` :

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Formats de sortie

### Statut du nom (par défaut)

Chaque fichier modifié reçoit une lettre de statut et son chemin. `A` est ajouté, `M` modifié, `D` supprimé, `R` renommé (avec le chemin ancien affiché). Une ligne de résumé suit avec le décompte par catégorie.

### `--name-only`

Un chemin par ligne, pas de lettre de statut, pas de résumé. Utilisez-le quand une commande en aval souhaite une liste de fichiers propre.

### `--stat`

Chaque ligne porte le delta en octets et le delta en blocs du fichier. Un pied de page rapporte le nombre total de fichiers et le nombre total d'octets touchés. Cela montre où se situe le poids d'un changement, pas seulement les fichiers qui ont bougé.

### `--content <path>`

Une comparaison unifiée standard (en-têtes `---`/`+++`, blocs `@@`) pour un seul fichier texte. Les fichiers binaires signalent `Binary files differ` et ne produisent pas de blocs.

### `--json`

Le résultat structuré complet. Les données vont à stdout ; la progression et les diagnostiques vont à stderr, donc le JSON se branche facilement dans `jq` ou un autre analyseur même pendant l'impression de la progression.

## Schéma JSON

Le CLI enveloppe le résultat de renet dans l'enveloppe standard (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). Le résultat de la comparaison se trouve dans `data` avec des champs snake_case :

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Chaque objet dans `entries[]` décrit un chemin modifié :

| Champ | Type | Description |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Ajouté, Modifié, Supprimé ou Renommé. |
| `path` | string | Chemin du côté cible (ou côté de base pour une suppression). |
| `old_path` | string | Chemin précédent. Présent uniquement sur les renommages. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Type d'entrée. |
| `old_size` | number | Taille en octets du côté de base. |
| `size` | number | Taille en octets du côté cible. |
| `bytes_changed` | number | Octets qui diffèrent, arrondis aux blocs entiers. |
| `blocks_changed` | number | Nombre de blocs modifiés. |
| `inode` | number | Numéro d'inode, utilisé pour la détection des renommages. |
| `content_changed` | boolean | Si le contenu du fichier (pas seulement les métadonnées) a changé. |
| `mode_changed` | boolean | Si le mode du fichier a changé. `old_mode`/`new_mode` sont présents quand vrai. |
| `uid_changed` | boolean | Si le propriétaire a changé. `old_uid`/`new_uid` sont présents quand vrai. |
| `gid_changed` | boolean | Si le groupe a changé. `old_gid`/`new_gid` sont présents quand vrai. |
| `old_target` / `new_target` | string | Cibles de lien symbolique. Présent pour les liens symboliques modifiés. |

Pour les champs d'enveloppe et les règles de détection automatique qui émettent du JSON dans les environnements non-TTY, consultez la [Référence de sortie JSON](/fr/docs/ai-agents-json-output).

## Comment ça marche

Un référentiel est un fichier image LUKS2 sur un pool btrfs, et un fork est un reflink à temps constant de cette image. `repo diff` compare les deux images chiffrées au niveau des blocs via FIEMAP, en lisant uniquement les métadonnées du système de fichiers et en ne déchiffrant jamais rien. Il décale les décalages de texte chiffré modifiés par le décalage de données LUKS pour obtenir les décalages de dispositif ext4, puis remappose ces décalages aux noms de fichiers via la carte d'étendue ext4 de chaque fichier. Une marche d'identité finale d'inode des deux montages réconcilie le résultat en entrées Ajouté, Modifié, Supprimé et Renommé. Étant donné que le travail est borné par le décompte des blocs modifiés, la comparaison est indépendante de la taille du référentiel, et parce qu'elle réutilise un montage actif en place, elle ne perturbe jamais un référentiel en cours d'exécution. Le mécanisme complet est décrit dans [Git diff for encrypted disk images](/en/blog/git-diff-for-encrypted-disk-images).

## Limitations

- **Forks connexes uniquement.** Les deux côtés doivent partager un ancêtre en copie à l'écriture. Il n'y a pas de comparaison significative au niveau des blocs entre des référentiels non associés.
- **La détection des renommages est basée sur l'inode.** Un fichier est signalé comme renommé quand le même inode apparaît à un nouveau chemin. Une suppression puis une recréation (un nouvel inode) s'affiche comme une entrée Supprimée plus une entrée Ajoutée, pas un renommage.
- **`--content` est texte uniquement.** Il produit des blocs au niveau des lignes pour les fichiers texte. Les fichiers binaires signalent `Binary files differ`.
- **`--fast` peut signaler excessivement Modifié.** Il fait confiance au filtre de bloc et ignore l'étape de confirmation du hachage de contenu, donc un fichier dont les blocs ont bougé sans changer de contenu peut apparaître comme Modifié.
- **Le temps de la marche d'étendue s'échelonne avec la fragmentation, pas la taille.** Un système de fichiers très fragmenté a plus d'étendues à mapper, ce qui allonge la marche même quand le volume en octets des changements est petit.

## Voir aussi

- [rdc repo fork](/fr/docs/repositories). Créez le fork en copie à l'écriture que cette commande compare.
- [rdc repo status](/fr/docs/repositories). État actuel d'un seul référentiel.
- [rdc repo cat](/fr/docs/repositories). Lisez un seul fichier hors d'un référentiel.
