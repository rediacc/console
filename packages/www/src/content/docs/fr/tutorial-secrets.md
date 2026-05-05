---
title: "Gestion des secrets"
description: "Définir des secrets par dépôt, les câbler dans compose, vérifier qu'ils atteignent le conteneur, les faire tourner et confirmer que les forks n'en héritent aucun."
category: "Tutorials"
order: 7
language: fr
sourceHash: "fb8bc967ed22fc10"
---

# Comment gérer les secrets par dépôt avec Rediacc

Les vraies applications ont besoin d'identifiants : une clé Stripe live, un mot de passe de base de données, un token d'API. Le mauvais endroit est à l'intérieur du dépôt. Un fork hérite de tout ce qui vit dans l'image chiffrée, et ses conteneurs démarrent en s'identifiant comme le parent face aux services externes. Le bon endroit est `rdc repo secret`. Les valeurs atterrissent en dehors de l'image chiffrée, donc les forks démarrent avec une carte de secrets vide.

Dans ce tutoriel, vous définissez les deux modes de secret, vous les câblez dans un fichier compose, vous vérifiez qu'ils atteignent le conteneur, vous en faites tourner un et vous confirmez qu'un fork n'hérite de rien.

## Prérequis

- La CLI `rdc` installée avec une configuration initialisée
- Une machine provisionnée et un dépôt créé (voir [Tutoriel : Cycle de vie du dépôt](/fr/docs/tutorial-repos))
- Un `Rediaccfile` et un `docker-compose.yml` que vous pouvez modifier

## Étape 1 : Définir un secret

Deux modes de livraison sont disponibles. `env` exporte la valeur en tant que `REDIACC_SECRET_<KEY>` pour l'interpolation `${...}` de compose. `file` écrit la valeur dans un fichier tmpfs côté hôte à `/var/run/rediacc/secrets/<networkID>/<KEY>` pour utilisation avec le bloc `secrets:` de Docker compose. Utilisez `file` pour tout ce qui est sensible. Les valeurs en mode env apparaissent dans `docker inspect` et dans `/proc/<pid>/environ`.

Pour la première écriture d'une clé toute nouvelle, passez `--current ""` (vide) pour reconnaître qu'il n'y a pas de valeur précédente.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Étape 2 : Lister ce qui est là

```bash
rdc repo secret list --name my-app
```

La sortie est JSON avec le nom et le mode de chaque secret. Les valeurs n'apparaissent jamais dans le listage. Elles ne sont même pas récupérées du disque.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Étape 3 : Câbler dans compose

Les deux modes sont référencés depuis le même `docker-compose.yml` :

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

Le `stripe_key` en minuscules sur le service est le nom de fichier `/run/secrets/<name>` dans le conteneur. Le `STRIPE_KEY` en majuscules dans le chemin hôte correspond au `--key` que vous avez défini. `${REDIACC_NETWORK_ID}` est interpolé automatiquement par `renet compose`. C'est important car l'ID réseau est par fork, donc le même fichier compose fonctionne dans le parent et dans tout fork (où, comme vous le verrez à l'étape 6, le fichier n'existera tout simplement pas).

> **Isolation inter-dépôts appliquée.** Le validateur compose de renet rejette tout chemin `secrets: file:` (ou `configs: file:`, ou `env_file:`) qui pointe vers l'ID réseau d'un autre dépôt. Le token littéral `${REDIACC_NETWORK_ID}` (ou l'entier de votre propre réseau) est la seule forme acceptée, et `--unsafe` ne l'annule PAS. Le bac à sable Landlock autour du sous-processus bash du Rediaccfile cadre aussi les lectures de système de fichiers vers le répertoire de secrets de votre propre réseau. Donc même un `cat /var/run/rediacc/secrets/<autre>/X` malveillant depuis un Rediaccfile échoue avec EACCES au niveau du noyau. Vous n'avez rien à activer ; la protection est active par défaut.

## Étape 4 : Déployer et vérifier

```bash
rdc repo up --name my-app -m server-1
```

Après le déploiement, exec'ez dans le conteneur pour confirmer que les deux modes sont arrivés :

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

Si vous voulez inspecter directement le fichier tmpfs côté hôte :

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Étape 5 : Faire tourner sans connaître la valeur précédente

Vous pouvez lire un digest avec `rdc repo secret get`, mais jamais la valeur en clair. C'est le modèle write-only. Si vous devez vérifier qu'une valeur stockée correspond à ce que vous avez, passez-la via `--current` et regardez la précondition passer ou échouer :

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

Si vous avez complètement oublié la valeur précédente (votre gestionnaire de mots de passe l'a perdue ou vous avez hérité du dépôt), utilisez `--rotate-secret` pour ignorer la précondition. Le journal d'audit enregistre cela fortement comme une rotation :

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` et `--rotate-secret` sont mutuellement exclusifs. Choisissez l'un.

## Étape 6 : Confirmer que les forks n'héritent de rien

Le but principal : forkez le dépôt et vérifiez la liste de secrets du fork :

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Vide. Les conteneurs du fork ne peuvent pas interpoler `${REDIACC_SECRET_DB_HOST}` (la variable n'est pas définie, donc chaîne vide), et le fichier à `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` n'existe simplement pas. Si le `repo up` du fork essaie de le monter via le bloc `secrets:` de compose, le déploiement échouera avec une erreur claire. Exactement le mode d'échec que vous voulez, car cela signifie que le bac à sable ne peut pas se faire passer pour la production face aux services externes.

Pour utiliser des secrets dans le fork, définissez-les explicitement sur le fork avec des valeurs limitées au bac à sable :

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Maintenant le fork parle à une base de données de test et à un compte sandbox Stripe. Les identifiants de production du parent ne quittent jamais le parent.

## Nettoyage

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## Voir aussi

- [Dépôts § Secrets](/fr/docs/repositories#secrets). La référence complète
- [Aide-mémoire CLI RDC § Secrets par dépôt](/fr/docs/rdc-cheat-sheet#per-repo-secrets). Référence rapide des commandes
- [Sécurité des agents IA](/fr/docs/ai-agents-safety). Le gate de mutation symétrique et les indices d'action `next` structurés dans les enveloppes d'erreur
- [Services § Utiliser des secrets par dépôt dans compose](/fr/docs/services#using-per-repo-secrets-in-compose). Référence du modèle compose
