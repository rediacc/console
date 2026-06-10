---
title: "Démarrage automatique et récupération"
description: "Comment fonctionne le démarrage automatique, le réconciliateur périodique qui récupère les dépôts tombés après le démarrage, et comment inspecter l'état de récupération."
category: "Guides"
order: 5
language: fr
sourceHash: "7fa4f919475b304e"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Démarrage automatique et récupération

Les dépôts avec le démarrage automatique se démarrent d'eux-mêmes au boot. Si l'un d'eux tombe en panne par la suite, le réconciliateur périodique le rétablit. Aucune intervention. Aucun redémarrage manuel.

Pour savoir comment activer ou désactiver le démarrage automatique sur un dépôt, consultez [Services: Démarrage automatique au démarrage](/fr/docs/services#autostart-on-boot).

## Comment fonctionne le démarrage automatique

Lorsque vous activez le démarrage automatique pour un dépôt, Rediacc génère un fichier de clé LUKS aléatoire de 256 octets et l'ajoute au slot LUKS 1 du volume chiffré. Le fichier de clé est stocké à :

```
{datastore}/.credentials/keys/{guid}.key
```

Cela permet à la machine de monter le dépôt sans demander la phrase secrète. Le slot LUKS 0 (votre phrase secrète) n'est pas modifié.

Le slot du fichier de clé utilise la KDF rapide PBKDF2 : un fichier de clé aléatoire de 256 octets constitue en lui-même sa propre marge de sécurité, de sorte qu'une KDF à mémoire élevée n'ajouterait que de la latence au déverrouillage sans renforcer la protection. Les montages s'ouvrent en bien moins d'une seconde. Les dépôts créés avant cette optimisation paient encore une dérivation Argon2id de plusieurs secondes à chaque montage ; convertissez-les sur place (dépôt démonté) avec la commande opérateur `renet repository kdf-migrate --name <guid>` sur la machine. Le slot 0 conserve Argon2id, le bon choix pour une phrase secrète humaine.

Au démarrage, un service systemd one-shot nommé `rediacc-autostart.service` lit la liste des dépôts avec le démarrage automatique activé, monte chacun d'eux avec son fichier de clé, démarre le Docker daemon par dépôt, et exécute le hook `up()` du Rediaccfile. À l'arrêt, le service exécute `down()`, arrête Docker et ferme les volumes LUKS.

> **Note de sécurité :** Le fichier de clé donne un accès root au dépôt sans la phrase secrète. Toute personne ayant un accès root au serveur peut monter les dépôts avec démarrage automatique activé. Évaluez cela en fonction de votre modèle de menace avant d'activer le démarrage automatique sur des dépôts sensibles.

## L'écart de récupération

Le démarrage automatique au boot s'exécute exactement une fois par démarrage. Le watchdog du routeur, qui tourne en continu ensuite, ne redémarre que les *conteneurs à l'intérieur d'un dépôt déjà en fonctionnement avec un Docker daemon actif*. Il ne peut pas remonter un volume LUKS ni redémarrer un Docker daemon par réseau qui s'est arrêté.

Cela signifie que si le volume LUKS d'un dépôt est démonté ou si son Docker daemon s'arrête après le démarrage du serveur, ni le service de démarrage ni le watchdog ne le récupèreront. Avant l'existence du réconciliateur, un dépôt dans cet état restait hors service jusqu'à l'intervention d'un opérateur.

## Réconciliateur périodique

Le timer systemd `rediacc-autostart-reconcile.timer` se déclenche environ toutes les 3 minutes et exécute `renet repository reconcile`. Pour chaque dépôt avec démarrage automatique activé, le réconciliateur vérifie trois choses :

1. Le volume LUKS est-il monté ?
2. Le Docker daemon par réseau est-il en cours d'exécution ?
3. Les services du dépôt sont-ils actifs ?

Si une vérification échoue, le réconciliateur restaure le dépôt en utilisant son fichier de clé : il monte le volume, démarre le Docker daemon et exécute `up()`. Aucune phrase secrète n'est requise.

Les dépôts qui sont sains, actuellement utilisés par une sauvegarde froide, ou dans leur fenêtre de back-off sont ignorés.

### Back-off et marqueurs de défaillance persistants

Un dépôt qui échoue à la récupération ne réessaie pas immédiatement à chaque tick. Le réconciliateur utilise un back-off exponentiel :

| Nombre d'échecs | Attente avant la prochaine tentative |
|-----------------|--------------------------------------|
| 1 | 1 minute |
| 2 | 2 minutes |
| 3 | 5 minutes |
| 4 | 15 minutes |
| 5+ | 30 minutes, puis 60 minutes |

Après 5 échecs consécutifs, le réconciliateur écrit un fichier marqueur durable à :

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Ce fichier survit à la rotation des journaux. Sa présence signifie que le dépôt nécessite l'intervention d'un opérateur. Le réconciliateur journalise l'échec au niveau erreur et cesse de tenter une récupération automatique pour ce dépôt jusqu'à ce que le marqueur soit effacé.

Causes courantes d'échec de récupération persistant :

- **Licence de dépôt non approuvée ou expirée**: la vérification de licence s'exécute avant `up()`.
- **Fichier de clé manquant**: si le fichier de clé à `{datastore}/.credentials/keys/{guid}.key` a été supprimé, le réconciliateur ne peut pas monter le volume sans phrase secrète.
- **Rediaccfile défaillant**: une erreur de syntaxe ou un hook `up()` qui se termine toujours avec un code non nul.

### Relation avec le watchdog du routeur

Le réconciliateur et le watchdog du routeur gèrent différents niveaux de défaillance et sont conçus pour se compléter :

| Couche | Ce qu'elle gère |
|--------|----------------|
| **Watchdog du routeur** | Redémarrages au niveau des conteneurs à l'intérieur d'un dépôt en cours d'exécution, monté, avec un Docker daemon actif |
| **Réconciliateur (`rediacc-autostart-reconcile.timer`)** | Récupération au niveau du dépôt : remontage LUKS, redémarrage du Docker daemon, ré-exécution de `up()` |

Si un seul conteneur plante dans un dépôt sain, le watchdog le gère. Si le daemon entier du dépôt s'arrête, le réconciliateur le gère.

## Inspecter l'état de récupération

### Statut du timer et du service

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Journaux du réconciliateur

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Marqueurs de défaillance persistants

Lister les dépôts avec des marqueurs de défaillance durables :

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Chaque nom de fichier est un GUID de dépôt. Faites la correspondance avec `rdc config repository list` pour associer les GUID aux noms de dépôts.

Pour effacer un marqueur après avoir résolu le problème sous-jacent, supprimez le fichier :

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

Le réconciliateur tentera à nouveau la récupération au prochain tick du timer.

## Pages connexes

- [Services: Démarrage automatique au démarrage](/fr/docs/services#autostart-on-boot): activer et désactiver le démarrage automatique, gestion du fichier de clé
- [Sauvegarde et restauration](/fr/docs/backup-restore): interaction des sauvegardes froides avec les services en cours d'exécution
