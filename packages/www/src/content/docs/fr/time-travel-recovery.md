---
title: Récupération du voyage dans le temps
description: "Récupérez des données supprimées il y a des semaines à l'aide d'instantanés btrfs, même après que vos sauvegardes normales sont passées à autre chose."
category: Use Cases
order: 2
language: fr
sourceHash: "4c1fcb1667a89759"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Lorsque d'autres perdent des données pour toujours, vous pouvez voyager dans le temps.**

**Remarque :** Il s’agit d’un **exemple de cas d’utilisation** montrant comment Rediacc gère ce type de problème. Nous sommes une startup. Ce sont des scénarios réalistes pour lesquels le produit a été conçu, pas des études de cas déjà livrées à des clients.

**Scénario de crise :** Un nouvel employé a **accidentellement supprimé** des lignes critiques de votre base de données en direct il y a 3 semaines. Votre système de sauvegarde ne conserve que 2 semaines d’historique. Avec une configuration normale, ces données sont perdues.

## Le problème

Mehmet est un expert système responsable de la base de données d'une grande entreprise d'achats en ligne. Un matin, suite à des plaintes de clients, il remarque que certains enregistrements de commandes passées **ne sont pas visibles** dans le système. L'enquête révèle qu'un employé nouvellement embauché a **accidentellement supprimé** certaines données critiques de la base de données en direct il y a 3 semaines, **se connectant à la base de données en direct au lieu de l'environnement de test**.

**Système de sauvegarde existant :** 
* Les sauvegardes complètes sont effectuées une fois par semaine 
* **Les sauvegardes incrémentielles** sont enregistrées quotidiennement

**Dilemme :** La suppression a eu lieu **avant la date des sauvegardes complètes**, les données perdues ne sont donc pas dans les sauvegardes. Les sauvegardes quotidiennes **enregistrent uniquement les données les plus récentes**, donc **les éléments supprimés ne peuvent pas être récupérés**.

## Impact de la crise

En raison de la perte de données : 
* Les clients **ne peuvent pas traiter les demandes de remboursement** 
* Des incohérences surviennent dans le système de paiement 
* Les plaintes se propagent rapidement sur les réseaux sociaux

**Résultats :** 
* L'équipe de support client est soumise à **une pression intense** 
* La réputation de l'entreprise est **rapidement endommagée** 
* Les efforts de récupération manuelle des données obtiennent **seulement 15 % de réussite**

**Défi supplémentaire :** 
* Pour réduire les coûts de stockage, l'entreprise conserve **uniquement les 2 dernières semaines de sauvegardes** 
* Les données supprimées ne figurent pas dans les **sauvegardes récentes**

## Solution de rediacc

Mehmet propose une solution de type « machine à voyager dans le temps » avec Rediacc :

![Time Travel Recovery](/img/time-travel-recovery.svg)

### 1. **Instantanés** 
* Rediacc prend automatiquement des instantanés du système toutes les heures 
* Ces instantanés couvrent également les instants juste avant la suppression des données

### 2. **Remonter le temps** 
* Mehmet sélectionne la date et l'heure auxquelles la suppression a eu lieu dans l'interface Rediacc 
* Restaure un instantané du système d'il y a 3 semaines vers une nouvelle instance en 1 minute

### 3. **Récupération complète** 
* Les données perdues sont restaurées complètement et systématiquement

## Résultat

* La réputation de l'entreprise a été réparée **en 24 heures** 
* La perte financière a été évitée de **95 %** 
* Rediacc a prouvé que des sauvegardes fréquentes pouvaient être effectuées **sans augmenter les coûts de stockage**
