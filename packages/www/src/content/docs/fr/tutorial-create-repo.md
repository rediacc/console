---
title: "Créer votre premier dépôt"
description: "Créez un dépôt chiffré sur votre serveur et ouvrez-le dans VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: fr
sourceHash: "1294b0494f20671b"
---

# Créer votre premier dépôt

Un dépôt Rediacc est un fichier chiffré unique sur votre serveur. Une fois monté, il devient un dossier avec son propre daemon Docker et ses propres données d'application : complètement isolé, complètement portable.

Pensez-y comme une clé USB pour la production : un fichier au repos, un serveur en exécution.

## Regarder le tutoriel

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## Fichier sur disque, environnement une fois monté

![Un fichier chiffré se monte en dossier isolé](/img/tutorials/tutorial-create-repo/slide-1.svg)

La forme sur disque est une image chiffrée unique. Une fois montée, vous obtenez :

- Un daemon Docker dédié (distinct de celui de l'hôte)
- Les données d'application à l'intérieur du volume chiffré
- Des adresses IP loopback qui n'entrent pas en conflit avec quoi que ce soit d'autre sur la machine

Les dépôts sont portables. Vous pouvez en déplacer un entre machines, le sauvegarder ou en faire un fork instantanément. Chaque dépôt est isolé de tous les autres sur le même serveur.

## En créer un

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Cela crée un dépôt chiffré de 2 Go sur `my-server`. Vérifiez-le :

```bash
time rdc repo list -m my-server
```

## L'ouvrir dans VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code s'ouvre directement à l'intérieur du dépôt. Notez que l'espace de travail est vide. C'est votre environnement isolé. Tout ce que vous créez ici vit dans le volume chiffré, invisible pour tout autre dépôt sur le même serveur.

---

Suivant : [Déployer votre première application](/en/docs/tutorial-deploy-app).
