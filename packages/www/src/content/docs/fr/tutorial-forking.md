---
title: "Forker un dépôt"
description: "Clonez un dépôt entier (application, base de données, fichiers) en quelques secondes. Toute taille. Zéro disque supplémentaire."
category: "Tutorials"
subcategory: advanced
order: 7
language: fr
sourceHash: "9237f00dce2ee5ec"
---

# Forker un dépôt

C'est la fonctionnalité clé : cloner un environnement de production entier (l'application, la base de données, les fichiers de configuration) en quelques secondes. Toute taille. Zéro disque supplémentaire. Forkez autant de fois que vous le souhaitez.

Le slogan : **clonez la production, ne cassez rien.**

## Regarder le tutoriel

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## Créer quelque chose à perdre

Tout d'abord, donnez à l'application en cours d'exécution un fichier pour prouver l'isolation du fork. Ouvrez le dépôt dans VS Code :

```bash
rdc vscode connect -m my-server -r my-app
```

À l'intérieur du dépôt, créez un fichier marqueur :

```bash
time echo "Hello from production" > index.html
```

Maintenant, forkez.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Le parent se démultiplie en clones indépendants](/img/tutorials/tutorial-forking/slide-1.svg)

Une seule commande. Tout a été cloné (l'application, la base de données, les fichiers de configuration) et cela s'est produit en quelques secondes. Relancez-la et vous obtenez un autre clone indépendant.

## Pourquoi est-ce si rapide ?

![Partager un lien de dossier prend le même temps quelle que soit la taille du dossier](/img/tutorials/tutorial-forking/slide-2.svg)

Imaginez partager un lien de dossier. Le lien est le même que le dossier soit petit ou énorme. Le dossier est lourd, le lien est léger.

![1 Go, 100 Go, 1 To. Même temps, à chaque fois.](/img/tutorials/tutorial-forking/slide-3.svg)

Le fork fonctionne de la même manière. 1 Go, 100 Go, 1 To. Même temps, à chaque fois.

## Ce qui est partagé, ce qui vous appartient

![Plusieurs miroirs, un soleil : base partagée, vos modifications vous appartiennent](/img/tutorials/tutorial-forking/slide-4.svg)

Pensez au dépôt parent comme au soleil. Vous ne pouvez pas tenir le soleil, mais vous pouvez tenir un miroir qui le capte. Ce miroir, c'est votre fork. Peignez sur le miroir, et vos dessins vous appartiennent. Le soleil reste le même, peu importe combien de miroirs lui font face.

> Vous ne pouvez pas tenir le soleil, mais vous pouvez le tenir dans un miroir.

## Que se passe-t-il si le parent change ensuite ?

![Un fork est une photographie figée ; le parent continue de couler comme une rivière](/img/tutorials/tutorial-forking/slide-5.svg)

Pensez maintenant à une rivière. L'eau continue de couler. À chaque instant, elle est différente. Quand vous forkez, vous prenez une photographie de la rivière, figée à cet instant. La rivière continue de couler. Votre photographie, non.

Si le dépôt parent change ensuite, votre fork reste là où il était.

> Vous ne pouvez pas tenir une rivière, mais vous pouvez la tenir dans une photo.

## L'utilisation du disque reste stable

![Cinq forks d'un dépôt de 100 Go, toujours environ 100 Go au total](/img/tutorials/tutorial-forking/slide-6.svg)

C'est pourquoi votre disque n'explose pas. Cinq forks d'un dépôt de 100 Go ? Toujours environ 100 Go au total. Vous ne payez en espace disque que ce que vous modifiez dans chaque fork.

> Forkez cinq fois si vous le souhaitez. Votre disque ne le remarquera même pas.

## Ce que les forks n'héritent *pas* : les secrets

Il y a une chose que le fork ne suit délibérément pas : les secrets. Un fork démarre sans clés API, sans mots de passe de base de données, sans tokens Stripe. C'est pourquoi "clonez la production, ne cassez rien" fonctionne vraiment. Votre sandbox ne peut pas facturer de vrais clients parce qu'il ne peut pas se faire passer pour vous. Nous configurons cela correctement dans le tutoriel [Gérer les secrets](/en/docs/tutorial-managing-secrets).

## Vérifier l'isolation

Listez les deux dépôts côte à côte :

```bash
time rdc repo list -m my-server
```

Vous verrez `my-app` et `my-app:experiment` tournant simultanément.

Dans le dépôt original, vérifiez ce qui tourne :

```bash
time docker ps
```

Notez le temps de fonctionnement. Ce sont les conteneurs originaux. Maintenant passez au fork :

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Mêmes images, mais le temps de fonctionnement est récent. Ceux-ci ont démarré quand le fork a été créé.

Rendez la différence encore plus évidente. Ajoutez un conteneur uniquement dans le fork :

```bash
time docker run --rm -it -d nginx
time docker ps
```

nginx tourne, mais uniquement dans ce fork.

Essayez quelque chose de destructif :

```bash
time rm index.html
```

Disparu ici. Revenez maintenant à l'original :

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Pas de nginx. Les conteneurs du fork sont restés dans le fork. Et `index.html` est toujours là, intact. L'original n'a rien su de ce qui s'est passé. Mêmes images, daemons Docker séparés, systèmes de fichiers séparés.

## Nettoyer

Quand vous avez terminé, supprimez simplement le fork :

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

L'original reste exactement comme il était. **Forkez, expérimentez, cassez des choses, supprimez.** Aucun risque.

---

Suivant : [Gérer les secrets](/en/docs/tutorial-managing-secrets).
