---
title: "Chaîne de licence et délégation"
description: "Émission de licences inviolable, signature déléguée pour l'on-premise et détection de fork."
category: "Guides"
order: 8
language: fr
sourceHash: "6486263bfb9ebf98"
sourceCommit: "fc24769cfd0684622952395c5bafe44e6180530d"
---

# Chaîne de licence et délégation

Rediacc utilise une chaîne de hachage inviolable pour l'émission de licences et un modèle de certificat de délégation pour les déploiements on-premise. Cette page explique comment le système protège contre la falsification, les attaques par rejeu et le partage de licences.

## Pourquoi une chaîne ?

Chaque licence émise par un serveur de compte est enregistrée dans un registre en ajout seul. Chaque entrée est liée à la précédente via un hachage SHA-256, formant une chaîne. La chaîne possède trois propriétés qui rendent toute falsification détectable :

1. **Les numéros de séquence** sont globaux et monotoniques par abonnement. Sauter ou réordonner des entrées brise la chaîne.
2. **Les hachages de chaîne** lient chaque entrée à toutes les entrées précédentes. La modification d'une entrée passée invalide toutes les entrées suivantes.
3. **Renet stocke la séquence la plus élevée vue** par clé de signature et par abonnement. Un serveur qui effectue un rollback de séquence est détecté immédiatement.

## Comment une licence est émise

Lorsque la CLI demande une licence de dépôt, le serveur de compte :

1. Lit la tête de chaîne actuelle (dernière séquence + hachage) pour l'abonnement.
2. Construit la charge utile de licence avec le numéro de séquence suivant et le hachage de chaîne précédent intégrés.
3. Signe la charge utile avec Ed25519.
4. Calcule `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Ajoute l'entrée au registre d'émission de façon atomique. Si deux requêtes concurrentes entrent en collision sur la même séquence, le perdant re-acquiert la séquence suivante et re-signe.
6. Retourne le blob signé avec le hachage de chaîne à la CLI.

La `sequence` et `prevChainHash` se trouvent dans la charge utile signée (elles ne peuvent pas être modifiées sans invalider la signature). Le `chainHash` se trouve sur l'enveloppe (calculé après la signature pour éviter une dépendance circulaire).

## Comment une licence est renouvelée

L'émission part de votre station de travail, authentifiée en votre nom. Le renouvellement, lui, part de la machine, qui ne détient aucun identifiant de compte. Il lui faut donc une autre porte d'entrée :

```
POST /licenses/renew
{ license: <le blob signé installé>, machineId, clusterId? }
```

**La licence présentée sert d'identifiant.** Ce point de terminaison n'attend aucun token API. Le serveur vérifie la signature Ed25519 du blob, et passe par le certificat de délégation quand le blob en porte un, exactement comme le fait Renet sur la machine. Détenir une licence valablement signée pour un dépôt prouve le droit d'usage, et une machine qui en détient une se l'est forcément déjà vu accorder.

L'URL complète de ce point de terminaison voyage à l'intérieur de chaque licence que le serveur émet ou renouvelle, dans le champ `renewalUrl`. Une machine lit l'adresse de son propre serveur de comptes dans sa propre licence au lieu d'être configurée avec, ce qui permet à une machine desservant deux univers de compte de se renouveler auprès des deux.

Le blob renouvelé conserve le GUID du dépôt, le GUID grand et le type de celui qui a été présenté, prend la séquence suivante dans le même registre avec le hachage de chaîne qui en découle, et reçoit des fenêtres de validité recalculées. L'ID de machine est relié à la machine qui a présenté le blob, ce qui permet à une migration de VM de se réparer d'elle-même dans la fenêtre de grâce de 40 jours. L'identité de stockage (l'UUID LUKS ou l'empreinte de stockage) est reprise telle quelle, car un appel réseau ne peut pas ré-analyser le disque qu'il décrit.

### Refus

| Code | Statut | Signification |
|---|---|---|
| `INVALID_LICENSE_SIGNATURE` | 403 | La signature du blob n'a pas pu être vérifiée, ou son hachage de chaîne ne correspond pas au registre du serveur à cette séquence |
| `INVALID_LICENSE_PAYLOAD` | 400 | Le blob est mal formé |
| `DELEGATION_CERT_INVALID` | 403 | Le certificat joint a violé une contrainte ou la signature de sa clé maître |
| `DELEGATION_CERT_EXPIRED` | 403 | Le certificat joint est hors de sa fenêtre de validité |
| `DELEGATION_CERT_REVOKED` | 403 | Le certificat joint a été révoqué en amont |
| `LICENSE_IDENTITY_MISMATCH` | 403 | La machine qui présente la licence n'est pas celle sous licence et la grâce de 40 jours est écoulée |
| `SUBSCRIPTION_LAPSED` | 403 | L'abonnement a expiré ou est suspendu |
| `GRACE_PERIOD_ENDED` | 403 | La période de grâce de l'abonnement est terminée |
| `TRIAL_REQUIRED` | 403 | L'abonnement nécessite un essai ou un plan actif |
| `REPO_GUID_OWNERSHIP_CONFLICT` | 403 | Le GUID du dépôt appartient à un autre abonnement |
| `LICENSE_RENEWAL_FAILED` | 500 | Tout ce qui n'est pas classé |

Un refus laisse la licence installée intacte. La machine continue de fonctionner avec ce qu'elle a jusqu'à l'expiration définitive de cette licence.

### Renouvellement et slot de machine

Un renouvellement réussi touche la ligne d'activation de la machine : il réclame un slot si la machine n'en avait pas, et le rafraîchit si elle en avait un. Contrairement à l'émission, il n'est jamais refusé pour dépassement de limite. La réponse porte `overLimit`, et l'activation est signalée pour que le portail, le point de terminaison de statut de licence et `rdc subscription status` puissent l'afficher. L'émission d'une licence véritablement nouvelle, elle, bute toujours sur le plafond. Le raisonnement est détaillé dans [Abonnement et licences - Slots de machine](/fr/docs/subscription-licensing).

### Ordre de déploiement

Les serveurs de comptes se déploient avant les builds de la CLI et de l'agent Renet qui dépendent des champs ci-dessus. Un agent Renet qui ne trouve aucun `renewalUrl` dans une licence ignore ce dépôt et le signale plutôt que d'échouer, si bien qu'une licence plus ancienne continue de fonctionner jusqu'à ce qu'un rafraîchissement depuis la station de travail renseigne le champ. Dans l'autre sens, vous vous retrouvez avec des machines qui réclament un point de terminaison qui n'existe pas encore.

## Comment Renet valide

Chaque machine exécutant Renet stocke son dernier état de chaîne connu dans `{licenseDir}/chain-state.json` (c'est-à-dire `/var/lib/rediacc/license/chain-state.json`, un répertoire frère du `repos/` propre à chaque dépôt). L'état de la chaîne est délimité par clé de signature, par abonnement, par dépôt et par datastore, indexé sous la forme `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` (la partie datastore reste vide pour un dépôt sur le datastore par défaut de la machine).

Les parties « dépôt » et « datastore » de cette clé sont essentielles. Côté serveur, les numéros de séquence sont attribués par abonnement : sur une machine hébergeant plusieurs dépôts sous un même abonnement, une tête de chaîne enregistrée pour le dépôt B se retrouverait en avance sur la licence que le dépôt A s'apprête à présenter, et le dépôt A serait rejeté comme un rejeu alors qu'il n'y est pour rien. Un fork de datastore aggrave le même problème : le clone conserve le GUID du dépôt, seule son identité de datastore est réémise, donc sans la partie datastore la licence plus récente du fork ferait avancer une tête contre laquelle le dépôt d'origine valide encore. Rattacher la tête enregistrée au dépôt et au datastore que la licence nomme supprime les deux cas. Les entrées écrites par un agent Renet plus ancien dans un format de clé plus court sont supprimées au premier enregistrement de l'état, et la validation suivante réamorce la tête.

L'état de chaîne n'est lu et avancé que sur les opérations validées au niveau complet. Le niveau d'exploitation ne le lit ni ne l'avance, de sorte que démarrer un dépôt ne peut jamais déplacer une tête.

À chaque validation de licence, Renet vérifie :

| Vérification | Échec signifie |
|---|---|
| La signature Ed25519 est valide | La licence a été falsifiée ou altérée |
| `sequence >= lastKnownSequence` | Le serveur a effectué un rollback de la chaîne (attaque par rejeu) |
| Une répétition de `lastKnownSequence` porte le même `chainHash` | Une chaîne forkée a réutilisé un numéro de séquence |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | L'entrée de chaîne a été modifiée |

Revalider la licence déjà installée n'est pas une régression : la même séquence avec le même hachage de chaîne est acceptée, ce qui permet à une machine de valider le même fichier à chaque démarrage d'un dépôt.

Si l'une des vérifications échoue, la licence est rejetée et la raison de l'échec est signalée.

## Certificats de délégation (on-premise)

Pour les déploiements isolés du réseau ou auto-hébergés, le serveur de compte amont émet un **certificat de délégation** autorisant un serveur on-premise à signer des licences avec sa propre clé Ed25519. Le certificat contraint ce que le serveur on-premise peut faire.

### Structure du certificat

Un certificat de délégation contient :

- `subscriptionId` - l'abonnement auquel ce certificat s'applique
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` - limites de plan intégrées
- `maxTotalIssuances` - borne supérieure sur le numéro de séquence de la chaîne
- `delegatedPublicKey` - la clé publique Ed25519 du serveur on-premise (SPKI base64). Son empreinte hexadécimale à 16 caractères (les 8 premiers octets du `SHA-256` de la clé brute) est le `publicKeyId` enregistré sur chaque blob de licence que cette clé signe. `publicKeyId` est toujours une véritable empreinte de clé, jamais un espace réservé comme `"default"`.
- `genesisHash` - le point de départ de la chaîne (continuation depuis un certificat précédent, ou "genesis")
- `genesisSequence` - séquence de chaîne au moment de l'émission. Utilisé par `/onprem/cert-upload` pour valider que le nouveau certificat lie à une entrée connue dans le registre d'émission local lorsque la chaîne a avancé pendant le transit. Optionnel pour la rétrocompatibilité (traité comme 0 si absent).
- `validFrom`, `validUntil` - fenêtre de validité (régie par la politique de validité ci-dessous)
- Signé par la clé maître Ed25519 amont

### Comment fonctionne la délégation

1. L'administrateur Enterprise génère une paire de clés Ed25519 sur le serveur on-premise.
2. L'administrateur demande un certificat de délégation à l'amont :
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. L'amont signe le certificat avec sa clé maître et le retourne.
4. Le serveur on-premise stocke le certificat et sa clé privée, prêt à signer les licences.
5. Lorsqu'une CLI demande une licence au serveur on-premise, le serveur signe avec sa clé déléguée et **intègre le certificat de délégation complet dans le blob de licence** (le champ `delegationCert`). Le certificat n'est pas récupéré séparément ; il voyage avec chaque licence de dépôt.
6. Renet effectue une **validation à deux niveaux**, dans cet ordre :
   - Vérifie la signature du certificat contre la clé maître amont intégrée.
   - Applique la fenêtre de validité du certificat (`validFrom` / `validUntil`) sur les opérations de croissance (`repo create`, `fork`, `resize`, `expand`) et sur le transfert de sauvegardes (`repo push`, `pull`, sauvegardes). Le niveau d'exploitation (`repo up`, `up all`, démarrage automatique) ignore uniquement la fenêtre, à l'image de ce qu'il fait déjà pour l'expiration de la licence : vos charges de travail en cours ne s'arrêtent jamais parce qu'un certificat a expiré, mais un certificat expiré ne peut autoriser rien de nouveau. La signature, la liaison de clé et toutes les autres contraintes du certificat restent appliquées à tous les niveaux.
   - Exige que `fingerprint(cert.delegatedPublicKey) == blob.publicKeyId` (l'empreinte de clé hexadécimale à 16 caractères), de sorte que le certificat ne puisse garantir que les licences signées avec exactement la clé à laquelle il délègue.
   - Vérifie la signature du blob contre la clé déléguée du certificat.
   - Applique les contraintes du certificat : correspondance de l'abonnement, correspondance du plan, plafond de taille (`maxRepositorySizeGb`) et `blob.sequence <= cert.maxTotalIssuances`.
   - Applique toutes les vérifications standard de la chaîne.

Un échec du certificat échoue immédiatement avec une raison dédiée : `cert_expired` (hors de la fenêtre de validité) ou `cert_invalid` (signature de clé maître invalide ou contrainte violée). Ces raisons sont vérifiées **avant** `invalid_signature`, la raison liée au certificat l'emporte donc.

Le serveur on-premise ne peut pas :
- Forger une licence hors des limites de plan du certificat de délégation (renet la rejette).
- Émettre plus de `maxTotalIssuances` opérations au total (renet rejette le débordement de séquence).
- Continuer à signer des licences exploitables après le `validUntil` du certificat (la fenêtre est appliquée même sur les opérations qui ignorent l'expiration).
- Modifier le certificat (la signature amont est invalidée).

## Politique de validité

La fenêtre de validité d'un certificat de délégation est calculée par un assistant de politique partagé (`computeDelegationCertValidity()`) qui s'exécute à la fois sur le backend amont et sur le frontend du portail client. Les mêmes entrées produisent toujours le même `validUntil`, afin que les clients puissent prévisualiser la validité effective dans la fenêtre de création avant de soumettre.

### Valeurs par défaut et plafonds par plan

| Plan | Validité par défaut | Plafond du plan |
|---|---|---|
| COMMUNITY | 15 jours | 30 jours |
| PROFESSIONAL | 60 jours | 120 jours |
| BUSINESS | 90 jours | 180 jours |
| ENTERPRISE | 120 jours | 365 jours |

La valeur par défaut est celle que le point de terminaison de création utilise lorsque l'appelant omet `validDays`. Le plafond est la borne supérieure que l'appelant peut demander.

### Remplacement par abonnement

Les administrateurs peuvent définir une valeur `delegationCertDefaultDays` personnalisée sur un abonnement spécifique via la page de détail de l'abonnement admin. **Le remplacement remplace à la fois la valeur par défaut ET le plafond pour cet abonnement.** C'est une échappatoire pour les clients spéciaux (ex. un contrat enterprise nécessitant un certificat de 200 jours sur un plan COMMUNITY). Le schéma Zod applique tout de même une plage absolue de `1..365`.

### Plafond absolu : fin d'abonnement + 3 jours de grâce

Indépendamment du plafond du plan et du remplacement, chaque certificat est plafonné à `subscription.expiresAt + 3 jours` (le `SUBSCRIPTION_CONFIG.gracePeriodDays` existant). Cela signifie :

- Pour les abonnements perpétuels (`expiresAt = null`), aucun plafond d'expiration ne s'applique - seulement le plafond du plan.
- Pour les abonnements mensuels facturés par Stripe, le plafond est approximativement la prochaine date de facturation + 3 jours. Quand Stripe fait avancer `expiresAt` chaque mois, le plafond se déplace avec lui.
- Pour les abonnements d'essai, le plafond est la fin de l'essai + 3 jours.

### Jours effectifs et raison

Chaque réponse de création/renouvellement inclut `effectiveDays` et `reason` pour que l'appelant comprenne exactement pourquoi le certificat a obtenu cette validité :

| Raison | Signification |
|---|---|
| `plan_default` | Aucune demande, aucun remplacement : valeur par défaut du plan utilisée |
| `subscription_override` | Aucune demande : remplacement par abonnement utilisé comme valeur par défaut |
| `requested` | Demande de l'appelant honorée dans tous les plafonds |
| `plan_max_clamp` | La demande de l'appelant dépasse le plafond du plan - limitée |
| `override_max_clamp` | La demande de l'appelant dépasse le remplacement par abonnement - limitée |
| `subscription_cap_clamp` | La cible autrement valide surpasserait l'`expiresAt + 3 jours` de l'abonnement |

La fenêtre de création du portail client utilise ces raisons pour afficher un aperçu en direct ("Vous recevrez un certificat de 18 jours. Limité car le certificat ne peut pas dépasser la date de fin de votre abonnement de plus de 3 jours.") pour que les clients ne soumettent pas sans visibilité.

### Seuil de renouvellement adaptatif

La boucle de renouvellement automatique on-premise utilise un seuil adaptatif modélisé d'après Let's Encrypt :

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

Un certificat COMMUNITY de 15 jours se renouvelle à 5 jours restants. Un certificat BUSINESS de 90 jours se renouvelle à 14 jours restants (le plafond configuré par l'environnement s'applique). Un certificat ENTERPRISE de 120 jours se renouvelle à 14 jours restants. Cela empêche les certificats de courte durée de déclencher un renouvellement immédiatement tout en donnant aux certificats de longue durée une marge confortable.

## Application de l'unicité

Un abonnement peut avoir **au plus un certificat de délégation actif à la fois** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Pourquoi un seul ?

Chaque installation on-premise applique `maxRepoLicenseIssuancesPerMonth`, `maxActivations` et l'intégrité de la chaîne contre son propre registre d'émission local. L'on-premise ne synchronise pas les compteurs d'utilisation vers l'amont. C'est tout l'intérêt de la délégation capable de fonctionner hors ligne.

Si un abonnement avait plusieurs certificats actifs (un par installation), chaque installation appliquerait la limite indépendamment :

- Un abonnement de 500/mois avec 3 certificats actifs autoriserait jusqu'à **1 500 émissions/mois** en pratique.
- Trois chaînes parallèles, chacune ancrée à la genèse, sans aucune réconciliation d'audit possible.

L'amont ne peut pas détecter ce contournement car les on-prems sont conçus pour fonctionner hors ligne. **L'unicité est le seul modèle applicable.** Les clients multi-installations (production + staging + DR) doivent acheter un abonnement par installation.

### Comportement en cas de collision

`POST /admin/delegation-certs` et `POST /portal/delegation-certs` rejettent une seconde création avec :

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

Le portail client affiche cela avec une boîte de dialogue dédiée expliquant les conséquences :

- **Renouveler (recommandé)** - étend la chaîne existante. Toutes les licences de dépôt précédemment émises continuent de fonctionner.
- **Révoquer et créer** - supprime la chaîne existante et repart de la genèse. Les licences de dépôt précédemment émises deviennent invérifiables une fois que le `validUntil` de l'ANCIEN certificat est passé. À utiliser uniquement lors d'une migration vers un nouvel on-prem avec une clé de signature différente, ou lors de la récupération d'une clé compromise.

`renew()` est l'échange atomique qui préserve l'unicité et n'est **pas** soumis à la vérification de collision 409.

### Limite de débit

Même avec l'unicité, un appelant malveillant pourrait boucler `révoquer → créer → révoquer → créer` pour épuiser les cycles de signature de la clé maître amont. Les deux points de terminaison de création limitent à **10 tentatives par période glissante de 24h** par abonnement via la table `rateLimits` existante :

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

Le compteur s'incrémente à chaque tentative indépendamment du résultat (les boucles de spam par collision sont également limitées).

## Détection de fork

Si un client partage son certificat de délégation avec un tiers (ou exécute deux serveurs on-premise depuis le même certificat), les chaînes divergent. L'amont détecte cela au moment du renouvellement.

### Flux de renouvellement

1. L'administrateur on-premise appelle `POST /admin/delegation-certs/renew` avec la tête de chaîne actuelle :
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. L'amont parcourt les entrées de chaîne contre son propre enregistrement dans le registre.
3. Si `currentChainHash` ne correspond pas à l'enregistrement de chaîne de l'amont à `currentSequence`, fork détecté :
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. Le `genesisHash` du nouveau certificat est défini sur le hachage de chaîne actuel, afin que les machines avec l'ancien état de chaîne puissent continuer depuis où elles se sont arrêtées.

Si le certificat est partagé avec un tiers :
- Il peut l'utiliser pendant la période de validité du certificat.
- Au premier renouvellement, l'amont ne voit qu'une seule chaîne (la légitime).
- Le `genesisHash` du nouveau certificat ne correspond qu'à la chaîne légitime.
- Les machines sur la chaîne partagée rejetteront immédiatement les nouvelles licences car leur `chainHash` stocké ne se connecte pas au `genesisHash` du nouveau certificat.

## Renouvellement isolé du réseau

Pour les installations on-premise sans accès HTTPS sortant vers l'amont, le flux de renouvellement est entièrement hors ligne. Trois nouveaux points de terminaison ferment la boucle :

**Sur l'on-premise (`auth, root, requireElevated()`) :**
- `GET /onprem/cert-current` - télécharger le certificat signé actuellement chargé (sauvegarde, audit, re-import)
- `GET /onprem/renewal-request` - générer un manifeste signé contenant la tête de chaîne locale + clé publique déléguée, signé par la clé privée on-premise

**Sur l'amont (portail admin ou à portée org) :**
- `POST /admin/delegation-certs/process-renewal-request` (root système inter-client)
- `POST /portal/delegation-certs/process-renewal-request` (propriétaire/admin d'org)

### Manifeste de demande de renouvellement

La demande de renouvellement est un petit document JSON :

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

La signature est calculée sur l'encodage canonique du manifeste (clés triées alphabétiquement, puis `JSON.stringify`) en utilisant la clé privée on-premise. Cela garantit que les deux côtés calculent des octets identiques indépendamment de l'ordre de construction de l'objet.

### Vérification à l'amont

`processRenewalManifest()` effectue cinq vérifications :

1. **Un certificat actif existe** pour l'abonnement du manifeste. Retourne `404 NO_ACTIVE_CERT` sinon - le client doit utiliser le flux de création, pas le renouvellement.
2. **La clé publique déléguée correspond** au certificat actif. Retourne `400 DELEGATED_KEY_MISMATCH` sinon - protège contre le rejeu depuis un on-prem différent.
3. **La signature du manifeste se vérifie** contre la `delegatedPublicKey` du certificat actif. Retourne `400 MANIFEST_SIGNATURE_INVALID` sinon - prouve que le manifeste provient d'un détenteur de la clé privée on-premise.
4. **L'âge du manifeste** est dans les 7 jours (`RENEWAL_MANIFEST_MAX_AGE_MS`). Retourne `400 MANIFEST_EXPIRED` sinon - ancre anti-rejeu.
5. **La liaison du hachage de chaîne** à la `currentSequence` du manifeste correspond au registre de l'amont. Retourne `409 CHAIN_FORK_DETECTED` sinon - protège contre les chaînes forkées.

Si toutes les vérifications réussissent, `processRenewalManifest` appelle le flux `renew()` existant, qui expire atomiquement l'ancien certificat et en insère un nouveau. **Il n'est pas soumis au 409 de création côté single-active** car c'est un échange atomique, pas un révoquer+créer en 2 étapes.

### Avancement de séquence pendant le transit

Un manifeste de demande de renouvellement capture la tête de chaîne au moment de sa génération. Pendant que le manifeste est en transit (livraison USB, email chiffré), l'on-premise peut continuer à émettre des licences de dépôt, faisant avancer sa chaîne locale.

Lorsque le nouveau certificat est uploadé en retour vers l'on-premise, `/onprem/cert-upload` valide que le `genesisSequence` du nouveau certificat lie toujours à une entrée connue dans le registre d'émission local :

- Si `cert.genesisSequence > localHead.sequence` → retourne `409 CHAIN_HEAD_BEHIND` (l'amont est sur une chaîne forkée).
- Si `cert.genesisSequence > 0` et l'entrée du registre local à cette séquence a un `chainHash` différent de `cert.genesisHash` → retourne `409 CHAIN_FORK_ON_UPLOAD` (la chaîne locale a divergé).
- Sinon, le certificat est accepté. Les futures émissions continuent depuis `localHead.sequence + 1`.

Cela signifie **qu'aucun gel d'écriture n'est requis pendant le transit**. La chaîne s'étend naturellement des deux côtés. Analogue à la façon dont le renouvellement de certificat X.509 gère les numéros de série en vol.

## Audit périodique

L'amont fournit un point de terminaison d'audit pour vérifier l'intégrité de la chaîne sans renouveler le certificat :

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

L'amont parcourt les entrées et retourne soit `{ valid: true }` soit `{ valid: false, divergedAtSequence: N, expected, actual }`.

Les serveurs on-premise devraient appeler ce point de terminaison périodiquement (par défaut : hebdomadairement via la variable d'env `UPSTREAM_AUDIT_URL`) pour détecter les forks rapidement.

### Preuves d'audit côté machine

Renet peut vérifier la continuité de la chaîne localement en utilisant `VerifyAuditProof`. Lorsqu'une machine renouvelle sa licence après une longue interruption, le serveur peut retourner les entrées de chaîne intermédiaires comme preuve. La machine parcourt la preuve pour vérifier que chaque `chainHash` dérive du `prevHash + blobHash` précédent via SHA-256, détectant toute falsification sans contacter l'amont.

## Sécurité de la concurrence

D1 (la base de données de Cloudflare) ne prend pas en charge les transactions interactives. L'émission concurrente de licences pour le même abonnement pourrait entrer en collision sur le numéro de séquence. Le serveur de compte gère cela en :

1. Lisant la prochaine séquence + le hachage de chaîne précédent.
2. Construisant et signant le blob avec cette séquence intégrée.
3. Insérant l'entrée du registre avec `onConflictDoNothing`.
4. Si l'insertion retourne 0 lignes modifiées, la séquence a été réclamée par une autre requête - re-acquérir la séquence, re-construire, **re-signer** et réessayer.
5. Après 10 tentatives échouées, échouer avec une erreur.

Le détail critique : la tentative **re-signe** le blob. Une tentative naïve qui ne mettrait à jour que l'entrée du registre laisserait le blob signé avec un numéro de séquence obsolète, brisant la chaîne.

## Transport d'emails

Le serveur de compte peut envoyer des emails transactionnels (liens magiques, réinitialisation de mot de passe, notifications de sécurité) via deux transports configurables :

| Transport | Configuration |
|---|---|
| `ses` (par défaut) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Les deux transports fonctionnent pour les déploiements cloud et on-premise. Choisissez celui qui convient à votre infrastructure : AWS SES avec votre propre compte AWS, ou n'importe quel serveur SMTP (Microsoft Exchange, Postfix, SendGrid, Mailgun, etc.).

Le transport est sélectionné au démarrage via la variable d'environnement `EMAIL_TRANSPORT`. SMTP utilise le pooling de connexions et le chargement paresseux, donc la bibliothèque cliente SMTP n'est initialisée que si SMTP est sélectionné.

Tous les templates d'email et l'API email publique sont identiques entre les transports.

## Documentation liée

- [Installation On-Premise](/fr/docs/on-premise) - comment déployer le serveur on-premise
- [Abonnement et licences](/fr/docs/subscription-licensing) - limites du plan et emplacements machine
- [Canaux de publication](/fr/docs/release-channels) - canaux edge vs stable
- [Régions de données](/fr/docs/data-regions) - résidence des données par région
