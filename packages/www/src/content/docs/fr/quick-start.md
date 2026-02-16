---
title: "Guide de Démarrage Rapide"
description: "Guide étape par étape pour déployer une infrastructure chiffrée et isolée sur vos propres serveurs en utilisant Rediacc en mode local."
category: "Core Concepts"
order: 0
language: fr
---

# Guide de Démarrage Rapide

Ce guide vous accompagne dans le déploiement d'une infrastructure chiffrée et isolée sur vos propres serveurs en utilisant Rediacc en **mode local**. À la fin, vous disposerez d'un dépôt pleinement opérationnel exécutant des services conteneurisés sur une machine distante, le tout géré depuis votre poste de travail.

Le mode local signifie que tout fonctionne sur une infrastructure que vous contrôlez. Pas de comptes cloud, pas de dépendances SaaS. Votre poste de travail orchestre les serveurs distants via SSH, et tout l'état est stocké localement sur votre machine et sur les serveurs eux-mêmes.

## Vue d'Ensemble de l'Architecture

Rediacc utilise une architecture à deux outils :

```
Votre Poste de Travail                Serveur Distant
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (binaire Go)      │
│  rdc (CLI)   │                   │    ├── Chiffrement LUKS  │
│              │ ◀──────────────   │    ├── Démon Docker      │
│  config.json │    stdout/stderr  │    ├── Exec Rediaccfile  │
└──────────────┘                   │    └── Proxy Traefik     │
                                   └──────────────────────────┘
```

- **rdc** s'exécute sur votre poste de travail (macOS ou Linux). Il lit votre configuration locale, se connecte aux machines distantes via SSH et invoque les commandes renet.
- **renet** s'exécute sur le serveur distant avec des privilèges root. Il gère les images disque chiffrées LUKS, les démons Docker isolés, l'orchestration des services et la configuration du proxy inverse.

Chaque commande que vous tapez localement se traduit par un appel SSH qui exécute renet sur la machine distante. Vous n'avez jamais besoin de vous connecter manuellement aux serveurs en SSH.

## Ce Dont Vous Aurez Besoin

Avant de commencer, assurez-vous de disposer des éléments suivants :

**Sur votre poste de travail :**
- macOS ou Linux avec un client SSH
- Une paire de clés SSH (par ex., `~/.ssh/id_ed25519` ou `~/.ssh/id_rsa`)

**Sur le serveur distant :**
- Ubuntu 20.04+ ou Debian 11+ (d'autres distributions Linux peuvent fonctionner mais ne sont pas testées)
- Un compte utilisateur avec les privilèges `sudo`
- Votre clé publique SSH ajoutée à `~/.ssh/authorized_keys`
- Au moins 20 Go d'espace disque libre (davantage selon vos charges de travail)

## Étape 1 : Installer rdc

Installez le CLI Rediacc sur votre poste de travail :

```bash
curl -fsSL https://get.rediacc.com | sh
```

Ceci télécharge le binaire `rdc` dans `$HOME/.local/bin/`. Assurez-vous que ce répertoire est dans votre PATH. Vérifiez l'installation :

```bash
rdc --help
```

> Pour mettre à jour ultérieurement, exécutez `rdc update`.

## Étape 2 : Créer un Contexte Local

Un **contexte** est une configuration nommée qui stocke vos identifiants SSH, les définitions de machines et les mappages de dépôts. Considérez-le comme un espace de travail de projet.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Requis | Description |
|--------|--------|-------------|
| `--ssh-key <path>` | Oui | Chemin vers votre clé privée SSH. Le tilde (`~`) est développé automatiquement. |
| `--renet-path <path>` | Non | Chemin personnalisé vers le binaire renet sur les machines distantes. Par défaut, l'emplacement d'installation standard. |

Ceci crée un contexte local nommé `my-infra` et le stocke dans `~/.rediacc/config.json`.

> Vous pouvez avoir plusieurs contextes (par ex., `production`, `staging`, `dev`). Basculez entre eux avec le drapeau `--context` sur n'importe quelle commande.

## Étape 3 : Ajouter une Machine

Enregistrez votre serveur distant comme machine dans le contexte :

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Requis | Par défaut | Description |
|--------|--------|------------|-------------|
| `--ip <address>` | Oui | - | Adresse IP ou nom d'hôte du serveur distant. |
| `--user <username>` | Oui | - | Nom d'utilisateur SSH sur le serveur distant. |
| `--port <port>` | Non | `22` | Port SSH. |
| `--datastore <path>` | Non | `/mnt/rediacc` | Chemin sur le serveur où Rediacc stocke les dépôts chiffrés. |

Après l'ajout de la machine, rdc exécute automatiquement `ssh-keyscan` pour récupérer les clés d'hôte du serveur. Vous pouvez également exécuter ceci manuellement :

```bash
rdc context scan-keys server-1
```

Pour afficher toutes les machines enregistrées :

```bash
rdc context machines
```

## Étape 4 : Configurer la Machine

Provisionnez le serveur distant avec toutes les dépendances requises :

```bash
rdc context setup-machine server-1
```

Cette commande :
1. Téléverse le binaire renet sur le serveur via SFTP
2. Installe Docker, containerd et cryptsetup (si non présents)
3. Crée le répertoire du datastore et le prépare pour les dépôts chiffrés

| Option | Requis | Par défaut | Description |
|--------|--------|------------|-------------|
| `--datastore <path>` | Non | `/mnt/rediacc` | Répertoire du datastore sur le serveur. |
| `--datastore-size <size>` | Non | `95%` | Proportion du disque disponible à allouer au datastore. |
| `--debug` | Non | `false` | Activer la sortie détaillée pour le dépannage. |

> La configuration ne doit être exécutée qu'une seule fois par machine. Il est possible de la relancer en toute sécurité si nécessaire.

## Étape 5 : Créer un Dépôt

Un **dépôt** est une image disque chiffrée LUKS sur le serveur distant. Une fois monté, il fournit :
- Un système de fichiers isolé pour les données de votre application
- Un démon Docker dédié (séparé du Docker de l'hôte)
- Des adresses IP de bouclage uniques pour chaque service au sein d'un sous-réseau /26

Créez un dépôt :

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Requis | Description |
|--------|--------|-------------|
| `-m, --machine <name>` | Oui | Machine cible où le dépôt sera créé. |
| `--size <size>` | Oui | Taille de l'image disque chiffrée (par ex., `5G`, `10G`, `50G`). |

La sortie affichera trois valeurs générées automatiquement :

- **GUID du dépôt** -- Un UUID qui identifie l'image disque chiffrée sur le serveur.
- **Identifiant (Credential)** -- Une phrase secrète aléatoire utilisée pour chiffrer/déchiffrer le volume LUKS.
- **ID réseau** -- Un entier (commençant à 2816, incrémenté de 64) qui détermine le sous-réseau IP pour les services de ce dépôt.

> **Conservez l'identifiant en lieu sûr.** C'est la clé de chiffrement de votre dépôt. En cas de perte, les données ne pourront pas être récupérées. L'identifiant est stocké dans votre fichier local `config.json` mais n'est pas stocké sur le serveur.

## Étape 6 : Le Rediaccfile

Le **Rediaccfile** est un script Bash qui définit comment vos services sont préparés, démarrés et arrêtés. C'est le mécanisme principal de gestion du cycle de vie des services.

### Qu'est-ce qu'un Rediaccfile ?

Un Rediaccfile est un script Bash contenant jusqu'à trois fonctions : `prep()`, `up()` et `down()`. Il doit être nommé `Rediaccfile` ou `rediaccfile` (insensible à la casse) et placé à l'intérieur du système de fichiers monté du dépôt.

Les Rediaccfiles sont découverts à deux emplacements :
1. La **racine** du chemin de montage du dépôt
2. Les **sous-répertoires de premier niveau** du chemin de montage (non récursif)

Les répertoires cachés (noms commençant par `.`) sont ignorés.

### Fonctions du Cycle de Vie

| Fonction | Quand elle s'exécute | Objectif | Comportement en cas d'erreur |
|----------|---------------------|----------|------------------------------|
| `prep()` | Avant `up()` | Installer les dépendances, récupérer les images, exécuter les migrations | **Arrêt immédiat** -- si un `prep()` échoue, l'ensemble du processus s'arrête immédiatement. |
| `up()` | Après que tous les `prep()` sont terminés | Démarrer les services (par ex., `docker compose up -d`) | L'échec du Rediaccfile racine est **critique** (arrête tout). Les échecs des sous-répertoires sont **non critiques** (journalisés, passage au suivant). |
| `down()` | Lors de l'arrêt | Arrêter les services (par ex., `docker compose down`) | **Au mieux** -- les échecs sont journalisés mais tous les Rediaccfiles sont toujours exécutés. |

Les trois fonctions sont optionnelles. Si une fonction n'est pas définie dans un Rediaccfile, elle est silencieusement ignorée.

### Ordre d'Exécution

- **Démarrage (`up`) :** Rediaccfile racine en premier, puis les sous-répertoires en **ordre alphabétique** (A à Z).
- **Arrêt (`down`) :** Sous-répertoires en **ordre alphabétique inverse** (Z à A), puis la racine en dernier.

### Variables d'Environnement

Lorsqu'une fonction du Rediaccfile s'exécute, les variables d'environnement suivantes sont disponibles :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Chemin de montage du dépôt | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | GUID du dépôt | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ID réseau (entier) | `2816` |
| `DOCKER_HOST` | Socket Docker pour le démon isolé de ce dépôt | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de bouclage pour chaque service défini dans `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Les variables `{SERVICE}_IP` sont auto-générées à partir de `.rediacc.json` (voir Étape 7). La convention de nommage convertit le nom du service en majuscules avec les tirets remplacés par des underscores, puis ajoute `_IP`. Par exemple, `listmonk-app` devient `LISTMONK_APP_IP`.

### Exemple de Rediaccfile

Un Rediaccfile simple pour une application web :

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### Exemple Multi-Services

Pour les projets avec plusieurs groupes de services indépendants, utilisez des sous-répertoires :

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Racine : configuration partagée (par ex., créer les réseaux Docker)
├── docker-compose.yml       # Fichier compose racine
├── database/
│   ├── Rediaccfile          # Services de base de données
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # Serveur API
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

Ordre d'exécution pour `up` : racine, puis `backend`, `database`, `monitoring` (A-Z).
Ordre d'exécution pour `down` : `monitoring`, `database`, `backend`, puis racine (Z-A).

## Étape 7 : Réseau de Services (.rediacc.json)

Chaque dépôt obtient un sous-réseau /26 (64 adresses IP) dans la plage de bouclage `127.x.x.x`. Les services se lient à des adresses IP de bouclage uniques afin de pouvoir fonctionner sur les mêmes ports sans conflits. Par exemple, deux instances PostgreSQL peuvent toutes deux écouter sur le port 5432, chacune sur une adresse IP différente.

### Le Fichier .rediacc.json

Le fichier `.rediacc.json` associe les noms de services à des numéros de **slot**. Chaque slot correspond à une adresse IP unique au sein du sous-réseau du dépôt.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Les services sont écrits par ordre alphabétique.

### Génération Automatique depuis Docker Compose

Vous n'avez pas besoin de créer `.rediacc.json` manuellement. Lorsque vous exécutez `rdc repo up`, Rediacc effectue automatiquement les opérations suivantes :

1. Analyse tous les répertoires contenant un Rediaccfile à la recherche de fichiers compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` ou `compose.yaml`).
2. Extrait les noms de services de la section `services:` de chaque fichier compose.
3. Attribue le prochain slot disponible à tout nouveau service.
4. Enregistre le résultat dans `{repository}/.rediacc.json`.

### Calcul des Adresses IP

L'adresse IP d'un service est calculée à partir de l'ID réseau du dépôt et du slot du service. L'ID réseau est réparti sur les deuxième, troisième et quatrième octets d'une adresse de bouclage `127.x.y.z`. Chaque service reçoit un décalage de `slot + 2` ajouté à l'ID réseau (les décalages 0 et 1 sont réservés pour l'adresse réseau et la passerelle).

Par exemple, avec l'ID réseau `2816` (`0x0B00`), l'adresse de base est `127.0.11.0` et les services commencent à `127.0.11.2`.

**Exemple** pour l'ID réseau `2816` :

| Service | Slot | Adresse IP |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Chaque dépôt prend en charge jusqu'à **61 services** (slots 0 à 60).

### Utilisation des IP de Services dans Docker Compose

Puisque chaque dépôt exécute un démon Docker isolé, les services utilisent `network_mode: host` et se lient à leurs adresses IP de bouclage assignées :

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

Les variables `${POSTGRES_IP}` et `${API_IP}` sont automatiquement exportées depuis `.rediacc.json` lorsque le Rediaccfile s'exécute.

## Étape 8 : Démarrer les Services

Montez le dépôt et démarrez tous les services :

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Requis | Description |
|--------|--------|-------------|
| `-m, --machine <name>` | Oui | Machine cible. |
| `--mount` | Non | Monter le dépôt au préalable s'il n'est pas déjà monté. Sans ce drapeau, le dépôt doit déjà être monté. |
| `--prep-only` | Non | Exécuter uniquement les fonctions `prep()`, ignorer `up()`. Utile pour pré-récupérer les images ou exécuter les migrations. |

La séquence d'exécution est :

1. Monter le dépôt chiffré LUKS (si `--mount` est spécifié)
2. Démarrer le démon Docker isolé pour ce dépôt
3. Générer automatiquement `.rediacc.json` à partir des fichiers compose
4. Exécuter `prep()` dans tous les Rediaccfiles (ordre A-Z, arrêt immédiat en cas d'échec)
5. Exécuter `up()` dans tous les Rediaccfiles (ordre A-Z)

## Étape 9 : Arrêter les Services

Arrêtez tous les services d'un dépôt :

```bash
rdc repo down my-app -m server-1
```

| Option | Requis | Description |
|--------|--------|-------------|
| `-m, --machine <name>` | Oui | Machine cible. |
| `--unmount` | Non | Démonter le dépôt chiffré après l'arrêt des services. Cela arrête également le démon Docker isolé et ferme le volume LUKS. |

La séquence d'exécution est :

1. Exécuter `down()` dans tous les Rediaccfiles (ordre inverse Z-A, au mieux)
2. Arrêter le démon Docker isolé (si `--unmount`)
3. Démonter et fermer le volume chiffré LUKS (si `--unmount`)

## Autres Opérations Courantes

### Monter et Démonter (sans démarrer les services)

```bash
rdc repo mount my-app -m server-1     # Déchiffrer et monter
rdc repo unmount my-app -m server-1   # Démonter et re-chiffrer
```

### Vérifier le Statut du Dépôt

```bash
rdc repo status my-app -m server-1
```

### Lister Tous les Dépôts

```bash
rdc repo list -m server-1
```

### Redimensionner un Dépôt

```bash
rdc repo resize my-app -m server-1 --size 20G    # Définir une taille exacte
rdc repo expand my-app -m server-1 --size 5G      # Ajouter 5 Go à la taille actuelle
```

### Supprimer un Dépôt

```bash
rdc repo delete my-app -m server-1
```

> Ceci détruit définitivement l'image disque chiffrée et toutes les données qu'elle contient.

### Dupliquer (Fork) un Dépôt

Créez une copie d'un dépôt existant dans son état actuel :

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Ceci crée une nouvelle copie chiffrée avec son propre GUID et ID réseau. La copie partage le même identifiant LUKS que le parent.

### Valider un Dépôt

Vérifiez l'intégrité du système de fichiers d'un dépôt :

```bash
rdc repo validate my-app -m server-1
```

## Démarrage Automatique au Boot

Par défaut, les dépôts doivent être montés et démarrés manuellement après un redémarrage du serveur. Le **démarrage automatique** configure les dépôts pour qu'ils se montent automatiquement, démarrent Docker et exécutent le `up()` du Rediaccfile au démarrage du serveur.

### Fonctionnement

Lorsque vous activez le démarrage automatique pour un dépôt :

1. Un fichier de clé LUKS aléatoire de 256 octets est généré et ajouté au slot LUKS 1 du dépôt (le slot 0 reste la phrase secrète utilisateur).
2. Le fichier de clé est stocké dans `{datastore}/.credentials/keys/{guid}.key` avec les permissions `0600` (root uniquement).
3. Un service systemd (`rediacc-autostart`) est installé et s'exécute au démarrage pour monter tous les dépôts activés et démarrer leurs services.

Lors de l'arrêt ou du redémarrage du système, le service arrête gracieusement tous les services (Rediaccfile `down()`), arrête les démons Docker et ferme les volumes LUKS.

> **Note de sécurité :** L'activation du démarrage automatique stocke un fichier de clé LUKS sur le disque du serveur. Toute personne ayant un accès root au serveur peut monter le dépôt sans la phrase secrète. C'est un compromis entre la commodité (démarrage automatique) et la sécurité (saisie manuelle de la phrase secrète requise). Évaluez ceci en fonction de votre modèle de menace.

### Activer le Démarrage Automatique

```bash
rdc repo autostart enable my-app -m server-1
```

La phrase secrète du dépôt vous sera demandée. Elle est nécessaire pour autoriser l'ajout du fichier de clé au volume LUKS.

### Activer le Démarrage Automatique pour Tous les Dépôts

```bash
rdc repo autostart enable-all -m server-1
```

### Désactiver le Démarrage Automatique

```bash
rdc repo autostart disable my-app -m server-1
```

Ceci supprime le fichier de clé et invalide le slot LUKS 1. Le dépôt ne se montera plus automatiquement au démarrage.

### Lister le Statut du Démarrage Automatique

```bash
rdc repo autostart list -m server-1
```

Affiche quels dépôts ont le démarrage automatique activé et si le service systemd est installé.

## Exemple Complet : Déployer une Application Web

Cet exemple de bout en bout déploie une application web avec PostgreSQL, Redis et un serveur API.

### 1. Configurer l'Environnement

```bash
# Installer rdc
curl -fsSL https://get.rediacc.com | sh

# Créer un contexte local
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Enregistrer votre serveur
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Provisionner le serveur
rdc context setup-machine prod-1

# Créer un dépôt chiffré (10 Go)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Monter et Préparer le Dépôt

```bash
rdc repo mount webapp -m prod-1
```

Connectez-vous au serveur en SSH et créez les fichiers de l'application à l'intérieur du dépôt monté. Le chemin de montage est affiché dans la sortie (typiquement `/mnt/rediacc/repos/{guid}`).

### 3. Créer les Fichiers de l'Application

À l'intérieur du dépôt, créez les fichiers suivants :

**docker-compose.yml :**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile :**

```bash
#!/bin/bash

prep() {
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. Tout Démarrer

```bash
rdc repo up webapp -m prod-1
```

Ceci va :
1. Générer automatiquement `.rediacc.json` avec les slots pour `api`, `postgres` et `redis`
2. Exécuter `prep()` pour créer les répertoires et récupérer les images
3. Exécuter `up()` pour démarrer tous les conteneurs

### 5. Activer le Démarrage Automatique

```bash
rdc repo autostart enable webapp -m prod-1
```

Après un redémarrage du serveur, le dépôt se montera automatiquement et démarrera tous les services.

## Comprendre la Configuration du Contexte

Toute la configuration du contexte est stockée dans `~/.rediacc/config.json`. Voici un exemple annoté de ce à quoi ressemble ce fichier après avoir complété les étapes ci-dessus :

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Champs principaux :**

| Champ | Description |
|-------|-------------|
| `mode` | `"local"` pour le mode local, `"s3"` pour les contextes sauvegardés sur S3. |
| `apiUrl` | `"local://"` indique le mode local (pas d'API distante). |
| `ssh.privateKeyPath` | Chemin vers la clé privée SSH utilisée pour toutes les connexions aux machines. |
| `machines.<name>.knownHosts` | Clés d'hôte SSH issues de `ssh-keyscan`, utilisées pour vérifier l'identité du serveur. |
| `repositories.<name>.repositoryGuid` | UUID identifiant l'image disque chiffrée sur le serveur. |
| `repositories.<name>.credential` | Phrase secrète de chiffrement LUKS. **Non stockée sur le serveur.** |
| `repositories.<name>.networkId` | ID réseau déterminant le sous-réseau IP (2816 + n*64). Attribué automatiquement. |

> Ce fichier contient des données sensibles (chemins de clés SSH, identifiants LUKS). Il est stocké avec les permissions `0600` (lecture/écriture propriétaire uniquement). Ne le partagez pas et ne le commitez pas dans un système de contrôle de version.

## Dépannage

### La Connexion SSH Échoue

- Vérifiez que vous pouvez vous connecter manuellement : `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Exécutez `rdc context scan-keys server-1` pour rafraîchir les clés d'hôte
- Vérifiez que le port SSH correspond : `--port 22`

### La Configuration de la Machine Échoue

- Assurez-vous que l'utilisateur a un accès sudo sans mot de passe, ou configurez `NOPASSWD` pour les commandes requises
- Vérifiez l'espace disque disponible sur le serveur
- Exécutez avec `--debug` pour une sortie détaillée : `rdc context setup-machine server-1 --debug`

### La Création du Dépôt Échoue

- Vérifiez que la configuration a été effectuée : le répertoire du datastore doit exister
- Vérifiez l'espace disque sur le serveur
- Assurez-vous que le binaire renet est installé (relancez la configuration si nécessaire)

### Les Services Ne Démarrent Pas

- Vérifiez la syntaxe du Rediaccfile : il doit être du Bash valide
- Assurez-vous que les fichiers `docker compose` utilisent `network_mode: host`
- Vérifiez que les images Docker sont accessibles (envisagez `docker compose pull` dans `prep()`)
- Consultez les journaux des conteneurs : connectez-vous au serveur en SSH et utilisez `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Erreurs de Permission Refusée

- Les opérations sur les dépôts nécessitent l'accès root sur le serveur (renet s'exécute via `sudo`)
- Vérifiez que votre utilisateur est dans le groupe `sudo`
- Vérifiez que le répertoire du datastore a les permissions correctes

## Prochaines Étapes

- **Référence CLI** -- Consultez la page [Application CLI](/fr/docs/cli-application) pour la référence complète des commandes.
- **Sauvegarde et Restauration** -- Configurez des sauvegardes hors site vers un stockage compatible S3 pour la reprise après sinistre.
- **Proxy Inverse** -- Configurez Traefik pour le HTTPS avec des certificats Let's Encrypt automatiques.
- **CRIU Checkpoint/Restore** -- Créez des points de contrôle des conteneurs en cours d'exécution pour une migration ou un retour en arrière instantané.
