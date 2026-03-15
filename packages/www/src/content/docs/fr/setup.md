---
title: "Configuration de la machine"
description: "Créez une configuration, ajoutez des machines, provisionnez des serveurs et configurez l'infrastructure."
category: "Guides"
order: 3
language: fr
sourceHash: "ebf1c9967814ec86"
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
rdc config machine add server-1 --ip 203.0.113.50 --user deploy
```

| Option | Requis | Par défaut | Description |
|--------|--------|------------|-------------|
| `--ip <address>` | Oui | - | Adresse IP ou nom d'hôte du serveur distant |
| `--user <username>` | Oui | - | Nom d'utilisateur SSH sur le serveur distant |
| `--port <port>` | Non | `22` | Port SSH |
| `--datastore <path>` | Non | `/mnt/rediacc` | Chemin sur le serveur où Rediacc stocke les dépôts chiffrés |

Après l'ajout de la machine, rdc exécute automatiquement `ssh-keyscan` pour récupérer les clés d'hôte du serveur. Vous pouvez également l'exécuter manuellement :

```bash
rdc config machine scan-keys server-1
```

Pour afficher toutes les machines enregistrées :

```bash
rdc config machine list
```

## Étape 3 : Configurer la machine

Provisionnez le serveur distant avec toutes les dépendances requises :

```bash
rdc config machine setup server-1
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
rdc config machine scan-keys server-1
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
rdc config infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Portée | Description |
|--------|--------|-------------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address — proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address — proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | Domaine de base pour les applications (par ex., `example.com`) |
| `--cert-email <email>` | Config | Email pour les certificats TLS Let's Encrypt (partagé entre les machines) |
| `--cf-dns-token <token>` | Config | Jeton API DNS Cloudflare pour les challenges ACME DNS-01 (partagé entre les machines) |
| `--tcp-ports <ports>` | Machine | Ports TCP supplémentaires à rediriger, séparés par des virgules (par ex., `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Ports UDP supplémentaires à rediriger, séparés par des virgules (par ex., `53`) |

Les options de portée Machine sont stockées par machine. Les options de portée Config (`--cert-email`, `--cf-dns-token`) sont partagées entre toutes les machines de la configuration — définissez-les une fois et elles s'appliquent partout.

### Afficher l'infrastructure

```bash
rdc config infra show server-1
```

### Déployer sur le serveur

Générez et déployez la configuration du proxy inverse Traefik sur le serveur :

```bash
rdc config infra push server-1
```

Cette commande :
1. Déploie le binaire renet sur la machine distante
2. Configure le proxy inverse Traefik, le routeur et les services systemd
3. Crée les enregistrements DNS Cloudflare pour le sous-domaine de la machine (`server-1.example.com` et `*.server-1.example.com`) si `--cf-dns-token` est défini

L'étape DNS est automatique et idempotente — elle crée les enregistrements manquants, met à jour les enregistrements dont les IPs ont changé et ignore les enregistrements déjà corrects. Si aucun jeton Cloudflare n'est configuré, le DNS est ignoré avec un avertissement. Per-repo wildcard DNS records (for auto-routes) are created automatically when you run `rdc repo up`.

## Provisionnement cloud

Au lieu de créer des VMs manuellement, vous pouvez configurer un fournisseur cloud et laisser `rdc` provisionner les machines automatiquement avec [OpenTofu](https://opentofu.org/).

### Prérequis

Installez OpenTofu : [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Assurez-vous que votre configuration SSH inclut une clé publique :

```bash
rdc config set ssh.privateKeyPath ~/.ssh/id_ed25519
```

### Ajouter un fournisseur cloud

```bash
rdc config provider add my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Option | Requis | Description |
|--------|--------|-------------|
| `--provider <source>` | Oui* | Source de fournisseur connu (par ex., `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Oui* | Source de fournisseur OpenTofu personnalisée (pour les fournisseurs inconnus) |
| `--token <token>` | Oui | Jeton API du fournisseur cloud |
| `--region <region>` | Non | Région par défaut pour les nouvelles machines |
| `--type <type>` | Non | Type/taille d'instance par défaut |
| `--image <image>` | Non | Image OS par défaut |
| `--ssh-user <user>` | Non | Nom d'utilisateur SSH (par défaut : `root`) |

\* `--provider` ou `--source` est requis. Utilisez `--provider` pour les fournisseurs connus (valeurs par défaut intégrées). Utilisez `--source` avec les drapeaux supplémentaires `--resource`, `--ipv4-output`, `--ssh-key-attr` pour les fournisseurs personnalisés.

### Provisionner une machine

```bash
rdc machine provision prod-2 --provider my-linode
```

Cette unique commande :
1. Crée une VM chez le fournisseur cloud via OpenTofu
2. Attend la connectivité SSH
3. Enregistre la machine dans votre configuration
4. Installe renet et toutes les dépendances
5. Configures Traefik proxy and Cloudflare DNS (auto-detects base domain from sibling machines, or pass `--base-domain` explicitly)

| Option | Description |
|--------|-------------|
| `--provider <name>` | Nom du fournisseur cloud (de `add-provider`) |
| `--region <region>` | Remplace la région par défaut du fournisseur |
| `--type <type>` | Remplace le type d'instance par défaut |
| `--image <image>` | Remplace l'image OS par défaut |
| `--base-domain <domain>` | Base domain for infrastructure. Auto-detected from sibling machines if not specified |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | Affiche la sortie détaillée du provisionnement |

### Déprovisionner une machine

```bash
rdc machine deprovision prod-2
```

Détruit la VM via OpenTofu et la supprime de votre configuration. Nécessite une confirmation sauf si `--force` est utilisé. Ne fonctionne que pour les machines créées avec `machine provision`.

### Lister les fournisseurs

```bash
rdc config provider list
```

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
