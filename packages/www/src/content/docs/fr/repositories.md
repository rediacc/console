---
title: "Dépôts"
description: "Créez, gérez et opérez des dépôts chiffrés LUKS sur des machines distantes."
category: "Guides"
order: 4
language: fr
sourceHash: "ffb07e5870accfd8"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Dépôts

Un **dépôt** est une image disque chiffrée LUKS sur un serveur distant. Quand elle est montée, elle fournit :
- Un système de fichiers isolé pour les données de votre application
- Un démon Docker dédié (séparé du Docker de l'hôte)
- Des adresses IP loopback uniques pour chaque service dans un sous-réseau /26

## Créer un dépôt

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Option | Obligatoire | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Oui | Machine cible où le dépôt sera créé |
| `--size <size>` | Oui | Taille de l'image disque chiffrée (par ex. `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Non | Ignorer le redémarrage du serveur de routage après l'opération |

La sortie affichera trois valeurs générées automatiquement :

- **GUID du dépôt** - Un UUID qui identifie l'image disque chiffrée sur le serveur.
- **Credential** - Une phrase de passe aléatoire utilisée pour chiffrer/déchiffrer le volume LUKS.
- **ID réseau** - Un entier (commençant à 2816, incrémentant de 64) qui détermine le sous-réseau IP pour les services de ce dépôt.

> **Stockez le credential de manière sécurisée.** C'est la clé de chiffrement de votre dépôt. S'il est perdu, les données ne peuvent pas être récupérées. Le credential est stocké dans votre `config.json` local mais n'est pas stocké sur le serveur.

## Monter et démonter

Le montage déchiffre et rend le système de fichiers du dépôt accessible. Le démontage ferme le volume chiffré.

```bash
rdc repo mount --name my-app -m server-1  # Déchiffrer et monter
rdc repo unmount --name my-app -m server-1  # Démonter et re-chiffrer
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Créer un point de contrôle CRIU avant le montage/démontage (pour les conteneurs avec le label `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routage après l'opération |

## Vérifier le statut

```bash
rdc repo status --name my-app -m server-1
```

## Lister les dépôts

```bash
rdc repo list -m server-1
```

### Colonne Type et miroir d'état

La table de sortie inclut une colonne `Type` avec trois valeurs :

- **`grand`**. Un dépôt de niveau supérieur enregistré dans votre configuration CLI locale sans parent. Le cas de base.
- **`fork`**. Un fork copy-on-write d'un autre dépôt. Identifié soit via `grandGuid` dans la configuration locale **soit** via le miroir `.interim/state` de renet sur la machine. L'une ou l'autre source est autoritaire ; les deux doivent être en accord une fois le miroir rempli.
- **`unknown`**. Aucun signal ne peut classifier le dépôt. Le plus souvent un fork legacy pré-miroir (créé avant le code du miroir et jamais remonté depuis), ou un `grand` obsolète dont l'entrée de configuration locale a été supprimée par erreur. Le CLI refuse de deviner ; l'opérateur doit exécuter [le remplissage du miroir](/fr/docs/pruning#migration-state-mirror-backfill) ou supprimer le répertoire s'il est réellement orphelin.

Le miroir `.interim/state/<guid>/.rediacc.json` est un petit fichier annexe écrit **en dehors** du volume chiffré LUKS, de sorte que les outils de sauvegarde et `repo list` peuvent lire la lignée des forks sans déverrouiller chaque image. Il a la même structure que le `.rediacc.json` dans le volume (`is_fork`, `grand_guid`, `name`, etc.) et est actualisé à chaque `Repository.SaveState`. C'est-à-dire à chaque montage et à chaque mutation d'état. C'est la source de vérité pour la détection de forks dans les sauvegardes planifiées : un fork non monté avec un miroir qui dit `is_fork: true` est correctement ignoré des uploads `cold` et `hot`.

Pour le nettoyage régulier des entrées unknown, voir [`rdc machine prune --prune-unknown`](/fr/docs/pruning#phase-3---prune-unknown-surgical).

## Redimensionner

Définir le dépôt à une taille exacte ou l'agrandir d'une quantité donnée :

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Définir à une taille exacte
rdc repo expand --name my-app -m server-1 --size 5G  # Ajouter 5G à la taille actuelle
```

> Le dépôt doit être démonté avant le redimensionnement.

## Fork

Créer une copie d'un dépôt existant à son état actuel :

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Les forks utilisent le modèle name:tag : le fork résultant est nommé `my-app:staging`. Cela crée une nouvelle copie chiffrée avec son propre GUID et ID réseau, tout en partageant le nom du parent. Le fork partage le même credential LUKS que le parent.

> Les forks partagent les données du parent via reflink BTRFS, y compris tous les credentials stockés sur le disque. Voir [Ce que Rediacc n'isole pas](/fr/docs/ai-agents-safety#what-rediacc-does-not-isolate) pour les implications quand ces credentials autorisent des services externes comme Stripe, AWS ou Railway. Pour garder les credentials de déploiement hors de la portée du fork, utilisez [les secrets par dépôt](#secrets) plutôt que d'intégrer les valeurs dans les fichiers `.env` du dépôt.

À la création du fork, `repo fork` écrit le [fichier annexe du miroir d'état](#colonne-type-et-miroir-détat) à `<datastore>/.interim/state/<fork-guid>/.rediacc.json` immédiatement. Sans déverrouiller le volume. De sorte que le nouveau fork est correctement identifié comme `is_fork: true` dès le moment de sa création. Cela permet aux sauvegardes planifiées de l'ignorer (les forks sont exclus du pipeline d'upload par défaut) même s'il n'est jamais monté. Lors du fork d'un fork, `grand_guid` s'enchaîne correctement : le miroir du nouveau fork pointe vers le GUID du grand-parent original, pas vers le fork intermédiaire.

## Gestion de versions à la manière de git

Les forks peuvent jouer le rôle de commits git. `rdc repo commit` gèle un fork de travail en un commit immuable et stable en octets ; `rdc repo branch` nomme une ligne d'historique ; `rdc repo checkout` clone par reflink un commit dans un nouveau fork de travail modifiable ; `rdc repo log` parcourt la chaîne de parents ; et `rdc repo merge` combine deux lignes sans muter un dépôt actif en place. `rdc repo fork --immutable` produit en une seule étape une base équivalente à un commit.

```bash
rdc repo commit --name my-app:work --message "schéma migré" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Voir la [référence du branchement à la manière de git](/fr/docs/repo-branching) pour l'ensemble des commandes, les options et les exemples travaillés.

## Secrets

Les secrets par dépôt sont des credentials de déploiement injectés dans les conteneurs sans être écrits dans l'image du dépôt chiffré. Ils sont conservés sur un plan séparé des données du dépôt, de sorte que `rdc repo fork` ne les propage pas. Un fork commence avec une map de secrets vide et ses conteneurs démarrent en s'identifiant comme un principal externe différent du parent.

> Vous voulez une procédure pas à pas ? Consultez le [tutoriel de gestion des secrets](/fr/docs/tutorial-managing-secrets) pour le cycle complet set/list/deploy/verify/rotate.

**Modèle d'écriture seule (style GitHub) :** `get` retourne uniquement le digest SHA-256. La valeur en texte brut n'est jamais retournée à personne, humain ou agent. Si vous oubliez quelle est une valeur, cherchez-la dans votre gestionnaire de mots de passe et effectuez une rotation ; vous ne pouvez pas la relire depuis Rediacc par conception. Cela élimine toute une classe de fuite : enregistrements de terminal, historique shell, redirection accidentelle, coup d'oeil.

Deux modes de livraison :

- `env`. Le secret est exporté comme `REDIACC_SECRET_<KEY>` dans le shell renet sur la machine cible. Référencez-le depuis votre `docker-compose.yml` via l'interpolation `${REDIACC_SECRET_<KEY>}`. Visible à l'intérieur de l'environnement du conteneur, utilisez ceci pour les valeurs en forme de chaîne de connexion que l'application attend déjà dans env.
- `file`. Le secret est écrit à `/var/run/rediacc/secrets/<networkID>/<KEY>` sur l'hôte (tmpfs, jamais persisté). Référencez-le depuis votre fichier compose via une déclaration `secrets:` de haut niveau avec source `file:`, plus une liste `secrets:` par service. Les conteneurs lisent depuis `/run/secrets/<key>`. Préférez ce mode pour tout ce qui est sensible. Il n'apparaît jamais dans `docker inspect` ou `/proc/<pid>/environ`.

```bash
# Définir, lister, obtenir (digest uniquement), supprimer
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — pas de valeur
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Portail de mutation symétrique.** Les humains et les agents ont besoin de `--current <previous-value>` pour écraser ou supprimer un secret (condition préalable de type passwd). Pour la première écriture d'une nouvelle clé, passez `--current ""` (vide). Pour effectuer une rotation sans vérifier la valeur antérieure, passez `--rotate-secret` à la place. Ceci est fortement audité comme une rotation. `--current` et `--rotate-secret` s'excluent mutuellement.

Passez `--value -` pour lire depuis stdin au lieu de argv (évite l'exposition de l'historique shell pour les écritures uniques).

Dans votre `docker-compose.yml` :

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

La référence côté service en minuscules (`stripe_live_key`) est le nom de fichier `/run/secrets/<name>` dans le conteneur ; la fin en majuscules du chemin hôte (`STRIPE_LIVE_KEY`) correspond à ce que vous définissez avec `--key`. `${REDIACC_NETWORK_ID}` est interpolé automatiquement par `renet compose`.

> **Isolation cross-repo appliquée** : le validateur compose de renet rejette les chemins `secrets: file:` (et `configs: file:`, et `env_file:`) qui référencent l'ID réseau d'un autre dépôt. Le token littéral `${REDIACC_NETWORK_ID}` (ou l'entier de votre réseau) est la seule forme acceptée pour les références `/var/run/rediacc/secrets/...`. Et `--unsafe` ne remplace PAS ce contrôle. Le bac à sable Landlock autour du sous-processus bash Rediaccfile limite également l'accès au système de fichiers uniquement à votre répertoire de secrets du réseau, de sorte qu'une `cat /var/run/rediacc/secrets/<other>/X` malveillante depuis un Rediaccfile échoue avec EACCES au niveau du noyau.

> **Forks** : `rdc repo fork` **ne copie pas** les secrets. Pour utiliser les secrets dans un fork, exécutez `rdc repo secret set --name <fork>` sur le fork explicitement. C'est la propriété de sécurité essentielle. Les conteneurs du fork ne doivent pas pouvoir agir comme le principal de production envers les services externes.

> **Agents** (Claude Code, Cursor, etc.) : `repo secret list` et `repo secret get` sont exposés comme outils MCP (lecture-sûr. Noms + digests uniquement, jamais de valeurs). `set` et `unset` sont CLI-only car la cérémonie `--current`/`--rotate-secret` nécessite une surveillance humaine ; les agents les appelant via shell obtiennent le même portail que les humains. Quand la condition préalable échoue, l'enveloppe JSON contient un champ structuré `errors[].next.options[].run`. Les agents doivent relayer ces commandes verbatim à l'utilisateur. Voir [sécurité des agents AI](/fr/docs/ai-agents-safety) pour le modèle complet.

## Valider

Vérifier l'intégrité du système de fichiers d'un dépôt :

```bash
rdc repo validate --name my-app -m server-1
```

## Propriété

Définir la propriété des fichiers dans un dépôt à l'utilisateur universel (UID 7111). Ceci est généralement nécessaire après avoir téléchargé des fichiers depuis votre station de travail, qui arrivent avec votre UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

La commande détecte automatiquement les répertoires de données des conteneurs Docker (montages bind inscriptibles) et les exclut. Cela évite de casser les conteneurs qui gèrent les fichiers avec leurs propres UIDs (par ex. MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Définir un UID personnalisé au lieu de 7111 |
| `--skip-router-restart` | Ignorer le redémarrage du serveur de routage après l'opération |

Pour forcer la propriété sur tous les fichiers, y compris les données du conteneur :

```bash
rdc repo ownership --name my-app -m server-1
```

Consultez le [Guide de migration](/fr/docs/migration) pour une procédure complète de quand et comment utiliser la propriété lors de la migration de projet.

## Modèle

Appliquer un modèle pour initialiser un dépôt avec des fichiers :

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Supprimer

Détruire de manière permanente un dépôt et toutes les données qu'il contient :

```bash
rdc repo delete --name my-app -m server-1
```

> Cela détruit définitivement l'image disque chiffrée. Cette action ne peut pas être annulée.

## Migrer un dépôt

Migrer en direct un dépôt d'une machine à une autre. Le seul temps d'arrêt est la phase de synchronisation delta finale : généralement quelques secondes à quelques minutes selon le taux d'écriture au moment du basculement.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--provision` | Provisionner le dépôt sur la machine cible avant la migration (crée l'image LUKS et enregistre la config) |
| `--checkpoint` | Créer un point de contrôle CRIU des conteneurs en cours d'exécution avant le basculement |
| `--bwlimit <kbps>` | Limiter la bande passante rsync en kilooctets par seconde |
| `--skip-dns` | Ignorer la mise à jour des enregistrements DNS après le basculement |

**Flux en trois phases :**

1. **Pré-copie en direct** - rsync transfère les données tandis que le dépôt reste en cours d'exécution sur la source. Les fichiers volumineux sont transférés avant tout temps d'arrêt.
2. **Basculement** - le dépôt est arrêté sur la source, une dernière passe rsync synchronise les modifications restantes, et le dépôt démarre sur la cible.
3. **Démarrer sur la cible** - renet monte et démarre le dépôt sur la machine cible. Le DNS est mis à jour sauf si `--skip-dns` est passé.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrate :**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Opération | Copier | Déplacer |
| Source après | Inchangée | Arrêtée |
| Temps d'arrêt | Aucun (copie uniquement) | Fenêtre de basculement brève |
| Mise à jour DNS | Non | Oui (sauf `--skip-dns`) |
| Cas d'utilisation | Sauvegarde, clone de staging | Remplacement de machine, déplacement de serveur |

## Élaguer

Après suppression de dépôts ou récupération d'opérations échouées, des répertoires de montage orphelins, des fichiers de verrouillage et des marqueurs immobiles peuvent rester. L'élagage les supprime de manière sûre :

```bash
# Aperçu de ce qui serait supprimé
rdc machine prune --name server-1 --dry-run

# Supprimer les ressources orphelines
rdc machine prune --name server-1
```

Seules les ressources sans image de dépôt correspondante sont affectées. Les répertoires de montage non vides ne sont jamais supprimés.
