---
title: "Hub"
description: "Fournit des environnements de conteneurs par utilisateur avec authentification, Docker daemons par utilisateur, sélection de modèles multiples, checkpoint/restauration CRIU, journaux d'audit et collecte des déchets des data-roots."
category: "Guides"
order: 14
language: fr
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Le Hub fournit des environnements de conteneurs par utilisateur derrière une authentification OAuth. Les utilisateurs visitent une seule URL, s'authentifient auprès de n'importe quel fournisseur OAuth2 et sont acheminés de manière transparente vers leur conteneur personnel. Les conteneurs sont créés à la demande, chaque utilisateur dispose de son propre Docker daemon isolé, et les sessions inactives sont sauvegardées par checkpoint CRIU pour une reprise instantanée.

Tout est configuré via des labels `docker-compose.yml`. Le Hub lui-même s'exécute en tant que service systemd hôte matérialisé par la commande `renet hub install` depuis le fichier Compose de votre dépôt. Les dépôts définissent le comportement ; le Hub gère l'authentification, le routage, le cycle de vie et l'isolation par utilisateur.

## Fonctionnement

1. Un utilisateur visite `code.example.com` (ou `term.`, `desktop.`, ou tout autre préfixe configuré).
2. Le Hub vérifie le cookie de session. S'il est absent, l'utilisateur est redirigé vers le fournisseur OAuth2 configuré (Nextcloud, Keycloak, GitHub, etc.).
3. Après l'authentification, le Hub identifie l'utilisateur et recherche son conteneur.
4. Si aucun conteneur n'existe, le Hub provisionne un Docker daemon dédié pour cet utilisateur sur l'hôte, puis crée son conteneur.
5. La requête est transmise en proxy inverse au conteneur de l'utilisateur via le réseau loopback.
6. Les conteneurs inactifs sont sauvegardés par checkpoint CRIU et leur daemon par utilisateur est arrêté pour libérer de la mémoire. À la prochaine connexion, le daemon redémarre et CRIU restaure l'état du conteneur en quelques secondes.

## Démarrage rapide

Ajoutez le Hub en tant que service dans le `docker-compose.yml` de votre dépôt. Le service est marqué `install_as=systemd` pour qu'il s'exécute en tant que service hôte plutôt que comme conteneur Docker (nécessaire pour la gestion des daemons par utilisateur, qui utilise systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Mappage des routes : préfixe de sous-domaine -> port sur les conteneurs utilisateur
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Modèle de conteneur
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Routes Traefik (fournisseur de fichier ; rediacc-router lit aussi ces labels)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Créez `hub/.env` avec les identifiants de votre fournisseur OAuth2 :

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Installez l'unité systemd hôte (une seule fois, nécessite root) :

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Cela lit les services `install_as=systemd` et écrit :

- `/etc/systemd/system/rediacc-hub.service` (l'unité)
- `/etc/rediacc/hub/hub.labels.yaml` (les labels de modèle)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (routes du fournisseur de fichier Traefik)

Puis `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Pour supprimer : `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Référence de la commande install

| Commande | Rôle |
|---------|---------|
| `sudo renet hub install <compose-file>` | Traduire les services `install_as=systemd` du fichier Compose en artefacts hôtes et démarrer l'unité. |
| `sudo renet hub uninstall <compose-file>` | Arrêter, désactiver et supprimer tous les artefacts des services. Les data-roots sous `<workspace>/<user>-docker/` sont conservés. |
| `sudo renet hub gc <workspace-dir>` | Nettoyer les data-roots par utilisateur abandonnés (par défaut : plus de 30 jours sans daemon actif). Flags : `--max-age=30d`, `--dry-run`. |
| `renet hub status` | Statut JSON de tous les conteneurs via l'API du Hub en cours d'exécution. |
| `renet hub stop <username>` | Arrêter le conteneur d'un utilisateur spécifique. |

## Configuration

Toute la configuration du Hub réside dans les labels Compose du service Hub. Les secrets (OAuth client_secret, session_secret) vont dans `hub/.env`, pas dans les labels.

### Mappage des routes

Mappez les préfixes de sous-domaine aux ports des conteneurs utilisateur. Le Hub lit ces labels pour savoir où transmettre chaque requête.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Mappe `{prefix}.{domain}` vers ce port sur le conteneur de l'utilisateur | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Chaque route nécessite également un routeur Traefik correspondant pointant vers le port du Hub (7112). Le Hub gère le routage par utilisateur en interne en fonction du nom d'hôte.

### Modèle de conteneur

Définissez l'apparence des conteneurs utilisateur. Le Hub lit ces labels et les utilise lors de la création d'un nouveau conteneur.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.image` | Image du conteneur | Valeur du flag `--container-image` |
| `rediacc.hub.command` | Commande de démarrage (compatible bash -c) | aucune |
| `rediacc.hub.user` | Utilisateur du conteneur (non-root recommandé) | `vscode` |
| `rediacc.hub.workspace` | Point de montage du workspace dans le conteneur | `/workspace` |
| `rediacc.hub.shm_size` | Taille de la mémoire partagée en octets | `1073741824` (1 Go) |
| `rediacc.hub.docker` | `per-user` pour provisionner un dockerd dédié par utilisateur (fortement recommandé) | `""` |

Le label `command` prend en charge l'expansion de `${SERVICE_IP}` et `__SERVICE_IP__` (ce dernier évite la pré-expansion de Compose) pour l'IP loopback attribuée au conteneur.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Docker daemon par utilisateur

Lorsque `rediacc.hub.docker=per-user` est défini, chaque utilisateur obtient une instance `dockerd` dédiée sur l'hôte, montée comme `/var/run/docker.sock` dans son conteneur. Cela offre :

- `docker ps`, `docker run`, `docker build` complets dans l'environnement utilisateur sans conteneurs privilégiés ni Docker-in-Docker.
- Isolation complète entre les utilisateurs (l'utilisateur A ne peut pas voir les conteneurs ou images de l'utilisateur B).
- Un data-root BTRFS par utilisateur dans `<workspace-dir>/<user>-docker/.rediacc/docker/data`, conservé entre les sessions afin que les images en cache survivent aux cycles de checkpoint inactif.

Les daemons sont alloués dans une plage d'identifiants réseau dédiée commençant à 32768. Un fichier marqueur `.networkid` dans le data-root de chaque utilisateur enregistre son identifiant attribué afin que les utilisateurs récurrents retrouvent le même daemon.

### Limites de ressources

Définissez des limites de ressources par utilisateur pour éviter qu'un seul utilisateur consomme toutes les ressources de l'hôte. Les limites s'appliquent à la fois au conteneur de l'utilisateur et à son instance dockerd par utilisateur (via systemd `CPUQuota=` / `MemoryMax=`).

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Valeur systemd CPUQuota | `200%` (2 cœurs) |
| `rediacc.hub.limits.memory` | Valeur systemd MemoryMax | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Les daemons sont placés dans le slice systemd `rediacc.slice` afin d'hériter des limites au niveau du slice.

### Support multi-modèles

Proposez plusieurs types d'environnement. Les utilisateurs choisissent un modèle à la connexion en visitant `https://code.example.com/_hub/login?template=python` (la sélection transite par l'état OAuth). Changer de modèle lors des connexions suivantes reconstruit le conteneur.

Définissez les modèles avec des labels `rediacc.hub.templates.<name>.<field>`. Les labels plats `rediacc.hub.image` / `rediacc.hub.command` / etc. continuent de définir le modèle "par défaut" implicite pour les utilisateurs qui n'en choisissent pas.

```yaml
labels:
  # Le modèle par défaut quand ?template=... est omis.
  - "rediacc.hub.template=fulldev"

  # Un environnement complet VS Code + bureau + terminal.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # VS Code uniquement, léger.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Environnement spécifique Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Hooks de cycle de vie

Exécutez des commandes dans le conteneur utilisateur à des points du cycle de vie. Les hooks s'exécutent en tant qu'utilisateur du conteneur (pas root).

| Label | Quand il s'exécute | Exemple |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Après la création du conteneur (première connexion) | Cloner des dépôts, installer des dépendances |
| `rediacc.hub.hook.checkpoint.pre_dump` | Avant le checkpoint CRIU d'une session inactive | Arrêter les daemons qui ne peuvent pas être sauvegardés (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Après la restauration CRIU | Redémarrer les daemons arrêtés dans pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restauration

Lorsque `--checkpoint` est défini, les conteneurs utilisateur inactifs sont sauvegardés par checkpoint CRIU et leur daemon par utilisateur est arrêté pour libérer de la mémoire. À la prochaine connexion, le daemon redémarre et CRIU restaure l'état du conteneur depuis le disque, en préservant les fichiers ouverts, les processus en cours d'exécution et les sessions de terminal. Le temps de reprise typique est de quelques secondes quelle que soit la charge de travail.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Activer le checkpoint CRIU pour les conteneurs utilisateur | `false` |

Passez `--checkpoint` et un `--idle-timeout` non nul (par exemple `30m`) dans la commande du Hub. Les répertoires de checkpoint se trouvent dans `<workspace-dir>/<user>/.checkpoint/`.

Si CRIU échoue 3 fois de suite pour un utilisateur, le checkpoint est désactivé pour cet utilisateur et le repli devient arrêt-et-recréation.

### Mode éphémère

Par défaut, les workspaces utilisateur sont persistants (survivent aux redémarrages). Le mode éphémère fournit un environnement propre à chaque connexion, utile pour les démos, la formation ou le CI.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` ou `ephemeral` | `persistent` |

En mode éphémère, le workspace utilise tmpfs (sauvegardé en RAM) et le conteneur est automatiquement supprimé à l'arrêt.

### Timeout d'inactivité

| Flag | Description | Valeur par défaut |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Arrêter/sauvegarder les conteneurs inactifs depuis plus longtemps que cette durée | `0` (désactivé) |

`0` garde les conteneurs actifs indéfiniment. Une valeur pratique est `30m` : les utilisateurs inactifs libèrent de la mémoire après une demi-heure, et les utilisateurs qui reviennent reprennent en quelques secondes via CRIU.

### Contrôle d'accès

| Variable | Description |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Groupes séparés par des virgules autorisés à utiliser le Hub (quand votre fournisseur expose des claims de groupe) |
| `HUB_ADMIN_USERS` | Noms d'utilisateur administrateurs séparés par des virgules. Les admins voient et contrôlent les conteneurs des autres utilisateurs dans le tableau de bord. |

## Journal d'audit

Chaque événement de conteneur/image initié par l'utilisateur (create, start, stop, destroy, kill, pull, push) sur le daemon par utilisateur est ajouté comme enregistrement JSON délimité par des lignes dans `/var/log/rediacc/hub/<user>.log` :

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Les entrées survivent au checkpoint/restauration CRIU (le flux d'audit est réarmé à la restauration). Utilisez `logrotate` pour limiter l'utilisation du disque ; un exemple de configuration :

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Tableau de bord

Le Hub inclut un tableau de bord en libre-service sur `/_hub/dashboard`. Il affiche :

- Tous les environnements en cours d'exécution avec leur statut
- Modèle sélectionné
- Liens de service (un clic pour ouvrir le code, le terminal, le bureau ou toute autre route)
- Minuteries d'inactivité
- Utilisation du disque par utilisateur, nombre de conteneurs en cours d'exécution et nombre d'images
- Les admins voient tous les conteneurs ; les utilisateurs ordinaires voient seulement les leurs

Les statistiques sont échantillonnées toutes les 30 secondes.

## Collecte des déchets des data-roots

Les data-roots par utilisateur s'accumulent sur les hôtes à longue durée de vie. Planifiez `renet hub gc` pour nettoyer les abandonnés. Un timer systemd convient bien :

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` enregistre les candidats sans les supprimer. Un data-root est éligible quand son fichier marqueur `.networkid` est plus ancien que `--max-age` ET que le daemon enregistré n'est plus configuré sur l'hôte.

## Configuration OAuth

Le Hub fonctionne avec n'importe quel fournisseur OAuth2 standard. La configuration se fait via des variables d'environnement.

| Variable | Description | Requis |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID client OAuth2 | Oui |
| `HUB_OAUTH_CLIENT_SECRET` | Secret client OAuth2 | Oui |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint d'autorisation du fournisseur | Oui |
| `HUB_OAUTH_TOKEN_URL` | Endpoint de token du fournisseur | Oui |
| `HUB_OAUTH_USERINFO_URL` | Endpoint userinfo du fournisseur | Oui |
| `HUB_OAUTH_USERINFO_PATH` | Chemin pointé pour extraire le nom d'utilisateur de la réponse JSON | Oui |
| `HUB_OAUTH_REDIRECT_URI` | Remplacer l'URL de callback (calculée automatiquement si vide) | Non |
| `HUB_OAUTH_SCOPES` | Scopes supplémentaires (séparés par des espaces) | Non |
| `HUB_SESSION_SECRET` | Chaîne hexadécimale de 32+ octets pour la signature des cookies | Recommandé |

### Exemples de fournisseurs

**Nextcloud :**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak :**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub :**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` est un chemin séparé par des points dans la réponse JSON. Pour les objets imbriqués comme `{"ocs":{"data":{"id":"alice"}}}` de Nextcloud, utilisez `ocs.data.id`.

## Exemples

### Environnement de développement (VS Code + Terminal + Bureau)

Un environnement de développement complet avec OpenVSCode Server, un terminal web (ttyd) et un bureau noVNC. Les utilisateurs ont leur propre Docker daemon à l'intérieur.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Routeurs Traefik pour chaque préfixe ...
```

### Environnement Jupyter Notebook

Un environnement de science des données avec JupyterLab :

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Application web simple (Éphémère)

Un environnement à service unique qui repart de zéro à chaque connexion :

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guides associés

- [**Services**](/fr/docs/services) -- Cycle de vie Rediaccfile, modèles Compose
- [**Réseau**](/fr/docs/networking) -- Labels Docker, routage Traefik, certificats TLS
- [**Sauvegarde et restauration**](/fr/docs/backup-restore) -- Persistance du workspace et récupération
- [**Environnements de développement**](/fr/docs/development-environments) -- Clonage de production pour les environnements de développement
