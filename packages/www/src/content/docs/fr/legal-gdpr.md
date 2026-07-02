---
title: "Conformité RGPD"
description: "Comment l'architecture auto-hébergée de Rediacc correspond aux exigences du RGPD pour la protection des données et la vie privée."
category: "Legal"
order: 1
language: fr
sourceHash: "76d2b3a911e0d14c"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Le Règlement Général sur la Protection des Données (RGPD) est la loi de l'Union européenne sur la protection des données, en vigueur depuis mai 2018. Il régit la manière dont les organisations collectent, traitent et stockent les données personnelles des individus dans l'UE.

Texte intégral : [Règlement (UE) 2016/679](https://gdpr-info.eu/)

## Correspondance des articles

Le tableau ci-dessous met en correspondance les articles spécifiques du RGPD avec les capacités techniques de Rediacc.

| Article | Exigence | Capacité Rediacc |
|---------|----------|-----------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Principes | Minimisation des données, intégrité, confidentialité | Les clones CoW (`cp --reflink=always`) dupliquent les données sur la même machine sans transfert réseau. LUKS2 AES-256 chiffre toutes les données au repos. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Droit à l'effacement | Supprimer les données personnelles sur demande | `rdc repo delete` efface cryptographiquement le volume LUKS. La suppression d'un fork retire entièrement la copie clonée. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Protection des données dès la conception | Vie privée par défaut | Le chiffrement est obligatoire, pas optionnel. Chaque dépôt dispose d'un Docker daemon isolé et d'un réseau dédié. Aucun partage de données entre dépôts. Le magasin de configuration utilise le chiffrement à connaissance nulle : les configurations sont chiffrées côté client avec AES-256-GCM avant l'envoi, le serveur ne peut donc lire aucune donnée en clair. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Sous-traitant | Obligations de traitement des données par un tiers | Auto-hébergé : Rediacc s'exécute sur votre infrastructure. Aucune donnée ne quitte votre machine pendant les opérations de fork, clone ou sauvegarde. Aucun composant SaaS ne traite de données personnelles. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Registre des traitements | Tenir un registre des activités de traitement | La journalisation d'audit trace plus de 40 types d'événements au niveau du compte : authentification, jetons API, opérations du magasin de configuration et licences. Export via le tableau de bord d'administration ou la page d'activité du portail (export JSON disponible). |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Sécurité du traitement | Mesures techniques appropriées | Chiffrement LUKS2 AES-256 au repos, isolation réseau via iptables et Docker daemons séparés, sous-réseaux IP loopback (/26) par dépôt. Le magasin de configuration utilise un chiffrement à triple couche : clés SDK à fenêtre temporelle, dérivation CEK à clé fractionnée (passkey + secret serveur) et chiffrement par phrase secrète de l'organisation. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Notification de violation | Notification sous 72 heures avec piste forensique | Les journaux d'audit fournissent une piste forensique de toutes les opérations. L'architecture auto-hébergée limite le rayon d'impact aux dépôts individuels. |

## Résidence des données

Les clones CoW ne quittent jamais la machine source. La commande `rdc repo fork` crée une copie au niveau du système de fichiers en utilisant des reflinks. Aucune donnée n'est transférée sur le réseau.

Pour les opérations inter-machines, `rdc repo push/pull` transfère les données via SSH. La destination de sauvegarde reçoit des volumes chiffrés LUKS qui ne peuvent être lus sans les identifiants de l'opérateur.

## Clonage d'environnement et masquage des données

Lors du clonage d'environnements de production pour le développement ou les tests, le hook de cycle de vie `up()` du Rediaccfile exécute des scripts de nettoyage après la création d'un fork : supprimer les données personnelles des bases de données, remplacer les adresses e-mail réelles par des adresses de test, retirer les jetons API et les données de session, anonymiser les fichiers de logs. L'environnement de développement obtient la structure de production sans les identités de production, satisfaisant le principe de minimisation des données ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Magasin de configuration à connaissance nulle

Le magasin de configuration optionnel permet la synchronisation des configurations CLI entre appareils. Il est conçu pour que le serveur n'ait aucune connaissance du contenu des configurations :

- **Chiffrement côté client** : Les configurations sont chiffrées avec AES-256-GCM avant l'envoi. La clé de chiffrement (CEK) est dérivée d'un secret passkey PRF et d'un secret côté serveur en utilisant HKDF avec séparation de domaine. Aucune des deux parties ne peut dériver la clé seule.
- **Le serveur ne voit que des blobs opaques** : Clés SSH, identifiants, adresses IP, topologie réseau. Rien de cela n'est visible pour le serveur. Seules les métadonnées (identifiants de configuration, versions, horodatages) sont stockées en clair.
- **Accès des membres via X25519** : Lorsqu'un membre d'équipe est ajouté, la CEK est chiffrée avec sa clé publique X25519 et relayée par le serveur. Le serveur ne voit jamais la CEK en clair.
- **Révocation immédiate** : La suppression d'un membre efface sa CEK encapsulée et révoque ses jetons. Les configurations futures utilisent de nouvelles époques SDK inaccessibles au membre retiré.
- **Jetons rotatifs** : L'authentification CLI utilise des jetons rotatifs à usage unique (fenêtre de tolérance de 3 requêtes), liés à l'IP lors de la première utilisation, avec expiration automatique de 24 heures.

Même une compromission totale du serveur ne peut pas exposer le contenu des configurations. Le serveur n'a jamais la clé.

Pour plus de détails, consultez [Stockage de configuration](/fr/docs/config-storage).

## Responsable du traitement et sous-traitant

Puisque Rediacc est un logiciel auto-hébergé, votre organisation est à la fois le responsable du traitement et le sous-traitant. Rediacc (l'entreprise) n'accède pas à vos données, ne les traite pas et ne les stocke pas. Aucun accord de traitement des données n'est requis avec Rediacc pour le produit auto-hébergé, car aucune donnée personnelle ne transite par l'infrastructure de Rediacc.

Le magasin de configuration est le seul composant qui touche les serveurs de Rediacc (pour la synchronisation), mais sa conception à connaissance nulle signifie que le serveur ne stocke que des blobs chiffrés qu'il ne peut pas déchiffrer.
