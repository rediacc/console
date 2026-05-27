---
title: Dépannage
description: >-
  Solutions aux problèmes courants avec SSH, la configuration, les dépôts, les
  services et Docker.
category: Guides
order: 10
language: fr
sourceHash: "658b00b83875950d"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Dépannage

Problèmes courants et leurs solutions. En cas de doute, commencez par `rdc doctor` pour exécuter une vérification diagnostique complète.

## Échec de la connexion SSH

- Vérifiez que vous pouvez vous connecter manuellement : `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Exécutez `rdc config machine scan-keys -m server-1` pour actualiser les clés de l'hôte
- Vérifiez que le port SSH correspond : `--port 22`
- Testez avec une commande simple : `rdc term connect -m server-1 -c "hostname"`

## Discordance de clé d'hôte

Si un serveur a été réinstallé ou ses clés SSH ont changé, vous verrez "host key verification failed" :

```bash
rdc config machine scan-keys -m server-1
```

Cette commande récupère de nouvelles clés d'hôte et met à jour votre configuration.

## Échec de la configuration de la machine

- Assurez-vous que l'utilisateur SSH dispose d'un accès sudo sans mot de passe, ou configurez `NOPASSWD` pour les commandes requises
- Vérifiez l'espace disque disponible sur le serveur
- Exécutez avec `--debug` pour une sortie détaillée : `rdc config machine setup --name server-1 --debug`

## Problèmes de configuration spécifiques à la distribution

Les cinq systèmes d'exploitation serveur officiellement pris en charge (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) sont livrés avec des politiques de sécurité et des gestionnaires de paquets différents. La plupart des configurations fonctionnent sans problème ; les cas ci-dessous couvrent les exceptions.

### Refus SELinux (Fedora 43, Oracle Linux 10)

Les deux fonctionnent avec SELinux en mode enforcing. rdc setup n'installe pas de politique SELinux personnalisée ; le daemon Docker par dépôt s'exécute dans le contexte standard `container_t`. Si le setup échoue avec des refus AVC, consultez le journal d'audit et identifiez le domaine :

```bash
sudo ausearch -m AVC -ts recent | head -40
# Ou :
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Si un refus pointe vers le binaire renet ou un chemin de fichier spécifique, la solution consiste presque toujours à relabeler (`restorecon -v /path`) plutôt que de désactiver SELinux. En attendant d'avoir terminé votre investigation, `sudo setenforce 0` place le système en mode permissif. Réactivez-le avec `sudo setenforce 1` une fois que vous avez confirmé la persistance du relabeling.

### Refus AppArmor (Ubuntu 24.04, openSUSE Leap 16.0)

Les deux utilisent AppArmor par défaut ; le daemon Docker par dépôt utilise le profil de conteneur par défaut. Si un conteneur dans un dépôt est bloqué :

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU est le cas connu qui déclenche AppArmor. Renet définit automatiquement `security_opt: apparmor=unconfined` sur les conteneurs étiquetés `rediacc.checkpoint=true`. Vous ne devriez pas avoir besoin de configurer des profils AppArmor manuellement pour autre chose. Consultez les notes CRIU dans [Règles de Rediacc](/en/docs/rules-of-rediacc).

### Signatures d'erreur du gestionnaire de paquets

| Système d'exploitation | Gestionnaire de paquets | Erreur typique | Résolution |
|---|---|---|---|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cache Cloudflare en périphérie en retard sur l'origine. Relancez `apt-get update` après ~15 s ; la vérification d'intégrité réussit lors du prochain sondage. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Les métadonnées du dépôt RPM en cache sur le disque sont obsolètes. Exécutez `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Exécutez `sudo zypper refresh rediacc` une fois ; les installations suivantes devraient réussir. |

### Module btrfs manquant (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Si `rdc config machine setup` ou `renet system check-btrfs` échoue avec :

```
Module btrfs not found
```

...le serveur utilise le noyau standard de RHEL 10, livré sans le module btrfs intégré. Il ne s'agit pas d'un bug Rediacc ; RHEL 10 a supprimé btrfs intentionnellement. La solution est d'utiliser **Oracle Linux 10 à la place**. Oracle 10 utilise par défaut l'Unbreakable Enterprise Kernel (UEK), qui conserve btrfs. Consultez [Prérequis -- Pourquoi UEK ?](/en/docs/requirements) pour l'explication complète.

## Échec de la création du dépôt

- Vérifiez que la configuration est terminée : le répertoire du datastore doit exister
- Vérifiez l'espace disque sur le serveur
- Assurez-vous que le binaire renet est installé (relancez la configuration si nécessaire)

## Les services ne démarrent pas

- Vérifiez la syntaxe du Rediaccfile : ce doit être du Bash valide
- Assurez-vous que votre Rediaccfile utilise `renet compose --` (et non `docker compose`)
- Vérifiez que les images Docker sont accessibles (envisagez `renet compose -- pull` dans `up()`)
- Consultez les journaux des conteneurs via le socket Docker du dépôt :

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Ou affichez tous les conteneurs :

```bash
rdc machine containers --name server-1
```

## Erreurs de permission refusée

- Les opérations sur les dépôts nécessitent les droits root sur le serveur (renet s'exécute via `sudo`)
- Vérifiez que votre utilisateur SSH appartient au groupe `sudo`
- Assurez-vous que le répertoire du datastore a les bonnes permissions

## Problèmes de socket Docker

Chaque dépôt dispose de son propre Docker daemon. Lorsque vous exécutez des commandes Docker manuellement, vous devez spécifier le bon socket :

```bash
# Avec rdc term (configuré automatiquement) :
rdc term connect -m server-1 -r my-app -c "docker ps"

# Ou manuellement avec le socket :
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Remplacez `2816` par l'identifiant réseau de votre dépôt (disponible dans `rediacc.json` ou `rdc repo status`).

## `docker run` n'a pas de réseau, `apt update` échoue, `curl` se bloque

À l'intérieur d'un shell de dépôt, lancer un conteneur sans `--network host` vous donne un conteneur isolé avec uniquement une interface de loopback, pas de DNS et aucune connectivité sortante. Des commandes comme `apt update`, `pip install`, `curl https://...`, ou toute récupération réseau échoueront immédiatement avec des erreurs DNS.

C'est intentionnel. Le modèle réseau de Rediacc est **le réseau hôte pour chaque service**, appliqué par `renet compose`. Un bridge Docker par défaut avec NAT contournerait l'isolation de loopback au niveau du noyau qui empêche un dépôt d'atteindre les services d'un autre dépôt, si bien que le daemon Docker par dépôt (`FlavorRediacc`) est configuré avec `"bridge": "none"` et `"iptables": false`. Il n'existe aucun bridge routable auquel un conteneur `docker run` simple pourrait se rattacher. (Les daemons Hub par utilisateur (`FlavorHub`) utilisés par les environnements de développement font exception : ils activent le bridge et iptables afin que les conteneurs utilisateur disposent d'une connectivité réseau sortante.)

**Pour obtenir un accès réseau dans un conteneur ad hoc, utilisez le réseau hôte :**

```bash
# À l'intérieur d'un shell de dépôt (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Désormais apt update, curl, pip install fonctionnent tous.
```

**Pour les services de production, utilisez un Rediaccfile avec `renet compose`** au lieu d'un `docker run` brut. `renet compose` injecte automatiquement `network_mode: host`, les labels d'IP de service et les labels de routage Traefik. Consultez [Services](/fr/docs/services) pour les détails.

## Permission refusée par VS Code sur des fichiers du sandbox

En vous connectant avec `rdc vscode connect -m <machine> -r <repo>`, il se peut que vous ayez vu des erreurs comme `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` après une précédente session VS Code. Cela provenait d'une propriété de fichiers mixte à l'intérieur du répertoire du sandbox, qui contenait des fichiers écrits à la fois par votre utilisateur SSH et par l'utilisateur interne `rediacc`.

Les versions récentes de renet corrigent cela en :

- Créant le workspace de sandbox par dépôt (`/mnt/rediacc/.interim/sandbox/<repo>/`) avec le groupe `rediacc` et le bit set-group-ID (mode `2775`), de sorte que chaque fichier écrit en dessous hérite du bon groupe.
- Appliquant un umask `002` à l'intérieur du runtime du sandbox pour que les nouveaux fichiers soient créés accessibles en écriture par le groupe (`0664`/`0775`).
- Normalisant au démarrage une arborescence `.vscode-server/` existante, afin que les fichiers obsolètes antérieurs au correctif soient réparés automatiquement.

Si vous voyez encore des erreurs de permissions, redémarrez une fois le daemon Docker du dépôt avec `sudo systemctl restart rediacc-docker-<network-id>` depuis un shell sur la machine pour que la passe de normalisation s'exécute, puis relancez `rdc vscode connect`.

## Le daemon ne démarre pas après une mise à niveau de renet

Avant chaque démarrage, `renet daemon start-foreground` réécrit `daemon.json` et `containerd.toml` dans le répertoire de configuration du dépôt à partir des modèles actuels, de sorte qu'un dépôt dont la configuration a été générée par une ancienne version de renet reprend automatiquement le nouveau format. Vous n'avez pas besoin d'exécuter une commande de migration, ni de régénérer manuellement l'unité systemd. Redémarrez simplement le service :

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Si l'unité échoue toujours, consultez le journal pour une erreur spécifique :

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Conteneurs créés sur le mauvais Docker daemon

Si vos conteneurs apparaissent sur le Docker daemon du système hôte au lieu du daemon isolé du dépôt, la cause la plus courante est l'utilisation de `sudo docker` dans un Rediaccfile.

`sudo` réinitialise les variables d'environnement, donc `DOCKER_HOST` est perdu et Docker utilise par défaut le socket système (`/var/run/docker.sock`). Rediacc bloque cela automatiquement, mais si vous le rencontrez :

- **Utilisez `docker` directement**, les fonctions du Rediaccfile s'exécutent déjà avec des privilèges suffisants
- Si vous devez utiliser sudo, utilisez `sudo -E docker` pour préserver les variables d'environnement
- Vérifiez votre Rediaccfile pour tout commande `sudo docker` et supprimez le `sudo`

## Le terminal ne fonctionne pas

Si `rdc term` ne parvient pas à ouvrir une fenêtre de terminal :

- Utilisez le mode en ligne avec `-c` pour exécuter des commandes directement :
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Forcez un terminal externe avec `--external` si le mode en ligne pose des problèmes
- Sous Linux, assurez-vous d'avoir installé `gnome-terminal`, `xterm` ou un autre émulateur de terminal

## Exécuter les diagnostics

```bash
rdc doctor
```

Cette commande vérifie votre environnement, l'installation de renet, la configuration et l'état de l'authentification. Chaque vérification signale OK, Warning ou Error avec une brève explication.
