---
title: Services
description: >-
  Déployez et gérez des services conteneurisés avec les Rediaccfiles, le réseau
  de services et le démarrage automatique.
category: Guides
order: 5
language: fr
sourceHash: "1eddcf9de8bfac31"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Services

Si vous hésitez sur l'outil a utiliser, consultez [rdc vs renet](/fr/docs/rdc-vs-renet).

Cette page couvre le déploiement et la gestion des services conteneurisés : Rediaccfiles, réseau de services, démarrage/arrêt, opérations en masse et démarrage automatique.

## Le Rediaccfile

Le **Rediaccfile** est un script Bash qui définit comment vos services sont démarrés et arrêtés. Il doit être nommé `Rediaccfile` ou `rediaccfile` (insensible à la casse) et placé à l'intérieur du système de fichiers monté du dépôt.

Les Rediaccfiles sont découverts à deux emplacements :
1. La **racine** du chemin de montage du dépôt
2. Les **sous-répertoires de premier niveau** du chemin de montage (non récursif)

Les répertoires cachés (noms commençant par `.`) sont ignorés.

### Fonctions du cycle de vie

Un Rediaccfile contient jusqu'à deux fonctions :

| Fonction | Quand elle s'exécute | Objectif | Comportement en cas d'erreur |
|----------|---------------------|----------|------------------------------|
| `up()` | Au démarrage | Démarrer les services (par ex., `renet compose -- up -d`) | L'échec du Rediaccfile racine est **critique** (arrête tout). Les échecs des sous-répertoires sont **non critiques** (journalisés, passage au suivant) |
| `down()` | Lors de l'arrêt | Arrêter les services (par ex., `renet compose -- down`) | **Au mieux** -- les échecs sont journalisés mais tous les Rediaccfiles sont toujours exécutés |

Les deux fonctions sont optionnelles. Si une fonction n'est pas définie dans un Rediaccfile, elle est silencieusement ignorée.

### Ordre d'exécution

- **Démarrage (`up`) :** Rediaccfile racine en premier, puis les sous-répertoires en **ordre alphabétique** (A à Z).
- **Arrêt (`down`) :** Sous-répertoires en **ordre alphabétique inverse** (Z à A), puis la racine en dernier.

### Variables d'environnement

Lorsqu'une fonction du Rediaccfile s'exécute, les variables d'environnement suivantes sont disponibles :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Chemin de montage du dépôt | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID du dépôt | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID réseau (entier) | `2816` |
| `DOCKER_HOST` | Socket Docker pour le démon isolé de ce dépôt | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de bouclage pour chaque service défini dans `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Les variables `{SERVICE}_IP` sont auto-générées à partir de `.rediacc.json`. La convention de nommage convertit le nom du service en majuscules avec les tirets remplacés par des underscores, puis ajoute `_IP`. Par exemple, `listmonk-app` devient `LISTMONK_APP_IP`.

> **Attention : N'utilisez pas `sudo docker` dans les Rediaccfiles.** La commande `sudo` réinitialise les variables d'environnement, ce qui signifie que `DOCKER_HOST` est perdu et les commandes Docker cibleront le démon système au lieu du démon isolé du dépôt. Cela casse l'isolation des conteneurs et peut causer des conflits de ports.
>
> Utilisez `renet compose` dans vos Rediaccfiles, il gère automatiquement `DOCKER_HOST`, injecte les labels réseau pour la découverte des routes et configure le réseau des services. Consultez [Réseau](/fr/docs/networking) pour les détails sur l'exposition des services via le proxy inverse. Si vous appelez Docker directement, utilisez `docker` sans `sudo`, les fonctions du Rediaccfile s'exécutent déjà avec les privilèges suffisants. Si vous devez utiliser sudo, utilisez `sudo -E docker` pour préserver les variables d'environnement.

### Exemple

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Important :** Utilisez toujours `renet compose --` au lieu de `docker compose`. Le wrapper `renet compose` impose le réseau hôte, l'allocation d'IP et les labels de découverte de services requis par renet-proxy. Les capacités CRIU checkpoint/restauration sont ajoutées aux conteneurs avec le label `rediacc.checkpoint=true`. L'utilisation directe de `docker compose` est rejetée par la validation du Rediaccfile. Consultez [Réseau](/fr/docs/networking) pour les détails.

### Disposition multi-services

Pour les projets avec plusieurs groupes de services indépendants, utilisez des sous-répertoires :

```
/mnt/rediacc/mounts/my-app/
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

Puisque chaque dépôt exécute un démon Docker isolé, `renet compose` configure automatiquement `network_mode: host` pour tous les services. Le noyau réécrit de façon transparente les appels `bind()` vers l'IP de bouclage assignée au service, de sorte que les services peuvent se lier à `0.0.0.0` ou `localhost` sans conflits. Pour les connexions **vers d'autres services**, utilisez le **nom du service** -- renet injecte chaque nom de service comme nom d'hôte qui résout toujours vers la bonne IP, même dans les forks :

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Pas de listen_addresses explicite nécessaire -- le noyau réécrit bind vers la bonne IP de bouclage

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # utiliser le nom de service
      LISTEN_ADDR: 0.0.0.0:8080                                      # le noyau réécrit vers l'IP du service
```

> **Noms de service pour les connexions :** Utilisez le **nom de service** (p.ex. `postgres`, `redis`) pour **vous connecter à** d'autres services -- renet mappe automatiquement chaque nom de service vers son IP de bouclage via `/etc/hosts`. Intégrer `${POSTGRES_IP}` dans des chaînes de connexion stockées dans des bases de données ou des fichiers de configuration figera l'IP brute, ce qui rompt l'isolation des forks et constitue une **erreur de validation**. Les variables `${SERVICE_IP}` restent disponibles pour un usage explicite, mais la liaison est gérée automatiquement par le noyau.

> **Note :** N'ajoutez pas `network_mode: host` manuellement, `renet compose` l'injecte automatiquement. Les politiques de redémarrage (p.ex., `restart: always`) sont sûres à utiliser, renet les supprime automatiquement pour la compatibilité CRIU et le watchdog du routeur gère la récupération des conteneurs.

### Récupération des conteneurs et politique de redémarrage

renet et Docker ont délibérément des avis divergents sur la façon de gérer les redémarrages de conteneurs. Comprendre cette séparation est important pour diagnostiquer pourquoi un conteneur est ou n'est pas revenu.

**Traduction de la politique de redémarrage.** Lorsque vous écrivez `restart: always` (ou `unless-stopped`, ou `on-failure`) dans votre fichier compose, renet la **supprime** lors de la synthèse du déploiement compose réel et la remplace par `restart: no`. La valeur originale est sauvegardée dans `.rediacc.json` du dépôt sous `services.<name>.restart_policy`. Cela empêche le redémarrage automatique au niveau du démon Docker d'interférer avec CRIU checkpoint/restore (un redémarrage piloté par le démon reprendrait depuis un état antérieur au checkpoint devenu obsolète).

**Application du watchdog.** Le watchdog du routeur s'exécute périodiquement sur chaque machine. À chaque cycle :

1. Il lit `.rediacc.json` pour chaque dépôt et trouve les services avec une `restart_policy` récupérable.
2. Il liste tous les conteneurs du démon de ce dépôt, identifie ceux qui sont arrêtés, et les redémarre selon la politique sauvegardée. Une période de grâce de 30 secondes empêche tout conflit avec un opérateur qui vient d'exécuter `docker stop`.
3. La même boucle traite également `/var/run/rediacc/cold-backup-<guid>.running.json` (voir [Sémantique Cold Backup](backup-restore.md#cold-backup-semantics)). Les conteneurs listés sont redémarrés indépendamment de la politique sauvegardée, car le sidecar signifie "renet a arrêté ces conteneurs intentionnellement et doit à l'opérateur un redémarrage."

**Pourquoi `on-failure` peut sembler cassé.** La politique `on-failure` de Docker redémarre uniquement lorsque le conteneur sort avec un code non nul. Un arrêt propre (exit 0) depuis `docker stop` ou un arrêt du démon n'est pas un "échec" et ne déclenche PAS de redémarrage, ni par la logique native de Docker ni par le chemin de politique sauvegardée du watchdog. Le sidecar cold backup est le filet de sécurité : tout conteneur que nous avons arrêté intentionnellement est redémarré indépendamment de sa politique.

**Comment interpréter l'état d'exécution :**

- `docker inspect <container>` → `RestartPolicy.Name` : sera toujours `no` pour les conteneurs gérés par renet. Ne vous fiez pas à cela pour la politique sémantique.
- `.rediacc.json` à la racine du montage du dépôt → `services.<name>.restart_policy` : l'intention réelle.
- `docker ps --format '{{.Status}}'` : état d'exécution.

**Comment corriger une dérive.** Si la politique sauvegardée dans `.rediacc.json` d'un conteneur est incorrecte (par exemple parce que vous avez modifié compose sans jamais recréer le conteneur), relancez `rdc repo up --name <repo> -m <machine>`. Le conteneur est recréé avec la politique mise à jour enregistrée.

> **Expérimental :** La récupération basée sur le sidecar cold backup et le flag `--sync-certs` sur `rdc machine query` ont été livrés dans renet 0.9+. Les versions antérieures s'appuient uniquement sur la `restart_policy` sauvegardée pour la récupération par watchdog, ce qui peut laisser les conteneurs `on-failure` bloqués après un cold backup.

> **Le réseau bridge Docker est désactivé pour les daemons par dépôt.** Chaque daemon par dépôt (`FlavorRediacc`) est configuré avec `"bridge": "none"` et `"iptables": false`. Un simple `docker run <image>` dans un shell de dépôt se lancera quand même, mais le conteneur n'obtiendra qu'une interface de loopback et ne disposera ni de DNS ni de connectivité sortante. C'est voulu : l'isolation de loopback entre dépôts est appliquée par des hooks cgroup eBPF qu'un conteneur bridgé contournerait. Les services de production doivent utiliser `renet compose` (qui injecte le réseau hôte pour vous) ; pour le débogage ponctuel, passez explicitement `--network host` : `docker run --rm --network host -it ubuntu bash`.
>
> Les daemons Hub par utilisateur (`FlavorHub`, utilisés dans les environnements de développement) font exception : ils définissent `bridge="docker0"`, `iptables=true` et `live-restore=true` afin que les conteneurs lancés par l'utilisateur bénéficient d'un réseau bridge normal et d'une connectivité sortante.

> **Note :** Les repos fork obtiennent des auto-routes sous le sous-domaine du parent : `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Les domaines personnalisés sont ignorés pour les forks.

## Démarrer les services

Montez le dépôt et démarrez tous les services :

```bash
rdc repo up --name my-app -m server-1
```

| Option | Description |
|--------|-------------|
| `--skip-router-restart` | Ne pas redémarrer le serveur de routes après l'opération |

La séquence d'exécution est :
1. Monter le dépôt chiffré LUKS (montage automatique si non monté)
2. Démarrer le démon Docker isolé
3. Générer automatiquement `.rediacc.json` à partir des fichiers compose
4. Exécuter `up()` dans tous les Rediaccfiles (ordre A-Z)

Après le déploiement, la sortie affiche une section **PROXY ROUTES** avec les URLs réelles pour chaque service. Les services avec des labels Traefik personnalisés affichent leurs domaines personnalisés comme URLs principales :

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

## Arrêter les services

```bash
rdc repo down --name my-app -m server-1
```

| Option | Description |
|--------|-------------|
| `--unmount` | Démonter le dépôt chiffré après l'arrêt des services. Si cela ne prend pas effet, utilisez `rdc repo unmount` séparément. |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routes après l'opération |

La séquence d'exécution est :
1. Exécuter `down()` dans tous les Rediaccfiles (ordre inverse Z-A, au mieux)
2. Arrêter le démon Docker isolé (si `--unmount`)
3. Démonter et fermer le volume chiffré LUKS (si `--unmount`)

## Opérations en masse

Démarrez ou arrêtez tous les dépôts d'une machine en une seule fois :

```bash
rdc repo up -m server-1
```

| Option | Description |
|--------|-------------|
| `--include-forks` | Inclure les dépôts dupliqués (forks) |
| `--mount-only` | Monter uniquement, sans démarrer les conteneurs |
| `--dry-run` | Afficher ce qui serait fait |
| `--parallel` | Exécuter les opérations en parallèle |
| `--concurrency <n>` | Nombre maximum d'opérations simultanées (par défaut : 3) |
| `--skip-router-restart` | Ne pas redémarrer le serveur de routes après l'opération |

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
rdc repo autostart enable --name my-app -m server-1
```

La phrase secrète du dépôt vous sera demandée.

### Activer pour tous les dépôts

```bash
rdc repo autostart enable -m server-1
```

### Désactiver

```bash
rdc repo autostart disable --name my-app -m server-1
```

Ceci supprime le fichier de clé et invalide le slot LUKS 1.

### Actualisation du fichier de clé lors du déploiement

Quand le démarrage automatique est activé, `rdc repo up` valide le fichier de clé du slot LUKS 1.
Si le fichier de clé sur disque correspond encore au slot LUKS, aucun changement n'est effectué.

Après avoir transféré un dépôt entre machines via `repo push` / `repo pull`,
le fichier de clé sur la nouvelle machine ne correspondra pas. Dans ce cas, `repo up` régénère automatiquement
le fichier de clé et met à jour le slot LUKS 1. Vous verrez des messages de journal :

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

C'est sans risque, le slot 0 (votre phrase secrète) n'est jamais modifié. Si le démarrage automatique n'est pas
activé, la vérification est silencieusement ignorée. Les échecs sont non fatals et ne bloquent pas le déploiement.

### Lister le statut

```bash
rdc repo autostart list -m server-1
```

## Exemple complet

Cet exemple déploie une application web avec PostgreSQL, Redis et un serveur API.

### 1. Configurer l'environnement

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Monter et préparer

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Créer les fichiers de l'application

À l'intérieur du dépôt, créez les fichiers suivants :

**docker-compose.yml :**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile :**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up --name webapp -m prod-1
```

### 5. Activer le démarrage automatique

```bash
rdc repo autostart enable --name webapp -m prod-1
```
