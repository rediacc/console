---
title: "Article 21(2)(d) est une question de fournisseur. L'auto-hébergement est la réponse que vous cessez de devoir."
description: "Pourquoi le registre des tiers-TIC se réduit lorsque le plan de données ne quitte jamais votre périmètre. Lecture pratique de l'Article 21(2)(d) de NIS2 pour les RSSI et les responsables achats qui renégocient leurs DPA en 2026."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - chaine-approvisionnement
  - auto-heberge
  - souverainete
  - conformite
featured: false
language: fr
sourceHash: "30fcebe300afa3f2"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

> **En bref.** L'Article 21(2)(d) de NIS2 fait du risque lié à la chaîne d'approvisionnement une question de niveau conseil d'administration, et non une note de bas de page dans un contrat d'achat. La directive n'impose pas réellement l'auto-hébergement. Elle demande en revanche ce qui se trouve dans votre chemin de données et ce qui vous arrive quand l'un de ces fournisseurs connaît une mauvaise journée. Une infrastructure auto-hébergée effondre trois des quatre couches présentes sur la plupart des chemins de données SaaS. Elle n'effondre pas les quatre, et prétendre le contraire est le geste marketing qui met un RSSI en difficulté face à un auditeur.
>
> - Le texte de la directive et les orientations de l'ENISA, expliqués clairement.
> - Le chemin de données SaaS en quatre couches que la plupart des équipes oublient de schématiser.
> - Ce que le modèle à deux outils de Rediacc retire de votre registre fournisseurs, et ce qu'il y laisse.
> - Une liste de contrôle en six questions pour tout fournisseur se réclamant "prêt pour NIS2".

En juillet 2020, Blackbaud a payé une rançon et en a informé le monde après coup. L'entreprise a notifié plus de 13 000 organisations clientes après les faits, a dû faire face à des actions collectives dans sept juridictions, et a finalement payé 49,5 millions de dollars dans le cadre de règlements avec les procureurs généraux des États américains, ainsi qu'une amende de 3 millions de dollars de la SEC pour des communications trompeuses. Chacune de ces 13 000 organisations disposait d'un accord de traitement des données (DPA) avec Blackbaud. La plupart avaient examiné le rapport SOC 2 de Blackbaud. Beaucoup avaient Blackbaud dans un registre des risques fournisseurs, avec une cote de criticité, une date de renouvellement et un responsable désigné.

Rien de tout cela n'a arrêté la cascade. Les données se trouvaient du côté de Blackbaud. Lorsque leur environnement de sauvegarde a été compromis, toutes les organisations clientes ont été atteintes simultanément.

L'Article 21(2)(d) de NIS2 pose une question plus difficile que "avez-vous audité votre fournisseur". Il demande ce qui se trouve dans le chemin de données et ce qui vous arrive quand ce fournisseur connaît une mauvaise journée. La réponse, pour la plupart des équipes, est : "nous sommes eux, et nous ne l'avions pas réalisé."

Cet article s'adresse aux RSSI et aux responsables achats qui renégocient leurs DPA en 2026. C'est une lecture axée sur le chemin de données de l'Article 21(2)(d), non sur les certifications. Il est également honnête sur ce que l'infrastructure auto-hébergée ne résout pas, car la section sur les lacunes est ce qu'un auditeur demandera et qu'une brochure commerciale passera sous silence.

## Ce qu'oblige réellement l'Article 21(2)(d)

Le texte de la directive, légèrement condensé pour la clarté :

> "Les États membres veillent à ce que les entités essentielles et importantes prennent les mesures techniques, opérationnelles et organisationnelles appropriées et proportionnées pour gérer les risques qui menacent la sécurité des réseaux et des systèmes d'information que ces entités utilisent [...] et elles comprennent au moins: [...] d) la sécurité de la chaîne d'approvisionnement, y compris les aspects liés à la sécurité concernant les relations entre chaque entité et ses fournisseurs ou prestataires de services directs"

Deux éléments de ce texte importent pour un acheteur.

Premièrement, l'obligation vous incombe, et non au fournisseur. Les certifications du fournisseur, son SOC 2, son ISO 27001 constituent des données d'entrée pour votre évaluation des risques. Ils n'en sont pas un substitut. Si votre fournisseur affiche une posture de conformité parfaite mais est quand même compromis, la question du régulateur portera sur votre gestion du risque fournisseur, pas sur la sienne.

Deuxièmement, l'obligation va au-delà du contrat. Les orientations d'exécution 2024 de l'ENISA, à l'Annexe IV du Règlement d'exécution de la Commission (UE) 2024/2690, décrivent la pratique attendue : tenir un registre des fournisseurs TIC, les classer par criticité, évaluer chacun pour le risque qu'il représente pour vos opérations et pour les données qu'il traite, et renouveler l'évaluation à une cadence définie. L'Annexe IV nomme explicitement "les fournisseurs des fournisseurs" comme étant dans le périmètre, ce qui est là où la plupart des équipes découvrent que leur registre fournisseurs n'est pas vraiment un registre -- c'est une liste de contrats avec une étiquette.

Si vous abordez cela du côté des achats, la traduction pratique est la suivante : tout fournisseur disposant d'un accès logique à vos données de production doit être répertorié, évalué, surveillé et remplaçable. "Remplaçable" est la partie qui remet en question la plupart des arrangements existants.

## Le chemin de données SaaS en quatre couches que la plupart des équipes oublient de schématiser

Asseyez-vous avec un responsable achats et examinez ce qui se passe lorsque le produit d'un fournisseur de sauvegarde écrit un seul enregistrement. Le chemin de données honnête ressemble à ceci, de haut en bas :

1. L'**application du fournisseur**. Le code qui ingère vos données, prend des décisions de routage et applique la logique métier. S'exécute sur l'infrastructure du fournisseur. Maintenu, corrigé et surveillé par le fournisseur.
2. Le **cloud du fournisseur**. La région d'hyperscaler ou le datacentre propre du fournisseur où s'exécute l'application. Volumes de stockage, réseau, IAM. Souvent un hyperscaler avec lequel le fournisseur a conclu un accord de sous-traitant.
3. La **garde des clés du fournisseur**. Les clés de chiffrement qui protègent les données au repos dans le cloud du fournisseur. Dans la plupart des arrangements SaaS, c'est le fournisseur qui les détient. Les "clés gérées par le client" sont parfois disponibles en option de niveau supérieur ; dans ces arrangements, les clés se trouvent quand même dans un KMS d'hyperscaler que l'IAM du fournisseur peut appeler.
4. Les **sous-traitants du fournisseur**. Les services tiers qu'utilise le fournisseur (CDN, observabilité, facturation, outils de support client) qui peuvent transiter ou stocker vos données, ou des métadonnées qui en sont dérivées.

Chacune de ces quatre couches constitue une entrée dans votre registre fournisseurs au titre de l'Article 21(2)(d). Chacune a son propre historique d'incidents, son propre rayon d'explosion en cas de violation, sa propre surface de négociation contractuelle. Lorsque vous renouvelez avec le fournisseur SaaS, vous renouvelez les quatre implicitement, car le contrat du fournisseur SaaS est le seul que vous pouvez négocier.

L'incident Blackbaud était une violation de couche 2 (cloud du fournisseur) qui s'est propagée à travers la couche 1 (application du fournisseur) et était visible par tous les clients en raison de la couche 3 (garde des clés du fournisseur -- dans leur cas, des clés côté serveur sans séparation par locataire dans la base de données affectée). Les sous-traitants de Blackbaud n'étaient pas le vecteur de la violation, mais les clients ont découvert trois d'entre eux qu'ils n'avaient pas répertoriés.

## Blackbaud, la garde des clés façon Druva, et le schéma de cascade

Trois détails des dépôts SEC de Blackbaud sont ceux qui importent pour une lecture NIS2.

Premièrement, Blackbaud détenait les clés de chiffrement des données clients, y compris pour l'environnement de sauvegarde qui était la cible de la violation. Les clés gérées par le client n'étaient pas proposées. Dans le contentieux SEC post-incident, cela a été qualifié de lacune de contrôle, et non de violation, car les contrats de Blackbaud le permettaient. La perspective de NIS2 sur le même arrangement, au titre de l'Article 21(2)(d), est plus sévère, car le client ne peut pas évaluer de manière significative le risque d'un contrôle sur lequel il n'a pas de visibilité.

Deuxièmement, la violation a touché des données de sauvegarde plus anciennes que la base de données en production. Les organisations clientes dont les données en production avaient été supprimées des systèmes primaires de Blackbaud avaient encore des données exposées via l'environnement de sauvegarde. C'est le schéma de cascade : une compromission d'un fournisseur atteint des données historiques que le client pensait déjà hors périmètre.

Troisièmement, plus de 13 000 organisations clientes ont reçu des notifications de violation. Beaucoup d'entre elles étaient de petites associations à but non lucratif et des établissements scolaires qui n'avaient aucune capacité opérationnelle pour répondre, pas de guide de reprise après sinistre, pas de second fournisseur de sauvegarde vers lequel basculer. L'incident du fournisseur est devenu, en ce sens, leur incident.

Pour une sauvegarde SaaS moderne façon Druva, l'architecture est meilleure sur certains points (la séparation des clés par locataire est plus courante, le BYOK est proposé aux niveaux supérieurs) mais le chemin de données en quatre couches est identique. L'application du fournisseur, le cloud du fournisseur (typiquement AWS), la garde des clés (parfois par le fournisseur, parfois BYOK dans le KMS du client, parfois hybride), les sous-traitants. Une violation à n'importe quelle couche atteint simultanément tous les clients, car les données de chaque client se trouvent du même côté de la frontière.

C'est l'argument structurel. Ce n'est pas un réquisitoire contre Druva. Druva gère un navire plus rigoureux que ne le faisait Blackbaud. L'argument est que la structure de tout produit de sauvegarde conçu nativement en SaaS rend les violations de couche 2 et de couche 3 une obligation au titre de l'Article 21(2)(d) que le client ne peut pas s'acquitter de manière significative.

## L'auto-hébergement effondre trois des quatre couches

Rediacc est construit différemment. L'architecture complète est documentée sur la [page Architecture](/fr/docs/architecture), mais la forme pertinente pour la chaîne d'approvisionnement est deux binaires qui communiquent via SSH :

- `rdc` s'exécute sur le poste de travail de l'opérateur. Il lit un fichier de configuration JSON plat (sous `~/.config/rediacc/`), se connecte aux propres machines de l'opérateur via SSH, et distribue des commandes.
- `renet` s'exécute sur le propre serveur de l'opérateur, avec les droits root, et gère les images disque chiffrées LUKS2, les daemons Docker isolés et le proxy inverse.

L'opérateur ne se connecte jamais à l'infrastructure de Rediacc-en-tant-que-société pour exécuter une sauvegarde, une restauration ou un fork. Il n'y a pas de cloud Rediacc-en-tant-que-société dans le chemin de données. La clé LUKS du dépôt est stockée dans le fichier de configuration local de l'opérateur (mode `0600`), jamais sur le serveur, jamais envoyée à Rediacc. Le chemin de données ressemble à ceci :

1. **Poste de travail de l'opérateur.** Exécute `rdc`. Détient la clé LUKS.
2. **Propre serveur de l'opérateur.** Exécute `renet`. Détient les dépôts chiffrés LUKS2.
3. **Propre cible de sauvegarde de l'opérateur.** Tout stockage compatible rclone (S3, B2, OneDrive, MinIO sur site). Reçoit les volumes chiffrés.

Il n'y a pas de couche 4. Rediacc-en-tant-que-société n'est pas un sous-traitant pour tout opérateur qui n'a pas opté pour l'[adaptateur Cloud](/fr/docs/architecture) expérimental. Pour les opérateurs auto-hébergés, la relation avec Rediacc-en-tant-que-société est une licence logicielle, pas un accord de traitement des données.

C'est l'argument du chemin de données, et c'est le bon argument pour ouvrir une conversation sur le registre fournisseurs. Un concurrent SaaS peut proposer des clés gérées par le client (et la plupart des solutions modernes le font). Un concurrent SaaS ne peut pas proposer "nous ne sommes pas un sous-traitant."

Le second point, une fois l'argument du chemin de données posé, est la garde des clés. Avec Rediacc, la clé LUKS se trouve dans le fichier de configuration de l'opérateur, un point c'est tout. Il n'y a pas d'entiercement de clé, pas de service de récupération que Rediacc-en-tant-que-société pourrait exécuter si l'opérateur perd la clé. C'est également l'architecture recommandée pour le [magasin de configuration à connaissance zéro](/fr/docs/config-storage), où la clé de chiffrement est dérivée côté client à partir d'une extension PRF passkey et le serveur stocke des blobs opaques. Le serveur ne peut pas lire les clés SSH, les clés LUKS, les adresses IP ou toute configuration en clair. La rotation du jeton d'accès ne donne pas au serveur une lecture rétroactive.

Pour l'Article 21(2)(h) (chiffrement), cela importe. Pour l'Article 21(2)(d) (chaîne d'approvisionnement), cela importe davantage, car cela supprime le dernier chemin d'accès logique de Rediacc-en-tant-que-société aux données de l'opérateur.

## Ce que l'auto-hébergement n'effondre pas

L'auto-hébergement déplace la liste des fournisseurs, il ne la supprime pas. Trois choses qu'un auditeur demandera encore :

**1. Vous avez toujours des fournisseurs, simplement différents.** Le fournisseur de matériel (Hetzner, Hostinger, OVH, votre colocation, votre propre métal nu). L'hyperviseur (KVM, VMware). Le système d'exploitation (Debian, Ubuntu, RHEL). Le registre de conteneurs (Docker Hub, GHCR, votre registre privé). Les images de base que vos services récupèrent. Chacun de ces éléments est une entrée au titre de l'Article 21(2)(d). L'auto-hébergement déplace la liste des fournisseurs, il ne la supprime pas.

**2. Rediacc ne dispose pas encore d'ISO 27001, de SOC 2 ou de BSI C5.** Ceux-ci sont sur la feuille de route, pas encore obtenus. Pour une équipe achats qui utilise les certifications comme mécanisme de filtrage, c'est une vraie friction. La réponse défendable est celle que cet article développe : l'argument du chemin de données signifie que la majeure partie de ce que ces certifications attestent (contrôles de sécurité du cloud du fournisseur, gestion des accès du personnel du fournisseur, gestion des sous-traitants du fournisseur) n'est pas dans le périmètre, car Rediacc-en-tant-que-société ne se trouve pas dans le chemin de données. Cet argument doit être présenté avec soin et de manière défendable, et non comme substitut aux certifications quand ce sont les certifications dont l'acheteur a besoin.

**3. La couche GRC reste à votre charge.** Rediacc donne à l'opérateur un journal d'audit à chaîne de hachage de plus de 70 événements (`rdc audit verify` valide la chaîne de bout en bout). Il ne vous fournit pas un registre fournisseurs, un cadre de contrôle ou un flux de collecte de preuves. Ceux-ci proviennent toujours de Drata, Vanta, OneTrust ou de l'un des entrants européens. L'article complémentaire sur [la vraie facture](/fr/blog/nis2-the-real-bill) couvre en détail la structure de coût de cette complémentarité.

## Le DPA que vous n'avez plus à négocier

Pour rendre cela concret, voici une ligne "avant / après" d'un registre issu d'une véritable conversation d'achat, anonymisée. L'acheteur est une entreprise manufacturière allemande de 280 salariés, classée comme "entité importante" au sens de l'Annexe II. Son entrée initiale dans le registre fournisseurs pour la sauvegarde ressemblait à ceci :

| Champ | Avant |
|---|---|
| Fournisseur | Acme Backup SaaS |
| Criticité | Critique |
| Données traitées | Base de données de production, données personnelles clients, documents financiers |
| Sous-traitants | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Statut contractuel | DPA signé en 2023, CCT annexées, calendrier des mesures revu pour la dernière fois en janvier 2025 |
| Garde des clés | Géré par le fournisseur (option BYOK non disponible au niveau actuel) |
| Plan de sortie | "Le fournisseur s'engage à fournir un export de données en CSV dans les 30 jours suivant la résiliation" |
| Dernière évaluation | T1 2025, lacune notée sur la garde des clés, différée au renouvellement |

Après migration vers Rediacc sur Hetzner :

| Champ | Après |
|---|---|
| Fournisseurs | (1) Rediacc OÜ, licence logicielle ; (2) Hetzner, IaaS |
| Criticité | (1) Non critique (pas de plan de données) ; (2) Critique (plan de données, mais contrôlé par le client) |
| Données traitées | (1) Aucune ; (2) Volumes chiffrés, client détient les clés |
| Sous-traitants | (1) Aucun pour l'auto-hébergé ; (2) Interne Hetzner uniquement, listé dans leur DPA |
| Statut contractuel | (1) Licence logicielle, pas de DPA requis ; (2) DPA Hetzner + CCT déjà en place |
| Garde des clés | Client (clé LUKS dans la configuration de l'opérateur, pas sur le serveur) |
| Plan de sortie | "rdc repo backup pull depuis toute cible compatible rclone. Volumes chiffrés LUKS2 ; l'opérateur détient la clé." |
| Dernière évaluation | (2) couverte par la revue IaaS existante |

Deux entrées dans le registre au lieu d'une. L'entrée de criticité critique est pour le fournisseur IaaS, pour lequel l'acheteur avait déjà un DPA en place et un plan de sortie testé, car l'IaaS est une relation que la plupart des équipes savent gérer. L'entrée Rediacc est non critique car c'est une licence logicielle, pas un processeur de données.

C'est la raison structurelle pour laquelle un RSSI finit par vouloir moins de dépendances SaaS dans le plan de données, même si le coût d'achat semble similaire dans un tableur. L'entrée dans le registre n'a pas la même forme.

## Liste de contrôle pour les achats

Pour tout fournisseur se réclamant "prêt pour NIS2" lors d'un cycle de vente 2026, six questions :

**1. Où se trouve la clé de chiffrement de nos données au repos ?** Si la réponse est "dans notre HSM" ou "dans le KMS de notre client que nous pouvons appeler via IAM", le fournisseur se trouve dans votre chaîne de garde des clés. Si c'est "dans votre fichier de configuration local, jamais sur notre infrastructure", ils n'y sont pas.

**2. Qui dans votre entreprise peut techniquement lire nos données, sans tenir compte des termes juridiques ?** Pas "qui est autorisé à le faire" mais "qui pourrait, s'ils le voulaient et si le journal d'audit était désactivé." Si la réponse est non nulle, c'est votre population pour une évaluation du risque d'initié.

**3. La restauration est-elle testée sur un clone de production réel, ou sur des données de test synthétiques ?** Les Articles 21(2)(c) et (e) lus ensemble exigent que la sauvegarde se restaure effectivement. Un fournisseur qui ne valide que sur des données synthétiques ne valide pas la récupération -- il valide l'intégrité du fichier de sauvegarde. (Pour plus d'informations, voir l'article complémentaire sur l'[évaluation continue de l'efficacité](/fr/blog/nis2-effectiveness-without-theatre).)

**4. Votre piste d'audit enregistre-t-elle le type d'acteur, humain ou agent, derrière chaque action ?** L'activité des agents IA est la catégorie du journal d'audit qui croît le plus vite. Un journal d'audit 2026 qui ne distingue pas l'humain de l'agent ressemblera à une lacune en 2027.

**5. Listez chaque sous-traitant qui a un accès logique à nos données, y compris les métadonnées.** "Accès logique" est la bonne formulation. "Accès logique incluant les métadonnées" est la meilleure, car l'accès aux seules métadonnées est ce que les sous-traitants de facturation, d'observabilité et de support client ont typiquement, et c'est suffisant pour révéler une structure sensible même lorsque la charge utile est chiffrée.

**6. Quel est votre plan de sortie si vous êtes acquis par un acheteur non-européen en 2027 ?** Le cadre d'adéquation du RGPD, le Cloud Act et la FISA 702 sont tous des cibles mouvantes. La revendication de résidence des données d'un fournisseur aujourd'hui n'est pas une garantie dans trois ans. La question de l'acheteur est de savoir ce qui arrive au chemin de données si la propriété du fournisseur change.

Un fournisseur qui répond clairement aux six questions sur six est rare. Un fournisseur qui répond à quatre sur six et reconnaît ouvertement les deux autres est plus digne de confiance que celui qui répond à toutes les six avec assurance. Le signal de crédibilité est la volonté de nommer ce qui n'est pas résolu.

## Ce que cela implique pour le prochain cycle de renouvellement

Si vous vous apprêtez à renouveler un contrat de sauvegarde ou de reprise après sinistre dans les douze prochains mois et que l'Article 21(2)(d) figure dans votre grille d'évaluation des achats, trois actions concrètes :

1. Schématisez le chemin de données en quatre couches de votre fournisseur actuel sur un tableau blanc. Si vous ne pouvez pas nommer le troisième sous-traitant, vous avez un problème d'exhaustivité du registre qui prédate NIS2, et le renouvellement est le bon moment pour le corriger.
2. Appliquez la liste de contrôle en six questions ci-dessus à votre fournisseur en place. Envoyez les réponses à votre DPO et à votre auditeur et demandez si les lacunes sont acceptées. Si les lacunes incluent la couche 3 (garde des clés) ou la couche 4 (sous-traitants que vous n'avez pas répertoriés), c'est le levier.
3. Examinez à quoi ressemblerait un registre fournisseurs alternatif avec un plan de contrôle auto-hébergé. Comparez les entrées du registre, pas les coûts de licence. Les coûts de licence sont similaires à un facteur deux près ; les entrées du registre ont des formes différentes. (L'article complémentaire sur [le coût structurel de la pile NIS2](/fr/blog/nis2-the-real-bill) détaille ce qui se contracte et ce qui reste.)

Si nous sommes l'alternative dans votre liste restreinte, l'offre est concrète. Envoyez-nous votre questionnaire fournisseur. Nous le remplirons sur la base d'une instance déployée, avec nos réponses réelles à vos questions, y compris les lacunes. Si vous souhaitez parcourir l'architecture avant d'envoyer des documents, nous réserverons une revue d'architecture de 30 minutes avec le fondateur. Le chemin vers une entrée défendable dans le registre n'est pas une brochure brillante. Ce sont les réponses, y compris les plus inconfortables.

Pour la cartographie publique des capacités de Rediacc par rapport aux articles de NIS2, voir [NIS2 et DORA](/fr/docs/legal-nis2-dora). Pour le cadre de conformité plus large, voir [Vue d'ensemble de la conformité](/fr/docs/legal-overview), [Souveraineté des données](/fr/docs/legal-data-sovereignty) et [Sur site](/fr/docs/on-premise).
