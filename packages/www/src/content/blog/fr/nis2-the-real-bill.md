---
title: Ce que les acheteurs nous ont appris lors du premier cycle d'audit NIS2
description: >-
  La pile de cinq outils que les entités essentielles du marché intermédiaire
  assemblent discrètement en 2026, ce qu'un plan de contrôle auto-hébergé
  consolide, et les postes budgétaires qui restent à votre charge dans tous les
  cas.
author: Rediacc
publishedDate: 2026-05-09T00:00:00.000Z
category: guide
tags:
  - nis2
  - guide-acheteur
  - conformite
  - cout
  - marche-intermediaire
featured: false
language: fr
sourceHash: 29fbcbffd8a304bc
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

**Résumé.** Les premiers audits NIS2 sont désormais derrière nous pour la vague allemande. Les acheteurs avec lesquels nous avons échangé depuis décembre décrivent tous une version du même outillage : cinq outils, trois contrats, deux journaux d'audit qui se recoupent, et une lacune qu'ils n'arrivent pas à combler. Ce billet est la version structurelle de cette conversation. Ce qu'un plan de contrôle auto-hébergé consolide, ce qui reste de toute façon dans votre budget, et pourquoi le bon cadre pour un cycle de renouvellement 2026 n'est pas "moins cher que Veeam" mais "moins d'entrées au registre, moins de doublons, les mêmes lacunes nommées honnêtement."

- Frontier Economics évalue le coût annuel de conformité NIS2 à l'échelle de l'UE à 31,2 milliards d'euros. La réalité par organisation, dans le marché intermédiaire, est la suivante : "nous avions déjà une pile de sécurité ; NIS2 a mis en lumière ce qui manquait."
- La pile de cinq outils : sauvegarde, reprise après sinistre (DR), masquage ou données de test, contrat de test d'intrusion, GRC. Chacun fait une partie du travail. Aucun ne couvre l'ensemble.
- Rediacc consolide la sauvegarde, la DR, le fork en guise de données de test et la restauration instantanée en un seul plan de contrôle avec un seul journal d'audit. Il ne consolide pas la GRC, les certifications, la formation, la MFA d'entreprise au sens large, les tests d'intrusion, ni le SIEM et le SOC.
- Le tableau honnête "toujours à votre charge" est le point clé de ce billet. Un acheteur qui le lit et en conclut que Rediacc remplace Drata va décevoir son auditeur.

En décembre 2025, le BSI en Allemagne a envoyé 47 mises en demeure formelles à des entités qu'il considérait dans le périmètre NIS2 mais non enregistrées. L'ANSSI en France a lancé un exercice parallèle. L'ACN en Italie a commencé à relancer environ 2 000 entités qu'elle estimait non enregistrées. La première vague d'entités essentielles et importantes du marché intermédiaire est entrée dans son premier cycle d'audit NIS2.

Nous avons eu des échanges avec une trentaine d'entre elles depuis. Des secteurs différents, des tailles différentes, principalement en Allemagne et en Italie avec quelques-unes aux Pays-Bas et en Estonie. Les conversations se ressemblent. Chaque équipe dispose d'un éditeur de sauvegarde, d'un plan de DR qui a peut-être ou non été testé, d'un discours sur les environnements de pré-production qui n'est qu'à moitié vrai, et d'un budget d'approvisionnement approuvé avant que NIS2 ne figure sur le moindre diaporama.

Ce billet est la version structurelle de ces conversations. Ce qu'un DSF ou un acheteur est effectivement invité à signer en 2026, ce qu'un plan de contrôle auto-hébergé change à la facture, et à quoi ressemble honnêtement le coût résiduel. Il ne s'agit délibérément pas d'un calculateur de TCO. Les acheteurs avec lesquels nous discutons n'ont pas besoin d'un tableur de plus ; ils ont besoin d'une carte structurelle indiquant où va l'argent et quels postes se recoupent.

Si vous voulez l'argument sur le risque lié à la chaîne d'approvisionnement derrière l'affirmation "l'auto-hébergement compte", consultez le [billet complémentaire sur l'article 21(2)(d)](/fr/blog/nis2-supply-chain-self-hosted). Si vous voulez l'argument de niveau SRE expliquant pourquoi les tests d'intrusion annuels ne suffisent plus, consultez le [billet complémentaire sur l'efficacité continue](/fr/blog/nis2-effectiveness-without-theatre). Ce billet se situe entre les deux, au niveau de la conversation budgétaire.

## Le chiffre macroéconomique, et ce qu'il signifie ou non

L'étude 2024 de Frontier Economics pour la Commission européenne évalue le coût annuel direct de la conformité NIS2 à l'échelle de l'UE à 31,2 milliards d'euros. Ce chiffre est largement cité ; il est aussi largement mal interprété.

Les 31,2 milliards d'euros concernent environ 160 000 entités essentielles et importantes. Par organisation, la moyenne se situe entre 150 000 et 250 000 euros, la variance étant principalement liée au secteur et à la taille. Une entité essentielle du marché intermédiaire de 250 employés dans l'industrie manufacturière ou la santé se situe dans la fourchette haute. Une entité importante de 60 employés dans un secteur moins intensif en données se situe dans la fourchette basse.

Les orientations de l'ENISA sur les coûts de mise en oeuvre (annexe IV du règlement d'exécution (UE) 2024/2690) sont cohérentes avec le chiffre Frontier mais le décomposent différemment : environ 35 à 45 % pour les outils, 30 à 40 % pour le personnel et la formation, 15 à 20 % pour la certification et l'audit, 5 à 10 % pour les contrats de réponse aux incidents et les services managés.

Ce que cela signifie pour un DSF qui signe un budget 2026 : la couche outils représente environ 50 000 à 120 000 euros par an pour le marché intermédiaire, selon ce qui est déjà en place. C'est cette couche outils que nous allons passer en revue.

Ce que cela ne signifie pas : qu'acheter un pack "NIS2-ready" résout le problème. Les budgets de formation du personnel et de certification sont plus élevés que le budget outils pour la plupart des équipes, et aucun éditeur d'outils ne les réduit. Un discours commercial qui revendique une réduction de 50 % du coût NIS2 fait presque toujours le calcul par rapport au seul poste "outils", et non par rapport au coût total du programme.

## La pile de cinq outils que les équipes du marché intermédiaire ont discrètement assemblée

Sur la trentaine de conversations avec des acheteurs, la pile est identique dans 90 % des cas. Cinq catégories, avec un ou deux éditeurs nommés par catégorie. Les libellés de catégorie sont stables ; les choix d'éditeurs varient.

**1. Éditeur de sauvegarde.** Veeam Data Platform Foundation ou Premium est la réponse majoritaire. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect pour les structures plus petites. Coût annuel compris entre 15 000 et 60 000 euros pour le marché intermédiaire. Généralement le poste le plus ancien ; antérieur à NIS2 de plusieurs années.

**2. Site de DR ou DR-as-a-service.** Soit une région cloud secondaire avec un runbook, une location Veeam Cloud Connect ou Rubrik Cloud Vault, soit un contrat avec un prestataire de DR managée. Coût annuel entre 8 000 et 35 000 euros. Rarement testé en pratique ; le runbook est généralement plus aspirationnel qu'opérationnel.

**3. Outil de données de test ou de masquage.** Delphix (désormais Perforce DevOps Data) est la référence pour les grandes entreprises. Tonic.ai, Redgate Test Data Manager, parfois un script rsync-et-masquage fait maison. Coût annuel entre 25 000 et 90 000 euros pour les options sous licence. La plupart des équipes que nous avons interrogées n'ont pas ce poste ; elles disposent à la place d'un environnement de préproduction qu'elles espèrent suffisant. C'est la conversation d'audit liée à l'article 21(2)(e) qui le fait apparaître dans le budget.

**4. Contrat de test d'intrusion.** Un contrat-cadre avec un cabinet de tests de sécurité ou une plateforme autonome comme Pentera ou Horizon3.ai. Coût annuel entre 15 000 et 50 000 euros pour les outils autonomes, entre 20 000 et 80 000 euros pour les missions menées par des experts humains. La plupart des équipes disposent de ce poste. La plupart le font une à deux fois par an.

**5. Plateforme GRC.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Parfois un tableur fait maison pour les équipes les plus petites. Coût annuel entre 12 000 et 60 000 euros. Utilisée pour le registre des fournisseurs, l'attestation du cadre de contrôle, la collecte de preuves et, de plus en plus, le support aux audits SOC 2 ou ISO 27001.

Cinq postes, trois à cinq éditeurs nommés, typiquement entre 75 000 et 295 000 euros par an avant les coûts de personnel et de formation. La variance est élevée, mais la structure est cohérente.

Les cinq contrats ne communiquent souvent pas entre eux. Les journaux d'audit ne sont pas unifiés. Les plans de sortie sont rédigés séparément. Les revues fournisseurs sont effectuées séparément, parfois par des responsables des achats différents. C'est la forme structurelle que NIS2 rend inconfortable.

## Où se trouvent les recoupements

Chaque catégorie de la pile se recoup avec au moins une autre.

**La sauvegarde se recoupe avec la DR.** Les éditeurs de sauvegarde modernes revendiquent tous une capacité de DR. Veeam Data Platform avec Cloud Connect est un produit de DR. Rubrik avec Cloud Vault est un produit de DR. Les deux postes paient souvent des capacités adjacentes chez le même éditeur. Les acheteurs qui n'avaient pas historiquement consolidé ces postes avaient des raisons opérationnelles (équipes séparées, SLA distincts) ; dans le cadre de l'exigence NIS2 de "source unique de vérité pour la reprise", cet argument s'affaiblit.

**La sauvegarde se recoupe avec les données de test.** Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles proposent tous une forme de sauvegarde montable à des fins de test. Ils ne remplacent pas entièrement Delphix (la couche de masquage est séparée, l'intégration base de données est moins profonde), mais pour de nombreux cas d'usage liés aux données de test, l'outil de sauvegarde couvre la moitié du besoin. La plupart des équipes ne s'en rendent pas compte.

**Les tests d'intrusion se recoupent avec les tests autonomes.** Le test d'intrusion humain sous contrat-cadre et les tests continus de type Pentera sont parfois présentés comme des alternatives, parfois comme des compléments. En pratique, un acheteur qui dispose des deux paie deux fois pour des capacités adjacentes. Un acheteur qui ne dispose d'aucun des deux présente une lacune au titre de l'article 21(2)(f).

**La GRC se recoupe avec tout.** Drata revendique une intégration avec la sauvegarde, la DR, l'identité, la gestion des vulnérabilités, la formation et la réponse aux incidents. La profondeur des intégrations varie. Une plateforme GRC dont l'intégration avec un outil de sauvegarde est superficielle produit des preuves de conformité qui ne sont pas équivalentes aux preuves natives de l'outil de sauvegarde ; les auditeurs commencent à demander laquelle est la référence.

Les recoupements ne constituent pas un gaspillage. Ils sont la conséquence d'une pile assemblée sur une décennie, avant que NIS2 ne rende la question de la consolidation structurelle.

## Où se trouvent les lacunes

Les lacunes sont plus intéressantes que les recoupements, car ce sont elles que NIS2 met en évidence.

**Validation des correctifs sur des données de production réelles.** Aucune des cinq catégories ne le fait bien. Les outils de sauvegarde montent la sauvegarde ; l'environnement monté est la sauvegarde restaurée, pas la production actuelle. Les outils de données de test masquent les données de production ; l'environnement masqué est réaliste dans sa forme mais perd les deltas de configuration. Les contrats de test d'intrusion testent ce sur quoi ils sont pointés, à savoir l'environnement de préproduction dans 90 % des cas. Le fossé entre "nous avons des outils" et "nous pouvons tester un correctif CVE dans un environnement équivalent à la production actuelle en moins d'une heure" est réel et structurel.

**Évaluation continue de l'efficacité.** La cadence annuelle est ce que font la plupart des équipes. L'article 21(2)(f) exige quelque chose de plus fréquent. Aucune des cinq catégories ne produit par défaut des preuves hebdomadaires ou bihebdomadaires. L'acheteur soit organise des exercices personnalisés (rare, coûteux), soit accepte la cadence annuelle en espérant que l'auditeur l'acceptera également (ce qui est de moins en moins le cas).

**Consolidation du registre de la chaîne d'approvisionnement.** Chacun des cinq éditeurs constitue une entrée distincte dans le registre. Chacun est associé à son propre DPA, SCC, liste de sous-traitants et plan de sortie. Le registre compte cinq entrées de niveau 1 avant même d'y ajouter les outils de formation du personnel, les outils d'identité, les outils d'observabilité et les fournisseurs IaaS. La conversation sur la chaîne d'approvisionnement, dans le cadre NIS2, est autant une conversation sur la gestion du registre qu'une conversation sur la sécurité. (Voir le [billet sur la chaîne d'approvisionnement](/fr/blog/nis2-supply-chain-self-hosted) pour l'argumentation structurelle.)

**Flux de reporting au titre de l'article 23.** L'alerte précoce sous 24 heures, la notification sous 72 heures et le rapport sous un mois ne sont produits automatiquement par aucune des cinq catégories. Ils nécessitent un SIEM, un SOC (interne ou externalisé) et une personne sachant déclarer auprès du CSIRT national. Les équipes de plus petite taille ne disposent souvent pas de tout cela. Le premier incident constitue une expérience d'apprentissage douloureuse.

## Ce que Rediacc consolide

Rediacc est un plan de contrôle unique avec un journal d'audit unifié, remplaçant les capacités essentielles de quatre des cinq catégories pour l'infrastructure auto-hébergée.

**Sauvegarde** : fonctionne en deux modes. Le mode chaud est un snapshot BTRFS cohérent au niveau des pannes. Pas d'interruption. Le mode froid effectue un cycle arrêt, snapshot, démarrage. Les deux planifient via des timers systemd. Les deux livrent vers de nombreuses destinations via rclone. Les volumes sont chiffrés en LUKS. L'opérateur détient la clé. Rediacc en tant qu'entreprise ne voit jamais les données en clair. Voir [Sauvegarde & Restauration](/fr/docs/backup-restore) et [Stratégie de sauvegarde croisée](/fr/docs/cross-backup).

**DR** : même primitive que la sauvegarde, plus `rdc repo migrate` pour le transfert de données entre machines, plus la primitive de fork pour le démarrage rapide d'un état restauré sur une machine parallèle. Le site de DR peut être une autre machine Hetzner, une machine OVH, un rack sur site, partout où SSH est accessible. Aucun cloud d'éditeur DR dans le chemin de données.

**Données de test et clonage complet de la pile** : fonctionne sur le reflink BTRFS. Le fork est à durée constante, quelle que soit la taille du dépôt. Complet signifie données, configurations, conteneurs et services. Nous avons forké un dépôt de 128 Go en 7,2 secondes lors de notre [test PocketOS](/fr/blog/i-tested-rediacc-against-the-pocketos-incident). Le fork est la production actuelle, pas un environnement de préproduction allégé. Voir [Mises à jour sans risque](/fr/docs/risk-free-upgrades).

**Restauration instantanée** : `rdc repo backup pull` depuis n'importe quelle cible rclone vers un nouveau fork, démarré sous un sous-domaine spécifique au fork couvert par le certificat wildcard du dépôt parent. Pas de manipulation DNS, pas de renouvellement de certificat.

**Journal d'audit unifié.** Plus de 70 types d'événements sur l'ensemble du plan de contrôle. Ils couvrent les connexions, les jetons API, les écritures de configuration, le cycle de vie des dépôts, la sauvegarde, la synchronisation, les sessions terminal et les opérations machine. La chaîne est liée par hachage sur le poste de travail de l'opérateur. `rdc audit verify` la vérifie de bout en bout.

Pour une entité essentielle du marché intermédiaire de 250 employés, la consolidation passe de quatre éditeurs nommés (sauvegarde, DR, données de test, restauration instantanée) à un seul. Une licence, un journal d'audit, un ensemble de décisions de mise à niveau, une entrée dans le registre.

La cinquième catégorie, la GRC, n'est pas consolidée. Nous y revenons.

## Ce qui reste de toute façon dans votre budget

C'est la section qui détermine si le reste du billet est honnête. Le tableau à deux colonnes :

| Supprimé par Rediacc | Toujours à votre charge, poste par poste |
|---|---|
| Licence éditeur de sauvegarde | Plateforme GRC (Drata, Vanta, OneTrust, AuditBoard, DataGuard) pour le registre des fournisseurs, l'attestation du cadre de contrôle, la collecte de preuves et le support aux audits SOC 2 ou ISO 27001 |
| Contrat de site DR ou location DR-as-a-service | Coûts d'audit de certification (ISO 27001, SOC 2, BSI C5 si nécessaire ; Rediacc lui-même n'est pas encore certifié, ce coût reste donc à votre charge en attendant) |
| Licence outil de données de test ou de masquage | Budget de formation du personnel et de sensibilisation à la sécurité (article 21(2)(g) NIS2) |
| Licence de restauration instantanée chez l'éditeur de sauvegarde | Solution MFA d'entreprise au sens large ; Rediacc dispose du TOTP sur le portail, pas d'une plateforme MFA d'entreprise |
| | Contrat de test d'intrusion ou plateforme de test autonome ; Rediacc fournit l'environnement cible, pas la capacité de test |
| | SIEM et SOC pour la détection et le reporting au titre de l'article 23 ; Rediacc fournit des artefacts de qualité forensique, pas la couche de reporting opérationnel |
| | Fournisseur IaaS (Hetzner, OVH, votre colocation, votre bare metal) ; Rediacc s'exécute sur l'infrastructure, pas à sa place |
| | Personnel en charge du programme. Rediacc est une couche d'outils, pas une équipe sécurité |

La colonne de droite est plus longue que celle de gauche. Telle est la forme honnête du coût NIS2. Supprimer le recoupement sauvegarde-DR-données de test permet de réaliser de vraies économies et de réduire le nombre d'entrées dans le registre ; cela ne transforme pas un programme de sécurité en abonnement SaaS.

Un acheteur qui lit ceci et en conclut "je peux remplacer Drata par Rediacc" va décevoir son auditeur. La bonne lecture est la suivante : la consolidation des éditeurs du plan de données que Rediacc permet est précisément ce que les outils GRC ne peuvent pas faire, et le travail de registre et de preuves que font les outils GRC est précisément ce que Rediacc ne fait pas. Les deux sont complémentaires.

Trois liens supplémentaires si vous voulez approfondir. La cartographie publique se trouve sur [NIS2 et DORA](/fr/docs/legal-nis2-dora). Le cadrage plus large se trouve sur [Aperçu de la conformité](/fr/docs/legal-overview). Le volet commercial côté Rediacc se trouve sur [Abonnement et licences](/fr/docs/subscription-licensing).

## Un scénario de référence, structurel et non chiffré

Prenons une entreprise manufacturière allemande de 250 employés. Classification Annex II "entité importante". Données de production sur 4 à 6 serveurs, principalement auto-hébergées avec un ou deux outils SaaS (CRM, paie). Chiffre d'affaires annuel de 80 millions d'euros. Équipe sécurité existante de 3 personnes.

**Avant**, leur pile du plan de données :

- Veeam Data Platform Foundation, 24 000 EUR/an
- Veeam Cloud Connect pour la DR, 12 000 EUR/an
- Un schéma rsync-plus-pg_dump fait maison pour les données de test, gratuit en licence mais coûtant à un SRE une demi-journée toutes les deux semaines
- Test d'intrusion annuel, 22 000 EUR
- Drata pour la GRC, 18 000 EUR/an

Cinq contrats. Deux d'entre eux (Veeam, Veeam Cloud Connect) sont chez le même éditeur mais avec des SKU différentes. Les postes du plan de données totalisent 36 000 EUR/an avant de comptabiliser le test d'intrusion ou la GRC. L'équipe produit un test de reprise annuel, aucune preuve d'efficacité continue, et un registre fournisseurs avec cinq entrées rien que pour le plan de données.

**Après**, avec Rediacc sur Hetzner pour les charges de travail auto-hébergées :

- Rediacc niveau Business, 8 400 EUR/an (couvre la taille de leurs dépôts)
- IaaS Hetzner pour le site principal et secondaire, 9 600 EUR/an combinés (déjà dans le budget ; pas de nouveau poste)
- Le contrat de test d'intrusion est maintenu (22 000 EUR)
- Drata est maintenu (18 000 EUR)
- Le schéma de données de test fait maison est retiré ; la demi-journée bihebdomadaire du SRE est réaffectée à l'exécution de la routine d'efficacité hebdomadaire

Consolidation du plan de données : 5 postes réduits à 1 (Rediacc) plus la ligne IaaS existante. La section plan de données du registre fournisseurs passe de 5 entrées à 2. Le dispositif d'efficacité continue repose désormais sur des exercices hebdomadaires avec des preuves issues du journal d'audit chaîné par hachage ; le dispositif de test de reprise est désormais étayé par la sortie de `rdc machine backup status` et un exercice de restauration par semaine.

Les chiffres sont illustratifs, pas des promesses. Votre pile est différente. La forme -- quatre à cinq postes qui se consolident en un seul plus l'IaaS existant -- est ce à quoi ressemble une vraie conversation avec un acheteur.

## Une note sur ce que ce billet n'est pas

Ce billet n'est pas une charge contre Veeam ni un calculateur de TCO. Veeam détient la plus grande part de marché de sauvegarde de VM en Europe pour de bonnes raisons ; leur produit est mature, leur réseau de partenaires est large, leur marketing NIS2 est solide, et un acheteur qui choisit Veeam en 2026 ne commet pas une erreur. Les chiffres du scénario de référence sont illustratifs, tirés de vraies conversations avec des acheteurs, pas de benchmarks. Menez l'analyse structurelle sur vos propres contrats.

Ce que ce billet est : un cadrage du côté acheteur pour un DSF qui renégocie un contrat de sauvegarde, de DR ou de conformité dans les douze prochains mois et qui veut savoir ce qu'un plan de contrôle auto-hébergé change aux postes budgétaires.

## Prochaines étapes

Si vous entrez dans un cycle de renouvellement et que le budget est ouvert, trois actions concrètes :

1. **Extrayez les trois plus grands postes sécurité et infrastructure de l'année écoulée.** Envoyez-les à votre DPO, votre CISO et votre auditeur. Demandez lesquels étaient déjà redondants avant que NIS2 ne le rende visible. La plupart des équipes identifient au moins un recoupement pour lequel elles payaient.
2. **Cartographiez votre pile actuelle du plan de données par rapport à la liste des cinq catégories ci-dessus.** Notez pour quelles catégories vous avez un éditeur, pour lesquelles vous en avez deux, et pour lesquelles vous n'en avez aucun. Les cases vides sont les lacunes que NIS2 va mettre en évidence.
3. **Réalisez l'exercice du registre fournisseurs tiré du [billet sur la chaîne d'approvisionnement](/fr/blog/nis2-supply-chain-self-hosted)** pour chaque éditeur du plan de données. Comptez les entrées dans le registre. Le chiffre est généralement plus élevé que ce à quoi l'équipe s'attendait.

Si nous figurons sur la liste restreinte, l'offre est concrète. Envoyez vos trois plus grands postes du budget sécurité et infrastructure de l'année écoulée. Nous vous indiquerons par écrit, en une semaine, lesquels peuvent être consolidés et lesquels ne peuvent pas l'être. La réponse inclura les lacunes, car nommer les lacunes est ce qui rend le reste de la réponse fiable.

Trois docs supplémentaires si vous voulez aller plus loin. [Sauvegarde à coût zéro](/fr/docs/zero-cost-backup) explique pourquoi nous fonctionnons avec moins de stockage que les éditeurs établis. [Stratégie de sauvegarde croisée](/fr/docs/cross-backup) couvre la DR intercontinentale. [Abonnement et licences](/fr/docs/subscription-licensing) est le volet commercial.
