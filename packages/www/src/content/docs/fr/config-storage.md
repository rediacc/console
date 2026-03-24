---
title: "Config Storage (Rediacc Provider)"
description: "Synchronisez en toute sécurité la configuration CLI entre appareils et équipes avec un chiffrement à connaissance nulle."
category: "Guides"
order: 9
language: fr
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

Le fournisseur de stockage de configuration Rediacc synchronise votre configuration CLI entre appareils et équipes avec un chiffrement à connaissance nulle. Vos clés SSH, adresses IP de machines et identifiants sont chiffrés côté client avant de quitter votre machine -- même les opérateurs Rediacc ne peuvent pas lire vos données.

## Prérequis

- **Fournisseur de passkey avec support PRF** : une clé de sécurité FIDO2 (ex. YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane
- **2FA activé** pour les propriétaires/administrateurs d'organisation (requis pour la configuration du store et la gestion des membres)
- **Abonnement de compte** avec config storage activé

## Démarrage rapide

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Configuration

### Bureau (avec navigateur)

```bash
rdc store add my-config --type rediacc
```

1. Une fenêtre de navigateur s'ouvre vers le portail de compte Rediacc
2. Enregistrez un passkey (popup YubiKey/iCloud Keychain/1Password)
3. L'extension PRF du passkey dérive vos clés de chiffrement
4. Les clés sont stockées dans le stockage sécurisé natif de votre OS (Keychain/keyctl/DPAPI)
5. Terminé -- aucun mot de passe à retenir

### Serveurs headless (sans navigateur)

```bash
rdc store add my-config --type rediacc --headless
```

1. La CLI affiche une URL avec un code d'appareil
2. Ouvrez l'URL sur votre téléphone ou ordinateur portable
3. Complétez l'enregistrement du passkey dans le navigateur
4. La CLI reçoit automatiquement vos clés chiffrées via un relais sécurisé
5. Connaissance nulle préservée -- le serveur ne relaie qu'un blob chiffré opaque

### URL de serveur personnalisée

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

Après la configuration, push et pull fonctionnent sans mot de passe ni invite :

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Chaque opération utilise un token rotatif qui s'autodétruit après une seule utilisation. Aucun identifiant statique.

## Gestion d'équipe

Les membres de l'équipe sont gérés via le portail web à `/account/config-storage/members`.

### Ajouter des membres

1. L'administrateur ouvre la page des membres config storage
2. Clique sur "Add Member" (nécessite 2FA)
3. Le navigateur de l'administrateur chiffre la clé de chiffrement d'équipe pour le nouveau membre
4. Le nouveau membre se connecte et accepte l'invitation
5. Les deux peuvent désormais push/pull les mêmes configurations

### Supprimer des membres

1. L'administrateur clique sur "Remove" à côté du membre (nécessite 2FA)
2. Les clés de chiffrement du membre sont supprimées immédiatement
3. Dans les 30 secondes, le membre perd tout accès aux configurations chiffrées

Aucune rotation de clé nécessaire -- le serveur cesse simplement de fournir les clés de déchiffrement au membre supprimé.

## Propriétés de sécurité

| Propriété | Comment |
|-----------|---------|
| **Connaissance nulle** | Le client chiffre avant l'envoi ; le serveur ne voit que des blobs opaques |
| **Pas de mot de passe maître** | La biométrie du passkey remplace entièrement les mots de passe |
| **Dérivation de clé divisée** | CEK nécessite passkey_secret (client) + server_secret (serveur) |
| **Tokens rotatifs** | Chaque appel API génère un nouveau token ; les anciens expirent |
| **Liaison IP** | Les tokens sont liés à l'IP du client à la première utilisation |
| **Triple chiffrement** | SDK (fenêtre temporelle) + CEK (client) + phrase d'organisation (serveur) |
| **Révocation instantanée** | Cesser de fournir le SDK aux membres supprimés ; délai max de 30 secondes |
| **Détection de falsification** | HMAC sur les blobs chiffrés ; vérifié à chaque pull |

Pour l'architecture de sécurité complète, consultez le [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## Dépannage

### "Passkey must support PRF extension"

Votre fournisseur de passkey ne supporte pas l'extension PRF. Utilisez :
- Une clé de sécurité FIDO2 (ex. YubiKey)
- iCloud Keychain (Safari sur macOS/iOS)
- Google Password Manager (Chrome sur Android/ChromeOS)
- 1Password
- Dashlane

### "Two-factor authentication required"

Les propriétaires et administrateurs d'organisation doivent activer le 2FA avant de configurer config storage. Allez dans Account Settings -> Security -> Enable 2FA.

### "Version conflict"

Un autre membre de l'équipe a poussé une version plus récente. Tirez d'abord :
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Les tokens expirent après 24 heures d'inactivité. Exécutez n'importe quelle commande pour actualiser :
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

La clé de chiffrement a été perdue du stockage sécurisé de votre OS (redémarrage sous Linux, réinitialisation du keychain). Relancez la configuration :
```bash
rdc store add my-config --type rediacc
```
