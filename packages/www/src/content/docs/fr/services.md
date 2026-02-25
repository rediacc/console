---
title: Services
description: >-
  Déployez et gérez des services conteneurisés avec les Rediaccfiles, le réseau
  de services et le démarrage automatique.
category: Guides
order: 5
language: fr
sourceHash: 294f92dc32f10c86
---

# Services

Si vous hésitez sur l'outil a utiliser, consultez [rdc vs renet](/fr/docs/rdc-vs-renet).

Cette page couvre le déploiement et la gestion des services conteneurisés : Rediaccfiles, réseau de services, démarrage/arrêt, opérations en masse et démarrage automatique.

## Le Rediaccfile

Le **Rediaccfile** est un script Bash qui définit comment vos services sont préparés, démarrés et arrêtés. Il doit être nommé `Rediaccfile` ou `rediaccfile` (insensible à la casse) et placé à l'intérieur du système de fichiers monté du dépôt.

Les Rediaccfiles sont découverts à deux emplacements :
1. La **racine** du chemin de montage du dépôt
2. Les **sous-répertoires de premier niveau** du chemin de montage (non récursif)

Les répertoires cachés (noms commençant par `.`) sont ignorés.

### Fonctions du cycle de vie

Un Rediaccfile contient jusqu'à trois fonctions :

| Fonction | Quand elle s'exécute | Objectif | Comportement en cas d'erreur |
|----------|---------------------|----------|------------------------------|
| `prep()` | Avant `up()` | Installer les dépendances, récupérer les images, exécuter les migrations | **Arrêt immédiat** -- si un `prep()` échoue, l'ensemble du processus s'arrête immédiatement |
| `up()` | Après que tous les `prep()` sont terminés | Démarrer les services (par ex., `docker compose up -d`) | L'échec du Rediaccfile racine est **critique** (arrête tout). Les échecs des sous-répertoires sont **non critiques** (journalisés, passage au suivant) |
| `down()` | Lors de l'arrêt | Arrêter les services (par ex., `docker compose down`) | **Au mieux** -- les échecs sont journalisés mais tous les Rediaccfiles sont toujours exécutés |

Les trois fonctions sont optionnelles. Si une fonction n'est pas définie dans un Rediaccfile, elle est silencieusement ignorée.

### Ordre d'exécution

- **Démarrage (`up`) :** Rediaccfile racine en premier, puis les sous-répertoires en **ordre alphabétique** (A à Z).
- **Arrêt (`down`) :** Sous-répertoires en **ordre alphabétique inverse** (Z à A), puis la racine en dernier.

### Variables d'environnement

Lorsqu'une fonction du Rediaccfile s'exécute, les variables d'environnement suivantes sont disponibles :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Chemin de montage du dépôt | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | GUID du dépôt | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ID réseau (entier) | `2816` |
| `DOCKER_HOST` | Socket Docker pour le démon isolé de ce dépôt | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de bouclage pour chaque service défini dans `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Les variables `{SERVICE}_IP` sont auto-générées à partir de `.rediacc.json`. La convention de nommage convertit le nom du service en majuscules avec les tirets remplacés par des underscores, puis ajoute `_IP`. Par exemple, `listmonk-app` devient `LISTMONK_APP_IP`.

> **Attention : N'utilisez pas `sudo docker` dans les Rediaccfiles.** La commande `sudo` réinitialise les variables d'environnement, ce qui signifie que `DOCKER_HOST` est perdu et les commandes Docker cibleront le démon système au lieu du démon isolé du dépôt. Cela casse l'isolation des conteneurs et peut causer des conflits de ports.
>
> Utilisez `renet compose` dans vos Rediaccfiles — il gère automatiquement `DOCKER_HOST`, injecte les labels réseau pour la découverte des routes et configure le réseau des services. Consultez [Réseau](/fr/docs/networking) pour les détails sur l'exposition des services via le proxy inverse. Si vous appelez Docker directement, utilisez `docker` sans `sudo` — les fonctions du Rediaccfile s'exécutent déjà avec les privilèges suffisants. Si vous devez utiliser sudo, utilisez `sudo -E docker` pour préserver les variables d'environnement.

### Exemple

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` fonctionne aussi puisque `DOCKER_HOST` est défini automatiquement, mais `renet compose` est préféré car il injecte en plus les labels `rediacc.*` nécessaires à la découverte des routes du proxy inverse. Consultez [Réseau](/fr/docs/networking) pour les détails.

### Disposition multi-services

Pour les projets avec plusieurs groupes de services indépendants, utilisez des sous-répertoires :

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Racine : configuration partagée
├── docker-compose.yml
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

## Réseau de services (.rediacc.json)

Chaque dépôt obtient un sous-réseau /26 (64 adresses IP) dans la plage de bouclage `127.x.x.x`. Les services se lient à des adresses IP de bouclage uniques afin de pouvoir fonctionner sur les mêmes ports sans conflits.

### Le fichier .rediacc.json

Associe les noms de services à des numéros de **slot**. Chaque slot correspond à une adresse IP unique au sein du sous-réseau du dépôt.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Génération automatique depuis Docker Compose

Vous n'avez pas besoin de créer `.rediacc.json` manuellement. Lorsque vous exécutez `rdc repo up`, Rediacc effectue automatiquement les opérations suivantes :

1. Analyse tous les répertoires contenant un Rediaccfile à la recherche de fichiers compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` ou `compose.yaml`)
2. Extrait les noms de services de la section `services:`
3. Attribue le prochain slot disponible à tout nouveau service
4. Enregistre le résultat dans `{repository}/.rediacc.json`

### Calcul des adresses IP

L'adresse IP d'un service est calculée à partir de l'ID réseau du dépôt et du slot du service. L'ID réseau est réparti sur les deuxième, troisième et quatrième octets d'une adresse de bouclage `127.x.y.z`. Chaque service reçoit un décalage de `slot + 2` (les décalages 0 et 1 sont réservés).

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Exemple** pour l'ID réseau `2816` (`0x0B00`), adresse de base `127.0.11.0` :

| Service | Slot | Adresse IP |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Chaque dépôt prend en charge jusqu'à **61 services** (slots 0 à 60).

### Utilisation des IP de services dans Docker Compose

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

## Démarrer les services

Montez le dépôt et démarrez tous les services :

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Description |
|--------|-------------|
| `--mount` | Monter le dépôt au préalable s'il n'est pas déjà monté |
| `--prep-only` | Exécuter uniquement les fonctions `prep()`, ignorer `up()` |
| `--skip-router-restart` | Skip restarting the route server after the operation |

La séquence d'exécution est :
1. Monter le dépôt chiffré LUKS (si `--mount`)
2. Démarrer le démon Docker isolé
3. Générer automatiquement `.rediacc.json` à partir des fichiers compose
4. Exécuter `prep()` dans tous les Rediaccfiles (ordre A-Z, arrêt immédiat en cas d'échec)
5. Exécuter `up()` dans tous les Rediaccfiles (ordre A-Z)

## Arrêter les services

```bash
rdc repo down my-app -m server-1
```

| Option | Description |
|--------|-------------|
| `--unmount` | Démonter le dépôt chiffré après l'arrêt des services. Si cela ne prend pas effet, utilisez `rdc repo unmount` séparément. |
| `--skip-router-restart` | Skip restarting the route server after the operation |

La séquence d'exécution est :
1. Exécuter `down()` dans tous les Rediaccfiles (ordre inverse Z-A, au mieux)
2. Arrêter le démon Docker isolé (si `--unmount`)
3. Démonter et fermer le volume chiffré LUKS (si `--unmount`)

## Opérations en masse

Démarrez ou arrêtez tous les dépôts d'une machine en une seule fois :

```bash
rdc repo up-all -m server-1
```

| Option | Description |
|--------|-------------|
| `--include-forks` | Inclure les dépôts dupliqués (forks) |
| `--mount-only` | Monter uniquement, sans démarrer les conteneurs |
| `--dry-run` | Afficher ce qui serait fait |
| `--parallel` | Exécuter les opérations en parallèle |
| `--concurrency <n>` | Nombre maximum d'opérations simultanées (par défaut : 3) |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Démarrage automatique au boot

Par défaut, les dépôts doivent être montés et démarrés manuellement après un redémarrage du serveur. Le **démarrage automatique** configure les dépôts pour qu'ils se montent automatiquement, démarrent Docker et exécutent le `up()` du Rediaccfile au démarrage du serveur.

### Fonctionnement

Lorsque vous activez le démarrage automatique pour un dépôt :

1. Un fichier de clé LUKS aléatoire de 256 octets est généré et ajouté au slot LUKS 1 du dépôt (le slot 0 reste la phrase secrète utilisateur)
2. Le fichier de clé est stocké dans `{datastore}/.credentials/keys/{guid}.key` avec les permissions `0600` (root uniquement)
3. Un service systemd (`rediacc-autostart`) est installé et s'exécute au démarrage pour monter tous les dépôts activés et démarrer leurs services

Lors de l'arrêt ou du redémarrage du système, le service arrête gracieusement tous les services (Rediaccfile `down()`), arrête les démons Docker et ferme les volumes LUKS.

> **Note de sécurité :** L'activation du démarrage automatique stocke un fichier de clé LUKS sur le disque du serveur. Toute personne ayant un accès root au serveur peut monter le dépôt sans la phrase secrète. Évaluez ceci en fonction de votre modèle de menace.

### Activer

```bash
rdc repo autostart enable my-app -m server-1
```

La phrase secrète du dépôt vous sera demandée.

### Activer pour tous les dépôts

```bash
rdc repo autostart enable-all -m server-1
```

### Désactiver

```bash
rdc repo autostart disable my-app -m server-1
```

Ceci supprime le fichier de clé et invalide le slot LUKS 1.

### Lister le statut

```bash
rdc repo autostart list -m server-1
```

## Exemple complet

Cet exemple déploie une application web avec PostgreSQL, Redis et un serveur API.

### 1. Configurer l'environnement

```bash
curl -fsSL https://get.rediacc.com | sh
rdc config init production --ssh-key ~/.ssh/id_ed25519
rdc config add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc config setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Monter et préparer

```bash
rdc repo mount webapp -m prod-1
```

### 3. Créer les fichiers de l'application

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
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
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
    renet compose -- down
}
```

### 4. Démarrer

```bash
rdc repo up webapp -m prod-1
```

### 5. Activer le démarrage automatique

```bash
rdc repo autostart enable webapp -m prod-1
```
