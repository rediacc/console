---
title: "Déployer votre première application"
description: "Déployez une application conteneurisée à partir d'un modèle intégré en utilisant renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: fr
sourceHash: "f75b5b6a716e94bf"
---

# Déployer votre première application

Vous avez un dépôt vide. `rdc` est livré avec des modèles intégrés pour vous permettre de lancer de vraies applications sans écrire un `docker-compose` from scratch. Trois étapes : choisir un modèle, l'appliquer, l'exécuter.

## Regarder le tutoriel

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Choisir, appliquer, exécuter

![Choisir un modèle, l'appliquer, l'exécuter](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Étape 1 : Choisir

Parcourez les modèles disponibles :

```bash
time rdc repo template list
```

Vous verrez des configurations prêtes à l'emploi pour les applications courantes : Postgres, Redis, serveurs web, et bien d'autres.

## Étape 2 : Appliquer

Déposez le modèle dans votre dépôt. Nous utiliserons `app-postgres` :

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Deux nouveaux fichiers apparaissent dans le dépôt : `docker-compose.yml` et `Rediaccfile`. Le fichier compose décrit les conteneurs ; le `Rediaccfile` définit ce qui se passe au démarrage et à l'arrêt de l'application (ses hooks de cycle de vie `up` et `down`).

## Étape 3 : Exécuter

Vous êtes déjà à l'intérieur du sandbox du dépôt (via la connexion VS Code du tutoriel précédent), donc utilisez `renet` directement :

```bash
time renet dev up
```

C'est tout. Votre application est en cours d'exécution. Vérifiez-le :

```bash
time docker ps
```

`docker ps` liste ici uniquement les conteneurs de ce dépôt. Les autres dépôts sur le même serveur ont leurs propres daemons Docker et sont complètement invisibles depuis celui-ci.

---

Suivant : [Travailler avec votre dépôt](/en/docs/tutorial-work-with-repo).
