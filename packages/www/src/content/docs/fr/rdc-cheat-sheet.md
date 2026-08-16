---
title: Aide-mémoire RDC CLI
description: "Référence rapide des commandes rdc : configurations, dépôts, machines, synchronisation et conteneurs. Ensemble complet d'options : ajoutez --help à toute commande."
category: Guides
order: 3
cardGrid: true
language: fr
sourceHash: "26e60c6b486eadd0"
sourceCommit: "45cd71f8a80949d4cd621f233377c48715bbf531"
---

# Aide-mémoire RDC CLI

Cette aide-mémoire couvre les commandes `rdc` essentielles au déploiement quotidien, non la liste exhaustive. Pour voir toutes les options, ajoutez `--help` à n'importe quelle commande. Les cas particuliers et options rarement utilisées figurent dans la documentation complète.

## Cycle de vie du dépôt

| Commande | Description |
|----------|-------------|
| `rdc repo create <repo> -m <machine>` | Créer un nouveau dépôt sur une machine |
| `rdc repo up <repo>@<machine>` | Déployer ou mettre à jour un dépôt |
| `rdc repo down <repo>@<machine>` | Arrêter un dépôt |
| `rdc repo delete <repo>@<machine>` | Supprimer un dépôt |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Bifurquer un dépôt (quasi-instantané, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Promouvoir un fork validé en production sous le nom du dépôt parent |
| `rdc repo list` | Lister tous les dépôts avec leur nom et GUID |
| `rdc repo resize <repo> --size <size>` | Redimensionner le volume d'un dépôt arrêté |
| `rdc repo expand <repo> --size <size>` | Agrandir sur place le volume d'un dépôt en cours d'exécution |

## Secrets par dépôt

Identifiants de déploiement en lecture seule. `get` retourne seulement un digest. La valeur n'est jamais retournée. Consultez [Dépôts § Secrets](/en/docs/repositories#secrets) pour le guide complet.

| Commande | Description |
|----------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Créer un nouveau secret (`--current ""` pour la première écriture) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Écraser un secret existant (précondition de type passwd) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Écraser sans vérifier la valeur précédente (audité comme rotation) |
| `rdc repo secret list <repo>` | Lister les noms des secrets et modes de livraison (jamais les valeurs, jamais les digests) |
| `rdc repo secret get <repo> --key <KEY>` | Afficher le digest du secret et le mode (aucune valeur en clair, jamais) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Supprimer un secret |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Supprimer sans vérifier la valeur précédente |

> Les bifurcations n'héritent pas des secrets. Définissez-les explicitement sur la bifurcation avec `rdc repo secret set <repo>:<tag>`.

## Sauvegarde et restauration

| Commande | Description |
|----------|-------------|
| `rdc repo push ... --bwlimit <limit>` | Limiter la bande passante rsync lors de l'envoi (ex. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limiter la bande passante rsync lors de la réception |
| `rdc repo push ... --checkpoint` | Créer un point de contrôle des conteneurs avant l'envoi |
| `rdc backup manifests <repo-ref>` | Lister les instantanés que le stockage fragmenté contient |
| `rdc backup browse <repo-ref>` | Lister les fichiers contenus dans un dépôt (local, lecture seule) |
| `rdc backup snapshot <repo>` | Envoyer un instantané vers le stockage fragmenté : inventaire complet d'abord, cellules modifiées ensuite |
| `rdc backup snapshot <repo> --dry-run` | Planifier l'instantané sans l'envoyer ; indique ce qui serait déplacé |
| `rdc backup verify <repo>` | Vérifier l'ancre de sauvegarde d'un dépôt par rapport au stockage fragmenté |
| `rdc backup usage` | Afficher les octets stockés dans le stockage fragmenté par rapport à votre quota |
| `rdc backup manifests <repo>` | Lister les manifestes d'instantanés enregistrés sur le serveur |
| `rdc storage browse <storage>` | Parcourir le contenu du stockage |

## Migration de dépôt

| Commande | Description |
|----------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Déplacer un dépôt entre deux machines |
| `rdc repo migrate ... --provision` | Provisionner la destination avant le transfert |
| `rdc repo migrate ... --checkpoint` | Créer un point de contrôle avant de migrer |
| `rdc repo migrate ... --skip-dns` | Ignorer la mise à jour DNS après la migration |
| `rdc repo migrate ... --bwlimit <limit>` | Limiter la bande passante de transfert |

## Stratégies de sauvegarde

| Commande | Description |
|----------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Créer ou mettre à jour une stratégie de sauvegarde nommée |
| `rdc backup strategy list` | Lister toutes les stratégies définies |
| `rdc backup strategy show <name>` | Afficher les détails d'une stratégie |
| `rdc backup strategy remove <name>` | Supprimer une stratégie |
| `rdc backup schedule -m <machine>` | Déployer les stratégies de sauvegarde configurées sur une machine |

## Opérations de sauvegarde

| Commande | Description |
|----------|-------------|
| `rdc backup schedule -m <machine>` | Déployer les stratégies associées comme minuteries systemd |
| `rdc backup schedule -m <machine> --dry-run` | Aperçu des unités de minuterie sans déploiement (tokens masqués) |
| `rdc backup run -m <machine>` | Exécuter immédiatement toutes les stratégies associées |
| `rdc backup run <name> -m <machine>` | Exécuter immédiatement une stratégie spécifique |
| `rdc backup status -m <machine>` | Afficher l'état des minuteries et les résultats récents des tâches |
| `rdc backup status <name> -m <machine>` | Afficher l'état d'une stratégie spécifique |
| `rdc backup cancel -m <machine>` | Annuler les sauvegardes en cours |
| `rdc backup cancel <name> -m <machine>` | Annuler une sauvegarde en cours spécifique |

## Gestion des machines

| Commande | Description |
|----------|-------------|
| `rdc machine status <machine>` | État complet de la machine (système, conteneurs, services, dépôts, réseau) |
| `rdc machine status <machine> --system` | Informations système uniquement |
| `rdc machine status <machine> --containers` | Liste des conteneurs uniquement |
| `rdc machine status <machine> --repositories` | Liste des dépôts uniquement |
| `rdc machine status <machine> --services` | Liste des services uniquement |
| `rdc machine status <machine> --network` | Informations réseau uniquement |
| `rdc machine status <machine> --block-devices` | Informations sur les périphériques de bloc uniquement |
| `rdc machine list` | Lister toutes les machines dans la configuration |
| `rdc machine setup <machine>` | Exécuter le provisionnement initial de la machine |
| `rdc machine health <machine>` | Vérifier l'état de santé d'une machine |
| `rdc machine scan-keys <machine>` | Actualiser les clés d'hôte SSH après une reconstruction |
| `rdc machine prune <machine>` | Supprimer les ressources inutilisées de la machine |
| `rdc machine deprovision <machine>` | Déprovisionner complètement une machine |

## Terminal et synchronisation

| Commande | Description |
|----------|-------------|
| `rdc term connect <machine>` | Ouvrir un terminal SSH vers la machine |
| `rdc term connect <repo>@<machine>` | Ouvrir un terminal SSH vers le dépôt (définit DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Exécuter une commande sur la machine |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Téléverser un ou plusieurs fichiers/répertoires locaux vers le dépôt |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Téléverser un fichier local unique vers un chemin distant explicite |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Télécharger un répertoire du dépôt localement |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Télécharger un fichier distant dans un répertoire local |
| `rdc vscode connect <repo>@<machine>` | Ouvrir une session VS Code Remote SSH |
| `rdc vscode list` | Lister les configurations SSH créées par `vscode connect` |
| `rdc vscode cleanup --all` | Supprimer toutes les configurations SSH écrites par `vscode connect` |
| `rdc repo tunnel <repo> -c <container> --port <port>` | Rediriger le port d'un conteneur via SSH |

## Configuration

| Commande | Description |
|----------|-------------|
| `rdc config init <name>` | Créer un fichier de configuration nommé |
| `rdc config list` | Lister toutes les configurations sur cette machine |
| `rdc config set machine <alias>` | Faire pointer un alias vers une autre machine |
| `rdc machine add <machine> --ip <host> --user <user>` | Ajouter une machine à la configuration |
| `rdc storage import rclone.conf` | Importer des fournisseurs de stockage depuis la configuration rclone |
| `rdc storage list` | Lister les fournisseurs de stockage configurés |
| `rdc backup strategy set ...` | Définir une stratégie de sauvegarde nommée |
| `rdc --config <name> <command>` | Utiliser un fichier de configuration nommé |

## Débogage et accès direct

| Commande | Description |
|----------|-------------|
| `rdc repo logs <repo>@<machine> -c <container> --lines 200 --follow` | Diffuser les journaux d'un conteneur (recommandé) |
| `rdc repo exec <repo>@<machine> -c <container> -- <command>` | Exécuter une commande dans un conteneur (recommandé) |
| `rdc repo exec <repo>@<machine> -c <container> -i -- bash` | Ouvrir un shell interactif dans un conteneur |
| `rdc term connect <repo>@<machine> -c "docker ps"` | Lister les conteneurs dans un dépôt |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Récupérer les journaux d'un conteneur |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Exécuter une commande dans un conteneur |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Redémarrer un conteneur |
