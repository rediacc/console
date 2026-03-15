---
title: "Configuration de la machine"
description: "Créez un profil de configuration, enregistrez une machine distante, vérifiez la connectivité SSH et configurez les paramètres d'infrastructure."
category: "Tutorials"
order: 2
language: fr
sourceHash: "04756cddd86e097c"
---

# Comment configurer une machine avec Rediacc

Chaque déploiement Rediacc commence par un profil de configuration et une machine enregistrée. Dans ce tutoriel, vous créez une configuration, enregistrez un serveur distant, vérifiez la connectivité SSH, exécutez des diagnostics d'environnement et configurez le réseau d'infrastructure. À la fin, votre machine est prête pour les déploiements de dépôts.

## Prérequis

- La CLI `rdc` installée
- Un serveur distant (ou VM locale) accessible via SSH
- Une clé privée SSH pouvant s'authentifier auprès du serveur

## Enregistrement interactif

![Tutoriel : Configuration de la machine](/assets/tutorials/setup-tutorial.cast)

### Étape 1 : Créer une nouvelle configuration

Un profil de configuration stocke les définitions de machines, les identifiants SSH et les paramètres d'infrastructure. Créez-en un pour cet environnement.

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Cela crée un fichier de configuration nommé dans `~/.config/rediacc/tutorial-demo.json`.

### Étape 2 : Voir les configurations

Vérifiez que le nouveau profil apparaît dans la liste des configurations.

```bash
rdc config list
```

Liste toutes les configurations disponibles avec leur type d'adaptateur (local ou cloud) et le nombre de machines.

### Étape 3 : Ajouter une machine

Enregistrez une machine avec son adresse IP et son utilisateur SSH. La CLI récupère et stocke automatiquement les clés d'hôte du serveur via `ssh-keyscan`.

```bash
rdc config machine add bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### Étape 4 : Voir les machines

Confirmez que la machine a été enregistrée correctement.

```bash
rdc config machine list --config tutorial-demo
```

Affiche toutes les machines dans la configuration actuelle avec leurs détails de connexion.

### Étape 5 : Définir la machine par défaut

Définir une machine par défaut évite de répéter `-m bridge-vm` à chaque commande.

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### Étape 6 : Tester la connectivité

Avant de déployer quoi que ce soit, vérifiez que la machine est accessible via SSH.

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Les deux commandes s'exécutent sur la machine distante et retournent immédiatement. Si l'une échoue, vérifiez que votre clé SSH est correcte et que le serveur est accessible.

### Étape 7 : Exécuter les diagnostics

```bash
rdc doctor
```

Vérifie votre environnement local : version de la CLI, Docker, binaire renet, état de la configuration, clé SSH et prérequis de virtualisation. Chaque vérification indique **OK**, **Warning** ou **Error**.

### Étape 8 : Configurer l'infrastructure

Pour les services accessibles publiquement, la machine nécessite une configuration réseau — son IP externe, un domaine de base et un email de certificat pour TLS.

```bash
rdc config infra set bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Vérifiez la configuration :

```bash
rdc config infra show bridge-vm
```

Déployez la configuration du proxy Traefik générée sur le serveur avec `rdc config infra push bridge-vm`.

## Dépannage

**"SSH key not found" ou "Permission denied (publickey)"**
Vérifiez que le chemin de clé passé à `config init` existe et correspond au `authorized_keys` du serveur. Vérifiez les permissions : le fichier de clé privée doit être `600` (`chmod 600 ~/.ssh/id_ed25519`).

**"Connection refused" sur les commandes SSH**
Confirmez que le serveur fonctionne et que l'IP est correcte. Vérifiez que le port 22 est ouvert : `nc -zv <ip> 22`. Si vous utilisez un port non standard, passez `--port` lors de l'ajout de la machine.

**"Host key verification failed"**
La clé d'hôte stockée ne correspond pas à la clé actuelle du serveur. Cela se produit après une reconstruction du serveur ou une réattribution d'IP. Exécutez `rdc config machine scan-keys <machine>` pour actualiser la clé.

## Étapes suivantes

Vous avez créé un profil de configuration, enregistré une machine, vérifié la connectivité et configuré le réseau d'infrastructure. Pour déployer des applications :

- [Configuration de la machine](/fr/docs/setup) — référence complète pour toutes les commandes de configuration et de setup
- [Tutoriel : Cycle de vie des dépôts](/fr/docs/tutorial-repos) — créer, déployer et gérer des dépôts
- [Démarrage rapide](/fr/docs/quick-start) — déployer une application conteneurisée de bout en bout
