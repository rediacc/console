---
title: Supervision
description: >-
  Supervisez la santé des machines, les conteneurs, les services, les dépôts et
  exécutez des diagnostics.
category: Guides
order: 9
language: fr
sourceHash: "d3b8ff142fe2df34"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Supervision

Rediacc fournit des commandes de supervision intégrées pour inspecter la santé des machines, les conteneurs en cours d'exécution, les services, le statut des dépôts et les diagnostics système.

## Santé de la machine

Obtenez un rapport de santé détaillé pour une machine :

```bash
rdc machine health --name server-1
```

Ce rapport inclut :
- **Système** : temps de fonctionnement, utilisation du disque, utilisation du datastore
- **Conteneurs** : nombre en cours d'exécution, sains, défaillants
- **Stockage** : santé SMART
- **Problèmes** : problèmes identifiés

Utilisez `--output json` pour une sortie lisible par les machines.

## Lister les conteneurs

Affichez tous les conteneurs en cours d'exécution sur tous les dépôts d'une machine :

```bash
rdc machine containers --name server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du conteneur |
| Status | Temps de fonctionnement ou raison de l'arrêt |
| State | En cours d'exécution, arrêté, etc. |
| Health | Sain, défaillant, aucun |
| CPU | Pourcentage d'utilisation du processeur |
| Memory | Utilisation de la mémoire / limite |
| Repository | Dépôt propriétaire du conteneur |

Options :
- `--health-check`, Effectuer des vérifications de santé actives sur les conteneurs
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut les détails complets des conteneurs (`labels`, `port_mappings`, `image`, `id`) ainsi que `repository` (nom résolu), `repository_guid` (GUID d'origine), `domain` et `autoRoute`.

## Lister les services

Affichez les services systemd liés à Rediacc sur une machine :

```bash
rdc machine services --name server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du service |
| State | Actif, inactif, en échec |
| Sub-state | En cours d'exécution, arrêté, etc. |
| Restarts | Nombre de redémarrages |
| Memory | Utilisation de la mémoire du service |
| Repository | Dépôt associé |

Options :
- `--stability-check`, Signaler les services instables (en échec, >3 redémarrages, redémarrage automatique)
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut les détails complets des services avec `repository` (nom résolu) et `repository_guid` (GUID d'origine).

## Lister les dépôts

Affichez les dépôts sur une machine avec des statistiques détaillées :

```bash
rdc machine repos --name server-1
```

| Colonne | Description |
|---------|-------------|
| Name | Nom du dépôt |
| Size | Taille de l'image disque |
| Mount | Monté ou démonté |
| Docker | Démon Docker en cours d'exécution ou arrêté |
| Containers | Nombre de conteneurs |
| Disk Usage | Utilisation réelle du disque au sein du dépôt |
| Modified | Date de dernière modification |

Options :
- `--search <text>`, Filtrer par nom ou chemin de montage
- `--output json`, Sortie JSON lisible par les machines

La sortie JSON inclut `name` (résolu) et `guid` (GUID d'origine), et imbrique pour chaque dépôt les tableaux `containers` (avec `domain`, `autoRoute`, `repository`/`repository_guid`) et `services`.

## Santé du stockage

Inspectez la fragmentation BTRFS et le partage de reflinks sur tous les dépôts d'une machine :

```bash
rdc machine query --name server-1 --storage-health
```

| Colonne | Description |
|---------|-------------|
| Size | Taille du fichier image LUKS (ce à quoi ressemble le dépôt) |
| Unique | Données uniques réelles appartenant uniquement à ce dépôt |
| Shared | Blocs de données réutilisés entre dépôts via les reflinks BTRFS (copies gratuites) |
| Divergence | Pourcentage de l'image propre à ce dépôt plutôt que partagé (plus élevé = davantage récupérable en cas de suppression) |
| Extents | Nombre d'extents de fichiers dans l'image copy-on-write (plus élevé = plus fragmenté) |
| Frag | Niveau de fragmentation : faible, modéré ou élevé (informatif uniquement) |

Le résumé affiche les économies totales réalisées grâce aux reflinks BTRFS :

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Taille virtuelle** est la somme de toutes les tailles d'image de dépôt. C'est ce à quoi ressemblent les dépôts, mais cela compte double les blocs partagés via les reflinks.
- **Données uniques** correspond au stockage réellement consommé par les données d'un dépôt n'existant que dans un seul dépôt. C'est ce qui serait libéré en supprimant un dépôt.
- **Partagé** désigne les données réutilisées entre dépôts via les reflinks BTRFS. La bifurcation d'un dépôt crée des copies reflink qui partagent des blocs jusqu'à ce que l'un ou l'autre côté écrive de nouvelles données, moment auquel les blocs divergent.
- **Efficacité** est le pourcentage de données réutilisées via les reflinks. Plus élevé est mieux. Une machine avec de nombreuses bifurcations depuis le même dépôt parent affichera une efficacité proche de 100%.

La colonne Frag est informative. Elle compte les extents du fichier image copy-on-write, pas les fichiers que votre application lit à l'intérieur, donc elle affiche des valeurs élevées sous des charges d'écriture aléatoires normales (bases de données, couches de conteneurs) et ne prédit pas les performances de lecture sur un stockage SSD. Rediacc ne propose délibérément aucune commande de défragmentation : `btrfs filesystem defragment` dé-partage les forks et snapshots avec reflinks, ce qui sur un pool presque plein peut faire exploser l'utilisation de l'espace alors que les benchmarks ne montrent aucun gain de lecture mesurable. Pour les mesures complètes et le raisonnement, voir [Votre chiffre de fragmentation semble terrifiant. J'ai mesuré ce qu'il coûte.](/fr/blog/i-benchmarked-btrfs-fragmentation).

Le scan s'exécute en parallèle et prend 5 à 15 secondes selon le nombre et la taille des dépôts. Quand `--storage-health` n'est pas spécifié, une indication d'une ligne apparaît après la sortie de la requête comme rappel.

## Scrub BTRFS

Rediacc planifie automatiquement un scrub BTRFS hebdomadaire sur chaque machine. Le scrub lit chaque bloc de données du datastore, vérifie les sommes de contrôle et signale toute corruption. Cela détecte la corruption silencieuse des données (bitrot) avant qu'elle ne se propage aux sauvegardes et aux bifurcations.

Le scrub s'exécute chaque dimanche à 02h00 heure locale (fuseau horaire de la machine) avec un délai aléatoire pouvant aller jusqu'à 1 heure. Il s'exécute avec la priorité d'E/S la plus basse (`ionice idle`, `nice 19`) afin de ne pas interférer avec les services en cours. Sur les machines avec SSD, comptez environ 8 minutes par 100 Go de datastore.

Le minuteur de scrub est installé automatiquement au premier démarrage du daemon après une mise à niveau de renet. Lorsque la politique de scrub change dans une future version de renet, elle se met à jour au prochain démarrage du daemon sans intervention de l'utilisateur.

### Statut du scrub

Le résultat du dernier scrub est sauvegardé hors du volume BTRFS (dans `/var/lib/rediacc/scrub-last-result.json`) afin qu'il reste lisible même si le volume rencontre des problèmes. La sortie de `rdc machine query --system` inclut un champ `scrub_status` :

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Statut | Signification |
|--------|---------------|
| `ok` | Le dernier scrub s'est terminé sans erreur |
| `never_run` | Le scrub n'a pas encore été exécuté (le minuteur vient d'être installé) |
| `overdue` | Le dernier scrub date de plus de 14 jours |
| `errors_found` | Le scrub a trouvé des erreurs de somme de contrôle (vérifiez les compteurs `total_errors` et `uncorrectable`) |
| `failed` | Le processus de scrub s'est terminé avec un code non nul |

Si `uncorrectable` est supérieur à zéro, les blocs affectés ne peuvent pas être réparés automatiquement (BTRFS sur un seul disque n'a pas de copie redondante). Restaurez le dépôt affecté depuis la sauvegarde la plus récente.

### Scrub manuel

Pour lancer un scrub immédiatement (par exemple après une coupure de courant ou une migration de disque) :

```bash
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Le résultat est sauvegardé dans le même fichier JSON et est immédiatement visible dans le prochain `rdc machine query --system`.

## Statut du coffre

Obtenez un aperçu complet d'une machine incluant les informations de déploiement :

```bash
rdc machine vault-status --name server-1
```

Ceci fournit :
- Nom d'hôte et temps de fonctionnement
- Utilisation de la mémoire, du disque et du datastore
- Nombre total de dépôts, nombre de montés, nombre de démons Docker actifs
- Informations détaillées par dépôt

Utilisez `--output json` pour une sortie lisible par les machines.

## Tester la connexion

> **Adaptateur cloud uniquement.** Avec l'adaptateur local, utilisez `rdc term connect -m server-1 -c "hostname"` pour vérifier la connectivité.

Vérifiez la connectivité SSH vers une machine :

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Ce rapport inclut :
- Statut de la connexion (succès/échec)
- Méthode d'authentification utilisée
- Configuration de la clé SSH
- Statut de déploiement de la clé publique
- Entrée des clés d'hôte connues

Options :
- `--port <number>`, Port SSH (par défaut : 22)
- `--save -m server-1`, Enregistrer la clé d'hôte vérifiée dans la configuration de la machine

## Diagnostics (doctor)

Exécutez une vérification diagnostique de votre environnement Rediacc :

```bash
rdc doctor
```

| Catégorie | Vérifications |
|-----------|---------------|
| **Environnement** | Version de Node.js, version du CLI, mode SEA, installation de Go, disponibilité de Docker |
| **Renet** | Emplacement du binaire, version, CRIU, rsync, ressources SEA embarquées |
| **Paramètres** | Profil actif, adaptateur, machines, clé SSH |
| **Virtualisation** | Vérifie si votre système peut exécuter des machines virtuelles locales (`rdc ops`) |

Chaque vérification indique **OK**, **Avertissement** ou **Erreur**. Utilisez cette commande comme première étape lors du dépannage de tout problème.

Codes de sortie : `0` = tout réussi, `1` = avertissements, `2` = erreurs.
