---
title: "Post-installation"
description: "Configuration du démarrage automatique, structure du contexte et dépannage pour Rediacc."
category: "Getting Started"
order: 3
language: fr
---

# Post-installation

Après avoir complété le [Guide étape par étape](/fr/docs/guide), cette page couvre la configuration du démarrage automatique, la compréhension du fichier de configuration du contexte et le dépannage des problèmes courants.

## Démarrage automatique au boot

Par défaut, les dépôts doivent être montés et démarrés manuellement après un redémarrage du serveur. Le **démarrage automatique** configure les dépôts pour qu'ils se montent automatiquement, démarrent Docker et exécutent le `up()` du Rediaccfile au démarrage du serveur.

### Fonctionnement

Lorsque vous activez le démarrage automatique pour un dépôt :

1. Un fichier de clé LUKS aléatoire de 256 octets est généré et ajouté au slot LUKS 1 du dépôt (le slot 0 reste la phrase secrète utilisateur).
2. Le fichier de clé est stocké dans `{datastore}/.credentials/keys/{guid}.key` avec les permissions `0600` (root uniquement).
3. Un service systemd (`rediacc-autostart`) est installé et s'exécute au démarrage pour monter tous les dépôts activés et démarrer leurs services.

Lors de l'arrêt ou du redémarrage du système, le service arrête gracieusement tous les services (Rediaccfile `down()`), arrête les démons Docker et ferme les volumes LUKS.

> **Note de sécurité :** L'activation du démarrage automatique stocke un fichier de clé LUKS sur le disque du serveur. Toute personne ayant un accès root au serveur peut monter le dépôt sans la phrase secrète. C'est un compromis entre la commodité (démarrage automatique) et la sécurité (saisie manuelle de la phrase secrète requise). Évaluez ceci en fonction de votre modèle de menace.

### Activer le démarrage automatique

```bash
rdc repo autostart enable my-app -m server-1
```

La phrase secrète du dépôt vous sera demandée. Elle est nécessaire pour autoriser l'ajout du fichier de clé au volume LUKS.

### Activer le démarrage automatique pour tous les dépôts

```bash
rdc repo autostart enable-all -m server-1
```

### Désactiver le démarrage automatique

```bash
rdc repo autostart disable my-app -m server-1
```

Ceci supprime le fichier de clé et invalide le slot LUKS 1. Le dépôt ne se montera plus automatiquement au démarrage.

### Lister le statut du démarrage automatique

```bash
rdc repo autostart list -m server-1
```

Affiche quels dépôts ont le démarrage automatique activé et si le service systemd est installé.

## Comprendre la configuration du contexte

Toute la configuration du contexte est stockée dans `~/.rediacc/config.json`. Voici un exemple annoté de ce à quoi ressemble ce fichier après avoir complété le guide :

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Champs principaux :**

| Champ | Description |
|-------|-------------|
| `mode` | `"local"` pour le mode local, `"s3"` pour les contextes sauvegardés sur S3. |
| `apiUrl` | `"local://"` indique le mode local (pas d'API distante). |
| `ssh.privateKeyPath` | Chemin vers la clé privée SSH utilisée pour toutes les connexions aux machines. |
| `machines.<name>.knownHosts` | Clés d'hôte SSH issues de `ssh-keyscan`, utilisées pour vérifier l'identité du serveur. |
| `repositories.<name>.repositoryGuid` | UUID identifiant l'image disque chiffrée sur le serveur. |
| `repositories.<name>.credential` | Phrase secrète de chiffrement LUKS. **Non stockée sur le serveur.** |
| `repositories.<name>.networkId` | ID réseau déterminant le sous-réseau IP (2816 + n*64). Attribué automatiquement. |

> Ce fichier contient des données sensibles (chemins de clés SSH, identifiants LUKS). Il est stocké avec les permissions `0600` (lecture/écriture propriétaire uniquement). Ne le partagez pas et ne le commitez pas dans un système de contrôle de version.

## Dépannage

### La connexion SSH échoue

- Vérifiez que vous pouvez vous connecter manuellement : `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Exécutez `rdc context scan-keys server-1` pour rafraîchir les clés d'hôte
- Vérifiez que le port SSH correspond : `--port 22`

### La configuration de la machine échoue

- Assurez-vous que l'utilisateur a un accès sudo sans mot de passe, ou configurez `NOPASSWD` pour les commandes requises
- Vérifiez l'espace disque disponible sur le serveur
- Exécutez avec `--debug` pour une sortie détaillée : `rdc context setup-machine server-1 --debug`

### La création du dépôt échoue

- Vérifiez que la configuration a été effectuée : le répertoire du datastore doit exister
- Vérifiez l'espace disque sur le serveur
- Assurez-vous que le binaire renet est installé (relancez la configuration si nécessaire)

### Les services ne démarrent pas

- Vérifiez la syntaxe du Rediaccfile : il doit être du Bash valide
- Assurez-vous que les fichiers `docker compose` utilisent `network_mode: host`
- Vérifiez que les images Docker sont accessibles (envisagez `docker compose pull` dans `prep()`)
- Consultez les journaux des conteneurs : connectez-vous au serveur en SSH et utilisez `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Erreurs de permission refusée

- Les opérations sur les dépôts nécessitent l'accès root sur le serveur (renet s'exécute via `sudo`)
- Vérifiez que votre utilisateur est dans le groupe `sudo`
- Vérifiez que le répertoire du datastore a les permissions correctes

### Exécuter les diagnostics

Utilisez la commande doctor intégrée pour diagnostiquer les problèmes :

```bash
rdc doctor
```

Ceci vérifie votre environnement, l'installation de renet, la configuration du contexte et le statut d'authentification.
