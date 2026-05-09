---
title: "Travailler avec votre dépôt"
description: "Tunnelisez un port vers votre navigateur, exécutez des commandes dans le sandbox et synchronisez des fichiers entre votre ordinateur et le dépôt."
category: "Tutorials"
subcategory: essentials
order: 6
language: fr
sourceHash: "3d56eb69e72c1a5a"
---

# Travailler avec votre dépôt

Votre application est en cours d'exécution, mais jusqu'à présent vous ne l'avez vue qu'à travers `docker ps`. Trois commandes couvrent le flux de travail quotidien : **tunnel** pour voir l'application dans un navigateur, **term** pour exécuter des commandes dans le sandbox, **sync** pour déplacer des fichiers entre votre ordinateur et le dépôt.

## Regarder le tutoriel

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## Les trois commandes du quotidien

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel** : ouvrir votre application dans un navigateur.
2. **Term** : exécuter une commande dans le sandbox.
3. **Sync** : déplacer des fichiers vers et depuis le dépôt.

## Tunnel : voir votre application dans un navigateur

L'application tourne sur le serveur, pas sur votre ordinateur. Transférez le port d'un conteneur via SSH :

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Ouvrez `localhost` dans votre navigateur. Votre application est là. Appuyez sur `Ctrl+C` quand vous avez terminé.

Pour un autre conteneur, changez `-c` et choisissez le port :

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term : exécuter des commandes dans le dépôt

Ignorez VS Code quand vous avez juste besoin d'un shell :

```bash
rdc term connect -m my-server -r my-app
```

Vous êtes maintenant dans le sandbox du dépôt. Essayez :

```bash
time docker ps
```

Vous ne voyez que les conteneurs de `my-app`, la même vue que dans VS Code.

Pour des commandes ponctuelles, utilisez `-c` et ignorez le shell interactif :

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync : déplacer des fichiers entre l'ordinateur et le dépôt

Envoyer un dossier depuis votre ordinateur vers le dépôt :

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Récupérer des fichiers :

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Prévisualisez d'abord si vous n'êtes pas sûr. `--dry-run` montre ce qui changerait sans rien copier :

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Trois commandes couvrent la boucle quotidienne.

---

Suivant : [Forker un dépôt](/en/docs/tutorial-forking).
