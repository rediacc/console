---
title: Securite du compte et API
description: Authentification, tokens API, gestion des sessions et modele de permissions.
category: Guides
order: 13
language: fr
---

### Authentification

Rediacc prend en charge plusieurs methodes d'authentification :

![Auth Flow](/img/account-auth-flow.svg)

- **Mot de passe** : Connexion traditionnelle avec e-mail et mot de passe
- **Magic Link** : Connexion sans mot de passe via un lien envoye par e-mail (expire apres 15 minutes)
- **Authentification a deux facteurs (2FA)** : Basee sur TOTP avec codes de secours

Lorsque la 2FA est activee, la connexion necessite a la fois votre mot de passe (ou magic link) et un code TOTP a 6 chiffres.

### Tokens API

Les tokens API authentifient les operations de machine a machine (activation de licence CLI, verifications d'etat).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Portees :**
- `license:read` -- Consulter l'etat de l'abonnement et de la licence
- `license:activate` -- Activer des machines et emettre des licences de depot
- `subscription:read` -- Lire les details de l'abonnement

**Fonctionnalites de securite :**
- Liaison IP : la premiere requete verrouille le token a cette adresse IP
- Portee par equipe : les tokens peuvent etre restreints a une equipe specifique
- Revocation automatique : les tokens sont revoques lorsque le createur est supprime de l'organisation

Creer un token :
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### Flux de code d'appareil

La CLI peut s'authentifier sur les machines sans ecran en utilisant le flux de code d'appareil :

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

Pour une configuration chiffree et synchronisee avec le serveur, consultez [Config Storage](/en/docs/config-storage) pour le guide complet. Config storage utilise :
- Chiffrement zero-knowledge (le serveur ne voit jamais le texte en clair)
- Derivation de cles basee sur passkey (WebAuthn + PRF)
- Tokens rotatifs avec rotation par requete

### Securite des sessions

| Type de token | Duree de vie | Stockage | Rafraichissement |
|---------------|-------------|----------|------------------|
| Access Token (JWT) | 15 minutes | Cookie HttpOnly | Automatique via refresh token |
| Refresh Token | 7 jours | Cookie HttpOnly | Rotation a chaque utilisation |
| Elevated Session | 10 minutes | Cote serveur | Declenche par reauthentification |

Les sessions elevees sont requises pour les operations sensibles : changements de mot de passe, changements d'e-mail, configuration 2FA, transferts de propriete et actions administratives destructives.

### Modele de permissions

Rediacc utilise trois couches de permissions independantes :

![Permission Flow](/img/account-permission-flow.svg)

**Couche 1 : Role systeme** -- Determine l'acces aux endpoints d'administration systeme.

**Couche 2 : Role d'organisation** -- Controle ce qu'un utilisateur peut faire au sein de son organisation (owner, admin, member).

**Couche 3 : Role d'equipe** -- Limite l'acces aux ressources specifiques de l'equipe (team_admin, member). Les proprietaires et administrateurs de l'organisation contournent les verifications de role d'equipe.

Chaque requete API passe par toutes les couches applicables en sequence. Une requete vers un endpoint de portee equipe doit satisfaire l'authentification de session, l'appartenance a l'organisation et l'acces a l'equipe.

### Canaux de mise a jour

La CLI prend en charge deux canaux de publication :
- **stable** (par defaut) : Teste en profondeur, recommande pour la production
- **edge** : Dernieres fonctionnalites, mis a jour a chaque publication

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
