---
title: "Installation"
description: "Installez le CLI rdc sur votre ordinateur en une seule commande et vérifiez-le avec rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: fr
sourceHash: "99d4ca1a4f89278e"
---

# Installation

L'installation de `rdc` se fait en trois étapes : ouvrez la page d'installation, choisissez votre système d'exploitation, collez la commande dans votre terminal. L'ensemble se termine généralement en une minute ou deux.

## Regarder le tutoriel

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Les trois étapes

![Aperçu des trois étapes](/img/tutorials/tutorial-installation/slide-1.svg)

1. Ouvrez la [page d'installation](/en/install).
2. Choisissez votre système d'exploitation.
3. Copiez la commande d'installation et collez-la dans votre terminal.

## Installer sur votre plateforme

La page d'installation génère la bonne commande pour vous, mais voici les commandes canoniques en une ligne.

**Linux / macOS :**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell) :**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> Le préfixe `time` est une astuce shell qui affiche la durée d'exécution d'une commande. Nous l'utilisons tout au long de cette série pour que vous puissiez voir la vitesse réelle de chaque étape. Il est facultatif. Supprimez-le si vous ne le souhaitez pas.

## Vérifier l'installation

Une fois le script terminé, vérifiez que tout ce dont `rdc` a besoin est présent :

```bash
time rdc doctor
```

`rdc doctor` parcourt Node, SSH et le reste des dépendances de `rdc`, puis signale les éventuels manques.

## Pourquoi `rdc` réside sur votre ordinateur

![rdc sur votre ordinateur, renet sur le serveur](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` est le CLI sur votre ordinateur. Le serveur exécute un composant distinct appelé `renet`, que `rdc` provisionne et pilote via SSH. Vous n'avez jamais besoin de vous connecter manuellement à un serveur en SSH. `rdc` le fait pour vous.

Nous configurerons cela correctement dans les deux prochains tutoriels.

---

Suivant : [Configuration des clés SSH](/en/docs/tutorial-ssh-keys).
