---
title: "Gérer les secrets"
description: "Placez vos identifiants de déploiement dans un endroit inaccessible aux forks. En écriture seule par conception."
category: "Tutorials"
subcategory: advanced
order: 8
language: fr
sourceHash: "0b4d72c80b489e12"
---

# Gérer les secrets

Les vraies applications ont besoin de vrais identifiants : une clé Stripe de production, un mot de passe de base de données, un token API. Le mauvais endroit pour les placer est dans le dépôt, car un fork hérite de tout ce qui se trouve dans l'image chiffrée. Soudain, votre sandbox facture de vrais clients.

Le bon endroit est `rdc repo secret`. Deux modes de livraison, en écriture seule par conception, et le fork démarre avec rien.

## Regarder le tutoriel

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## Le piège : `.env` dans le dépôt

![Un fichier .env dans l'image du dépôt est cloné par chaque fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

La plupart des équipes mettent `.env` dans le dépôt. C'est le geste évident.

Puis elles forkent.

Le fork est une copie octet par octet de l'image du parent. Ce qui se trouve dans `.env` se retrouve dans le `.env` du fork. Les conteneurs du fork démarrent. Ils lisent la même clé Stripe. Ils appellent la même API Stripe avec les identifiants de production. Du côté de Stripe, cet appel, c'est *vous*.

C'est une mauvaise journée.

## Définir un secret

La solution est `rdc repo secret`. Définissez-en un en mode `env`. La valeur atterrit comme variable d'environnement dans le conteneur :

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Deux choses à noter :

- `--mode env`. La valeur atterrit comme variable d'environnement.
- `--current ""`. Chaîne vide. Nous déclarons qu'il s'agit d'un tout nouveau secret sans valeur antérieure.

Définissez-en un autre, en mode `file`, pour tout ce qui est sensible :

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

Le mode `file` ne place jamais la valeur dans l'environnement du conteneur. Il l'écrit à `/run/secrets/stripe_key` à la place, en utilisant le mécanisme standard de Docker.

Listez ce que vous avez :

```bash
time rdc repo secret list --name my-app
```

Vous voyez les noms et les modes. **Aucune valeur.** La liste n'affiche jamais les valeurs.

## L'intégrer dans compose

Ouvrez `docker-compose.yml`. Référencez les deux modes :

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

`${REDIACC_SECRET_DB_HOST}` est le mode `env` : le wrapper compose de `renet` le développe depuis votre store de secrets au moment du déploiement.

Le bloc `secrets:` est le mode `file`, utilisant le mécanisme standard de Docker. Le chemin hôte utilise `${REDIACC_NETWORK_ID}` pour que le même compose fonctionne pour les parents et les forks. Chaque fork a son propre identifiant réseau.

Déployez :

```bash
time rdc repo up --name my-app -m my-server
```

## Vérifier dans le conteneur

Les deux modes devraient maintenant être dans le conteneur. Vérifiez le secret en mode env :

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. Le secret en mode env a atteint l'environnement du conteneur.

Maintenant celui en mode file :

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. Le fichier est monté via le mécanisme de secrets standard de Docker.

## Vous ne pouvez jamais le relire

![Modèle en écriture seule : get retourne un digest, jamais la valeur](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Maintenant, la partie qui surprend tout le monde :

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Vous obtenez un digest. **Pas la valeur.** Il n'y a pas de flag qui le fait retourner la valeur. Il n'y a aucune commande qui vous donnera le texte en clair.

C'est le modèle GitHub Actions : en écriture seule. Vous pouvez prouver que vous connaissez un secret en passant `--current <valeur>` et en observant la précondition réussir. Vous ne pouvez pas demander à Rediacc de vous dire ce que c'est.

Perdu la valeur ? **Ne regardez pas. Faites une rotation.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` ignore la précondition. Le journal d'audit marque l'opération comme une rotation : explicite, délibérée.

Si vous vous souvenez de l'ancienne valeur, prouvez-le plutôt :

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

C'est la voie la plus sûre. Elle détecte l'erreur "je suis dans le mauvais terminal".

## La révélation du fork

![Après le fork, la liste des secrets est vide](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Vous souvenez-vous du piège ? Forkez le dépôt et regardez :

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Vide.**

Le fork n'a pas de clé Stripe. Pas de mot de passe de base de données. Pas de token API. Les conteneurs du fork ne peuvent pas interpoler `${REDIACC_SECRET_STRIPE_KEY}`. Le fichier à `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` n'existe pas.

Le fork ne peut pas se faire passer pour vous.

Si vous voulez des secrets dans le fork pour les tests, définissez-les explicitement sur le fork avec des valeurs sandbox :

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Maintenant le fork parle au sandbox Stripe. Les identifiants de production n'ont jamais quitté la production.

## Résumé

- `rdc repo secret` place vos identifiants en dehors de l'image du dépôt.
- Le fork ne peut pas y accéder.
- `get` retourne un digest, jamais la valeur.
- Faites une rotation si vous oubliez. Ne regardez pas.

Des secrets que le fork ne peut pas suivre.

---

Suivant : [Réseau et domaines](/en/docs/tutorial-networking).
