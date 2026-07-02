---
title: Abonnement et licences
description: >-
  Comprendre comment account, rdc et renet gèrent les slots de machine, les
  licences de dépôt et les limites de plan.
category: Guides
order: 7
language: fr
sourceHash: 10e9f781881854be
sourceCommit: 2e3862505c06f97f846b7d879375434011954f95
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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Vous pouvez également injecter le token directement via l'environnement afin que le CLI puisse émettre et renouveler les licences de dépôt sans aucune étape de connexion interactive :

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slots de machine et licences de dépôt

### Slots de machine (côté serveur)

Le suivi des slots de machine est appliqué côté serveur. Lorsque le CLI émet une licence de dépôt, le serveur de comptes vérifie le quota de slots de machine de l'abonnement (par exemple, 2 machines pour Community, 3 pour Professional). Un slot est conservé pendant 5 heures à partir de la dernière émission de licence de dépôt sur cette machine et se libère automatiquement après inactivité. Un plan Business à 10 slots peut donc couvrir des dizaines de machines au fil du temps, puisque les slots ne sont conservés que lorsque vous approvisionnez activement.

Aucun fichier de licence de machine n'est stocké sur la machine. L'application des slots se fait au moment de l'émission sur le serveur.

### Licence de dépôt

Une licence de dépôt est une licence signée pour un dépôt sur une machine. C'est le seul fichier de licence stocké sur la machine (`/var/lib/rediacc/license/repos/{guid}.json`).

Elle est utilisée pour :

- `rdc repo create` et `rdc repo fork`, validé avant l'approvisionnement (pré-émise sans preuves d'identité, puis réémise avec preuves d'identité après création)
- `rdc repo resize` et `rdc repo expand`, validation complète incluant l'expiration
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validé avec **expiration ignorée**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validé avec **expiration ignorée**
- démarrage automatique du dépôt au redémarrage de la machine, validé avec **expiration ignorée**

Les licences de dépôt sont liées à la machine et au dépôt cible. Chaque licence contient l'ID de machine, le GUID du dépôt, l'ID d'abonnement, les limites de plan et l'expiration. Pour les dépôts chiffrés, Rediacc vérifie également l'identité LUKS du volume sous-jacent.

Plusieurs abonnements peuvent coexister sur la même machine. Chaque dépôt porte sa propre licence avec son propre contexte d'abonnement.

## Limites par défaut

La taille du dépôt dépend du niveau de droits :

- Community : jusqu'à `10 GB`
- plans payants : limite du plan ou du contrat

Limites par défaut des plans payants :

| Plan | Licences flottantes | Taille du dépôt | Émissions mensuelles de licences de dépôt | Validité cert de délégation par défaut / max |
|------|---------------------|-----------------|-------------------------------------------|----------------------------------------------|
| Community | 2 | 10 GB | 100 | 15d / 30d |
| Professional | 3 | 50 GB | 2,000+ | 60d / 120d |
| Business | 10 | 200 GB | 5,000+ | 90d / 180d |
| Enterprise | 25+ | 1 TB+ | 15,000+ | 120d / 365d |

Les limites spécifiques au contrat peuvent augmenter ou diminuer ces valeurs pour un client particulier. La validité des certificats de délégation est également plafonnée à `subscription.expiresAt + 3 day grace`, de sorte que les abonnements facturés mensuellement obtiennent naturellement des certificats alignés sur leur cycle de facturation. Voir [Chaîne de licences et délégation - Politique de validité](/fr/docs/license-chain) pour les règles complètes.

## Période de grâce pour la migration de VM

Quand un fournisseur d'hébergement migre une VM vers du matériel physique différent, l'ID de machine change (il est dérivé d'identifiants matériels comme l'UUID DMI, `/etc/machine-id` et les adresses MAC des cartes réseau). Les licences de dépôt sont liées à l'ID de machine, donc une migration invaliderait normalement toutes les licences.

Pour gérer cela de manière transparente, les licences de dépôt incluent une **période de grâce de 40 jours pour l'ID de machine**. Si l'ID de machine ne correspond pas mais que la licence a été émise il y a moins de 40 jours, la licence est toujours acceptée. Puisque les licences se renouvellent tous les 30 jours, le prochain renouvellement lie automatiquement à l'ID de machine.

En pratique :
- VM migrée, ID de machine change : les dépôts continuent de fonctionner (dans la fenêtre de 40 jours)
- La prochaine opération `rdc` renouvelle la licence avec l'ID de machine
- Aucune intervention manuelle requise
- Vérifiez l'ID de machine et le statut de la licence avec `rdc machine query --system --licenses --name <machine>`

**Les utilisateurs du canal Edge** reçoivent 2X les limites Community sans frais supplémentaires (dépôts de 20 GB, 200 émissions/mois, 4 machines). Les plans payants ne sont disponibles que sur le canal Stable. Voir [Canaux de publication](/fr/docs/release-channels) pour plus de détails.

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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Pour les environnements non interactifs, définir `REDIACC_SUBSCRIPTION_TOKEN` est l'option la plus simple. Le token ne doit avoir une portée que pour les opérations d'abonnement et de licence de dépôt dont l'agent a besoin.

Afficher le statut d'abonnement soutenu par le compte :

```bash
rdc subscription status
```

Afficher les détails d'activation de machine pour une machine :

```bash
rdc subscription activation status -m hostinger
```

Afficher les détails de licence de dépôt installés sur une machine :

```bash
rdc subscription repo status -m hostinger
```

Renouveler les licences de dépôt en lot sur une machine :

```bash
rdc subscription refresh repos -m hostinger
```

Les dépôts découverts sur la machine mais absents de la configuration locale de `rdc` sont rejetés lors de l'actualisation en lot. Ils sont signalés comme des échecs et ne sont pas auto-classifiés.

Forcer le renouvellement de licence de dépôt pour un dépôt existant :

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

Lors de la première utilisation, une opération de dépôt ou de sauvegarde sous licence qui ne trouve pas de licence de dépôt utilisable peut déclencher automatiquement un transfert d'autorisation de compte. Le CLI imprime une URL d'autorisation, essaie d'ouvrir le navigateur dans les terminaux interactifs, et retente l'opération une fois après que l'autorisation et l'émission ont réussi.

Dans les environnements non interactifs, le CLI n'attend pas l'approbation du navigateur. Il vous indique plutôt de fournir un token à portée limitée avec `rdc subscription login --token ...` ou `REDIACC_SUBSCRIPTION_TOKEN`.

Pour la configuration initiale de la machine, consultez [Configuration de machine](/fr/docs/setup).

## Comportement hors ligne et expiration

La validation des licences s'effectue localement sur la machine. Vous n'avez pas besoin de contacter le serveur de comptes pour exploiter vos dépôts.

Cela signifie :

- un environnement en cours d'exécution n'a pas besoin de connectivité en temps réel avec le compte à chaque commande
- tous les dépôts peuvent toujours démarrer, s'arrêter et être supprimés même avec des licences expirées, les utilisateurs ne sont jamais bloqués dans l'exploitation de leurs propres dépôts
- les opérations d'approvisionnement (`create`, `fork`) nécessitent une licence de dépôt pré-émise, et les opérations de croissance (`resize`, `expand`) nécessitent une licence de dépôt valide
- les licences de dépôt véritablement expirées doivent être renouvelées via `rdc` avant resize/expand
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

Ces cas d'échec rapide ne consomment pas automatiquement les appels de renouvellement ou d'émission soutenus par le compte.

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

Si vous avez besoin d'une vue de l'utilisation et de l'historique récent d'émission de licences de dépôt orientée client, utilisez le portail de comptes. Si vous avez besoin d'une inspection côté machine, utilisez `rdc subscription activation status -m` et `rdc subscription repo status -m`.
