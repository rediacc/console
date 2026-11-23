---
title: "Réponse aux incidents de sécurité"
description: "Comment Rediacc traite ses propres incidents de sécurité : les avis échelonnés aux clients, les éléments de l'art. 33(3) du GDPR, la voie de notification du CRA et ce que reçoivent les clients."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: fr
sourceHash: "6b9f728f093ecb0c"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Cette page décrit ce qui se passe lorsque Rediacc subit lui-même un incident de sécurité, par exemple une compromission de ses propres systèmes ou une vulnérabilité activement exploitée dans ses produits. Les incidents survenant dans les dépôts d'un client relèvent de ce dernier, qui les instruit et les notifie ; Rediacc fournit pour cela les outils de collecte de preuves. Les signalements de vulnérabilités venant de l'extérieur sont couverts par la [politique de divulgation](/fr/docs/security-disclosure-policy).

## Étapes

Chaque incident a une horloge qui démarre lorsque Rediacc en prend connaissance. Les informations sont communiquées par étapes, car le tableau complet est rarement connu dès le premier jour et l'art. 33(4) du GDPR permet de fournir les informations de manière échelonnée.

| Étape | Échéance | Contenu |
|-------|----------|---------|
| Alerte précoce | sous 24 heures | ce qui est connu à ce stade, et si des actes malveillants sont soupçonnés |
| Notification | sous 72 heures | la nature de l'incident, une évaluation initiale et les mesures prises |
| Rapport final | sous un mois | une description détaillée, la cause racine, et les mesures appliquées et en cours |

## Les éléments de l'art. 33(3)

Chaque étape comporte les quatre éléments énumérés à l'art. 33(3) du GDPR :

1. la nature de la violation, avec les catégories et le nombre approximatif de personnes concernées ainsi que d'enregistrements de données personnelles concernés
2. le nom et les coordonnées du point de contact auprès duquel obtenir davantage d'informations
3. les conséquences probables
4. les mesures prises ou proposées pour remédier à la violation, y compris les mesures visant à en atténuer les éventuelles conséquences négatives

Lorsqu'une valeur n'est pas encore connue, l'étape le signale et indique la date à laquelle elle le sera.

## Ce que reçoivent les clients

Lorsqu'un incident touche une organisation :

- chaque étape est envoyée sous forme d'avis dans le portail du compte et par e-mail, aux propriétaires et administrateurs de l'organisation ainsi qu'à son contact sécurité
- l'avis et l'e-mail sont envoyés quelles que soient les préférences de notification, car il s'agit de communications de sécurité
- un bandeau du portail renvoie vers la page de l'incident, qui présente chaque étape publiée
- chaque étape propose un lot STIX 2.1 contenant les indicateurs de compromission, dans un format lisible par machine que les outils de sécurité peuvent importer

Une organisation non touchée ne reçoit rien. Les propriétaires et administrateurs définissent le contact sécurité de l'organisation dans le portail, afin que le message parvienne à la bonne personne.

## Notifications réglementaires

Rediacc notifie ses propres incidents lorsque la loi l'exige.

- **GDPR.** Lorsque Rediacc agit en tant que sous-traitant, l'avis échelonné informe le responsable du traitement dans les meilleurs délais (art. 33(2)), et c'est ce dernier qui décide de la notification à son autorité de contrôle. Lorsque Rediacc est le responsable du traitement, il notifie l'autorité de contrôle compétente dans un délai de 72 heures dans la mesure du possible (art. 33(1)).
- **Cyber Resilience Act.** Depuis le 11 septembre 2026, l'art. 14 du règlement (UE) 2024/2847 impose au fabricant de notifier une vulnérabilité activement exploitée ou un incident grave affectant la sécurité d'un produit comportant des éléments numériques au CSIRT désigné et à l'ENISA, via la plateforme unique de notification. Les mêmes étapes de 24 heures, 72 heures et de rapport final s'appliquent, et le même dossier d'incident alimente à la fois l'avis aux clients et la déclaration.

## Signaler un incident présumé

Toute personne qui soupçonne un incident affectant Rediacc, y compris un client qui observe un comportement inattendu dans un composant Rediacc, écrit à [security@rediacc.com](mailto:security@rediacc.com). Le signalement d'une vulnérabilité suit la [politique de divulgation](/fr/docs/security-disclosure-policy).
