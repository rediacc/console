---
title: "VM expérimentales"
description: "Provisionner des clusters de VM locaux pour le développement et les tests avec rdc ops."
category: "Concepts"
order: 2
language: fr
sourceHash: fa4069c48c650a79
---

# Experimental VMs

Provisionnez des clusters de VM locaux sur votre poste de travail pour le développement et les tests — aucun fournisseur cloud externe requis.

## Prérequis

`rdc ops` nécessite l'**adaptateur local**. Il n'est pas disponible avec l'adaptateur cloud.

```bash
rdc ops check
```

## Vue d'ensemble

Les commandes `rdc ops` vous permettent de créer et de gérer des clusters de VM expérimentaux en local. Il s'agit de la même infrastructure utilisée par le pipeline CI pour les tests d'intégration, désormais disponible pour l'expérimentation pratique.

Cas d'usage :
- Tester les déploiements Rediacc sans fournisseurs VM externes (Linode, Vultr, etc.)
- Développer et déboguer des configurations de dépôts en local
- Apprendre la plateforme dans un environnement totalement isolé
- Exécuter des tests d'intégration sur votre poste de travail

## Compatibilité des plateformes

| Plateforme | Architecture | Backend | Statut |
|------------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Testé en CI |
| macOS | Intel | QEMU + HVF | Testé en CI |
| Linux | ARM64 | KVM (libvirt) | Supporté (non testé en CI) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Supporté (non testé en CI) |
| Windows | x86_64 / ARM64 | Hyper-V | Planifié |

**Linux (KVM)** utilise libvirt pour la virtualisation matérielle native avec une mise en réseau bridge.

**macOS (QEMU)** utilise QEMU avec le framework Hypervisor d'Apple (HVF) pour des performances quasi-natives, avec une mise en réseau en mode utilisateur et une redirection de port SSH.

**Windows (Hyper-V)** est planifié. Voir [issue #380](https://github.com/rediacc/console/issues/380) pour les détails. Nécessite Windows Pro/Enterprise.

## Prérequis et configuration

### Linux

```bash
# Installer les prérequis automatiquement
rdc ops setup

# Ou manuellement :
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Installer les prérequis automatiquement
rdc ops setup

# Ou manuellement :
brew install qemu cdrtools
```

### Vérifier la configuration

```bash
rdc ops check
```

Cette commande effectue des vérifications spécifiques à la plateforme et rapporte succès/échec pour chaque prérequis.

## Démarrage rapide

```bash
# 1. Vérifier les prérequis
rdc ops check

# 2. Provisionner un cluster minimal (bridge + 1 worker)
rdc ops up --basic

# 3. Vérifier l'état des VM
rdc ops status

# 4. Se connecter en SSH à la VM bridge
rdc ops ssh 1

# 4b. Ou exécuter une commande directement
rdc ops ssh 1 hostname

# 5. Démanteler
rdc ops down
```

## Composition du cluster

Par défaut, `rdc ops up` provisionne :

| VM | ID | Rôle |
|----|-----|------|
| Bridge | 1 | Nœud principal — exécute le service bridge Rediacc |
| Worker 1 | 11 | Nœud worker pour les déploiements de dépôts |
| Worker 2 | 12 | Nœud worker pour les déploiements de dépôts |

Utilisez l'option `--basic` pour ne provisionner que le bridge et le premier worker (IDs 1 et 11).

Utilisez `--skip-orchestration` pour provisionner des VM sans démarrer les services Rediacc — utile pour tester la couche VM de manière isolée.

## Configuration

La VM bridge utilise des ressources par défaut plus petites que les VM workers :

| Rôle VM | CPUs | RAM | Disque |
|---------|------|-----|--------|
| Bridge | 1 | 1024 Mo | 8 Go |
| Worker | 2 | 4096 Mo | 16 Go |

Les variables d'environnement remplacent les ressources des VM workers :

| Variable | Par défaut | Description |
|----------|------------|-------------|
| `VM_CPU` | 2 | Cœurs CPU par VM worker |
| `VM_RAM` | 4096 | RAM en Mo par VM worker |
| `VM_DSK` | 16 | Taille du disque en Go par VM worker |
| `VM_NET_BASE` | 192.168.111 | Base réseau (KVM uniquement) |
| `RENET_DATA_DIR` | ~/.renet | Répertoire de données pour les disques et la configuration des VM |

## Référence des commandes

| Commande | Description |
|----------|-------------|
| `rdc ops setup` | Installer les prérequis de la plateforme (KVM ou QEMU) |
| `rdc ops check` | Vérifier que les prérequis sont installés et fonctionnels |
| `rdc ops up [options]` | Provisionner le cluster de VM |
| `rdc ops down` | Détruire toutes les VM et nettoyer |
| `rdc ops status` | Afficher le statut de toutes les VM |
| `rdc ops ssh <vm-id> [command...]` | Se connecter en SSH à une VM, ou y exécuter une commande |

### Options de `rdc ops up`

| Option | Description |
|--------|-------------|
| `--basic` | Cluster minimal (bridge + 1 worker) |
| `--lite` | Ignorer le provisionnement des VM (clés SSH uniquement) |
| `--force` | Forcer la recréation des VM existantes |
| `--parallel` | Provisionner les VM en parallèle |
| `--skip-orchestration` | VM uniquement, sans services Rediacc |
| `--backend <kvm\|qemu>` | Remplacer le backend auto-détecté |
| `--os <name>` | Image OS (par défaut : ubuntu-24.04) |
| `--debug` | Sortie détaillée |

## Différences selon la plateforme

### Linux (KVM)
- Utilise libvirt pour la gestion du cycle de vie des VM
- Mise en réseau bridge — les VM obtiennent des IP sur un réseau virtuel (192.168.111.x)
- SSH direct vers les IP des VM
- Nécessite `/dev/kvm` et le service libvirtd

### macOS (QEMU + HVF)
- Utilise des processus QEMU gérés via des fichiers PID
- Mise en réseau en mode utilisateur avec redirection de port SSH (localhost:222XX)
- SSH via les ports redirigés, pas les IP directes
- ISOs cloud-init créés via `mkisofs`

## Dépannage

### Mode debug

Ajoutez `--debug` à n'importe quelle commande pour une sortie détaillée :

```bash
rdc ops up --basic --debug
```

### Problèmes courants

**KVM non disponible (Linux)**
- Vérifiez que `/dev/kvm` existe : `ls -la /dev/kvm`
- Activez la virtualisation dans le BIOS/UEFI
- Chargez le module noyau : `sudo modprobe kvm_intel` ou `sudo modprobe kvm_amd`

**libvirtd non lancé (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU introuvable (macOS)**
```bash
brew install qemu cdrtools
```

**Les VM ne démarrent pas**
- Vérifiez l'espace disque dans `~/.renet/disks/`
- Exécutez `rdc ops check` pour vérifier tous les prérequis
- Essayez `rdc ops down` puis `rdc ops up --force`
