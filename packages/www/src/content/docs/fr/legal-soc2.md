---
title: "Conformité SOC 2"
description: "Voilà SOC 2 : les auditeurs veulent des preuves que vos contrôles fonctionnent. Rediacc vous donne les journaux, la piste de gestion des changements et tout ce qu'ils demandent d'autre."
category: "Legal"
order: 2
language: fr
sourceHash: "27d2366f84e21d8c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Je sais ce qu'est SOC 2 parce que j'ai participé à des réunions d'audit. Les auditeurs utilisent le cadre de l'AICPA pour vérifier que vos contrôles fonctionnent réellement, pas seulement que vous prétendez qu'ils fonctionnent. Cinq critères de services de confiance : sécurité, disponibilité, intégrité du traitement, confidentialité et vie privée.

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

Donc Rediacc enregistre plus de 70 types d'événements différents. Les actions des utilisateurs, les changements système, les mises à jour de configuration, les modifications de contrôle d'accès, les événements de sécurité, les opérations de fork, les pistes d'audit. Je sais que ça semble beaucoup, mais les auditeurs tiennent vraiment à voir tout ça.

- **Authentification** : connexion, déconnexion, changements de mot de passe, activation/désactivation 2FA, révocation de sessions
- **Autorisation** : création/révocation de jetons API, changements de rôles, appartenance aux équipes
- **Paramétrage** : envoi/récupération du magasin de configuration, gestion des membres, échecs d'accès (discordance IP, refus SDK)
- **Licences** : émission de licences de dépôt, suivi des emplacements machine, changements d'abonnement
- **Opérations machine** : création/démarrage/arrêt/suppression de dépôt, fork, envoi/récupération de sauvegarde, synchronisation de fichiers, sessions terminal

Trois façons d'accéder à ces journaux. Tableau de bord d'administration avec filtrage par utilisateur, équipe et date. Page d'activité du portail pour les administrateurs org, avec filtrage par type et date. Ou `rdc audit` CLI pour l'export programmatique. Vous pouvez les diriger vers vos propres outils, les intégrer partout. Les opérations machine s'enregistrent également dans vos journaux système, donc vous avez une protection en profondeur.

## Gestion des changements

Les forks rendent la gestion des changements auditable. Vous forquez la production et obtenez une copie de l'état en direct. Testez-la. Examinez-la. Promouvez-la ou abandonnez-la. Chaque étape horodatée et attribuée à une personne. C'est ce que les auditeurs veulent voir : aucun changement anonyme.

1. Forker un dépôt de production (`rdc repo fork`)
2. Appliquer et tester les changements sur le fork
3. Valider le fork de manière indépendante
4. Promouvoir le fork en production (`rdc repo takeover`)

Chaque étape : enregistrée. Horodatée. Attribuée à une personne. Pas de 'je ne sais pas qui a changé ça'.

## Contrôle d'accès

- **Accès machine** : Authentification par clé SSH uniquement. Pas de SSH par mot de passe.
- **Jetons API** : Permissions à portée définie, liaison IP optionnelle, révocation automatique lors du retrait d'une équipe.
- **Isolation des dépôts** : Chaque dépôt a son propre socket Docker daemon. L'accès à un dépôt ne donne pas accès à un autre sur la même machine.
- **Jetons du magasin de configuration** : Jetons rotatifs à usage unique avec liaison IP à la première utilisation, expiration automatique de 24 heures et fenêtre de tolérance de 3 requêtes pour la concurrence. Accès des membres géré via l'échange de clés X25519 avec révocation immédiate.
