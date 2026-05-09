---
title: "Sauvegarde et restauration"
description: "Poussez votre dépôt vers un stockage externe et restaurez-le sur un nouveau serveur quand vous en avez besoin."
category: "Tutorials"
subcategory: advanced
order: 11
language: fr
sourceHash: "8b48f3b19352aebe"
---

# Sauvegarde et restauration

Votre application est en production. Assurez-vous maintenant de ne jamais la perdre. `rdc` peut pousser votre dépôt entier (application, base de données, fichiers, configurations) vers un stockage externe et le récupérer à tout moment. Résistez aux ransomwares, aux pannes matérielles, à tout.

## Regarder le tutoriel

![Tutorial: Backup and restore](/assets/tutorials/tutorial-backup-restore.cast)

## Trois étapes

![Configurer, pousser, restaurer](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **Configurer** un fournisseur de stockage.
2. **Pousser** une sauvegarde.
3. **Restaurer** quand vous en avez besoin.

## Étape 1 : Configurer le stockage

Vous avez besoin d'un fichier de configuration `rclone`. Si vous utilisez déjà rclone, importez-le directement :

```bash
time rdc config storage import --file rclone.conf
```

Cela prend en charge S3, B2, Google Drive, Dropbox et bien d'autres. Vérifiez ce qui est configuré :

```bash
time rdc config storage list
```

## Étape 2 : Pousser une sauvegarde

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

Votre dépôt entier (application, base de données, fichiers, tout) est maintenant sauvegardé. Comme le dépôt lui-même est chiffré, la sauvegarde l'est aussi. Aucune gestion de clé supplémentaire.

Listez vos sauvegardes à tout moment :

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Pourquoi aucun temps d'arrêt ?

L'application continue de tourner pendant que la sauvegarde se téléverse. Comment est-ce cohérent ?

Même logique qu'un [fork](/en/docs/tutorial-forking). `rdc` forke d'abord, puis téléverse le fork. Le fork capture l'instant ; votre application en direct continue. Aucun temps d'arrêt, aucune incohérence.

## Étape 3 : Restaurer sur un nouveau serveur

Supposons que votre serveur tombe en panne. Configurez un nouveau serveur, ajoutez-le à `rdc` et récupérez :

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Puis démarrez-le :

```bash
time rdc repo up --name my-app -m new-server
```

Votre application est de retour. Mêmes données, mêmes conteneurs, machine différente.

## Sauvegardes plus rapides : de machine à machine

Vous pouvez également pousser directement entre machines, sans stockage cloud intermédiaire :

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **Conseil.** Les téléversements vers le stockage envoient toujours tout. De machine à machine, seule la différence est envoyée. Le premier push de machine à machine prend le temps habituel, mais chaque push suivant est beaucoup plus rapide. Idéal pour les sauvegardes fréquentes.

---

Suivant : [Surveillance](/en/docs/tutorial-monitoring).
