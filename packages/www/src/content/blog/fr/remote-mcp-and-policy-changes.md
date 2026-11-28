---
title: "MCP distant : un agent qui ne lit que ce que sa personne peut lire"
description: "Le MCP distant tourne sur les trois Workers régionaux. Un grant porte la clé d'une config et les clés de politique de sa personne, jamais la clé maître, et aucun jeton ne survit au grant."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: fr
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **En bref.** Le MCP distant donne à un agent IA une URL plutôt qu'un terminal. La vraie question de conception n'était pas de connecter l'agent, mais de savoir ce qu'il a le droit de voir une fois connecté. La réponse : exactement ce que voit la personne qui a créé le grant, et rien de plus.
>
> - Un grant atteint **une seule config** et vit dans **une seule région**.
> - Les jetons durent au plus **1 heure** (accès) et **30 jours** (rafraîchissement), jamais plus longtemps que le grant.
> - Le grant porte la clé de contenu d'une config et deux **clés de lecture de politique**, jamais la clé maître du config store.
> - Le format des enregistrements de politique a changé. Les anciens sont refusés, sans chemin de migration.

## Une URL, pas un shell de connexion

Le serveur MCP local (`rdc mcp serve`) tourne à côté de l'agent et hérite des accès de la machine qui l'héberge. Le serveur distant fonctionne autrement. Un Worker MCP tourne dans chaque région à l'adresse `mcp.<region>.rediacc.cloud`, et chaque agent se connecte à l'URL d'un grant : `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Les appels d'outils s'exécutent sur l'exécuteur de l'organisation, pas sur le portable d'un développeur.

Les clients interactifs comme claude.ai s'authentifient par OAuth 2.1 avec PKCE. Les agents sans interface envoient un jeton `rmcp_<grantId>.<secret>`. Les deux formes identifient le grant, et l'identifiant dans l'URL ne fait que le nommer.

## Le grant est la frontière

Un grant est un objet petit et précis. Il désigne une config, une échéance et un périmètre : un indicateur lecture seule, une liste d'outils autorisés, et des motifs de noms de machines et de dépôts.

Trois règles en découlent :

- **Une config.** Un `tools/call` qui nomme une autre config est refusé avec `REDIACC_GRANT_SCOPE` avant que quoi que ce soit ne s'exécute. Qui possède trois configs crée trois grants.
- **Une région.** Les identifiants de grant commencent par leur région. Une requête arrivée sur le mauvais Worker reçoit une réponse HTTP 421 avec la bonne URL, sans jamais être transmise.
- **Une durée.** Un jeton d'accès dure le plus court entre 1 heure et le temps restant au grant. Un jeton de rafraîchissement dure le plus court entre 30 jours et le temps restant au grant. Chaque rafraîchissement relit le grant, donc un grant révoqué cesse de fonctionner à l'échange suivant. Présenter deux fois un jeton de rafraîchissement révoque le grant.

Une URL de grant vit 7 jours par défaut, 30 jours au maximum.

## Jugé comme sa personne

Le point intéressant tient aux clés. Un grant est un secret partagé en deux. Le navigateur tire une valeur aléatoire et ne l'affiche qu'une fois. Le serveur de comptes ne conserve que l'empreinte d'une étiquette dérivée, et l'exécuteur ne dérive la clé de slot que tant qu'il détient les deux moitiés. Cette clé de slot ouvre la clé de contenu de la config, jamais la clé maître de l'organisation.

La même clé de slot ouvre aussi deux **clés de politique**. La politique, c'est-à-dire les règles d'autorisation d'une entrée de config, vit désormais dans son propre enregistrement, scellé sous une clé dérivée de la clé du store et du pointeur de l'enregistrement : store, config, équipe et génération de clé. Le grant porte la clé de sa config d'équipe et celle de la config de niveau organisation. Ce sont les deux enregistrements de politique que sa personne lit, donc l'exécuteur lit les mêmes.

Résultat : un agent est jugé comme sa personne. Le plafond est la politique de l'organisation, restreinte par celle de l'équipe. L'agent n'agit que là où un consentement humain et ce plafond l'autorisent tous deux. Il ne peut ni modifier la politique, ni lire les valeurs des secrets, ni élargir son propre grant. Une clé que l'organisation verrouille est ignorée dans une politique d'équipe, et l'agent subit ce résultat comme la personne.

Lier chaque clé à un pointeur a un effet de bord utile. Qui détient une clé de politique ouvre les enregistrements de ce pointeur sous cette génération de clé, et aucun autre. Un blob servi pour un autre store, une autre config ou une autre équipe, ou rejoué sous une autre version, échoue au contrôle d'intégrité.

## Ce qui change pour les installations existantes

- **Les enregistrements de politique passent en version 2.** Un enregistrement de version 1, scellé sous la clé du store elle-même, ne s'ouvre pas. C'est une rupture franche, voulue.
- **Les écritures hébergées subissent la même politique.** Les écritures de config faites par l'exécuteur hébergé sont vérifiées contre le plafond de politique avant d'être enregistrées.
- **Les agents locaux gardent le même plafond.** `REDIACC_ALLOW_CONFIG_EDIT` autorise toujours un agent à modifier la config pour les pointeurs qu'il nomme, mais seulement dans les limites de la politique.
- **Un grant expiré ou une clé tournée échoue clairement.** `initialize` et `tools/list` répondent toujours, et chaque appel renvoie `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` ou `REDIACC_KEY_ROTATED` avec une `reauthUrl`.

Chaque grant autorise 60 appels par minute et 5 en parallèle.

## Ce que rapporte une URL divulguée

Une URL divulguée agit comme cet utilisateur sur sa seule config, jusqu'à son expiration ou sa révocation. Elle n'ouvre aucune autre config de l'organisation, ni rien en dehors de l'exécuteur hébergé de sa région. La sortie des outils parvient bien au fournisseur de modèle que l'utilisateur connecte. Rediacc ne choisit pas ce fournisseur.

Le guide d'installation est [MCP Server Setup](/fr/docs/ai-agents-mcp), et l'organisation des clés est décrite dans le [modèle de sécurité](/fr/docs/security-model).
