---
title: "Règles de Rediacc"
description: "Règles et conventions essentielles pour construire des applications sur la plateforme Rediacc. Couvre Rediaccfile, compose, réseau, stockage, CRIU et déploiement."
category: "Guides"
order: 5
language: fr
sourceHash: 166f333b848c718b
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
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
- **N'utilisez PAS `restart: always` ni `restart: unless-stopped`** — ceux-ci entrent en conflit avec le checkpoint/restore CRIU. Utilisez `restart: on-failure` ou omettez-le.
- **N'utilisez PAS les volumes nommés Docker** — ils résident en dehors du dépôt chiffré et ne seront pas inclus dans les sauvegardes ni les forks.

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

## Réseau

- **Chaque dépôt obtient son propre daemon Docker** à `/var/run/rediacc/docker-<networkId>.sock`.
- **Chaque service reçoit une IP de loopback unique** dans un sous-réseau /26 (ex. `127.0.24.192/26`).
- **Liez à `SERVICE_IP`**, pas à `0.0.0.0` — le réseau hôte signifie que `0.0.0.0` entrerait en conflit avec d'autres dépôts.
- **Communication inter-services** : Utilisez les IPs de loopback ou la variable d'environnement `SERVICE_IP`. Les noms DNS Docker NE fonctionnent PAS en mode hôte.
- **Les conflits de ports sont impossibles** entre dépôts — chacun a son propre daemon Docker et sa propre plage d'IP.
- **Redirection de ports TCP/UDP** : Ajoutez des labels pour exposer les ports non-HTTP :
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Stockage

- **Toutes les données persistantes doivent utiliser des bind mounts `${REPOSITORY_PATH}/...`.**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Les volumes nommés Docker résident en dehors du dépôt LUKS — ils ne sont **pas chiffrés**, **pas sauvegardés** et **pas inclus dans les forks**.
- Le volume LUKS est monté à `/mnt/rediacc/mounts/<guid>/`.
- Les snapshots BTRFS capturent l'intégralité du fichier de support LUKS, y compris toutes les données montées en bind.

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
- Évitez `restart: always` — cela interfère avec la restauration CRIU.
- Évitez de dépendre du DNS Docker — utilisez les IPs de loopback pour la communication inter-services.

## Sécurité

- **Le chiffrement LUKS** est obligatoire pour les dépôts standard. Chaque dépôt a sa propre clé de chiffrement.
- **Les identifiants sont stockés dans la configuration CLI** (`~/.config/rediacc/rediacc.json`). Perdre la configuration signifie perdre l'accès aux volumes chiffrés.
- **Ne committez jamais d'identifiants** dans le contrôle de version. Utilisez `env_file` et générez les secrets dans `up()`.
- **Isolation des dépôts** : Le daemon Docker, le réseau et le stockage de chaque dépôt sont entièrement isolés des autres dépôts sur la même machine.
- **Isolation des agents** : Par défaut, les agents IA fonctionnent en mode fork-only. Ils ne peuvent modifier que des dépôts fork, pas les dépôts grand (originaux). Les commandes exécutées via `term_exec` ou `rdc term` avec un contexte de dépôt sont isolées au niveau du noyau avec Landlock LSM, ce qui empêche l'accès au système de fichiers entre dépôts.

## Déploiement

- **`rdc repo up`** exécute `up()` dans tous les Rediaccfiles.
- **`rdc repo up --mount`** ouvre d'abord le volume LUKS, puis exécute le cycle de vie. Requis après `backup push` vers une nouvelle machine.
- **`rdc repo down`** exécute `down()` et arrête le daemon Docker.
- **`rdc repo down --unmount`** ferme également le volume LUKS (verrouille le stockage chiffré).
- **Forks** (`rdc repo fork`) créent un clone CoW (copy-on-write) avec un nouveau GUID et networkId. Le fork partage la clé de chiffrement du parent.
- **Les routes proxy** mettent environ 3 secondes à devenir actives après le déploiement. L'avertissement « Proxy is not running » pendant `repo up` est informatif dans les environnements ops/dev.

## Erreurs courantes

- Utiliser `docker compose` au lieu de `renet compose` — les conteneurs n'obtiendront pas l'isolation réseau.
- Utiliser `restart: always` — empêche la restauration CRIU et interfère avec `repo down`.
- Utiliser des volumes nommés Docker — les données ne sont pas chiffrées, pas sauvegardées, pas forkées.
- Se lier à `0.0.0.0` — cause des conflits de ports entre dépôts en mode réseau hôte.
- Coder les IPs en dur — utilisez la variable d'environnement `SERVICE_IP` ; les IPs sont allouées dynamiquement par networkId.
- Oublier `--mount` lors du premier déploiement après `backup push` — le volume LUKS nécessite une ouverture explicite.
- Utiliser `rdc term -c` comme contournement pour les commandes échouées — signalez les bugs à la place.
