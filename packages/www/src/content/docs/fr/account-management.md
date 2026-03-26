---
title: Gestion des comptes
description: Organisations, equipes, membres et abonnements dans Rediacc.
category: Guides
order: 12
language: fr
---

### Organisations

Lors de votre inscription, Rediacc cree automatiquement une organisation pour vous. Votre organisation est le conteneur principal de toutes les ressources -- machines, depots, abonnements et membres d'equipe.

![Registration Flow](/img/account-registration-flow.svg)

Chaque organisation dispose de :
- Un nom unique (par defaut votre adresse e-mail)
- Un plan d'abonnement (commence avec COMMUNITY)
- Une equipe par defaut (tous les membres y sont ajoutes automatiquement)

### Membres et Roles

Les organisations prennent en charge trois roles :

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Role | Capacites |
|------|-----------|
| **Owner** | Controle total : facturation, transfert de propriete, gestion de tous les membres et equipes |
| **Admin** | Inviter et supprimer des membres, creer et gerer des equipes, revoquer les tokens API |
| **Member** | Consulter les donnees de l'organisation, creer des tokens API, acceder aux equipes assignees |

Inviter des membres :
```bash
# From the portal: Organization > Members > Invite
# Or via API
```

Lorsqu'un membre est supprime, ses tokens API et ses tokens de config storage sont automatiquement revoques.

### Equipes

Les equipes permettent de limiter les ressources au sein d'une organisation. Chaque organisation commence avec une equipe par defaut.

![Team Structure](/img/account-team-structure.svg)

Roles d'equipe :
- **Team Admin** : Peut ajouter/supprimer des membres au sein de l'equipe
- **Member** : Peut acceder aux ressources de l'equipe

Les proprietaires et administrateurs de l'organisation ont automatiquement acces a toutes les equipes sans adhesion explicite.

### Abonnements et Plans

Rediacc propose quatre plans :

| Plan | Machines | Licences repo/mois | Fonctionnalites |
|------|----------|---------------------|-----------------|
| COMMUNITY | 2 | 500 | Basique |
| PROFESSIONAL | 10 | 2 000 | Groupes de permissions, priorite de file d'attente |
| BUSINESS | 25 | 5 000 | Ceph, analyses avancees, journal d'audit |
| ENTERPRISE | Illimite | Illimite | Marque personnalisee, compte dedie |

![Subscription Flow](/img/account-subscription-flow.svg)

Tous les plans commencent avec une periode de grace de 3 jours. Les activations de machines sont suivies par equipe et se liberent automatiquement apres inactivite.

### Facturation

Seul le **proprietaire** de l'organisation peut gerer la facturation :
- Creer une session de paiement Stripe pour les mises a niveau de plan
- Acceder au portail de facturation Stripe pour modifier le mode de paiement
- Demander des remboursements en libre-service (dans les 14 jours, avec un delai de 30 jours)
