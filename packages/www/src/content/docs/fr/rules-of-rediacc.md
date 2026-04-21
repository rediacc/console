---
title: Règles de Rediacc
description: >-
  Règles et conventions essentielles pour construire des applications sur la
  plateforme Rediacc. Couvre Rediaccfile, compose, réseau, stockage, CRIU et
  déploiement.
category: Guides
order: 5
language: fr
sourceHash: 9365e0cabf7e8f03
sourceCommit: d5c06171af0ef58b551a9682905d98af81e496cd
---

# Règles de Rediacc

Chaque dépôt Rediacc s'exécute dans un environnement isolé avec son propre daemon Docker, volume LUKS chiffré et plage d'IP dédiée. Ces règles garantissent que votre application fonctionne correctement au sein de cette architecture.

## Rediaccfile

- **Chaque dépôt a besoin d'un Rediaccfile**, un script bash avec des fonctions de cycle de vie.
- **Fonctions du cycle de vie** : `up()`, `down()`. Optionnel : `info()`.
- `up()` démarre vos services. `down()` les arrête.
- `info()` fournit des informations d'état (état des conteneurs, logs récents, santé).
- Rediaccfile est sourcé par renet, il a accès aux variables shell, pas seulement aux variables d'environnement.

### Variables d'environnement disponibles dans Rediaccfile

| Variable | Exemple | Description |
|----------|---------|-------------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Chemin racine du dépôt monté |
| `REDIACC_NETWORK_ID` | `6336` | Identifiant d'isolation réseau |
| `REDIACC_REPOSITORY` | `abc123-...` | GUID du dépôt |
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

- **Utilisez `renet compose`, jamais `docker compose`**, renet injecte l'isolation réseau, le réseau hôte, les IPs de loopback et les labels de service.
- **NE définissez PAS `network_mode`** dans votre fichier compose, renet force `network_mode: host` sur tous les services. Toute valeur que vous définissez est écrasée.
- **NE définissez PAS les labels `rediacc.*`**, renet auto-injecte `rediacc.network_id`, `rediacc.service_ip` et `rediacc.service_name`.
- **Les mappages `ports:` sont ignorés** en mode réseau hôte. Ajoutez le label `rediacc.service_port` pour le routage HTTP (les services sans ce label n'obtiennent pas de routes HTTP). Utilisez les labels `rediacc.tcp_ports`/`rediacc.udp_ports` pour la redirection TCP/UDP.
- **Les politiques de redémarrage (`restart: always`, `on-failure`, etc.) sont sûres à utiliser**, renet les supprime automatiquement pour la compatibilité CRIU. Le watchdog du routeur récupère automatiquement les conteneurs arrêtés selon la politique originale enregistrée dans `.rediacc.json`.
- **Les paramètres dangereux sont bloqués par défaut**, `privileged: true`, `pid: host`, `ipc: host` et les bind mounts vers des chemins système sont rejetés. Utilisez `renet compose --unsafe` pour contourner à vos risques et périls.

### Variables d'environnement à l'intérieur des conteneurs

Renet auto-injecte celles-ci dans chaque conteneur :

| Variable | Description |
|----------|-------------|
| `SERVICE_IP` | IP de loopback dédiée de ce conteneur |
| `REDIACC_NETWORK_ID` | ID d'isolation réseau |

### Nommage des services et routage

- Le **nom du service** compose devient le préfixe de l'URL d'auto-route.
- **Grand repos** : `https://{service}.{repo}.{machine}.{baseDomain}` (ex. : `https://myapp.marketing.server-1.example.com`).
- **Fork repos** : `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (ex. : `https://myapp-fork-staging.marketing.server-1.example.com`). Le séparateur `-fork-` empêche les collisions d'URL avec les noms de service du grand repo. L'URL du fork utilise toujours le certificat wildcard existant du dépôt parent, donc aucun nouveau certificat n'est nécessaire.
- Pour les domaines personnalisés, utilisez les labels Traefik (attention : les domaines personnalisés ne sont PAS compatibles avec fork, le domaine appartient au grand repo).

## Réseau

- **Chaque dépôt obtient son propre daemon Docker** à `/var/run/rediacc/docker-<networkId>.sock`.
- **Chaque service reçoit une IP de loopback unique** dans un sous-réseau /26 (ex. `127.0.24.192/26`).
- **La liaison est automatique** : Les services peuvent se lier à `0.0.0.0` ou `localhost`, le noyau réécrit l'adresse de manière transparente vers l'IP de loopback assignée au service. La liaison explicite à `${SERVICE_IP}` fonctionne toujours mais n'est plus requise.
- **Les health checks peuvent utiliser `localhost`** ou `${SERVICE_IP}`. Exemple : `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Les connexions inter-dépôts sont bloquées par le noyau** : Le noyau bloque automatiquement les connexions aux IPs de loopback en dehors du sous-réseau `/26` du dépôt. Un service dans un dépôt ne peut pas atteindre les services d'un autre dépôt.
- **Communication inter-services** : Utilisez les **noms de service** (ex. `db`, `redis`), renet injecte automatiquement chaque nom de service comme nom d'hôte qui résout vers la bonne IP. Les noms DNS Docker NE fonctionnent PAS en mode hôte, mais les noms de service via `/etc/hosts` fonctionnent. Évitez d'intégrer `${DB_IP}` ou similaire dans des fichiers de configuration persistants (ex. chaînes de connexion stockées dans une base de données), en cas de fork, l'IP brute est reportée et pointe vers le mauvais dépôt. Les noms de service se résolvent toujours correctement par dépôt.
- **Les conflits de ports sont impossibles** entre dépôts, chacun a son propre daemon Docker et sa propre plage d'IP.
- **Redirection de ports TCP/UDP** : Ajoutez des labels pour exposer les ports non-HTTP :
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Stockage

- **Toutes les données Docker sont stockées dans le dépôt chiffré**, le `data-root` de Docker se trouve à `{mount}/.rediacc/docker/data` dans le volume LUKS. Les volumes nommés, les images et les couches de conteneurs sont tous chiffrés, sauvegardés et forkés automatiquement.
- **Les bind mounts vers `${REDIACC_WORKING_DIR}/...` sont recommandés** pour la clarté, mais les volumes nommés fonctionnent également en toute sécurité.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (recommandé)
    - pgdata:/var/lib/postgresql/data      # named volume (également sûr)
  ```
- Le volume LUKS est monté à `/mnt/rediacc/mounts/<guid>/`.
- Les snapshots BTRFS capturent l'intégralité du fichier de support LUKS, y compris toutes les données montées en bind.
- Le datastore est un fichier de pool BTRFS de taille fixe sur le disque système. Utilisez `rdc machine query --name <name> --system` pour voir l'espace libre effectif. Agrandissez avec `rdc datastore resize`.

## CRIU (Migration à chaud)

- **Activation par label** : Ajoutez `rediacc.checkpoint=true` aux conteneurs que vous souhaitez checkpointer. Les conteneurs sans ce label (bases de données, caches) démarrent à froid et récupèrent via leurs propres mécanismes (WAL, LDF, AOF).
- **`repo down --checkpoint`** sauvegarde l'état du processus avant l'arrêt, le prochain `repo up` restaure automatiquement. **C'est le flux principal sur la même machine**, vérifié fonctionnel.
- **`backup push --checkpoint`** capture la mémoire des processus en cours ainsi que l'état du disque pour les conteneurs labellisés, puis transfère le volume vers une autre machine. Restauration sur la machine cible via `repo up`.
- **`repo fork --checkpoint`** capture l'état du processus avant le fork et CoW-clone le checkpoint avec le fork. ⚠️ Sur la même machine, le `repo up` suivant sur le fork **échoue actuellement** avec `criu failed: type RESTORE errno 0` tant que le parent est encore en cours d'exécution. Bugs CRIU upstream [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Utilisez `repo down --checkpoint` pour la sauvegarde/restauration sur place, ou `backup push --checkpoint` pour la migration inter-machines.
- **`repo up`** détecte automatiquement les données de checkpoint et restaure si trouvé. Utilisez `--skip-checkpoint` pour forcer un démarrage à froid.
- **Restauration tenant compte des dépendances** : Utilise `depends_on` de compose pour démarrer les bases de données d'abord (attendre healthy), puis restaurer CRIU des conteneurs applicatifs.
- **Les connexions TCP deviennent obsolètes après la restauration**, les applications doivent gérer `ECONNRESET` et se reconnecter. CRIU ne préserve pas l'état des connexions TCP actives lors de la restauration dans aucun flux supporté.
- **Le mode expérimental Docker** est activé automatiquement sur les daemons par dépôt.
- **CRIU est installé** lors de `rdc config machine setup`.
- **`/etc/criu/runc.conf`** est configuré avec `tcp-established` par défaut.
- **Les paramètres de sécurité sont auto-injectés pour les conteneurs labellisés**, `renet compose` ajoute ce qui suit aux conteneurs avec `rediacc.checkpoint=true` :
  - `cap_add` : `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (ensemble minimal pour CRIU sur kernel 5.9+)
  - `security_opt` : `apparmor=unconfined` (le support AppArmor de CRIU n'est pas encore stable en amont)
  - `userns_mode: host` (CRIU nécessite l'accès au namespace init pour `/proc/pid/map_files`)
- Les conteneurs sans le label fonctionnent avec une posture de sécurité plus propre (pas de capabilities supplémentaires).
- Le profil seccomp par défaut de Docker est préservé, CRIU utilise `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) pour suspendre temporairement les filtres lors du checkpoint/restore.
- **Ne définissez PAS les capabilities CRIU manuellement** dans votre fichier compose, renet s'en charge selon le label.
- Voir le [template heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) pour une implémentation de référence compatible CRIU.

### Patterns d'application compatibles CRIU

- Gérez `ECONNRESET` sur toutes les connexions persistantes (pools de base de données, websockets, files de messages).
- Utilisez des bibliothèques de pool de connexions qui supportent la reconnexion automatique.
- Ajoutez `process.on("uncaughtException")` comme filet de sécurité pour les erreurs de sockets obsolètes provenant d'objets de bibliothèques internes.
- Les politiques de redémarrage sont gérées automatiquement par renet (supprimées pour CRIU, le watchdog gère la récupération).
- Évitez de dépendre du DNS Docker, utilisez les IPs de loopback pour la communication inter-services.

### Politiques de sécurité de l'hôte par système d'exploitation

Sur les cinq systèmes d'exploitation serveur officiellement supportés (voir [Prérequis](/en/docs/requirements)), le daemon Docker de chaque dépôt et les conteneurs qu'il exécute utilisent les **labels de conteneur par défaut**. `rdc config machine setup` n'installe ni politique SELinux personnalisée ni profil AppArmor personnalisé.

- **Ubuntu 24.04 / openSUSE Leap 16.0** : AppArmor est activé par défaut. Les conteneurs s'exécutent sous le profil docker-container par défaut. La seule exception est CRIU (`apparmor=unconfined` pour les conteneurs portant `rediacc.checkpoint=true`, comme indiqué ci-dessus).
- **Fedora 43 / Oracle Linux 10** : SELinux s'exécute en mode enforcing par défaut. Les conteneurs reçoivent le contexte `container_t` standard. Aucune installation de politique supplémentaire n'est nécessaire. Si une étape de configuration échoue avec des refus AVC, consultez [Dépannage : refus SELinux](/en/docs/troubleshooting).
- **Debian 13** : AppArmor est disponible mais n'est pas appliqué par défaut sur tous les domaines. Les conteneurs utilisent tout de même le profil docker-container.

Aucun indicateur de posture de sécurité spécifique au système d'exploitation n'est requis ; `rdc` et `renet` détectent ce qui est en cours d'exécution et produisent la même isolation par dépôt sur les cinq distributions.

## Sécurité

- **Le chiffrement LUKS** est obligatoire pour les dépôts standard. Chaque dépôt a sa propre clé de chiffrement.
- **Les identifiants sont stockés dans la configuration CLI** (`~/.config/rediacc/rediacc.json`). Perdre la configuration signifie perdre l'accès aux volumes chiffrés.
- **Ne committez jamais d'identifiants** dans le contrôle de version. Utilisez `env_file` et générez les secrets dans `up()`.
- **Isolation des dépôts** : Le daemon Docker, le réseau et le stockage de chaque dépôt sont entièrement isolés des autres dépôts sur la même machine.
- **Isolation des agents** : Les agents IA fonctionnent par défaut en mode fork-only. Chaque dépôt possède sa propre clé SSH avec application du sandbox côté serveur (ForceCommand `sandbox-gateway`). Toutes les connexions sont isolées avec Landlock LSM, overlay OverlayFS du home et TMPDIR par dépôt. L'accès au système de fichiers entre dépôts est bloqué par le noyau.
- **`sudo` est désactivé à l'intérieur du sandbox d'un dépôt, par conception.** L'isolation du système de fichiers par Landlock nécessite `NoNewPrivs`, qui empêche toute élévation de privilèges, et `sudo` échouera donc avec `no new privileges flag is set`. L'utilisateur propriétaire du dépôt dispose déjà des permissions nécessaires pour tout ce qui se trouve dans le point de montage et le socket Docker du dépôt. Pour des opérations réellement privilégiées (installation de paquets hôtes, réglages du noyau), exécutez-les en dehors du sandbox ou depuis une fonction `up()` d'un Rediaccfile exécutée par le chemin infrastructure.
- **Le réseau bridge Docker est désactivé sur chaque daemon par dépôt.** Le `daemon.json` de chaque dépôt contient `"bridge": "none"` et `"iptables": false`, de sorte qu'un simple `docker run <image>` crée un conteneur avec uniquement une interface de loopback et aucune connectivité sortante. Ce n'est pas un bug, c'est ainsi que l'isolation inter-dépôts est appliquée : les hooks eBPF au niveau du noyau qui empêchent un dépôt d'atteindre les IPs de loopback d'un autre dépôt ne s'appliquent qu'aux conteneurs vivant dans le namespace réseau de l'hôte. Pour les services de production, utilisez `renet compose`, qui injecte automatiquement `network_mode: host`. Pour les conteneurs ad hoc ponctuels dans un shell, passez explicitement `--network host`.

## Déploiement

- **`rdc repo up`** monte automatiquement le volume LUKS s'il n'est pas monté, puis exécute `up()` dans tous les Rediaccfiles.
- **`rdc repo down`** exécute `down()` et arrête le daemon Docker.
- **`rdc repo down --unmount`** ferme également le volume LUKS (verrouille le stockage chiffré).
- **Forks** (`rdc repo fork`) créent un clone CoW (copy-on-write) avec un nouveau GUID et networkId, en **temps constant quelle que soit la taille du dépôt**. Le reflink BTRFS duplique les métadonnées de l'image, pas les données, si bien qu'un dépôt de 100 Go se fork en autant de secondes qu'un dépôt de 1 Go. Le fork partage la clé de chiffrement du parent.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) remplace les données du grand dépôt par celles d'un fork. Le grand conserve son identité (GUID, networkId, domaines, autostart, chaîne de sauvegardes). Les anciennes données de production sont conservées sous forme de fork de sauvegarde. Utilisation : tester une mise à jour sur un fork, vérifier, puis takeover en production. Réverter avec `rdc repo takeover --name <backup-fork> -m <machine>`.
- **Les routes proxy** mettent environ 3 secondes à devenir actives après le déploiement. L'avertissement « Proxy is not running » pendant `repo up` est informatif dans les environnements ops/dev.
- **`rdc repo up` et `rdc repo fork --up` impriment le modèle d'URL** à la fin du déploiement pour les services étiquetés avec `rediacc.service_port`. Remplacez `{service}` par le nom de votre service exposé pour obtenir l'URL exacte. Les services sans `rediacc.service_port` (bases de données, workers) n'obtiennent pas de routes et ne sont pas affichés.

## Erreurs courantes

- Utiliser `docker compose` au lieu de `renet compose`, les conteneurs n'obtiendront pas l'isolation réseau.
- Les politiques de redémarrage sont sûres, renet les supprime automatiquement et le watchdog gère la récupération.
- Utiliser `privileged: true`, inutile, renet injecte des capabilities CRIU spécifiques à la place.
- Coder en dur des IPs brutes dans des fichiers de configuration persistants - utilisez les noms de service pour les connexions afin de préserver l'isolation du fork.
- Utiliser `rdc term connect -c` comme contournement pour les commandes échouées, signalez les bugs à la place.
- `repo delete` effectue un nettoyage complet incluant les IPs de loopback et les unités systemd. Exécutez `rdc machine prune --name <name>` pour nettoyer les restes des suppressions anciennes.
