---
title: Stratégie de sauvegarde croisée
description: Votre sauvegarde échoue au moment même où sa machine tombe. Rediacc réplique les instantanés sur une machine distincte afin qu'une seule défaillance disque ne vous fasse perdre l'essentiel.
category: Use Cases
order: 5
language: fr
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **En cas de catastrophe, vos données survivront-elles ? Avec Rediacc, c'est toujours le cas.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** montrant comment Rediacc peut résoudre ce problème. Ces scénarios représentent des applications potentielles, pas des études de cas finalisées.

**Scénario de crise :** Un appel client révèle la panne : **défaillance disque**. La dernière sauvegarde du serveur distant remontait à **3 semaines**. Des semaines de données, perdues.

## Le problème

L'entreprise prend conscience des risques liés à la sauvegarde des données **uniquement sur la même machine** : 
* Pannes matérielles 
* Cyberattaques 
* Catastrophes physiques comme la guerre, les tremblements de terre, les incendies, les inondations 
* Protection insuffisante contre la perte de données

**Rechercher une solution :** 
* Il est décidé de sauvegarder 20 To de données sur **un serveur distant** 
* Cependant, avec les méthodes traditionnelles, cette sauvegarde prend **2 semaines** et occupe **99,99 % (en fonction du taux de mise à jour des données totales entre les instantanés)** de la bande passante.

## Impact de la crise

Après un appel client : 
* On remarque que **les services ne fonctionnent pas** 
* Une **panne de disque** est détectée 
* Lors de la vérification du serveur de sauvegarde distant, il est entendu que **la dernière sauvegarde a été effectuée il y a 3 semaines**

**Résultats :** 
* Les tentatives de récupération manuelle du disque **échouent** 
* En raison de 3 semaines de perte de données, **les contrats clients sont annulés** 
* La **réputation de l'entreprise est sérieusement endommagée**

## Solution Rediacc

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **Première sauvegarde** 
* La première fois que 20 To de données sont transférés vers un serveur distant, cela prend 2 semaines

### 2. **Sauvegardes croisées horaires** 
* Toutes les heures, une perception de sauvegarde complète est créée, mais **seules les données modifiées** sont transférées

### 3. **Préparation aux scénarios de catastrophe** 
* Les données peuvent être sauvegardées même sur des serveurs **intercontinentaux** 
* Même si la machine principale tombe en panne, les données datant d'il y a à peine 1 heure sont **activées en quelques minutes**

## Résultat

**Gain de temps :** 
* Le temps de sauvegarde a été réduit de **2 semaines à une moyenne de 4 minutes** 
* Le risque de perte de données a été réduit à **1 heure**

**Optimisation des coûts :** 
* La consommation de bande passante a diminué de **98 %**

**Continuité ininterrompue des activités :** 
* Lorsque le serveur principal tombait en panne, la sauvegarde à distance était activée en **7 minutes**
