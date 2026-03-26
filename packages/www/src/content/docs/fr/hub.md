---
title: "Hub"
description: "Fournissez des environnements conteneurisés authentifiés par utilisateur avec provisionnement automatique, gestion de l'inactivité et checkpoint/restauration."
category: "Guides"
order: 14
language: fr
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Le Hub fournit des environnements conteneurisés par utilisateur derrière une authentification OAuth. Les utilisateurs visitent une URL unique, s'authentifient auprès de n'importe quel fournisseur OAuth2 et sont acheminés de manière transparente vers leur conteneur personnel. Les conteneurs sont créés à la demande et gérés automatiquement.

Tout est configuré via les labels `docker-compose.yml`. Le Hub ne connaît pas et ne se soucie pas de ce qui s'exécute dans les conteneurs -- il gère l'authentification, le routage et le cycle de vie. Les dépôts définissent le comportement.

## Fonctionnement

![Architecture du Hub](/img/hub-architecture.svg)

1. Un utilisateur visite `code.example.com`
2. Le Hub vérifie le cookie de session. S'il est absent, l'utilisateur est redirigé vers le fournisseur OAuth2 configuré (Nextcloud, Keycloak, GitHub, etc.)
3. Après l'authentification, le Hub identifie l'utilisateur et recherche son conteneur
4. Si aucun conteneur n'existe, un est créé à la demande à partir du modèle configuré
5. La requête est acheminée par proxy inverse vers le conteneur de l'utilisateur
6. Le Hub détermine le port cible en fonction du nom d'hôte (par ex., `code.` -> port 8080, `term.` -> port 7681)

Les conteneurs inactifs sont automatiquement arrêtés ou sauvegardés par checkpoint (CRIU) pour une restauration instantanée lors de la prochaine connexion.

## Démarrage rapide

Ajoutez le Hub comme service dans le `docker-compose.yml` de votre dépôt :

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # Mappage des routes : préfixe de sous-domaine -> port sur les conteneurs utilisateur
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Modèle de conteneur
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Routes Traefik (une par sous-domaine)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Créez `hub.env` avec les identifiants de votre fournisseur OAuth2 :

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

Déployez avec `rdc repo up`.

## Configuration

Toute la configuration du Hub réside dans les labels Compose du service Hub lui-même. Aucun fichier de configuration à l'intérieur du binaire Hub.

### Mappage des routes

Associez des préfixes de sous-domaine aux ports des conteneurs utilisateur. Le Hub lit ces labels pour savoir où acheminer chaque requête.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Associe `{prefix}.{domain}` à ce port sur le conteneur de l'utilisateur | `rediacc.hub.route.code=8080` |

Vous pouvez définir autant de routes que nécessaire. Le préfixe est comparé au premier segment du nom d'hôte :

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Chaque route nécessite également un routeur Traefik correspondant pointant vers le port du Hub (7112). Le Hub gère le routage par utilisateur en interne.

### Modèle de conteneur

Définissez l'apparence des conteneurs utilisateur. Le Hub lit ces labels et les utilise lors de la création d'un nouveau conteneur pour un utilisateur.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.image` | Image du conteneur | Valeur du flag `--container-image` |
| `rediacc.hub.command` | Commande de démarrage (compatible bash -c) | aucune |
| `rediacc.hub.user` | Utilisateur du conteneur (non-root recommandé) | `vscode` |
| `rediacc.hub.workspace` | Point de montage du workspace dans le conteneur | `/workspace` |
| `rediacc.hub.shm_size` | Taille de la mémoire partagée en octets | `1073741824` (1 Go) |

Le label `command` prend en charge l'expansion `${SERVICE_IP}`, qui est remplacée par l'IP de loopback assignée au conteneur lors de sa création.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **Astuce :** Utilisez `$$` pour un `$` littéral dans les labels Compose afin d'empêcher l'expansion prématurée des variables d'environnement par Docker Compose.

### Limites de ressources

Définissez des limites de ressources par utilisateur pour empêcher un seul utilisateur de consommer toutes les ressources de l'hôte.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Limite CPU (coeurs) | `2` |
| `rediacc.hub.limits.memory` | Limite mémoire | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### Hooks de cycle de vie

Exécutez des commandes dans le conteneur utilisateur à des moments spécifiques du cycle de vie.

| Label | Moment d'exécution | Exemple |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Après la création du conteneur (première connexion) | Cloner des dépôts, installer des dépendances |
| `rediacc.hub.hook.on_start` | Après le démarrage ou la restauration du conteneur | Monter les secrets, rafraîchir les tokens |
| `rediacc.hub.hook.on_idle` | Avant l'arrêt ou le checkpoint du conteneur | Sauvegarder l'état, pousser les modifications |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### Checkpoint / Restauration

Lorsqu'activé, les conteneurs inactifs sont sauvegardés par checkpoint via CRIU au lieu d'être arrêtés. Lors de la prochaine connexion, le conteneur est restauré depuis le checkpoint en quelques secondes, préservant l'état exact : fichiers ouverts, processus en cours, sessions de terminal.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Activer le checkpoint CRIU pour les conteneurs utilisateur | `false` |

Passez également `--checkpoint` lors du démarrage du Hub :

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...autres flags...
```

> **Note :** Le checkpoint/restauration nécessite que le binaire CRIU soit disponible sur l'hôte et que le conteneur fonctionne en mode réseau hôte (la valeur par défaut pour les services Rediacc).

### Contrôle d'accès

Limitez qui peut utiliser le Hub et qui dispose des privilèges administrateur.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Groupes autorisés séparés par des virgules | `developers,ops` |
| `rediacc.hub.admin_users` | Noms d'utilisateur administrateur séparés par des virgules | `alice,bob` |

Les utilisateurs administrateurs peuvent voir et gérer tous les conteneurs dans le tableau de bord. Les utilisateurs réguliers ne voient que les leurs.

### Mode éphémère

Par défaut, les espaces de travail utilisateur sont persistants (survivent aux redémarrages de conteneur). Le mode éphémère fournit un environnement propre à chaque connexion, utile pour les démos, la formation ou le CI.

| Label | Description | Valeur par défaut |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` ou `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

En mode éphémère, l'espace de travail utilise tmpfs (sauvegarde en RAM) et le conteneur est automatiquement supprimé à l'arrêt.

### Support multi-modèles

Proposez plusieurs types d'environnements. Les utilisateurs peuvent choisir leur modèle lors de la première connexion ou changer via le tableau de bord.

```yaml
labels:
  # Modèle par défaut
  - "rediacc.hub.template.default=fulldev"

  # Environnement de développement complet
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # Option légère
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## Configuration OAuth

Le Hub fonctionne avec n'importe quel fournisseur OAuth2 standard. La configuration se fait via des variables d'environnement, pas des labels Compose (les secrets ne doivent pas figurer dans les labels).

| Variable | Description | Requis |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID client OAuth2 | Oui |
| `HUB_OAUTH_CLIENT_SECRET` | Secret client OAuth2 | Oui |
| `HUB_OAUTH_AUTHORIZE_URL` | Point de terminaison d'autorisation du fournisseur | Oui |
| `HUB_OAUTH_TOKEN_URL` | Point de terminaison de token du fournisseur | Oui |
| `HUB_OAUTH_USERINFO_URL` | Point de terminaison d'information utilisateur du fournisseur | Oui |
| `HUB_OAUTH_USERINFO_PATH` | Chemin à points pour extraire le nom d'utilisateur de la réponse JSON | Oui |
| `HUB_OAUTH_REDIRECT_URI` | Remplacer l'URL de callback (calculé automatiquement si vide) | Non |
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

Le `HUB_OAUTH_USERINFO_PATH` est un chemin séparé par des points dans la réponse JSON. Pour les objets imbriqués comme celui de Nextcloud `{"ocs":{"data":{"id":"alice"}}}`, utilisez `ocs.data.id`.

## Tableau de bord

Le Hub inclut un tableau de bord en libre-service à `/_hub/dashboard`. Il affiche :

- Tous les environnements en cours d'exécution avec leur statut
- Liens vers les services (un clic pour ouvrir le code, le terminal ou le bureau)
- Minuteurs d'inactivité et utilisation des ressources
- Contrôles de démarrage/arrêt
- Les administrateurs peuvent voir et gérer tous les conteneurs

Accédez au tableau de bord en visitant `https://code.example.com/_hub/dashboard` après authentification.

## Exemples

### Environnement de développement (VS Code + Terminal + Bureau)

Un environnement de développement complet avec OpenVSCode Server, un terminal web (ttyd) et un bureau noVNC :

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Environnement Jupyter Notebook

Un environnement de science des données avec JupyterLab :

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### Application web simple

Un environnement à service unique pour un framework web :

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guides associés

- [**Services**](/fr/docs/services) -- Cycle de vie Rediaccfile, modèles Compose
- [**Réseau**](/fr/docs/networking) -- Labels Docker, routage Traefik, certificats TLS
- [**Sauvegarde et restauration**](/fr/docs/backup-restore) -- Persistance et récupération des espaces de travail
- [**Environnements de développement**](/fr/docs/development-environments) -- Clonage de production pour les environnements de développement
