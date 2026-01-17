---
title: Mise à l'échelle dynamique des ressources
description: Créez une architecture cloud avec une flexibilité illimitée pour la formation en IA et les charges de travail dynamiques.
category: Use Cases
order: 1
language: fr
---

> **Votre architecture cloud est-elle rigide ? Construisez avec une flexibilité illimitée.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** démontrant comment Rediacc peut résoudre ce problème. En tant que startup, ces scénarios représentent des applications potentielles plutôt que des études de cas réalisées.

**Scénario de crise :** Les délais de formation de l'IA **ont été prolongés de 2 à 3 fois**, entraînant des retards dans le projet. Les ingénieurs ont subi une perte de productivité importante en attendant les ressources, menaçant l'avantage concurrentiel de l'entreprise.

## Le problème

Les ingénieurs logiciels de l'entreprise rencontrent des problèmes de performances avec les serveurs **sur site** utilisés pour la **formation des modèles d'IA** : 
* Pendant les **heures de bureau** (de 8 h 00 à 17 h 00), les requêtes du serveur atteignent 99 % de leur capacité. 
* Une formation nécessitant une puissance de traitement élevée rend le matériel **insuffisant**

**Rechercher une solution :** 
* Le coût de la mise à niveau du serveur n'est **pas considéré comme approprié** en raison de **6 à 7 heures d'utilisation quotidienne** 
* Bien que la migration vers le cloud soit envisagée, le **coût de transfert de données** et les **difficultés de synchronisation** constituent des obstacles.

## Impact de la crise

* Les temps de formation de l'IA **s'étendent de 2 à 3 fois**, les projets sont retardés 
* Les ingénieurs subissent une **perte de productivité** en attendant des ressources 
* L'entreprise court le risque de **perdre progressivement son avantage concurrentiel**

## Solution de rediacc

L'ingénieur système Yüksel développe **un modèle hybride** avec Rediacc :

![Mise à l'échelle hybride du cloud](/img/hybrid-cloud-scaling.svg)

### 1. **Migration instantanée vers le cloud** 
* Pendant les heures de bureau, les services sur site sont clonés dans le cloud **avec toutes les données et configurations** 
* 100 To de données sont synchronisés en 9 minutes en transférant **uniquement les pièces modifiées** grâce à Rediacc

### 2. **Mise à l'échelle dynamique** 
* Les serveurs dans l'environnement cloud sont loués **autant que nécessaire pour la formation en IA** 
* La puissance de traitement peut être **augmentée 10 fois** en fonction de la demande

### 3. **Synchronisation de nuit** 
* À la fin de la journée de travail, **toutes les modifications apportées au cloud** sont **automatiquement transférées** vers l'environnement sur site. 
* Les ingénieurs travaillant la nuit poursuivent leurs opérations avec **des données à jour**

## Résultat

**Avantage de coût :** 
* En **louant des ressources cloud à l'heure**, le coût mensuel a été réduit de **60 %** 
* La nécessité de mettre à niveau les serveurs sur site **a été éliminée**

**Augmentation des performances :** 
* Les temps de formation de l'IA ont été réduits de **8 heures à 1,5 heure** 
* La productivité des ingénieurs a augmenté de **40 %**

**Travail flexible :** 
* **La cohérence des données** entre les environnements cloud et sur site a été assurée de manière transparente 
* Les équipes de nuit **avaient un accès instantané à des données à jour**