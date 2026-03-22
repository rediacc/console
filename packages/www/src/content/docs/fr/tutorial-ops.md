---
title: "Provisionnement de VM locales"
description: "Provisionner un cluster de VM local, exécuter des commandes via SSH et le démonter avec la CLI."
category: "Tutorials"
order: 1
language: fr
sourceHash: "2fdc49f796b03e18"
---

# Comment provisionner des VMs locales avec Rediacc

Tester l'infrastructure localement avant de déployer en production fait gagner du temps et évite les erreurs de configuration. Dans ce tutoriel, vous provisionnez un cluster de VM minimal sur votre poste de travail, vérifiez la connectivité, exécutez des commandes via SSH et démontez le tout. À la fin, vous disposez d'un environnement de développement local reproductible.

## Prérequis

- Un poste de travail Linux ou macOS avec la virtualisation matérielle activée
- La CLI `rdc` installée et une configuration initialisée avec l'adaptateur local
- KVM/libvirt (Linux) ou QEMU (macOS) installé — voir [VMs expérimentales](/fr/docs/experimental-vms) pour les instructions d'installation

## Enregistrement interactif

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### Étape 1 : Vérifier les prérequis système

Avant le provisionnement, confirmez que votre poste de travail dispose du support de virtualisation et des paquets requis installés.

```bash
rdc ops check
```

Rediacc vérifie la virtualisation matérielle (VT-x/AMD-V), les paquets requis (libvirt, QEMU) et la configuration réseau. Toutes les vérifications doivent réussir avant de pouvoir créer des VMs.

### Étape 2 : Provisionner un cluster de VM minimal

```bash
rdc ops up --basic --skip-orchestration
```

Crée un cluster de deux VMs : une VM **pont** (1 CPU, 1024 Mo RAM, 8 Go disque) et une VM **worker** (2 CPU, 4096 Mo RAM, 16 Go disque). L'option `--skip-orchestration` ignore le provisionnement de la plateforme Rediacc, vous donnant des VMs nues avec accès SSH uniquement.

> **Remarque :** Le premier provisionnement télécharge les images de base, ce qui prend plus de temps. Les exécutions suivantes réutilisent les images mises en cache.

### Étape 3 : Vérifier le statut du cluster

```bash
rdc ops status
```

Affiche l'état de chaque VM dans le cluster — adresses IP, allocation des ressources et statut d'exécution. Les deux VMs devraient apparaître comme en cours d'exécution.

### Étape 4 : Exécuter des commandes sur une VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Exécute des commandes sur la VM pont (ID `1`) via SSH. Passez n'importe quelle commande après l'ID de la VM. Pour un shell interactif, omettez la commande : `rdc ops ssh 1`.

### Étape 5 : Démonter le cluster

Lorsque vous avez terminé, détruisez toutes les VMs et libérez les ressources.

```bash
rdc ops down
```

Supprime toutes les VMs et nettoie le réseau. Le cluster peut être reprovisionné à tout moment avec `rdc ops up`.

## Dépannage

**"KVM not available" ou "hardware virtualization not supported"**
Vérifiez que la virtualisation est activée dans les paramètres de votre BIOS/UEFI. Sous Linux, vérifiez avec `lscpu | grep Virtualization`. Sous WSL2, la virtualisation imbriquée nécessite des flags de noyau spécifiques.

**"libvirt daemon not running"**
Démarrez le service libvirt : `sudo systemctl start libvirtd`. Sous macOS, vérifiez que QEMU est installé via Homebrew : `brew install qemu`.

**"Insufficient memory for VM allocation"**
Le cluster de base nécessite au moins 6 Go de RAM libre (1 Go pont + 4 Go worker + overhead). Fermez les autres applications gourmandes en ressources ou réduisez les spécifications des VMs.

## Étapes suivantes

Vous avez provisionné un cluster de VM local, exécuté des commandes via SSH et démonté le tout. Pour déployer une infrastructure réelle :

- [VMs expérimentales](/fr/docs/experimental-vms) — référence complète pour les commandes `rdc ops`, la configuration des VMs et le support des plateformes
- [Tutoriel : Configuration des machines](/fr/docs/tutorial-setup) — enregistrer des machines distantes et configurer l'infrastructure
- [Démarrage rapide](/fr/docs/quick-start) — déployer un service conteneurisé de bout en bout
