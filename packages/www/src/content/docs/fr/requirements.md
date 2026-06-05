---
title: Prérequis
description: Configuration requise et plateformes prises en charge pour exécuter Rediacc.
category: Guides
order: 0
language: fr
sourceHash: "e84db3bb90270473"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Prérequis

La plupart de cela relève d'une configuration Linux standard. Quelques détails sont spécifiques au fonctionnement de Rediacc, alors vérifiez-les avant de commencer.

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

Si vous hésitez sur l'outil à utiliser, consultez [rdc vs renet](/en/docs/rdc-vs-renet). En bref : utilisez `rdc` pour les opérations normales et `renet` directement uniquement pour les tâches avancées côté serveur.

### Systèmes d'exploitation pris en charge

Les serveurs distants exécutent le binaire `renet` et hébergent les démons Docker chiffrés et isolés par dépôt. Les cinq distributions suivantes sont testées par la matrice Bridge Workers en CI à chaque pull request et sont les seules officiellement prises en charge :

| OS | Version | Noyau par défaut | Notes |
|----|---------|-----------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Recommandé. AppArmor activé par défaut. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 fonctionne également (noyau 6.1 minimum). |
| Fedora | 43 | 6.12 | SELinux en mode enforcing par défaut. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor activé par défaut. |
| Oracle Linux | 10 | UEK 7+ | Utilise UEK, qui conserve le module btrfs. SELinux en mode enforcing par défaut. Voir "Pourquoi UEK ?" ci-dessous. |

Toutes les lignes sont en `x86_64`. `arm64` est compilé mais pas testé en continu pour chaque OS serveur ; ouvrez un ticket si vous en avez besoin sur une distribution spécifique. D'autres distributions Linux avec systemd, le support Docker et cryptsetup peuvent fonctionner, mais ne sont pas officiellement prises en charge et peuvent se casser lors des mises à niveau sans préavis.

#### Pourquoi UEK ? (et pourquoi Rocky 10 / RHEL 10 standard n'est pas pris en charge)

Le backend de stockage chiffré de Rediacc nécessite le module noyau `btrfs` intégré. **Le noyau standard de RHEL 10 ne l'inclut pas** : `modprobe btrfs` échoue avec "Module btrfs not found" et `dnf search btrfs` ne retourne rien. Rocky Linux 10 et AlmaLinux 10 héritent du même noyau et ne peuvent donc pas fonctionner comme serveurs Rediacc.

Oracle Linux 10 utilise par défaut le **Unbreakable Enterprise Kernel (UEK)**, qui conserve btrfs intégré. C'est la seule cible compatible RHEL sur la liste des systèmes pris en charge. Si vous devez absolument utiliser un serveur de la famille RHEL, utilisez Oracle Linux 10 avec UEK. (La source de vérité pour cette décision se trouve dans `.github/workflows/ct-tests.yml` en tant que matrice CI Bridge Workers.)

#### Poste de travail uniquement (cibles d'installation CLI)

Le CLI `rdc` s'installe également proprement sur Alpine 3.19+ (APK avec la couche de compatibilité `gcompat`, installée automatiquement) et Arch Linux (rolling, via pacman). Ce sont des chemins d'installation côté client uniquement (voir [Installation](/en/docs/installation)) et ne sont pas pris en charge comme cibles de serveur `renet`.

### Politiques de sécurité par OS

Le démon Docker par dépôt et les conteneurs du dépôt s'exécutent avec des **étiquettes de conteneur par défaut** sur chaque OS pris en charge. `rdc config machine setup` n'installe pas de politiques SELinux personnalisées ni de profils AppArmor. Comportement par OS :

- **Ubuntu 24.04, openSUSE Leap 16.0** : AppArmor est activé par défaut. Le profil docker-container par défaut s'applique ; aucune configuration supplémentaire n'est requise.
- **Fedora 43, Oracle Linux 10** : SELinux fonctionne en mode enforcing. Le démon par dépôt étiquette les conteneurs avec le contexte standard `container_t`. Aucune politique SELinux personnalisée n'est nécessaire.
- **CRIU** (checkpoint/restore) est le seul cas qui contourne le profil AppArmor avec `apparmor=unconfined`, car le support AppArmor de CRIU upstream n'est pas encore stable. Voir les notes CRIU dans [Règles de Rediacc](/en/docs/rules-of-rediacc).

Si une étape de configuration échoue avec des refus AVC SELinux ou des rejets AppArmor, consultez [Dépannage](/en/docs/troubleshooting), section "Problèmes de configuration spécifiques à la distribution".

### Prérequis du serveur

- Un compte utilisateur avec les privilèges `sudo` (sudo sans mot de passe recommandé)
- Votre clé publique SSH ajoutée à `~/.ssh/authorized_keys`
- Au moins 20 Go d'espace disque libre (davantage selon vos charges de travail)
- Un accès Internet pour récupérer les images Docker (ou un registre privé)

### Installé automatiquement

La commande `rdc config machine setup` installe les éléments suivants sur le serveur distant :

- **Docker** et **containerd** (moteur d'exécution de conteneurs)
- **cryptsetup** (chiffrement de disque LUKS)
- Binaire **renet** (téléversé via SFTP)

Vous n'avez pas besoin de les installer manuellement.

## Machines virtuelles locales (Optionnel)

Si vous souhaitez tester des déploiements localement avec `rdc ops`, votre poste de travail a besoin du support de virtualisation : KVM sur Linux ou QEMU sur macOS. Consultez le guide [VMs expérimentales](/en/docs/experimental-vms) pour les étapes de configuration et les détails de la plateforme.
