---
title: Abonnement et licences
description: Comprendre comment account, rdc et renet gèrent les slots de machine, les licences de dépôt et les limites de plan.
category: Guides
order: 7
language: fr
sourceHash: "e7a65f722fbb1093"
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

`account` est la source de vérité pour les plans, les remplacements contractuels, l'état d'activation des machines et les émissions mensuelles de licences de dépôt.

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

## Licences de machine vs. Licences de dépôt

### Activation de machine

L'activation de machine remplit un double rôle :

- **Côté serveur** : comptabilisation des slots de machines flottantes, vérifications d'activation au niveau machine, liaison de l'émission de dépôts soutenue par le compte à une machine spécifique
- **Sur disque** : `rdc` écrit un blob d'abonnement signé dans `/var/lib/rediacc/license/machine.json` lors de l'activation. Ce blob est validé localement pour les opérations d'approvisionnement (`rdc repo create`, `rdc repo fork`). La licence de machine est valide 1 heure à partir de la dernière activation.

### Licence de dépôt

Une licence de dépôt est une licence signée pour un dépôt sur une machine.

Elle est utilisée pour :

- `rdc repo resize` et `rdc repo expand` — validation complète incluant l'expiration
- `rdc repo up`, `rdc repo down`, `rdc repo delete` — validé avec **expiration ignorée**
- `rdc backup push`, `rdc backup pull`, `rdc backup sync` — validé avec **expiration ignorée**
- démarrage automatique du dépôt au redémarrage de la machine — validé avec **expiration ignorée**

Les licences de dépôt sont liées à la machine et au dépôt cible, et Rediacc renforce ce lien avec les métadonnées d'identité du dépôt. Pour les dépôts chiffrés, cela inclut l'identité LUKS du volume sous-jacent.

En pratique :

- l'activation de machine répond : « cette machine peut-elle approvisionner de nouveaux dépôts ? »
- la licence de dépôt répond : « ce dépôt spécifique peut-il s'exécuter sur cette machine spécifique ? »

## Limites par défaut

La taille du dépôt dépend du niveau de droits :

- Community : jusqu'à `10 Go`
- plans payants : limite du plan ou du contrat

Limites par défaut des plans payants :

| Plan | Licences flottantes | Taille du dépôt | Émissions mensuelles de licences de dépôt |
|------|---------------------|-----------------|-------------------------------------------|
| Community | 2 | 10 Go | 500 |
| Professional | 5 | 100 Go | 5 000 |
| Business | 20 | 500 Go | 20 000 |
| Enterprise | 50 | 2048 Go | 100 000 |

Les limites spécifiques au contrat peuvent augmenter ou diminuer ces valeurs pour un client particulier.

## Ce qui se passe lors de la création, du démarrage, de l'arrêt et du redémarrage d'un dépôt

### Créer et bifurquer un dépôt

Lorsque vous créez ou bifurquez un dépôt :

1. `rdc` s'assure que votre token d'abonnement est disponible (déclenche l'authentification par code d'appareil si nécessaire)
2. `rdc` active la machine et écrit le blob d'abonnement signé sur la machine distante
3. La licence de machine est validée localement (elle doit se situer dans l'heure suivant l'activation)
4. Après la création réussie, `rdc` émet la licence de dépôt pour le nouveau dépôt

Cette émission soutenue par le compte est comptabilisée dans votre utilisation mensuelle des **émissions de licences de dépôt**.

### Démarrer, arrêter et supprimer un dépôt

`rdc` valide la licence de dépôt installée sur la machine mais **ignore la vérification d'expiration**. La signature, l'ID de machine, le GUID du dépôt et l'identité sont toujours vérifiés. Les utilisateurs ne sont jamais bloqués dans l'exploitation de leurs dépôts, même avec un abonnement expiré.

### Redimensionner et étendre un dépôt

`rdc` effectue une validation complète de la licence de dépôt incluant l'expiration et les limites de taille.

### Redémarrage de machine et démarrage automatique

Le démarrage automatique utilise les mêmes règles que `rdc repo up` — l'expiration est ignorée, de sorte que les dépôts redémarrent toujours librement.

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
rdc subscription activation-status -m hostinger
```

Afficher les détails de licence de dépôt installés sur une machine :

```bash
rdc subscription repo-status -m hostinger
```

Renouveler l'activation de machine et actualiser les licences de dépôt en lot :

```bash
rdc subscription refresh -m hostinger
```

Les dépôts découverts sur la machine mais absents de la configuration locale de `rdc` sont rejetés lors de l'actualisation en lot. Ils sont signalés comme des échecs et ne sont pas auto-classifiés.

Forcer le renouvellement de licence de dépôt pour un dépôt existant :

```bash
rdc subscription refresh-repo my-app -m hostinger
```

Lors de la première utilisation, une opération de dépôt ou de sauvegarde sous licence qui ne trouve pas de licence de dépôt utilisable peut déclencher automatiquement un transfert d'autorisation de compte. Le CLI imprime une URL d'autorisation, essaie d'ouvrir le navigateur dans les terminaux interactifs, et retente l'opération une fois après que l'autorisation et l'émission ont réussi.

Dans les environnements non interactifs, le CLI n'attend pas l'approbation du navigateur. Il vous indique plutôt de fournir un token à portée limitée avec `rdc subscription login --token ...` ou `REDIACC_SUBSCRIPTION_TOKEN`.

Pour la configuration initiale de la machine, consultez [Configuration de machine](/fr/docs/setup).

## Comportement hors ligne et expiration

La validation des licences s'effectue localement sur la machine — elle ne nécessite pas de connectivité en temps réel avec le serveur de comptes.

Cela signifie :

- un environnement en cours d'exécution n'a pas besoin de connectivité en temps réel avec le compte à chaque commande
- tous les dépôts peuvent toujours démarrer, s'arrêter et être supprimés même avec des licences expirées — les utilisateurs ne sont jamais bloqués dans l'exploitation de leurs propres dépôts
- les opérations d'approvisionnement (`create`, `fork`) nécessitent une licence de machine valide, et les opérations de croissance (`resize`, `expand`) nécessitent une licence de dépôt valide
- les licences de dépôt véritablement expirées doivent être renouvelées via `rdc` avant resize/expand

L'activation de machine et les licences d'exécution de dépôt sont des surfaces distinctes. Une machine peut être inactive dans l'état du compte tandis que certains dépôts ont encore des licences de dépôt installées valides. Dans ce cas, inspectez les deux surfaces séparément plutôt que de supposer qu'elles signifient la même chose.

## Comportement de récupération

La récupération automatique est intentionnellement limitée :

- `missing` : `rdc` peut autoriser l'accès au compte si nécessaire, actualiser les licences de dépôt en lot et réessayer une fois
- `expired` : `rdc` peut actualiser les licences de dépôt en lot et réessayer une fois
- `machine_mismatch` : échoue rapidement et vous indique de réémettre depuis le contexte de machine actuel
- `repository_mismatch` : échoue rapidement et vous indique de renouveler les licences de dépôt explicitement
- `sequence_regression` : échoue rapidement comme un problème d'intégrité/état de licence de dépôt
- `invalid_signature` : échoue rapidement comme un problème d'intégrité/état de licence de dépôt
- `identity_mismatch` : échoue rapidement — l'identité du dépôt ne correspond pas à la licence installée

Ces cas d'échec rapide ne consomment pas automatiquement les appels de renouvellement ou d'émission soutenus par le compte.

## Émissions mensuelles de licences de dépôt

Cette métrique comptabilise l'activité réussie d'émission de licences de dépôt soutenue par le compte dans le mois du calendrier UTC en cours.

Elle inclut :

- l'émission de licence de dépôt pour la première fois
- le renouvellement réussi de licence de dépôt qui retourne une licence nouvellement signée

Elle n'inclut pas :

- les entrées de lot inchangées
- les tentatives d'émission échouées
- les dépôts non suivis rejetés avant l'émission

Si vous avez besoin d'une vue de l'utilisation et de l'historique récent d'émission de licences de dépôt orientée client, utilisez le portail de comptes. Si vous avez besoin d'une inspection côté machine, utilisez `rdc subscription activation-status -m` et `rdc subscription repo-status -m`.
