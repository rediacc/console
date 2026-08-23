---
title: Abonnement et licences
description: >-
  Comprendre comment account, rdc et renet gèrent les slots de machine, les
  licences de dépôt et les limites de plan.
category: Guides
tags:
  - account
subcategory: account
order: 7
language: fr
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
---

# Abonnement et licences

La gestion des licences Rediacc comporte trois parties mobiles :

- `account` signe les droits et suit l'utilisation
- `rdc` authentifie, demande les licences, les livre aux machines et les applique à l'exécution
- `renet` (l'environnement d'exécution sur la machine) valide les licences installées localement sans appeler le serveur de comptes

Cette page explique comment ces éléments s'articulent pour les déploiements locaux.

## Ce que fait la gestion des licences

La gestion des licences contrôle deux choses différentes :

- **La comptabilisation des accès machines** via les **licences flottantes**
- **L'autorisation d'exécution des dépôts** via les **licences de dépôt**

Ces deux éléments sont liés, mais ne constituent pas le même artefact.

## Comment fonctionne la gestion des licences

`account` est la source de vérité pour les plans, les remplacements contractuels, l'état des slots de machine et les émissions mensuelles de licences de dépôt.

`rdc` s'exécute sur votre station de travail. Il vous authentifie auprès du serveur de comptes, demande les licences nécessaires et les installe sur les machines distantes via SSH. Lorsque vous exécutez une commande de dépôt, `rdc` s'assure que les licences requises sont en place et les valide sur la machine à l'exécution.

Le flux normal ressemble à ceci :

1. Vous vous authentifiez avec `rdc subscription login`
2. Vous exécutez une commande de dépôt telle que `rdc repo create`, `rdc repo up` ou `rdc repo down`
3. Si la licence requise est manquante ou expirée, `rdc` la demande à `account`
4. `rdc` écrit la licence signée sur la machine
5. La licence est validée localement sur la machine et l'opération se poursuit

Consultez [rdc vs renet](/fr/docs/rdc-vs-renet) pour la répartition station de travail/serveur, et [Dépôts](/fr/docs/repositories) pour le cycle de vie du dépôt lui-même.

Pour l'automatisation et les agents IA, utilisez un token d'abonnement à portée limitée plutôt que la connexion par navigateur :

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Vous pouvez également injecter le token directement via l'environnement afin que le CLI puisse émettre et renouveler les licences de dépôt sans aucune étape de connexion interactive :

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slots de machine et licences de dépôt

### Slots de machine (côté serveur)

Le suivi des slots de machine est appliqué côté serveur. Lorsque le CLI émet une licence de dépôt, le serveur de comptes vérifie le quota de slots de machine de l'abonnement. Chaque plan en libre-service (Community, Professional, Business) inclut un slot de machine ; les déploiements multi-machines relèvent d'une configuration Enterprise dimensionnée avec nos partenaires. Un slot est conservé pendant 5 heures à partir de la dernière émission de licence de dépôt sur cette machine et se libère automatiquement après inactivité. Comme un slot n'est conservé que pendant que vous approvisionnez activement, un seul slot peut tout de même couvrir plusieurs machines au cours d'un mois.

Le plafond est lu dans votre fiche d'abonnement, et non dans une constante de plan figée dans le code : un nombre d'activations négocié est donc honoré dès qu'il est inscrit sur l'abonnement. Le niveau de plan ne fait que déterminer la valeur de départ.

L'émission et le renouvellement ne sont pas appliqués de la même façon, et la différence compte :

- **L'émission d'une nouvelle licence bute sur le plafond.** Si tous les slots sont pris, la requête échoue avec `MAX_MACHINES_REACHED` et rien n'est approvisionné.
- **Le renouvellement d'une licence existante ne bloque jamais.** Une machine qui se renouvelle alors que tous les slots sont pris continue de fonctionner, et son slot est enregistré comme dépassant la limite. Vous le voyez dans le portail sur la page Machines, dans `rdc subscription status` et dans le champ `overLimitCount` de l'API de statut de licence. L'indicateur disparaît de lui-même dès que la machine repasse sous la limite.

Le renouvellement est délibérément la voie la plus souple. Une machine qui renouvelle une licence qu'elle détient déjà n'ajoute pas de capacité, et la refuser arrêterait les sauvegardes sur une infrastructure déjà payée. Ce qui reste bloqué, c'est l'ajout de capacité.

Aucun fichier de licence de machine n'est stocké sur la machine. L'application des slots se fait au moment de l'émission sur le serveur.

### Licence de dépôt

Une licence de dépôt est une licence signée pour un dépôt sur une machine. C'est le seul fichier de licence stocké sur la machine, organisé par datastore et par clé de signature :

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Les dépôts sur le stockage par défaut d'une machine utilisent le premier chemin. Les dépôts dans un datastore nommé utilisent le second, où `{datastoreId}` est l'identité attribuée à ce datastore lors de sa création. C'est ce cloisonnement qui fait qu'un fork de datastore se comptabilise honnêtement : un datastore forké reçoit une identité toute neuve, donc ses dépôts démarrent sans aucune licence, remontent `missing` à leur première opération sous licence, et se voient émettre leurs propres licences. Un dépôt dont la licence nomme un autre datastore que celui où il se trouve échoue immédiatement en `identity_mismatch` plutôt que d'être réémis automatiquement, ce qui empêche de recopier un fichier de licence d'un endroit à l'autre.

`{keyId}` est une empreinte hexadécimale à 16 caractères (les 8 premiers octets du `SHA-256` de la clé publique Ed25519 du serveur signataire). Un dépôt géré par plus d'un univers de compte (par exemple production et bench se déployant sur la même machine) conserve un fichier par clé de signature dans son répertoire `{guid}`. Le build renet de la machine ne valide que le fichier que sa clé intégrée, ou un certificat de délégation qui en découle, peut vérifier ; les fichiers des autres univers restent inertes. Le changement d'univers n'invalide jamais les licences : la première opération dans un nouvel univers émet la licence de cet univers une seule fois (un résultat `missing` déclenche une émission automatique), et les deux coexistent ensuite.

Elle est utilisée pour :

- `rdc repo create`, `rdc repo fork` et `rdc repo commit`, validés avant l'approvisionnement (pré-émise sans preuves d'identité, puis réémise avec preuves d'identité après la création, car le dépôt n'existe pas encore au moment de la vérification)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` et `rdc repo promote`, **validation complète, expiration incluse**
- le transfert de sauvegarde, **validation complète, expiration incluse** : `rdc repo push`, `rdc repo pull`, `rdc repo migrate` et les sauvegardes planifiées
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` et le démarrage automatique du dépôt au redémarrage de la machine, validés avec **l'expiration et la fenêtre du certificat de délégation toutes deux ignorées**
- `rdc repo down`, `rdc repo delete` et les commandes en lecture seule comme la liste des dépôts n'ont besoin d'aucune licence

Les signatures, la liaison de clé, la liaison de machine, la liaison de dépôt et toutes les contraintes du certificat de délégation sont appliquées dans tous ces cas. Le dernier groupe ne relâche que les deux fenêtres temporelles, afin qu'une licence expirée ou un certificat périmé ne puisse jamais vous empêcher de faire tourner ou d'arrêter vos propres données.

Les licences de dépôt sont liées à la machine et au dépôt cible. Chaque licence contient l'ID de machine, le GUID du dépôt, l'ID d'abonnement, les limites de plan et l'expiration. Pour les dépôts chiffrés, Rediacc vérifie également l'identité LUKS du volume sous-jacent.

Plusieurs abonnements peuvent coexister sur la même machine. Chaque dépôt porte sa propre licence avec son propre contexte d'abonnement.

## Clusters

Le clustering se vend par l'intermédiaire de nos partenaires, dans le cadre d'un accord Enterprise. Ce n'est pas une option de plan en libre-service, et les points ci-dessous décrivent la façon dont il est comptabilisé, pas la façon de l'acheter.

**Un nœud est une machine.** Un cluster n'a pas d'identité de licence propre. Chaque nœud qui le compose est une machine ordinaire sur laquelle l'agent Renet est installé, et il est compté exactement comme une machine autonome.

**Il n'y a pas de mutualisation.** Un cluster de cinq nœuds ne puise pas dans un slot de cluster commun. Chaque nœud réclame son propre slot la première fois qu'un dépôt y est placé, et ce slot suit le même flottement de 5 heures que n'importe quel autre : il est conservé pendant 5 heures à partir de la dernière émission de licence de dépôt sur ce nœud, puis se libère de lui-même.

**Construire le cluster est gratuit. Ce sont les dépôts qui déclenchent le compteur.** Créer le cluster, y rattacher des nœuds, installer la couche de stockage distribué et monter le plan de contrôle Kubernetes ne coûtent aucun slot. Le décompte commence quand un dépôt arrive sur un nœud.

**Un fork de cluster recompte dépôt par dépôt.** Forker un cluster entier donne au datastore forké une nouvelle identité : chaque dépôt du fork obtient donc sa propre licence à la première sollicitation, sur le nœud où il tourne. La migration simple est le cas inverse : déplacer un dépôt d'une machine à l'autre emporte sa licence avec lui et continue de valider, car rien n'a changé dans son identité de stockage.

**Le renouvellement sur un cluster suit la règle souple ci-dessus.** Les nœuds renouvellent leurs propres licences sans intervention, si bien qu'un cluster qui a dépassé son nombre d'activations continue de fonctionner et signale ses nœuds hors limite plutôt que de faire échouer des sauvegardes en pleine nuit. Ajouter un nouveau nœud, en revanche, bute toujours sur le plafond.

Dimensionner un cluster est une discussion, pas une case à cocher. Les nombres d'activations pour les clusters sont convenus dans la commande, et votre partenaire les inscrit directement sur l'abonnement. Voir [Contact](/fr/contact) pour engager cette discussion.

## Limites par défaut

La taille du dépôt dépend du niveau de droits :

- Community : jusqu'à `10 GB`
- plans payants : limite du plan ou du contrat

Limites par défaut des plans payants :

| Plan | Licences flottantes | Taille du dépôt | Émissions mensuelles de licences de dépôt | Validité cert de délégation par défaut / max |
|------|---------------------|-----------------|-------------------------------------------|----------------------------------------------|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2,000+ | 60d / 120d |
| Business | 1 | 500 GB | 5,000+ | 90d / 180d |
| Enterprise | Sur mesure | 1 TB+ | 15,000+ | 120d / 365d |

Les limites spécifiques au contrat peuvent augmenter ou diminuer ces valeurs pour un client particulier. La validité des certificats de délégation est également plafonnée à `subscription.expiresAt + 3 day grace`, de sorte que les abonnements facturés mensuellement obtiennent naturellement des certificats alignés sur leur cycle de facturation. Voir [Chaîne de licences et délégation - Politique de validité](/fr/docs/license-chain) pour les règles complètes.

## Essai gratuit et repli sur Community

Les nouvelles inscriptions démarrent un essai gratuit de 14 jours sur Professional ou Business. Une carte bancaire est enregistrée à l'inscription, et le premier prélèvement n'intervient qu'à la fin de l'essai, donc annuler avant ne coûte rien. Un seul essai est disponible par client.

Community est le socle gratuit permanent. Ce n'est plus une option d'inscription directe pour les nouveaux comptes ; à la place, un compte bascule sur Community dès qu'un abonnement prend fin : annulation pendant l'essai, annulation ultérieure d'un plan payant, ou paiement en échec. Sur le repli Community, vous conservez une machine avec 10 Go par dépôt et 100 setups par mois. Les comptes créés avant le lancement du modèle basé sur l'essai conservent leur accès Community existant.

L'application des limites reste souple là où cela compte le plus : les dépôts en cours d'exécution continuent de fonctionner même après la fin d'un abonnement (`up`, `down`, `delete`, démarrage automatique). Au-delà, deux règles différentes s'appliquent, et c'est en les confondant que la grâce de 60 jours paraît incohérente :

- **Les opérations qui ont besoin du serveur de comptes** sont impossibles sans abonnement actif, parce que le serveur refuse de signer. Ce sont `create`, `fork` et tout rafraîchissement ou renouvellement de licence. Plus rien de nouveau n'est approvisionné une fois l'abonnement échu.
- **Les opérations qui n'ont besoin que d'une licence installée valide** continuent de fonctionner jusqu'à l'expiration définitive de cette licence, sans aucun serveur dans la boucle. Ce sont `resize` et `expand` sur les dépôts que vous avez déjà, ainsi que le transfert de sauvegarde (`push`, `pull`, sauvegardes planifiées). La licence principale d'un dépôt expire définitivement 60 jours après la date de fin de l'abonnement : c'est de là que vient la grâce de 60 jours. La licence d'un fork est bien plus courte, plafonnée à 7 jours, et c'est pourquoi les machines riches en forks dépendent de l'auto-renouvellement décrit plus bas.

Un abonnement échu vous empêche donc d'agrandir votre parc immédiatement, et d'agrandir les dépôts qu'il contient 60 jours plus tard.

## Période de grâce pour la migration de VM

Quand un fournisseur d'hébergement migre une VM vers du matériel physique différent, l'ID de machine change (il est dérivé d'identifiants matériels comme l'UUID DMI, `/etc/machine-id` et les adresses MAC des cartes réseau). Les licences de dépôt sont liées à l'ID de machine, donc une migration invaliderait normalement toutes les licences.

Pour gérer cela de manière transparente, les licences de dépôt incluent une **période de grâce de 40 jours pour l'ID de machine**. Si l'ID de machine ne correspond pas mais que la licence a été émise il y a moins de 40 jours, la licence est toujours acceptée. Puisque les licences se renouvellent tous les 30 jours, le prochain renouvellement lie automatiquement à l'ID de machine.

En pratique :
- VM migrée, ID de machine change : les dépôts continuent de fonctionner (dans la fenêtre de 40 jours)
- La prochaine opération `rdc` renouvelle la licence avec l'ID de machine
- Aucune intervention manuelle requise
- Vérifiez l'ID de machine et le statut de la licence avec `rdc machine status <machine> --system --licenses`

**Les comptes du canal Edge** fonctionnent sur le plan Community avec le double des limites (dépôts de 20 GB, 200 setups/mois, 2 machines). Les plans payants ne sont disponibles que sur le canal Stable. Voir [Canaux de publication](/fr/docs/release-channels) pour plus de détails.

## Ce qui se passe lors de la création, du démarrage, de l'arrêt et du redémarrage d'un dépôt

### Créer et bifurquer un dépôt

Lorsque vous créez ou bifurquez un dépôt :

1. `rdc` s'assure que votre token d'abonnement est disponible (déclenche l'authentification par code d'appareil si nécessaire)
2. `rdc` pré-émet une licence de dépôt depuis le serveur de comptes (le serveur vérifie le quota de slots de machine et les limites d'émission mensuelles à ce moment)
3. La licence de dépôt pré-émise est écrite sur la machine et validée localement (signature, ID de machine, GUID du dépôt, expiration et limite de taille)
4. Après la création réussie, `rdc` réémet la licence de dépôt avec des preuves d'identité du dépôt (UUID LUKS ou empreinte digitale de stockage)

Cette émission soutenue par le compte est comptabilisée dans votre utilisation mensuelle des **émissions de licences de dépôt**. Chaque licence contient l'adresse e-mail et le nom de l'entreprise du titulaire du compte, qui sont enregistrés lors de la validation de la licence par renet.

### Démarrer, arrêter et supprimer un dépôt

`rdc` valide la licence de dépôt installée sur la machine mais **ignore la vérification d'expiration**. La signature, l'ID de machine, le GUID du dépôt et l'identité sont toujours vérifiés. Les utilisateurs ne sont jamais bloqués dans l'exploitation de leurs dépôts, même avec un abonnement expiré.

### Redimensionner et étendre un dépôt

`rdc` effectue une validation complète de la licence de dépôt incluant l'expiration et les limites de taille.

### Redémarrage de machine et démarrage automatique

Le démarrage automatique utilise les mêmes règles que `rdc repo up` : l'expiration est ignorée, de sorte que les dépôts redémarrent toujours librement.

Les licences de dépôt utilisent un modèle de validité longue durée :

- `refreshRecommendedAt` est le point de renouvellement souple
- `hardExpiresAt` est le point de blocage

Si la licence de dépôt est périmée mais encore avant l'expiration définitive, l'exécution peut continuer. Une fois l'expiration définitive atteinte, `rdc` doit la renouveler pour les opérations de resize/expand.

### Autres opérations de dépôt

Les opérations telles que la liste des dépôts, l'inspection des informations de dépôt et le montage ne nécessitent aucune validation de licence.

## Vérifier le statut et renouveler les licences

Connexion humaine :

```bash
rdc subscription login
```

Connexion pour automatisation ou agent IA :

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Pour les environnements non interactifs, définir `REDIACC_TOKEN` est l'option la plus simple. Le token ne doit avoir une portée que pour les opérations d'abonnement et de licence de dépôt dont l'agent a besoin.

Afficher le statut d'abonnement soutenu par le compte :

```bash
rdc subscription status
```

Afficher les détails d'activation de machine pour une machine :

```bash
rdc subscription status -m hostinger
```

Afficher les détails de licence de dépôt installés sur une machine :

```bash
rdc subscription status -m hostinger
```

Renouveler la licence d'un dépôt sur une machine :

```bash
rdc subscription refresh -m hostinger --repo my-app
```

La réf `--repo` doit se résoudre dans votre configuration `rdc` locale. Un dépôt découvert sur la machine mais absent de la configuration locale est rejeté : il est signalé comme un échec et n'est pas auto-classifié.

Lors de la première utilisation, une opération de dépôt ou de sauvegarde sous licence qui ne trouve pas de licence de dépôt utilisable peut déclencher automatiquement un transfert d'autorisation de compte. Le CLI imprime une URL d'autorisation, essaie d'ouvrir le navigateur dans les terminaux interactifs, et retente l'opération une fois après que l'autorisation et l'émission ont réussi.

Dans les environnements non interactifs, le CLI n'attend pas l'approbation du navigateur. Il vous indique plutôt de fournir un token à portée limitée avec `rdc subscription login --token ...` ou `REDIACC_TOKEN`.

Pour la configuration initiale de la machine, consultez [Configuration de machine](/fr/docs/setup).

## Auto-renouvellement des licences

Tout ce qui précède suppose que vous êtes devant un clavier. Les sauvegardes planifiées, elles, ne le sont pas, et c'est précisément le cas pour lequel l'auto-renouvellement existe.

Une sauvegarde planifiée est validée au niveau strict : il lui faut donc une licence non expirée. Or la licence d'un fork est plafonnée à 7 jours. Vos machines ne détiennent aucune identification de compte, par conception, si bien qu'avant l'auto-renouvellement la sauvegarde d'un fork s'arrêtait tout simplement une semaine après sa création, sans bruit, à trois heures du matin.

### Comment une machine se renouvelle sans détenir de token

Chaque licence que Rediacc émet ou renouvelle porte un `renewalUrl`, l'adresse complète du point de terminaison de renouvellement sur le serveur de comptes qui l'a signée. Une machine lit cette adresse dans sa propre licence installée, elle n'a donc jamais besoin qu'on lui indique où se trouve son serveur de comptes.

La machine présente ensuite la licence installée à ce point de terminaison. La licence est son propre identifiant : elle est signée, le serveur vérifie cette signature, et aucun token d'API n'intervient nulle part. Le serveur renvoie une licence fraîche avec de nouvelles fenêtres de validité, et la machine l'installe puis la revalide avant de considérer le renouvellement comme terminé.

Le renouvellement porte sur toute la machine :

```bash
sudo renet license renew
```

Les dépôts sont regroupés par serveur signataire, si bien qu'une machine desservant deux univers de compte contacte chacun une seule fois. Un fichier de verrou empêche deux renouvellements de tourner en même temps, et `--jitter` étale un parc de machines qui, sinon, se réveilleraient toutes à l'heure pile.

Le serveur refuse un renouvellement dans trois cas, et chacun veut dire autre chose :

| Refus | Ce que cela signifie |
|---|---|
| L'abonnement est échu, suspendu, ou sa période de grâce est passée | Facturation. Le renouvellement reprend de lui-même une fois l'abonnement réactivé |
| Le certificat de délégation est expiré ou révoqué | Configuration on-premise. Renouvelez le certificat sur votre serveur on-premise, et les machines se renouvelleront normalement |
| L'identité de la machine ne correspond plus et la grâce de 40 jours est passée | La licence appartient à une machine qui n'est pas celle-ci. Réémettez depuis le contexte de la machine actuelle |

Un refus n'interrompt jamais toute la série. Un dépôt échu ne bloque pas le renouvellement des autres dépôts de la même machine.

### Les sauvegardes planifiées se renouvellent elles-mêmes

Chaque unité de sauvegarde écrite par Rediacc lance d'abord un renouvellement :

```
ExecStartPre=-<renet> license renew --jitter 45s
```

Le `-` en tête le marque volontairement comme « au mieux ». Un renouvellement refusé, une coupure réseau ou un agent Renet plus ancien qui ne connaît pas encore la commande ne doivent jamais faire tomber la sauvegarde elle-même. La sauvegarde s'exécute, et la licence est renouvelée au passage chaque fois que c'est possible.

### Quand une sauvegarde est bloquée

Si la gestion des licences refuse bel et bien une sauvegarde, la machine l'enregistre. Ce marqueur est le seul signal indiquant que les sauvegardes automatiques ont cessé de copier des données, il est donc mis en évidence :

```bash
rdc machine status <machine> --licenses
```

La colonne `backups` affiche `BLOCKED` avec le motif, et la même information est imprimée sous le tableau sous forme d'erreur pour ne pas se perdre parmi trente dépôts. La colonne `renewed` montre comment s'est passé le dernier renouvellement automatique, y compris le code de refus du serveur le cas échéant, ce qui vous indique si le correctif relève de la facturation ou du certificat on-premise.

Un renouvellement réussi efface le marqueur, tout comme une sauvegarde qui passe sa vérification de licence. Il n'y a rien à acquitter ni à réinitialiser à la main.

## Comportement hors ligne et expiration

La validation des licences s'effectue localement sur la machine. Vous n'avez pas besoin de contacter le serveur de comptes pour exploiter vos dépôts.

Cela signifie :

- un environnement en cours d'exécution n'a pas besoin de connectivité en temps réel avec le compte à chaque commande
- tous les dépôts peuvent toujours démarrer, s'arrêter et être supprimés même avec des licences expirées, les utilisateurs ne sont jamais bloqués dans l'exploitation de leurs propres dépôts
- les opérations d'approvisionnement (`create`, `fork`) nécessitent une licence de dépôt pré-émise, et les opérations de croissance (`resize`, `expand`) nécessitent une licence de dépôt valide
- les licences de dépôt véritablement expirées doivent être remplacées avant resize/expand, soit via `rdc` depuis votre station de travail, soit par la machine qui se renouvelle elle-même
- les signatures de licence sont vérifiées contre une clé publique intégrée, la vérification des signatures ne peut pas être désactivée

## Comportement de récupération

La récupération automatique est intentionnellement limitée :

- `missing` : `rdc` peut autoriser l'accès au compte si nécessaire, actualiser les licences de dépôt en lot et réessayer une fois
- `expired` : `rdc` peut actualiser les licences de dépôt en lot et réessayer une fois
- `machine_mismatch` : échoue rapidement et vous indique de réémettre depuis le contexte de machine actuel
- `repository_mismatch` : échoue rapidement et vous indique de renouveler les licences de dépôt explicitement
- `sequence_regression` : échoue rapidement comme un problème d'intégrité/état de licence de dépôt
- `invalid_signature` : échoue rapidement comme un problème d'intégrité/état de licence de dépôt
- `identity_mismatch` : échoue rapidement, l'identité du dépôt ne correspond pas à la licence installée
- `cert_expired` : échoue immédiatement sur les opérations de croissance (`create`, `fork`, `resize`) et sur le transfert de sauvegardes (`push`, `pull`) ; `repo up` et le démarrage automatique continuent de fonctionner, conformément au modèle souple d'expiration de licence. Renouvelez le certificat de délégation
- `cert_invalid` : échoue immédiatement, le certificat de délégation a échoué à une contrainte (signature de clé maître invalide, incompatibilité d'abonnement/de plan, plafond de taille ou séquence dépassant `maxTotalIssuances`). Réémettez le certificat après avoir corrigé la limite sous-jacente

Ces cas d'échec rapide ne consomment pas automatiquement les appels de renouvellement ou d'émission soutenus par le compte.

Deux remarques pour lire cette liste :

- `missing` n'est pas toujours un problème. C'est aussi le résultat normal la première fois qu'un dépôt est sollicité dans un datastore fraîchement forké, et c'est exactement ce qui fait que ce fork se comptabilise : la licence est émise, un slot est réclamé, et l'opération se poursuit. `identity_mismatch` est le contraire délibéré : un fichier de licence recopié depuis un autre datastore échoue immédiatement au lieu d'être réémis en silence.
- Cette liste décrit la récupération depuis votre station de travail. Une machine qui se renouvelle elle-même a ses propres issues, rapportées par `rdc machine status <machine> --licenses` plutôt que levées comme un échec de commande, parce qu'une sauvegarde planifiée n'a personne à prévenir.

## Certificats de délégation pour les déploiements on-premise

Pour les déploiements on-premise et en réseau isolé, le serveur de comptes amont émet un **certificat de délégation** qui autorise votre installation on-premise à signer des licences avec sa propre clé Ed25519. Cela limite l'installation on-premise à ses limites de plan et crée une chaîne infalsifiable.

Points clés pour les propriétaires d'abonnement :

- **Un certificat actif par abonnement.** Chaque installation on-premise applique des quotas mensuels et par machine contre son propre registre local, de sorte que plusieurs installations multiplieraient le quota effectif sans possibilité de réconciliation. Les clients ayant besoin de production + préproduction + reprise après sinistre doivent acheter un abonnement par installation.
- **Validité par défaut basée sur le palier** (15d / 60d / 90d / 120d) et plafonds (30d / 120d / 180d / 365d) - voir le tableau des limites ci-dessus.
- **Libre-service depuis le portail client.** Les propriétaires et administrateurs d'org peuvent créer, renouveler et révoquer des certificats de délégation à `/account/delegation-certs`. La page est visible par tous les clients quel que soit leur plan - seules les limites diffèrent.
- **Le renouvellement automatique** est pris en charge via un bootstrap en un clic qui émet un token API avec la portée `delegation:renew` pour que l'installation on-premise l'utilise pour les appels de renouvellement vers l'amont.
- **Le renouvellement en réseau isolé** est pris en charge via un manifeste de demande de renouvellement signé que l'administrateur on-premise télécharge, transfère hors ligne vers l'amont, et que l'amont traite pour émettre un nouveau certificat.

Voir [Installation on-premise - Licences pour les déploiements en réseau isolé](/fr/docs/on-premise) pour la configuration opérationnelle, et [Chaîne de licences et délégation](/fr/docs/license-chain) pour la conception cryptographique.

## Émissions mensuelles de licences de dépôt

Cette métrique comptabilise l'activité réussie d'émission de licences de dépôt soutenue par le compte dans le mois du calendrier UTC en cours.

Elle inclut :

- l'émission de licence de dépôt pour la première fois
- le renouvellement réussi de licence de dépôt qui retourne une licence nouvellement signée

Elle n'inclut pas :

- les entrées de lot inchangées
- les tentatives d'émission échouées
- les dépôts non suivis rejetés avant l'émission

Si vous avez besoin d'une vue de l'utilisation et de l'historique récent d'émission de licences de dépôt orientée client, utilisez le portail de comptes. Si vous avez besoin d'une inspection côté machine, utilisez `rdc subscription status -m` et `rdc subscription status -m`.
