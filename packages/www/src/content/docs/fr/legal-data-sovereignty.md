---
title: "Souveraineté des données"
description: "Comment l'architecture auto-hébergée de Rediacc satisfait les exigences de résidence et de souveraineté des données dans les juridictions mondiales."
category: "Legal"
order: 7
language: fr
sourceHash: "5dcc2bc3e601c128"
---

De nombreux pays exigent que les données personnelles de leurs citoyens soient stockées et traitées dans les frontières nationales. L'architecture auto-hébergée de Rediacc satisfait ces exigences par conception : les données restent sur votre machine, dans votre centre de données, dans votre juridiction. Aucune donnée ne quitte la machine pendant le clonage, et aucun SaaS tiers ne traite vos données.

## Pourquoi l'auto-hébergement résout la souveraineté des données

Le transfert transfrontalier de données est le problème de conformité le plus difficile du cloud computing. Chaque juridiction a des règles différentes, des décisions d'adéquation et des mécanismes de transfert. L'auto-hébergement élimine toute la catégorie :

- **Pas de transfert transfrontalier** : Le clonage CoW (`cp --reflink=always`) duplique les données sur la même machine
- **Pas de sous-traitant tiers** : Rediacc fonctionne sur votre infrastructure, pas sur les serveurs de Rediacc
- **Pas d'évaluation d'adéquation nécessaire** : les données ne quittent jamais la juridiction, donc les règles de transfert ne s'appliquent pas
- **Pas de clauses contractuelles types** : il n'y a pas de flux de données international à réguler

## Couverture juridictionnelle

### Union européenne

Le [RGPD](https://gdpr-info.eu/) restreint les transferts de données personnelles hors de l'UE/EEE sauf si la destination offre une protection adéquate. L'arrêt Schrems II a invalidé le Privacy Shield UE-US, et l'[amende de 1,2 Md EUR contre Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) a démontré le coût d'erreurs dans les transferts transfrontaliers.

Rediacc auto-hébergé dans l'UE garde toutes les données dans l'UE. Aucun mécanisme de transfert n'est nécessaire. Voir [Conformité RGPD](/fr/docs/legal-gdpr) pour la correspondance au niveau des articles.

### Chine

La [PIPL](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) exige le stockage des données personnelles des citoyens chinois en Chine. Les transferts transfrontaliers nécessitent des évaluations de sécurité par la CAC. Rediacc auto-hébergé sur infrastructure chinoise évite entièrement les évaluations de la CAC.

### Brésil

La [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) exige des mesures de sécurité adéquates et restreint les transferts internationaux. L'auto-hébergement au Brésil élimine les préoccupations de transfert et satisfait l'exigence de l'Art. 46 par le chiffrement LUKS2 et l'isolation réseau.

### Inde

Le [DPDP Act (2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) restreint les transferts vers les pays non inscrits sur une liste approuvée. L'auto-hébergement sur infrastructure indienne signifie aucun transfert quel que soit le pays mis sur liste noire. Les secteurs gouvernemental et de défense de l'Inde préfèrent fortement les solutions on-premises.

### Turquie

Le [KVKK (Loi n. 6698)](https://kvkk.gov.tr/en/) restreint les transferts internationaux avec des exigences d'adéquation complexes. La Turquie n'est pas sur la liste d'adéquation de l'UE. L'auto-hébergement en Turquie élimine entièrement cette problématique.

### Corée du Sud

Le [PIPA](https://www.pipc.go.kr/eng/index.do) est l'un des plus stricts au monde et impose explicitement le chiffrement des données personnelles lors du stockage et de la transmission. LUKS2 AES-256 satisfait directement cette exigence. Amendes jusqu'à 3% du chiffre d'affaires.

### Japon

L'[APPI](https://www.ppc.go.jp/en/legal/) restreint les transferts transfrontaliers sauf si le pays destinataire offre une protection adéquate. L'auto-hébergement au Japon évite les restrictions de transfert.

### Australie

Le [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) tient l'entité divulgatrice responsable du traitement par le destinataire étranger (APP 8). L'auto-hébergement élimine entièrement cette responsabilité. Le chiffrement LUKS2 et l'isolation réseau fournissent des "mesures raisonnables" concrètes sous APP 11.

### Emirats arabes unis

Le [Décret-Loi fédéral n. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) exige des mesures de sécurité adéquates et restreint les transferts transfrontaliers. Les secteurs gouvernemental et financier des EAU préfèrent fortement les déploiements on-premises.

### Arabie saoudite

Le [PDPL](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) exige que les données personnelles des résidents saoudiens soient stockées et traitées en Arabie saoudite. L'auto-hébergement satisfait directement cette exigence stricte de localisation.

### Singapour

Le [PDPA](https://sso.agc.gov.sg/Act/PDPA2012) exige une sécurité raisonnable et restreint les transferts transfrontaliers. L'auto-hébergement à Singapour, un hub de données majeur en APAC, satisfait la conformité régionale pour les opérations ASEAN.

### Russie

La [Loi fédérale 242-FZ](https://pd.rkn.gov.ru/) exige le stockage des données personnelles des citoyens russes sur des serveurs en Russie. Les violations peuvent entraîner le blocage de sites web. L'auto-hébergement en Russie assure la conformité par l'architecture.

## Le schéma

Dans toutes les juridictions, l'équation de conformité est la même :

| Propriété | Cloud/SaaS | Rediacc auto-hébergé |
|-----------|-----------|---------------------|
| Emplacement des données | Centres de données du fournisseur (peuvent traverser les frontières) | Votre machine, votre juridiction |
| Mécanisme de transfert nécessaire | Oui (CCT, adéquation, consentement) | Non (aucun transfert n'a lieu) |
| Responsabilité du sous-traitant tiers | Oui | Non |
| Contrôle du chiffrement | Clés gérées par le fournisseur | Vos identifiants LUKS, stockés localement |
| Données de clonage/staging | Peuvent traverser les frontières ou échapper à votre contrôle | CoW sur la même machine, même juridiction |
