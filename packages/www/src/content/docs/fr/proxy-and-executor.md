---
title: Proxy et executor
description: >-
  Comment les commandes du navigateur et du client léger s'exécutent sans que
  le client ne détienne jamais de clés SSH ni d'adresses machine
category: Concepts
order: 4
language: fr
sourceHash: "3f522a473a550b0c"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy et executor

Normalement, `rdc` s'exécute sur votre machine avec votre configuration et vos clés SSH, et se connecte directement à vos serveurs. Le modèle proxy scinde cela en deux : un client léger qui ne détient aucun secret, et un **executor** qui les détient et fait le travail. Le bouton Exécuter de la [console web](/fr/docs/web-console) et le flag `--proxy` du CLI sont tous deux des clients légers, et ils parlent le même protocole.

## L'intention de la commande, pas la commande elle-même

Un client léger ne détient jamais de clé SSH, d'adresse machine ni de configuration déchiffrée. Quand il veut exécuter quelque chose, il n'envoie que l'intention de la commande : un identifiant pour la commande (son chemin dans le contrat CLI, par exemple `repo up`) plus les paramètres. L'executor recherche la commande dans le même contrat, la résout vers la fonction côté serveur correspondante, résout la machine cible depuis la configuration déchiffrée, puis l'exécute via sa propre connexion SSH. La sortie est renvoyée en flux au client.

L'executor est le CLI lui-même, démarré en tant que serveur avec `rdc serve`. Le même binaire que les opérateurs utilisent sur un ordinateur portable devient l'outil qui exécute des commandes en leur nom. Il a deux modes de déploiement :

- **`--mode daemon`** : s'exécute sur un hôte que vous contrôlez, enrôlé sans interface comme n'importe quel CLI (voir [Stockage de configuration](/fr/docs/config-storage)), il peut donc dériver la clé de configuration lui-même et n'a besoin d'aucune autorisation par session. C'est le niveau le plus strict : le SSH ne quitte jamais votre réseau.
- **`--mode container`** : s'exécute dans un conteneur hébergé pour vous, propre à votre organisation. Il démarre sans aucune clé et ne peut rien faire tant qu'un client ne lui en accorde pas une pour la session. C'est le niveau le plus pratique.

## L'octroi de la CEK

Le stockage de configuration est à connaissance nulle : le serveur ne stocke jamais que des blobs chiffrés, et la clé de chiffrement de contenu (CEK) n'existe en clair que sur un client qui l'a déverrouillée. Un executor en mode conteneur doit donc se voir *accorder* la clé, et cet octroi ne doit à aucun moment l'exposer au serveur.

Le déroulement : un navigateur déverrouillé ouvre une session avec l'executor, reçoit la clé publique de cette session, puis scelle la CEK pour cette session via X25519. Le blob scellé transite par le serveur de compte, mais celui-ci ne peut pas l'ouvrir, si bien que la connaissance nulle est préservée de bout en bout. L'executor déchiffre la CEK uniquement en mémoire vive, avec une expiration d'inactivité de 30 minutes ; rien n'est jamais écrit sur disque. Les requêtes de commande suivantes référencent la session accordée via l'en-tête `X-Config-Session`.

Un détail compte pour l'audit : la même identité d'utilisateur couvre les trois étapes (ouverture de la session, octroi de la clé, exécution des commandes). Le serveur de compte ne transmet jamais son propre identifiant à l'executor. Pour chaque étape, il émet un token de courte durée attribué à l'utilisateur réel, et revérifie l'appartenance de cet utilisateur à chaque fois. L'executor vérifie le token qui lui est présenté avant d'agir. Un octroi effectué par un utilisateur ne peut pas être utilisé par un autre.

La moitié « state » d'une configuration (les données d'exécution locales à l'hôte) ne transite jamais dans le blob de configuration, elle n'atteint donc jamais un executor par ce chemin non plus.

## Ce qui peut passer par un proxy

Toutes les commandes n'ont pas de sens à distance. Chaque commande du contrat porte un flag `proxyCapable`, que l'executor applique côté serveur, indépendamment de toute configuration de politique :

- Les **commandes du plan machine, non interactives** (déploiement, sauvegarde, statut, logs, etc.) sont compatibles avec le proxy.
- Les **commandes du plan configuration** ne le sont pas : elles modifient la configuration, ce qui sur ce chemin reste le travail du navigateur (la console web les route plutôt vers son éditeur de configuration).
- Les **commandes interactives** (terminaux, sessions VS Code) ne le sont pas : il n'y a pas de TTY sur ce fil.
- Les **commandes de transfert côté client** (`rdc repo sync`) ne le sont pas : elles déplacent des données entre le système de fichiers du *client* et une machine, et l'executor n'a pas accès aux fichiers du client.

La console web lit le même flag pour décider si une commande obtient un bouton Exécuter, mais l'executor refuse les commandes non compatibles quoi que le client envoie.

## L'executor simulé

En développement, quand aucun executor réel n'est configuré, le serveur de compte répond lui-même aux requêtes de commande avec des flux simulés et des données clairement fictives (noms de ressources préfixés par `mock-`). Cela permet d'exercer l'ensemble de la console, formulaires, flux et rendu des résultats compris, sans machine ni déverrouillage. L'exécution réelle nécessite un véritable executor.

## Voir aussi

- [Console Web](/fr/docs/web-console), le client navigateur construit sur ce modèle
- [Stockage de configuration](/fr/docs/config-storage), le store à connaissance nulle que protège la CEK
