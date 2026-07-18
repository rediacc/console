---
title: "Server-Referenz"
description: "Verzeichnisstruktur, renet-Befehle, systemd-Dienste und Arbeitsabläufe für den entfernten Server."
category: "Concepts"
order: 3
language: de
sourceHash: "af2e8fc3da708d9a"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# Server-Referenz

Melden Sie sich per SSH bei einem Rediacc-Server an und hier ist, was Sie erhalten: die Verzeichnisstruktur, `renet`-Befehle, systemd-Dienste und die erforderlichen Arbeitsabläufe.

Die meisten Benutzer verwalten Server über `rdc` von ihrer Arbeitsstation aus und benötigen diese Seite nicht. Sie ist für erweitertes Debugging oder für den Fall gedacht, dass Sie direkt auf dem Server arbeiten müssen.

Die übergeordnete Architektur finden Sie unter [Architektur](/de/docs/architecture). Den Unterschied zwischen `rdc` und `renet` erläutert [rdc vs renet](/de/docs/rdc-vs-renet).

## Verzeichnisstruktur

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## renet-Befehle

`renet` ist die serverseitige Binärdatei. Alle Befehle erfordern Root-Rechte (`sudo`).

### Repository-Lebenszyklus

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Compose-Befehle gegen den Docker-Daemon eines bestimmten Repositorys ausführen:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Docker-Befehle direkt ausführen:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Sie können den Docker-Socket auch direkt verwenden:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Führen Sie compose immer aus dem Verzeichnis aus, das `docker-compose.yml` enthält, sonst findet Docker die Datei nicht.

### Dateisystem-Sandbox

```bash
# Landlock-Unterstützung prüfen
renet sandbox-exec --detect

# Einen Befehl in einer Landlock-Sandbox ausführen (intern verwendet)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` wendet Landlock-LSM-Dateisystembeschränkungen an und führt dann den angegebenen Befehl aus. Es wird automatisch von `sandbox-gateway` (dem SSH-ForceCommand-Handler) für alle Verbindungen auf Repository-Ebene aufgerufen.

### Benutzerspezifischer Hub (Entwicklungsumgebungen)

Der Hub gibt jedem Benutzer einen eigenen Docker-Daemon für Entwicklungsumgebungen, getrennt von den repository-spezifischen `FlavorRediacc`-Daemons.

```bash
# Benutzerspezifische Hub-systemd-Einheiten installieren / entfernen
sudo renet hub install
sudo renet hub uninstall

# Inaktive benutzerspezifische Hub-Daemons bereinigen
sudo renet hub gc
```

Daemons laufen unter einem von zwei Flavors, ausgewählt mit `--flavor`:

```bash
# Repository-isolierter Daemon (bridge=none, iptables=false) — der Standard
sudo renet daemon start-foreground --flavor=rediacc ...

# Benutzerspezifischer Hub-Daemon (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

Der `hub`-Flavor aktiviert normales Bridge-Networking, damit benutzerbetriebene Container ausgehende Verbindungen haben; der `rediacc`-Flavor erzwingt Loopback-Isolation zwischen Repositories. Hub-Audit-Logs werden nach `/var/log/rediacc/hub/<user>.log` geschrieben.

**Flags:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: Landlock-Pfadregeln
- `--home-overlay`: OverlayFS über das Home-Verzeichnis einbinden für repository-spezifische Schreibisolierung
- `--sandbox-dir`: Repository-spezifischer Arbeitsbereich (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: Arbeitsverzeichnis setzen und `.envrc` für die Repository-Umgebung laden
- `--run-as`: Privilegien nach dem Setup auf den Zielbenutzer absenken
- `--reset-home`: Repository-spezifisches Home-Overlay für einen Neustart löschen

**`sandbox-gateway`** ist der SSH-ForceCommand-Handler, der über `command=` in `authorized_keys` gesetzt wird. Der SSH-Schlüssel jedes Repositorys löst das Gateway mit dem eingebetteten Repository-Namen aus, der vom Client nicht gefälscht werden kann. Das Gateway erstellt sandbox-exec-Argumente und führt sie via sudo aus.

### Proxy und Routing

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Routen werden automatisch aus Container-Labels ermittelt. Wie Sie Traefik-Labels konfigurieren, beschreibt [Netzwerk](/de/docs/networking).

### Systemstatus

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Daemon-Verwaltung

Jedes Repository betreibt seinen eigenen Docker-Daemon. Sie können diese einzeln verwalten:

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Backup und Wiederherstellung

Backups auf einen anderen Rechner oder in den Cloud-Speicher übertragen:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> Die meisten Benutzer sollten stattdessen `rdc repo push/pull` verwenden. Die `rdc`-Befehle verarbeiten Anmeldedaten und Maschinenauflösung automatisch.

### Checkpointing (CRIU)

Checkpoints speichern den Zustand laufender Container, damit sie später wiederhergestellt werden können:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Wartung

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

### Datastore-Backends (Ceph RBD)

Ein Datastore ist entweder lokal (loop-gestütztes BTRFS auf der Festplatte der Maschine, der Standard) oder über ein RBD-Image von einem externen Ceph-Cluster gestützt. Das Backend wird zum Zeitpunkt von `init` gewählt:

```bash
# Lokales Backend (Standard)
renet datastore init --size 50G

# Ceph-RBD-Backend: BTRFS auf einem RBD-Image, gemappt von einem externen Ceph-Cluster
renet datastore init --backend ceph --pool rbd --image {name} --cluster ceph
```

Auf dem Ceph-Backend verwenden Fork und Unfork RBDs eigene Copy-on-Write-Primitive statt BTRFS-Reflinks:

```bash
renet datastore fork   --source {image} --target {new-image}   # RBD-Snapshot -> protect -> clone
renet datastore unfork --image {image}                         # einen Clone in Abhängigkeitsreihenfolge abbauen
```

Ceph-Knoten öffnen niemals LUKS (auf diesem Backend gibt es keine Per-Image-LUKS-Schicht), sodass sich ihr Speicherbedarf nach dem Ceph-Daemon-Tuning richtet (`osd_memory_target`), nicht nach KDF-Mathematik. Ein zweiter Client kann dasselbe RBD-Image schreibgeschützt mit einem lokalen Copy-on-Write-Overlay mappen, was der schreibarme Scale-out-Pfad ist.

### Kubernetes (renet kube)

Auf einem Cluster-Knoten umhüllt renet k3s auf dieselbe Weise wie Docker. `renet kube` ist das Compose-Analogon: Es injiziert `KUBECONFIG` und wendet Manifeste oder Helm-Charts aus dem `up()` eines Rediaccfile an.

```bash
sudo renet kube apply -f manifests/     # in den Namespace des Repos anwenden
sudo renet kube -- get pods             # an kubectl im gepinnten Namespace durchreichen
```

Cluster-Zustand liegt in Datastore-gestützten Copy-on-Write-Images (das k3s-`--data-dir` bindet innerhalb des Image-Mounts), was einen ganzen Cluster fork- und migrierbar macht. Persistent Volumes sind separate Copy-on-Write-Einheiten: RBD-Images auf Ceph (ein RADOS-Namespace pro Cluster-Instanz und pro Fork) oder kleine Datastore-Image-Dateien über einen lokalen PV-Provisioner auf dem lokalen Backend. Der nutzerseitige Workflow steht im [Kubernetes](/de/docs/kubernetes)-Guide; die CLI steuert diese Pfade über `rdc cluster` und die Cluster-fähigen `rdc repo`-Befehle.

## systemd-Dienste

Jedes Repository erstellt folgende systemd-Units:

| Unit | Zweck |
|------|-------|
| `rediacc-docker-{id}.service` | Isolierter Docker-Daemon |
| `rediacc-docker-{id}.socket` | Docker-API-Socket-Aktivierung |
| `rediacc-loopback-{id}.service` | Loopback-IP-Alias-Einrichtung |
| `rediacc-k3s-{id}.service` | Pro-Cluster-k3s-Knoten (nur Cluster-Hosts) |

Globale Dienste, die von allen Repositories gemeinsam genutzt werden:

| Unit | Zweck |
|------|-------|
| `rediacc-router.service` | Routenermittlung (Port 7111) |
| `rediacc-autostart.service` | Repository-Einbindung beim Start |
| `rediacc-autostart-reconcile.service` | Periodischer Autostart-Reconciler (wird vom Timer unten gestartet) |
| `rediacc-autostart-reconcile.timer` | Führt `renet repository reconcile` ungefähr alle 3 Minuten aus, um Autostart-Repos wiederherzustellen, die nach dem Start ausgefallen sind |

## Typische Arbeitsabläufe

### Einen neuen Dienst bereitstellen

1. Ein verschlüsseltes Repository erstellen:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Es einbinden und die Dateien `docker-compose.yml`, `Rediaccfile` und `.rediacc.json` hinzufügen.
3. Starten:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Auf einen laufenden Container zugreifen

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Herausfinden, welcher Docker-Socket einen Container betreibt

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Einen Dienst nach Konfigurationsänderungen neu erstellen

```bash
sudo renet compose -- up -d
```

Führen Sie dies aus dem Verzeichnis mit `docker-compose.yml` aus. Geänderte Container werden automatisch neu erstellt.

### Alle Container über alle Daemons prüfen

```bash
renet list containers
```

## Hinweise

- Verwenden Sie für `renet compose`-, `renet repository`- und `renet docker`-Befehle immer `sudo`, da sie Root-Rechte für LUKS- und Docker-Operationen benötigen
- Das Trennzeichen `--` ist erforderlich, bevor Argumente an `renet compose` und `renet docker` übergeben werden
- Führen Sie compose aus dem Verzeichnis aus, das `docker-compose.yml` enthält
- Slot-Zuweisungen in `.rediacc.json` sind stabil und dürfen nach der Bereitstellung nicht geändert werden
- Verwenden Sie `/run/rediacc/docker-{id}.sock`-Pfade (systemd kann veraltete `/var/run/`-Pfade ändern)
- Führen Sie `renet prune --dry-run` von Zeit zu Zeit aus, um verwaiste Ressourcen zu finden
- BTRFS-Snapshots (`renet backup`) sind schnell und günstig, verwenden Sie sie vor riskanten Änderungen
- Repositories sind LUKS-verschlüsselt, der Verlust des Passworts bedeutet den Verlust der Daten
