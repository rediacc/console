---
title: Architecture
description: >-
  Comment Rediacc fonctionne : architecture à deux outils, détection
  d'adaptateur, modèle de sécurité et structure de configuration.
category: Concepts
order: 0
language: fr
sourceHash: "b41d8631ce30c981"
sourceCommit: 5c97ef070ea0c474b03651ceea03433b3f48abcd
---

# Architecture

Cette page explique le fonctionnement interne de Rediacc : l'architecture à deux outils, la détection d'adaptateur, le modèle de sécurité et la structure de configuration.

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

Pour un guide pratique orienté opérateur, consultez [rdc vs renet](/en/docs/rdc-vs-renet). Vous pouvez aussi utiliser `rdc ops` pour lancer un cluster de VM locales pour les tests, voir [VM expérimentales](/en/docs/experimental-vms).

## Config

Tout l'état du CLI est stocké dans des fichiers de configuration JSON plats sous `~/.config/rediacc/`.

### Adaptateur local (par défaut)

Le mode par défaut pour un usage auto-hébergé. Tout l'état réside dans un fichier de configuration sur votre poste de travail (par ex., `~/.config/rediacc/rediacc.json`).

- Connexions SSH directes aux machines
- Aucun service externe requis
- Mono-utilisateur, mono-poste
- La configuration par défaut est créée automatiquement au premier lancement du CLI. Les configurations nommées sont créées avec `rdc config init --name <name>`

### Adaptateur cloud (expérimental)

Activé automatiquement lorsqu'une configuration contient les champs `apiUrl` et `token`. Utilise l'API Rediacc pour la gestion de l'état et la collaboration en équipe.

- État stocké dans l'API cloud
- Équipes multi-utilisateurs avec contrôle d'accès basé sur les rôles
- Console web pour la gestion visuelle
- Configuré avec `rdc auth login`

> **Note :** Les commandes de l'adaptateur cloud sont expérimentales. Activez-les en définissant `REDIACC_EXPERIMENTAL=1`.

Les deux adaptateurs utilisent les mêmes commandes CLI. L'adaptateur n'affecte que l'emplacement de stockage de l'état et le fonctionnement de l'authentification.

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

Cette structure unifiée élimine les collisions de montage en lecture seule et lecture-écriture qui survenaient lorsque les chemins du daemon étaient répartis entre le système de fichiers de l'hôte et le volume chiffré. Les daemons par dépôt et les daemons autonomes suivent la même structure de répertoires, de sorte que les outils et les diagnostics fonctionnent de manière identique dans les deux cas.

## Chiffrement LUKS

Les dépôts sont des images disque chiffrées LUKS stockées dans le datastore du serveur (par défaut : `/mnt/rediacc`). Chaque dépôt :

1. Possède une phrase secrète de chiffrement générée aléatoirement (l'identifiant)
2. Est stocké sous forme de fichier : `{datastore}/repos/{guid}.img`
3. Est monté via `cryptsetup` lors de l'accès

L'identifiant est stocké dans votre fichier de configuration mais **jamais** sur le serveur. Sans l'identifiant, les données du dépôt ne peuvent pas être lues. Lorsque le démarrage automatique est activé, un fichier de clé LUKS secondaire est stocké sur le serveur pour permettre le montage automatique au démarrage.

## Structure de configuration

Chaque configuration est un fichier JSON plat stocké dans `~/.config/rediacc/`. La configuration par défaut est `rediacc.json` ; les configurations nommées utilisent le nom comme nom de fichier (par ex., `production.json`). Voici un exemple annoté :

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 1,
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
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Champs principaux :**

| Champ | Description |
|-------|-------------|
| `id` | Identifiant unique pour ce fichier de configuration |
| `version` | Version du schéma du fichier de configuration |
| `ssh.privateKeyPath` | Clé privée SSH utilisée pour toutes les connexions aux machines |
| `machines.<name>.user` | Nom d'utilisateur SSH pour la connexion à la machine |
| `machines.<name>.knownHosts` | Clés d'hôte SSH issues de `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID identifiant l'image disque chiffrée |
| `repositories.<name>.credential` | Phrase secrète de chiffrement LUKS (**non stockée sur le serveur**) |
| `repositories.<name>.networkId` | Détermine le sous-réseau IP (2816 + n*64), attribué automatiquement |
| `nextNetworkId` | Compteur global pour l'attribution des ID réseau |
| `universalUser` | Remplace l'utilisateur système par défaut (`rediacc`) |

> Ce fichier contient des données sensibles (chemins de clés SSH, identifiants LUKS). Il est stocké avec les permissions `0600` (lecture/écriture propriétaire uniquement). Ne le partagez pas et ne le commitez pas dans un système de contrôle de version.
