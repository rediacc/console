---
title: Gestion des comptes
description: Organisations, équipes, membres et abonnements dans Rediacc.
category: Guides
order: 12
language: fr
---

### Organisations

Lors de votre inscription, Rediacc crée automatiquement une organisation pour vous. Votre organisation est le conteneur principal de toutes les ressources -- machines, dépôts, abonnements et membres d'équipe.

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

| Plan | Machines | Licences repo/mois | Fonctionnalités |
|------|----------|---------------------|-----------------|
| COMMUNITY | 2 | 500 | Basique |
| PROFESSIONAL | 10 | 2 000 | Groupes de permissions, priorité de file d'attente |
| BUSINESS | 25 | 5 000 | Ceph, analyses avancées, journal d'audit |
| ENTERPRISE | Illimité | Illimité | Marque personnalisée, compte dédié |

![Subscription Flow](/img/account-subscription-flow.svg)

Tous les plans commencent avec une période de grâce de 3 jours. Les activations de machines sont suivies par équipe et se libèrent automatiquement après inactivité.

### Facturation

Seul le **propriétaire** de l'organisation peut gérer la facturation :
- Créer une session de paiement Stripe pour les mises à niveau de plan
- Accéder au portail de facturation Stripe pour modifier le mode de paiement
- Demander des remboursements en libre-service (dans les 14 jours, avec un délai de 30 jours)
