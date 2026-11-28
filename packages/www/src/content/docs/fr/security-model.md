---
title: Modèle de sécurité
description: Qui peut voir quoi dans le stockage de configuration, comment les clés sont cloisonnées, ce que les agents et le MCP distant peuvent atteindre, et ce qui est récupérable.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: fr
sourceHash: "dd01eccb85dd4e7c"
sourceCommit: "467795d4f62f378389037e0027cac2676125b437"
---

# Modèle de sécurité

Cette page indique ce que protège le stockage de configuration, quelle clé ouvre quoi et ce que chaque type d'appelant peut atteindre. Pour la mise en place, voir [Stockage de configuration](/fr/docs/config-storage) ; pour les sessions et les jetons, voir [Sécurité du compte et API](/fr/docs/account-security).

## Qui peut voir quoi

![Hiérarchie des clés](/img/security-key-hierarchy.svg)

*Le serveur détient les clés de la couche SDK et de la phrase secrète de l'organisation ; seuls les détenteurs d'emplacements de clé déballent la CEK.*

![Qui peut voir le contenu des configurations](/img/security-who-can-see.svg)

*Ce que chaque type d'attaquant peut lire.*

Une configuration stockée est chiffrée en trois couches. La couche du SDK et la couche de la phrase secrète de l'organisation sont gérées par le serveur. La couche intermédiaire est la clé de chiffrement du contenu (CEK), que seuls les détenteurs d'un emplacement de clé peuvent déverrouiller : un secret d'emplacement conservé sur l'appareil se combine avec un secret détenu par le serveur, et aucune des deux moitiés ne l'ouvre seule.

| L'attaquant détient | Voit le contenu de la configuration | Pourquoi |
|---|---|---|
| Une copie de la base de données seule | Non | Les blobs de configuration résident dans le stockage d'objets, pas dans la base de données |
| La base de données et le stockage d'objets | Non | La couche de la phrase secrète de l'organisation exige le secret du Worker, et la couche CEK un secret d'emplacement |
| Une compromission complète du serveur | Pas sans secret d'emplacement | Les couches serveur tombent, mais la CEK reste derrière la sortie PRF du passkey ou le kit de récupération de 160 bits, et aucun des deux ne se devine |
| L'appareil d'un membre retiré | Ce qui a déjà été récupéré | Les versions ultérieures restent fermées après une rotation de la CEK |
| Une URL d'agent divulguée | Une configuration, en tant que cet utilisateur | Voir [Agents et MCP distant](#agents-and-remote-mcp) |

Le serveur voit encore les métadonnées (identifiants de configuration, équipes, versions, horodatages, tailles de blob) et peut refuser, retarder ou supprimer des requêtes. Un opérateur qui sert un code de portail malveillant peut lire les clés dans le navigateur. Chaque blob est lié à son stockage, à sa configuration, à son équipe et à sa version : le serveur ne peut donc pas en échanger ou en modifier un sans être détecté, et la CLI refuse toute version plus ancienne que celle qu'elle a déjà vue.

## Portée des clés

![Portée des clés](/img/security-key-scope.svg)

*Un magasin et une CEK par organisation ; les équipes relèvent du contrôle d'accès, pas de clés séparées.*

- Un stockage de configuration par organisation et une CEK par stockage. Les équipes relèvent du contrôle d'accès côté serveur, pas d'un isolement cryptographique : un kit de récupération ou un emplacement de clé ouvre la CEK de toute l'organisation.
- Les emplacements de clé sont uniques par stockage, utilisateur et méthode, donc un kit de récupération par utilisateur et par organisation. Un utilisateur présent dans deux organisations détient deux kits, et il n'existe pas de kit d'équipe.
- Un secret de machine est unique par machine et par organisation, et sert à enrôler une machine sans interface.
- Chaque configuration a sa propre clé de contenu sous la CEK. Une délégation d'agent porte la clé de contenu d'une seule configuration, si bien qu'aucune autre configuration de l'organisation ne s'ouvre avec elle.
- La politique d'autorisation de chaque configuration est un enregistrement distinct, sous une clé dérivée de la CEK et du pointeur de l'enregistrement. Le détenteur d'une clé de politique n'ouvre que les enregistrements de ce pointeur.

## Agents et MCP distant

![Flux MCP distant](/img/security-remote-mcp-flow.svg)

*Un appel client passe par le Worker MCP jusqu'à l'exécuteur de l'organisation ; une autorisation expirée renvoie le client se réautoriser.*

Une délégation d'agent est le type de détenteur de clés qui se cache derrière une URL de MCP distant. Elle porte la clé de contenu d'une configuration ainsi que les clés de politique de la configuration d'équipe de la délégation et de la configuration au niveau de l'organisation, jamais la CEK : un agent lit donc exactement ce que lit la personne qu'il représente.

- **Durée de vie.** Une URL vit 7 jours par défaut et 30 jours au plus, puis elle expire ou est révoquée. Une délégation expirée est refusée et le client réautorise.
- **Périmètre.** Une délégation atteint une configuration et appartient à une région (eu, us ou asia). Une URL présentée à une autre région est refusée avec la bonne région indiquée, et n'est jamais transmise. Les installations sur site comptent une seule région.
- **Politique.** Un agent n'agit que là où un consentement humain et le plafond de la politique l'autorisent tous deux. Le plafond est la politique de l'organisation restreinte par celle de l'équipe. Un agent ne peut ni modifier la politique, ni lire des valeurs secrètes, ni élargir sa propre délégation.
- **Rayon d'impact.** Une URL divulguée agit comme cet utilisateur sur sa seule configuration jusqu'à son expiration ou sa révocation. Elle n'ouvre rien en dehors de l'exécuteur hébergé de sa région.

La sortie des outils parvient au fournisseur de modèle que l'utilisateur connecte, et que Rediacc ne choisit pas.

### Sur site

Cloudflare n'intervient pas. Les secrets de Worker du cloud deviennent des variables d'environnement ou de la configuration sur l'hôte du client : l'accès à l'hôte remplace donc la frontière du secret de Worker du tableau ci-dessus, et les appels d'outils s'exécutent sur l'exécuteur démon du client.

## Politique

![Plafond de politique](/img/security-policy-ceiling.svg)

*Un agent n'agit que là où l'accord humain et l'intersection des politiques de l'organisation et de l'équipe le permettent.*

La politique est un enregistrement distinct, scellé par entrée de configuration avec des données authentifiées qui lient stockage, configuration, équipe, version et génération de clé. Le serveur ne peut pas la lire, et un enregistrement rejoué ou échangé échoue à son étiquette d'intégrité. Les enregistrements de politique en version 1 sont refusés.

Seul un propriétaire ou administrateur de l'organisation écrit la politique de l'organisation, et seul un administrateur d'équipe (ou un propriétaire ou administrateur) écrit celle de son équipe. Une écriture exige la 2FA et une session élevée, ainsi qu'un passkey lié lorsque le stockage impose les passkeys. Chaque membre et chaque exécuteur qui les sert la lit. Une clé verrouillée par l'organisation est ignorée dans une politique d'équipe.

## Ce qui est récupérable

![Voies de déverrouillage et de récupération](/img/security-unlock-recovery.svg)

*Chaque méthode de déverrouillage aboutit à la CEK, et le kit de récupération est obligatoire.*

| Situation | Récupération |
|---|---|
| Passkey perdu | Déverrouiller avec le kit de récupération, puis enrôler un nouveau passkey |
| Kit perdu | Le régénérer depuis un passkey fonctionnel ; l'ancienne version imprimée cesse de fonctionner |
| Les deux perdus | Un propriétaire ou administrateur rajoute le membre via la passation de membre |
| Le dernier détenteur de clé perd les deux | Irrécupérable, d'où le conseil d'avoir un second détenteur de clé |
| Membre retiré | Ses emplacements et jetons disparaissent aussitôt ; une rotation de la CEK ferme les versions ultérieures à une clé qu'il aurait conservée |
| Rotation de la CEK | Réenveloppe la CEK sous une nouvelle génération et invalide tous les kits de récupération |

Le serveur refuse toute suppression d'emplacement, tout retrait de membre ou tout départ de membre qui laisserait moins de deux détenteurs de clé et aucun emplacement de récupération. Chaque membre reçoit un kit de récupération obligatoire à l'enrôlement, et le conserver relève de sa responsabilité.
