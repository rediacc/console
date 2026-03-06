---
title: "Sauvegarde et réseau"
description: "Configurez des planifications de sauvegarde automatisées, gérez les fournisseurs de stockage, configurez le réseau d'infrastructure et enregistrez les ports de service."
category: "Tutorials"
order: 6
language: fr
sourceHash: "e756fef6749b54c5"
---

# Comment configurer les sauvegardes et le réseau avec Rediacc

Les sauvegardes automatisées protègent vos dépôts, et le réseau d'infrastructure expose les services au monde extérieur. Dans ce tutoriel, vous configurez les planifications de sauvegarde avec les fournisseurs de stockage, mettez en place le réseau public avec les certificats TLS, enregistrez les ports de service et vérifiez la configuration. Une fois terminé, votre machine est prête pour le trafic de production.

## Prérequis

- La CLI `rdc` installée avec une configuration initialisée
- Une machine provisionnée (voir [Tutoriel : Configuration de la machine](/fr/docs/tutorial-setup))

## Enregistrement interactif

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### Étape 1 : Voir les stockages actuels

Les fournisseurs de stockage (S3, B2, Google Drive, etc.) servent de destinations de sauvegarde. Vérifiez quels fournisseurs sont configurés.

```bash
rdc config storages
```

Liste tous les fournisseurs de stockage configurés importés depuis les configurations rclone. Si vide, ajoutez d'abord un fournisseur de stockage — voir [Sauvegarde et restauration](/fr/docs/backup-restore).

### Étape 2 : Configurer la planification de sauvegarde

Mettez en place des sauvegardes automatisées qui s'exécutent selon un calendrier cron.

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Ceci planifie des sauvegardes quotidiennes à 2h du matin, envoyant tous les dépôts vers le stockage `my-s3`. La planification est stockée dans votre configuration et peut être déployée sur les machines en tant que minuteur systemd.

### Étape 3 : Voir la planification de sauvegarde

Vérifiez que la planification a été appliquée.

```bash
rdc backup schedule show
```

Affiche la configuration de sauvegarde actuelle : destination, expression cron et statut d'activation.

### Étape 4 : Configurer l'infrastructure

Pour les services accessibles publiquement, la machine a besoin de son IP externe, du domaine de base et d'un e-mail de certificat pour Let's Encrypt TLS.

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc génère une configuration de proxy inverse Traefik à partir de ces paramètres.

### Étape 5 : Ajouter des ports TCP/UDP

Si vos services nécessitent des ports non HTTP (par ex. SMTP, DNS), enregistrez-les comme points d'entrée Traefik.

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Ceci crée des points d'entrée Traefik (`tcp-25`, `udp-53`, etc.) que les services Docker peuvent référencer via des labels.

### Étape 6 : Voir la configuration d'infrastructure

Vérifiez la configuration complète de l'infrastructure.

```bash
rdc config show-infra server-1
```

Affiche les IPs publiques, le domaine, l'e-mail de certificat et tous les ports enregistrés.

### Étape 7 : Désactiver la planification de sauvegarde

Pour arrêter les sauvegardes automatisées sans supprimer la configuration :

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

La configuration est conservée et peut être réactivée ultérieurement avec `--enable`.

## Dépannage

**"Invalid cron expression"**
Le format cron est `minute hour day month weekday`. Planifications courantes : `0 2 * * *` (quotidien 2h), `0 */6 * * *` (toutes les 6 heures), `0 0 * * 0` (hebdomadaire dimanche minuit).

**"Storage destination not found"**
Le nom de destination doit correspondre à un fournisseur de stockage configuré. Exécutez `rdc config storages` pour voir les noms disponibles. Ajoutez de nouveaux fournisseurs via la configuration rclone.

**"Infrastructure config incomplete" lors du déploiement**
Les trois champs sont requis : `--public-ipv4`, `--base-domain` et `--cert-email`. Exécutez `rdc config show-infra <machine>` pour vérifier les champs manquants.

## Étapes suivantes

Vous avez configuré les sauvegardes automatisées, mis en place le réseau d'infrastructure, enregistré les ports de service et vérifié la configuration. Pour gérer les sauvegardes :

- [Sauvegarde et restauration](/fr/docs/backup-restore) — référence complète pour les commandes push, pull, list et sync
- [Réseau](/fr/docs/networking) — labels Docker, certificats TLS, DNS et redirection TCP/UDP
- [Tutoriel : Configuration de la machine](/fr/docs/tutorial-setup) — configuration initiale et provisionnement
