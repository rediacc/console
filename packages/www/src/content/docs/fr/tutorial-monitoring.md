---
title: "Surveillance et diagnostics"
description: "Vérifier l'état de la machine, inspecter les conteneurs, examiner les services systemd, scanner les clés d'hôte et exécuter les diagnostics d'environnement."
category: "Tutorials"
order: 4
language: fr
sourceHash: "af9f17a05dfb13b9"
---

# Comment surveiller et diagnostiquer l'infrastructure avec Rediacc

Maintenir une infrastructure saine nécessite une visibilité sur l'état de la machine, le statut des conteneurs et la santé des services. Dans ce tutoriel, vous exécutez des diagnostics d'environnement, vérifiez l'état de la machine, inspectez les conteneurs et services, examinez l'état du coffre et vérifiez la connectivité. À la fin, vous saurez comment identifier et investiguer les problèmes dans votre infrastructure.

## Prérequis

- La CLI `rdc` installée avec une configuration initialisée
- Une machine provisionnée avec au moins un dépôt en cours d'exécution (voir [Tutoriel : Cycle de vie des dépôts](/fr/docs/tutorial-repos))

## Enregistrement interactif

![Tutoriel : Surveillance et diagnostics](/assets/tutorials/monitoring-tutorial.cast)

### Étape 1 : Exécuter les diagnostics

Commencez par vérifier votre environnement local pour détecter tout problème de configuration.

```bash
rdc doctor
```

Vérifie Node.js, la version de la CLI, le binaire renet, la configuration et le support de la virtualisation. Chaque vérification indique **OK**, **Warning** ou **Error**.

### Étape 2 : Vérification de la santé de la machine

```bash
rdc machine health server-1
```

Récupère un rapport de santé complet de la machine distante : temps de fonctionnement du système, utilisation du disque, utilisation du datastore, nombre de conteneurs, état SMART du stockage et problèmes identifiés.

### Étape 3 : Voir les conteneurs en cours d'exécution

```bash
rdc machine containers server-1
```

Liste tous les conteneurs en cours d'exécution sur tous les dépôts de la machine, affichant le nom, le statut, l'état, la santé, l'utilisation CPU, l'utilisation mémoire et le dépôt propriétaire de chaque conteneur.

### Étape 4 : Vérifier les services systemd

Pour voir les services sous-jacents qui alimentent le Docker daemon et le réseau de chaque dépôt :

```bash
rdc machine services server-1
```

Liste les services systemd liés à Rediacc (Docker daemons, alias loopback) avec leur état, sous-état, nombre de redémarrages et utilisation mémoire.

### Étape 5 : Vue d'ensemble de l'état du coffre

```bash
rdc machine vault-status server-1
```

Fournit une vue d'ensemble de haut niveau de la machine : nom d'hôte, temps de fonctionnement, mémoire, disque, datastore et nombre total de dépôts.

### Étape 6 : Scanner les clés d'hôte

Si une machine a été reconstruite ou si son IP a changé, actualisez la clé SSH d'hôte stockée.

```bash
rdc config machine scan-keys server-1
```

Récupère les clés d'hôte actuelles du serveur et met à jour votre configuration. Cela évite les erreurs "host key verification failed".

### Étape 7 : Vérifier la connectivité

Une vérification rapide de la connectivité SSH pour confirmer que la machine est accessible et répond.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Le nom d'hôte confirme que vous êtes connecté au bon serveur. Le temps de fonctionnement confirme que le système fonctionne normalement.

## Dépannage

**La vérification de santé expire ou affiche "SSH connection failed"**
Vérifiez que la machine est en ligne et accessible : `ping <ip>`. Vérifiez que votre clé SSH est correctement configurée avec `rdc term <machine> -c "echo ok"`.

**"Service not found" dans la liste des services**
Les services Rediacc n'apparaissent qu'après le déploiement d'au moins un dépôt. Si aucun dépôt n'existe, la liste des services est vide.

**La liste des conteneurs affiche des conteneurs obsolètes ou arrêtés**
Les conteneurs de déploiements précédents peuvent persister si `repo down` n'a pas été exécuté proprement. Arrêtez-les avec `rdc repo down <repo> -m <machine>` ou inspectez directement via `rdc term <machine> <repo> -c "docker ps -a"`.

## Étapes suivantes

Vous avez exécuté les diagnostics, vérifié l'état de la machine, inspecté les conteneurs et services, et vérifié la connectivité. Pour travailler avec vos déploiements :

- [Surveillance](/fr/docs/monitoring) — référence complète pour toutes les commandes de surveillance
- [Dépannage](/fr/docs/troubleshooting) — problèmes courants et solutions
- [Tutoriel : Outils](/fr/docs/tutorial-tools) — terminal, synchronisation de fichiers et intégration VS Code
