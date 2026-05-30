---
title: Aide-mémoire RDC CLI
description: "Référence rapide des commandes rdc : configurations, dépôts, machines, synchronisation et conteneurs."
category: Guides
order: 3
language: fr
sourceHash: "ad0ae49efa847fbc"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Aide-mémoire RDC CLI

Référence rapide des commandes `rdc` les plus courantes. Exécutez n'importe quelle commande avec `--help` pour voir toutes les options.

## Cycle de vie du dépôt

| Commande | Description |
|----------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Créer un nouveau dépôt sur une machine |
| `rdc repo up --name <repo> -m <machine>` | Déployer ou mettre à jour un dépôt |
| `rdc repo down --name <repo> -m <machine>` | Arrêter un dépôt |
| `rdc repo delete --name <repo> -m <machine>` | Supprimer un dépôt |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Bifurquer un dépôt (quasi-instantané, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Prendre possession d'un dépôt existant |
| `rdc config repository list` | Lister tous les dépôts avec leur nom et GUID |

## Sauvegarde et restauration

| Commande | Description |
|----------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Pousser une sauvegarde du dépôt vers le stockage |
| `rdc repo push --to <storage> -m <machine>` | Pousser tous les dépôts vers le stockage |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Restaurer un dépôt depuis le stockage |
| `rdc repo pull --from <storage> -m <machine>` | Restaurer tous les dépôts depuis le stockage |
| `rdc repo push ... --bwlimit <limit>` | Limiter la bande passante rsync lors de l'envoi (ex. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limiter la bande passante rsync lors de la réception |
| `rdc repo push ... --checkpoint` | Créer un point de contrôle des conteneurs avant l'envoi |
| `rdc repo backup list --from <storage> -m <machine>` | Lister les sauvegardes disponibles dans le stockage |
| `rdc storage browse --name <storage>` | Parcourir le contenu du stockage |

## Migration de dépôt

| Commande | Description |
|----------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Déplacer un dépôt entre deux machines |
| `rdc repo migrate ... --provision` | Provisionner la destination avant le transfert |
| `rdc repo migrate ... --checkpoint` | Créer un point de contrôle avant de migrer |
| `rdc repo migrate ... --skip-dns` | Ignorer la mise à jour DNS après la migration |
| `rdc repo migrate ... --bwlimit <limit>` | Limiter la bande passante de transfert |

## Stratégies de sauvegarde

| Commande | Description |
|----------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Créer ou mettre à jour une stratégie de sauvegarde nommée |
| `rdc config backup-strategy list` | Lister toutes les stratégies définies |
| `rdc config backup-strategy show --name <name>` | Afficher les détails d'une stratégie |
| `rdc config backup-strategy remove --name <name>` | Supprimer une stratégie |
| `rdc machine backup schedule -m <machine>` | Déployer les stratégies de sauvegarde configurées sur une machine |

## Opérations de sauvegarde

| Commande | Description |
|----------|-------------|
| `rdc machine backup schedule -m <machine>` | Déployer les stratégies associées comme minuteries systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Aperçu des unités de minuterie sans déploiement (tokens masqués) |
| `rdc machine backup now -m <machine>` | Exécuter immédiatement toutes les stratégies associées |
| `rdc machine backup now -m <machine> --strategy <name>` | Exécuter immédiatement une stratégie spécifique |
| `rdc machine backup status -m <machine>` | Afficher l'état des minuteries et les résultats récents des tâches |
| `rdc machine backup status -m <machine> --strategy <name>` | Afficher l'état d'une stratégie spécifique |
| `rdc machine backup cancel -m <machine>` | Annuler les sauvegardes en cours |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Annuler une sauvegarde en cours spécifique |

## Gestion des machines

| Commande | Description |
|----------|-------------|
| `rdc machine query --name <machine>` | État complet de la machine (système, conteneurs, services, dépôts, réseau) |
| `rdc machine query --name <machine> --system` | Informations système uniquement |
| `rdc machine query --name <machine> --containers` | Liste des conteneurs uniquement |
| `rdc machine query --name <machine> --repositories` | Liste des dépôts uniquement |
| `rdc machine query --name <machine> --services` | Liste des services uniquement |
| `rdc machine query --name <machine> --network` | Informations réseau uniquement |
| `rdc machine query --name <machine> --block-devices` | Informations sur les périphériques de bloc uniquement |
| `rdc machine list` | Lister toutes les machines dans la configuration |
| `rdc config machine setup --name <machine>` | Exécuter le provisionnement initial de la machine |
| `rdc machine prune --name <machine>` | Supprimer les ressources inutilisées de la machine |
| `rdc machine deprovision --name <machine>` | Déprovisionner complètement une machine |
| `rdc machine vault-status --name <machine>` | Afficher l'état du vault LUKS |

## Terminal et synchronisation

| Commande | Description |
|----------|-------------|
| `rdc term connect -m <machine>` | Ouvrir un terminal SSH vers la machine |
| `rdc term connect -m <machine> -r <repo>` | Ouvrir un terminal SSH vers le dépôt (définit DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Exécuter une commande sur la machine |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Téléverser un fichier, un répertoire ou plusieurs sources vers le dépôt |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Télécharger un répertoire du dépôt localement |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Télécharger un fichier distant dans un répertoire local |
| `rdc vscode connect -m <machine> -r <repo>` | Ouvrir une session VS Code Remote SSH |

## Configuration

| Commande | Description |
|----------|-------------|
| `rdc config init --name <name>` | Créer un fichier de configuration nommé |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Ajouter une machine à la configuration |
| `rdc config storage import --file rclone.conf` | Importer des fournisseurs de stockage depuis la configuration rclone |
| `rdc config storage list` | Lister les fournisseurs de stockage configurés |
| `rdc config backup-strategy set ...` | Définir une stratégie de sauvegarde nommée |
| `rdc --config <name> <command>` | Utiliser un fichier de configuration nommé |

## Débogage et accès direct

| Commande | Description |
|----------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Lister les conteneurs dans un dépôt |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Récupérer les journaux d'un conteneur |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Exécuter une commande dans un conteneur |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Redémarrer un conteneur |
