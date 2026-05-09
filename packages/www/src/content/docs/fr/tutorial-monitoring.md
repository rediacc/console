---
title: "Surveillance"
description: "Vérifiez l'état de santé de vos serveurs et dépôts depuis votre ordinateur avec les commandes rdc machine."
category: "Tutorials"
subcategory: advanced
order: 12
language: fr
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Surveillance

Votre application est déployée, en production et sauvegardée. Assurez-vous maintenant que tout reste en bonne santé. `rdc` vous donne une vue complète de n'importe quel serveur (état, conteneurs, dépôts) depuis votre ordinateur.

## Regarder le tutoriel

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Trois choses à vérifier

![État, conteneurs, dépôts](/img/tutorials/tutorial-monitoring/slide-1.svg)

## État : informations système

Commencez par la vue système :

```bash
time rdc machine query --name my-server --system
```

Cela affiche le temps de fonctionnement du système, l'utilisation du disque et l'état du stockage. Si quelque chose ne va pas, il vous le dit.

## Conteneurs

Pour voir tous les conteneurs en cours d'exécution sur tous les dépôts de la machine :

```bash
time rdc machine query --name my-server --containers
```

Vous obtenez le nom, le statut, l'état de santé, le CPU et la mémoire de chaque conteneur, ainsi que le dépôt auquel il appartient.

## Dépôts

Pour vérifier vos dépôts :

```bash
time rdc machine query --name my-server --repositories
```

Cela affiche chaque dépôt avec sa taille, son état de montage, l'état du daemon Docker et l'utilisation du disque.

## Tout en une seule commande

```bash
time rdc machine query --name my-server
```

Informations système, dépôts, conteneurs, tout en une seule commande. Sans filtre, `query` retourne le tableau complet ; ajoutez `--system`, `--containers`, `--repositories`, `--services`, `--network` ou `--block-devices` pour cibler une rubrique précise.

## Vérification locale

`rdc doctor` vérifie votre configuration locale (Node, clé SSH, `renet`, Docker), indépendamment de tout serveur spécifique :

```bash
time rdc doctor
```

## Vous avez terminé

C'est la série complète. Vous pouvez maintenant installer, configurer, déployer, forker, mettre en production, activer le démarrage automatique, sauvegarder et surveiller. Tout depuis votre terminal, tout sur vos propres serveurs.
