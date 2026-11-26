---
title: "Rapports d'incident : par étapes, signés et vérifiables"
description: "Générez l'alerte précoce, la notification et le rapport final d'un incident survenu dans un dépôt client au format JSON, STIX 2.1 ou PDF. Chaque rapport est signé en Ed25519, porte un lien de vérification par QR code et fait correspondre ses champs à NIS2, au format 2025/302 et à l'art. 33, par. 3 du RGPD."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: fr
sourceHash: "d7f6e084c5c1d0d9"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Rapports d'incident

Un incident déclaré ([réponse aux incidents](/fr/docs/incident-response)) produit trois rapports par étapes que le client dépose auprès d'une autorité de contrôle. Rediacc génère les documents à partir des preuves. Savoir si un incident est significatif ou à notifier reste l'appréciation du client, et chaque rapport le précise.

## Étapes

Chaque étape ajoute les sections listées ci-dessous et reprend celles de l'étape précédente : une section qu'aucune étape ne demande est omise plutôt que laissée vide.

| Étape | Échéance | Ajoute |
|---|---|---|
| Alerte précoce | 24 heures après la prise de connaissance | En-tête, chronologie, indicateurs de compromission, impact malveillant présumé et transfrontalier |
| Notification | 72 heures après la prise de connaissance | Évaluation initiale, impact sur les données (catégories, nombres approximatifs, États membres) et techniques ATT&CK |
| Final | Un mois calendaire après la notification | Cause racine et mesures d'atténuation |

Le rapport final fait suite à une notification, la notification est donc générée en premier.

Chaque fait d'un rapport indique comment il est connu : observé dans les preuves, saisi par le client ou déduit. Un fait déduit porte un niveau de confiance et la raison du détecteur. L'évaluation, les catégories de données, les États membres, la cause présumée, les actions menées, le point de contact et les techniques sont des éléments que le client saisit sur la page de l'incident avant la génération.

## Formats

| Format | Usage |
|---|---|
| JSON | La forme canonique et vérifiable |
| STIX 2.1 | Un lot d'indicateurs pour les outils de renseignement sur les menaces |
| PDF | Un document lisible avec Noto Sans intégrée (latin, cyrillique et turc) ou Noto Sans Arabic ; les rapports en japonais, coréen et chinois sont refusés tant que leurs polices ne sont pas figées. Avec l'avertissement, un QR code et le hash du rapport en pied de chaque page |

Depuis la page de l'incident, chaque étape dispose d'un bouton de téléchargement par format. En ligne de commande :

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

Le format par défaut est JSON. `--format` ne s'applique qu'avec `--stage`. Le fichier est écrit sous son identifiant de rapport.

## Signature et vérification

Chaque rapport est signé avec une clé de rapport Ed25519, et l'identifiant, l'étape et le hash du rapport figurent sur un registre public. La signature couvre le contenu canonique du rapport, toute modification après la signature est donc détectée.

Un rapport se vérifie à trois endroits :

- La page de vérification à `/account/verify/report/<id>`, qu'ouvre le QR code du PDF. La vérification s'exécute dans le navigateur contre la clé de rapport publiée, et rien n'est envoyé. Un fichier JSON est entièrement vérifié. Un PDF ne peut pas être re-haché dans le navigateur : la page confirme donc que le PDF porte le hash du rapport et renvoie au fichier JSON pour une vérification complète.
- La ligne de commande, pour un rapport JSON :

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

La commande se termine avec le code 1 quand le contenu ou la signature ne correspondent pas. Un PDF se vérifie via le rapport JSON dont il est issu.

- Le cachet de preuves à l'intérieur du rapport, qui consigne le résultat de Verify evidence pour la fenêtre : qui a vérifié, avec quelle version et quand.

## Table de correspondance des champs

Chaque champ du rapport correspond aux régimes sous lesquels le client déclare, afin que le contenu puisse être repris sans ressaisie. La table couvre trois régimes : NIS2 art. 23, par. 4, le format de notification d'incident du règlement d'exécution (UE) 2025/302 et le RGPD art. 33, par. 3. Exemples :

| Champ du rapport | NIS2 | RGPD |
|---|---|---|
| Moment de la prise de connaissance | Art. 23(4)(a) | Art. 33(1) |
| Chronologie | Art. 23(4)(d) | Art. 33(3)(a) |
| Point de contact | Art. 23(4) | Art. 33(3)(b) |

Un champ sans équivalent dans un régime en explique la raison au lieu d'être omis. La notification de l'art. 33, par. 3 du RGPD n'a par exemple ni numéro de référence ni heure de clôture.

## Ce qu'un rapport n'affirme pas

Deux déclarations sont imprimées à chaque étape :

- Les enregistrements de flux prouvent le volume et la destination, pas le contenu.
- Savoir si l'incident est significatif ou à notifier relève de l'appréciation du client.

Rediacc ne dépose rien auprès d'une autorité de contrôle au nom du client.
