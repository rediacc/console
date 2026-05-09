---
title: "Configuration des clés SSH"
description: "Configurez votre clé SSH pour que rdc puisse se connecter à vos serveurs sans mot de passe."
category: "Tutorials"
subcategory: essentials
order: 2
language: fr
sourceHash: "009a1bd345e93413"
---

# Configuration des clés SSH

`rdc` se connecte à vos serveurs via SSH, donc chaque serveur doit faire confiance à votre clé SSH. Trois étapes au total. Deux sont à effectuer une seule fois, et une se répète pour chaque nouveau serveur que vous ajoutez.

## Regarder le tutoriel

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## Les trois étapes

![Générer, copier, enregistrer](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Générer** une clé SSH sur votre ordinateur. Une seule fois, définitivement.
2. **Copier** la clé sur votre serveur. À répéter pour chaque nouveau serveur.
3. **Enregistrer** la clé auprès de `rdc`. Une seule fois, définitivement.

## Étape 1 : Générer une clé

Si vous avez déjà une clé que vous souhaitez utiliser, passez à l'étape suivante. Sinon :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` est le standard moderne : compact, rapide et bien supporté.

## Étape 2 : La copier sur votre serveur

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Remplacez `user` et `your-server-ip` par l'utilisateur SSH et l'adresse IP de votre serveur. Vous serez invité à saisir votre mot de passe de serveur une dernière fois. Après cela, l'authentification par mot de passe n'est plus nécessaire.

## Étape 3 : Enregistrer la clé auprès de `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

C'est tout. Désormais, chaque commande `rdc` s'authentifie avec cette clé. Plus de mots de passe, plus d'invites interactives.

---

Suivant : [Ajouter votre premier serveur](/en/docs/tutorial-add-server).
