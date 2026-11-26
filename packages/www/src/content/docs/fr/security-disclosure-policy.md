---
title: "Politique de divulgation des vulnérabilités"
description: "Comment signaler une faille de sécurité chez Rediacc : périmètre, protection juridique, mode de signalement et délais de réponse attendus."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: fr
sourceHash: "612e816f7a8be282"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

Rediacc accueille volontiers les signalements de vulnérabilités de sécurité touchant ses produits et services. Cette politique précise ce qui entre dans le périmètre, comment signaler une faille et ce que l'auteur du signalement peut attendre en retour. Le fichier de contact lisible par machine se trouve à l'adresse [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Périmètre

Dans le périmètre :

- la CLI `rdc` et l'orchestrateur de machines `renet`
- le serveur de comptes, son portail web et son API
- les sites web de Rediacc sous `rediacc.com` et `rediacc.cloud`
- les artefacts de publication : binaires, images de conteneur et programmes d'installation

Hors périmètre :

- les constats qui exigent un accès physique à une machine, ou un poste compromis que l'auteur du signalement contrôle déjà
- le déni de service par saturation, le spam et l'ingénierie sociale visant le personnel
- les rapports issus de scanners automatiques sans impact démontré
- les vulnérabilités de logiciels tiers que Rediacc se contente de redistribuer sans modification ; elles relèvent du projet amont, et une copie adressée à Rediacc est la bienvenue

## Comment signaler

Envoyez le signalement à [security@rediacc.com](mailto:security@rediacc.com). Indiquez :

- le produit concerné et sa version, ou l'URL
- les étapes de reproduction, ou une preuve de concept
- l'impact estimé par l'auteur du signalement
- si le problème est déjà public ou exploité
- une adresse de contact pour le suivi, et si une mention de crédit est souhaitée

Les signalements en anglais sont préférés. Les données réelles de clients n'ont pas leur place dans le signalement : une preuve minimale de l'accès suffit.

## Protection juridique (safe harbour)

Rediacc n'engagera ni ne soutiendra aucune action en justice contre l'auteur d'un signalement qui agit de bonne foi dans le cadre de cette politique, c'est-à-dire qui :

- ne teste que ses propres comptes, machines et données, ou des ressources appartenant à Rediacc
- s'arrête dès que le problème est démontré, et ne lit, ne modifie, ne copie ni ne supprime aucune donnée appartenant à des tiers
- ne dégrade pas le service pour les autres utilisateurs
- signale rapidement et garde les détails confidentiels jusqu'à la date de divulgation coordonnée indiquée ci-dessous

Un travail qui reste dans ces limites est considéré comme autorisé, et Rediacc le confirmera à tout tiers qui le demande.

## Délais de réponse

| Étape | Objectif |
|-------|----------|
| Accusé de réception du signalement | 2 jours ouvrés |
| Première évaluation, avec la gravité | 5 jours ouvrés |
| Points d'avancement tant que le dossier est ouvert | au moins tous les 14 jours |
| Correctif ou mesure d'atténuation pour un problème critique | 14 jours à compter de l'évaluation |
| Correctif ou mesure d'atténuation pour les autres problèmes confirmés | 90 jours à compter de l'évaluation |

Ces délais sont des objectifs : un signalement qui demande plus de temps reçoit une explication et une nouvelle date.

## Divulgation coordonnée

Les détails sont publiés en même temps que le correctif, en principe dans les 90 jours suivant la première évaluation. L'auteur qui souhaite une publication plus tôt ou plus tard indique la date dans son signalement, et les deux parties s'accordent sur une date. Une vulnérabilité déjà exploitée dans la nature est traitée comme un incident, comme décrit sur la [page de réponse aux incidents](/fr/docs/security-incident-response).

## Crédit

Un signalement confirmé est cité dans les notes de version ou l'avis de sécurité, sous le nom ou le pseudonyme choisi par son auteur. Rediacc ne propose pas de programme de primes rémunéré.

## Voir aussi

- [Réponse aux incidents](/fr/docs/security-incident-response)
- [Sécurité du compte et API](/fr/docs/account-security)
