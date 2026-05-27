---
title: Guide de migration
description: Migrer des projets existants vers des dépôts chiffrés Rediacc.
category: Guides
order: 11
language: fr
sourceHash: "69ab61a2875f8d70"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Guide de migration

Migrez un projet existant, fichiers, services Docker, bases de données, depuis un serveur traditionnel ou un environnement de développement local vers un dépôt chiffré Rediacc.

## Prérequis

- CLI `rdc` installé ([Installation](/fr/docs/installation))
- Une machine ajoutée et provisionnée ([Configuration](/fr/docs/setup))
- Suffisamment d'espace disque sur le serveur pour votre projet (vérifiez avec `rdc machine query`)

## Etape 1 : Créer un dépôt

Créez un dépôt chiffré dimensionné pour votre projet. Prévoyez de l'espace supplémentaire pour les images Docker et les données des conteneurs.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **Astuce :** Vous pouvez redimensionner plus tard avec `rdc repo resize` si nécessaire, mais le dépôt doit d'abord être démonté. Il est plus simple de commencer avec suffisamment d'espace.

## Etape 2 : Téléverser vos fichiers

Utilisez `rdc repo sync upload` pour transférer les fichiers de votre projet dans le dépôt.

```bash
# Aperçu de ce qui sera transféré (aucune modification effectuée)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Téléverser les fichiers
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

Le dépôt doit être monté avant le téléversement. S'il ne l'est pas encore :

```bash
rdc repo mount --name my-project -m server-1
```

Pour les synchronisations suivantes où vous souhaitez que le distant corresponde exactement à votre répertoire local :

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> L'option `--mirror` supprime les fichiers sur le serveur distant qui n'existent pas en local. Utilisez d'abord `--dry-run` pour vérifier.

## Etape 3 : Corriger la propriété des fichiers

Les fichiers téléversés arrivent avec l'UID de votre utilisateur local (par ex. 1000). Rediacc utilise un utilisateur universel (UID 7111) afin que VS Code, les sessions terminal et les outils aient un accès cohérent. Exécutez la commande de propriété pour convertir :

```bash
rdc repo ownership --name my-project -m server-1
```

### Exclusion compatible Docker

Si des conteneurs Docker sont en cours d'exécution (ou ont été exécutés), la commande de propriété détecte automatiquement leurs répertoires de données accessibles en écriture et **les ignore**. Cela évite de casser des conteneurs qui gèrent leurs propres fichiers avec des UIDs différents (par ex. MariaDB utilise l'UID 999, Nextcloud utilise l'UID 33).

La commande affiche un rapport :

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Quand exécuter

- **Après le téléversement des fichiers**, pour convertir votre UID local en 7111
- **Après le démarrage des conteneurs**, si vous souhaitez que les répertoires de volumes Docker soient automatiquement exclus. Si les conteneurs n'ont pas encore été démarrés, il n'y a pas de volumes à exclure et tous les répertoires sont modifiés (ce qui est normal, les conteneurs recréeront leurs données au premier démarrage)

### Mode forcé

Pour ignorer la détection des volumes Docker et modifier la propriété de tout, y compris les répertoires de données des conteneurs :

```bash
rdc repo ownership --name my-project -m server-1
```

> **Avertissement :** Cela peut casser les conteneurs en cours d'exécution. Arrêtez-les d'abord avec `rdc repo down` si nécessaire.

### UID personnalisé

Pour définir un UID autre que l'UID par défaut 7111 :

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

> **Attention :** `7111` est l'UID universel Rediacc utilisé partout (il correspond à l'utilisateur `rediacc` intégré dans l'image du devcontainer). Ne le surchargez avec `--uid` que pour assurer la compatibilité ascendante avec des fichiers appartenant à un UID externe spécifique. Ce n'est **pas** une cible de migration. Les nouveaux dépôts doivent conserver la valeur par défaut.

## Etape 4 : Configurer votre Rediaccfile

Créez un `Rediaccfile` à la racine de votre projet. Ce script Bash définit comment vos services sont démarrés et arrêtés.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

Les deux fonctions du cycle de vie :

| Fonction | Objectif | Comportement en cas d'erreur |
|----------|----------|------------------------------|
| `up()` | Démarrer les services | L'échec racine est critique ; les échecs dans les sous-répertoires sont journalisés et continuent |
| `down()` | Arrêter les services | Meilleur effort : tente toujours tout |

> **Important :** Utilisez toujours `renet compose --` au lieu de `docker compose` dans votre Rediaccfile. Le wrapper `renet compose` impose le réseau hôte, les capacités de checkpoint/restore CRIU, l'allocation d'IP et la découverte de services requises par renet-proxy. L'utilisation directe de `docker compose` contourne tout cela et sera rejetée lors de la validation.
>
> N'utilisez jamais `sudo docker` non plus, `sudo` réinitialise les variables d'environnement, y compris `DOCKER_HOST`, ce qui entraîne la création des conteneurs sur le daemon Docker du système au lieu du daemon isolé du dépôt. Les fonctions du Rediaccfile s'exécutent déjà avec des privilèges suffisants.

Voir [Services](/fr/docs/services) pour tous les détails sur les Rediaccfiles, les configurations multi-services et l'ordre d'exécution.

## Etape 5 : Configurer le réseau des services

Rediacc exécute un daemon Docker isolé par dépôt. Les services utilisent `network_mode: host` et se lient à des IPs de loopback uniques afin de pouvoir utiliser les ports standard sans conflits entre les dépôts.

### Adapter votre docker-compose.yml

**Avant (traditionnel) :**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Après (Rediacc) :**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

Modifications principales :

1. **Supprimer les mappages `ports:`** - `renet compose` utilise le réseau hôte et supprime automatiquement les mappages de ports
2. **Supprimer `network_mode: host`** - `renet compose` l'ajoute automatiquement
3. **Les politiques de redémarrage peuvent être conservées** - renet les supprime automatiquement pour la compatibilité CRIU et le watchdog du routeur récupère automatiquement les conteneurs arrêtés
4. **Utiliser les noms de service pour les connexions inter-services** (p. ex. `postgres`, `redis`) - renet injecte chaque nom de service comme nom d'hôte résolvable. Ne pas intégrer d'IPs brutes dans les chaînes de connexion stockées dans les bases de données ou les fichiers de configuration ; utilisez le nom du service pour conserver l'isolation des forks
5. **La liaison est automatique** - le noyau réécrit `bind()` vers la bonne IP de loopback. Les services peuvent utiliser `0.0.0.0` ou `localhost`

Les variables `{SERVICE}_IP` sont toujours disponibles si vous en avez besoin, mais la liaison explicite n'est plus requise. Convention de nommage : majuscules, tirets remplacés par des underscores, suffixe `_IP`. Par exemple, `listmonk-app` devient `LISTMONK_APP_IP`.

Voir [Réseau des services](/fr/docs/services#service-networking-rediaccjson) pour les détails sur l'attribution des IP et `.rediacc.json`.

## Etape 6 : Démarrer les services

Montez le dépôt (s'il n'est pas déjà monté) et démarrez tous les services :

```bash
rdc repo up --name my-project -m server-1
```

Cela va :
1. Monter le dépôt chiffré
2. Démarrer le daemon Docker isolé
3. Générer automatiquement `.rediacc.json` avec les attributions d'IP des services
4. Exécuter `up()` de tous les Rediaccfiles

Vérifiez que vos conteneurs sont en cours d'exécution :

```bash
rdc machine containers --name server-1
```

## Etape 7 : Activer le démarrage automatique (Optionnel)

Par défaut, les dépôts doivent être montés et démarrés manuellement après un redémarrage du serveur. Activez le démarrage automatique pour que vos services se lancent automatiquement :

```bash
rdc repo autostart enable --name my-project -m server-1
```

Vous serez invité à saisir la phrase de passe du dépôt.

> **Note de sécurité :** Le démarrage automatique stocke un fichier de clé LUKS sur le serveur. Toute personne ayant un accès root peut monter le dépôt sans la phrase de passe. Voir [Démarrage automatique](/fr/docs/services#autostart-on-boot) pour plus de détails.

## Scénarios de migration courants

### WordPress / PHP avec base de données

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # Fichiers WordPress (UID 33 en exécution)
├── database/data/          # Données MariaDB (UID 999 en exécution)
└── wp-content/uploads/     # Fichiers uploadés par les utilisateurs
```

1. Téléversez les fichiers de votre projet
2. Démarrez d'abord les services (`rdc repo up`) pour que les conteneurs créent leurs répertoires de données
3. Exécutez la correction de propriété, les répertoires de données MariaDB et de l'application sont automatiquement exclus

### Node.js / Python avec Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Code source de l'application
├── node_modules/           # Dépendances
└── redis-data/             # Persistance Redis (UID 999 en exécution)
```

1. Téléversez votre projet (envisagez d'exclure `node_modules` et de les récupérer dans `up()`)
2. Exécutez la correction de propriété après le démarrage des conteneurs

### Projet Docker personnalisé

Pour tout projet avec des services Docker :

1. Téléverser les fichiers du projet
2. Adapter `docker-compose.yml` (voir Etape 5)
3. Créer un `Rediaccfile` avec les fonctions du cycle de vie
4. Exécuter la correction de propriété
5. Démarrer les services

## Dépannage

### Permission refusée après le téléversement

Les fichiers ont encore votre UID local. Exécutez la commande de propriété :

```bash
rdc repo ownership --name my-project -m server-1
```

### Le conteneur ne démarre pas

Vérifiez que les services sont en cours d'exécution et consultez leurs journaux :

```bash
# Vérifier les IPs attribuées
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# Vérifier les logs du conteneur
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### Conflit de ports entre les dépôts

Chaque dépôt reçoit des IPs de loopback uniques et le noyau réécrit automatiquement les appels `bind()` vers la bonne IP. Les conflits de ports entre dépôts ne devraient pas se produire. Si vous observez un comportement inattendu, vérifiez que les services sont démarrés via `renet compose` (pas `docker compose`). Pour se connecter à d'autres services, utilisez le nom du service (p. ex. `postgres`) plutôt que des IPs brutes ; les noms de service se résolvent correctement dans chaque fork.

### La correction de propriété casse les conteneurs

Si vous avez exécuté `rdc repo ownership` et qu'un conteneur a cessé de fonctionner, les fichiers de données du conteneur ont été modifiés. Arrêtez le conteneur, supprimez son répertoire de données et redémarrez, le conteneur le recréera :

```bash
rdc repo down --name my-project -m server-1
# Supprimer le répertoire de données du conteneur (par ex. database/data)
rdc repo up --name my-project -m server-1
```
