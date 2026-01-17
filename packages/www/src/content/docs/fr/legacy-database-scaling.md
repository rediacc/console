---
title: Mise à l'échelle de la base de données héritée
description: Faites évoluer les bases de données existantes sans migration en tirant parti de la réplication des données en temps réel et de la distribution des requêtes.
category: Use Cases
order: 3
language: fr
---

> **Votre base de données héritée vous retient. Libérez-vous sans le casser.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** démontrant comment Rediacc peut résoudre ce problème. En tant que startup, ces scénarios représentent des applications potentielles plutôt que des études de cas réalisées.

**Scénario de crise :** Malgré la mise à l'échelle des serveurs 10 fois avec Kubernetes, les performances ne se sont améliorées que 2 fois. Les clients se plaignaient de la lenteur des requêtes, de l'augmentation des coûts sans résultats satisfaisants et de la réputation menacée.

## Le problème

Les services de l'entreprise dans l'environnement cloud avaient **du mal à répondre**. En guise de solution, l'équipe logicielle : 
* Réalisation d'une **mise à l'échelle horizontale avec Kubernetes** et **augmentation du nombre de serveurs par 10** 
* Cependant, les performances se sont améliorées **seulement 2 fois**

**Détection des goulots d'étranglement :** 
* Il a été entendu que la source du problème était une **base de données héritée qui ne peut pas être mise à l'échelle** 
* La base de données ne pouvait pas fonctionner de manière distribuée comme dans les architectures modernes

**Dilemme :** 
* La migration vers une base de données moderne **pourrait prendre des années** → Cela nécessitait une réécriture du code, une migration des données et des processus de test 
* Les coûts et les pertes de temps étaient inacceptables

## Impact de la crise

* Les clients se plaignent de **la lenteur des requêtes**. 
* Les coûts des serveurs augmentent, mais **les performances ne sont pas satisfaisantes** 
* Le risque de **perte de réputation** augmente sur un marché concurrentiel

## Solution de rediacc

L'ingénieur système Yüksel, utilisant la fonctionnalité de sauvegarde croisée de Rediacc :

![Mise à l'échelle de la base de données héritée](/img/legacy-scaling.svg)

### 1. **Réplication des données en temps réel** 
* Les modifications apportées à l'ancienne base de données ont été transférées vers d'autres serveurs **à intervalles de 10 à 15 minutes** 
* **Seules les données modifiées** ont été synchronisées → **Consommation de bande passante réduite de 95 %**

### 2. **Distribution des requêtes** 
* Les requêtes de lecture ont été **distribuées sur plusieurs machines** 
* Les opérations d'écriture ont été conservées **dans la base de données principale** pour assurer la cohérence

### 3. **Mise à l'échelle gratuite** 
* L'ancien système a été pris en charge avec des serveurs supplémentaires **sans être modifié** 
* Pas besoin d'acquisition de nouveau matériel → **Les serveurs cloud ont été loués à l'heure** pour optimiser les coûts

## Résultat

**Augmentation des performances :** 
* Les temps de requête ont été réduits de **55 secondes à 7 secondes** 
* Capacité du système augmentée **8 fois**

**Contrôle des coûts :** 
* Économies liées à la réécriture du système existant → **Les ressources financières ont été préservées**

**Gain de temps :** 
* La solution a été mise en œuvre **dans un délai de 3 semaines** 
* Les plaintes des clients ont été résolues à **99,99 % (en fonction du taux de mise à jour du total des données entre les instantanés)**