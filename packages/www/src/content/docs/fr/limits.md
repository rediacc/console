---
title: Limites et quotas
description: >-
  Référence des limites, maximums et quotas qui s'appliquent aux
  repositories, services, réseaux et stockage Rediacc.
category: Reference
order: 99
language: fr
sourceHash: "ece2d423d416e7ec"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Limites et quotas

Limites de déploiement Rediacc. Trois sont incontournables et ne peuvent pas être contournées en ajoutant du matériel : le plafond de 61 services par repository (allocation d'espace d'adressage réseau), la version minimale de kernel 6.1 (exigences CRIU), et le plafond d'émission Let's Encrypt de 50 certificats génériques par domaine enregistré par semaine. Tout le reste est souple : cela évolue quand vous ajoutez du matériel. Connaître cette distinction avant de définir votre topologie.

---

## Services par repository

Chaque repository prend en charge jusqu'à **61 services** fonctionnant simultanément.

Il s'agit d'une limite fixe déterminée par l'espace d'adresses réseau alloué à chaque repository. Chaque service reçoit sa propre adresse IP privée dédiée, et le bloc d'adresses de chaque repository accueille exactement 61 emplacements de service.

Atteindre 61 services dans un seul repository signale généralement un problème architectural, pas une contrainte Rediacc. La solution est de déplacer les sidecars et les agents de surveillance dans un repository séparé avec sa propre frontière d'isolation, ou de réduire le nombre de processus fonctionnant indépendamment dans l'application elle-même.

---

## Repositories par machine

Il n'y a pas de limite fixe imposée par Rediacc. La limite pratique dépend des ressources de votre machine :

| Ressource | Impact |
|-----------|--------|
| Espace disque | Chaque repository est une image disque chiffrée. Une machine avec 1 To de stockage utilisable peut contenir de nombreux repositories, mais la taille totale de toutes les images doit tenir dans le pool du datastore. |
| RAM | Chaque repository en cours d'exécution démarre son propre Docker daemon et ses conteneurs. L'utilisation de la mémoire dépend de vos charges de travail. |
| CPU | Les opérations parallèles sur les repositories (démarrage, backup, fork) ajoutent une charge CPU temporaire. |

**Les déploiements typiques** exécutent 10 à 50 repositories par machine sans problème. Les machines avec 32 Go+ de RAM et 500 Go+ de stockage exécutent régulièrement 100+ repositories.

### Limite d'ID réseau à l'échelle du système

Chaque repository se voit attribuer un **ID réseau** unique, un nombre utilisé pour calculer sa plage d'adresses IP privées. Ce pool est partagé entre toutes les machines et repositories gérés par la même configuration Rediacc.

| Limite | Valeur |
|--------|--------|
| IDs réseau disponibles au total | ~261 944 |
| Portée | Par configuration (partagé entre toutes les machines d'une configuration) |

Lorsqu'un repository est supprimé, son ID réseau est libéré et devient disponible pour réutilisation. Rediacc attribue les identifiants de manière séquentielle et ne recherche les espaces libérés que lorsque le compteur progressif approche du plafond. En pratique, vous n'atteindrez jamais cette limite. Nous ne l'avons jamais observé. Épuiser le pool nécessiterait de créer et gérer des centaines de milliers de repositories sous une seule configuration.

---

## Forks

Il n'y a pas de limite sur le nombre de forks actifs d'un repository. Chaque fork est un clone complet en copie sur écriture avec son propre stockage chiffré, ses propres adresses réseau et son propre Docker daemon. Les forks consomment de l'espace disque proportionnel aux données écrites après la création (pas la taille complète du repository parent).

---

## Ports externes

### Ports toujours actifs

Les ports ne sont ouverts qu'une fois que vous configurez une IP publique avec `rdc config infra set --public-ipv4`. Jusque-là, aucun port n'est ouvert sur la machine. Une fois configuré :

| Port | Protocole | Fonction |
|------|-----------|----------|
| 80 | TCP | HTTP : géré par Traefik ; renvoie 404 pour les domaines non configurés, n'est transmis à aucun service |
| 443 | TCP | HTTPS : identique à ci-dessus ; les requêtes sans route correspondante sont rejetées au niveau du proxy |
| 10000–10010 | TCP | Plage dynamique pour le transfert TCP géré par Rediacc |

HTTP/HTTPS diffèrent des ports TCP bruts : même si 80 et 443 sont ouverts, chaque requête est validée par le proxy inverse par rapport à une table de routage explicite. Sans un service configuré et un domaine correspondant, aucun code applicatif n'est atteint et aucune donnée n'est exposée.

### Transfert TCP/UDP optionnel

Tous les autres ports (bases de données, caches, brokers de messages, DNS, messagerie) sont **fermés par défaut** et doivent être ouverts explicitement. Cela maintient la surface d'attaque de la machine au minimum.

Pour exposer un port d'un service spécifique :

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Pour ouvrir un port au niveau de la machine (disponible pour tous les services) :

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> N'exposez jamais les ports de bases de données ou de caches à l'extérieur, sauf si vous avez un besoin spécifique. Utilisez les routes automatiques HTTPS pour les services web et gardez les services de stockage internes.

---

## Datastore

Le datastore est un pool de taille fixe créé lors de la première configuration d'une machine. Sa taille ne croît pas automatiquement.

- **Taille minimale recommandée** : 50 Go
- **Taille maximale** : Limitée par votre disque. Un seul pool peut occuper un disque entier.
- **Redimensionnement** : Utilisez `rdc datastore resize` pour modifier la taille du pool (tous les repositories doivent être démontés au préalable).
- **Système de fichiers** : Rediacc utilise BTRFS en interne pour les snapshots en copie sur écriture et le forking efficace. Nécessite une machine avec **Linux kernel 6.1 ou ultérieur** pour une stabilité complète en production.

Chaque repository a une taille maximale définie à la création (par défaut : 10 Go). Utilisez `rdc repo resize` pour la modifier manuellement, ou définissez une [politique de taille automatique](/fr/docs/repositories#politique-de-taille-automatique) pour que la machine le fasse en ligne quand il se remplit (borné par un plafond explicite par repository et une réserve d'espace libre dans le pool). La croissance automatique s'applique uniquement aux repositories individuels ; le pool lui-même n'est jamais agrandi automatiquement.

Les images de repository sont éparses : un repository n'occupe dans le pool que ce qu'il a réellement écrit, et l'espace libéré par des suppressions revient au pool via [`repo trim`](/fr/docs/repositories#récupérer-de-lespace-trim) ou un trim automatique planifié. Les quotas peuvent donc dépasser la taille du pool, le [rapport de santé du stockage](/fr/docs/monitoring#santé-du-stockage) indiquant le niveau de remplissage réel.

---

## Routes HTTP

Chaque service avec le label `rediacc.service_port` obtient automatiquement une route HTTPS. Il n'y a pas de limite sur le nombre de services avec des routes, sous réserve du maximum de 61 services par repository.

Les certificats TLS génériques sont provisionnés par repository lors du premier déploiement via Let's Encrypt (challenge Cloudflare DNS-01). Let's Encrypt plafonne l'émission à **50 certificats par domaine enregistré par semaine**. Comme Rediacc utilise un certificat générique par repository (pas par service), un déploiement qui crée 50+ nouveaux repositories en une seule semaine atteindra ce plafond.

Les forks réutilisent le certificat générique existant du repository parent et ne consomment aucun quota de certificats.

---

## Checkpoint / Restore (CRIU)

La migration à chaud via CRIU a les contraintes suivantes :

- **Opt-in** : Seuls les conteneurs avec le label `rediacc.checkpoint=true` sont inclus dans le checkpoint. Les bases de données et les services sans état sont exclus par défaut et démarrent à neuf lors de la restauration.
- **Exigence de kernel** : Linux 6.1+ sur la machine source et la machine de destination.
- **Mode réseau** : CRIU nécessite le mode réseau host. Les conteneurs utilisant des configurations réseau personnalisées ne peuvent pas être inclus dans le checkpoint.
- **Mémoire** : La taille des données de checkpoint correspond à la mémoire résidente du processus. Les grands ensembles de données en mémoire (par exemple, une application Node.js mettant en cache 4 Go de données) produisent des fichiers de checkpoint de 4 Go.
- **Connexions TCP** : Les applications doivent tolérer la perte de connexions lors de la restauration. Les connexions TCP actives **ne sont pas** préservées, le processus restauré voit les sockets comme fermés et doit se reconnecter. Cela s'applique aux restaurations sur la même machine et inter-machines.
- **Le fork à chaud sur la même machine redirige les adresses du parent** : `rdc repo fork --parent X --tag Y --checkpoint` suivi de `rdc repo up` fonctionne pendant que le parent continue de tourner. Les processus restaurés portent les adresses loopback du parent au moment du checkpoint ; le système les redirige donc de manière transparente vers les adresses propres du fork (même service, copie des données du fork). La première utilisation d'une connexion TCP restaurée échoue toujours et l'application doit se reconnecter, voir le point TCP ci-dessus.

---

## Backups

| Limite | Valeur |
|--------|--------|
| Destinations de backup par repository | Illimitées |
| Jobs de backup simultanés | 1 par repository (les jobs sont mis en file d'attente s'ils sont déclenchés simultanément) |
| Fréquence de backup | Aucun intervalle minimum imposé ; limité par la bande passante de votre stockage. Utilisez `rdc config backup-strategy set --name <name> --bwlimit "6M"` pour limiter la vitesse d'envoi (syntaxe rclone `--bwlimit` : simple `6M`, directionnelle `6M:off`, ou tableau horaire `08:00,3M;22:00,10M`) |
| Rétention | Contrôlée par votre fournisseur de stockage (S3, Cloudflare R2, etc.). Rediacc n'impose pas de politiques de rétention. |
| Backup inter-machines | Pris en charge ; la machine de destination doit disposer d'un espace datastore suffisant |

---

## CLI & API

| Limite | Valeur |
|--------|--------|
| Commandes `rdc` simultanées contre la même machine | Illimitées (chaque commande ouvre sa propre connexion SSH) |
| Concurrence par défaut au démarrage des repositories en parallèle | 3 (ajustable avec `--concurrency`) |
| Délai d'attente de connexion SSH | 30 secondes pour la connexion initiale |
| Durée de session `rdc` | Aucun délai d'attente ; les opérations longues maintiennent la connexion active |

---

## Versions de système d'exploitation prises en charge

Les machines distantes doivent exécuter l'une des options suivantes pour répondre aux exigences de kernel, système de fichiers et isolation réseau de Rediacc. Cette liste est l'ensemble canonique testé en CI (matrice Bridge Workers) et doit rester synchronisée avec [Prérequis](/en/docs/requirements) :

| SE | Version minimale | Kernel par défaut | Notes |
|----|------------------|-------------------|-------|
| Ubuntu | 24.04 LTS *(recommandé)* | 6.8 | AppArmor par défaut. |
| Debian | 13 (Trixie) ; 12 Bookworm fonctionne aussi | 6.12 (6.1 sur Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing par défaut. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor par défaut. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK conserve btrfs ; SELinux enforcing par défaut. |

**Kernel minimum requis : 6.1.** Les machines avec des kernels plus anciens sont rejetées lors de la configuration avec un message d'erreur clair.

> **Pourquoi le kernel 6.1 ?** Rediacc utilise BTRFS pour le stockage chiffré des repositories et le forking en copie sur écriture. Linux 6.1 a introduit des améliorations critiques de BTRFS qui réduisent considérablement les temps de montage pour les grands datastores, améliorent les performances de suppression des snapshots et corrigent des problèmes d'intégrité des données présents dans les kernels antérieurs. Le kernel 6.1 est également nécessaire pour les hooks d'isolation réseau au niveau du kernel qui appliquent l'isolation entre repositories, en réécrivant de manière transparente les appels `bind()` et en bloquant les connexions entre repositories.

> **Pourquoi pas Rocky Linux 10 / kernel stock de RHEL 10 ?** Le kernel stock de RHEL 10 est livré sans le module `btrfs` (`modprobe btrfs` échoue avec "Module btrfs not found"). Le backend de stockage chiffré de Rediacc ne peut pas fonctionner sans btrfs. **Oracle Linux 10 est la seule cible compatible RHEL sur la liste prise en charge** car il utilise par défaut l'Unbreakable Enterprise Kernel (UEK), qui conserve btrfs. Voir [Prérequis : Pourquoi UEK ?](/en/docs/requirements) pour l'explication complète.

### Matrice des fonctionnalités du kernel

Lisez cette matrice d'un coup d'oeil pour voir ce que chaque OS testé en CI fournit par défaut. Les cinq satisfont toutes les exigences, c'est donc une référence pour les opérateurs, pas un critère de sélection.

| SE | Module btrfs | cgroups v2 | Landlock (ABI >= 1) | Hooks eBPF cgroup |
|----|--------------|------------|---------------------|-------------------|
| Ubuntu 24.04 | intégré | unified hierarchy | oui (5.13+) | oui |
| Debian 13 | intégré | unified hierarchy | oui | oui |
| Fedora 43 | intégré | unified hierarchy | oui | oui |
| openSUSE Leap 16.0 | intégré | unified hierarchy | oui | oui |
| Oracle Linux 10 (UEK) | intégré (via UEK) | unified hierarchy | oui | oui |
