---
title: rdc vs renet
description: Différences entre rdc et renet, et à quel moment utiliser chacun de ces éléments.
category: Concepts
order: 1
language: fr
sourceHash: 0396eec8815a0b4e
---

# rdc vs renet

Rediacc possède deux binaires. Voici quand utiliser chacun d'entre eux.

| | rdc | renet |
|---|-----|-------|
| **S'exécute sur** | Votre poste de travail | Le serveur distant |
| **Se connecte via** | SSH | S'exécute localement avec les droits root |
| **Utilisé par** | Tout le monde | Débogage avancé uniquement |
| **Installation** | Vous l'installez | `rdc` le provisionne automatiquement |

> Pour le travail quotidien, utilisez `rdc`. Vous avez rarement besoin de `renet` directement.

## Comment ils fonctionnent ensemble

`rdc` se connecte à votre serveur via SSH et exécute les commandes `renet` à votre place. Vous tapez une seule commande sur votre poste de travail, et `rdc` gère le reste :

1. Lit votre configuration locale (`~/.rediacc/config.json`)
2. Se connecte au serveur via SSH
3. Met à jour le binaire `renet` si nécessaire
4. Exécute l'opération `renet` correspondante sur le serveur
5. Renvoie le résultat à votre terminal

## Utiliser `rdc` pour le travail courant

Toutes les tâches courantes passent par `rdc` sur votre poste de travail :

```bash
# Configurer un nouveau serveur
rdc context setup-machine server-1

# Créer et démarrer un dépôt
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Arrêter un dépôt
rdc repo down my-app -m server-1

# Vérifier la santé de la machine
rdc machine health server-1
```

Consultez le [Démarrage rapide](/fr/docs/quick-start) pour un guide complet.

## Utiliser `renet` pour le débogage côté serveur

Vous n'avez besoin de `renet` directement que lorsque vous vous connectez en SSH à un serveur pour :

- Le débogage d'urgence lorsque `rdc` ne peut pas se connecter
- La vérification d'éléments internes du système non disponibles via `rdc`
- Les opérations de récupération de bas niveau

Toutes les commandes `renet` nécessitent les privilèges root (`sudo`). Consultez la [Référence serveur](/fr/docs/server-reference) pour la liste complète des commandes `renet`.

## Expérimental : `rdc ops` (VM locales)

`rdc ops` encapsule `renet ops` pour gérer des clusters de VM locaux sur votre poste de travail :

```bash
rdc ops setup       # Installer les prérequis (KVM ou QEMU)
rdc ops up --basic  # Démarrer un cluster minimal
rdc ops status      # Vérifier l'état des VM
rdc ops ssh 1       # Se connecter en SSH à la VM bridge
rdc ops down        # Détruire le cluster
```

Ces commandes exécutent `renet` localement (pas via SSH). Consultez [VM expérimentales](/fr/docs/experimental-vms) pour la documentation complète.

## Note sur le Rediaccfile

Vous pouvez voir `renet compose -- ...` à l'intérieur d'un `Rediaccfile`. C'est normal — les fonctions du Rediaccfile s'exécutent sur le serveur où `renet` est disponible.

Depuis votre poste de travail, démarrez et arrêtez les charges de travail avec `rdc repo up` et `rdc repo down`.
