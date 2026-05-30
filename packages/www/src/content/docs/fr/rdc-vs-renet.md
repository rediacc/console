---
title: rdc vs renet
description: >-
  Différences entre rdc et renet, et à quel moment utiliser chacun de ces
  éléments.
category: Concepts
order: 1
language: fr
sourceHash: "026a183f8a5f9dd4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
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

Sur votre poste de travail, vous exécutez `rdc`. Il ouvre une connexion SSH vers votre serveur et y exécute la commande `renet` correspondante. Une commande, un seul endroit pour l'exécuter :

1. Lit votre configuration locale (`~/.config/rediacc/rediacc.json`)
2. Se connecte au serveur via SSH
3. Met à jour le binaire `renet` si nécessaire
4. Exécute l'opération `renet` correspondante sur le serveur
5. Renvoie le résultat à votre terminal

## Utiliser `rdc` pour le travail courant

Toutes les tâches courantes passent par `rdc` sur votre poste de travail :

```bash
# Configurer un nouveau serveur
rdc config machine setup --name server-1

# Créer et démarrer un dépôt
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# Arrêter un dépôt
rdc repo down --name my-app -m server-1

# Vérifier la santé de la machine
rdc machine health --name server-1
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
rdc ops setup              # Installer les prérequis (KVM ou QEMU)
rdc ops up --basic         # Démarrer un cluster minimal
rdc ops status             # Vérifier l'état des VM
rdc ops ssh --vm-id 1  # Se connecter en SSH à la VM bridge
rdc ops ssh --vm-id 1 -c hostname  # Exécuter une commande sur la VM bridge
rdc ops down               # Détruire le cluster
```

> Nécessite l'adaptateur local. Non disponible avec l'adaptateur cloud.

Ces commandes exécutent `renet` localement (pas via SSH). Consultez [VM expérimentales](/fr/docs/experimental-vms) pour la documentation complète.

## Note sur le Rediaccfile

Vous verrez `renet compose -- ...` à l'intérieur d'un `Rediaccfile`. Ne vous inquiétez pas. Les fonctions du Rediaccfile s'exécutent sur le serveur, où `renet` est déjà installé.

Depuis votre poste de travail, démarrez et arrêtez les charges de travail avec `rdc repo up` et `rdc repo down`.
