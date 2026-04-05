---
title: "Conformité CCPA"
description: "Comment le modèle auto-hébergé de Rediacc répond aux exigences du California Consumer Privacy Act pour la protection des données des consommateurs."
category: "Legal"
order: 4
language: fr
sourceHash: "50081a040deb3183"
---

Le California Consumer Privacy Act (CCPA) est une loi de l'État de Californie qui accorde aux consommateurs californiens des droits sur leurs informations personnelles, notamment le droit de savoir quelles données sont collectées, le droit de les supprimer et le droit de refuser leur vente.

Référence : [Procureur général de Californie, CCPA](https://oag.ca.gov/privacy/ccpa)

## Correspondance des droits des consommateurs

Le CCPA se concentre sur les droits des consommateurs liés aux informations personnelles. Rediacc est un outil auto-hébergé déployé sur votre infrastructure, et non un service tiers qui collecte ou vend des données de consommateurs. Le tableau ci-dessous montre comment Rediacc soutient la conformité de votre organisation au CCPA.

| Droit CCPA | Exigence | Capacité Rediacc |
|-----------|----------|-----------------|
| Droit de savoir (1798.100) | Divulguer les catégories et finalités des données collectées | Les journaux d'audit tracent toutes les opérations de données. Auto-hébergé : votre organisation conserve une visibilité complète sur les données présentes dans chaque dépôt. |
| Droit de suppression (1798.105) | Supprimer les informations personnelles du consommateur sur demande | `rdc repo destroy` efface cryptographiquement le volume chiffré LUKS. La suppression d'un fork retire entièrement les copies clonées. |
| Droit de refus (1798.120) | Ne pas vendre ni partager les informations personnelles | Architecture auto-hébergée : aucun transfert de données vers Rediacc ou un tiers. Les données restent sur vos serveurs. La synchronisation du magasin de configuration utilise le chiffrement à connaissance nulle. Même le serveur de synchronisation ne peut pas lire les données. |
| Sécurité des données (1798.150) | Mettre en place des mesures de sécurité raisonnables | Chiffrement LUKS2 AES-256, isolation réseau, accès SSH uniquement, Docker daemons isolés, journalisation d'audit. Le magasin de configuration utilise un chiffrement à triple couche avec dérivation de clé fractionnée et jetons rotatifs à usage unique. |

## Statut de fournisseur de services

Rediacc en tant que logiciel n'accède pas aux données des consommateurs, ne les traite pas et ne les stocke pas. Votre équipe informatique exploite Rediacc sur votre propre infrastructure. Aucune donnée ne transite vers l'entreprise Rediacc. Les implications :

- Rediacc n'est pas un "fournisseur de services" au sens du CCPA (il ne traite pas de données en votre nom)
- Aucun accord de traitement des données n'est requis avec Rediacc pour le produit auto-hébergé
- Vos obligations CCPA se situent entre votre organisation et vos consommateurs

## Inventaire des données

Chaque dépôt Rediacc est une unité de données discrète et chiffrée avec un GUID unique. Vous pouvez inventorier précisément quelles données existent et où :

- `rdc machine query <machine> --repositories` liste tous les dépôts sur une machine avec leur taille et leur état de montage
- Chaque dépôt est isolé au niveau du système de fichiers, du réseau et des conteneurs
- Les relations de fork sont tracées, vous permettant d'identifier toutes les copies d'un jeu de données

Le CCPA exige une cartographie des données. Le modèle de dépôts de Rediacc la fournit : un GUID par jeu de données, énumérable par machine, avec un suivi de la lignée des forks.
