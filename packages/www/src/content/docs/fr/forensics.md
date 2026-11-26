---
title: "Investigation numérique : des preuves issues d'un dépôt compromis"
description: "Enregistrements des flux réseau et des ouvertures de fichiers sensibles par dépôt, au niveau choisi par le client, expédiés toutes les 30 secondes sous forme de lots signés et chaînés. Couvre les trois niveaux de capture, le déclencheur de pic, les quotas des offres, la détection hors ligne et côté serveur, et ce que le serveur peut lire."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: fr
sourceHash: "c349f479d246dee4"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Investigation numérique

L'investigation numérique répond à deux questions lorsqu'un logiciel exécuté dans un dépôt est compromis : quand des données ont été prises, et lesquelles. Rediacc ne peut pas combler une faille dans un logiciel tiers, la fonction enregistre donc des preuves qui survivent à la compromission. Les enregistrements sont écrits par un collecteur exécuté en root sur la machine, hors du bac à sable du dépôt, puis envoyés vers un bucket que les administrateurs du client ne peuvent pas atteindre.

Les enregistrements montrent le volume, la destination et l'horaire. Les enregistrements de flux prouvent le volume et la destination, pas le contenu. Le [workflow d'incident](/fr/docs/incident-response) les lit, et les [rapports d'incident](/fr/docs/incident-reports) les transforment en documents signés destinés à une autorité de contrôle.

## Ce qui est enregistré

La capture se fait par dépôt. Les dépôts utilisent le réseau de l'hôte, le trafic est donc attribué par cgroup (la slice propre au dépôt), jamais par adresse IP.

| Enregistrement | Contenu |
|---|---|
| Flux réseau | Heure, processus, adresse et port de destination, protocole, octets sortants et entrants, nom DNS s'il est connu, ainsi que l'ASN et le pays de la destination s'ils sont connus |
| Ouverture de fichier | Heure, processus et chemin, pour un chemin correspondant à la liste des chemins sensibles |
| Heartbeat | Un marqueur signé dans chaque lot, afin qu'un collecteur arrêté apparaisse comme un trou plutôt que comme du silence |

La liste sensible par défaut couvre les fichiers `.env`, les fichiers de clés et de certificats (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), les bases de mots de passe (`*.kdbx`), les dumps et fichiers de bases de données (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) et les répertoires de données de bases comme `pgdata`. Un dépôt peut étendre la liste ou la remplacer par ses propres motifs.

Le contenu des paquets et celui des fichiers ne sont jamais enregistrés.

## Niveaux de capture

Chaque dépôt a un seul niveau, le plus bas par défaut. Un niveau supérieur enregistre tout ce qu'enregistre un niveau inférieur.

| Niveau | Enregistré |
|---|---|
| `basic` | Un résumé toutes les 5 minutes par destination, port et protocole, avec les octets entrants et sortants |
| `standard` | Un enregistrement de flux par minute, avec le processus et le nom DNS |
| `full` | Standard, plus les ouvertures de fichiers sur les chemins sensibles |

Le niveau se règle par dépôt :

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

Le collecteur plafonne le niveau à ce que l'offre inclut. Lorsqu'une offre n'a pas de quota d'investigation, le dépôt n'enregistre rien.

### Le déclencheur de pic

Chaque niveau arme un déclencheur. Quand les octets sortants d'un dépôt en une minute dépassent dix fois sa propre moyenne mobile (et 50 MiB par minute), une fois le dépôt observé pendant 24 heures, il passe en Full pendant 24 heures. Une minute déclenchante n'alimente pas la moyenne, si bien qu'une seule exfiltration ne peut pas relever la référence censée détecter la suivante.

## Offres et quotas

L'investigation numérique est réservée aux offres payantes et n'enregistre que tant que l'offre est payée. Une montée en gamme démarre sans historique.

| Offre | Quota d'investigation |
|---|---|
| Free, Community | 0 (rien n'est enregistré) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, ou un quota personnalisé fixé par les administrateurs de Rediacc |

Le quota représente un quart du quota de sauvegarde de l'offre et est comptabilisé séparément des sauvegardes. Un quota supplémentaire s'obtient uniquement en changeant d'offre.

Quand le quota est plein, les enregistrements les plus anciens sont évincés en premier (FIFO). Les 7 derniers jours sont verrouillés et jamais évincés, car le bucket les verrouille pendant 7 jours. Si les seuls octets verrouillés dépassaient le quota, les nouveaux lots sont refusés. Si l'ingestion prévue sur 7 jours ne tenait pas, le niveau est plafonné à Basic. Les propriétaires et administrateurs reçoivent un avis à 80 pour cent du quota, quand le plafond tombe à Basic et quand un lot est refusé.

Les enregistrements compris dans un incident déclaré sont exclus de l'éviction jusqu'à 30 jours après la clôture de l'incident. Voir la [réponse aux incidents](/fr/docs/incident-response).

## Expédition et intégrité

Le collecteur coupe un lot toutes les 30 secondes. Chaque lot est signé avec la clé de spool de la machine et porte le hash du lot précédent, de sorte qu'un lot supprimé ou modifié rompt la chaîne. Les lots sont envoyés via des URL présignées en création seule, émises à partir du blob de licence de la machine : la machine peut ajouter des enregistrements, mais pas les écraser ni les supprimer. Quand la connexion est perdue, les lots attendent dans un spool local signé et partent au retour de la connexion.

Le compactage nocturne fusionne les lots en un fichier journalier par dépôt et un fichier d'en-têtes par machine, où chaque en-tête signé est listé et chaque trou signalé. Les fichiers journaliers d'audit du compte sont chaînés de la même façon, par organisation et par jour.

`rdc forensics verify` et le bouton Verify evidence de la page d'investigation recalculent ces chaînes. Voir la [réponse aux incidents](/fr/docs/incident-response).

## Détection

La détection d'anomalies s'exécute deux fois. Un détecteur statistique sur la machine réagit immédiatement et passe le dépôt en Full. Le serveur exécute ses propres détecteurs à l'ingestion, la détection survit donc à un hôte compromis. Aucune IA ne tourne sur chaque enregistrement de journal.

Les détecteurs sont superposés et chaque dépôt apprend de son propre trafic :

| Détecteur | Recherche |
|---|---|
| Références par heure de la semaine | Octets, connexions, destinations distinctes, nouveaux noms DNS et nouveaux processus hors du rythme habituel du dépôt pour cette heure de la semaine |
| Half-Space Trees | Un flux différent de ceux vus auparavant |
| ECOD et HBOS | Des lots de flux qui obtiennent un score aberrant, avec les caractéristiques qui ont fait ce score |
| Première occurrence | Un processus qui ouvre un fichier sensible qu'il n'avait jamais ouvert |

Chaque constat porte les raisons par caractéristique qui l'ont produit, et l'explication est un modèle construit à partir de ces raisons. Hors ligne, il n'y a pas de modèle de langage. Un constat devient un avis du compte et un e-mail aux propriétaires, aux administrateurs et au contact sécurité. Quand la machine est hors ligne, elle agit aussitôt en local (capture Full et une entrée dans son spool signé) et délivre l'alerte au retour de la connexion, en conservant l'heure de détection d'origine.

### Bundles de modèles

Les paramètres des détecteurs sont publiés sous forme de bundles signés sur `data.rediacc.com/models/` : des fichiers adressés par contenu, un manifeste signé avec une clé de modèle Ed25519 hors ligne intégrée à renet, une version minimale de renet et une version qui ne fait qu'augmenter, ce qui fait refuser un retour en arrière. Un bundle est vérifié avant son installation, et le précédent peut être rétabli.

```bash
renet models status
renet models update
renet models rollback
```

Les installations isolées du réseau reçoivent le même bundle signé dans `rdc server bundle`, sauf si `--no-models` est passé.

## Ce que le serveur peut lire

Le serveur de comptes lit les enregistrements, car la chronologie, la vérification et les détecteurs serveur en ont besoin : destinations, ports, noms de processus, noms DNS, compteurs d'octets et chemins de fichiers sensibles. Il ne reçoit ni le contenu des paquets ni celui des fichiers.

Une adresse client entrante est stockée tronquée dans les enregistrements (à /24 en IPv4 et /48 en IPv6), et l'adresse complète figure dans une section séparée supprimée au bout de 30 jours. Le hash de la section supprimée reste dans l'en-tête signé, la chaîne se vérifie donc toujours et le vérificateur signale l'adresse comme masquée. Les destinations sortantes restent entières, car elles sont la preuve.

Les clients ouvrent les enregistrements au moyen d'une investigation, qui exige une offre payante, le rôle de propriétaire ou d'administrateur et une réauthentification récente, et chaque consultation est auditée. Le support Rediacc ne voit les données d'investigation que sous une autorisation limitée dans le temps, émise par le client. Les conditions de traitement figurent dans l'[accord de traitement des données](/fr/data-processing-agreement).
