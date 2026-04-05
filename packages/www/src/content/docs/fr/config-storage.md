---
title: Stockage de configuration
description: >-
  Synchronisation chiffrée à connaissance nulle des configurations avec
  chiffrement basé sur les passkeys
category: Guides
order: 8
language: fr
sourceHash: "9612a5fecf063eea"
---

# Stockage de configuration

Le stockage de configuration fournit une synchronisation chiffrée à connaissance nulle de votre configuration CLI entre appareils. Vos configurations sont chiffrées avec des clés dérivées de votre passkey, le serveur ne voit jamais les données en clair.

## Prérequis

- **Authentification à deux facteurs** activée sur votre compte
- **Fournisseur de passkey avec support PRF** : clé de sécurité FIDO2 (ex. YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane
- **Navigateur** : Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+

## Configuration

1. Accédez à **Stockage de configuration** dans la barre latérale, puis cliquez sur **Configurer le stockage de configuration**
2. La liste de vérification des prérequis vérifie votre navigateur, la 2FA et l'état de la session
3. Cliquez sur **Démarrer la configuration**, vous devrez toucher votre clé de sécurité deux fois :
   - Premier toucher : enregistre le passkey
   - Second toucher : dérive les clés de chiffrement via PRF
4. Configuration terminée, votre secret de passkey est stocké dans le trousseau de clés de votre système d'exploitation

Après la configuration, les opérations CLI quotidiennes (push/pull) fonctionnent sans le passkey.

## Compatibilité des fournisseurs PRF

| Fournisseur | Support PRF | Plateformes |
|----------|:-----------:|-----------|
| YubiKey / clés de sécurité FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplateforme |
| Extension Bitwarden | ❌ | En développement |
| Windows Hello | ❌ | Non supporté |

## Gestion des membres

Le stockage de configuration est limité par organisation. Les membres sont gérés via le portail web :

- **Voir les membres** : Stockage de configuration → Membres
- **Ajouter un membre** : Actuellement via CLI uniquement (interface web prévue)
- **Supprimer un membre** : Cliquez sur le bouton de suppression sur la page Membres (nécessite 2FA + ré-authentification)

Les protections de sécurité empêchent la suppression du dernier membre actif ou de vous-même.

## Sécurité

- **Connaissance nulle** : Le serveur stocke des données triplement chiffrées qu'il ne peut pas déchiffrer
- **Clé divisée** : Le déchiffrement nécessite à la fois votre secret de passkey (client) et le secret du serveur (serveur)
- **Jetons rotatifs** : Chaque appel API utilise un jeton neuf ; les anciens jetons s'autodétruisent
- **Liaison IP** : Les jetons sont liés à votre IP lors de la première utilisation
- **Révocation instantanée** : Les membres supprimés perdent l'accès en 30 secondes

## Dépannage

| Erreur | Cause | Solution |
|-------|-------|-----|
| PRF not supported | L'authentificateur ne dispose pas de l'extension PRF | Utilisez YubiKey, iCloud Keychain, 1Password ou Dashlane |
| X25519 not supported | Version du navigateur trop ancienne | Mettez à jour vers Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Already configured | Un stockage existe déjà pour votre organisation | Visitez /account/config-storage pour gérer |
| Config storage not configured | Le serveur ne dispose pas de stockage blob | Contactez votre administrateur pour configurer R2/RustFS |
| Token expired | Aucune activité pendant 24 heures | Exécutez n'importe quelle commande de stockage de configuration pour actualiser |
| Cannot remove last member | Verrouillerait le stockage de façon permanente | Ajoutez d'abord un autre membre |
