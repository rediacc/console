---
title: "Canaux de publication"
description: "Comprendre les canaux de publication Edge et Stable, leurs différences et comment choisir."
category: "Concepts"
order: 2
language: fr
sourceHash: "d6ff18f9265392d2"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

Rediacc publie les mises à jour via deux canaux de publication : **Stable** et **Edge**. Chaque canal s'adresse à un public différent et implique des compromis distincts.

## Canal Stable

Stable est le canal par défaut pour tous les utilisateurs. Les versions sont promues depuis Edge après une période de stabilisation de 7 jours sans incident signalé.

- Recommandé lorsque vous préférez une cadence de mise à jour conservatrice et souhaitez accéder aux plans payants
- Déployé après 7 jours de tests sur Edge
- Les correctifs critiques peuvent être poussés directement
- Domaines : `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

Edge reçoit chaque modification immédiatement après sa fusion dans la branche principale. Il s'agit de la version la plus récente du logiciel, déployée en continu.

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

Les utilisateurs Edge sur le plan Community bénéficient de limites de ressources doublées sans frais supplémentaires :

| Ressource | Community Stable | Community Edge |
|---|---|---|
| Taille des dépôts | 10 Go | 20 Go |
| Émissions de licences par mois | 500 | 1 000 |
| Activations de machines | 2 | 4 |

Si vous avez besoin de limites plus élevées ou de fonctionnalités des plans payants, créez un compte sur le canal Stable et effectuez une mise à niveau depuis celui-ci.

## Comptes séparés

Edge et Stable fonctionnent sur des infrastructures séparées avec des bases de données distinctes. Un compte créé sur Edge n'existe pas sur Stable, et vice versa. Il n'existe pas de chemin de migration entre les canaux. Si vous démarrez sur Edge et souhaitez ensuite un plan payant, vous devrez créer un nouveau compte sur Stable.

## Comment fonctionnent les promotions

1. Chaque fusion dans la branche principale est déployée immédiatement sur Edge.
2. Après 7 jours sans incident, Edge est automatiquement promu vers Stable.
3. Les correctifs critiques peuvent être poussés simultanément sur les deux canaux.

Stable se trouve donc toujours au maximum à 7 jours derrière Edge. La période de stabilisation permet de détecter les régressions avant qu'elles ne soient propagées d'Edge à Stable.

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

Consultez [Installation](/fr/docs/installation) pour les commandes d'installation depuis l'un ou l'autre canal, y compris la configuration du gestionnaire de paquets et les tags Docker.

## Gestion du canal via la CLI

La CLI utilise automatiquement le canal configuré lors de l'installation ou de la connexion. Pour changer de canal :

```bash
rdc update --channel edge      # Basculer vers Edge
rdc update --channel stable    # Basculer vers Stable
```

Lorsque vous exécutez `rdc subscription login` et sélectionnez une région Edge, la CLI configure automatiquement le canal de mise à jour Edge. Aucun indicateur `--channel` manuel n'est nécessaire.
