---
title: "Cycle de vie des dépôts"
description: "Créer un dépôt chiffré, déployer une application conteneurisée, inspecter les conteneurs et nettoyer."
category: "Tutorials"
order: 3
language: fr
sourceHash: "0c4edddefa30df1c"
---

# Comment déployer et gérer des dépôts avec Rediacc

Les dépôts sont l'unité de déploiement principale dans Rediacc — chacun est un environnement isolé et chiffré avec son propre Docker daemon et un stockage dédié. Dans ce tutoriel, vous créez un dépôt chiffré, déployez une application conteneurisée, inspectez les conteneurs en cours d'exécution et nettoyez. À la fin, vous aurez complété un cycle de déploiement complet.

## Prérequis

- Le CLI `rdc` installé avec une configuration initialisée
- Une machine provisionnée (voir [Tutoriel : Configuration de machine](/fr/docs/tutorial-setup))
- Une application simple avec un `Rediaccfile` et un `docker-compose.yml`

## Enregistrement interactif

![Tutoriel : Cycle de vie des dépôts](/assets/tutorials/repos-tutorial.cast)

### Étape 1 : Créer un dépôt chiffré

Chaque dépôt obtient son propre volume de stockage chiffré LUKS. Spécifiez la machine et la taille du stockage.

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc crée un volume chiffré de 2 Go, le formate et le monte automatiquement. Le dépôt est prêt pour le téléchargement de fichiers.

### Étape 2 : Lister les dépôts

Confirmez que le nouveau dépôt est disponible.

```bash
rdc repo list -m server-1
```

Affiche tous les dépôts sur la machine avec leur taille, état de montage et état de chiffrement.

### Étape 3 : Inspecter le chemin de montage

Avant de déployer, vérifiez que le stockage du dépôt est monté et accessible.

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

Le répertoire de montage est l'emplacement des fichiers d'application — `Rediaccfile`, `docker-compose.yml` et tous les volumes de données.

### Étape 4 : Démarrer les services

Déployez l'application en montant le dépôt et en démarrant ses services Docker.

```bash
rdc repo up test-app -m server-1 --mount
```

Cela monte le dépôt (s'il n'est pas déjà monté), démarre un Docker daemon isolé et démarre les services via `up()`.

> **Remarque :** Le premier déploiement prend plus de temps car les images Docker sont téléchargées. Les démarrages suivants réutilisent les images en cache.

### Étape 5 : Voir les conteneurs en cours d'exécution

```bash
rdc machine containers server-1
```

Affiche tous les conteneurs en cours d'exécution sur tous les dépôts de la machine, y compris l'utilisation du processeur et de la mémoire.

### Étape 6 : Accéder au terminal du dépôt

Pour exécuter des commandes dans l'environnement Docker isolé du dépôt :

```bash
rdc term server-1 test-app -c "docker ps"
```

La session terminal définit `DOCKER_HOST` sur le socket Docker isolé du dépôt. Toute commande Docker s'exécute uniquement sur les conteneurs de ce dépôt.

### Étape 7 : Arrêter et nettoyer

Lorsque vous avez terminé, arrêtez les services, fermez le volume chiffré et supprimez optionnellement le dépôt.

```bash
rdc repo down test-app -m server-1      # Arrêter les services
rdc repo unmount test-app -m server-1   # Fermer le volume chiffré
rdc repo delete test-app -m server-1    # Supprimer le dépôt définitivement
```

`down` arrête les conteneurs et le Docker daemon. `unmount` ferme le volume LUKS. `delete` supprime définitivement le dépôt et son stockage chiffré.

> **Avertissement :** `repo delete` est irréversible. Toutes les données du dépôt sont détruites. Créez d'abord une sauvegarde si nécessaire.

## Dépannage

**« Espace disque insuffisant » lors de la création du dépôt**
Le volume chiffré nécessite de l'espace libre contigu sur l'hôte. Vérifiez l'espace disponible avec `df -h` sur le serveur. Envisagez une valeur `--size` plus petite ou libérez de l'espace disque.

**Délai d'attente du téléchargement d'image Docker pendant `repo up`**
Les grandes images peuvent dépasser le délai sur les connexions lentes. Réessayez avec `rdc repo up` — il reprend là où il s'est arrêté. Pour les environnements isolés, préchargez les images dans le Docker daemon du dépôt.

**« Échec du montage » ou « Échec de l'ouverture LUKS »**
La phrase de passe LUKS est dérivée de la configuration. Vérifiez que vous utilisez la même configuration qui a créé le dépôt. Si le volume est déjà monté par un autre processus, démontez-le d'abord.

## Étapes suivantes

Vous avez créé un dépôt chiffré, déployé une application, inspecté les conteneurs et nettoyé. Pour surveiller vos déploiements :

- [Services](/fr/docs/services) — référence Rediaccfile, réseaux de services, démarrage automatique et configurations multi-services
- [Tutoriel : Surveillance et diagnostic](/fr/docs/tutorial-monitoring) — vérifications de santé, inspection de conteneurs et diagnostic
- [Outils](/fr/docs/tools) — terminal, synchronisation de fichiers et intégration VS Code
