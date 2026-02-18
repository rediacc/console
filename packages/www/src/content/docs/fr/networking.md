---
title: "Réseau"
description: "Exposez des services avec le proxy inverse, les labels Docker, les certificats TLS, le DNS et la redirection de ports TCP/UDP."
category: "Guides"
order: 6
language: fr
---

# Réseau

Cette page explique comment les services exécutés dans des démons Docker isolés deviennent accessibles depuis Internet. Elle couvre le système de proxy inverse, les labels Docker pour le routage, les certificats TLS, le DNS et la redirection de ports TCP/UDP.

Pour comprendre comment les services obtiennent leurs adresses IP de bouclage et le système de slots `.rediacc.json`, consultez [Services](/fr/docs/services#réseau-de-services-rediaccjson).

## Fonctionnement

Rediacc utilise un système de proxy à deux composants pour router le trafic externe vers les conteneurs :

1. **Serveur de routes** — un service systemd qui découvre les conteneurs en cours d'exécution sur tous les démons Docker des dépôts. Il inspecte les labels des conteneurs et génère la configuration de routage, servie comme un point d'accès YAML.
2. **Traefik** — un proxy inverse qui interroge le serveur de routes toutes les 5 secondes et applique les routes découvertes. Il gère le routage HTTP/HTTPS, la terminaison TLS et la redirection TCP/UDP.

Le flux est le suivant :

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ interroge toutes les 5s
           Serveur de routes (découvre les conteneurs)
               ↓ inspecte les labels
           Démons Docker (/var/run/rediacc/docker-*.sock)
               ↓
           Conteneurs (liés aux IP de bouclage 127.x.x.x)
```

Lorsque vous ajoutez les bons labels à un conteneur et le démarrez avec `renet compose`, il devient automatiquement routable — aucune configuration manuelle du proxy n'est nécessaire.

## Labels Docker

Le routage est contrôlé par les labels des conteneurs Docker. Il existe deux niveaux :

### Niveau 1 : Labels `rediacc.*` (automatiques)

Ces labels sont **automatiquement injectés** par `renet compose` lors du démarrage des services. Vous n'avez pas besoin de les ajouter manuellement.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.service_name` | Identité du service | `myapp` |
| `rediacc.service_ip` | IP de bouclage assignée | `127.0.11.2` |
| `rediacc.network_id` | ID du démon du dépôt | `2816` |

Lorsqu'un conteneur possède uniquement des labels `rediacc.*` (sans `traefik.enable=true`), le serveur de routes génère une **route automatique** :

```
{service}-{networkID}.{baseDomain}
```

Par exemple, un service nommé `myapp` dans un dépôt avec l'ID réseau `2816` et le domaine de base `example.com` obtient :

```
myapp-2816.example.com
```

Les routes automatiques sont utiles pour le développement et l'accès interne. Pour les services de production avec des domaines personnalisés, utilisez les labels de niveau 2.

### Niveau 2 : Labels `traefik.*` (définis par l'utilisateur)

Ajoutez ces labels à votre `docker-compose.yml` lorsque vous souhaitez un routage par domaine personnalisé, le TLS ou des points d'entrée spécifiques. Définir `traefik.enable=true` indique au serveur de routes d'utiliser vos règles personnalisées au lieu de générer une route automatique.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Ceux-ci utilisent la syntaxe standard des [labels Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Astuce :** Les services internes uniquement (bases de données, caches, files de messages) ne devraient **pas** avoir `traefik.enable=true`. Ils n'ont besoin que des labels `rediacc.*`, qui sont injectés automatiquement.

## Exposer des services HTTP/HTTPS

### Prérequis

1. Infrastructure configurée sur la machine ([Configuration de la machine — Configuration de l'infrastructure](/fr/docs/setup#configuration-de-linfrastructure)) :

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. Enregistrements DNS pointant votre domaine vers l'IP publique du serveur (voir [Configuration DNS](#configuration-dns) ci-dessous).

### Ajouter des labels

Ajoutez les labels `traefik.*` aux services que vous souhaitez exposer dans votre `docker-compose.yml` :

```yaml
services:
  myapp:
    image: myapp:latest
    network_mode: host
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    network_mode: host
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # Pas de labels traefik — la base de données est interne uniquement
```

| Label | Objectif |
|-------|----------|
| `traefik.enable=true` | Active le routage Traefik personnalisé pour ce conteneur |
| `traefik.http.routers.{name}.rule` | Règle de routage — typiquement `Host(\`domaine\`)` |
| `traefik.http.routers.{name}.entrypoints` | Ports d'écoute : `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Résolveur de certificats — utilisez `letsencrypt` pour Let's Encrypt automatique |
| `traefik.http.services.{name}.loadbalancer.server.port` | Le port sur lequel votre application écoute à l'intérieur du conteneur |

Le `{name}` dans les labels est un identifiant arbitraire — il doit simplement être cohérent entre les labels de routeur/service/middleware associés.

> **Note :** Les labels `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) sont injectés automatiquement par `renet compose`. Vous n'avez pas besoin de les ajouter à votre fichier compose.

## Certificats TLS

Les certificats TLS sont obtenus automatiquement via Let's Encrypt en utilisant le challenge DNS-01 de Cloudflare. Cela se configure une seule fois lors de la mise en place de l'infrastructure :

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Lorsqu'un service a `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, Traefik effectue automatiquement :
1. La demande d'un certificat auprès de Let's Encrypt
2. La validation de la propriété du domaine via le DNS Cloudflare
3. Le stockage local du certificat
4. Le renouvellement avant expiration

Le jeton API DNS Cloudflare nécessite la permission `Zone:DNS:Edit` pour les domaines que vous souhaitez sécuriser. Cette approche fonctionne pour tout domaine géré par Cloudflare, y compris les certificats wildcard.

## Redirection de ports TCP/UDP

Pour les protocoles non-HTTP (serveurs de messagerie, DNS, bases de données exposées à l'extérieur), utilisez la redirection de ports TCP/UDP.

### Étape 1 : Enregistrer les ports

Ajoutez les ports requis lors de la configuration de l'infrastructure :

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

Ceci crée des points d'entrée Traefik nommés `tcp-{port}` et `udp-{port}`.

> Après avoir ajouté ou supprimé des ports, relancez toujours `rdc context push-infra` pour mettre à jour la configuration du proxy.

### Étape 2 : Ajouter des labels TCP/UDP

Utilisez les labels `traefik.tcp.*` ou `traefik.udp.*` dans votre fichier compose :

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993) — passthrough TLS
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Concepts clés :
- **`HostSNI(\`*\`)`** correspond à n'importe quel nom d'hôte (pour les protocoles qui n'envoient pas de SNI, comme le SMTP en clair)
- **`tls.passthrough=true`** signifie que Traefik transmet la connexion TLS brute sans la déchiffrer — l'application gère le TLS elle-même
- Les noms des points d'entrée suivent la convention `tcp-{port}` ou `udp-{port}`

### Ports pré-configurés

Les ports TCP/UDP suivants ont des points d'entrée par défaut (pas besoin de les ajouter via `--tcp-ports`) :

| Port | Protocole | Utilisation courante |
|------|-----------|---------------------|
| 80 | HTTP | Web (redirection automatique vers HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000–10010 | TCP | Plage dynamique (allocation automatique) |

## Configuration DNS

Pointez vos domaines vers les adresses IP publiques du serveur configurées dans `set-infra` :

### Domaines de services individuels

Créez des enregistrements A (IPv4) et/ou AAAA (IPv6) pour chaque service :

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### Wildcard pour les routes automatiques

Si vous utilisez les routes automatiques (niveau 1), créez un enregistrement DNS wildcard :

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

Cela route tous les sous-domaines vers votre serveur, et Traefik les associe au service correct en fonction de la règle `Host()` ou du nom d'hôte de la route automatique.

## Middlewares

Les middlewares Traefik modifient les requêtes et les réponses. Appliquez-les via des labels.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Mise en tampon pour les gros fichiers

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Middlewares multiples

Chaînez les middlewares en les séparant par des virgules :

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Pour la liste complète des middlewares disponibles, consultez la [documentation des middlewares Traefik](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnostics

Si un service n'est pas accessible, connectez-vous au serveur en SSH et vérifiez les points d'accès du serveur de routes :

### Vérification de l'état

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Affiche le statut général, le nombre de routeurs et services découverts, et si les routes automatiques sont activées.

### Routes découvertes

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Liste tous les routeurs HTTP, TCP et UDP avec leurs règles, points d'entrée et services backend.

### Allocations de ports

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Affiche les mappages de ports TCP et UDP pour les ports alloués dynamiquement.

### Problèmes courants

| Problème | Cause | Solution |
|----------|-------|----------|
| Service absent des routes | Conteneur non démarré ou labels manquants | Vérifiez avec `docker ps` sur le démon du dépôt ; vérifiez les labels |
| Certificat non émis | DNS ne pointant pas vers le serveur, ou jeton Cloudflare invalide | Vérifiez la résolution DNS ; vérifiez les permissions du jeton API Cloudflare |
| 502 Bad Gateway | L'application n'écoute pas sur le port déclaré | Vérifiez que l'application se lie à son `{SERVICE}_IP` et que le port correspond à `loadbalancer.server.port` |
| Port TCP non accessible | Port non enregistré dans l'infrastructure | Exécutez `rdc context set-infra --tcp-ports ...` et `push-infra` |

## Exemple complet

Cet exemple déploie une application web avec une base de données PostgreSQL. L'application est accessible publiquement sur `app.example.com` avec TLS ; la base de données est interne uniquement.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    network_mode: host
    restart: unless-stopped
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Pas de labels traefik — interne uniquement
```

### Rediaccfile

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Créez un enregistrement A pointant `app.example.com` vers l'IP publique de votre serveur :

```
app.example.com   A   203.0.113.50
```

### Déployer

```bash
rdc repo up my-app -m server-1 --mount
```

En quelques secondes, le serveur de routes découvre le conteneur, Traefik récupère la route, demande un certificat TLS, et `https://app.example.com` est en ligne.
