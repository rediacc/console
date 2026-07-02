---
title: "Ce que la conformité requiert vraiment"
description: "Rediacc s'exécute sur votre infrastructure. Vous contrôlez vos données. Voici comment cela s'aligne avec les principaux cadres de conformité."
category: "Legal"
order: 0
language: fr
sourceHash: "e6044a3b067b54d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc s'exécute entièrement sur votre infrastructure. Lors du clonage, des sauvegardes et des déploiements, vos données restent sur vos machines. Vous êtes à la fois le responsable du traitement et le prestataire de traitement. Aucun SaaS tiers, aucun accès externe.

Nous mettons en correspondance les capacités techniques de Rediacc avec les exigences majeures de conformité. Chaque page détaille une réglementation spécifique avec des références au texte juridique officiel.

## Matrice de conformité

| Cadre | Portée | Capacités clés de Rediacc |
|-------|--------|---------------------------|
| [RGPD](/fr/docs/legal-gdpr) | Protection des données et vie privée dans l'UE | Clonage CoW sur la même machine, chiffrement LUKS2, magasin de configuration à connaissance nulle, journalisation d'audit, droit à l'effacement via `rdc repo delete` |
| [SOC 2](/fr/docs/legal-soc2) | Critères de services de confiance pour les organisations de services | Chiffrement au repos, synchronisation de configuration à connaissance nulle, isolation réseau, piste d'audit, sauvegarde et récupération |
| [HIPAA](/fr/docs/legal-hipaa) | Protection des informations de santé aux États-Unis | Chiffrement LUKS2, magasin de configuration à connaissance nulle, accès SSH uniquement, Docker daemons isolés, sécurité de transmission |
| [CCPA](/fr/docs/legal-ccpa) | Droits de confidentialité des consommateurs californiens | Auto-hébergé (pas de vente/partage de données), chiffrement à connaissance nulle, suppression chiffrée, inventaire des données par dépôt |
| [ISO 27001](/fr/docs/legal-iso27001) | Contrôles de gestion de la sécurité de l'information | Gestion des actifs, contrôles cryptographiques, magasin de configuration à connaissance nulle, contrôle d'accès, sécurité opérationnelle |
| [PCI DSS](/fr/docs/legal-pci-dss) | Protection des données de cartes de paiement | Segmentation réseau par architecture, chiffrement obligatoire, journalisation d'audit, réduction du périmètre via l'auto-hébergement |
| [NIS2 et DORA](/fr/docs/legal-nis2-dora) | Cybersécurité et résilience financière de l'UE | Élimination des risques liés à la chaîne d'approvisionnement, tests de résilience via clonage CoW, chiffrement, détection d'incidents |
| [Souveraineté des données](/fr/docs/legal-data-sovereignty) | Lois mondiales sur la résidence des données (PIPL, LGPD, KVKK, PIPA et autres) | Auto-hébergé = les données ne quittent jamais votre juridiction. Pas de transferts transfrontaliers, pas d'évaluations d'adéquation |

## Fondations architecturales

Voici ce qui les relie : chaque cadre de conformité dans cette section revient à la même fondation technique.

- **Chiffrement au repos** : Chaque dépôt est chiffré en LUKS2 AES-256. Les identifiants sont stockés uniquement dans la configuration locale de l'opérateur, jamais sur le serveur.
- **Isolation réseau** : Chaque dépôt dispose de son propre Docker daemon, sous-réseau IP loopback (/26) et règles iptables. Les conteneurs de différents dépôts ne peuvent pas communiquer entre eux.
- **Clonage copy-on-write** : `rdc repo fork` utilise des reflinks du système de fichiers (`cp --reflink=always`). Les données sont dupliquées sur la même machine sans aucun transfert réseau.
- **Journalisation d'audit** : Plus de 70 types d'événements couvrant l'authentification (connexion, 2FA, changements de mot de passe, révocation de session), le cycle de vie des jetons API, les opérations du magasin de configuration, l'activité d'abonnement/licence et les opérations CLI au niveau machine (cycle de vie du dépôt, sauvegarde, synchronisation, sessions terminales). Accessible via le tableau de bord d'administration et la page d'activité du portail (avec filtrage au niveau de l'organisation et export JSON). Les opérations au niveau machine sont également enregistrées dans vos journaux système pour la défense en profondeur.
- **Sauvegarde chiffrée** : `rdc repo push/pull` transfère les données via SSH. La destination de sauvegarde reçoit des volumes chiffrés LUKS.
- **Magasin de configuration à connaissance nulle** : Synchronisation chiffrée optionnelle des configurations entre appareils. Les configurations sont chiffrées côté client avec AES-256-GCM avant l'envoi. Le serveur ne stocke que des blobs opaques. Le serveur ne peut pas lire les clés SSH, les identifiants, les adresses IP ou les données de configuration en clair. La dérivation de clé utilise passkey PRF extension + HKDF avec séparation de domaine. L'accès des membres est géré via l'échange de clés X25519, et la révocation est immédiate.

Pour plus de détails sur ces capacités, consultez [Architecture](/fr/docs/architecture), [Dépôts](/fr/docs/repositories), [Stockage de configuration](/fr/docs/config-storage) et [Sécurité du compte](/fr/docs/account-security).

## Pourquoi c'est important

Les manquements à la conformité sont coûteux. Vraiment coûteux. Les cas ci-dessous montrent des problèmes que l'architecture de Rediacc empêche structurellement :

| Incident | Amende | Ce qui a mal tourné |
|----------|--------|---------------------|
| [Meta : transferts de données UE-US](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 Md EUR | Des données personnelles transférées au-delà des frontières sans garanties adéquates. Auto-hébergé signifie aucun transfert. |
| [Equifax : données non chiffrées](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 M USD | 147 millions d'enregistrements stockés sans chiffrement avec une segmentation réseau insuffisante. LUKS2 est obligatoire, pas optionnel. |
| [Target : mouvement latéral](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 M USD | Les attaquants ont pivoté d'un fournisseur HVAC vers les systèmes de paiement via un réseau plat. L'isolation par dépôt empêche cela. |
| [Anthem : PHI non chiffrées](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 M USD | 79 millions de dossiers de santé stockés sans chiffrement. LUKS2 AES-256 est toujours actif. |
| [Blackbaud : cascade de brèche SaaS](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 M USD | Un ransomware chez un fournisseur SaaS a exposé les données de plus de 13 000 organisations clientes. Auto-hébergé signifie qu'une brèche du fournisseur ne peut pas atteindre vos données. |
| [British Airways : segmentation insuffisante](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 M GBP | Les attaquants ont injecté du code malveillant en raison de contrôles réseau inadéquats. Les Docker daemons isolés et iptables empêchent l'accès latéral. |
| [Google : droit à l'effacement](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 M EUR | Difficulté à effacer complètement les données dans les systèmes distribués. L'effacement cryptographique via la destruction LUKS est instantané et complet. |

## Avis important

Ces pages expliquent comment l'architecture de Rediacc s'aligne avec les exigences de conformité. Mais voici la réalité : la conformité est plus vaste que le simple logiciel. Vous aurez besoin de politiques, de procédures, de formation et probablement d'audits tiers. Rediacc gère la partie infrastructure. Travaillez avec vos équipes juridique et de conformité pour le reste.
