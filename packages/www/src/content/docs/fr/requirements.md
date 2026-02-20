---
title: Prérequis
description: Configuration requise et plateformes prises en charge pour exécuter Rediacc.
category: Guides
order: 0
language: fr
sourceHash: ea4a06f2deefab73
---

# Prérequis

Si vous hésitez sur l'outil a utiliser, consultez [rdc vs renet](/fr/docs/rdc-vs-renet).

Avant de déployer avec Rediacc, assurez-vous que votre poste de travail et vos serveurs distants répondent aux exigences suivantes.

## Poste de travail (Plan de contrôle)

Le CLI `rdc` s'exécute sur votre poste de travail et orchestre les serveurs distants via SSH.

| Plateforme | Version minimale | Notes |
|----------|----------------|-------|
| macOS | 12 (Monterey)+ | Intel et Apple Silicon pris en charge |
| Linux (x86_64) | Toute distribution moderne | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Support natif via l'installateur PowerShell |

**Exigences supplémentaires :**
- Une paire de clés SSH (par ex., `~/.ssh/id_ed25519` ou `~/.ssh/id_rsa`)
- Un accès réseau à vos serveurs distants sur le port SSH (par défaut : 22)

## Serveur distant (Plan de données)

Le binaire `renet` s'exécute sur les serveurs distants avec les privilèges root. Il gère les images disque chiffrées, les démons Docker isolés et l'orchestration des services.

### Systèmes d'exploitation pris en charge

| OS | Version | Architecture |
|----|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |

Ce sont les distributions testées en CI. D'autres distributions Linux avec systemd, le support Docker et cryptsetup peuvent fonctionner mais ne sont pas officiellement prises en charge.

### Prérequis du serveur

- Un compte utilisateur avec les privilèges `sudo` (sudo sans mot de passe recommandé)
- Votre clé publique SSH ajoutée à `~/.ssh/authorized_keys`
- Au moins 20 Go d'espace disque libre (davantage selon vos charges de travail)
- Un accès Internet pour récupérer les images Docker (ou un registre privé)

### Installé automatiquement

La commande `rdc context setup-machine` installe les éléments suivants sur le serveur distant :

- **Docker** et **containerd** (moteur d'exécution de conteneurs)
- **cryptsetup** (chiffrement de disque LUKS)
- Binaire **renet** (téléversé via SFTP)

Vous n'avez pas besoin de les installer manuellement.
