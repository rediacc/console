---
title: "NIS2 et DORA"
description: "Comment Rediacc répond aux exigences de la directive européenne NIS2 sur la cybersécurité et du règlement DORA sur la résilience opérationnelle numérique."
category: "Legal"
order: 8
language: fr
sourceHash: "a2078388f7ae1906"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

NIS2 et DORA sont des réglementations européennes qui imposent des exigences de cybersécurité et de résilience opérationnelle aux organisations d'infrastructures critiques et du secteur financier. Les deux sont entrées en vigueur en 2025 et s'appliquent largement aux industries de l'UE.

## Directive NIS2

La Directive sur la sécurité des réseaux et de l'information 2 (NIS2) établit des exigences de cybersécurité pour les entités "essentielles" et "importantes" dans des secteurs incluant l'énergie, les transports, la santé, l'infrastructure numérique et l'administration publique.

Texte intégral : [Directive (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### Correspondance des exigences NIS2

| Exigence NIS2 | Capacité Rediacc |
|--------------|-----------------|
| Mesures de gestion des risques (Art. 21) | Chiffrement LUKS2 au repos, isolation réseau par dépôt, accès SSH uniquement, journalisation d'audit au niveau du compte (40+ types d'événements) |
| Gestion des incidents (Art. 21(2)(b)) | 40+ types d'événements au niveau du compte (auth, jetons, config, licences) fournissent une piste forensique. L'isolation par dépôt limite le rayon d'impact. |
| Continuité d'activité (Art. 21(2)(c)) | `rdc repo push/pull` avec sauvegarde chiffrée multi-destination. Snapshots CoW pour restauration instantanée. |
| Sécurité de la chaîne d'approvisionnement (Art. 21(2)(d)) | L'auto-hébergement élimine les risques liés à la chaîne d'approvisionnement SaaS. Aucun fournisseur cloud tiers ne traite vos données. |
| Sécurité réseau (Art. 21(2)(e)) | Docker daemons par dépôt, règles iptables, isolation IP loopback (sous-réseaux /26). |
| Chiffrement (Art. 21(2)(h)) | Chiffrement LUKS2 AES-256 obligatoire. Magasin de configuration à connaissance nulle avec AES-256-GCM. |
| Contrôle d'accès (Art. 21(2)(i)) | Authentification par clé SSH, jetons API à portée définie avec liaison IP, authentification à deux facteurs (TOTP). |
| Signalement d'incidents, alerte précoce 24h (Art. 23) | La journalisation d'audit permet la détection et la délimitation rapides des incidents. |

### Risque de chaîne d'approvisionnement

La sécurité de la chaîne d'approvisionnement est une préoccupation centrale de NIS2 (Art. 21(2)(d)). Les organisations doivent évaluer et gérer les risques de leurs fournisseurs de services TIC et de leurs sous-traitants.

Rediacc auto-hébergé supprime la plus grande surface d'attaque de la chaîne d'approvisionnement : aucun SaaS tiers ne traite vos données, aucun fournisseur cloud n'a d'accès logique à votre infrastructure, et aucun environnement multi-locataire ne crée d'exposition à la posture de sécurité d'autres clients. [L'attaque de ransomware contre Blackbaud en 2020 a exposé les données de plus de 13 000 organisations clientes, coûtant 49,5 millions de dollars en règlements.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Digital Operational Resilience Act)

DORA établit des exigences pour la gestion des risques TIC, le signalement des incidents, les tests de résilience et la gestion des risques des tiers pour le secteur financier de l'UE. Il s'applique aux banques, compagnies d'assurance, sociétés d'investissement, prestataires de services sur crypto-actifs et leurs fournisseurs tiers critiques de TIC.

Texte intégral : [Règlement (UE) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### Correspondance des exigences DORA

| Exigence DORA | Capacité Rediacc |
|--------------|-----------------|
| Cadre de gestion des risques TIC (Art. 6) | Le chiffrement, l'isolation, la journalisation d'audit et la sauvegarde forment la couche de contrôles techniques. |
| Protection et prévention (Art. 9) | Chiffrement LUKS2 AES-256 au repos. L'isolation réseau empêche le déplacement latéral. Accès SSH uniquement. |
| Détection (Art. 10) | 40+ types d'événements au niveau du compte. Tableau de bord d'administration avec filtrage par utilisateur et équipe. Opérations machine auditables via SSH et journaux système. |
| Réponse et récupération (Art. 11) | Snapshots CoW pour restauration instantanée. `rdc repo push/pull` pour récupération multi-destination. Tests de reprise après sinistre basés sur les forks. |
| Risque TIC tiers (Art. 28-30) | L'auto-hébergement élimine entièrement la classification de "fournisseur tiers critique de TIC". |
| Tests de résilience opérationnelle numérique (Art. 24-27) | Le clonage CoW permet des tests de pénétration dirigés par les menaces sur des environnements similaires à la production sans exposition de données. Cloner, tester, détruire. |

### Risque des fournisseurs TIC tiers

Les exigences les plus contraignantes de DORA concernent la gestion des fournisseurs tiers critiques de TIC (Art. 28-30). Les institutions financières doivent tenir des registres de fournisseurs TIC, mener des évaluations de risques, négocier des dispositions contractuelles spécifiques et planifier des stratégies de sortie.

Rediacc auto-hébergé évite cela entièrement. Aucun fournisseur tiers de TIC à enregistrer, évaluer ou surveiller. L'institution financière contrôle directement sa propre infrastructure.

### Tests de résilience

DORA impose des tests de résilience opérationnelle numérique, incluant des tests de pénétration dirigés par les menaces (TLPT) pour les grandes institutions (Art. 26). Le clonage CoW gère cela directement :

1. Forker l'environnement de production (instantané, même machine, pas de transfert de données)
2. Exécuter des tests de pénétration contre le fork
3. Détruire le fork une fois terminé

La production n'est jamais touchée, mais l'environnement de test est une réplique exacte. Aucune donnée ne quitte la machine.
