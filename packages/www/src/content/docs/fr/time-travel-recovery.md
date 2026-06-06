---
title: Récupération par voyage dans le temps
description: "Récupérez des données supprimées il y a des semaines à l'aide d'instantanés btrfs, même après que vos sauvegardes normales les aient dépassées."
category: Use Cases
order: 2
language: fr
sourceHash: "e55d51b8df91b20f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Lorsque d'autres perdent des données pour toujours, vous pouvez voyager dans le temps.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** montrant comment Rediacc gère ce type de problème. Nous sommes une startup. Ce sont des scénarios réalistes pour lesquels le produit a été conçu, pas des études de cas déjà livrées à des clients.

**Scénario de crise :** Un nouvel employé a **accidentellement supprimé** des lignes critiques de votre base de données en direct il y a 3 semaines. Votre système de sauvegarde ne conserve que 2 semaines d'historique. Avec une configuration normale, ces données sont perdues.

## Le problème

Mehmet gère la base de données pour une grande plateforme de commerce électronique. Un matin, les clients commencent à se plaindre que les enregistrements de commandes passées **ne sont pas visibles** d'aucune manière. Il enquête. Un ingénieur nouvellement embauché avait **accidentellement supprimé** des lignes critiques de la base de données en direct il y a 3 semaines, **se connectant à la base de données en direct au lieu de l'environnement de test**. L'erreur classique. Chaque administrateur de base de données l'a soit commise lui-même, soit vu un nouvel employé la commettre.

**Système de sauvegarde existant :**
* Les sauvegardes complètes sont effectuées une fois par semaine
* **Les sauvegardes incrémentielles** sont enregistrées quotidiennement

**Le dilemme :** la suppression a eu lieu **avant la date des sauvegardes complètes**, donc les données perdues ne figurent dans aucun fichier de sauvegarde. Les sauvegardes quotidiennes **enregistrent uniquement les données les plus récentes**, donc **les éléments supprimés ne peuvent pas être récupérés**.

## Impact de la crise

En raison de la perte de données :
* Les clients **ne peuvent pas traiter les demandes de remboursement**
* Des incohérences surviennent dans le système de paiement
* Les plaintes se propagent rapidement sur les réseaux sociaux

**Résultats :**
* L'équipe d'assistance client est soumise à **une pression intense**
* La réputation de l'organisation est **rapidement endommagée**
* Les efforts de récupération manuelle des données obtiennent **seulement 15 % de réussite**

**Défi supplémentaire :**
* Pour réduire les coûts de stockage, l'organisation conserve **uniquement les 2 dernières semaines de sauvegardes**
* Les données supprimées ne figurent pas dans les **sauvegardes récentes**

## Solution Rediacc

Voici la configuration de machine à voyager dans le temps que Mehmet construit avec Rediacc :

![Time Travel Recovery](/img/time-travel-recovery.svg)

### 1. **Instantanés**
* Rediacc prend automatiquement des instantanés du système toutes les heures
* Ces instantanés couvrent également les moments juste avant la suppression des données

### 2. **Remonter dans le temps**
* Mehmet sélectionne la date et l'heure auxquelles la suppression a eu lieu dans l'interface Rediacc
* Restaure un instantané du système d'il y a 3 semaines vers une nouvelle instance en 1 minute

### 3. **Récupération complète**
* Les données perdues sont restaurées complètement et de façon cohérente

## Résultat

* La réputation de l'organisation a été rétablie **en 24 heures**
* La perte financière a été évitée de **95 %**
* Rediacc a prouvé que les sauvegardes fréquentes pourraient être effectuées **sans augmenter les coûts de stockage**
