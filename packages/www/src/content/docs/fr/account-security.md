---
title: Sécurité du compte et API
description: Authentification, tokens API, gestion des sessions et modèle de permissions.
category: Guides
tags:
  - account
  - security
subcategory: account
order: 13
language: fr
sourceHash: "cbfa1730b069f73c"
sourceCommit: "c707ed4d0e178e7c4cec46e5ff989a1472a8eb82"
---

### Authentification

Rediacc prend en charge plusieurs méthodes d'authentification :

![Auth Flow](/img/account-auth-flow.svg)

- **Mot de passe** : Connexion traditionnelle avec e-mail et mot de passe
- **Magic Link** : Connexion sans mot de passe via un lien envoyé par e-mail (expire après 15 minutes)
- **Authentification à deux facteurs (2FA)** : Basée sur TOTP avec codes de secours

Lorsque la 2FA est activée, la connexion nécessite à la fois votre mot de passe (ou magic link) et un code TOTP à 6 chiffres.

### Tokens API

Les tokens API authentifient les opérations de machine à machine (activation de licence CLI, vérifications d'état).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Portées :**
- `license:read` -- Consulter l'état de l'abonnement et de la licence
- `license:activate` -- Activer des machines et émettre des licences de dépôt
- `subscription:read` -- Lire les détails de l'abonnement

**Fonctionnalités de sécurité :**
- Liaison IP : un token ne vaut que pour l'adresse IP de sa première requête ; une nouvelle adresse demande une vérification TOTP ou une nouvelle connexion (voir ci-dessous)
- Portée par équipe : les tokens peuvent être restreints à une équipe spécifique
- Révocation automatique : les tokens sont révoqués lorsque le créateur est supprimé de l'organisation

Créer un token :
```bash
# Via le portail : API Tokens > Create
# La valeur du token est affichée une seule fois -- conservez-la en sécurité
```

#### Quand l'adresse IP change

Un token lié à une adresse IP est refusé depuis toute autre adresse, par exemple quand le fournisseur d'accès attribue une nouvelle adresse. La CLI se charge du transfert :

- **Terminal interactif, 2FA activée** : la CLI demande le code à 6 chiffres de l'application d'authentification, transfère le token vers la nouvelle adresse et relance la commande. Les codes de secours ne sont pas acceptés pour un transfert.
- **Scripts et CI (sans terminal)** : la commande échoue et indique les deux solutions : lancer une fois n'importe quelle commande `rdc` dans un terminal interactif (par exemple `rdc subscription status`) et saisir le code, ou lancer `rdc subscription login`.
- **2FA désactivée** : le token ne peut pas être transféré. `rdc subscription login` en émet un nouveau et, avec la 2FA activée, le prochain transfert ne demande qu'un code.
- **Codes erronés** : 5 codes erronés en 15 minutes bloquent le transfert, d'abord pendant 5 minutes, puis deux fois plus longtemps à chaque fois, jusqu'à 1 heure. Après 4 blocages, le transfert est désactivé pour ce token jusqu'au prochain `rdc subscription login`.
- **Les tokens d'executor** avec une liaison IP `unbound` ou `cloudflare` ne sont pas concernés.

Chaque transfert apparaît dans le journal d'activité du portail, avec l'ancienne et la nouvelle adresse.

### Flux de code d'appareil

La CLI peut s'authentifier sur les machines sans écran en utilisant le flux de code d'appareil :

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc subscription login
# Affiche : Entrez le code XXXX-XXXX-XX sur https://www.rediacc.com/account/authorize
# Après approbation, la CLI reçoit automatiquement les identifiants
```

### Config Storage

Pour une configuration chiffrée et synchronisée avec le serveur, consultez [Config Storage](/fr/docs/config-storage) pour le guide complet. Config storage utilise :
- Chiffrement zéro-knowledge (le serveur ne voit jamais le texte en clair)
- Dérivation de clés basée sur passkey (WebAuthn + PRF)
- Tokens rotatifs avec rotation par requête

### Sécurité des sessions

| Type de token | Durée de vie | Stockage | Rafraîchissement |
|---------------|-------------|----------|------------------|
| Access Token (JWT) | 15 minutes | Cookie HttpOnly | Automatique via refresh token |
| Refresh Token | 7 jours | Cookie HttpOnly | Rotation à chaque utilisation |
| Session élevée | 10 minutes | Côté serveur | Déclenché par réauthentification |

Les sessions élevées sont requises pour les opérations sensibles : changements de mot de passe, changements d'e-mail, configuration 2FA, transferts de propriété et actions administratives destructives.

### Modèle de permissions

Rediacc utilise trois couches de permissions indépendantes :

![Permission Flow](/img/account-permission-flow.svg)

**Couche 1 : Rôle système** -- Détermine l'accès aux endpoints d'administration système.

**Couche 2 : Rôle d'organisation** -- Contrôle ce qu'un utilisateur peut faire au sein de son organisation (owner, admin, member).

**Couche 3 : Rôle d'équipe** -- Limite l'accès aux ressources spécifiques de l'équipe (team_admin, member). Les propriétaires et administrateurs de l'organisation contournent les vérifications de rôle d'équipe.

Chaque requête API passe par toutes les couches applicables en séquence. Une requête vers un endpoint de portée équipe doit satisfaire l'authentification de session, l'appartenance à l'organisation et l'accès à l'équipe.

### Canaux de mise à jour

La CLI prend en charge deux canaux de publication :
- **stable** (par défaut) : Promu depuis edge après une période de stabilisation de 7 jours ; choisissez ce canal pour une cadence de mise à jour conservatrice
- **edge** : Dernières fonctionnalités, mis à jour à chaque publication

```bash
rdc update --channel edge      # Passer à edge
rdc update --channel stable    # Revenir à stable
rdc update --status            # Afficher le canal actuel
```

### Posture de sécurité CLI pour les agents IA

Les agents de codage qui invoquent `rdc` constituent une vraie surface d'attaque, et nous les traitons donc comme un principal distinct. Chaque invocation de `rdc` est classée au démarrage comme **humaine** ou **agent** sur la base de signaux d'environnement (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) et d'un parcours de l'arborescence `/proc` sous Linux. La détection est au mieux-effort. Un wrapper déterminé peut usurper les variables d'environnement, d'où l'importance du parcours de l'arborescence. Les agents bénéficient d'un ensemble de permissions réduit : les mutations de configuration sensibles nécessitent la barrière de connaissance (`--current <ancienne-valeur>`), l'éditeur interactif est refusé sans une dérogation `REDIACC_ALLOW_CONFIG_EDIT` vérifiée par l'arborescence, et `--reveal` sur toute commande d'affichage est bloqué. Chaque décision (autoriser, refuser ou accorder `--reveal`) écrit une ligne JSONL chaînée par hachage dans `~/.config/rediacc/audit.log.jsonl`. Exécutez `rdc config audit verify` pour vérifier l'intégrité de la chaîne.

Voir [Sûreté et garde-fous des agents IA](/fr/docs/ai-agents-safety) pour la matrice complète de ce que les agents peuvent et ne peuvent pas faire, des exemples de la barrière de connaissance et la mécanique de dérogation de portée.
