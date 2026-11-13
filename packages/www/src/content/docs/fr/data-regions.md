---
title: "Régions de données"
description: "Où vos données sont stockées et comment fonctionne la résidence des données par région."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: fr
sourceHash: "9efeb1e2b1f9c8db"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Lorsque vous créez un compte Rediacc, vous choisissez une région de données. Toutes vos données restent dans cette région. Ce choix est permanent et ne peut pas être modifié après l'inscription. Aucune migration n'est possible. Choisissez votre région en fonction de l'endroit où vos données doivent résider légalement, et non en fonction de l'emplacement actuel de vos serveurs.

## Régions disponibles

| Région | Emplacement | Domaine |
|---|---|---|
| **Europe (EU)** | Union européenne | `eu.rediacc.cloud` |
| **États-Unis (US)** | Est de l'Amérique du Nord | `us.rediacc.cloud` |
| **Asie-Pacifique** | Asie-Pacifique | `asia.rediacc.cloud` |

La colonne Emplacement indique une région Cloudflare, pas une ville de centre de données. Cloudflare ne promet aucune ville.

Le produit fonctionne sur ces domaines `rediacc.cloud`. Toute la documentation et le site marketing se trouvent sur `www.rediacc.com`, qui vous dirige vers la bonne région depuis son sélecteur de région.

À l'inscription, le sélecteur propose une région d'après votre localisation, que vous confirmez ou modifiez. À la connexion, il vous redirige vers votre région après un court compte à rebours que vous pouvez annuler ou modifier. Si votre entreprise dispose de son propre déploiement, l'option « Client Enterprise ? » vous y conduit à partir de votre e-mail professionnel. Seul le domaine est envoyé pour trouver la région ; l'e-mail sert uniquement à préremplir la page de connexion.

## Ce qui reste dans votre région

Ces types de données sont stockés et traités dans la région que vous avez choisie, sauf que l'e-mail transactionnel pour l'Asie-Pacifique passe par le point de terminaison de l'UE (voir plus bas l'infrastructure régionale pour ce qui est garanti) :

- **Données de compte** : email, nom, organisation, appartenances aux équipes
- **Enregistrements de facturation et d'abonnement** : plan, activations, émissions de licences
- **Blobs de configuration chiffrés** : chiffrement zéro-connaissance côté client. Le serveur ne peut pas les déchiffrer.
- **Emails transactionnels** : réinitialisation de mot de passe, liens magiques, notifications. Envoyés depuis un point de terminaison email régional.

## Ce qui est global

Ces éléments ne sont pas spécifiques à une région :

- **Artefacts de publication de la CLI** : binaires publics hébergés sur un CDN mondial
- **Site web marketing et documentation** : `www.rediacc.com`, servi mondialement depuis des emplacements edge
- **Traitement des paiements Stripe** : géré par la propre infrastructure de Stripe dans le cadre de leur accord de traitement des données

## Infrastructure régionale

| Composant | EU | US | Asie |
|---|---|---|---|
| Base de données (D1) | Indication Europe de l'Est (EEUR) | Indication Est de l'Amérique du Nord (ENAM) | Indication Asie-Pacifique (APAC) |
| Stockage de config (R2) | Juridiction de l'UE (garantie) | Aucune juridiction (au mieux) | Aucune juridiction (au mieux) |
| Email (SES) | Francfort (eu-central-1) | Virginie (us-east-1) | Francfort (eu-central-1) |

Seul le stockage de configuration de l'EU est soumis à une juridiction garantie : Cloudflare maintient dans l'UE les objets R2 placés sous la juridiction de l'UE. Le placement de la base D1 et le stockage US et Asie-Pacifique reposent sur des indications d'emplacement, appliquées au mieux. Cloudflare ne garantit pas qu'ils s'exécutent dans la région indiquée.

Chaque région fonctionne avec une infrastructure indépendante. Il n'y a pas de requêtes inter-régions ni de flux de données entre les régions.

## Garanties pour la région EU

Si vous êtes soumis aux exigences de résidence des données européennes, la région EU offre une garantie ferme et un placement au mieux :

- **Base de données D1** : placée avec l'indication d'emplacement EEUR (Europe de l'Est), au mieux et sans garantie
- **Stockage de configuration R2** : soumis à la juridiction de l'UE, que Cloudflare garantit (une restriction ferme, pas seulement une indication d'emplacement)
- **Email** : envoyé depuis Francfort (eu-central-1)

Pour la cartographie RGPD détaillée, consultez [Conformité RGPD](/fr/docs/legal-gdpr).

## Chiffrement zéro-connaissance

Les blobs de configuration stockés dans R2 sont chiffrés côté client avant le téléchargement via un échange de clés X25519 et AES-256-GCM. Le serveur ne détient que le texte chiffré. Ni Rediacc ni aucun fournisseur d'infrastructure ne peut lire vos données de configuration.

Les clés sont dérivées d'une clé d'accès avec extension PRF. Le serveur stocke un secret côté serveur qui participe à la dérivation des clés, mais ni la clé d'accès seule ni le secret serveur seul ne peuvent déchiffrer les données.

Pour plus de détails sur l'architecture de chiffrement, consultez [Stockage de configuration](/fr/docs/config-storage).

## Comment choisir

- **Choisissez la région la plus proche de vous** pour la latence la plus faible.
- **Choisissez la région requise par votre organisation** pour la conformité. Si votre entreprise exige la résidence des données EU, choisissez EU.
- **Le choix est permanent.** Vous ne pouvez pas transférer votre compte vers une autre région après l'inscription.

## Pour les responsables de la conformité

Propriétés techniques de l'architecture régionale :

- **Bases de données séparées par région** : chaque région possède sa propre base de données Cloudflare D1. Pas de requêtes inter-régions.
- **Stockage séparé par région** : chaque région possède son propre bucket R2. Seul le bucket EU est soumis à une juridiction ; US et Asie-Pacifique sont placés au mieux.
- **Livraison des emails via AWS SES** : les emails transactionnels sont envoyés via AWS SES. L'EU et les États-Unis utilisent des points de terminaison régionaux dédiés ; l'Asie-Pacifique achemine les messages via le point de terminaison EU (eu-central-1).
- **Un utilisateur, une région** : un compte utilisateur existe dans exactement une région. Il ne peut pas couvrir plusieurs régions.
- **Isolation des webhooks** : les événements webhook Stripe sont reçus par tous les workers régionaux mais traités uniquement par la région qui possède l'enregistrement client.
- **Chiffrement zéro-connaissance de la configuration** : le serveur ne peut pas lire les données de configuration. Les clés de chiffrement ne quittent jamais l'appareil client.

Pour une vue d'ensemble de la conformité à la souveraineté des données, consultez [Souveraineté des données](/fr/docs/legal-data-sovereignty).
