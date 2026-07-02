---
title: Gestion des comptes
description: 'Organisations, équipes, membres et abonnements dans Rediacc.'
category: Guides
order: 12
language: fr
sourceHash: 3887adc59fc63c26
sourceCommit: 2e3862505c06f97f846b7d879375434011954f95
---

### Organisations

Créez un compte et Rediacc crée automatiquement une organisation pour vous. Cette organisation est le conteneur principal de tout ce que vous possédez ici : machines, dépôts, abonnements et personnes que vous invitez. Vous n'en créerez pas une seconde par accident. Il y a exactement une organisation par compte, et toutes les équipes et ressources en dépendent.

![Registration Flow](/img/account-registration-flow.svg)

Chaque organisation dispose de :
- Un nom unique (par défaut votre adresse e-mail)
- Un plan d'abonnement (commence avec COMMUNITY)
- Une équipe par défaut (tous les membres y sont ajoutés automatiquement)

### Membres et Rôles

Les organisations prennent en charge trois rôles :

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rôle | Capacités |
|------|-----------|
| **Owner** | Contrôle total : facturation, transfert de propriété, gestion de tous les membres et équipes |
| **Admin** | Inviter et supprimer des membres, créer et gérer des équipes, révoquer les tokens API |
| **Member** | Consulter les données de l'organisation, créer des tokens API, accéder aux équipes assignées |

Inviter des membres :
```bash
# Via le portail : Organisation > Membres > Inviter
# Ou via l'API
```

Lorsqu'un membre est supprimé, ses tokens API et ses tokens de config storage sont automatiquement révoqués.

### Équipes

Les équipes permettent de limiter les ressources au sein d'une organisation. Chaque organisation commence avec une équipe par défaut.

![Team Structure](/img/account-team-structure.svg)

Rôles d'équipe :
- **Team Admin** : Peut ajouter/supprimer des membres au sein de l'équipe
- **Member** : Peut accéder aux ressources de l'équipe

Les propriétaires et administrateurs de l'organisation ont automatiquement accès à toutes les équipes sans adhésion explicite.

### Abonnements et Plans

Rediacc propose quatre plans :

| Plan | Machines | Licences repo/mois | Validité cert de délégation par défaut / max | Fonctionnalités |
|------|----------|--------------------|----------------------------------------------|-----------------|
| COMMUNITY | 2 | 100 | 15d / 30d | Basique |
| PROFESSIONAL | 3 | 2 000+ | 60d / 120d | Groupes de permissions, journal d'audit, marque personnalisée, support prioritaire |
| BUSINESS | 10 | 5 000+ | 90d / 180d | Ceph, analyses avancées, priorité de file d'attente, file d'attente avancée |
| ENTERPRISE | 25+ | 15 000+ | 120d / 365d | Responsable de compte dédié |

![Subscription Flow](/img/account-subscription-flow.svg)

Tous les plans commencent avec une période de grâce de 3 jours. Les activations de machines sont suivies par équipe et se libèrent automatiquement après inactivité. Voir [Abonnement et licences](/fr/docs/subscription-licensing) pour le modèle complet machine vs licence de dépôt.

### Facturation

Seul le **propriétaire** de l'organisation peut gérer la facturation :
- Créer une session de paiement Stripe pour les mises à niveau de plan
- Accéder au portail de facturation Stripe pour modifier le mode de paiement
- Demander des remboursements en libre-service (dans les 14 jours, avec un délai de 30 jours)

### Région des données

Votre compte est stocké dans la région de données que vous avez sélectionnée lors de l'inscription (EU, US ou Asie-Pacifique). Ce choix est permanent. Le badge de région dans le portail indique la région où résident vos données. Voir [Régions de données](/fr/docs/data-regions) pour plus de détails.

### Canal Edge

Si votre compte est sur le canal Edge, un badge « Edge » s'affiche dans la barre latérale du portail. Les comptes Edge disposent de 2X les limites Community mais n'ont pas accès aux plans payants. Voir [Canaux de publication](/fr/docs/release-channels) pour les différences entre Edge et Stable.

### Certificats de délégation

Pour les déploiements on-premise et en réseau isolé, vous pouvez gérer vos propres certificats de délégation depuis le portail client à **/account/delegation-certs**. La page est visible par tous les clients quel que soit leur plan ; seules les validités par défaut par palier diffèrent.

#### Contrôle d'accès par rôle

| Action | Org Owner | Org Admin | Member |
|--------|-----------|-----------|--------|
| Lister / consulter / télécharger des certs | ✓ | ✓ | ✓ |
| Créer un nouveau cert | ✓ | ✓ | ✗ |
| Révoquer un cert | ✓ | ✓ | ✗ |
| Émettre un token de renouvellement automatique | ✓ | ✓ | ✗ |
| Traiter une demande de renouvellement en réseau isolé | ✓ | ✓ | ✗ |

Les membres peuvent consulter la liste et télécharger les certs existants (utile pour distribuer le cert à une flotte de machines), mais seuls les propriétaires et les administrateurs peuvent en émettre ou les révoquer.

#### Contrainte d'unicité

Un abonnement ne peut avoir qu'**un seul certificat de délégation actif à la fois**. Chaque installation on-premise applique des quotas mensuels et par machine contre son propre registre local ; plusieurs certs actifs multiplieraient le quota effectif sans possibilité de réconciliation.

Si vous tentez de créer un second cert alors qu'un est déjà actif, le portail affiche une boîte de dialogue avec deux choix :

- **Renouveler (recommandé)** - prolonge la chaîne existante. Toutes les licences de dépôt précédemment émises continuent de fonctionner sous le cert renouvelé. À utiliser lors de la rotation d'un cert arrivant à expiration sur la même installation on-premise.
- **Révoquer et créer un nouveau** - abandonne la chaîne existante et repart de zéro depuis la genèse. Les licences de dépôt précédemment émises deviennent invérifiables une fois que le `validUntil` de l'ANCIEN cert est dépassé. À utiliser uniquement lors d'une migration vers une nouvelle installation on-premise avec une clé de signature différente, ou lors de la récupération après une clé compromise.

Si vous avez besoin d'environnements séparés (production + préproduction + reprise après sinistre + multi-région), achetez un abonnement par installation.

#### Bootstrap du renouvellement automatique

Pour activer le renouvellement automatique on-premise, cliquez sur **Obtenir un token de renouvellement automatique** sur la page Certificats de délégation. Cela émet un token API avec la portée `delegation:renew` (permanent, sans expiration) et affiche les valeurs à coller dans votre fichier `.env` on-premise :

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

Le token accorde **uniquement** le renouvellement de cert de délégation. Il ne peut pas lire ni modifier d'autres ressources. C'est le seul moyen d'émettre un token `delegation:renew` ; le flux standard `/portal/api-tokens` n'inclut pas cette portée.

#### Renouvellement en réseau isolé

Si votre installation on-premise n'a pas d'accès HTTPS sortant, utilisez le flux de manifeste hors ligne :

1. Sur la page d'administration on-premise, cliquez sur **Télécharger la demande de renouvellement**. L'installation on-premise génère un manifeste signé contenant la tête de chaîne locale.
2. Transférez le manifeste vers l'amont (USB, e-mail chiffré, tout canal disponible).
3. Sur le portail amont, cliquez sur **Téléverser la demande de renouvellement** et sélectionnez le manifeste. L'amont vérifie la signature du manifeste, émet un nouveau cert et le retourne en tant que fichier `.json` téléchargeable.
4. Transférez le nouveau cert vers l'installation on-premise et téléversez-le via la page d'administration on-premise.

L'amont rejette les manifestes datant de plus de 7 jours. Voir [Installation on-premise](/fr/docs/on-premise) pour la procédure complète et [Chaîne de licences et délégation](/fr/docs/license-chain) pour la conception cryptographique.

#### Limite de fréquence

La création de cert est limitée à **10 tentatives par période glissante de 24h** par abonnement, tentatives échouées incluses (spam de collision, saisie invalide). Si vous atteignez la limite, le portail affiche une valeur `Retry-After` indiquant à quel moment vous pouvez réessayer.
