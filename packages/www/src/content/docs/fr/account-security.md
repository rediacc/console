---
title: Sécurité du compte et API
description: Authentification, tokens API, gestion des sessions et modèle de permissions.
category: Guides
order: 13
language: fr
sourceHash: "dcd061b971573573"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
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
- Liaison IP : la première requête verrouille le token à cette adresse IP
- Portée par équipe : les tokens peuvent être restreints à une équipe spécifique
- Révocation automatique : les tokens sont révoqués lorsque le créateur est supprimé de l'organisation

Créer un token :
```bash
# Via le portail : API Tokens > Create
# La valeur du token est affichée une seule fois -- conservez-la en sécurité
```

### Flux de code d'appareil

La CLI peut s'authentifier sur les machines sans écran en utilisant le flux de code d'appareil :

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
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
