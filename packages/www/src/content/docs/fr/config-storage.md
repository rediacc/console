---
title: Stockage de configuration
description: >-
  Synchronisation chiffrée côté client des configurations, avec
  déverrouillage par passkey, mot de passe principal ou code de récupération
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: fr
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Stockage de configuration

Le stockage de configuration synchronise une configuration CLI entre appareils. Les configurations sont chiffrées sur l'appareil avec une clé de chiffrement de contenu (CEK) que le serveur ne détient jamais. La section [Sécurité](#security) précise exactement contre quoi cela protège, et contre quoi non.

## Méthodes de déverrouillage (emplacements de clé)

Chaque store possède une seule CEK, enveloppée indépendamment pour chaque méthode de déverrouillage, un peu comme les slots de clé LUKS. N'importe quel emplacement ouvre la même clé, et les emplacements peuvent être ajoutés ou retirés sans avoir à rechiffrer vos données :

| Méthode | Ce que c'est | Remarques |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn avec l'extension PRF | L'option la plus robuste, adossée au matériel |
| **Mot de passe principal** | Un mot de passe de votre choix, étiré avec PBKDF2-SHA256 (600 000 itérations) | Fonctionne sans matériel compatible PRF ; permet aussi l'enrôlement CLI sans interface |
| **Code de récupération** | Un code généré au format `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Affiché une seule fois à la création, conservez-le en lieu sûr |

Chaque méthode alimente le même mécanisme : l'emplacement produit un secret qui se combine à un secret détenu par le serveur pour déballer la CEK. Aucune des deux moitiés ne suffit seule, et le secret de l'emplacement n'atteint jamais le serveur. Un emplacement mot de passe principal est le plus faible des trois : le serveur détient tout ce qu'il faut pour tester des mots de passe hors ligne, d'où l'exigence d'un mot de passe robuste. Les emplacements passkey et code de récupération n'ont pas cette faiblesse.

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
3. Choisissez la première méthode de déverrouillage, puis cliquez sur **Créer l'espace de configuration** :
   - **Passkey**, si votre fournisseur prend en charge PRF : vous touchez votre clé de sécurité deux fois, une fois pour l'enregistrer et une fois pour dériver les clés de chiffrement.
   - **Mot de passe maître**, qui fonctionne avec n'importe quel navigateur, y compris les fournisseurs de passkeys sans PRF comme Bitwarden.
   - En option, un **code de récupération**, affiché une seule fois et à conserver avant la création du stockage.
4. La configuration est terminée. La CLI conserve le secret de déverrouillage dans le trousseau de votre système.

Une passkey peut être ajoutée plus tard depuis la page Config Storage. Gardez au moins deux méthodes de déverrouillage, pour qu'un authentificateur perdu ou non pris en charge ne vous bloque pas.

## Compatibilité des fournisseurs PRF

| Fournisseur | Support PRF | Plateformes |
|----------|:-----------:|-----------|
| YubiKey / clés de sécurité FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplateforme |
| Extension Bitwarden | ❌ | Utilisez plutôt un mot de passe principal |
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
- **Les modifications concurrentes depuis deux machines** se résolvent par pull-replay-repush : le serveur n'accepte un push que par-dessus la version qu'il remplace, et le push perdant est rejoué sur la copie fraîche, de sorte qu'une modification simultanée ailleurs n'est pas écrasée.
- **Une configuration locale** (sans bloc `remote`) n'est pas concernée par tout cela et fonctionne entièrement hors ligne.

## Ce qui se synchronise

Tout dans une configuration se synchronise, y compris l'ID réseau de chaque dépôt, à l'exception de ces champs propres à l'appareil : `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier`, ainsi que les champs de connexion `account.accountServer` et `account.e2ePublicKey`. La connexion et la déconnexion se font par appareil.

## Versions et restauration

Le serveur conserve les 50 dernières versions de chaque configuration.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Une restauration publie l'ancien contenu comme une nouvelle version par-dessus la version actuelle ; le numéro de version ne recule jamais. Chaque appareil reçoit le contenu restauré à son prochain pull, et la restauration est enregistrée dans le journal d'audit.

## Rotation de clé

Faire tourner la CEK du store la réenveloppe sous une nouvelle génération :

- **Les codes de récupération sont toujours invalidés** par la rotation, générez-en et sauvegardez-en un nouveau ensuite
- Un **emplacement mot de passe principal** ne survit que si le mot de passe est ressaisi pendant l'assistant de rotation
- Un emplacement resté sur une ancienne génération est signalé comme obsolète plutôt que d'échouer avec une erreur de déchiffrement obscure
- Les tokens de configuration des autres membres sont révoqués, et un appareil qui détient encore l'ancienne clé est invité à se réactiver avec `rdc config remote enable`

## Gestion des membres

Le stockage de configuration est limité par organisation. Les membres sont gérés via le portail web :

- **Voir les membres** : Stockage de configuration → Membres
- **Ajouter un membre** : Actuellement via CLI uniquement (interface web prévue)
- **Supprimer un membre** : Cliquez sur le bouton de suppression sur la page Membres (nécessite 2FA + ré-authentification)

Les protections de sécurité empêchent la suppression du dernier membre actif ou de vous-même.

Les configurations du store sont en outre limitées par équipe, mais cette limitation relève du **contrôle d'accès côté serveur, pas d'un isolement cryptographique** : une seule CEK à l'échelle de l'organisation chiffre les configurations de toutes les équipes, et c'est le serveur qui impose quelles équipes un membre peut lire.

## Sécurité

**Ce qui est protégé.** Les configurations stockées sont confidentielles face à une compromission du stockage du serveur et face à un opérateur passif. Chaque blob est lié à son store, sa configuration, son équipe et sa version, si bien que le serveur ne peut pas substituer le blob d'une configuration à celui d'une autre, ni le modifier sans que cela se voie.

**Ce qui n'est pas protégé.** Un opérateur qui sert du code de portail malveillant peut lire la clé dans le navigateur. Un opérateur peut aussi retenir la version la plus récente face à un appareil qui ne l'a jamais vue.

| Le serveur peut | Le serveur ne peut pas |
|---|---|
| Voir les ids de configuration, les équipes, les numéros de version, les horodatages, la taille des blobs, le nombre de champs qu'une configuration engage et le type de chacun, ainsi que les adresses IP des clients | Voir les noms de machines, de dépôts ou de stores (ils sont aveuglés), ni aucune valeur de configuration |
| Refuser, retarder ou supprimer des configurations et leur historique | Servir le contenu d'une configuration comme s'il s'agissait d'une autre, ou le modifier, sans que l'appareil le détecte |
| Servir une ancienne version à un appareil qui n'en a jamais vu de plus récente | Servir au CLI une version plus ancienne qu'une autre déjà vue : le CLI la refuse |
| Tester des mots de passe principaux hors ligne | Ouvrir un emplacement passkey ou code de récupération |

Autres garanties :

- **Clé divisée** : le déchiffrement nécessite à la fois le secret de l'emplacement (sur l'appareil) et le secret du serveur
- **La suppression exige la connaissance** : retirer une valeur engagée d'une configuration exige de prouver que cette valeur était connue, si bien qu'un acteur à accès partiel ne peut pas retirer des champs en silence
- **Jetons rotatifs** : chaque requête fait tourner le jeton de configuration ; un jeton est lié à l'IP de sa première utilisation et expire au bout de 7 jours
- **Révocation** : supprimer un membre efface d'un coup ses emplacements de clé et ses jetons ; ce qu'il avait déjà récupéré reste sur son appareil, et une rotation de la CEK empêche une clé conservée d'ouvrir des versions ultérieures

## Dépannage

| Erreur | Cause | Solution |
|-------|-------|-----|
| PRF not supported | L'authentificateur ne dispose pas de l'extension PRF | Utilisez YubiKey, iCloud Keychain, 1Password ou Dashlane, ou ajoutez un emplacement mot de passe principal |
| X25519 not supported | Version du navigateur trop ancienne | Mettez à jour vers Chrome 133+, Edge 133+, Firefox 130+ ou Safari 17+ |
| Already configured | Un stockage existe déjà pour votre organisation | Visitez /account/config-storage pour gérer |
| Config storage not configured | Le serveur ne dispose pas de stockage blob | Contactez votre administrateur pour configurer R2/RustFS |
| Token expired | Aucune activité pendant 7 jours, ou la machine a changé de réseau | Renouvelé automatiquement via la connexion ; si aucune connexion n'est enregistrée, exécutez `rdc subscription login` ou `rdc config remote enable` |
| Config came back at an older version | Le serveur a renvoyé une copie plus ancienne que celle déjà vue par cet appareil | Rien n'a changé localement ; réessayez, et signalez-le si cela persiste |
| Cannot remove last member | Verrouillerait le stockage de façon permanente | Ajoutez d'abord un autre membre |
| Stale slot | L'emplacement date d'avant la dernière rotation de clé | Réajoutez l'emplacement (les codes de récupération doivent être régénérés après chaque rotation) |

## Voir aussi

- [Console Web](/fr/docs/web-console), déverrouiller le store dans le navigateur pour exécuter des commandes
- [Proxy et executor](/fr/docs/proxy-and-executor), comment la clé déverrouillée est accordée à un executor
