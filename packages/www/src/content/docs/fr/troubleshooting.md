---
title: "Dépannage"
description: "Solutions aux problèmes courants avec SSH, la configuration, les dépôts, les services et Docker."
category: "Guides"
order: 10
language: fr
---

# Dépannage

Problèmes courants et leurs solutions. En cas de doute, commencez par `rdc doctor` pour exécuter une vérification diagnostique complète.

## Échec de la connexion SSH

- Vérifiez que vous pouvez vous connecter manuellement : `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Exécutez `rdc context scan-keys server-1` pour actualiser les clés de l'hôte
- Vérifiez que le port SSH correspond : `--port 22`
- Testez la connectivité : `rdc machine test-connection --ip 203.0.113.50 --user deploy`

## Discordance de clé d'hôte

Si un serveur a été réinstallé ou ses clés SSH ont changé, vous verrez "host key verification failed" :

```bash
rdc context scan-keys server-1
```

Cette commande récupère de nouvelles clés d'hôte et met à jour votre configuration.

## Échec de la configuration de la machine

- Assurez-vous que l'utilisateur SSH dispose d'un accès sudo sans mot de passe, ou configurez `NOPASSWD` pour les commandes requises
- Vérifiez l'espace disque disponible sur le serveur
- Exécutez avec `--debug` pour une sortie détaillée : `rdc context setup-machine server-1 --debug`

## Échec de la création du dépôt

- Vérifiez que la configuration est terminée : le répertoire du datastore doit exister
- Vérifiez l'espace disque sur le serveur
- Assurez-vous que le binaire renet est installé (relancez la configuration si nécessaire)

## Les services ne démarrent pas

- Vérifiez la syntaxe du Rediaccfile : ce doit être du Bash valide
- Assurez-vous que les fichiers `docker compose` utilisent `network_mode: host`
- Vérifiez que les images Docker sont accessibles (envisagez `docker compose pull` dans `prep()`)
- Consultez les journaux des conteneurs via le socket Docker du dépôt :

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
```

Ou affichez tous les conteneurs :

```bash
rdc machine containers server-1
```

## Erreurs de permission refusée

- Les opérations sur les dépôts nécessitent les droits root sur le serveur (renet s'exécute via `sudo`)
- Vérifiez que votre utilisateur SSH appartient au groupe `sudo`
- Assurez-vous que le répertoire du datastore a les bonnes permissions

## Problèmes de socket Docker

Chaque dépôt dispose de son propre Docker daemon. Lorsque vous exécutez des commandes Docker manuellement, vous devez spécifier le bon socket :

```bash
# Avec rdc term (configuré automatiquement) :
rdc term server-1 my-app -c "docker ps"

# Ou manuellement avec le socket :
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Remplacez `2816` par l'identifiant réseau de votre dépôt (disponible dans `config.json` ou `rdc repo status`).

## Conteneurs créés sur le mauvais Docker daemon

Si vos conteneurs apparaissent sur le Docker daemon du système hôte au lieu du daemon isolé du dépôt, la cause la plus courante est l'utilisation de `sudo docker` dans un Rediaccfile.

`sudo` réinitialise les variables d'environnement, donc `DOCKER_HOST` est perdu et Docker utilise par défaut le socket système (`/var/run/docker.sock`). Rediacc bloque cela automatiquement, mais si vous le rencontrez :

- **Utilisez `docker` directement** — les fonctions du Rediaccfile s'exécutent déjà avec des privilèges suffisants
- Si vous devez utiliser sudo, utilisez `sudo -E docker` pour préserver les variables d'environnement
- Vérifiez votre Rediaccfile pour tout commande `sudo docker` et supprimez le `sudo`

## Le terminal ne fonctionne pas

Si `rdc term` ne parvient pas à ouvrir une fenêtre de terminal :

- Utilisez le mode en ligne avec `-c` pour exécuter des commandes directement :
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- Forcez un terminal externe avec `--external` si le mode en ligne pose des problèmes
- Sous Linux, assurez-vous d'avoir installé `gnome-terminal`, `xterm` ou un autre émulateur de terminal

## Exécuter les diagnostics

```bash
rdc doctor
```

Cette commande vérifie votre environnement, l'installation de renet, la configuration du contexte et l'état de l'authentification. Chaque vérification signale OK, Warning ou Error avec une brève explication.
