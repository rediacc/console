---
title: "Architecture"
description: "Comment Rediacc fonctionne : architecture à deux outils, modes de fonctionnement, modèle de sécurité et structure de configuration."
category: "Guides"
order: 2
language: fr
---

# Architecture

Cette page explique le fonctionnement interne de Rediacc : l'architecture à deux outils, les modes de fonctionnement, le modèle de sécurité et la structure de configuration.

## Architecture à deux outils

Rediacc utilise deux binaires qui fonctionnent ensemble via SSH :

![Architecture à deux outils](/img/arch-two-tool.svg)

- **rdc** s'exécute sur votre poste de travail (macOS, Linux ou Windows). Il lit votre configuration locale, se connecte aux machines distantes via SSH et invoque les commandes renet.
- **renet** s'exécute sur le serveur distant avec des privilèges root. Il gère les images disque chiffrées LUKS, les démons Docker isolés, l'orchestration des services et la configuration du proxy inverse.

Chaque commande que vous tapez localement se traduit par un appel SSH qui exécute renet sur la machine distante. Vous n'avez jamais besoin de vous connecter manuellement aux serveurs en SSH.

## Modes de fonctionnement

Rediacc prend en charge trois modes, chacun déterminant où l'état est stocké et comment les commandes sont exécutées.

![Modes de fonctionnement](/img/arch-operating-modes.svg)

### Mode local

Le mode par défaut pour un usage auto-hébergé. Tout l'état réside dans `~/.rediacc/config.json` sur votre poste de travail.

- Connexions SSH directes aux machines
- Aucun service externe requis
- Mono-utilisateur, mono-poste
- Le contexte est créé avec `rdc context create-local`

### Mode cloud (expérimental)

Utilise l'API Rediacc pour la gestion de l'état et la collaboration en équipe.

- État stocké dans l'API cloud
- Équipes multi-utilisateurs avec contrôle d'accès basé sur les rôles
- Console web pour la gestion visuelle
- Le contexte est créé avec `rdc context create`

> **Note :** Les commandes du mode cloud sont expérimentales. Activez-les avec `rdc --experimental <command>` ou en définissant `REDIACC_EXPERIMENTAL=1`.

### Mode S3

Stocke l'état chiffré dans un bucket compatible S3. Combine la nature auto-hébergée du mode local avec la portabilité entre postes de travail.

- État stocké dans un bucket S3/R2 sous forme de `state.json`
- Chiffrement AES-256-GCM avec un mot de passe maître
- Portable : tout poste de travail disposant des identifiants du bucket peut gérer l'infrastructure
- Le contexte est créé avec `rdc context create-s3`

Les trois modes utilisent les mêmes commandes CLI. Le mode n'affecte que l'emplacement de stockage de l'état et le fonctionnement de l'authentification.

## L'utilisateur rediacc

Lorsque vous exécutez `rdc context setup-machine`, renet crée un utilisateur système appelé `rediacc` sur le serveur distant :

- **UID** : 7111
- **Shell** : `/sbin/nologin` (ne peut pas se connecter via SSH)
- **Objectif** : Propriétaire des fichiers du dépôt et exécuteur des fonctions du Rediaccfile

L'utilisateur `rediacc` n'est pas accessible directement via SSH. À la place, rdc se connecte avec l'utilisateur SSH que vous avez configuré (par ex., `deploy`), et renet exécute les opérations sur les dépôts via `sudo -u rediacc /bin/sh -c '...'`. Cela signifie :

1. Votre utilisateur SSH a besoin de privilèges `sudo`
2. Toutes les données des dépôts appartiennent à `rediacc`, pas à votre utilisateur SSH
3. Les fonctions du Rediaccfile (`prep()`, `up()`, `down()`) s'exécutent en tant que `rediacc`

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

## Chiffrement LUKS

Les dépôts sont des images disque chiffrées LUKS stockées dans le datastore du serveur (par défaut : `/mnt/rediacc`). Chaque dépôt :

1. Possède une phrase secrète de chiffrement générée aléatoirement (l'« identifiant »)
2. Est stocké sous forme de fichier : `{datastore}/repos/{guid}.img`
3. Est monté via `cryptsetup` lors de l'accès

L'identifiant est stocké dans votre fichier local `config.json` mais **jamais** sur le serveur. Sans l'identifiant, les données du dépôt ne peuvent pas être lues. Lorsque le démarrage automatique est activé, un fichier de clé LUKS secondaire est stocké sur le serveur pour permettre le montage automatique au démarrage.

## Structure de configuration

Toute la configuration est stockée dans `~/.rediacc/config.json`. Voici un exemple annoté :

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
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
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Champs principaux :**

| Champ | Description |
|-------|-------------|
| `mode` | `"local"`, `"s3"`, ou omis pour le mode cloud |
| `apiUrl` | `"local://"` pour le mode local, URL de l'API pour le mode cloud |
| `ssh.privateKeyPath` | Clé privée SSH utilisée pour toutes les connexions aux machines |
| `machines.<name>.user` | Nom d'utilisateur SSH pour la connexion à la machine |
| `machines.<name>.knownHosts` | Clés d'hôte SSH issues de `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID identifiant l'image disque chiffrée |
| `repositories.<name>.credential` | Phrase secrète de chiffrement LUKS (**non stockée sur le serveur**) |
| `repositories.<name>.networkId` | Détermine le sous-réseau IP (2816 + n*64), attribué automatiquement |
| `nextNetworkId` | Compteur global pour l'attribution des ID réseau |
| `universalUser` | Remplace l'utilisateur système par défaut (`rediacc`) |

> Ce fichier contient des données sensibles (chemins de clés SSH, identifiants LUKS). Il est stocké avec les permissions `0600` (lecture/écriture propriétaire uniquement). Ne le partagez pas et ne le commitez pas dans un système de contrôle de version.
