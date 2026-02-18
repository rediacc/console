---
title: "Supervision"
description: "Supervisez la santé des machines, les conteneurs, les services, les dépôts et exécutez des diagnostics."
category: "Guides"
order: 9
language: fr
---

# Supervision

Rediacc fournit des commandes de supervision intégrées pour inspecter la santé des machines, les conteneurs en cours d'exécution, les services, le statut des dépôts et les diagnostics système.

## Santé de la machine

Obtenez un rapport de santé complet pour une machine :

```bash
rdc machine health server-1
```

Ce rapport inclut :
- **Système** : temps de fonctionnement, utilisation de la mémoire, utilisation du disque
- **Datastore** : capacité et utilisation
- **Conteneurs** : nombre en cours d'exécution, sains, défaillants
- **Services** : statut et nombre de redémarrages
- **Stockage** : santé SMART et température
- **Dépôts** : statut de montage et statut du démon Docker
- **Problèmes** : problèmes identifiés

Utilisez `--output json` pour une sortie lisible par les machines.

## Lister les conteneurs

Affichez tous les conteneurs en cours d'exécution sur tous les dépôts d'une machine :

```bash
rdc machine containers server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du conteneur |
| Status | En cours d'exécution, arrêté, etc. |
| Health | Sain, défaillant, aucun |
| CPU | Pourcentage d'utilisation du processeur |
| Memory | Utilisation de la mémoire |
| Repository | Dépôt propriétaire du conteneur |

Options :
- `--health-check` — Effectuer des vérifications de santé actives sur les conteneurs
- `--output json` — Sortie JSON lisible par les machines

## Lister les services

Affichez les services systemd liés à Rediacc sur une machine :

```bash
rdc machine services server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du service |
| State | Actif, inactif, en échec |
| Sub-state | En cours d'exécution, arrêté, etc. |
| Restarts | Nombre de redémarrages |
| Memory | Utilisation de la mémoire du service |
| Repository | Dépôt associé |

Options :
- `--stability-check` — Signaler les services instables (en échec, >3 redémarrages, redémarrage automatique)
- `--output json` — Sortie JSON lisible par les machines

## Lister les dépôts

Affichez les dépôts sur une machine avec des statistiques détaillées :

```bash
rdc machine repos server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du dépôt |
| Size | Taille de l'image disque |
| Mount | Monté ou démonté |
| Docker | Démon Docker en cours d'exécution ou arrêté |
| Containers | Nombre de conteneurs |
| Disk Usage | Utilisation réelle du disque au sein du dépôt |
| Modified | Date de dernière modification |

Options :
- `--search <text>` — Filtrer par nom ou chemin de montage
- `--output json` — Sortie JSON lisible par les machines

## Statut du coffre

Obtenez un aperçu complet d'une machine incluant les informations de déploiement :

```bash
rdc machine vault-status server-1
```

Ceci fournit :
- Nom d'hôte et temps de fonctionnement
- Utilisation de la mémoire, du disque et du datastore
- Nombre total de dépôts, nombre de montés, nombre de démons Docker actifs
- Informations détaillées par dépôt

Utilisez `--output json` pour une sortie lisible par les machines.

## Tester la connexion

Vérifiez la connectivité SSH vers une machine :

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Ce rapport inclut :
- Statut de la connexion (succès/échec)
- Méthode d'authentification utilisée
- Configuration de la clé SSH
- Statut de déploiement de la clé publique
- Entrée des clés d'hôte connues

Options :
- `--port <number>` — Port SSH (par défaut : 22)
- `--save -m server-1` — Enregistrer la clé d'hôte vérifiée dans la configuration de la machine

## Diagnostics (doctor)

Exécutez une vérification diagnostique complète de votre environnement Rediacc :

```bash
rdc doctor
```

| Catégorie | Vérifications |
|-----------|---------------|
| **Environnement** | Version de Node.js, version du CLI, mode SEA, installation de Go, disponibilité de Docker |
| **Renet** | Emplacement du binaire, version, CRIU, rsync, ressources SEA embarquées |
| **Configuration** | Contexte actif, mode, machines, clé SSH |
| **Authentification** | Statut de connexion, email utilisateur |

Chaque vérification indique **OK**, **Avertissement** ou **Erreur**. Utilisez cette commande comme première étape lors du dépannage de tout problème.

Codes de sortie : `0` = tout réussi, `1` = avertissements, `2` = erreurs.
