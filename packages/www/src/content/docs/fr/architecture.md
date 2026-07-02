---
title: Architecture
description: >-
  Comment Rediacc fonctionne : architecture à deux outils, détection
  d'adaptateur, modèle de sécurité et structure de configuration.
category: Concepts
order: 0
language: fr
sourceHash: "947fcefa63eac600"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Architecture

Voici le concept : rdc sur votre poste de travail, renet sur vos serveurs, communiquant via SSH. L'ensemble de l'architecture de Rediacc repose sur cette séparation. Cette page explique comment les deux outils divisent les responsabilités, comment la détection d'adaptateur achemine l'état, à quoi ressemble le modèle de sécurité et comment la configuration est structurée.

## Vue d'ensemble du stack complet

Le trafic transite depuis internet via un proxy inverse vers des démons Docker isolés, chacun adossé à un stockage chiffré :

![Architecture du stack complet](/img/arch-full-stack.svg)

Chaque dépôt dispose de son propre démon Docker, d'un sous-réseau IP loopback (/26 = 64 IPs) et d'un volume BTRFS chiffré LUKS. Le serveur de routes découvre les conteneurs en cours d'exécution sur tous les démons et transmet la configuration de routage à Traefik.

## Architecture à deux outils

Rediacc utilise deux binaires qui fonctionnent ensemble via SSH :

![Architecture à deux outils](/img/arch-two-tool.svg)

- **rdc** s'exécute sur votre poste de travail (macOS, Linux ou Windows). Il lit votre configuration locale, se connecte aux machines distantes via SSH et invoque les commandes renet.
- **renet** s'exécute sur le serveur distant avec des privilèges root. Il gère les images disque chiffrées LUKS, les démons Docker isolés, l'orchestration des services et la configuration du proxy inverse.

Chaque commande que vous tapez localement se traduit par un appel SSH qui exécute renet sur la machine distante. Vous n'avez jamais besoin de vous connecter manuellement aux serveurs en SSH.

Pour un guide pratique orienté opérateur, consultez [rdc vs renet](/fr/docs/rdc-vs-renet). Vous pouvez aussi utiliser `rdc ops` pour lancer un cluster de VM locales pour les tests, voir [VM expérimentales](/fr/docs/experimental-vms).

## Config

Tout l'état du CLI est stocké dans des fichiers de configuration JSON plats sous `~/.config/rediacc/`.

Tout l'état réside dans un fichier de configuration sur votre poste de travail (par ex., `~/.config/rediacc/rediacc.json`).

- Connexions SSH directes aux machines
- Aucun service externe requis
- La configuration par défaut est créée automatiquement au premier lancement du CLI. Les configurations nommées sont créées avec `rdc config init --name <name>`
- La synchronisation chiffrée de la configuration (optionnelle) stocke le même fichier dans le magasin de configuration, avec une portée par équipe

## L'utilisateur rediacc

Lorsque vous exécutez `rdc config machine setup`, renet crée un utilisateur système appelé `rediacc` sur le serveur distant :

- **UID** : 7111
- **Shell** : `/sbin/nologin` (ne peut pas se connecter via SSH)
- **Objectif** : Propriétaire des fichiers du dépôt et exécuteur des fonctions du Rediaccfile

L'utilisateur `rediacc` n'est pas accessible directement via SSH. A la place, rdc se connecte avec l'utilisateur SSH que vous avez configuré (par ex., `deploy`), et renet exécute les opérations sur les dépôts via `sudo -u rediacc /bin/sh -c '...'`. Cela signifie :

1. Votre utilisateur SSH a besoin de privilèges `sudo`
2. Toutes les données des dépôts appartiennent à `rediacc`, pas à votre utilisateur SSH
3. Les fonctions du Rediaccfile (`up()`, `down()`) s'exécutent en tant que `rediacc`

Cette séparation garantit que les données des dépôts ont une propriété cohérente quel que soit l'utilisateur SSH qui les gère.

## Isolation Docker

Chaque dépôt dispose de son propre démon Docker isolé. Lorsqu'un dépôt est monté, renet démarre un processus `dockerd` dédié avec un socket unique :

![Isolation Docker](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Par exemple, un dépôt avec l'ID réseau `2816` utilise :
```
/var/run/rediacc/docker-2816.sock
```

Cela signifie :
- Les conteneurs de différents dépôts ne peuvent pas se voir mutuellement
- Chaque dépôt dispose de son propre cache d'images, réseaux et volumes
- Le démon Docker de l'hôte (s'il existe) est complètement séparé

Les fonctions du Rediaccfile ont automatiquement `DOCKER_HOST` configuré avec le socket correct.

Lorsqu'un agent IA accède à un dépôt via `rdc term connect -r <repo>`, la même isolation s'applique : la session s'exécute en tant qu'utilisateur non privilégié `rediacc` (UID 7111), dans un espace de noms de montage distinct, avec `DOCKER_HOST` limité au socket du daemon de ce seul dépôt. Le flux fork-first combine cette isolation d'exécution avec une primitive de clonage CoW : l'agent opère sur un fork dédié à la tâche, jamais sur les dépôts grand (production). Consultez [Sécurité et garde-fous pour les agents IA](/fr/docs/ai-agents-safety) pour le modèle de bac à sable complet, la sémantique des substitutions et la frontière de responsabilité du développeur pour les identifiants des services externes.

### Structure des chemins du daemon

Les données et la configuration Docker sont stockées dans le point de montage du dépôt, ce qui maintient chaque daemon complètement isolé de l'hôte et des autres dépôts.

**Structure par dépôt :**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Racine des données Docker
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Configuration Docker
```

**Structure autonome** (daemons non rattachés à un point de montage de dépôt) :
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Chemin d'exécution partagé** (inchangé) :
```
/run/rediacc/docker-{N}.sock
```

Cette structure unifiée élimine les collisions de montage en lecture seule et lecture-écriture qui survenaient lorsque les chemins du daemon étaient répartis entre le système de fichiers de l'hôte et le volume chiffré. Nous avons rencontré cette répartition plus d'une fois avant de nous arrêter sur celle-ci. Les daemons par dépôt et les daemons autonomes suivent la même structure de répertoires, de sorte que les outils et les diagnostics fonctionnent de manière identique dans les deux cas.

## Chiffrement LUKS

Les dépôts sont des images disque chiffrées LUKS stockées dans le datastore du serveur (par défaut : `/mnt/rediacc`). Chaque dépôt :

1. Possède une phrase secrète de chiffrement générée aléatoirement (l'identifiant)
2. Est stocké sous forme de fichier : `{datastore}/repos/{guid}.img`
3. Est monté via `cryptsetup` lors de l'accès

L'identifiant est stocké dans votre fichier de configuration mais **jamais** sur le serveur. Sans l'identifiant, les données du dépôt ne peuvent pas être lues. Lorsque le démarrage automatique est activé, un fichier de clé LUKS secondaire est stocké sur le serveur pour permettre le montage automatique au démarrage.

## Structure de configuration

Chaque configuration est un fichier JSON stocké dans `~/.config/rediacc/`. La configuration par défaut est `rediacc.json` ; les configurations nommées utilisent le nom comme nom de fichier (par ex., `production.json`). Les champs sont regroupés par objectif : `resources` contient les déploiements, `credentials` contient les secrets, `account` contient les paramètres par défaut cloud, `infra` contient les TLS/DNS, et `encryption` contient l'état au repos par champ. Le discriminateur `schemaVersion: 2` de haut niveau ancre la compatibilité directe.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Groupes de clés :**

| Groupe | Contenu |
|---|---|
| `schemaVersion` | Discriminateur (actuellement `2`). Les chargeurs rejettent les versions inconnues. |
| `id` / `version` | UUID immutable + compteur monotone ; utilisés pour le verrouillage optimiste sur le magasin de configuration distant. |
| `defaults.*` | Paramètres par défaut d'exécution non sensibles (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Paire de clés SSH inline + `knownHosts`. Remplace le `ssh.privateKeyPath` hérité (plus d'indirection de chemin de fichier ; le contenu est résolu au chargement et stocké inline). |
| `credentials.cfDnsApiToken` | Token Cloudflare DNS-01 ACME. |
| `credentials.masterPasswordVerifier` | Présent uniquement lorsque `encryption.mode === "master-password"`. |
| `resources.machines.*` | Détail de connexion SSH par machine. |
| `resources.storages.*` | Identifiants de sauvegarde hors site compatibles rclone. |
| `resources.repositories.*` | GUID par dépôt + identifiant LUKS + clé SSH pour accès agent isolé en bac à sable. |
| `infra.acmeCertCache.*` | acme.json de Traefik en cache, gzip+base64, indexé par domaine. |
| `encryption.mode` | `"plaintext"` (par défaut) ou `"master-password"`. |
| `encryption.encryptedFields` | Lorsque chiffré, carte blob AES-GCM par pointeur (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Une invite de déverrouillage par session déchiffre à mesure que les champs sont lus. |
| `remote` | Présent uniquement lorsque la configuration est synchronisée au magasin de configuration chiffré ; voir [Magasin de configuration chiffré](/fr/docs/config-storage). |

**Éditez en toute sécurité avec le CLI, pas `vim` :**

```bash
# Modifications de champs uniques adressées par pointeur (contrôlées par connaissance pour les chemins sensibles)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Éditeur complet avec projection JSONC masquée (humains uniquement)
rdc config edit

# Dump JSONC en lecture seule, sûr pour les scripts et les agents
rdc config edit --dump

# Inspectez chaque mutation + refus + révélation dans le journal d'audit
rdc config audit log --since 24h
rdc config audit verify
```

> Ce fichier contient des données sensibles (clés SSH privées, identifiants LUKS, tokens Cloudflare). Il est stocké avec les permissions `0600` (lecture/écriture propriétaire uniquement). Ne le partagez pas et ne le commitez pas dans un système de contrôle de version. Lorsque n'importe quelle commande `rdc` le lit, les champs sensibles sont [masqués par défaut](/fr/docs/ai-agents-safety) : le texte en clair n'apparaît qu'avec `--reveal` sur un terminal TTY interactif humain.

### Enveloppe v2 et application côté serveur

Lorsque la configuration est synchronisée au [magasin de configuration chiffré](/fr/docs/config-storage), le CLI enveloppe chaque champ sensible dans un engagement HMAC par champ et porte ces engagements dans l'enveloppe en texte clair. Le serveur ne voit que des digests hexadécimaux : jamais les valeurs : mais peut appliquer des portes de connaissance à chaque écriture :

- **Vérification de précondition** : sur `PUT /configs/<id>`, le client soumet les digests qu'il prétend connaître pour les chemins qu'il souhaite muter. Le serveur compare par rapport aux engagements de l'enveloppe stockée. Désaccord → `409 precondition_failed` avec `mismatchedPaths`. Zéro connaissance : le serveur ne voit jamais le texte en clair.
- **Anti-dégradation** : la nouvelle enveloppe doit s'engager sur chaque chemin sensible que l'enveloppe précédente s'était engagée. Un agent ne peut pas supprimer un chemin des engagements pour contourner une précondition future.
- **Épinglage de version d'enveloppe** : le serveur rejette les enveloppes manquant `envelopeVersion: 2` avec `400 unsupported_envelope_version`. Pas de fenêtre d'acceptation duale.
- **Chiffrement par champ au repos** (côté CLI) : lorsque `encryption.mode === "master-password"`, chaque secret devient un blob AES-GCM individuel chiffré par la phrase de passe maître. Les lectures ne déclenchent une invite que si la commande touche réellement un secret (donc `rdc machine list` reste exempt d'invite).

La clé d'engagement (FCK) est dérivée côté client depuis la CEK via `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` avec un salt par configuration. Faire tourner `fckSalt` invalide tous les engagements antérieurs, forçant un recalcul complet : utile lors de la rotation de CEK.
