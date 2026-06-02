---
title: "Canaux de publication"
description: "Comment Edge et Stable diffèrent, et quel canal utiliser."
category: "Concepts"
order: 2
language: fr
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc livre les mises à jour via deux canaux : **Stable** et **Edge**. Ils fonctionnent sur des infrastructures séparées et impliquent des compromis distincts.

## Canal Stable

Stable est le canal par défaut. Une version ne l'atteint qu'après avoir séjourné 7 jours sur Edge sans incident signalé.

- Recommandé lorsque vous préférez une cadence de mise à jour conservatrice et souhaitez accéder aux plans payants
- Déployé après 7 jours de tests sur Edge
- Les correctifs critiques peuvent être poussés directement
- Domaines : `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

Edge récupère chaque modification dès sa fusion dans la branche principale. C'est la version live du logiciel, déployée en continu.

- Dernières fonctionnalités et correctifs, déployés à chaque fusion
- Limites du plan Community doublées (voir tableau ci-dessous)
- Gratuit pour toujours. Aucun plan payant disponible sur Edge.
- Comptes séparés de Stable. Les données ne sont pas transférées entre les canaux.
- Domaines : `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Comparaison

| | Stable | Edge |
|---|---|---|
| **Cadence de déploiement** | Après stabilisation de 7 jours | À chaque fusion dans main |
| **Stabilité** | Testé pendant 7 jours | Code le plus récent, moins de stabilisation |
| **Limites du plan Community** | 10 Go de dépôts, 500 émissions/mois, 2 machines | 20 Go de dépôts, 1 000 émissions/mois, 4 machines |
| **Plans payants** | Disponibles (Professional, Business, Enterprise) | Non disponibles |
| **Comptes** | Indépendants | Indépendants (séparés de Stable) |
| **Idéal pour** | Production, charges payantes | Tests, évaluation, projets annexes, accès anticipé |

## Limites doublées sur Edge

Utilisez Edge sur le plan Community et vos limites de ressources doublent, sans frais supplémentaires :

| Ressource | Community Stable | Community Edge |
|---|---|---|
| Taille des dépôts | 10 Go | 20 Go |
| Émissions de licences par mois | 500 | 1 000 |
| Activations de machines | 2 | 4 |

Vous avez besoin de limites plus élevées ou de fonctionnalités payantes ? Créez votre compte sur Stable et effectuez une mise à niveau depuis là.

## Comptes séparés

Edge et Stable fonctionnent sur des infrastructures séparées avec des bases de données distinctes. Un compte sur l'un n'existe pas sur l'autre, et il n'existe pas de chemin de migration. Vous démarrez sur Edge, décidez ensuite que vous voulez un plan payant, et vous créerez un compte tout neuf sur Stable.

## Comment fonctionnent les promotions

1. Chaque fusion dans la branche principale est déployée immédiatement sur Edge.
2. Après 7 jours sans incident, Edge est automatiquement promu vers Stable.
3. Les correctifs critiques peuvent être poussés simultanément sur les deux canaux.

Stable se trouve donc toujours au maximum à 7 jours derrière Edge. La fenêtre de stabilisation détecte les régressions sur Edge avant qu'elles n'atteignent jamais Stable.

## Quel canal choisir ?

**Choisissez Stable si :**
- Vous préférez une cadence de mise à jour conservatrice avec une fenêtre de stabilisation de 7 jours
- Vous avez besoin de plans payants (Professional, Business, Enterprise)
- Vous privilégiez la fiabilité maximale sur les dernières fonctionnalités

**Choisissez Edge si :**
- Vous souhaitez tester les nouvelles fonctionnalités en avant-première
- Vous évaluez la plateforme
- Vous voulez des limites gratuites généreuses pour des projets annexes
- Vous êtes à l'aise avec un code plus récent et moins testé

## Installation

Consultez [Installation](/fr/docs/installation) pour les commandes d'installation, la configuration du gestionnaire de paquets et les tags Docker pour chaque canal.

## Gestion du canal via la CLI

La CLI utilise le canal configuré lors de l'installation ou de la connexion. Pour changer :

```bash
rdc update --channel edge      # Basculer vers Edge
rdc update --channel stable    # Basculer vers Stable
```

Exécutez `rdc subscription login` et choisissez une région Edge, et la CLI configure le canal de mise à jour Edge pour vous. Aucun indicateur `--channel` requis.
