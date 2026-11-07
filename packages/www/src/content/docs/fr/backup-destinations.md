---
title: "Destinations de sauvegarde"
description: "Envoyez chaque stratégie de sauvegarde vers plus d'un store, restaurez depuis le store qui détient le meilleur instantané et lisez une ligne d'état par destination."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: fr
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Destinations de sauvegarde

Une stratégie de sauvegarde peut écrire dans plus d'un store. Chaque destination est un point de récupération distinct : elle a son propre instantané, son propre commit et sa propre ligne d'état, si bien qu'un store en échec n'abîme pas les autres.

Tous les stores appartiennent à un seul compte. Une seule config, une seule licence et une seule facture les couvrent. Une machine connectée à deux comptes reste refusée, car plusieurs destinations signifient plusieurs stores au sein d'un même compte.

## Stores

Un store est un bucket dans lequel le serveur de comptes écrit pour le compte de la machine. Chaque abonnement en a un dès le premier jour, nommé `home` : le store hébergé que les commandes de sauvegarde ont toujours utilisé. Une destination qui ne nomme aucun store écrit dans `home`.

Deux types peuvent être enregistrés en plus.

| Type | Ce que c'est | Ce que demande l'enregistrement |
|------|--------------|---------------------------------|
| `hosted-r2` | Une seconde région hébergée, choisie parmi celles que propose le déploiement | Un id et la région. Aucun identifiant |
| `customer-s3` | Un bucket exploité par le client, sur S3, RustFS ou tout service compatible S3 | Un id, le point de terminaison HTTPS, le bucket, la région de signature (`us-east-1` par défaut), un point de terminaison public facultatif et une paire de clés d'accès |

Une machine ne détient jamais les clés d'un bucket client. Les clés restent scellées sur le serveur de comptes, et la machine reçoit des URL présignées de courte durée pour le seul store que nomme sa session.

### Enregistrer un store

L'enregistrement est un appel à l'API du compte, pas une commande `rdc`. `POST /backups/stores` enregistre un store, `GET /backups/stores` liste ceux qui sont enregistrés et `DELETE /backups/stores/<id>` en retire un. Enregistrer, renouveler les clés et retirer demandent un jeton d'API avec le scope `backup:manage`, créé par un propriétaire ou un administrateur actuel de l'organisation, et chaque opération est auditée. La liste demande `backup:read`.

Le serveur vérifie un store avant de l'accepter.

- **Sonde de conformité.** Le serveur exécute les mêmes contrôles que ceux qu'un store hébergé réussit. Un store qui n'impose pas les sommes de contrôle est refusé à l'enregistrement, au lieu d'être découvert à la première sauvegarde.
- **Sonde de suppression.** La sonde tente aussi une suppression. Quand le store la refuse, il est enregistré avec le nettoyage désactivé (voir plus bas).
- **Règles de point de terminaison.** HTTPS uniquement, port 443, et aucun point de terminaison sur un réseau interne.
- **Limite de stores.** Le nombre de stores par abonnement dépend de l'offre, `home` compris, les stores retirés n'étant pas comptés.

| Offre | Stores |
|-------|--------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Enregistrer un id qui existe déjà ne renouvelle que ses identifiants, et la sonde repasse. Un store dont les identifiants cessent de fonctionner est marqué suspendu dès la première autorisation refusée. `GET /backups/stores` affiche le point de terminaison, le bucket et les derniers caractères de l'id de clé, jamais un secret.

Un store ne peut pas être retiré tant qu'une destination activée le nomme encore, et `home` ne peut pas être retiré.

## Désigner le store d'une destination

Une destination désigne son store avec `--target`, utilisé avec `--destination` :

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Option | Description |
|--------|-------------|
| `--destination <name>` | La destination à créer ou à modifier |
| `--target <storeId>` | Id du store enregistré dans lequel la destination écrit (`home` par défaut). Nécessite `--destination` |

Deux destinations activées d'une même stratégie ne peuvent pas nommer le même store, et un store non enregistré est refusé avec la liste des ids enregistrés.

Chaque exécution planifiée prend un instantané par destination activée, dans l'ordre où les destinations ont été déclarées, chacune avec son propre plafond de bande passante. Chaque instantané est un reflink copy-on-write neuf, donc chacun est un point dans le temps cohérent en soi. Une destination en échec n'empêche pas la suivante de s'exécuter. L'unité se termine tout de même avec un code non nul quand une destination a échoué, de sorte que systemd et la vérification des exécutions manquées voient l'échec.

## Restaurer depuis un store

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` et `rdc backup download --store` acceptent `--from <storeId>` :

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Sans `--from`, la CLI demande au serveur de comptes quels stores détiennent la lignée du dépôt, classés avec en premier le store dont l'instantané le plus récent a passé la dernière vérification, puis les essaie dans cet ordre. Un store sans instantané est ignoré. Si le classement est illisible, la restauration utilise `home` et le signale.

Sans `--from`, `backup restore`, `restore --path`, `browse --at` et `download --store` partent du premier store de ce classement et passent au suivant quand la défaillance vient du store : une erreur du serveur, une autorisation ou une session refusée, ou un point de terminaison qui ne répond pas. Chacun indique quel store l'a servi. Aucun ne bascule pour un défaut de l'instantané lui-même. Un instantané manquant, expiré ou corrompu a le même aspect dans tous les stores, donc l'erreur est affichée. Une commande avec `--from` lit uniquement ce store et ne bascule jamais.

Un id d'instantané donné sans `--from` est recherché dans tous les stores de la lignée.

## État par destination

`rdc backup status` affiche une ligne par destination à côté du tableau de planification :

| Colonne | Signification |
|---------|---------------|
| Store | L'id du store dans lequel la destination écrit |
| Last run | La fin de la dernière exécution pour ce store |
| Result | Le résultat de cette exécution |
| Newest snapshot | L'instantané le plus récent que détient le store |
| Verify | Le résultat de la dernière vérification du store |
| Clean-up | `enabled`, ou désactivé avec la raison |

Un store sur lequel le compte ne peut pas faire de rapport affiche `-` dans ses colonnes. La vérification des exécutions manquées se fait par store, donc un store qui ne reçoit plus de sauvegardes déclenche sa propre alarme pendant que les autres restent au vert.

## Ce qui compte dans le quota

Les stores hébergés, `home` et toute seconde région, sont mesurés en octets uniques stockés physiquement, et leurs octets comptent dans le même quota d'offre. `rdc backup usage` les affiche.

Les octets d'un bucket client ne sont pas stockés par Rediacc et ne comptent pas dans le quota. Les métadonnées que le compte conserve pour lui (lignes de manifeste, exécutions de vérification et objets d'index) sont mesurées comme celles d'un store hébergé.

## Stores avec nettoyage désactivé

Un store dont la suppression est refusée conserve tous ses objets. La rétention et le ramasse-miettes ne suppriment jamais rien dedans. Quand un instantané expire, le balayage le marque comme expiré sur le compte, cesse de le proposer à la restauration et laisse ses objets dans le bucket.

`rdc backup status` et le résumé de santé des sauvegardes signalent le store comme nettoyage désactivé. Le bucket continue de grossir jusqu'à ce que des identifiants de suppression soient ajoutés, en enregistrant à nouveau le même id avec des clés autorisées à supprimer.
