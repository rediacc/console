---
title: >-
  git diff pour les images disque chiffrées : comparer des forks sans les
  déchiffrer
description: >-
  rdc repo diff compare des images chiffrées au niveau des blocs et signale
  A/M/D/R. Aucune clé n'est utilisée. Le coût est proportionnel aux blocs
  modifiés, pas à la taille du dépôt.
author: Rediacc
publishedDate: 2026-05-28T00:00:00.000Z
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: fr
sourceHash: 1b08ca130594e2e4
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
---

> **TL;DR.** `rdc repo diff` affiche la différence au niveau fichier entre deux dépôts forkés, dans la grammaire de `git status --short` (A/M/D/R), sans jamais déchiffrer l'un ou l'autre.
>
> - Il compare les deux fichiers image LUKS au niveau des blocs via l'ioctl FIEMAP, qui ne lit que les métadonnées de la carte d'étendues. Aucune clé n'est chargée, aucun texte en clair n'est lu.
> - aes-xts conserve la longueur et chiffre chaque secteur de 512 octets indépendamment. Un secteur en texte clair modifié produit un secteur chiffré modifié au même décalage (décalé par le décalage de données LUKS de 16 Mio). Soustrayez le décalage, mappez les plages de blocs vers des noms de fichiers via la carte d'étendues ext4, et vous obtenez une liste de fichiers.
> - Le coût est proportionnel au nombre de blocs modifiés, pas à la taille du dépôt. Un fork de 1 Go et un fork de 100 Go se comparent en quelques millisecondes identiques, car la comparaison est purement sur les métadonnées.

Un fork dans Rediacc, c'est `cp --reflink=always` sur l'image LUKS d'un dépôt. Instantané, et indifférent à la taille. Un dépôt de 100 Go se forke aussi vite qu'un de 1 Go. Je sais que ça ressemble à du marketing, mais c'est juste le fonctionnement des reflinks : btrfs copie la carte d'étendues et partage les blocs en dessous. On s'appuie fortement là-dessus. Les forks sont le sandbox de test, la branche jetable, la copie de staging qu'on supprime quand on a terminé.

Ce qu'on n'avait pas, c'était une réponse bon marché à la question évidente suivante : qu'est-ce que ce fork a réellement changé ? La voie naïve : monter le fork, déverrouiller le conteneur LUKS, parcourir l'ext4 interne, hacher chaque fichier contre le parent. Ça évolue avec la taille du dépôt en lectures et en déchiffrement. Ça nécessite les clés actives sur le chemin du diff. Et ça jette la seule chose que la couche de stockage connaît déjà gratuitement : quels blocs ont divergé. `rdc repo diff` prend l'autre route. Il évolue avec les blocs modifiés. Il ne charge aucune clé. Il obtient sa liste de fichiers en comparant les deux images chiffrées.

## La pile que vous comparez

Soyons précis sur ce que "deux dépôts" signifie sur disque. Toute l'astuce en dépend. De bas en haut : un SSD, le stockage hôte, un pool btrfs. Par-dessus, un fichier image LUKS2 par dépôt. Déverrouillez-le et vous obtenez un périphérique dm-crypt. À l'intérieur vit le système de fichiers ext4 qu'utilisent les conteneurs. Un dépôt est un fichier dans le pool btrfs.

Un fork est un reflink de ce fichier. Juste après le fork, les deux fichiers image sont identiques octet par octet. Ils partagent chaque bloc physique. Le parent et le fork ne sont pas deux copies des données. Ce sont deux cartes d'étendues pointant vers les mêmes blocs. Quand vous écrivez dans le fork, la couche de stockage alloue un nouveau bloc pour la région modifiée. Seule la carte d'étendues du fork est réécrite. Les blocs du parent restent intacts.

Ainsi, "comparer deux dépôts" se réduit à "comparer deux fichiers qui partagent la plupart de leurs étendues". Le noyau peut déjà répondre à ça. Personne n'a besoin de lire un seul octet de l'un ou l'autre fichier.

## FIEMAP : interroger le noyau sur ce qui a changé sans le lire

L'ioctl FIEMAP retourne la carte d'étendues d'un fichier : une liste de tuples (décalage logique, décalage physique, longueur). Chaque tuple indique où une partie du fichier réside sur le disque. Ce sont de pures métadonnées du système de fichiers. Il ne lit pas les données du fichier. Pour une image chiffrée, il n'a besoin d'aucune clé. Le texte chiffré n'est que des octets que le noyau n'a jamais à interpréter.

Comparez les deux cartes d'étendues. Toute plage logique où les deux forks pointent vers le même bloc physique est partagée. Partagé signifie identique, parce que c'est littéralement le même bloc sur le périphérique. Les plages où le fork possède son propre bloc privé sont les écritures. Ce sont les blocs modifiés. On les a obtenus à partir des métadonnées que la couche de stockage conserve de toute façon.

Voilà d'où vient le raisonnement sur le coût. La comparaison FIEMAP lit des enregistrements d'étendues, pas des données. Son travail évolue avec le nombre d'étendues modifiées, pas avec la taille du dépôt. Le fork de 1 Go et le fork de 100 Go retournent la même courte liste d'étendues privées. Les mêmes millisecondes, s'ils ont modifié les mêmes fichiers. Mise en garde honnête : le temps de parcours des étendues évolue avec la fragmentation de l'image, pas avec la taille. Une image copy-on-write sous des écritures aléatoires intenses accumule des étendues. Le parcours complet `filefrag` a pris 3,19 secondes sur l'image de production la plus fragmentée que j'ai mesurée. Voir l'article de benchmark sur la fragmentation. C'est le plafond du côté des métadonnées. C'est un scan en arrière-plan, pas une lecture de données.

## D'un bloc modifié à un nom de fichier, à travers deux couches chiffrées

Une liste de plages d'octets modifiées dans l'image chiffrée n'est pas encore utile. Les plages sont des positions dans le texte chiffré. Les noms voulus sont deux couches au-dessus, dans l'ext4 interne. Le pont entre les deux est de l'arithmétique d'adresses, pas du déchiffrement.

LUKS chiffre avec aes-xts. C'est préservant la longueur et chiffre chaque secteur de 512 octets individuellement. Un secteur en texte clair modifié produit un secteur chiffré modifié au même décalage. Le seul décalage est le décalage de données LUKS : les 16 Mio d'en-tête et de slots de clés devant le payload chiffré. Soustrayez ce décalage de chaque plage d'image modifiée. Vous avez maintenant la plage correspondante sur le périphérique dm-crypt. C'est le périphérique bloc sur lequel repose l'ext4 interne. Aucune clé n'a été utilisée. C'est une soustraction.

Maintenant, mappez les plages de périphérique vers les fichiers. ext4 conserve également une carte d'étendues par inode. Même structure (logique, physique, longueur). On y accède via FIEMAP sur le système de fichiers interne monté. Parcourez les inodes une fois pour construire un index bloc-vers-fichier. Ensuite, recherchez chaque plage de périphérique modifiée dans cet index. Une plage qui chevauche les étendues de données de l'inode 1234 appartient au chemin de cet inode. Ce chemin est le fichier qui a changé.

Soyons clairs sur ce que cette approche ne fait jamais. Elle ne dérive jamais de texte en clair à partir de l'image modifiée. Elle lit la structure du système de fichiers à des décalages connus. Elle le fait à la fois du côté chiffré et du côté déchiffré. Puis elle joint les deux par adresse. Le filtre de blocs indique quelles régions du périphérique ont bougé. La carte d'étendues ext4 indique quel fichier possède chaque région. Ni l'une ni l'autre étape n'inspecte le contenu d'un bloc modifié pour décider qu'il a changé.

## Ajouts, suppressions et renommages : le parcours d'identité par inode

Les modifications découlent directement de la comparaison de blocs. Les ajouts, suppressions et renommages nécessitent une observation supplémentaire. Le reflink nous la donne gratuitement : un fork préserve les numéros d'inode. Le reflink de toute l'image clone le système de fichiers interne entier octet par octet avant toute divergence. Ainsi, un inode qui existait dans le parent a le même numéro dans le fork.

Cela fait de l'identité une comparaison d'ensembles. Un inode des deux côtés avec un chemin différent est un renommage. Un inode uniquement du nouveau côté est un ajout. Un inode uniquement de l'ancien côté est une suppression. Un renommage est confirmé par le chevauchement des étendues de périphérique. Les blocs de données du fichier renommé se trouvent aux mêmes décalages de périphérique sur les deux forks. Les deux forks partagent un système de coordonnées. Ce chevauchement exclut également la réutilisation d'un numéro d'inode pour des données sans rapport. Un renommage pur apparaît alors avec les blocs de données du fichier inchangés. Seule l'entrée de répertoire a bougé.

Voici le formulaire nom-statut par défaut, la même grammaire A/M/D/R que vous lisez déjà depuis `git status --short` :

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Un fichier modifié dans un dépôt de 1 Go. Signalé depuis une comparaison de blocs qui n'a lu aucune donnée de fichier. Rien n'a été déverrouillé.

Le mode par défaut fait une chose de plus pour la correction. Le filtre de blocs est un surensemble. Une étendue btrfs peut couvrir plus que les octets qui ont réellement changé. Ainsi, une écriture dans un fichier peut signaler un voisin qui partage une étendue. Pour éviter de signaler un fichier qui n'a pas changé, le mode par défaut confirme chaque candidat signalé par un bloc. Il hache uniquement ce fichier des deux côtés. Il hache les candidats, pas le dépôt. Ainsi, le coût de confirmation suit toujours l'ensemble des modifications. `--fast` fait confiance au filtre de blocs et ignore la confirmation. Utilisez-le quand vous voulez la réponse rapidement et tolérez un rare faux positif.

## Pourquoi un agent IA a besoin de ça

La raison pour laquelle cette commande existe, c'est le flux de travail de l'agent. Je regardais sans cesse des agents forker la production, effectuer des modifications, puis n'avoir aucun moyen propre de signaler ce qu'ils avaient réellement touché. Un agent IA peut forker la production instantanément. Il effectue un changement risqué dans le fork isolé. Ensuite, il doit savoir exactement ce qu'il a touché avant de promouvoir quoi que ce soit. Le fork est la branche. Le diff est la revue.

L'agent ne lit pas le statut de nom, il lit `--json` :

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

La sortie structurée donne à l'agent un ensemble de modifications précis : quels chemins il a modifiés, créés, supprimés. Avec `--stat`, la taille de modification par fichier en octets et en blocs. Un agent qui voit son diff avant de promouvoir est un agent qu'on peut laisser près de la production. Le rayon d'impact est inspecta­ble, pas affirmé. D'autres modes servent la même boucle de revue. `--name-only` pour une simple liste de chemins. `--content <path>` pour un diff texte unifié d'un seul fichier (texte uniquement ; un fichier binaire signale `Binary files differ`). `--stat` quand l'agent a besoin de savoir ce qui a changé et de combien.

## Pourquoi les tests de reprise après sinistre en ont besoin

Le même primitive répond à une question de reprise après sinistre qui était auparavant difficile à poser sans risque. Forkez la production. Restaurez une sauvegarde dans le fork. Comparez le fork avec la production. Le diff indique si la restauration a reproduit le jeu de fichiers attendu. Il le fait sans interrompre la production. Et il ne déchiffre rien sur le chemin du diff.

C'est une répétition qu'on peut effectuer selon un calendrier. La restauration se fait dans un fork isolé. Le diff signale le delta en grammaire git. Une répétition propre : l'ensemble modifié correspond à ce que la sauvegarde était censée contenir. On valide la récupération contre la production en direct. La copie ne coûte rien à créer et rien à jeter.

## Limites honnêtes

Le diff de contenu est texte uniquement. `--content` produit un diff unifié pour les fichiers texte. Pour tout le reste, il signale `Binary files differ`, comme git le fait. Un diff orienté lignes d'un blob chiffré puis compressé n'a aucun sens.

Il compare des forks liés, pas des dépôts arbitraires. Tout le mécanisme repose sur un système de coordonnées partagé. Les étendues partagées prouvent l'égalité. Les numéros d'inodes préservés ancrent l'identité. Un décalage de données commun les relie. Deux dépôts qui n'ont jamais été forkés depuis un ancêtre commun ne partagent rien de tout cela. Il n'existe pas de diff bon marché entre eux. C'est une fonctionnalité, pas un bug. Tout comme `git diff` entre deux historiques sans lien n'est pas significatif.

La détection des renommages est basée sur les inodes. Elle est exacte pour les renommages qu'un système de fichiers enregistre réellement comme des renommages. Une suppression suivie d'une création d'un contenu identique sous un nouveau nom ? Deux opérations dans la table des inodes. Le diff les signale donc comme une suppression et un ajout, pas un renommage. L'heuristique de similarité de contenu de git appellerait ça un renommage. Le parcours par inode ne le fera pas. C'est la bonne réponse sur ce que le système de fichiers a fait. Même si ce n'est pas la réponse sur ce qu'un humain voulait dire.

Et le parcours des métadonnées évolue avec la fragmentation. Sur une image très fragmentée, l'énumération des étendues prend des secondes, pas des millisecondes. C'est toujours indépendant de la taille du dépôt. C'est toujours sans lecture de données. Mais ce n'est pas littéralement instantané sur les images les plus fragmentées.

## La conclusion

`rdc repo diff` apporte l'ergonomie du contrôle de version à une infrastructure chiffrée et en cours d'exécution. L'interface est délibérément celle de git. A/M/D/R, diffs unifiés, `--stat`. Rien de nouveau à apprendre. Si vous savez lire `git status --short`, vous savez lire un diff entre deux images LUKS. L'ingénierie sous-jacente est la partie qui mérite attention. Elle se résume à deux refus. Elle ne déchiffre jamais. aes-xts permet à une comparaison FIEMAP au niveau des blocs de localiser chaque secteur modifié par adresse. Et elle ne paie jamais pour des données qui n'ont pas changé. La couche de stockage a déjà enregistré quels blocs ont divergé. Le fork est la branche. Le diff est la revue. La revue coûte ce que le changement coûte, pas ce que le dépôt pèse.
