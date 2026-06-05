---
title: "Conformité ISO 27001"
description: "Comment Rediacc correspond aux contrôles de sécurité de l'information ISO 27001 pour le chiffrement, la gestion des accès et la sécurité opérationnelle."
category: "Legal"
order: 5
language: fr
sourceHash: "52709a22c0b38178"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

D'accord. ISO/IEC 27001:2022 est la norme internationale pour les systèmes de management de la sécurité de l'information. Publiée par l'ISO/IEC, c'est un long document listant les contrôles pour le chiffrement, la gestion des accès, la réponse aux incidents et des dizaines de domaines de sécurité. Vous savez probablement déjà ce que c'est. Donc soyons directs : Rediacc n'adresse pas chaque contrôle de la norme, et nous ne prétendrons pas que c'est le cas. Ce qui suit est une correspondance honnête de là où Rediacc s'inscrit. La version actuelle est ISO/IEC 27001:2022.

Référence : [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Bon, Rediacc est un composant de la couche de contrôles techniques au sein d'un SMSI. Le tableau ci-dessous met en correspondance les capacités de Rediacc avec les domaines de contrôle pertinents de l'Annexe A.

## Correspondance des contrôles de l'Annexe A

| Domaine de contrôle | Contrôle | Capacité Rediacc |
|--------------------|----------|-----------------|
| **A.8**, Gestion des actifs | A.8.1 Inventaire des actifs | Chaque dépôt est un actif discret et identifiable avec un GUID unique. `rdc machine query --name <machine> --repositories` liste tous les dépôts avec taille, état de montage et nombre de conteneurs. |
| **A.8**, Gestion des actifs | A.8.24 Utilisation de la cryptographie | Chiffrement LUKS2 AES-256 obligatoire sur tous les dépôts. Gestion des clés : identifiants stockés uniquement dans la configuration locale de l'opérateur, jamais sur le serveur. |
| **A.9**, Contrôle d'accès | A.9.2 Gestion des accès utilisateurs | Authentification par clé SSH. Jetons API avec liaison IP, portée par équipe et révocation automatique lors du retrait d'une équipe. Authentification à deux facteurs (TOTP). |
| **A.10**, Cryptographie | A.10.1 Contrôles cryptographiques | LUKS2 avec paramètres de clé configurables. Identifiants de chiffrement par dépôt. Tout le transport distant via SSH. Le magasin de configuration implémente le chiffrement à connaissance nulle : AES-256-GCM avec dérivation de clé HKDF, échange de clés X25519 pour les membres et clés SDK à fenêtre temporelle pour la révocation immédiate. |
| **A.12**, Sécurité opérationnelle | A.12.3 Sauvegarde | `rdc repo push/pull` avec stockage chiffré hors site vers plusieurs destinations (SSH, S3, B2, Azure, GDrive). Snapshots CoW pour la récupération à un point dans le temps. `rdc repo validate` vérifie la santé des sauvegardes et l'intégrité des dépôts. |
| **A.12**, Sécurité opérationnelle | A.12.4 Journalisation et surveillance | Plus de 70 types d'événements (authentification, jetons API, configuration, licences, opérations sur les machines). Surveillance de la santé des machines via `rdc machine query`. Surveillance de l'état des conteneurs et des ressources. |
| **A.13**, Sécurité des communications | A.13.1 Gestion de la sécurité réseau | Isolation du Docker daemon par dépôt. Règles iptables bloquant le trafic inter-dépôts. Sous-réseaux IP loopback (/26) par dépôt. Proxy inverse avec terminaison TLS pour l'accès externe. |
| **A.14**, Développement de systèmes | A.14.2 Sécurité dans le développement | Les environnements de développement basés sur les forks fournissent la parité avec la production sans exposition des données de production. Les hooks de cycle de vie du Rediaccfile permettent le nettoyage automatisé des données dans les environnements clonés. |

## Gestion des actifs

C'est simple : le modèle de dépôts de Rediacc supporte naturellement les exigences d'inventaire des actifs :

- Chaque dépôt a un GUID unique attribué à la création
- Les dépôts sont énumérables par machine (`rdc machine query --repositories`)
- L'état de chiffrement, l'état de montage, le nombre de conteneurs et l'utilisation du disque de chaque dépôt sont visibles
- Les relations de fork tracent la lignée des environnements clonés

## Gestion des changements

C'est là que c'est intéressant : le workflow fork-test-promote s'aligne sur les exigences de gestion des changements d'ISO 27001 :

1. **Fork** : Créer une copie isolée de l'environnement de production
2. **Test** : Appliquer et valider les changements sur le fork
3. **Promouvoir** : Utiliser `rdc repo takeover` pour basculer le fork en production
4. **Audit** : Toutes les opérations sont enregistrées avec horodatage et identification de l'acteur

## Amélioration continue

- L'export des journaux d'audit supporte les revues de sécurité périodiques
- Les vérifications de santé des machines (`rdc machine query --system`) supportent la surveillance opérationnelle
- `rdc repo validate` vérifie la santé des sauvegardes après chaque opération
