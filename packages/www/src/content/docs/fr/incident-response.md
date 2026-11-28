---
title: "Réponse aux incidents : enquêter, déclarer et préserver les preuves"
description: "Ouvrez une investigation sur un dépôt ou une machine, lisez une chronologie unique d'audit, d'exécutions, de flux et d'ouvertures de fichiers, vérifiez les chaînes de hash, déclarez un incident pour figer les preuves et lancer les délais de 24 heures, 72 heures et un mois, et pilotez le tout depuis rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: fr
sourceHash: "0e7681b5366968f0"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Réponse aux incidents

Un incident désigne ici un incident survenant dans les propres dépôts d'un client. La page d'investigation, les commandes `rdc incident` et les lecteurs `rdc repo flows` et `rdc repo opens` travaillent tous à partir des enregistrements décrits dans [l'investigation numérique](/fr/docs/forensics). Les incidents touchant les systèmes de Rediacc suivent la [réponse aux incidents de sécurité](/fr/docs/security-incident-response).

## Accès

L'investigation exige une offre payante et le rôle de propriétaire ou d'administrateur. L'ouverture demande une réauthentification récente, et une investigation ouverte reste valable 60 minutes. Chaque consultation est écrite dans le journal d'audit.

Le support Rediacc ne voit les données d'investigation que sous une autorisation de support émise par le client. Une autorisation dure 7 jours au plus et peut être révoquée à tout moment.

Les lectures de la CLI nécessitent le scope `forensics:read`, et déclarer et clôturer nécessitent `incident:manage`. Une connexion CLI porte les deux pour les propriétaires et administrateurs après une approbation élevée dans le navigateur. Quand une commande répond qu'une approbation élevée récente est requise, le portail du compte la demande et la commande peut être relancée.

## La chronologie

La page Investigate fusionne un périmètre (un dépôt ou une machine) en une seule chronologie de cinq types de lignes : événements d'audit de la console, exécutions, flux réseau, ouvertures de fichiers et anomalies. Les changements depuis le dernier instantané peuvent être comparés à celui-ci. Un curseur de fenêtre temporelle règle la fenêtre, et une fenêtre couvre 31 jours au plus.

Une période sans preuve apparaît comme une ligne de trou qui nomme la machine et la raison, jamais comme une période vide. Un graphique des octets sortants par minute et une liste des principales destinations se trouvent au-dessus des lignes.

Les mêmes lectures sont disponibles en ligne de commande :

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` et `--until` acceptent un instant ISO 8601 ou une durée remontant depuis maintenant, comme `90m`, `24h` ou `7d`. La fenêtre par défaut couvre les dernières 24 heures. Les lignes de flux indiquent l'heure, le processus, la destination, les octets sortants et entrants, ainsi que l'ASN et le pays s'ils sont connus. Les lignes d'ouverture indiquent l'heure, le processus et le chemin, les chemins sensibles étant signalés.

## Vérifier les preuves

Verify evidence recalcule dans le navigateur la chaîne de hash des fichiers journaliers d'audit et les chaînes de lots signés des enregistrements d'investigation pour la fenêtre, et liste chaque trou et chaque modification. Les signatures des lots sont vérifiées avec les clés de spool que le serveur de comptes a épinglées pour chaque machine. Une clé écrite dans les preuves n'est jamais crue. Le résultat est apposé sur les rapports exportés.

Les preuves de plus de 2 GiB sont trop volumineuses pour le navigateur. Le même module s'exécute en ligne de commande :

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

La commande se termine avec le code 1 dès qu'un trou ou une modification est trouvé. `--machine-key <machine>=<public-key-hex>` (la clé fait 64 caractères hexadécimaux) fournit une clé extérieure au répertoire et peut être répétée. Une machine sans clé extérieure échoue.

## Déclarer un incident

Déclarer fige les preuves. L'enregistrement du compte est créé d'abord, puis le dépôt est préparé pour l'investigation :

1. L'incident est enregistré avec sa fenêtre, la personne qui l'a déclaré et le moment où l'organisation en a eu connaissance.
2. Une retenue d'éviction couvre la fenêtre, et les règles de verrouillage du bucket s'y étendent, si bien que FIFO ne peut pas supprimer ces jours.
3. Le dépôt est forké en instantané d'investigation, avec le tag `incident-<id>`.
4. Le niveau de capture du dépôt passe en Full.

Trois délais courent à partir du moment de la prise de connaissance, qui peut être fixé avant la déclaration et jamais après : l'alerte précoce est due 24 heures après la prise de connaissance, la notification 72 heures après, et le rapport final un mois calendaire après la notification (compté depuis l'échéance de notification tant qu'aucune notification n'est enregistrée). La page affiche chaque délai comme en attente, dû sous 6 heures, dépassé ou terminé.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Une étape machine en échec laisse l'enregistrement et sa retenue en place, se termine avec le code 1 et nomme la commande qui relance uniquement les étapes échouées :

```bash
rdc incident declare mail --resume <id>
```

`--resume` conserve la fenêtre et la prise de connaissance de la déclaration d'origine, `--since`, `--until` et `--aware-at` ne se combinent donc pas avec lui.

## Exporter les preuves

`rdc incident export` écrit la fenêtre de l'incident dans un répertoire : l'enregistrement de l'incident avec ses délais, la chronologie fusionnée, les agrégats d'octets sortants, le manifeste brut de la chaîne et les fichiers bruts qu'il liste. Quand le manifeste liste des fichiers journaliers d'audit ou des fichiers d'en-têtes d'investigation, les chaînes sont vérifiées au passage et le résultat va dans `verification.json`. La commande se termine avec le code 1 quand les preuves montrent un trou ou une modification.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Avec `--stage`, la même commande écrit à la place un rapport signé. Voir les [rapports d'incident](/fr/docs/incident-reports).

## Clôturer un incident

```bash
rdc incident close <id>
```

Rien n'est libéré immédiatement. La retenue d'éviction et les règles de verrouillage du bucket prennent fin 30 jours après la clôture.

## Interroger l'IA

La page d'investigation propose un assistant qui répond aux questions sur le périmètre et la fenêtre ouverts. Il ne lit que ce périmètre et cette fenêtre, au moyen d'un ticket à usage unique émis depuis l'investigation ouverte et utilisable pendant 15 minutes. La question et les lignes lues partent vers le fournisseur d'IA propre à l'organisation. L'assistant peut exécuter les commandes `rdc` ci-dessus selon les mêmes règles de permission que toute autre commande.

## Commandes

| Commande | Rôle |
|---|---|
| `rdc repo flows <ref>` | Flux réseau d'un dépôt sur une fenêtre |
| `rdc repo opens <ref>` | Ouvertures de fichiers sensibles d'un dépôt sur une fenêtre |
| `rdc forensics level <ref> <level>` | Définir le niveau de capture |
| `rdc forensics verify` | Vérifier un répertoire de preuves ou un rapport signé |
| `rdc incident declare <ref>` | Enregistrer un incident, forker le dépôt et passer en Full |
| `rdc incident status [id]` | Lister les incidents, ou en afficher un avec ses délais |
| `rdc incident export <id>` | Écrire la fenêtre de preuves, ou un rapport signé avec `--stage` |
| `rdc incident close <id>` | Clôturer un incident |
