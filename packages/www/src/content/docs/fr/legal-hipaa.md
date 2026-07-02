---
title: "Conformité HIPAA"
description: "Comment l'architecture de chiffrement et d'isolation de Rediacc correspond aux exigences de garanties HIPAA pour la protection des informations de santé."
category: "Legal"
order: 3
language: fr
sourceHash: "a0dd73c1923519b0"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Le Health Insurance Portability and Accountability Act (HIPAA) est une loi fédérale américaine qui établit des normes pour la protection des informations sensibles de santé des patients (PHI). Il s'applique aux entités couvertes (prestataires de soins, régimes d'assurance maladie, chambres de compensation) et à leurs partenaires commerciaux.

Texte intégral : [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Correspondance des garanties

HIPAA exige des garanties administratives, techniques et physiques. Le tableau ci-dessous les met en correspondance avec les capacités de Rediacc.

### Garanties techniques

| Exigence | Référence HIPAA | Capacité Rediacc |
|----------|----------------|-----------------|
| Contrôle d'accès | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Authentification par clé SSH. Jetons API avec liaison IP et restrictions de portée. L'isolation du Docker daemon par dépôt empêche l'accès inter-dépôts. |
| Contrôles d'audit | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Plus de 40 types d'événements au niveau du compte couvrant l'authentification, les jetons API, les opérations de configuration et les licences. Traçabilité par utilisateur et par équipe. Export via le tableau de bord d'administration ou la page d'activité du portail (export JSON disponible). |
| Contrôles d'intégrité | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Les snapshots CoW préservent les données originales avant modification. `rdc repo validate` vérifie l'intégrité du dépôt et la santé des sauvegardes (conteneur LUKS, cohérence du système de fichiers, configuration). |
| Chiffrement au repos | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Chiffrement LUKS2 AES-256 sur tous les volumes de dépôts. Identifiants stockés uniquement dans la configuration locale de l'opérateur, jamais sur le serveur. Le magasin de configuration utilise le chiffrement à connaissance nulle AES-256-GCM avec dérivation de clé fractionnée. Même le serveur ne peut pas déchiffrer les configurations stockées. |
| Sécurité de transmission | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Toutes les opérations distantes utilisent SSH. Le transport de sauvegarde est chiffré de bout en bout. Aucun transfert de données non chiffré. |

### Garanties administratives

| Exigence | Capacité Rediacc |
|----------|-----------------|
| Gestion des accès du personnel | Jetons API avec permissions à portée définie. Contrôle d'accès basé sur les équipes. Révocation automatique des jetons lors du retrait d'une équipe. |
| Procédures d'incidents de sécurité | Les journaux d'audit fournissent une piste forensique de toutes les opérations. L'isolation par dépôt limite le rayon d'impact. |
| Plan de contingence | `rdc repo push/pull` supporte la sauvegarde chiffrée multi-destination. Les snapshots CoW permettent une récupération instantanée. |

### Garanties physiques

| Exigence | Capacité Rediacc |
|----------|-----------------|
| Contrôles d'accès aux installations | Auto-hébergé : votre organisation contrôle la sécurité physique de vos serveurs. Aucune dépendance envers des centres de données tiers pour les opérations principales. |
| Sécurité des postes de travail | LUKS chiffre toutes les données au repos. Les dépôts non montés sont des blobs chiffrés sur le disque, illisibles sans les identifiants de l'opérateur. |

## Accord de partenariat commercial (BAA)

Puisque Rediacc est un logiciel auto-hébergé qui s'exécute sur votre infrastructure, il ne traite, stocke ni transmet de PHI via les systèmes de Rediacc (l'entreprise). L'exigence typique de BAA s'applique à votre fournisseur d'infrastructure (fournisseur cloud ou installation de colocation), pas à Rediacc.

Rediacc fonctionne comme un outil logiciel sur vos serveurs, similaire à un système d'exploitation ou un moteur de base de données. Il n'a pas accès à vos données. Le magasin de configuration optionnel synchronise des blobs chiffrés via les serveurs de Rediacc, mais sa conception à connaissance nulle signifie que le serveur ne peut pas déchiffrer le contenu. Il ne stocke que du texte chiffré opaque.

## Environnements de développement avec PHI

Lors du clonage d'environnements de production contenant des PHI à des fins de développement, utilisez le hook de cycle de vie `up()` du Rediaccfile pour exécuter des scripts de nettoyage qui :

- Suppriment les PHI des tables de la base de données
- Remplacent les identifiants des patients par des données synthétiques
- Retirent les jetons de session et les clés API

Les développeurs obtiennent une infrastructure similaire à la production avec des données dé-identifiées, satisfaisant le principe du minimum nécessaire de HIPAA.
