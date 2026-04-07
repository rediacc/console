---
title: "Régions de données"
description: "Où vos données sont stockées et comment fonctionne la résidence des données par région."
category: "Concepts"
order: 3
language: fr
sourceHash: "613595b3941c6186"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Lorsque vous créez un compte Rediacc, vous choisissez une région de données. Toutes vos données restent dans cette région. Ce choix est permanent et ne peut pas être modifié après l'inscription.

## Régions disponibles

| Région | Emplacement | Domaine |
|---|---|---|
| **Europe (EU)** | Francfort, Allemagne | `eu.rediacc.com` |
| **États-Unis (US)** | Virginie, États-Unis | `us.rediacc.com` |
| **Asie-Pacifique** | Tokyo, Japon | `asia.rediacc.com` |

Votre région est détectée automatiquement d'après votre fuseau horaire lors de l'inscription. Vous pouvez modifier la suggestion dans le sélecteur de région.

## Ce qui reste dans votre région

Ces types de données sont stockés et traités exclusivement dans votre région choisie :

- **Données de compte** : email, nom, organisation, appartenances aux équipes
- **Enregistrements de facturation et d'abonnement** : plan, activations, émissions de licences
- **Blobs de configuration chiffrés** : chiffrement zéro-connaissance côté client. Le serveur ne peut pas les déchiffrer.
- **Emails transactionnels** : réinitialisation de mot de passe, liens magiques, notifications. Envoyés depuis un point de terminaison email régional.

## Ce qui est global

Ces éléments ne sont pas spécifiques à une région :

- **Artefacts de publication de la CLI** : binaires publics hébergés sur un CDN mondial
- **Site web marketing** : servi mondialement depuis des emplacements edge
- **Traitement des paiements Stripe** : géré par la propre infrastructure de Stripe dans le cadre de leur accord de traitement des données

## Infrastructure régionale

| Composant | EU | US | Asie |
|---|---|---|---|
| Base de données (D1) | Europe de l'Est (EEUR) | Amérique du Nord Est (ENAM) | Asie-Pacifique (APAC) |
| Stockage de config (R2) | Juridiction EU | US | Asie-Pacifique |
| Email (SES) | Francfort (eu-central-1) | Virginie (us-east-1) | Tokyo (ap-northeast-1) |

Chaque région fonctionne avec une infrastructure indépendante. Il n'y a pas de requêtes inter-régions ni de flux de données entre les régions.

## Garanties pour la région EU

La région EU offre des garanties supplémentaires pour les organisations soumises à des exigences de résidence des données européennes :

- **Base de données D1** : fonctionne en Europe de l'Est (indicateur de localisation EEUR)
- **Stockage de config R2** : utilise l'application juridictionnelle EU (garantie contractuelle, pas seulement un indicateur de localisation)
- **Email** : envoyé depuis Francfort (eu-central-1)
- **Décision d'adéquation mutuelle UE-Japon (2019)** : permet des flux de données conformes pour l'infrastructure de la région Asie

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
- **Stockage séparé par région** : chaque région possède son propre bucket R2. L'EU utilise l'application juridictionnelle.
- **Points de terminaison email séparés par région** : les emails transactionnels sont envoyés depuis des points de terminaison AWS SES régionaux.
- **Un utilisateur, une région** : un compte utilisateur existe dans exactement une région. Il ne peut pas couvrir plusieurs régions.
- **Isolation des webhooks** : les événements webhook Stripe sont reçus par tous les workers régionaux mais traités uniquement par la région qui possède l'enregistrement client.
- **Chiffrement zéro-connaissance de la configuration** : le serveur ne peut pas lire les données de configuration. Les clés de chiffrement ne quittent jamais l'appareil client.

Pour une vue d'ensemble de la conformité à la souveraineté des données, consultez [Souveraineté des données](/fr/docs/legal-data-sovereignty).
