---
title: "Java4Shell : notre CPU était concerné, notre serveur n'avait pas de Java, et nos templates nous ont appris le pinning"
description: "CVE-2026-114938 demande un CPU AVX-512 VBMI et un JDK affecté. Notre serveur avait le CPU, mais zéro JVM. Le vrai travail s'est joué dans les templates d'applications que nous livrons, où un seul tag épinglé avait figé un JDK de 2023."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: fr
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **TL;DR.** Java4Shell (CVE-2026-114938) est une écriture hors limites dans le tas, dans le décodeur Base64 compilé par le JIT d'OpenJDK. Elle ne se déclenche que sur les CPU x86-64 dotés d'AVX-512 VBMI.
>
> - Le CPU de notre serveur de production **possède les quatre flags requis**. Sur le seul critère du CPU, il semblait exposé.
> - Une sonde sur **43 conteneurs**, l'hôte et les dépôts arrêtés n'a trouvé **aucun runtime Java**. Un essai témoin de la même sonde, cherchant `python3`, l'a trouvé partout où il devait être. Rien à patcher sur le serveur.
> - Les templates d'applications que nous livrons, c'était une autre histoire. **Quatre** d'entre eux démarrent une JVM. **Trois** utilisent des tags flottants et ont déjà été reconstruits en amont avec des JDK corrigés le 20 novembre.
> - **Un seul**, Elasticsearch, était épinglé sur `8.11.0` : une image de novembre 2023 avec le JDK embarqué `21.0.1`. Elastic n'a pas encore de version corrigée, donc le template démarre désormais Elasticsearch avec le flag de mitigation d'Elastic, vérifié sur un nœud en marche.

## Ce qui a été divulgué

Le 17 novembre, des chercheurs de Calif ont publié **Java4Shell**, et Oracle et OpenJDK ont livré des correctifs le jour même. Le bug se trouve dans le décodeur Base64 accéléré matériellement de HotSpot : le chemin AVX-512 VBMI traite mal les derniers caractères et peut écrire après la fin d'un buffer du tas. Un attaquant distant sans compte peut en tirer une corruption mémoire et, dans la bonne application, une exécution de code. L'analyse détaille des chaînes pré-authentification pour plusieurs produits serveur Java bien connus.

Les points qui comptent pour le tri :

- **Affectés :** OpenJDK 17.0.6 et suivants, 21, 25 et 27, avant les builds corrigés. Java 8 et Java 11 standard ne sont pas concernés.
- **Corrigés :** 17.0.21.1, 21.0.13.1, 25.0.5.1 et 27.0.1.1 (les builds Temurin portent `+2`, ou `+4` pour la 27). Un runtime qui affiche `17.0.21` sans le `.1` est toujours vulnérable.
- **Préconditions :** un CPU x86-64 avec AVX-512 VBMI, un JIT qui a déjà compilé le décodeur, et un chemin applicatif qui décode du Base64 provenant d'une entrée non fiable. ARM n'est pas concerné.
- **Score :** 9,2 en CVSS 4.0, 8,1 en CVSS 3.1. Une preuve de concept autonome est publique. Aucune exploitation dans la nature n'avait été signalée au moment de la rédaction.
- **Mitigation :** démarrer la JVM avec `-XX:-UseBASE64Intrinsics`. L'autre option publiée, `-XX:UseAVX=2`, fonctionne aussi sur x86-64 mais empêche une JVM ARM de démarrer.

Notre [précédent passage de patchs](/fr/blog/patching-nginx2root-and-php-fork-first) s'est terminé par un déploiement fork d'abord de quatre applications. Celui-ci s'est arrêté bien plus tôt, et la raison est ce qui est intéressant.

## Étape 1 : le CPU est-il concerné ?

La plupart des CVE ont une précondition logicielle. Celle-ci a aussi une précondition matérielle, facile à vérifier :

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Les quatre y sont. La machine tourne sur un AMD EPYC 9354P, un CPU serveur récent avec un support AVX-512 complet. Si le tri s'était arrêté là, la réponse aurait été « exposé, patcher tout ce qui est Java ce soir ».

![Les trois préconditions : le CPU est concerné, la vérification du JDK échoue, donc le chemin d'entrée n'est jamais atteint](/img/blog-java4shell-preconditions.svg)

## Étape 2 : y a-t-il du Java à patcher ?

Le CPU n'est qu'un maillon de la chaîne. Le second est un JDK affecté, et la question suivante était donc simple : quels conteneurs exécutent du Java ?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Nous l'avons lancée via `rdc term connect <repo>@hostinger` pour chaque dépôt de la machine. Le `find` sur `libjvm.so` repère les JVM embarquées dans un dossier d'application et absentes du `PATH`, ce qui est le cas d'Elasticsearch, par exemple, qui livre son propre JDK.

Le résultat était vide. Ni `java` ni `libjvm.so` dans les 43 conteneurs en cours d'exécution.

Un résultat vide ne prouve rien tant que la sonde n'a pas montré qu'elle sait trouver quelque chose. La même boucle a donc été relancée, cette fois pour `python3`, dont nous savons qu'il se trouve dans les conteneurs ERPNext. Elle a trouvé Python 3.14 dans chacun d'eux. La sonde fonctionne : le serveur n'a simplement pas de Java.

Deux endroits de plus ont été vérifiés avant de clore la question. L'hôte lui-même n'avait pas de Java ni de `/usr/lib/jvm`. Les dépôts sans rien en cours d'exécution n'avaient aucune image Java sur leurs démons Docker. L'un d'eux contenait un checkout de notre propre monorepo, dont les fichiers compose mentionnaient `cassandra:5.0` et `elasticsearch:8.11.0`. Cela menait à l'étape suivante.

## Étape 3 : les templates que nous livrons

Rediacc livre des templates d'applications prêts à l'emploi : un `docker-compose.yaml` plus un Rediaccfile par application. Un serveur que nous n'exploitons pas peut les déployer. Une image Java dans un template est donc une exposition pour chaque client avec le bon CPU, même quand notre propre serveur est propre.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Quatre templates démarrent une JVM. Pour deux d'entre eux, la config de l'image dans le registry nomme déjà le JDK. Pour les deux autres, non, nous avons donc lancé chaque image une fois pour poser la question :

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Template | Tag dans le template | JDK à l'intérieur aujourd'hui | Statut |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | corrigé en amont, reconstruit le 20 nov. |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | corrigé en amont, reconstruit le 20 nov. |
| Solr | `solr:9-slim` | 17.0.21.1+2 | corrigé en amont, reconstruit le 20 nov. |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (embarqué) | **vulnérable**, pas encore de version corrigée d'Elastic |

![Épinglé contre flottant : l'image Elasticsearch épinglée a gardé un JDK de 2023, les tags flottants ont été reconstruits avec le correctif](/img/blog-java4shell-pinned-vs-floating.svg)

## La leçon du pinning, révisée

L'article précédent se terminait par « épingler des tags exacts ». Ce passage ajoute une note de bas de page à cette règle.

Épingler est la bonne approche pour les applications que nous exploitons et mettons à jour volontairement. Le pin rend la version en cours visible, et un tag flottant peut pointer vers un correctif pendant que le serveur continue d'exécuter une ancienne image, car `docker compose up -d` ne télécharge pas une image qu'il a déjà.

Pour les templates que les gens déploient à neuf, le tableau s'inverse. Les trois tags majeurs flottants (`5.0`, `5-community`, `9-slim`) ont récupéré le JDK corrigé trois jours après le correctif, sans rien changer de notre côté. Le seul pin exact, `8.11.0`, a figé Elasticsearch sur une image construite en novembre 2023, avec un JDK qu'aucune reconstruction de ce tag ne corrigera.

La règle que nous gardons a donc deux moitiés. Les applications de production reçoivent des tags exacts et une mise à jour délibérée. Les templates aussi sont épinglés, car Elasticsearch et Kibana doivent tourner dans la même version, mais chaque pin de template figure désormais dans notre registre des pins, où les gates de fraîcheur signalent un pin qui prend du retard au lieu de le laisser dormir trois ans.

## Étape 4 : la mitigation, prouvée sur un vrai nœud

Elastic a annoncé que le correctif arrivera sous forme de mise à jour du JDK embarqué dans les prochaines versions 8.19.26, 9.4.10, 9.5.7 et 9.6.0. D'ici là, la consigne officielle est le flag JVM. Dans le template, cela représente un mot de plus dans `ES_JAVA_OPTS` :

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Ce que change le flag : le JIT garde le décodeur Java classique au lieu de l'intrinsic AVX-512](/img/blog-java4shell-intrinsic-flag.svg)

Un flag dans un fichier compose n'est qu'une affirmation tant que la JVM ne le confirme pas. Nous avons vérifié deux fois. D'abord, le JDK embarqué lui-même, avec et sans le flag :

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Ensuite, un vrai cluster à nœud unique démarré avec les options du template. Il est passé au vert, et sa propre API listait le flag parmi les arguments de la JVM :

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Ce qui s'est mal passé

**La vérification du CPU a failli décider de la réponse.** C'est la précondition la plus visible, elle tient en une commande, et elle disait « exposé ». Seule la seconde vérification, celle d'une vraie JVM, a transformé une urgence de minuit en modification de template.

**Une suite de tests a tourné là où elle ne devait pas.** Pour vérifier la modification du template, nous avons lancé la suite de cycle de vie du package de templates sur un poste de travail. Cette suite est prévue pour un dépôt Rediacc sous licence, pas pour un hôte Docker nu, et elle a passé plus de dix minutes à démarrer d'autres templates. Elle a aussi montré qu'un template sans rapport écrivait son secret généré dans son propre dossier source, un fichier que personne ne voudrait voir dans un commit. Ce template écrit désormais le secret en dehors de l'arborescence source, et la suite refuse de démarrer sans le dépôt dont elle a besoin.

**Il n'y avait rien à forker.** Notre étape de sécurité habituelle, un fork du dépôt de production avant tout changement, n'avait pas de cible cette fois. La modification vivait dans un fichier de template dans git, donc le filet de sécurité était un commit relisable et un test de démarrage en conditions réelles, pas un snapshot.

## Les choix, et pourquoi

| Option envisagée | Ce que nous avons choisi | Pourquoi |
|---|---|---|
| Prendre la vérification du CPU pour la réponse | Chercher une vraie JVM | Le CPU disait exposé ; sans JVM, il n'y avait rien à exploiter. |
| Se fier à une sonde vide | Lancer un témoin qui doit trouver quelque chose | Le résultat vide d'une sonde cassée ressemble à celui d'un serveur propre. |
| Lire la version du JDK dans le registry | Lancer chaque image une fois | Deux des quatre images n'enregistrent pas la version du JDK dans leur config. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Plus ciblé : cela désactive une seule routine, pas toutes les accélérations AVX-512, et une JVM ARM démarre toujours. |
| Passer Elasticsearch à la dernière 8.19 maintenant | Garder 8.11.0, ajouter le flag, monter de version à la sortie de la version corrigée | Les dernières versions disponibles aujourd'hui embarquent encore un JDK affecté, et Kibana doit changer dans la même étape. |
| Des pins exacts partout | Des pins exacts plus une gate de fraîcheur sur chaque pin de template | Un pin sans alarme a figé un JDK de 2023 ; la gate garde le pin et ajoute l'alarme. |

## La checklist que nous gardons

1. Vérifier chaque précondition, pas seulement la première qui correspond.
2. Chercher le runtime lui-même (`java`, `libjvm.so`), pas seulement un nom de produit.
3. Prouver chaque sonde vide avec un témoin.
4. Balayer ce que nous livrons, pas seulement ce que nous exploitons.
5. Lire la version à l'intérieur de l'image ; lancer l'image quand la config est muette.
6. Préférer la mitigation la plus ciblée, et la confirmer dans le processus en cours.
7. Suivre la version corrigée de l'éditeur et retirer la mitigation dès qu'elle sort.

Comme lors du précédent passage, un agent IA (Claude Code) a fait le travail via `rdc`, avec un accès à la production accordé par l'opérateur avant le début de la session. Cette fois, la production n'a pas changé du tout : chaque étape sur le serveur était une lecture, et l'unique correctif est passé dans un template, via git, avec un test en conditions réelles derrière.
