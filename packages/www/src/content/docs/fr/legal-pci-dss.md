---
title: "Conformité PCI DSS"
description: "Comment Rediacc répond aux exigences PCI DSS : sauvegardes immuables, isolation automatique du réseau et contrôle d'accès au niveau de l'infrastructure."
category: "Legal"
order: 6
language: fr
sourceHash: "d8391036876231a0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

PCI DSS v4.0.1. n'est pas optionnel si tu manipules des données de titulaires de cartes. La version 4.0.1. se résume à une exigence : l'isolement au niveau de l'infrastructure de tout le reste.

Référence : [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Correspondance des exigences

| Exigence PCI DSS | Description | Capacité Rediacc |
|------------------|-------------|-----------------|
| **Exig. 1**, Contrôles de sécurité réseau | Installer et maintenir des contrôles de sécurité réseau | Les règles iptables par dépôt bloquent tout trafic inter-dépôts. Chaque dépôt obtient son propre sous-réseau IP loopback (/26). |
| **Exig. 2**, Configurations sécurisées | Appliquer des configurations sécurisées à tous les composants système | Les hooks de cycle de vie du Rediaccfile imposent des configurations déterministes et reproductibles. Pas d'identifiants par défaut. Les clés LUKS sont générées par l'opérateur. |
| **Exig. 3**, Protéger les données stockées | Protéger les données de compte stockées avec le chiffrement | Chiffrement LUKS2 AES-256 sur tous les volumes de dépôts. Le chiffrement est obligatoire, pas optionnel. Effacement cryptographique via destruction de la clé LUKS. |
| **Exig. 4**, Protéger les données en transit | Protéger les données du titulaire avec une cryptographie forte pendant la transmission | Toutes les opérations distantes via SSH. Transport de sauvegarde chiffré de bout en bout. Aucun chemin de données non chiffré. |
| **Exig. 6**, Développement sécurisé | Développer et maintenir des systèmes et logiciels sécurisés | Le clonage CoW crée des environnements de test isolés sans exposer les données de cartes de production aux réseaux de développement. Workflow fork-test-promote. |
| **Exig. 7**, Restreindre l'accès | Restreindre l'accès aux composants système et aux données du titulaire selon le besoin d'en connaître | Sockets Docker daemon par dépôt. L'accès à un dépôt ne donne pas accès à un autre. Authentification par clé SSH. |
| **Exig. 8**, Identifier et authentifier | Identifier les utilisateurs et authentifier l'accès aux composants système | Authentification par clé SSH. Jetons API avec liaison IP et permissions à portée définie. Authentification à deux facteurs (TOTP). |
| **Exig. 9**, Restreindre l'accès physique | Restreindre l'accès physique aux données du titulaire | Auto-hébergé : la sécurité physique est sous votre contrôle direct. Le chiffrement LUKS rend les disques volés illisibles. |
| **Exig. 10**, Journaliser et surveiller | Journaliser et surveiller tous les accès aux composants système et aux données du titulaire | 70+ types d'événements (auth, jetons API, config, licences, opérations machines). Tableau de bord d'administration et portail avec filtrage par utilisateur, équipe, type et date. `rdc audit` CLI pour l'export programmatique. Les opérations machines sont également dans les journaux système pour la défense en profondeur. |
| **Exig. 12**, Politiques organisationnelles | Soutenir la sécurité de l'information avec des politiques et programmes organisationnels | L'auto-hébergement élimine le périmètre du sous-traitant tiers (Exig. 12.8). Réduit le périmètre de conformité PCI DSS. |

## Segmentation réseau

PCI DSS insiste fortement sur la segmentation. On voit constamment des équipes superposer des règles iptables sur une isolation insuffisante. Ça ne marche pas. Les équipes qui réussissent ont la segmentation construite dans l'architecture. Rediacc te l'offre par défaut :

- Chaque dépôt s'exécute dans son propre Docker daemon à `/var/run/rediacc/docker-<networkId>.sock`
- Les dépôts ont des sous-réseaux IP loopback isolés (127.0.x.x/26, 61 IPs utilisables par réseau)
- Les règles iptables appliquées par renet bloquent tout trafic inter-daemons
- Les conteneurs de différents dépôts ne peuvent pas communiquer au niveau réseau

Un dépôt de traitement des paiements s'exécute sur son propre daemon Docker et son propre sous-réseau loopback, isolé du réseau de toutes les autres applications sur la même machine. Aucune règle de pare-feu supplémentaire à rédiger.

## Réduction du périmètre

Rediacc auto-hébergé réduit le périmètre de conformité PCI DSS. Tu n'as pas besoin de configurer manuellement la segmentation réseau ; c'est automatique par conception. Notre documentation sur cette partie a encore besoin de travail, mais l'isolation est solide.

- Aucun fournisseur cloud tiers dans le flux de données du titulaire
- Aucun fournisseur SaaS à évaluer sous l'Exig. 12.8 (prestataires de services tiers)
- Contrôles de sécurité physique sous votre gestion directe
- Clés de chiffrement stockées uniquement dans la configuration locale de l'opérateur

## Cas d'application

La plupart des échecs d'audit PCI se résument à l'une de ces deux choses : une segmentation qui n'a jamais été correctement isolée, ou un chiffrement qui n'a jamais été testé contre des attaques réelles.

- Heartland Payment Systems (2008) : les attaquants se sont déplacés latéralement à travers 48 bases de données en raison d'une mauvaise segmentation réseau, exposant 130 millions de numéros de cartes. [Le coût total a dépassé 200 millions de dollars.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013) : les attaquants ont pivoté de l'accès réseau d'un fournisseur HVAC vers les systèmes de point de vente en raison d'une architecture réseau plate, capturant 40 millions de cartes de paiement. [Accord de 18,5 millions de dollars avec 47 procureurs généraux d'États.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
