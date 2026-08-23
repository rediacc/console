---
title: Console Web
description: >-
  Exécutez tout le CLI rdc depuis votre navigateur, avec formulaires,
  sélecteurs de ressources et historique des exécutions
category: Guides
tags:
  - cli
  - account
subcategory: cli-tools
order: 8
language: fr
sourceHash: "972ed654ae294102"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Console Web

La console web est une interface navigateur qui couvre l'intégralité du CLI `rdc`. Chaque commande du CLI apparaît dans la console avec un formulaire, une validation, des sélecteurs de ressources et un bouton Exécuter. Il n'y a pas d'ensemble de fonctionnalités « web » séparé : la console est générée à partir du contrat CLI, si bien que toute commande présente dans le CLI se retrouve aussi dans la console, et les nouvelles commandes apparaissent automatiquement.

Elle se trouve dans le portail web, à `/account/console`.

## Disponibilité

La console web est une fonctionnalité payante. Elle est incluse dans les plans payants et masquée sur le plan Communauté. L'accès est également soumis aux rôles, un administrateur d'organisation peut donc contrôler qui la voit.

## Son lien avec le stockage de configuration

La console lit vos ressources (machines, dépôts, etc.) depuis votre store de configuration chiffré, et ne déchiffre cette configuration que dans le navigateur. Concrètement :

- **Tant qu'elle est verrouillée**, vous pouvez tout de même parcourir le catalogue complet des commandes, ouvrir le formulaire de n'importe quelle commande et lire ses paramètres. Cela fonctionne sans aucune configuration préalable.
- **Pour exécuter des commandes et utiliser les sélecteurs**, vous devez d'abord déverrouiller votre store de configuration (passkey, mot de passe principal ou code de récupération, voir [Stockage de configuration](/fr/docs/config-storage)). Les boutons Exécuter, les pages de ressources et les sélecteurs de ressources dépendent tous de la session déverrouillée.

La clé déchiffrée ne reste qu'en mémoire du navigateur. Rafraîchir la page verrouille de nouveau la console, et 30 minutes d'inactivité la verrouillent automatiquement.

## Sélecteurs de ressources

Une fois déverrouillés, les formulaires de commande remplacent les champs de texte libre par des sélecteurs alimentés par votre configuration déchiffrée : machines, dépôts, datastores, stockages, clusters, fournisseurs cloud et stratégies de sauvegarde. Certains sélecteurs sont résolus en direct plutôt qu'à partir de la configuration, en exécutant une commande, par exemple les conteneurs d'une machine ou les snapshots d'un datastore.

Les sélecteurs se filtrent les uns les autres : choisissez une machine et le sélecteur de dépôt se restreint à cette machine. Pour les références de dépôt, un constructeur de référence compose la forme complète `nom:tag@machine` à partir des choix individuels. Les sélecteurs sont des aides, pas des contraintes, vous pouvez toujours saisir une valeur manuellement.

## Exécuter des commandes

Le navigateur ne détient jamais de clé SSH ni d'adresse machine. Quand vous cliquez sur Exécuter, la console n'envoie que l'intention de la commande, quelle commande et quels paramètres, et un executor résout tout le reste et l'exécute. Voir [Proxy et executor](/fr/docs/proxy-and-executor) pour le fonctionnement détaillé et savoir quelles commandes peuvent s'exécuter ainsi.

Les commandes qui se contentent de modifier votre configuration (par exemple créer une entrée machine) ne s'exécutent jamais à distance. La console les route vers l'éditeur de configuration intégré, où la modification est chiffrée et poussée comme n'importe quel autre changement de configuration.

Chaque formulaire affiche aussi la ligne de commande CLI équivalente, de sorte que tout ce que vous configurez dans la console peut être copié directement dans un terminal ou un script.

## Se repérer dans la console

- **Pages de ressources** : machines, dépôts et jobs ont chacun des pages de liste et de détail, avec les commandes pertinentes attachées comme actions.
- **Palette de commandes** : appuyez sur Cmd-K (Ctrl-K) pour rejoindre n'importe quelle commande ou ressource par son nom.
- **Historique des exécutions** : les exécutions passées sont conservées par session, pour que vous puissiez revoir la sortie et relancer avec les mêmes paramètres.

## Voir aussi

- [Stockage de configuration](/fr/docs/config-storage), configurer et déverrouiller le store de configuration chiffré
- [Proxy et executor](/fr/docs/proxy-and-executor), le modèle d'exécution derrière le bouton Exécuter
