---
title: "Configuration de la machine"
description: "Créez une configuration, ajoutez des machines, provisionnez des serveurs et configurez l'infrastructure."
category: "Guides"
order: 3
language: fr
sourceHash: bdc41b37f24ae8f8
---

# Configuration de la machine

Cette page vous guide dans la configuration de votre première machine : création d'une configuration, enregistrement d'un serveur, provisionnement et configuration optionnelle de l'infrastructure pour l'accès public.

## Étape 1 : Créer une configuration

Un **config** est un fichier de configuration nommé qui stocke vos identifiants SSH, les définitions de machines et les mappages de dépôts. Considérez-le comme un espace de travail de projet.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Requis | Description |
|--------|--------|-------------|
| `--ssh-key <path>` | Oui | Chemin vers votre clé privée SSH. Le tilde (`~`) est développé automatiquement. |
| `--renet-path <path>` | Non | Chemin personnalisé vers le binaire renet sur les machines distantes. Par défaut, l'emplacement d'installation standard. |

Ceci crée une configuration nommée `my-infra` et la stocke dans `~/.config/rediacc/my-infra.json`. La configuration par défaut (sans nom) est stockée sous `~/.config/rediacc/rediacc.json`.

> Vous pouvez avoir plusieurs configurations (par ex., `production`, `staging`, `dev`). Basculez entre elles avec le drapeau `--config` sur n'importe quelle commande.

## Étape 2 : Ajouter une machine

Enregistrez votre serveur distant comme machine dans la configuration :

```bash
rdc config add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Requis | Par défaut | Description |
|--------|--------|------------|-------------|
| `--ip <address>` | Oui | - | Adresse IP ou nom d'hôte du serveur distant |
| `--user <username>` | Oui | - | Nom d'utilisateur SSH sur le serveur distant |
| `--port <port>` | Non | `22` | Port SSH |
| `--datastore <path>` | Non | `/mnt/rediacc` | Chemin sur le serveur où Rediacc stocke les dépôts chiffrés |

Après l'ajout de la machine, rdc exécute automatiquement `ssh-keyscan` pour récupérer les clés d'hôte du serveur. Vous pouvez également l'exécuter manuellement :

```bash
rdc config scan-keys server-1
```

Pour afficher toutes les machines enregistrées :

```bash
rdc config machines
```

## Étape 3 : Configurer la machine

Provisionnez le serveur distant avec toutes les dépendances requises :

```bash
rdc config setup-machine server-1
```

Cette commande :
1. Téléverse le binaire renet sur le serveur via SFTP
2. Installe Docker, containerd et cryptsetup (si non présents)
3. Crée l'utilisateur système `rediacc` (UID 7111)
4. Crée le répertoire du datastore et le prépare pour les dépôts chiffrés

| Option | Requis | Par défaut | Description |
|--------|--------|------------|-------------|
| `--datastore <path>` | Non | `/mnt/rediacc` | Répertoire du datastore sur le serveur |
| `--datastore-size <size>` | Non | `95%` | Proportion du disque disponible à allouer au datastore |
| `--debug` | Non | `false` | Activer la sortie détaillée pour le dépannage |

> La configuration ne doit être exécutée qu'une seule fois par machine. Il est possible de la relancer en toute sécurité si nécessaire.

## Gestion des clés d'hôte

Si la clé d'hôte SSH d'un serveur change (par ex., après une réinstallation), rafraîchissez les clés stockées :

```bash
rdc config scan-keys server-1
```

Ceci met à jour le champ `knownHosts` dans votre configuration pour cette machine.

## Tester la connectivité SSH

Après l'ajout d'une machine, vérifiez qu'elle est accessible :

```bash
rdc term server-1 -c "hostname"
```

Cette commande ouvre une connexion SSH vers la machine et exécute la commande. Si elle réussit, votre configuration SSH est correcte.

Pour des diagnostics plus détaillés, exécutez :

```bash
rdc doctor
```

> **Adaptateur cloud uniquement** : La commande `rdc machine test-connection` fournit des diagnostics SSH détaillés mais nécessite l'adaptateur cloud. Pour l'adaptateur local, utilisez `rdc term` ou `ssh` directement.

## Configuration de l'infrastructure

Pour les machines devant servir du trafic public, configurez les paramètres d'infrastructure :

### Définir l'infrastructure

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Description |
|--------|-------------|
| `--public-ipv4 <ip>` | Adresse IPv4 publique pour l'accès externe |
| `--public-ipv6 <ip>` | Adresse IPv6 publique pour l'accès externe |
| `--base-domain <domain>` | Domaine de base pour les applications (par ex., `example.com`) |
| `--cert-email <email>` | Email pour les certificats TLS Let's Encrypt |
| `--cf-dns-token <token>` | Jeton API DNS Cloudflare pour les challenges ACME DNS-01 |
| `--tcp-ports <ports>` | Ports TCP supplémentaires à rediriger, séparés par des virgules (par ex., `25,143,465,587,993`) |
| `--udp-ports <ports>` | Ports UDP supplémentaires à rediriger, séparés par des virgules (par ex., `53`) |

### Afficher l'infrastructure

```bash
rdc config show-infra server-1
```

### Déployer sur le serveur

Générez et déployez la configuration du proxy inverse Traefik sur le serveur :

```bash
rdc config push-infra server-1
```

Ceci déploie la configuration du proxy basée sur vos paramètres d'infrastructure. Traefik gère la terminaison TLS, le routage et la redirection des ports.

## Définir les valeurs par défaut

Définissez des valeurs par défaut pour ne pas avoir à les spécifier à chaque commande :

```bash
rdc config set machine server-1    # Machine par défaut
rdc config set team my-team        # Équipe par défaut (adaptateur cloud, expérimental)
```

Après avoir défini une machine par défaut, vous pouvez omettre `-m server-1` dans les commandes :

```bash
rdc repo create my-app --size 10G   # Utilise la machine par défaut
```

## Configurations multiples

Gérez plusieurs environnements avec des configurations nommées :

```bash
# Créer des configurations séparées
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# Utiliser une configuration spécifique
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Afficher toutes les configurations :

```bash
rdc config list
```

Afficher les détails de la configuration actuelle :

```bash
rdc config show
```
