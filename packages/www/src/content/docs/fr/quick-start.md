---
title: Démarrage rapide
description: Lancez un service conteneurisé sur votre serveur en 5 minutes.
category: Guides
order: -1
language: fr
sourceHash: 71850d61f7e44292
---

# Démarrage rapide

Si vous hésitez sur l'outil a utiliser, consultez [rdc vs renet](/fr/docs/rdc-vs-renet).
Déployez un environnement de conteneurs chiffré et isolé sur votre propre serveur en 5 minutes. Ce guide utilise le **mode local** — aucun compte cloud ni dépendance SaaS.

## Prérequis

- Un poste de travail Linux ou macOS
- Un serveur distant (Ubuntu 24.04+, Debian 12+ ou Fedora 43+) avec accès SSH et privilèges sudo
- Une paire de clés SSH (par exemple `~/.ssh/id_ed25519`)

## 1. Installer le CLI

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Créer un contexte

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. Ajouter votre serveur

```bash
rdc context add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. Provisionner le serveur

```bash
rdc context setup-machine server-1
```

Cela installe Docker, cryptsetup et le binaire renet sur votre serveur.

## 5. Créer un dépôt chiffré

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. Déployer les services

Montez le dépôt, créez vos fichiers `docker-compose.yml` et `Rediaccfile` à l'intérieur, puis démarrez :

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. Vérifier

```bash
rdc machine containers server-1
```

Vous devriez voir vos conteneurs en cours d'exécution.

## Qu'est-ce que Rediacc ?

Rediacc déploie des services conteneurisés sur des serveurs distants que vous contrôlez. Tout est chiffré au repos avec LUKS, chaque dépôt dispose de son propre démon Docker isolé, et toute l'orchestration se fait via SSH depuis votre poste de travail.

Pas de comptes cloud. Pas de dépendances SaaS. Vos données restent sur vos serveurs.

## Étapes suivantes

- **[Architecture](/fr/docs/architecture)** — Comprendre le fonctionnement de Rediacc : modes, modèle de sécurité, isolation Docker
- **[Configuration du serveur](/fr/docs/setup)** — Guide de configuration détaillé : contextes, machines, configuration de l'infrastructure
- **[Dépôts](/fr/docs/repositories)** — Créer, gérer, redimensionner, dupliquer et valider des dépôts
- **[Services](/fr/docs/services)** — Rediaccfiles, réseau de services, déploiement, démarrage automatique
- **[Sauvegarde et restauration](/fr/docs/backup-restore)** — Sauvegarder vers un stockage externe et planifier des sauvegardes automatisées
- **[Surveillance](/fr/docs/monitoring)** — Santé du serveur, conteneurs, services, diagnostics
- **[Outils](/fr/docs/tools)** — Synchronisation de fichiers, terminal SSH, intégration VS Code
- **[Guide de migration](/fr/docs/migration)** — Intégrer des projets existants dans des dépôts Rediacc
- **[Dépannage](/fr/docs/troubleshooting)** — Solutions aux problèmes courants
- **[Référence CLI](/fr/docs/cli-application)** — Référence complète des commandes
