---
title: Réseau
description: >-
  Exposez des services avec le proxy inverse, les labels Docker, les certificats
  TLS, le DNS et la redirection de ports TCP/UDP.
category: Guides
order: 6
language: fr
sourceHash: 5f8a1092ed53e1b4
sourceCommit: 8b0f83c57ebaaa0a2bee93143db34ab677b4e68b
---

# Réseau

Cette page explique comment les services exécutés dans des démons Docker isolés deviennent accessibles depuis Internet. Elle couvre le système de proxy inverse, les labels Docker pour le routage, les certificats TLS, le DNS et la redirection de ports TCP/UDP.

Pour comprendre comment les services obtiennent leurs adresses IP de bouclage et le système de slots `.rediacc.json`, consultez [Services](/fr/docs/services#réseau-de-services-rediaccjson).

## Isolation Réseau

Chaque dépôt est automatiquement isolé au niveau du noyau via des hooks réseau. Cela nécessite Linux kernel 6.1 ou ultérieur. Aucune configuration n'est nécessaire.

- **Réécriture automatique des binds**: Les services peuvent se lier à `0.0.0.0` ou `127.0.0.1` comme d'habitude. Le noyau réécrit de manière transparente l'adresse vers l'IP de bouclage assignée au service. Pas besoin de se lier explicitement à `${SERVICE_IP}`.
- **Blocage des connexions inter-dépôts**: Si un service tente de se connecter à une IP de bouclage hors du sous-réseau `/26` de son dépôt, le noyau le bloque. Un processus dans le dépôt A ne peut pas atteindre les services du dépôt B.
- **Aucun changement d'application requis**: Les services utilisent `0.0.0.0` ou `localhost` pour le binding, et le noyau garantit qu'ils n'écoutent que sur leur IP de bouclage correcte. L'isolation est entièrement transparente.

## Fonctionnement

Rediacc utilise un système de proxy à deux composants pour router le trafic externe vers les conteneurs :

1. **Serveur de routes**, un service systemd qui découvre les conteneurs en cours d'exécution sur tous les démons Docker des dépôts. Il inspecte les labels des conteneurs et génère la configuration de routage, servie comme un point d'accès YAML.
2. **Traefik**, un proxy inverse qui interroge le serveur de routes toutes les 5 secondes et applique les routes découvertes. Il gère le routage HTTP/HTTPS, la terminaison TLS et la redirection TCP/UDP.

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

Lorsque vous ajoutez les bons labels à un conteneur et le démarrez avec `renet compose`, il devient automatiquement routable, aucune configuration manuelle du proxy n'est nécessaire.

> Le binaire du serveur de routes est maintenu synchronisé avec la version de votre CLI. Lorsque la CLI met à jour le binaire renet sur une machine, le serveur de routes est automatiquement redémarré (~1-2 secondes). Cela ne cause aucune interruption, Traefik continue de servir le trafic avec sa dernière configuration connue pendant le redémarrage et prend en compte la nouvelle configuration au prochain sondage. Les connexions clientes existantes ne sont pas affectées. Vos conteneurs d'application ne sont pas touchés.

## Labels Docker

Le routage est contrôlé par les labels des conteneurs Docker. Il existe deux niveaux :

### Niveau 1 : Labels `rediacc.*` (automatiques)

Ces labels sont **automatiquement injectés** par `renet compose` lors du démarrage des services. Vous n'avez pas besoin de les ajouter manuellement.

| Label | Description | Exemple |
|-------|-------------|---------|
| `rediacc.service_name` | Identité du service | `myapp` |
| `rediacc.service_ip` | IP de bouclage assignée | `127.0.11.2` |
| `rediacc.network_id` | ID du démon du dépôt | `2816` |
| `rediacc.repo_name` | Nom du dépôt | `marketing` |
| `rediacc.tcp_ports` | Ports TCP sur lesquels le service écoute | `8080,8443` |
| `rediacc.udp_ports` | Ports UDP sur lesquels le service écoute | `53` |

Lorsqu'un conteneur possède uniquement des labels `rediacc.*` (sans `traefik.enable=true`), le serveur de routes génère une **route automatique** en utilisant le nom du dépôt et le sous-domaine de la machine :

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Par exemple, un service nommé `myapp` dans un dépôt appelé `marketing` sur la machine `server-1` avec le domaine de base `example.com` obtient :

```
myapp.marketing.server-1.example.com
```

Pour les forks, le nom du service est combiné avec le mot réservé `fork` et le tag :

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Par exemple, un fork de `marketing` tagué `staging` obtient :

```
myapp-fork-staging.marketing.server-1.example.com
```

Chaque URL de fork se situe sous le sous-domaine du dépôt parent et est couverte par son certificat wildcard existant, donc aucun nouveau certificat n'est nécessaire. Le séparateur `-fork-` prévient les collisions avec les vrais noms de services du dépôt de production. Pour les services avec des domaines personnalisés, utilisez les labels de niveau 2 ou le label `rediacc.domain`.

#### Domaine personnalisé via `rediacc.domain`

Vous pouvez définir un domaine personnalisé pour un service en utilisant le label `rediacc.domain` dans votre `docker-compose.yml`. Les noms courts et les domaines complets sont pris en charge :

```yaml
labels:
  # Nom court, résolu en cloud.example.com en utilisant le baseDomain de la machine
  - "rediacc.domain=cloud"

  # Domaine complet, utilisé tel quel
  - "rediacc.domain=cloud.example.com"
```

Une valeur sans points est traitée comme un nom court et le `baseDomain` de la machine est automatiquement ajouté. Une valeur avec des points est utilisée comme domaine complet.

Lorsque `machineName` est configuré, les services avec domaine personnalisé obtiennent **deux routes** : une sur le domaine de base (`cloud.example.com`) et une sur le sous-domaine de la machine (`cloud.server-1.example.com`).

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

1. Infrastructure configurée sur la machine ([Configuration de la machine, Configuration de l'infrastructure](/fr/docs/setup#configuration-de-linfrastructure)) :

   ```bash
   # Identifiants partagés (une fois par config, s'applique à toutes les machines)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Paramètres spécifiques à la machine
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. Enregistrements DNS pointant votre domaine vers l'IP publique du serveur (voir [Configuration DNS](#configuration-dns) ci-dessous).

### Ajouter des labels

Ajoutez les labels `traefik.*` aux services que vous souhaitez exposer dans votre `docker-compose.yml` :

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # Pas de labels traefik, la base de données est interne uniquement
```

| Label | Objectif |
|-------|----------|
| `traefik.enable=true` | Active le routage Traefik personnalisé pour ce conteneur |
| `traefik.http.routers.{name}.rule` | Règle de routage, typiquement `Host(\`domaine\`)` |
| `traefik.http.routers.{name}.entrypoints` | Ports d'écoute : `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Résolveur de certificats, utilisez `letsencrypt` pour Let's Encrypt automatique |
| `traefik.http.services.{name}.loadbalancer.server.port` | Le port sur lequel votre application écoute à l'intérieur du conteneur |

Le `{name}` dans les labels est un identifiant arbitraire, il doit simplement être cohérent entre les labels de routeur/service/middleware associés.

> **Note :** Les labels `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) sont injectés automatiquement par `renet compose`. Vous n'avez pas besoin de les ajouter à votre fichier compose.

## Certificats TLS

Les certificats TLS sont obtenus automatiquement via Let's Encrypt en utilisant le challenge DNS-01 de Cloudflare. Les identifiants sont configurés une fois par config (partagés entre toutes les machines) :

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Les routes automatiques utilisent des **certificats wildcard** au niveau du sous-domaine du dépôt (`*.marketing.server-1.example.com`) au lieu de certificats par service. Le certificat est provisionné automatiquement par Traefik au premier `repo up` ; aucune étape manuelle n'est requise. Les forks réutilisent le wildcard existant du dépôt parent, donc ils ne déclenchent jamais une nouvelle demande de certificat. Les routes avec domaine personnalisé utilisent des wildcards au niveau machine (`*.server-1.example.com`).

> **Nécessite des identifiants Cloudflare.** Les certificats wildcard utilisent le challenge DNS-01. Sans `--cf-dns-token` (et optionnellement `--cert-email`), Traefik ne peut pas compléter le challenge et HTTPS ne fonctionnera pas. HTTP reste fonctionnel. Configurez les identifiants avec `rdc config infra set` avant le premier déploiement.

Pour les routes de niveau 2 avec `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, les SANs de domaine wildcard sont automatiquement injectés en fonction du nom d'hôte de la route.

Le jeton API DNS Cloudflare nécessite la permission `Zone:DNS:Edit` pour les domaines que vous souhaitez sécuriser.

### Cycle de Vie du Certificat TLS

Le chemin complet qu'un certificat Let's Encrypt parcourt depuis son émission jusqu'aux conteneurs de chaque dépôt :

1. **Emission sur l'hôte.** Un conteneur Traefik au niveau machine (`rediacc-proxy`, déployé dans `/opt/rediacc/proxy/`) possède le renouvellement ACME. Il stocke tout l'état dans `/opt/rediacc/proxy/letsencrypt/acme.json` sur l'hôte. Le renouvellement se déclenche automatiquement environ 30 jours avant l'expiration ; aucune action de l'opérateur n'est nécessaire tant que `--cf-dns-token` est configuré.

2. **Dump par dépôt (optionnel).** Les services qui ont besoin de fichiers de certificats dans leur propre conteneur (par exemple, un serveur de messagerie qui lit un `.pem` directement) déploient un petit conteneur `traefik-certs-dumper` à côté d'eux. Le dumper monte `/opt/rediacc/proxy/letsencrypt` en lecture seule et écrit le certificat et la clé extraits dans le volume de données du dépôt sous forme de `cert.pem` / `key.pem`. Pour que cela fonctionne, le démon Docker par dépôt doit avoir `/opt/rediacc/proxy` dans sa liste d'autorisations d'espace de noms de montage. Cela est déjà inclus par défaut.

3. **Cache côté client (`rediacc.json`).** La CLI met en cache une copie compressée de `acme.json` sous `acmeCertCache` dans votre fichier de configuration, indexée par `baseDomain`. Cela permet à plusieurs machines de partager des certificats (via `rdc config cert-cache push -m <machine>`) et sert d'inventaire hors ligne.

**Déclencheurs de synchronisation pour le cache client :**

- Automatiquement après `rdc repo up`, mais seulement si le cache local pour le `baseDomain` de la machine a plus de 6 heures. Les caches récents sont laissés tels quels pour que les déploiements successifs ne surchargent pas SSH.
- À la demande : `rdc config cert-cache pull -m <machine>` (forcer la récupération) ou `rdc machine query --name <machine> --sync-certs` (récupération comme effet secondaire d'une requête de statut).
- Lors de `rdc config infra push`, le cache est poussé vers la machine (les certificats locaux avec une expiration plus longue l'emportent sur les certificats distants).

**Maintenance du cache :**

- Les entrées de routes automatiques obsolètes (anciens domaines tagués avec l'ID réseau comme `service-3200.rediacc.io`) sont purgées à chaque récupération.
- Les certificats dont le `notAfter` est plus de 7 jours dans le passé sont supprimés entièrement. Ils sont inertes et ne font que gonfler le cache.
- `rdc config cert-cache clear` efface tout ; `rdc config cert-cache status` affiche l'inventaire.

**Résolution de problèmes :** si `traefik-certs-dumper` crashe avec `/traefik/acme.json: no such file or directory`, le démon du dépôt ne peut pas voir le stockage letsencrypt de l'hôte. Vérifiez (a) que `/opt/rediacc/proxy/letsencrypt/acme.json` existe sur l'hôte (c'est la responsabilité du `rediacc-proxy` au niveau hôte), et (b) que le démon du dépôt a été démarré avec un renet suffisamment récent qui autorise `/opt/rediacc/proxy`. Redéployez le dépôt avec `rdc repo up` après avoir mis à jour renet pour appliquer.

> **Expérimental :** La cadence de synchronisation automatique et la purge basée sur l'expiration ont été introduites dans renet 0.9+. Les versions plus anciennes de CLI/renet utilisent une synchronisation purement manuelle via `rdc config cert-cache pull`.

## Redirection de ports TCP/UDP

Pour les protocoles non-HTTP (serveurs de messagerie, DNS, bases de données exposées à l'extérieur), utilisez la redirection de ports TCP/UDP.

### Étape 1 : Enregistrer les ports

Ajoutez les ports requis lors de la configuration de l'infrastructure :

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Ceci crée des points d'entrée Traefik nommés `tcp-{port}` et `udp-{port}`.

> Après avoir ajouté ou supprimé des ports, relancez toujours `rdc config infra push` pour mettre à jour la configuration du proxy.

### Étape 2 : Ajouter des labels TCP/UDP

Utilisez les labels `traefik.tcp.*` ou `traefik.udp.*` dans votre fichier compose :

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), passthrough TLS
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Concepts clés :
- **`HostSNI(\`*\`)`** correspond à n'importe quel nom d'hôte (pour les protocoles qui n'envoient pas de SNI, comme le SMTP en clair)
- **`tls.passthrough=true`** signifie que Traefik transmet la connexion TLS brute sans la déchiffrer, l'application gère le TLS elle-même
- Les noms des points d'entrée suivent la convention `tcp-{port}` ou `udp-{port}`

### Exemple TCP Simple (Base de données)

Pour exposer une base de données à l'extérieur sans passthrough TLS (Traefik transfère le TCP brut) :

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Le port 5432 est pré-configuré (voir ci-dessous), donc aucune configuration `--tcp-ports` n'est nécessaire.

> **Note de sécurité :** Exposer une base de données sur Internet est un risque. Utilisez ceci uniquement lorsque les clients distants ont besoin d'un accès direct. Pour la plupart des configurations, gardez la base de données en interne et connectez-vous via votre application.

### Ports pré-configurés

Les ports TCP/UDP suivants ont des points d'entrée par défaut (pas besoin de les ajouter via `--tcp-ports`). Les points d'entrée ne sont générés que pour les familles d'adresses configurées, les points d'entrée IPv4 nécessitent `--public-ipv4`, les points d'entrée IPv6 nécessitent `--public-ipv6` :

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
| 10000-10010 | TCP | Plage dynamique (allocation automatique) |

## Configuration DNS

### DNS automatique (Cloudflare)

Lorsque `--cf-dns-token` est configuré, `rdc config infra push` crée automatiquement les enregistrements DNS nécessaires dans Cloudflare :

| Enregistrement | Type | Contenu | Créé par |
|----------------|------|---------|----------|
| `server-1.example.com` | A / AAAA | IP publique de la machine | `push-infra` |
| `*.server-1.example.com` | A / AAAA | IP publique de la machine | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | IP publique de la machine | `repo up` |

Les enregistrements au niveau machine sont créés par `push-infra` et couvrent les routes avec domaine personnalisé (`rediacc.domain`). Les enregistrements wildcard par dépôt sont créés automatiquement par `repo up` et couvrent les routes automatiques pour ce dépôt.

C'est idempotent, les enregistrements existants sont mis à jour si l'IP change, et laissés inchangés s'ils sont déjà corrects.

Le wildcard du domaine de base (`*.example.com`) doit être créé manuellement si vous utilisez des labels de domaine personnalisés comme `rediacc.domain=erp`.

### DNS manuel

Si vous n'utilisez pas Cloudflare ou gérez le DNS manuellement, créez des enregistrements A (IPv4) et/ou AAAA (IPv6) :

```
# Sous-domaine de la machine (pour les routes avec domaine personnalisé comme rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Wildcards par dépôt (pour les routes automatiques comme myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Wildcard du domaine de base (pour les services avec domaine personnalisé comme rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Avec Cloudflare DNS configuré, les enregistrements wildcard par dépôt sont créés automatiquement par `repo up`. Avec plusieurs machines, chaque machine obtient ses propres enregistrements DNS pointant vers sa propre IP.

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

Chainez les middlewares en les séparant par des virgules :

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
| 502 Bad Gateway | L'application n'écoute pas sur le port déclaré | Vérifiez que l'application est en cours d'exécution et que le port correspond à `loadbalancer.server.port` |
| Port TCP non accessible | Port non enregistré dans l'infrastructure | Exécutez `rdc config infra set --tcp-ports ...` et `push-infra` |
| Serveur de routes avec ancienne version | Le binaire a été mis à jour mais le service n'a pas été redémarré | Automatique lors du provisionnement ; manuel : `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN inaccessible | Adresses de relay mises en cache au démarrage | Recréez le service après des changements DNS ou IP pour qu'il récupère la nouvelle configuration réseau |

## Exemple complet

Cet exemple déploie une application web avec une base de données PostgreSQL. L'application est accessible publiquement sur `app.example.com` avec TLS ; la base de données est interne uniquement.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
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
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Pas de labels traefik, interne uniquement
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
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
rdc repo up --name my-app -m server-1
```

En quelques secondes, le serveur de routes découvre le conteneur, Traefik récupère la route, demande un certificat TLS, et `https://app.example.com` est en ligne.
