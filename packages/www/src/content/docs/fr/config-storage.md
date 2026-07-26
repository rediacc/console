---
title: Stockage de configuration
description: >-
  Synchronisation chiffrée à connaissance nulle des configurations, avec
  déverrouillage par passkey, mot de passe principal ou code de récupération
category: Guides
order: 8
language: fr
sourceHash: "97c64241ff4c0d81"
sourceCommit: "433347c5ea4754300fe3da80c4bfcee42dd161bc"
---

# Stockage de configuration

Le stockage de configuration fournit une synchronisation chiffrée à connaissance nulle de votre configuration CLI entre appareils. Vos configurations sont chiffrées côté client avec une clé de chiffrement de contenu (CEK), le serveur ne voit jamais les données en clair.

## Méthodes de déverrouillage (emplacements de clé)

Chaque store possède une seule CEK, enveloppée indépendamment pour chaque méthode de déverrouillage, un peu comme les slots de clé LUKS. N'importe quel emplacement ouvre la même clé, et les emplacements peuvent être ajoutés ou retirés sans avoir à rechiffrer vos données :

| Méthode | Ce que c'est | Remarques |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn avec l'extension PRF | L'option la plus robuste, adossée au matériel |
| **Mot de passe principal** | Un mot de passe de votre choix, étiré avec PBKDF2-SHA256 (600 000 itérations) | Fonctionne sans matériel compatible PRF ; permet aussi l'enrôlement CLI sans interface |
| **Code de récupération** | Un code généré au format `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Affiché une seule fois à la création, conservez-le en lieu sûr |

Chaque méthode alimente le même mécanisme : l'emplacement produit un secret qui se combine à un secret détenu par le serveur pour déballer la CEK. Aucune des deux moitiés ne suffit seule, si bien que la propriété de connaissance nulle tient pour les trois méthodes : le secret de l'emplacement n'atteint jamais le serveur.

Les emplacements se gèrent depuis le portail, sur la page Stockage de configuration. Les organisations qui souhaitent un déverrouillage exclusivement matériel peuvent activer la politique **exiger une passkey**, qui refuse et révoque les emplacements non-passkey pour tout le store.

Le déverrouillage se fait par appareil : vous déverrouillez une fois sur un nouvel appareil, après quoi les opérations CLI quotidiennes (push/pull) fonctionnent sans toucher à une passkey ni saisir de mot de passe.

## Prérequis

- **Authentification à deux facteurs** activée sur votre compte
- Pour la méthode **passkey** : un fournisseur de passkey avec support PRF, comme une clé de sécurité FIDO2 (ex. YubiKey), iCloud Keychain, Google Password Manager, 1Password ou Dashlane
- **Navigateur** : Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+

L'exigence PRF ne s'applique qu'à l'emplacement passkey. Les méthodes mot de passe principal et code de récupération fonctionnent avec n'importe quel navigateur pris en charge.

## Configuration

1. Accédez à **Stockage de configuration** dans la barre latérale, puis cliquez sur **Configurer le stockage de configuration**
2. La liste de vérification des prérequis vérifie votre navigateur, la 2FA et l'état de la session
3. Cliquez sur **Démarrer la configuration**. Pour un emplacement passkey, vous devrez toucher votre clé de sécurité deux fois :
   - Premier toucher : enregistre le passkey
   - Second toucher : dérive les clés de chiffrement via PRF
4. Configuration terminée, votre secret de passkey est stocké dans le trousseau de clés de votre système d'exploitation

Une fois la configuration terminée, ajoutez un emplacement mot de passe principal ou code de récupération depuis la page Stockage de configuration, pour qu'un authentificateur perdu ou non pris en charge ne puisse pas vous bloquer l'accès.

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

## Enrôlement CLI sans interface

Une machine sans navigateur (un serveur, un runner CI, un démon executor) peut s'enrôler dans un store existant grâce à la méthode du mot de passe principal :

```bash
rdc config remote enable --password
```

Prérequis :

- Un **emplacement mot de passe principal** déjà provisionné via le portail (le navigateur détient la clé pendant le provisionnement, cette étape ne peut donc pas elle-même se faire sans interface)
- Un **token API avec le scope `config:enroll`** pour authentifier l'appel

L'enrôlement est une lecture : le CLI récupère les paramètres KDF publics de l'emplacement ainsi que la clé enveloppée, dérive localement le secret du mot de passe, puis déballe la CEK sur l'appareil. Cela donne à l'appareil la capacité de déchiffrer et de synchroniser la configuration ; cela ne modifie pas le store.

## Activation et lectures hors ligne

`rdc config remote enable` connecte la configuration active au store. Lorsque le store est vide, l'activation **l'amorce à partir de votre configuration locale actuelle** : les ressources locales sont poussées (push) comme première version du store, puis récupérées (pull) pour prouver l'aller-retour. Lorsque le store contient déjà du contenu, l'activation se réconcilie avec lui plutôt que de l'écraser (elle échoue en cas de divergence réelle, sauf si vous passez `--force`).

Une fois activée, la configuration conserve un **cache de lecture** complet, chiffré au repos avec le même mécanisme que n'importe quelle configuration locale, de sorte que le store reste utilisable même lorsque le serveur de compte est inaccessible :

- **Les lectures fonctionnent hors ligne.** Le contenu en cache est servi avec un avertissement d'obsolescence sur stderr, étiqueté avec la version et l'horodatage mis en cache (`cachedVersion` / `cachedAt`).
- **Les écritures nécessitent le serveur et échouent proprement.** Il n'existe pas de file d'écriture hors ligne : une écriture qui ne peut pas atteindre le serveur échoue en nommant le serveur concerné. Si une commande d'écriture a réussi, le changement est sur le serveur.
- **Les modifications concurrentes depuis deux machines** se résolvent par pull-replay-repush au niveau du bucket de ressources, de sorte qu'une modification simultanée ailleurs n'écrase pas la vôtre.

## Rotation de clé

Faire tourner la CEK du store la réenveloppe sous une nouvelle génération :

- **Les codes de récupération sont toujours invalidés** par la rotation, générez-en et sauvegardez-en un nouveau ensuite
- Un **emplacement mot de passe principal** ne survit que si le mot de passe est ressaisi pendant l'assistant de rotation
- Un emplacement resté sur une ancienne génération est signalé comme obsolète plutôt que d'échouer avec une erreur de déchiffrement obscure

## Gestion des membres

Le stockage de configuration est limité par organisation. Les membres sont gérés via le portail web :

- **Voir les membres** : Stockage de configuration → Membres
- **Ajouter un membre** : Actuellement via CLI uniquement (interface web prévue)
- **Supprimer un membre** : Cliquez sur le bouton de suppression sur la page Membres (nécessite 2FA + ré-authentification)

Les protections de sécurité empêchent la suppression du dernier membre actif ou de vous-même.

Les configurations du store sont en outre limitées par équipe, mais cette limitation relève du **contrôle d'accès côté serveur, pas d'un isolement cryptographique** : une seule CEK à l'échelle de l'organisation chiffre les configurations de toutes les équipes, et c'est le serveur qui impose quelles équipes un membre peut lire.

## Sécurité

- **Connaissance nulle** : Le serveur stocke des données triplement chiffrées qu'il ne peut pas déchiffrer
- **Clé divisée** : Le déchiffrement nécessite à la fois votre secret d'emplacement (client) et le secret du serveur (serveur)
- **Jetons rotatifs** : Chaque appel API utilise un jeton neuf ; les anciens jetons s'autodétruisent
- **Liaison IP** : Les jetons sont liés à votre IP lors de la première utilisation
- **Révocation instantanée** : Les membres supprimés perdent l'accès en 30 secondes

## Dépannage

| Erreur | Cause | Solution |
|-------|-------|-----|
| PRF not supported | L'authentificateur ne dispose pas de l'extension PRF | Utilisez YubiKey, iCloud Keychain, 1Password ou Dashlane, ou ajoutez un emplacement mot de passe principal |
| X25519 not supported | Version du navigateur trop ancienne | Mettez à jour vers Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Already configured | Un stockage existe déjà pour votre organisation | Visitez /account/config-storage pour gérer |
| Config storage not configured | Le serveur ne dispose pas de stockage blob | Contactez votre administrateur pour configurer R2/RustFS |
| Token expired | Aucune activité pendant 24 heures | Exécutez n'importe quelle commande de stockage de configuration pour actualiser |
| Cannot remove last member | Verrouillerait le stockage de façon permanente | Ajoutez d'abord un autre membre |
| Stale slot | L'emplacement date d'avant la dernière rotation de clé | Réajoutez l'emplacement (les codes de récupération doivent être régénérés après chaque rotation) |

## Voir aussi

- [Console Web](/fr/docs/web-console), déverrouiller le store dans le navigateur pour exécuter des commandes
- [Proxy et executor](/fr/docs/proxy-and-executor), comment la clé déverrouillée est accordée à un executor
