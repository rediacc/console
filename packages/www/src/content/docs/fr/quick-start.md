---
title: Démarrage rapide
description: Lancez un service conteneurisé sur votre serveur en quelques minutes.
category: Guides
order: -1
language: fr
sourceHash: "2047fd1ce3a47944"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Démarrage rapide

Déployez un environnement de conteneurs chiffré et isolé sur votre propre serveur. Aucun compte cloud ni dépendance SaaS. Tout fonctionne sur du matériel que vous contrôlez.

---

## Introduction

### Concepts clés

Un repo est un fichier chiffré unique sur le disque. Déplacez-le, sauvegardez-le, dupliquez-le. C'est juste un fichier. Une fois monté, il devient un dossier avec un démon Docker dédié et les données de votre application à l'intérieur.

Pensez à un repo comme une clé USB : branchez-la dans n'importe quelle machine et les applications et données se montent, prêtes à s'exécuter. Déplacez-la entre machines ou fournisseurs cloud sans tout reconstruire.

**Deux outils, deux rôles :**

- **rdc** = CLI sur votre poste de travail (TypeScript, installé globalement)
- **renet** = orchestrateur sur le serveur (binaire Go, gère les démons/réseaux/isolation)
- RDC provisionne renet automatiquement lors de `config machine setup`. Aucune configuration manuelle sur le serveur.

> [Architecture](/fr/docs/architecture) explique le modèle de sécurité. [rdc vs renet](/fr/docs/rdc-vs-renet) explique quel outil utiliser selon le cas.

### 1. Installer le CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Vérification : Node, clé SSH, renet, Docker
```

> Windows, Alpine, Arch : voir [Installation](/fr/docs/installation). Configuration système requise complète : [Prérequis](/fr/docs/requirements).

### 2. Configuration de la clé SSH

rdc se connecte via SSH. Le serveur doit approuver votre clé publique avant que rdc puisse l'atteindre.

```bash
# Générer une clé (passez cette étape si vous en avez déjà une)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copier la clé publique sur le serveur (demandera le mot de passe)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Indiquer à rdc quelle clé utiliser
rdc config ssh set --key ~/.ssh/id_ed25519
```

Chaque commande rdc s'authentifie désormais avec cette clé. Aucun mot de passe.

### 3. Ajouter votre serveur

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # Provisionne renet + crée le datastore
```

**Ce qui se passe :** L'empreinte de la clé SSH de l'hôte est analysée, le binaire renet est téléversé, le datastore chiffré est initialisé sur le serveur. Prêt pour les repos.

> Dimensionnement du datastore, Ceph RBD, fournisseurs cloud : [Configuration du serveur](/fr/docs/setup). Échecs SSH : [Dépannage](/fr/docs/troubleshooting).

### 4. Fichier de configuration

```bash
rdc config show                            # Résumé lisible
cat ~/.config/rediacc/rediacc.json         # JSON brut : machines, repos, stockages, clé SSH
```

**Un fichier = un environnement.** Copiez-le sur un autre poste et vous êtes prêt.

---

## Travailler avec un repo

### 1. Créer un repo

```bash
rdc repo create --name my-app -m my-server --size 2G  # Créer un repo chiffré de 2 Go
```

Crée le volume chiffré, le monte et démarre son démon Docker. Le repo est enregistré dans votre configuration et prêt à l'emploi.

> Redimensionnement, suppression, validation : [Dépôts](/fr/docs/repositories).

### 2. Appliquer un modèle

```bash
rdc repo template list                                        # Afficher les modèles intégrés
rdc repo template apply --name app-postgres -m my-server -r my-app  # Déployer docker-compose.yml + Rediaccfile
```

Les modèles fournissent un `docker-compose.yml`, un `Rediaccfile` et des fichiers de support. Sans modèle (ou votre propre fichier compose), il n'y a rien à démarrer. Utilisez le modèle intégré pour votre premier repo. C'est le chemin le plus rapide pour voir tout le flux de travail de bout en bout.

### 3. Démarrer le repo

```bash
rdc repo up --name my-app -m my-server  # Exécuter Rediaccfile up()
rdc repo list -m my-server                           # Voir tous les repos sur la machine
rdc repo status --name my-app -m my-server  # État du montage, Docker, taille, chiffrement
```

`repo up` monte automatiquement si nécessaire. Aucun paramètre requis.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # Ouvre VS Code SSH, atterrit dans le bac à sable du repo
```

Vous éditez des fichiers *à l'intérieur* du volume chiffré. `docker ps` n'affiche que les conteneurs de ce repo. Enregistrez, compose up, itérez.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Où l'exécuter** | Votre poste de travail (CLI) | Dans le bac à sable VS Code |
| **Ce que ça fait** | SSH → montage auto → exécute Rediaccfile `up()` | Exécute Rediaccfile `up()` directement |
| **Cas d'usage** | CI/CD, automatisation, opérations à distance | Boucle de développement interne |
| **Isolation** | Orchestre depuis l'extérieur | Déjà dans le bac à sable |

**Flux de démonstration :** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → modifier `docker-compose.yml` → `renet dev up` → voir l'application en cours d'exécution → itérer.

> Structure du Rediaccfile : [Services](/fr/docs/services). Quand utiliser quel outil : [rdc vs renet](/fr/docs/rdc-vs-renet).

### 6. Modèle d'isolation

- **Utilisateur universel** (`rediacc`) : Même UID sur chaque machine. Déplacez un repo vers un autre serveur et les permissions de fichiers fonctionnent directement. Aucun casse-tête avec `chown`.
- **Démon Docker par repo** : Chaque repo dispose de son propre démon Docker isolé. `docker ps` n'affiche que les conteneurs de CE repo.
- **Bac à sable Landlock + OverlayFS** : Le shell VS Code est restreint au niveau du système de fichiers. Vous ne pouvez pas lire d'autres repos. Les écritures dans `$HOME` sont des overlays par repo.

> Fonctionnement de l'isolation : [Architecture](/fr/docs/architecture). Cycle de vie du Rediaccfile : [Services](/fr/docs/services).

### 7. Terminal, synchronisation et tunnel

**Terminal :**
```bash
rdc term connect -m my-server -r my-app                            # SSH dans le bac à sable du repo
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # Exécuter une commande et quitter
rdc term connect -m my-server                                   # SSH vers la machine (sans bac à sable)
```

**Synchronisation de fichiers (rsync via SSH) :**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # Téléverser un répertoire
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # Téléverser un fichier
rdc repo sync download -m my-server -r my-app --local ./backup                              # Télécharger un répertoire
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # Télécharger un fichier
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # Aperçu d'abord
```

**Tunnel (redirection de port SSH vers un conteneur) :**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # Détection automatique du port pour le conteneur app
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # Tunnel vers Postgres
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # Port local personnalisé
```

Lancez le tunnel → ouvrez `localhost:3000` dans le navigateur → application en direct depuis le serveur distant.

> Synchronisation, terminal, détails VS Code : [Outils](/fr/docs/tools).

---

## Fork et sauvegarde

### 1. Grand et fork de repos

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # Clone CoW instantané + démarrage
rdc repo list -m my-server                                  # Affiche : my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # Supprimer le fork, grand intact
```

**Clone instantané, zéro copie.** CoW (copy-on-write). Microsecondes, aucune donnée copiée. Les blocs sont partagés jusqu'à ce qu'un côté écrive.

**Cas d'usage :**
- **IA / ML :** Fork du jeu de données de production, exécuter une expérience, abandonner ou promouvoir
- **DevOps :** Fork → tester la migration → supprimer si échec, promouvoir si succès
- **Sauvegarde :** Fork = instantané immédiat, envoyez-le hors site

> Cycle de vie des forks, forks inter-machines : [Dépôts](/fr/docs/repositories).

### 2. Pousser vers une autre machine

```bash
# Pousser le repo vers une autre machine
rdc repo push --name my-app -m my-server --to backup-server

# Pousser et déployer automatiquement sur la cible
rdc repo push --name my-app -m my-server --to backup-server --up

# Pousser avec un checkpoint CRIU (migration en direct, préserve l'état mémoire)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# Pousser vers une nouvelle machine (provisionnement auto via fournisseur cloud)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. Pousser vers un stockage cloud (OneDrive, Google Drive, S3)

```bash
# Importer votre configuration rclone comme backend de stockage
rdc config storage import --file ~/rclone.conf

# Lister les stockages disponibles
rdc storage list

# Pousser le repo vers un stockage cloud
rdc repo push --name my-app -m my-server --to my-s3-backup

# Lister les sauvegardes sur le stockage
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` détecte automatiquement si la cible est une machine ou un backend de stockage. Fonctionne avec tout fournisseur supporté par rclone : S3, R2, B2, OneDrive, Google Drive, SFTP, etc.

### 4. Récupérer depuis un emplacement distant

```bash
# Récupérer le repo depuis une machine cloud vers votre serveur local
rdc repo pull --name my-app -m my-local-server --from cloud-server

# Récupérer depuis un stockage cloud
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# Récupérer et démarrer immédiatement
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**Pourquoi récupérer ?** Votre machine locale est derrière un NAT. Le cloud ne peut pas pousser vers vous. Mais vous pouvez atteindre le cloud. Pull ramène le repo chez vous.

**Cycle complet :** Créer en dev → pousser vers le cloud → récupérer en production → `--up`. Un repo, n'importe quelle machine, n'importe quel cloud.

> Planification, sauvegardes automatisées, restauration : [Sauvegarde et restauration](/fr/docs/backup-restore).

---

## Proxy et SSL

### 1. Configuration de l'infrastructure

```bash
rdc config infra set -m my-server  # Configurer : domaine de base, IPs publiques, plages de ports
rdc config infra show -m my-server  # Vérifier la configuration
rdc config infra push -m my-server  # Pousser la configuration du proxy vers le serveur distant
```

**Fonctionnement du routage :**
- Traefik découvre automatiquement les conteneurs via les labels `rediacc.service_name` et `rediacc.service_port`
- Routes : `{service}-{networkId}.{baseDomain}` → IP du conteneur:port
- SSL : Let's Encrypt via le challenge DNS-01 de Cloudflare (renouvellement automatique, certificats wildcard)

### 2. Modèle de proxy

```bash
rdc repo template apply --name proxy -m my-server -r infra  # Déployer le proxy dans un repo
rdc repo up --name infra -m my-server  # Démarrer Traefik
```

Traefik route désormais le trafic externe vers tous les repos sur cette machine. Chaque conteneur obtient automatiquement un point de terminaison HTTPS.

```bash
# Accédez à https://my-app.example.com → routé vers le conteneur
# Redirection TCP/UDP pour les bases de données :
#   rediacc.tcp_ports=3306,5432 → ports externes alloués automatiquement
```

> Règles de routage, DNS, configuration TLS : [Réseau](/fr/docs/networking).

---

## Prochaines étapes

- **[Guide de migration](/fr/docs/migration)** - Intégrer des projets existants dans des dépôts Rediacc
- **[Surveillance](/fr/docs/monitoring)** - Santé de la machine, conteneurs, services, diagnostics
- **[Référence CLI](/fr/docs/cli-application)** - Référence complète des commandes
- **[Aide-mémoire](/fr/docs/rdc-cheat-sheet)** - Recherche rapide de commandes
- **[Dépannage](/fr/docs/troubleshooting)** - Solutions aux problèmes courants
- **[Règles de Rediacc](/fr/docs/rules-of-rediacc)** - Bonnes pratiques pour les Rediaccfiles et checklist de déploiement
