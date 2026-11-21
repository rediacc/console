---
title: "Canaux de publication"
description: "Comment Edge et Stable diffèrent, et quel canal utiliser."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: fr
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc livre les mises à jour de la CLI via deux canaux : **Stable** et **Edge**. Les deux se connectent au même produit : le compte, le plan et les limites sont donc identiques sur l'un comme sur l'autre. Les canaux ne diffèrent que par la rapidité avec laquelle une version vous parvient.

## Canal Stable

Stable est le canal par défaut. Une version ne l'atteint qu'après avoir séjourné 7 jours sur Edge sans incident signalé.

- Recommandé lorsque vous préférez une cadence de mise à jour conservatrice
- Déployé après 7 jours de tests sur Edge
- Les correctifs critiques peuvent être poussés directement

## Canal Edge

Edge récupère chaque modification dès sa fusion dans la branche principale. C'est la version live du logiciel, déployée en continu.

- Publié à chaque fusion dans main
- Mêmes comptes, plans et limites que Stable
- Idéal pour essayer les nouveautés en avance

## Un produit, deux canaux

Votre compte vit dans votre région de données, sur `eu.rediacc.cloud`, `us.rediacc.cloud` ou `asia.rediacc.cloud`, quel que soit le canal utilisé. Changer de canal ne touche ni à votre compte, ni à vos données, ni à votre abonnement. Pour les régions, consultez [Régions de données](/fr/docs/data-regions).

## Comparaison

| | Stable | Edge |
|---|---|---|
| **Cadence de déploiement** | Après stabilisation de 7 jours | À chaque fusion dans main |
| **Stabilité** | Testé pendant 7 jours | Code le plus récent, moins de stabilisation |
| **Plans et limites** | Identiques | Identiques |
| **Compte et données** | Partagés | Partagés |
| **Idéal pour** | Production, charges de travail payantes | Accès anticipé, évaluation |

## Comment fonctionnent les promotions

1. Chaque fusion dans la branche principale est déployée immédiatement sur Edge.
2. Après 7 jours sans incident, Edge est automatiquement promu vers Stable.
3. Les correctifs critiques peuvent être poussés simultanément sur les deux canaux.

Stable se trouve donc toujours au maximum à 7 jours derrière Edge. La fenêtre de stabilisation détecte les régressions sur Edge avant qu'elles n'atteignent jamais Stable.

## Quel canal choisir ?

**Choisissez Stable si :**
- Vous préférez une cadence de mise à jour conservatrice avec une fenêtre de stabilisation de 7 jours
- Vous privilégiez la fiabilité maximale sur les dernières fonctionnalités

**Choisissez Edge si :**
- Vous souhaitez tester les nouvelles fonctionnalités en avant-première
- Vous évaluez la plateforme
- Vous êtes à l'aise avec un code plus récent et moins testé

## Installation

Consultez [Installation](/fr/docs/installation) pour les commandes d'installation, la configuration du gestionnaire de paquets et les tags Docker pour chaque canal.

## Gestion du canal via la CLI

La CLI utilise le canal configuré lors de l'installation. Pour changer :

```bash
rdc update --channel edge      # Basculer vers Edge
rdc update --channel stable    # Basculer vers Stable
```
