---
title: "Outils"
description: "Utilisez l'accès terminal SSH, la synchronisation de fichiers, l'intégration VS Code et les commandes de mise à jour CLI."
category: "Tutorials"
order: 5
language: fr
sourceHash: "f581499837e09360"
---

# Comment utiliser les outils Terminal, Sync et VS Code avec Rediacc

Le CLI comprend des outils de productivité pour les opérations quotidiennes : accès terminal SSH, synchronisation de fichiers via rsync, développement à distance avec VS Code et mises à jour du CLI. Dans ce tutoriel, vous exécutez des commandes à distance, synchronisez des fichiers vers un dépôt, vérifiez l'intégration VS Code et contrôlez votre version du CLI.

## Prérequis

- Le CLI `rdc` installé avec une configuration initialisée
- Une machine provisionnée avec un dépôt en cours d'exécution (voir [Tutoriel : Cycle de vie du dépôt](/fr/docs/tutorial-repos))

## Enregistrement interactif

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### Étape 1 : Se connecter à une machine

Exécutez des commandes en ligne sur une machine distante via SSH sans ouvrir une session interactive.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Le drapeau `-c` exécute une seule commande et retourne la sortie. Omettez `-c` pour ouvrir une session SSH interactive.

### Étape 2 : Se connecter à un dépôt

Pour exécuter des commandes dans l'environnement Docker isolé d'un dépôt :

```bash
rdc term server-1 my-app -c "docker ps"
```

Lors de la connexion à un dépôt, `DOCKER_HOST` est automatiquement défini sur le socket Docker isolé du dépôt. Toute commande Docker s'exécute uniquement contre les conteneurs de ce dépôt.

### Étape 3 : Aperçu de la synchronisation de fichiers (simulation)

Avant de transférer des fichiers, prévisualisez ce qui changerait.

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

Le drapeau `--dry-run` affiche les nouveaux fichiers, les fichiers modifiés et la taille totale du transfert sans rien télécharger réellement.

### Étape 4 : Télécharger des fichiers

Transférez des fichiers de votre machine locale vers le point de montage du dépôt distant.

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Les fichiers sont transférés via rsync sur SSH. Seuls les fichiers modifiés sont envoyés lors des téléchargements suivants.

### Étape 5 : Vérifier les fichiers téléchargés

Confirmez l'arrivée des fichiers en listant le répertoire de montage du dépôt.

```bash
rdc term server-1 my-app -c "ls -la"
```

### Étape 6 : Vérification de l'intégration VS Code

Pour développer à distance avec VS Code, vérifiez que les composants requis sont installés.

```bash
rdc vscode check
```

Vérifie votre installation VS Code, l'extension Remote SSH et la configuration SSH. Suivez la sortie pour résoudre les prérequis manquants, puis connectez-vous avec `rdc vscode <machine> [repo]`.

### Étape 7 : Vérifier les mises à jour du CLI

```bash
rdc update --check-only
```

Indique si une version plus récente du CLI est disponible. Pour installer la mise à jour, exécutez `rdc update` sans `--check-only`.

## Dépannage

**"rsync: command not found" lors de la synchronisation de fichiers**
Installez rsync sur votre machine locale et sur le serveur distant. Sur Debian/Ubuntu : `sudo apt install rsync`. Sur macOS : rsync est inclus par défaut.

**"Permission denied" lors du téléchargement de synchronisation**
Vérifiez que votre utilisateur SSH a un accès en écriture au répertoire de montage du dépôt. Les montages de dépôts appartiennent à l'utilisateur spécifié lors de l'enregistrement de la machine.

**"VS Code Remote SSH extension not found"**
Installez l'extension depuis le marketplace VS Code : recherchez "Remote - SSH" par Microsoft. Après l'installation, redémarrez VS Code et exécutez à nouveau `rdc vscode check`.

## Étapes suivantes

Vous avez exécuté des commandes à distance, synchronisé des fichiers, vérifié l'intégration VS Code et contrôlé les mises à jour du CLI. Pour protéger vos données :

- [Tools](/fr/docs/tools) — référence complète pour les commandes terminal, sync, VS Code et mise à jour
- [Tutoriel : Sauvegarde et réseau](/fr/docs/tutorial-backup) — planification des sauvegardes et configuration réseau
- [Services](/fr/docs/services) — référence Rediaccfile et réseaux de services
