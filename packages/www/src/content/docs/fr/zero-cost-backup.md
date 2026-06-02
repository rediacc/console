---
title: "Environnements de développement similaires à la production en quelques minutes"
description: "Réduisez la configuration de l'environnement de développement de quelques jours à quelques minutes grâce à la déduplication au niveau des blocs."
category: Use Cases
order: 7
language: fr
sourceHash: "2aa115fc621f5258"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Réduisez la configuration de l'environnement de quelques jours à quelques minutes grâce à l'architecture de stockage avec déduplication intelligente.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** montrant comment Rediacc accélère le travail de développement. Nous sommes une startup sans clients payants pour l'instant ; traitez donc ceci comme un scénario pour lequel nous avons conçu le produit, et non comme une étude de cas aboutie.

## Le problème

Mehmet gère le DevOps dans une entreprise de commerce électronique. Son équipe a besoin d'**environnements de type production** pour les tests, la préparation et le développement. Voici pourquoi :

**Là où l'ancienne approche échoue :**
* La configuration d'environnements de type production prend **heures ou jours** 
* Les développeurs attendent le provisionnement de l'infrastructure pour terminer les tests 
* Les incohérences de l'environnement entraînent des problèmes de « fonctionne sur ma machine »

Les cycles de développement traînaient en longueur car la création d'un nouvel environnement prenait des jours. Ce goulot d'étranglement :

* Ralentissement significatif de la **vitesse de développement** 
* Création de dépendances et de temps d'attente dans le pipeline de développement

## Impact de la crise

* Les coûts de stockage sont devenus **insoutenables** pour le budget informatique 
* Les fenêtres de sauvegarde ont dépassé le temps de maintenance disponible 
* Performances du système dégradées lors des opérations de sauvegarde 
* Risque de perte de données accru en raison de sauvegardes incomplètes

## Solution de rediacc

Mehmet a découvert Rediacc. Avec cet outil :

![Diagramme de sauvegarde](/img/backup-optimization.svg)

### Technologie de sauvegarde intelligente 
* **Des sauvegardes complètes semblent avoir été effectuées**, mais seules les **données modifiées** sont physiquement stockées 
* Par exemple, s'il y a des **modifications quotidiennes moyennes de 100 Go** dans une base de données de 10 To, le système **enregistre uniquement ces 100 Go**. 
* Les sauvegardes fonctionnent **de manière complète et transparente pendant la restauration**, même si elles sont stockées sous forme de fichier unique

### Avantages clés

**1. Économies de coûts** 
* Même avec **100 Go** de modifications quotidiennes dans une base de données de 10 To, le coût de stockage mensuel est limité à **~3 To** (c'était **~300 To** avec l'ancien système)

**2. Compatible avec toutes les technologies**
* Rediacc ne se limite pas à SQL Server. Il fonctionne de manière compatible avec **MySQL, PostgreSQL, MongoDB** et toutes les autres bases de données 
* Pas besoin de **savoir-faire séparé** pour différents systèmes

**3. Cycles plus rapides, moins de matériel**
* Le temps de sauvegarde est réduit de **heures à minutes** 
* La charge sur les ressources disque et réseau diminue de 99,99 % (en fonction du taux de mise à jour du total des données entre les instantanés)

## Résultat

Avec Rediacc, l'équipe :
* Réduction des coûts de stockage de **99,99 % (en fonction du taux de mise à jour du total des données entre les instantanés)** 
* Processus de sauvegarde et de restauration standardisés 
* A répondu à tous ses besoins avec **une solution unique** pour différents systèmes de bases de données
