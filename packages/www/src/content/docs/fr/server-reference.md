---
title: "Référence serveur"
description: "Organisation des répertoires, commandes renet, services systemd et procédures pour le serveur distant."
category: "Concepts"
order: 3
language: fr
sourceHash: "f68c27543a2fe3ff"
sourceCommit: "a3b80f4e653e80766813a8c1d7ef563f00904147"
---

# Référence serveur

Cette page décrit ce que vous trouvez lorsque vous vous connectez en SSH à un serveur Rediacc : l'organisation des répertoires, les commandes `renet`, les services systemd et les procédures courantes.

La plupart des utilisateurs gèrent les serveurs via `rdc` depuis leur poste de travail et n'ont pas besoin de cette page. Elle est destinée au débogage avancé ou aux situations où vous devez travailler directement sur le serveur.

Pour l'architecture de haut niveau, consultez [Architecture](/fr/docs/architecture). Pour la différence entre `rdc` et `renet`, consultez [rdc vs renet](/fr/docs/rdc-vs-renet).

## Organisation des répertoires

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## Commandes renet

`renet` est le binaire côté serveur. Toutes les commandes nécessitent les privilèges root (`sudo`).

### Cycle de vie d'un dépôt

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Exécuter des commandes compose contre le daemon Docker d'un dépôt spécifique :

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Exécuter des commandes Docker directement :

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Vous pouvez également utiliser le socket Docker directement :

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Exécutez toujours compose depuis le répertoire qui contient `docker-compose.yml`, sinon Docker ne trouvera pas le fichier.

### Sandbox du système de fichiers

```bash
# Vérifier la prise en charge de Landlock
renet sandbox-exec --detect

# Exécuter une commande dans une sandbox Landlock (utilisée en interne)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` applique les restrictions de système de fichiers Landlock LSM, puis exécute la commande spécifiée. Il est invoqué automatiquement par `sandbox-gateway` (le gestionnaire SSH ForceCommand) pour toutes les connexions au niveau du dépôt.

### Hub par utilisateur (environnements de développement)

Le Hub donne à chaque utilisateur son propre daemon Docker pour les environnements de développement, séparé des daemons `FlavorRediacc` par dépôt.

```bash
# Installer / supprimer les unités systemd du Hub par utilisateur
sudo renet hub install
sudo renet hub uninstall

# Collecter les daemons Hub par utilisateur inactifs
sudo renet hub gc
```

Les daemons fonctionnent sous l'un des deux flavors, sélectionné avec `--flavor` :

```bash
# Daemon isolé par dépôt (bridge=none, iptables=false) — par défaut
sudo renet daemon start-foreground --flavor=rediacc ...

# Daemon Hub par utilisateur (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

Le flavor `hub` active le réseau bridge normal afin que les conteneurs lancés par l'utilisateur disposent d'une connectivité sortante ; le flavor `rediacc` applique l'isolation loopback entre les dépôts. Les journaux d'audit du Hub sont écrits dans `/var/log/rediacc/hub/<user>.log`.

**Drapeaux :**
- `--allow-rw`, `--allow-ro`, `--allow-exec` : règles de chemin Landlock
- `--home-overlay` : monte OverlayFS sur le répertoire home pour isoler les écritures par dépôt
- `--sandbox-dir` : espace de travail par dépôt (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir` : définit le répertoire de travail et charge `.envrc` pour l'environnement du dépôt
- `--run-as` : supprime les privilèges vers l'utilisateur cible après la configuration
- `--reset-home` : efface l'overlay home par dépôt pour repartir de zéro

**`sandbox-gateway`** est le gestionnaire SSH ForceCommand configuré via `command=` dans `authorized_keys`. La clé SSH de chaque dépôt déclenche la passerelle avec le nom du dépôt intégré, que le client ne peut pas falsifier. La passerelle construit les arguments de sandbox-exec et les exécute via sudo.

### Proxy et routage

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Les routes sont découvertes automatiquement à partir des labels des conteneurs. Consultez [Réseau](/fr/docs/networking) pour savoir comment configurer les labels Traefik.

### État du système

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Gestion des daemons

Chaque dépôt exécute son propre daemon Docker. Vous pouvez les gérer individuellement :

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Sauvegarde et restauration

Envoyer des sauvegardes vers une autre machine ou vers un stockage cloud :

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> La plupart des utilisateurs devraient utiliser `rdc repo push/pull` à la place. Les commandes `rdc` gèrent automatiquement les identifiants et la résolution des machines.

### Points de contrôle (CRIU)

Les points de contrôle sauvegardent l'état des conteneurs en cours d'exécution afin de pouvoir les restaurer ultérieurement :

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Maintenance

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Services systemd

Chaque dépôt crée ces unités systemd :

| Unité | Rôle |
|-------|------|
| `rediacc-docker-{id}.service` | Daemon Docker isolé |
| `rediacc-docker-{id}.socket` | Activation du socket de l'API Docker |
| `rediacc-loopback-{id}.service` | Configuration de l'alias IP de loopback |

Services globaux partagés par tous les dépôts :

| Unité | Rôle |
|-------|------|
| `rediacc-router.service` | Découverte des routes (port 7111) |
| `rediacc-autostart.service` | Montage des dépôts au démarrage |
| `rediacc-autostart-reconcile.service` | Réconciliateur de démarrage automatique périodique (exécuté par le timer ci-dessous) |
| `rediacc-autostart-reconcile.timer` | Déclenche `renet repository reconcile` environ toutes les 3 minutes pour récupérer les dépôts autostart tombés après le démarrage |

## Procédures courantes

### Déployer un nouveau service

1. Créer un dépôt chiffré :
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Le monter et y ajouter les fichiers `docker-compose.yml`, `Rediaccfile` et `.rediacc.json`.
3. Le démarrer :
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Accéder à un conteneur en cours d'exécution

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Trouver quel socket Docker exécute un conteneur

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Recréer un service après des changements de configuration

```bash
sudo renet compose -- up -d
```

Exécutez ceci depuis le répertoire contenant `docker-compose.yml`. Les conteneurs modifiés sont automatiquement recréés.

### Vérifier tous les conteneurs sur tous les daemons

```bash
renet list containers
```

## Conseils

- Utilisez toujours `sudo` pour les commandes `renet compose`, `renet repository` et `renet docker`, elles ont besoin de root pour les opérations LUKS et Docker
- Le séparateur `--` est obligatoire avant de passer des arguments à `renet compose` et `renet docker`
- Exécutez compose depuis le répertoire qui contient `docker-compose.yml`
- Les assignations de slots dans `.rediacc.json` sont stables, ne les modifiez pas après le déploiement
- Utilisez les chemins `/run/rediacc/docker-{id}.sock` (systemd peut modifier les anciens chemins `/var/run/`)
- Exécutez `renet prune --dry-run` de temps en temps pour détecter les ressources orphelines
- Les snapshots BTRFS (`renet backup`) sont rapides et peu coûteux, utilisez-les avant d'effectuer des changements risqués
- Les dépôts sont chiffrés avec LUKS, perdre le mot de passe signifie perdre les données
