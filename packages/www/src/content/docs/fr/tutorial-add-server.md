---
title: "Ajouter votre première machine"
description: "Enregistrez votre première machine avec rdc, préparez-la et découvrez l'architecture rdc et renet."
category: "Tutorials"
subcategory: essentials
order: 3
language: fr
sourceHash: "2b5de59f61cfb88c"
---

# Ajouter votre premier serveur

Avant d'ajouter un serveur, il est utile de comprendre comment `rdc` fonctionne. Rediacc repose sur une architecture à deux outils : `rdc` sur votre ordinateur, `renet` sur le serveur.

## Regarder le tutoriel

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## Pourquoi deux outils ?

![rdc sur l'ordinateur, renet sur le serveur, SSH entre les deux](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** est le CLI sur votre ordinateur. Vous saisissez les commandes ici.
- **`renet`** est l'orchestrateur sur le serveur. Il gère le chiffrement, Docker et l'isolation.

Lorsque vous exécutez une commande localement, `rdc` se connecte via SSH et exécute `renet` sur le serveur. Vous n'avez jamais besoin de vous connecter manuellement à vos serveurs en SSH. `rdc` le fait pour vous.

## Étape 1 : Enregistrer le serveur

Indiquez à `rdc` les informations du serveur. Remplacez le nom, l'adresse IP et l'utilisateur par les vôtres.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Étape 2 : Le provisionner

La configuration installe `renet` et crée le datastore chiffré sur le serveur.

```bash
time rdc config machine setup --name my-server
```

Une fois terminé, votre serveur est prêt à héberger des dépôts.

## Où se trouve la configuration

Vérifiez ce que `rdc` sait de votre configuration :

```bash
time rdc config show
```

Ou ouvrez directement le fichier JSON brut :

```bash
vim ~/.config/rediacc/rediacc.json
```

Ce fichier unique contient tout : machines, dépôts, clé SSH, identifiants de chiffrement. Copiez-le sur un autre ordinateur et vous êtes prêt à travailler depuis cette machine également.

---

Suivant : [Créer votre premier dépôt](/en/docs/tutorial-create-repo).
