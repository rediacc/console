---
title: Mises à niveau sans risque
description: Testez les mises à niveau des bases de données sans risque grâce au clonage instantané et aux instantanés horaires.
category: Use Cases
order: 4
language: fr
---

> **Testez tout. Ne risquez rien. Mettez à niveau en toute confiance.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** démontrant comment Rediacc peut résoudre ce problème. En tant que startup, ces scénarios représentent des applications potentielles plutôt que des études de cas réalisées.

**Scénario de crise :** lors d'une mise à niveau de la base de données, une **erreur inattendue** s'est produite et a empêché de revenir à l'ancienne version ou de passer à la nouvelle. Les clients ne pouvaient pas accéder aux systèmes et plus de 5 000 employés ne pouvaient pas travailler.

## Le problème

Mehmet est un administrateur système expérimenté qui gère des bases de données à grande échelle. Il décide de **mettre à niveau une base de données PostgreSQL de 100 To de la version 13 à la version 14**. Son projet :

1. **Effectuer une sauvegarde** → Cependant, la sauvegarde prend **plusieurs jours** en raison de la taille des données 
2. **Effectuer la mise à niveau le week-end** → Les départements sont informés d'une panne le **samedi de 01h00 à 05h00**

## Impact de la crise

* Une **erreur inattendue** se produit lors de la mise à niveau 
* La base de données **ne peut ni revenir à l'ancienne version ni passer à la nouvelle version** 
* Même les équipes d'assistance externes ne peuvent pas résoudre le problème

**Impacts :** 
* Les clients **ne peuvent pas accéder aux systèmes de paiement et de commande** 
* Les employés de l'entreprise (**5 000+ personnes**) ne peuvent pas travailler 
* **La perte de réputation** et l'augmentation des plaintes commencent

**Solution temporaire :** 
* La dernière sauvegarde est chargée sur **un nouveau serveur** → **Le coût du matériel double** 
* Les données du jeudi et du vendredi sont **uniquement dans l'environnement en direct**, ce qui entraîne une perte de données 
* **Deux bases de données avec des versions différentes** sont créées → Augmentation des incohérences

## Solution de rediacc

Mehmet résout fondamentalement le problème avec Rediacc :

### 1. **Clonage instantané** 
* Un **clone de la base de données de 100 To est créé en quelques secondes** 
* Les tests de mise à niveau sont effectués **sans affecter le système live**

### 2. **Instantanés horaires** 
* Il est déterminé **quelle étape a échoué depuis quand** au cours du processus de mise à niveau 
* Les opérations problématiques sont **identifiées à l'avance** et corrigées

### 3. **Mise à niveau transparente** 
* Si la mise à niveau échoue, **l'environnement live n'est pas affecté** 
* Si la mise à niveau réussit, le nouvel environnement live devient le dernier clone

## Résultat

**Économies de temps et d'argent :** 
* Le temps de sauvegarde a été réduit de **7 jours à 10 secondes**

**Mise à niveau sans risque :** 
* Des erreurs ont été détectées à l'avance dans l'environnement de test → **Aucun problème dans le système live**

**Zéro temps d'arrêt :** 
* Les clients et les employés **n'ont ressenti aucune perturbation**