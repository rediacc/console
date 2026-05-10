---
title: "Votre test d'intrusion annuel, c'est du théâtre de conformité. L'Article 21(2)(f) de NIS2 vient de le rendre problématique."
description: "Évaluation continue de l'efficacité, le fork à temps constant qui la rend abordable, et le calendrier de notification de l'Article 23 que vous ne pouvez pas tenir sans artefacts de niveau forensique."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - sre
  - test-reprise
  - efficacite
  - notification-incident
featured: false
language: fr
sourceHash: "21965e5d5e9f25d5"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

> **En bref.** La plupart des programmes de sécurité testent la reprise une fois par an, contre un environnement de staging forké depuis la production à un moment de l'été dernier. Ils commandent un test d'intrusion contre un environnement qui ne ressemble pas à la production, obtiennent un rapport propre, et le classent. L'Article 21(2)(f) de NIS2 vient d'introduire une formulation sur laquelle les auditeurs vont s'appuyer fermement : "des politiques et des procédures pour évaluer l'efficacité" des mesures. Annuel n'est pas continu. Un staging obsolète n'est pas le système à l'épreuve.
>
> - La directive dit : 21(2)(e) et (f) ensemble exigent une reprise et des tests de sécurité qui fonctionnent réellement, à la demande, sur la production courante.
> - Le coût de bien faire les choses avec les outils de type Delphix, Veeam Instant Recovery ou Rubrik Live Mount est ce qui pousse la plupart des équipes à opter discrètement pour le staging.
> - Quand un fork de production prend sept secondes, l'économie s'inverse. Des exercices hebdomadaires deviennent réalistes. L'efficacité continue devient documentable.
> - La notification selon l'Article 23 (alerte précoce à 24 heures, notification à 72 heures, rapport à un mois) est impossible à tenir sans artefacts de niveau forensique. Nous fournissons les artefacts ; le SOC, le SIEM et le flux de dépôt auprès de l'ENISA restent de votre ressort.

Entrez dans n'importe quelle équipe SRE de taille moyenne et posez une question : quand avez-vous fait pour la dernière fois une reprise complète de bout en bout, pas une vérification de fichier de sauvegarde, mais vraiment démarré le système récupéré avec les applications, les bases de données et les configurations, et validé qu'il fonctionne ? La réponse honnête, dans la plupart des équipes, est "lors de l'exercice sur table de l'an dernier." Puis tout le monde reprend le travail.

L'Article 21(2)(f) de NIS2 introduit une formulation sur laquelle les auditeurs vont s'appuyer fermement :

> "des politiques et des procédures pour évaluer l'efficacité des mesures de gestion des risques en matière de cybersécurité"

Il ne dit pas "annuel." Il dit "des politiques et des procédures." Lu conjointement avec l'Article 21(2)(e), qui impose :

> "la sécurité de l'acquisition, du développement et de la maintenance des réseaux et des systèmes d'information, y compris le traitement et la divulgation des vulnérabilités"

l'obligation est continue, non périodique. Les orientations de mise en oeuvre de l'ENISA de 2024 (Annexe IV du Règlement d'exécution (UE) 2024/2690) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> confirment cette orientation avec des formulations comme "évaluation permanente" et "preuves documentées des tests couvrant les environnements de production actuels, et non des instantanés obsolètes ou de staging."

Si votre histoire d'efficacité se résume à "test d'intrusion annuel contre le staging," 2026 va être inconfortable.

Ce billet est destiné aux responsables SRE, aux directeurs opérationnels et aux ingénieurs sécurité qui effectuent réellement les exercices. C'est aussi le billet qui nomme le levier qu'un acteur établi utilisera dans tout contre-argumentaire : les services de reporting géré et les connecteurs SIEM pour les délais de l'Article 23. Nous ne résolvons pas cela. Nous vous fournissons les artefacts. Le flux de reporting, le SOC, le moteur de dépôt auprès de l'ENISA, ceux-là restent de votre ressort.

## Lire 21(2)(e) et (f) ensemble

L'Article 21 liste dix mesures minimales. Deux d'entre elles portent sur la façon dont vous construisez et dont vous vérifiez.

e) **Sécurité dans l'acquisition, le développement et la maintenance** : il s'agit de la mesure du côté de l'offre. Quand vous acceptez un correctif CVE, quand vous déployez un nouveau microservice, quand vous effectuez une fenêtre de maintenance, le changement doit être validé contre l'environnement réel dans lequel il va être intégré. Les orientations de l'ENISA sont explicites : les environnements de staging qui diffèrent de la production en termes de forme des données, d'échelle, de secrets ou de configuration ne satisfont pas l'obligation de test pour les changements à incidence sécuritaire.

f) **Évaluation de l'efficacité** : il s'agit de la mesure de vérification. Quels que soient vos contrôles, vous avez besoin de politiques et de procédures pour confirmer qu'ils fonctionnent réellement. La formulation "efficacité" fait un vrai travail. C'est la différence entre "nous avons une sauvegarde" (le contrôle existe) et "nous avons prouvé que nous pouvions la restaurer mardi dernier et que le système restauré a réussi un test de fumée" (le contrôle est efficace).

Lus ensemble, les deux mesures exigent que les changements à incidence sécuritaire soient testés dans des environnements équivalents à la production courante, et que les tests produisent des preuves que le changement a fonctionné. Annuel est trop rare. Un staging obsolète est la mauvaise cible. Une restauration non validée n'est pas efficace.

La réponse traditionnelle à cette obligation est ce que la plupart des équipes font déjà : déclarer que le staging ressemble à la production, effectuer des exercices contre le staging sur une cadence annuelle, rédiger un runbook décrivant ce qui se passerait lors d'un vrai incident, et espérer que le régulateur ne pose pas trop de questions. Cela fonctionnait quand le régulateur était l'autorité de contrôle RGPD et que l'incident était un événement lié à la vie privée. NIS2 place un régulateur différent dans le siège (le CSIRT national, ou le BSI en Allemagne, l'ANSSI en France, l'ACN en Italie), et ce régulateur pose des questions opérationnelles.

## Le piège du staging obsolète

Trois choses font que le staging n'est pas la production au moment où la plupart des équipes le testent.

**Forme des données** : les données de production ont des cas limites en longue traîne. Le client avec le champ notes de 8 000 caractères, le compte historique avec une valeur NULL là où toutes les autres lignes ont une valeur, la table jointe qui a renvoyé 12 millions de lignes pour le seul client qui a importé tout l'historique de son CRM. Le staging représente 1 % du volume de production et la longue traîne n'est pas dans l'échantillon.

**Échelle** : une requête qui répond en 50 ms contre 10 000 lignes en staging répond en 8 secondes contre 12 millions en production. Un scénario de test d'intrusion qui ne trouve pas de vulnérabilité d'épuisement en staging la trouve immédiatement en production. La forme de la vulnérabilité dépend de l'échelle des données.

**Dérive de configuration** : la production a accumulé des variables d'environnement, des rôles IAM, des politiques réseau, des secrets tournés trois fois, un certificat SSL renouvelé la semaine dernière, un indicateur de fonctionnalité qui était supposé être désactivé en mars mais qui est resté actif. Le staging a une copie propre de la configuration de l'été dernier plus ce qui a été ajouté pour le projet le plus récent. Les écarts se trouvent exactement là où se cachent les bugs de sécurité.

Ainsi, quand le correctif passe en staging, la confiance de l'équipe est mal placée. Quand le test d'intrusion rend un rapport propre contre le staging, le rapport est trompeur. Quand l'exercice de reprise restaure le staging avec succès, l'équipe n'a pas validé la reprise de la production.

Les auditeurs en 2026 ne débattent pas de la qualité suffisante du staging. Ils demandent des preuves de tests contre la production courante. Les preuves doivent être horodatées, montrer que le système testé ressemblait à la production au moment du test, et montrer que le test a produit un résultat.

La plupart des équipes ne peuvent pas produire ces preuves aujourd'hui, parce que le coût d'effectuer des exercices contre la production courante est prohibitif avec les outils traditionnels.

## Le coût de bien faire les choses avec les outils traditionnels

Le marché a des réponses. Les réponses sont coûteuses.

**Veeam Instant Recovery** : démarrer une VM directement depuis une sauvegarde, la monter, lui affecter une interface réseau. Utilisé pour les tests de reprise cohérents au niveau applicatif. Capable de tester la reprise depuis une sauvegarde récente ; l'environnement de staging devient la sauvegarde récupérée. Peu gourmand en capacité car les lectures disque viennent du dépôt de sauvegarde. Coût : le licensing Veeam Data Platform Premium évolue selon le nombre de VMs, et le test de reprise doit quand même être planifié et opéré par un ingénieur. La plupart des équipes effectuent cela une fois par trimestre.

**Rubrik Live Mount** : concept similaire, montage instantané d'un instantané de sauvegarde pour les tests. Meilleure intégration avec les charges de travail cloud-native. Même schéma opérationnel. Même surcoût d'ingénierie par test.

**Delphix (Perforce DevOps Data)** : outil de virtualisation de données qui crée des clones quasi-instantanés de bases de données source pour le développement et les tests. Résout le problème "nous voulons des données de forme production dans le dev." Uniquement base de données. Ne clone pas les services applicatifs, les configurations, les secrets ou l'état des conteneurs. La licence annuelle atteint six chiffres pour les équipes de taille intermédiaire.

**Tonic.ai, Redgate Test Data Manager** : approches par masquage et données synthétiques. Résolvent le compromis vie privée versus réalisme pour les environnements de dev et de test. Réalistes en termes de forme et d'échelle des données. Pas des clones full-stack. Pas conçus pour des scénarios de tests de sécurité où la configuration applicative importe.

**Construction maison** : prendre une sauvegarde à chaud, la restaurer dans un environnement parallèle, exécuter le test, le démonter. Conceptuellement possible. Opérationnellement un effort d'ingénierie de plusieurs jours par exercice. L'équipe le fait une fois parce qu'elle y a été contrainte, puis jamais plus.

Le problème structurel est que le clonage de production, full-stack et incluant l'état applicatif, a historiquement nécessité soit a) un transfert de données octet par octet (lent et coûteux à grande échelle), soit b) un clonage de VM par instantané (fonctionne pour l'IaaS, échoue pour les conteneurs et Kubernetes), soit c) la virtualisation de données (uniquement base de données). Les trois approches portent un coût par test qui évolue avec la taille de l'environnement.

Quand le coût par test évolue avec la taille, les exercices deviennent des événements rares. Les événements rares ne satisfont pas l'évaluation continue de l'efficacité.

## Ce qui change quand un fork de production prend sept secondes

Rediacc utilise les refliens BTRFS pour le fork de dépôt. Le mécanisme est un copy-on-write au niveau du système de fichiers : le fork partage des blocs avec le parent jusqu'à ce que l'un des deux écrive de nouvelles données, auquel cas seuls les blocs modifiés divergent. L'opération de fork elle-même est à temps constant indépendamment de la taille du dépôt.

Dans notre [billet de test PocketOS](/fr/blog/i-tested-rediacc-against-the-pocketos-incident), nous avons forké un dépôt de production de 128 Go en 7,2 secondes de bout en bout. Le reflen lui-même a pris 2,3 secondes. La majeure partie du reste correspond au provisionnement d'un nouveau daemon Docker, au montage du volume chiffré LUKS et au démarrage de la pile de services sur un nouveau sous-réseau loopback IP.

La forme du fork importe autant que la vitesse. Un fork Rediacc est full-stack. Le dépôt forké contient :

- Le volume chiffré LUKS avec tous les fichiers de données et l'état de la base de données.
- La configuration du daemon Docker et l'état des conteneurs.
- Les hooks de cycle de vie du Rediaccfile (`up`, `down`, `info`).
- Le sous-réseau loopback IP du dépôt (un nouveau `/26` découpé pour le fork).
- L'identifiant réseau du dépôt, la socket du daemon et l'espace de noms de montage.

Ce qu'il ne contient pas par défaut, ce sont les secrets dont vos services ont besoin pour communiquer avec des SaaS externes (Stripe, relais de messagerie, clés DKIM, clés de signature de webhook). Pour ceux-ci, `rdc repo secret` garde les identifiants hors de l'image du fork afin que les appels SaaS externes depuis un fork soient explicites, non hérités. Voir [Dépôts](/fr/docs/repositories) pour le modèle de secrets.

Cette forme, full-stack avec gestion explicite des secrets, est ce qui rend le fork adapté comme cible pour les tests de sécurité. Le fork est le système de production, avec les données de production courantes, la configuration de production courante, l'état actuel des conteneurs, dix secondes auparavant. C'est le système contre lequel l'auditeur veut que vous testiez.

Pour les cas d'usage documentés, voir [Mises à niveau sans risque](/fr/docs/risk-free-upgrades) et [Tutoriel : Fork](/fr/docs/tutorial-forking).

## Une routine d'efficacité continue exécutable chaque semaine

Voici une routine concrète qui satisfait l'Article 21(2)(e) et (f) pour un dépôt de production, exécutable sur une cadence hebdomadaire par un seul SRE.

**Étape 1** : forker la production.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

Le fork est nommé avec la semaine ISO pour que le journal d'audit soit auto-descriptif. Le dépôt est actif sous un sous-domaine spécifique au fork (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`) et le certificat wildcard du parent le couvre. Pas de nouvelle négociation TLS.

**Étape 2** : appliquer le correctif à tester, sur le fork.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

La session term s'exécute en tant qu'utilisateur non privilégié `rediacc` (UID 7111), dans un espace de noms de montage séparé, avec `DOCKER_HOST` limité à la socket du daemon du fork. L'accès entre dépôts est bloqué au niveau noyau (le fork ne peut pas atteindre le sous-réseau loopback de la production). Voir [Architecture - Isolation Docker](/fr/docs/architecture) pour le modèle d'isolation.

**Étape 3** : exécuter le test de fumée contre le fork.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (votre test de fumée spécifique au projet va ici)
```

**Étape 4** : exécuter l'exercice de restauration. Utiliser la sauvegarde à chaud la plus récente de la production, récupérée vers une cible alignée sur le fork.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# vérifier que le fork restauré répond au même test de fumée
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

C'est le test de reprise que 21(2)(c) et (f) demandent : non pas "l'intégrité du fichier de sauvegarde a été vérifiée" mais "le système récupéré répond à un test de fumée."

**Étape 5** : consigner le résultat dans le journal d'audit, puis démonter.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

Le journal d'audit capture chaque étape (création du fork, repo up, sessions term, backup pull, repo destroy). Il est chaîné par hachage. `rdc audit verify` sur le poste de travail de l'opérateur confirme que la chaîne n'a pas été modifiée depuis que les événements ont été écrits. Voir [Sécurité du compte - Posture de sécurité CLI pour les agents IA](/fr/docs/account-security) pour le modèle d'audit.

Le temps total d'exécution de la routine, sur un dépôt de 128 Go, est inférieur à 15 minutes. La majeure partie correspond au test de fumée et au temps de transit réseau pour le backup pull. Les opérations de fork elles-mêmes prennent quelques secondes chacune.

Un seul SRE exécutant cette routine une fois par semaine produit 52 enregistrements d'efficacité horodatés et consignés dans le journal d'audit par an. C'est la forme des preuves qu'un auditeur demande.

Pour l'histoire de reprise plus large incluant les exercices inter-machines et intercontinentaux, voir [Stratégie de sauvegarde croisée](/fr/docs/cross-backup) et [Sauvegarde et restauration](/fr/docs/backup-restore). Pour la sémantique de point dans le temps lors d'un événement de corruption partielle, voir [Reprise par voyage dans le temps](/fr/docs/time-travel-recovery).

## Article 23 : le calendrier de notification que vous ne pouvez pas tenir sans artefacts

L'Article 23 de NIS2 est l'horloge de notification des incidents. Trois délais :

- **24 heures** à compter de la prise de conscience d'un incident significatif : une alerte précoce au CSIRT national ou à l'autorité compétente. Indique que l'incident est en cours et fournit des informations initiales sur l'impact transfrontalier.
- **72 heures** à compter de la prise de conscience : une notification d'incident complète. Inclut l'évaluation de la sévérité, les indicateurs de compromission initiaux, le type de menace et l'impact connu.
- **Un mois** à compter de la notification : un rapport final. Description détaillée, cause profonde, mesures d'atténuation appliquées, risque résiduel.

C'est une horloge serrée. C'est aussi une horloge qui tourne pendant que l'incident est encore en cours. La version la plus douloureuse de l'Article 23 est celle où l'équipe est en train de restaurer les services, de préserver les preuves forensiques, de coordonner avec les forces de l'ordre, de briefer l'équipe de direction, et de rédiger l'alerte précoce, le tout dans les premières 24 heures.

Les outils de sauvegarde standard imposent un compromis : restaurer le système pour rétablir le service, ou préserver le système pour enquêter. Une fois que vous restaurez depuis une sauvegarde, les preuves vivantes de la compromission disparaissent. Une fois que vous figez le système compromis pour enquêter, vous ne servez pas les clients. Les deux sont mauvais dans un calendrier de l'Article 23.

Le mécanisme de fork résout ce compromis. L'état compromis peut être forké (le dépôt parent devient l'instantané forensique) et un fork parallèle peut être démarré depuis la sauvegarde propre la plus récente pour servir le trafic. Le fork forensique est en lecture seule pour l'analyse. Le fork de service répond aux clients. Les deux existent simultanément sur la même machine, partageant des blocs via reflen, ce qui explique pourquoi cela est opérationnellement abordable.

Concrètement, lors d'un incident :

```bash
# Instantané de l'état compromis pour la forensique. Le fork est l'instantané.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Démarrage d'un fork de service depuis la dernière sauvegarde propre. Étiquette différente.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Basculer le trafic vers le nouveau fork de service via DNS ou le serveur de route.
```

Le fork forensique répond à la question du régulateur à l'heure 60 : "montrez-nous l'état exact de vos systèmes au moment de la compromission." Le fork de service répond à la question du client. Le journal d'audit de plus de 70 événements répond à "qui a fait quoi, quand" de manière chaînée par hachage et vérifiable.

C'est ce que Rediacc donne à l'opérateur. Ce que nous ne donnons pas :

- **Le SIEM**. Nous ne diffusons pas vers Splunk, Datadog, Sentinel ou votre pile maison. Le journal d'audit est du JSONL local sur le poste de travail de l'opérateur ; le canaliser vers un SIEM est le travail d'intégration de l'opérateur.
- **Le SOC**. Nous ne gérons pas une capacité de détection 24h/24 7j/7. Nous ne produisons pas d'alertes. Nous ne faisons pas de triage.
- **Le reporting géré**. Nous ne déposons pas le rapport auprès de l'ENISA. Nous ne rédigeons pas l'alerte précoce. Nous ne coordonnons pas avec le CSIRT national en votre nom.

C'est le levier qu'un acteur établi utilisera contre nous. Veeam Data Platform avec les intégrations Coveware, Rubrik avec son bras de services gérés, et quelques firmes spécialisées en retainer de réponse aux incidents (Mandiant, Kroll, S-RM en Europe) vendent exactement la couche opérationnelle que Rediacc ne fournit pas. Prétendre le contraire est le geste marketing qui nous met en difficulté. La position défendable est : Rediacc vous donne des artefacts de niveau forensique que ces services ne peuvent pas produire seuls ; ces services vous donnent la couche de reporting opérationnel que Rediacc ne peut pas fournir. Ils sont complémentaires. Un programme NIS2 a besoin des deux.

## Ce que Rediacc ne gère pas pour vous

Deux choses qu'un SRE devrait connaître dès le départ, avant de décider que le reste du billet est intéressant.

**Rediacc ne gère pas les tests d'intrusion**. Le fork en tant que cible est l'environnement, pas la capacité de test. Un vrai test d'intrusion adversarial reste l'affaire de votre équipe rouge ou de votre cabinet de test contractuel (Pentera, Horizon3.ai pour l'autonome ; cabinets de conseil spécialisés pour le pilotage humain). Rediacc supprime leur excuse que l'environnement de test était irréaliste. Il ne supprime pas le coût du test.

**Rediacc ne rédige pas vos runbooks**. Les commandes CLI ci-dessus sont les éléments mobiles. Les décisions sur quand forker, quand basculer, comment communiquer avec les clients, quand engager les forces de l'ordre, sont des décisions de runbook. Celles-ci doivent quand même être rédigées, exercées et mises à jour par votre équipe. L'Article 21(2)(b) de NIS2 (gestion des incidents) est une obligation de processus, pas une obligation d'outillage, et nous en satisfaisons une partie, pas la totalité.

Pour le périmètre du côté des achats (certifications, GRC, effondrement du registre fournisseurs), voir le [billet sur la chaîne d'approvisionnement](/fr/blog/nis2-supply-chain-self-hosted). Pour le périmètre du côté des coûts (ce qui reste sur le poste budgétaire après un plan de contrôle auto-hébergé), voir le [billet sur la vraie facture](/fr/blog/nis2-the-real-bill).

La bonne lecture de ceux-ci : Rediacc est une couche d'outillage, pas un programme de sécurité. Il supprime les excuses et produit des preuves. Il ne gère pas le programme pour vous.

## Ce qu'un auditeur veut voir en 2026

Trois artefacts. Produisez-les et la conversation sur l'Article 21(2)(e) et (f) devient brève.

**Artefact 1 : la cadence des exercices de fork**. Un journal horodaté des exercices d'efficacité exécutés sur une cadence hebdomadaire ou bihebdomadaire sur douze mois glissants. Chaque entrée montre le dépôt parent, l'étiquette du fork, le correctif ou changement testé, le résultat du test de fumée et l'horodatage du démontage. Le journal d'audit produit par `rdc audit log --since` capture tout cela.

**Artefact 2 : le journal d'audit de ces exercices, chaîné par hachage**. La chaîne de hachage sur le journal d'audit est ce qui transforme "nous avons exécuté 47 exercices l'an dernier" d'une affirmation en preuve. `rdc audit verify` valide la chaîne de bout en bout. Le résultat de la validation est une sortie de commande unique qu'un auditeur peut réexécuter.

**Artefact 3 : la piste de vérification des sauvegardes**. Pour chaque stratégie de sauvegarde planifiée, l'unité systemd produit un fichier sidecar de statut à `/var/run/rediacc/cold-backup-<guid>.status.json` par dépôt et par exécution, ainsi qu'une ligne de journal de résumé finale. `rdc machine backup status` expose les deux. Combiné avec l'exercice de restauration hebdomadaire de l'Étape 4 de la routine ci-dessus, cela donne à l'auditeur une piste "sauvegarde-et-restauration-testée", et non seulement "sauvegarde-prise". Voir [Surveillance](/fr/docs/monitoring) pour la surface de diagnostic.

Les artefacts ensemble répondent à la question "vos contrôles sont-ils efficaces" avec des horodatages et des preuves chaînées par hachage, non par attestation.

## Ce que cela signifie pour la prochaine réunion de planification trimestrielle

Si votre équipe aborde la planification du T3 et que l'Article 21(2)(f) figure dans le backlog sécurité, trois actions concrètes :

1. Auditez votre histoire d'efficacité actuelle. Récupérez les douze derniers mois de rapports de tests d'intrusion, d'exercices de reprise et de tickets de validation de correctifs. Comptez combien d'entre eux ciblaient la production courante. Le compte honnête est généralement inférieur à cinq.
2. Choisissez un dépôt de production et exécutez la routine hebdomadaire ci-dessus contre lui pendant un mois. La routine est conçue pour être opérable par un seul SRE sans surcharge de planification. Après quatre semaines, vous avez quatre enregistrements d'efficacité horodatés ; c'est plus que ce que la plupart des équipes produisent en un an.
3. Ayez la conversation sur qui couvre le SIEM, le SOC et le flux de reporting de l'Article 23. Si la réponse est "nous n'en sommes pas encore là," le bon point de départ n'est pas Rediacc, c'est une capacité de détection 24h/24 7j/7. Nous sommes complémentaires à cette conversation ; nous n'en sommes pas le point de départ.

Si vous voulez voir le temps de fork sur votre plus grand dépôt, la proposition est simple. Exécutez-le lors d'un appel avec nous. Si le fork prend plus de dix secondes, vous ne nous devez rien. S'il prend sept secondes, nous passerons le reste de l'appel à parcourir la routine sur votre stack.

L'histoire des coûts structurels (ce qui s'effondre sur le reste de la pile sécurité et ce qui reste sur le poste budgétaire) se trouve dans le billet compagnon sur [la vraie facture](/fr/blog/nis2-the-real-bill). Pour l'angle registre fournisseurs et achats, voir [Article 21(2)(d) et l'auto-hébergement](/fr/blog/nis2-supply-chain-self-hosted).

Pour la cartographie publique des capacités aux articles NIS2, voir [NIS2 et DORA](/fr/docs/legal-nis2-dora).
