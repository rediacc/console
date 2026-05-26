---
title: "Riferimento server"
description: "Layout delle directory, comandi renet, servizi systemd e workflow per il server remoto. È il riferimento più completo per la gestione avanzata del server."
category: "Concepts"
order: 3
language: it
sourceHash: "f68c27543a2fe3ff"
sourceCommit: "a3b80f4e653e80766813a8c1d7ef563f00904147"
---

# Riferimento server

Questa pagina descrive cosa trovi quando accedi tramite SSH a un server Rediacc: il layout delle directory, i comandi `renet`, i servizi systemd e i workflow comuni.

La maggior parte degli utenti gestisce i server tramite `rdc` dalla propria workstation e non ha mai bisogno di questa pagina. È qui per il debug avanzato o quando devi lavorare direttamente sul server.

Per l'architettura di alto livello, consulta [Architettura](/it/docs/architecture). Per la differenza tra `rdc` e `renet`, consulta [rdc vs renet](/it/docs/rdc-vs-renet).

## Layout delle directory

```
/mnt/rediacc/                          # Datastore principale
├── repositories/                      # Immagini disco cifrate (LUKS)
│   └── {uuid}                         # Ognuna è un'immagine loop device
├── mounts/                            # Punti di mount per i repository decifrati
│   └── {uuid}/
│       ├── .rediacc.json              # Mapping servizio → slot IP
│       ├── .rediacc/docker/           # Dati daemon Docker (immagini, container)
│       └── {service-name}/            # Directory del servizio
│           ├── docker-compose.yml     # Definizione Compose
│           ├── Rediaccfile            # Hook del ciclo di vita (bash)
│           └── data/                  # Dati persistenti
├── immovable/                         # Contenuto condiviso di sola lettura
├── .credentials/                      # Segreti cifrati
└── .backup-*/                         # Snapshot BTRFS

/opt/rediacc/proxy/                    # Reverse proxy Traefik
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # Certificati ACME
└── traefik/dynamic/                   # File di route dinamiche

/run/rediacc/docker-{id}.sock          # Socket Docker per rete
/var/lib/rediacc/router/               # Stato del router (allocazioni porta)
```

## Comandi renet

`renet` è il binario lato server. Tutti i comandi richiedono privilegi di root (`sudo`).

### Ciclo di vita del repository

```bash
# Elenca tutti i repository
renet repository list

# Mostra i dettagli del repository
renet repository status --name {uuid}

# Avvia un repository (mount + esegui Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Ferma un repository (esegui Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Crea un nuovo repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (copia istantanea tramite reflink BTRFS)
renet repository fork --source {uuid} --target {new-uuid}

# Espandi un repository in esecuzione (senza downtime)
renet repository expand --name {uuid} --size 4G

# Elimina un repository e tutti i suoi dati
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Esegui comandi compose contro il daemon Docker di un repository specifico:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Esegui comandi docker direttamente:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Puoi anche usare il socket Docker direttamente:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Esegui sempre compose dalla directory che contiene `docker-compose.yml`, altrimenti Docker non troverà il file.

### Sandbox del filesystem

```bash
# Verifica il supporto Landlock
renet sandbox-exec --detect

# Esegui un comando all'interno di una sandbox Landlock (usato internamente)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` applica le restrizioni filesystem Landlock LSM, poi esegue il comando dato. Viene invocato automaticamente da `sandbox-gateway` (il gestore SSH ForceCommand) per tutte le connessioni a livello di repository.

### Hub per utente (ambienti di sviluppo)

L'Hub fornisce a ogni utente il proprio daemon Docker per gli ambienti di sviluppo, separato dai daemon `FlavorRediacc` per singolo repository.

```bash
# Installare / rimuovere le unita systemd dell'Hub per utente
sudo renet hub install
sudo renet hub uninstall

# Raccogliere i daemon Hub per utente inattivi
sudo renet hub gc
```

I daemon girano sotto uno dei due flavor, selezionato con `--flavor`:

```bash
# Daemon isolato per repository (bridge=none, iptables=false) — predefinito
sudo renet daemon start-foreground --flavor=rediacc ...

# Daemon Hub per utente (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

Il flavor `hub` abilita la normale rete bridge affinche i contenitori avviati dall'utente abbiano connettivita in uscita; il flavor `rediacc` impone l'isolamento loopback tra i repository. I log di audit dell'Hub vengono scritti in `/var/log/rediacc/hub/<user>.log`.

**Flag:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: regole di percorso Landlock
- `--home-overlay`: monta OverlayFS sulla home dir per l'isolamento in scrittura per singolo repository
- `--sandbox-dir`: workspace per singolo repository (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: imposta la directory di lavoro e carica `.envrc` per l'ambiente del repository
- `--run-as`: abbandona i privilegi dell'utente target dopo la configurazione
- `--reset-home`: cancella l'overlay home per singolo repository per un avvio fresco

**`sandbox-gateway`** è il gestore SSH ForceCommand impostato tramite `command=` in `authorized_keys`. La chiave SSH di ogni repository attiva il gateway con il nome del repository incorporato, non falsificabile dal client. Il gateway costruisce gli argomenti sandbox-exec ed esegue tramite sudo.

### Proxy e routing

```bash
renet proxy status          # Verifica Traefik + stato router
renet proxy routes          # Mostra tutte le route configurate
renet proxy refresh         # Aggiorna le route dai container in esecuzione
renet proxy up / down       # Avvia/ferma Traefik
renet proxy logs            # Visualizza i log del proxy
```

Le route vengono rilevate automaticamente dalle etichette dei container. Consulta [Networking](/it/docs/networking) per come configurare le etichette Traefik.

### Stato del sistema

```bash
renet ps                    # Stato generale del sistema
renet list all              # Tutto: sistema, container, repository
renet list containers       # Tutti i container su tutti i daemon Docker
renet list repositories     # Stato del repository e utilizzo disco
renet list system           # CPU, memoria, disco, rete
renet ips --network-id {id} # Allocazioni IP per una rete
```

### Gestione dei daemon

Ogni repository esegue il proprio daemon Docker. Puoi gestirli singolarmente:

```bash
renet daemon status --network-id {id}    # Stato del daemon Docker
renet daemon start  --network-id {id}    # Avvia il daemon
renet daemon stop   --network-id {id}    # Ferma il daemon
renet daemon logs   --network-id {id}    # Log del daemon
```

### Backup e ripristino

Invia backup a un'altra macchina o allo storage cloud:

```bash
# Invia a macchina remota (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Invia allo storage cloud (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Recupera da remoto
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# Elenca i backup remoti
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> La maggior parte degli utenti dovrebbe usare `rdc repo push/pull` al suo posto. I comandi `rdc` gestiscono credenziali e risoluzione della macchina automaticamente.

### Checkpoint (CRIU)

Il checkpoint salva lo stato dei container in esecuzione in modo che possano essere ripristinati in seguito:

```bash
renet checkpoint create    --network-id {id}   # Salva lo stato del container in esecuzione
renet checkpoint restore   --network-id {id}   # Ripristina dal checkpoint
renet checkpoint validate  --network-id {id}   # Verifica l'integrità del checkpoint
```

### Manutenzione

```bash
renet prune --dry-run       # Anteprima di reti e IP orfani
renet prune                 # Pulisce le risorse orfane
renet datastore status      # Stato del datastore BTRFS
renet datastore validate    # Verifica dell'integrità del filesystem
renet datastore expand      # Espande il datastore online
```

## Servizi Systemd

Ogni repository crea queste unità systemd:

| Unità | Scopo |
|-------|-------|
| `rediacc-docker-{id}.service` | Daemon Docker isolato |
| `rediacc-docker-{id}.socket` | Attivazione socket API Docker |
| `rediacc-loopback-{id}.service` | Configurazione alias IP loopback |

Servizi globali condivisi tra tutti i repository:

| Unità | Scopo |
|-------|-------|
| `rediacc-router.service` | Scoperta delle route (porta 7111) |
| `rediacc-autostart.service` | Montaggio dei repository all'avvio |
| `rediacc-autostart-reconcile.service` | Riconciliatore periodico dell'autostart (eseguito dal timer seguente) |
| `rediacc-autostart-reconcile.timer` | Attiva `renet repository reconcile` circa ogni 3 minuti per recuperare i repository autostart che si sono interrotti dopo l'avvio |

## Workflow comuni

### Distribuzione di un nuovo servizio

1. Crea un repository cifrato:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Montalo e aggiungi i tuoi file `docker-compose.yml`, `Rediaccfile` e `.rediacc.json`.
3. Avvialo:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Accesso a un container in esecuzione

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Trovare quale socket Docker esegue un container

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Ricreare un servizio dopo modifiche alla configurazione

```bash
sudo renet compose -- up -d
```

Esegui questo dalla directory con `docker-compose.yml`. I container modificati vengono ricreati automaticamente.

### Verificare tutti i container su tutti i daemon

```bash
renet list containers
```

## Suggerimenti

- Usa sempre `sudo` per i comandi `renet compose`, `renet repository` e `renet docker`; richiedono i privilegi di root per le operazioni LUKS e Docker
- Il separatore `--` è obbligatorio prima di passare argomenti a `renet compose` e `renet docker`
- Esegui compose dalla directory che contiene `docker-compose.yml`
- Le assegnazioni degli slot `.rediacc.json` sono stabili; non modificarle dopo il deployment
- Usa i percorsi `/run/rediacc/docker-{id}.sock` (systemd potrebbe modificare i percorsi legacy `/var/run/`)
- Esegui periodicamente `renet prune --dry-run` per trovare risorse orfane
- Gli snapshot BTRFS (`renet backup`) sono veloci ed economici; usali prima di apportare modifiche rischiose
- I repository sono cifrati con LUKS; perdere la password significa perdere i dati
