---
title: "Règles de Rediacc"
description: "Règles et conventions essentielles pour construire des applications sur la plateforme Rediacc. Couvre Rediaccfile, compose, réseau, stockage, CRIU et déploiement."
category: "Guides"
order: 5
language: fr
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
---

# Règles de Rediacc

Chaque dépôt Rediacc s'exécute dans un environnement isolé avec son propre daemon Docker, volume LUKS chiffré et plage d'IP dédiée. Ces règles garantissent que votre application fonctionne correctement au sein de cette architecture.

## Rediaccfile

- **Chaque dépôt a besoin d'un Rediaccfile** — un script bash avec des fonctions de cycle de vie.
- **Fonctions du cycle de vie** : `up()`, `down()`. Optionnel : `info()`.
- `up()` démarre vos services. `down()` les arrête.
- `info()` fournit des informations d'état (état des conteneurs, logs récents, santé).
- Rediaccfile est sourcé par renet — il a accès aux variables shell, pas seulement aux variables d'environnement.

### Variables d'environnement disponibles dans Rediaccfile

| Variable | Exemple | Description |
|----------|---------|-------------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | Chemin racine du dépôt monté |
| `REPOSITORY_NETWORK_ID` | `6336` | Identifiant d'isolation réseau |
| `REPOSITORY_NAME` | `abc123-...` | GUID du dépôt |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | IP de loopback par service (nom du service en majuscules) |

### Rediaccfile minimal

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Utilisez `renet compose`, jamais `docker compose`** — renet injecte l'isolation réseau, le réseau hôte, les IPs de loopback et les labels de service.
- **NE définissez PAS `network_mode`** dans votre fichier compose — renet force `network_mode: host` sur tous les services. Toute valeur que vous définissez est écrasée.
- **NE définissez PAS les labels `rediacc.*`** — renet auto-injecte `rediacc.network_id`, `rediacc.service_ip` et `rediacc.service_name`.
- **Les mappages `ports:` sont ignorés** en mode réseau hôte. Utilisez le label `rediacc.service_port` pour le routage proxy vers les ports non-80.
- **Les politiques de redémarrage (`restart: always`, `on-failure`, etc.) sont sûres à utiliser** — renet les supprime automatiquement pour la compatibilité CRIU. Le watchdog du routeur récupère automatiquement les conteneurs arrêtés selon la politique originale enregistrée dans `.rediacc.json`.
- **Les paramètres dangereux sont bloqués par défaut** — `privileged: true`, `pid: host`, `ipc: host` et les bind mounts vers des chemins système sont rejetés. Utilisez `renet compose --unsafe` pour contourner à vos risques et périls.

### Variables d'environnement à l'intérieur des conteneurs

Renet auto-injecte celles-ci dans chaque conteneur :

| Variable | Description |
|----------|-------------|
| `SERVICE_IP` | IP de loopback dédiée de ce conteneur |
| `REPOSITORY_NETWORK_ID` | ID d'isolation réseau |

### Nommage des services et routage

- Le **nom du service** compose devient le préfixe URL de la route automatique.
- Exemple : le service `myapp` avec networkId 6336 et domaine de base `example.com` devient `https://myapp-6336.example.com`.
- Pour les domaines personnalisés, utilisez les labels Traefik (mais attention : les domaines personnalisés ne sont PAS compatibles avec les forks).
- Les dépôts fork utilisent des routes automatiques plates sous le certificat wildcard de la machine. Les domaines personnalisés (`rediacc.domain`) sont ignorés sur les forks — le domaine appartient au grand dépôt.

## Réseau

- **Chaque dépôt obtient son propre daemon Docker** à `/var/run/rediacc/docker-<networkId>.sock`.
- **Chaque service reçoit une IP de loopback unique** dans un sous-réseau /26 (ex. `127.0.24.192/26`).
- **Liez à `SERVICE_IP`** — chaque service obtient une IP de loopback unique.
- **Les health checks doivent utiliser `${SERVICE_IP}`**, pas `localhost`. Exemple : `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **Communication inter-services** : Utilisez les IPs de loopback ou la variable d'environnement `SERVICE_IP`. Les noms DNS Docker NE fonctionnent PAS en mode hôte.
- **Les conflits de ports sont impossibles** entre dépôts — chacun a son propre daemon Docker et sa propre plage d'IP.
- **Redirection de ports TCP/UDP** : Ajoutez des labels pour exposer les ports non-HTTP :
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Stockage

- **Toutes les données Docker sont stockées dans le dépôt chiffré** — le `data-root` de Docker se trouve à `{mount}/.rediacc/docker/data` dans le volume LUKS. Les volumes nommés, les images et les couches de conteneurs sont tous chiffrés, sauvegardés et forkés automatiquement.
- **Les bind mounts vers `${REPOSITORY_PATH}/...` sont recommandés** pour la clarté, mais les volumes nommés fonctionnent également en toute sécurité.
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data        # bind mount (recommandé)
    - pgdata:/var/lib/postgresql/data      # named volume (également sûr)
  ```
- Le volume LUKS est monté à `/mnt/rediacc/mounts/<guid>/`.
- Les snapshots BTRFS capturent l'intégralité du fichier de support LUKS, y compris toutes les données montées en bind.
- Le datastore est un fichier de pool BTRFS de taille fixe sur le disque système. Utilisez `rdc machine query <name> --system` pour voir l'espace libre effectif. Agrandissez avec `rdc datastore resize`.

## CRIU (Migration à chaud)

- **`backup push --checkpoint`** capture la mémoire des processus en cours d'exécution + l'état du disque.
- **`repo up --mount --checkpoint`** restaure les conteneurs depuis le checkpoint (pas de démarrage à froid).
- **Les connexions TCP deviennent obsolètes après la restauration** — les applications doivent gérer `ECONNRESET` et se reconnecter.
- **Le mode expérimental Docker** est activé automatiquement sur les daemons par dépôt.
- **CRIU est installé** pendant `rdc config machine setup`.
- **`/etc/criu/runc.conf`** est configuré avec `tcp-established` pour la préservation des connexions TCP.
- **Les paramètres de sécurité des conteneurs sont auto-injectés par renet** — `renet compose` ajoute automatiquement ce qui suit à chaque conteneur pour la compatibilité CRIU :
  - `cap_add` : `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (ensemble minimal pour CRIU sur kernel 5.9+)
  - `security_opt` : `apparmor=unconfined` (le support AppArmor de CRIU n'est pas encore stable en upstream)
  - `userns_mode: host` (CRIU nécessite l'accès au namespace init pour `/proc/pid/map_files`)
- Le profil seccomp par défaut de Docker est préservé — CRIU utilise `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) pour suspendre temporairement les filtres pendant le checkpoint/restore.
- **NE définissez PAS ceux-ci manuellement** dans votre fichier compose — renet s'en charge. Les définir vous-même risque de créer des doublons ou des conflits.
- Voir le [template heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) pour une implémentation de référence compatible CRIU.

### Patterns d'application compatibles CRIU

- Gérez `ECONNRESET` sur toutes les connexions persistantes (pools de base de données, websockets, files de messages).
- Utilisez des bibliothèques de pool de connexions qui supportent la reconnexion automatique.
- Ajoutez `process.on("uncaughtException")` comme filet de sécurité pour les erreurs de sockets obsolètes provenant d'objets de bibliothèques internes.
- Les politiques de redémarrage sont gérées automatiquement par renet (supprimées pour CRIU, le watchdog gère la récupération).
- Évitez de dépendre du DNS Docker — utilisez les IPs de loopback pour la communication inter-services.

## Sécurité

- **Le chiffrement LUKS** est obligatoire pour les dépôts standard. Chaque dépôt a sa propre clé de chiffrement.
- **Les identifiants sont stockés dans la configuration CLI** (`~/.config/rediacc/rediacc.json`). Perdre la configuration signifie perdre l'accès aux volumes chiffrés.
- **Ne committez jamais d'identifiants** dans le contrôle de version. Utilisez `env_file` et générez les secrets dans `up()`.
- **Isolation des dépôts** : Le daemon Docker, le réseau et le stockage de chaque dépôt sont entièrement isolés des autres dépôts sur la même machine.
- **Isolation des agents** : Les agents IA fonctionnent par défaut en mode fork-only. Chaque dépôt possède sa propre clé SSH avec application du sandbox côté serveur (ForceCommand `sandbox-gateway`). Toutes les connexions sont isolées avec Landlock LSM, overlay OverlayFS du home et TMPDIR par dépôt. L'accès au système de fichiers entre dépôts est bloqué par le noyau.

## Déploiement

- **`rdc repo up`** exécute `up()` dans tous les Rediaccfiles.
- **`rdc repo up --mount`** ouvre d'abord le volume LUKS, puis exécute le cycle de vie. Requis après `backup push` vers une nouvelle machine.
- **`rdc repo down`** exécute `down()` et arrête le daemon Docker.
- **`rdc repo down --unmount`** ferme également le volume LUKS (verrouille le stockage chiffré).
- **Forks** (`rdc repo fork`) créent un clone CoW (copy-on-write) avec un nouveau GUID et networkId. Le fork partage la clé de chiffrement du parent.
- **Takeover** (`rdc repo takeover <fork> -m <machine>`) remplace les données du grand dépôt par celles d'un fork. Le grand conserve son identité (GUID, networkId, domaines, autostart, chaîne de sauvegardes). Les anciennes données de production sont conservées sous forme de fork de sauvegarde. Utilisation : tester une mise à jour sur un fork, vérifier, puis takeover en production. Réverter avec `rdc repo takeover <backup-fork> -m <machine>`.
- **Les routes proxy** mettent environ 3 secondes à devenir actives après le déploiement. L'avertissement « Proxy is not running » pendant `repo up` est informatif dans les environnements ops/dev.

## Erreurs courantes

- Utiliser `docker compose` au lieu de `renet compose` — les conteneurs n'obtiendront pas l'isolation réseau.
- Les politiques de redémarrage sont sûres — renet les supprime automatiquement et le watchdog gère la récupération.
- Utiliser `privileged: true` — inutile, renet injecte des capabilities CRIU spécifiques à la place.
- Ne pas se lier à `SERVICE_IP` — cause des conflits de ports entre dépôts.
- Coder les IPs en dur — utilisez la variable d'environnement `SERVICE_IP` ; les IPs sont allouées dynamiquement par networkId.
- Oublier `--mount` lors du premier déploiement après `backup push` — le volume LUKS nécessite une ouverture explicite.
- Utiliser `rdc term -c` comme contournement pour les commandes échouées — signalez les bugs à la place.
- `repo delete` effectue un nettoyage complet incluant les IPs de loopback et les unités systemd. Exécutez `rdc machine prune <name>` pour nettoyer les restes des suppressions anciennes.
