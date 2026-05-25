---
title: "Conformité SOC 2"
description: "Comment Rediacc correspond aux critères de services de confiance SOC 2 pour la sécurité, la disponibilité et la confidentialité."
category: "Legal"
order: 2
language: fr
sourceHash: "ebdae97034aa3cce"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

SOC 2 (System and Organization Controls 2) est un cadre développé par l'American Institute of Certified Public Accountants (AICPA) pour évaluer les contrôles d'une organisation en matière de sécurité, disponibilité, intégrité du traitement, confidentialité et vie privée.

Référence : [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Correspondance des critères de services de confiance

| Principe de confiance | Critère | Capacité Rediacc |
|----------------------|---------|-----------------|
| **Sécurité** (CC6) | Contrôles d'accès logiques, chiffrement | Chiffrement LUKS2 AES-256 au repos. Identifiants stockés uniquement dans la configuration locale de l'opérateur (`~/.config/rediacc/`), jamais sur le serveur. Accès par clé SSH. Docker daemons isolés par dépôt. |
| **Disponibilité** (A1) | Récupération et résilience du système | `rdc repo push/pull` avec copies chiffrées hors site vers SSH, S3, B2, Azure ou GDrive. Snapshots CoW pour restauration instantanée. Mises à jour basées sur les forks pour des changements sans interruption. |
| **Intégrité du traitement** (PI1) | Traitement précis et complet | Les hooks de cycle de vie déterministes du Rediaccfile (`up`/`down`) garantissent des déploiements cohérents. `rdc repo validate` vérifie l'intégrité du dépôt et la santé des sauvegardes après des arrêts inattendus ou des opérations de sauvegarde. |
| **Confidentialité** (C1) | Protection des données contre les accès non autorisés | Chiffrement par dépôt avec des identifiants LUKS uniques. Isolation réseau via iptables, Docker daemons séparés et sous-réseaux IP loopback. Les conteneurs de différents dépôts ne peuvent pas se voir. Le magasin de configuration à connaissance nulle chiffre les configurations côté client avant l'envoi. Le serveur ne stocke que des blobs opaques qu'il ne peut pas déchiffrer. |
| **Vie privée** (P1-P8) | Traitement des données personnelles | Auto-hébergé : pas de sortie de données pendant les opérations. Piste d'audit pour tous les accès aux données. Gestion des clés de chiffrement sous contrôle du client. Le magasin de configuration utilise la dérivation de clé fractionnée (passkey PRF + secret serveur) pour qu'aucune partie ne puisse accéder aux données seule. |

## Piste d'audit

Rediacc enregistre plus de 40 types d'événements au niveau du compte couvrant :

- **Authentification** : connexion, déconnexion, changements de mot de passe, activation/désactivation 2FA, révocation de sessions
- **Autorisation** : création/révocation de jetons API, changements de rôles, appartenance aux équipes
- **Paramétrage** : envoi/récupération du magasin de configuration, gestion des membres, échecs d'accès (discordance IP, refus SDK)
- **Licences** : activation de machines, émission de licences, changements d'abonnement

Ces journaux sont accessibles via le tableau de bord d'administration (avec filtrage par utilisateur, équipe et date) et `rdc audit` CLI pour l'export programmatique. Les opérations au niveau machine (fork, sauvegarde, déploiement) s'exécutent via SSH sur votre infrastructure, leurs pistes d'audit se trouvent donc dans vos journaux système.

## Gestion des changements

Le workflow basé sur les forks soutient une gestion des changements contrôlée :

1. Forker un dépôt de production (`rdc repo fork`)
2. Appliquer et tester les changements sur le fork
3. Valider le fork de manière indépendante
4. Promouvoir le fork en production (`rdc repo takeover`)

Chaque étape est enregistrée avec horodatage et identification de l'acteur.

## Contrôle d'accès

- **Accès machine** : Authentification par clé SSH uniquement. Pas de SSH par mot de passe.
- **Jetons API** : Permissions à portée définie, liaison IP optionnelle, révocation automatique lors du retrait d'une équipe.
- **Isolation des dépôts** : Chaque dépôt a son propre socket Docker daemon. L'accès à un dépôt ne donne pas accès à un autre sur la même machine.
- **Jetons du magasin de configuration** : Jetons rotatifs à usage unique avec liaison IP à la première utilisation, expiration automatique de 24 heures et fenêtre de tolérance de 3 requêtes pour la concurrence. Accès des membres géré via l'échange de clés X25519 avec révocation immédiate.
