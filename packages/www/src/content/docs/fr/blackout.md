---
title: Continuité bancaire pendant la panne d'électricité
description: >-
  Maintenez les opérations bancaires pendant les pannes de courant grâce à la
  mise en miroir des données intercontinentales.
category: Use Cases
order: 6
language: fr
sourceHash: "63861113cf5e7809"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
---

> **Lorsque les lumières s'éteignent, votre entreprise reste allumée.**

**Remarque :** Il s'agit d'un **exemple de cas d'utilisation** démontrant comment Rediacc peut résoudre ce problème. En tant que startup, ces scénarios représentent des applications potentielles plutôt que des études de cas réalisées.

**Scénario de crise :** Une panne d'électricité massive a touché l'Espagne et le Portugal le 28 avril 2025, déclenchée par une ligne de transport endommagée en France. La panne de courant a mis hors service une infrastructure informatique critique, entraînant la perte de l’accès à leurs systèmes par les grandes banques et les entreprises technologiques.

## Le problème

Le réseau électrique ibérique a été confronté à une cascade de pannes catastrophiques :

* Un **incendie dans le sud-ouest de la France** a endommagé une ligne de transport critique 
* Les dégâts provoqués par la **déconnexion brutale** des interconnexions transfrontalières 
* L'Espagne et le Portugal sont devenus **électriquement isolés** du réseau européen

**Impact sur les entreprises :** 
* Les centres de données à travers l'Espagne ont subi une **perte de courant immédiate** 
* Les générateurs de secours n'ont pas pu s'activer à plusieurs endroits en raison de pannes du système de contrôle. 
* Les systèmes bancaires ont été mis hors ligne, empêchant les transactions à travers le pays

**Défis de l'infrastructure informatique :** 
* **Les systèmes de sauvegarde locaux** étaient inefficaces car ils étaient situés dans la même région touchée 
* **Les procédures de récupération d'urgence** reposaient sur un accès local aux serveurs physiques 
* **Les plans de continuité des activités** n'ont pas pris en compte les pannes de courant à l'échelle nationale durant plus de 4 heures.

## Impact de la crise

L’interruption du service informatique a entraîné : 
* **Effondrement du système financier** avec des retards de transactions estimés à 4,5 milliards d'euros 
* Les données commerciales critiques deviennent inaccessibles pendant plus de 14 heures 
* Les principales plateformes de commerce électronique connaissent un arrêt complet 
* Les systèmes de service client échouent dans plusieurs secteurs

## Solution de rediacc

Un grand groupe bancaire espagnol qui a mis en œuvre la solution de réplication transcontinentale de Rediacc a maintenu ses opérations tout au long de la crise :

![Banking Continuity During Blackout](/img/blackout-continuity.svg)

### 1. **Miroir de données intercontinentales** 
* Les bases de données bancaires et les systèmes de transactions seraient **répliqués en permanence** dans des centres de données aux États-Unis 
* Les données clients et les enregistrements de transactions resteraient synchronisés dans la limite du délai de réplication que permettent votre liaison et votre volume

### 2. **Transition opérationnelle transparente** 
* Si les serveurs espagnols perdaient du courant, le trafic serait **automatiquement redirigé** vers les systèmes basés aux États-Unis 
* Les clients ne constateraient qu'une brève interruption le temps que la redirection s'effectue, plutôt qu'une panne aussi longue que celle du réseau électrique

### 3. **Poursuite du service à distance** 
* Les centres d'appels des pays non concernés pourraient accéder aux systèmes répliqués et continuer à assurer le support client 
* Les applications bancaires mobiles resteraient fonctionnelles grâce à la connexion à des centres de données alternatifs

## Résultat potentiel

**Continuité des activités :** 
* Les concurrents sont restés hors ligne plus de 14 heures. Une banque dotée de cette architecture continuerait à fonctionner pendant toute cette période

**Continuité du service :** 
* Elle pourrait continuer à traiter les transactions là où les établissements sans seconde région en seraient incapables

**Protection financière :** 
* Elle éviterait les pertes liées aux échecs de transactions qui s'accumulent à chaque heure où un système de paiement est hors service 
* Aucune donnée ne serait perdue ou corrompue, éliminant ainsi le besoin de toute opération de récupération
