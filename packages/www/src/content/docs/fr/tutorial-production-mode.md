---
title: "Mode production"
description: "Exécutez votre application indépendamment de votre ordinateur et survivez aux redémarrages du serveur avec le démarrage automatique."
category: "Tutorials"
subcategory: advanced
order: 10
language: fr
sourceHash: "0e070fcd877900ab"
---

# Mode production

Jusqu'à présent, vous avez exécuté l'application avec `renet dev up` depuis l'intérieur du dépôt. C'est parfait pour le développement. Pour la production, vous gérez tout depuis votre ordinateur avec `rdc`. Fermez votre ordinateur et l'application continue de tourner.

## Regarder le tutoriel

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Dev versus prod

La différence est simple :

- `renet dev up` s'exécute **à l'intérieur du dépôt**. Vous devez être connecté.
- `rdc repo up` s'exécute **depuis votre ordinateur**. Aucune connexion n'est nécessaire après cela.

Trois actions vous font passer du dev à la prod :

![Arrêter, démarrer, démarrage automatique](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Étape 1 : Arrêter la session de développement

Connectez-vous au dépôt et arrêtez-le :

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Étape 2 : Démarrer en mode production

Depuis le terminal de votre ordinateur :

```bash
time rdc repo up --name my-app -m my-server
```

C'est tout. Votre application tourne, et vous pouvez fermer votre ordinateur. Le `Rediaccfile` gère tout. `rdc repo up` appelle la même fonction `up` que `renet dev up`. Même `Rediaccfile`, façon différente de l'invoquer.

## Étape 3 : Survivre aux redémarrages du serveur

Assurez-vous que votre application revient automatiquement quand le serveur redémarre :

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Vérifiez quels dépôts ont le démarrage automatique activé :

```bash
time rdc repo autostart list -m my-server
```

## Arrêter en production

Quand vous devez arrêter votre application :

```bash
time rdc repo down --name my-app -m my-server
```

Une commande pour démarrer, une commande pour arrêter. Tout depuis votre ordinateur.

---

Suivant : [Sauvegarde et restauration](/en/docs/tutorial-backup-restore).
