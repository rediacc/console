---
title: Quick Start
description: Avvia un servizio containerizzato sul tuo server in pochi minuti. È più veloce di quanto ti aspetti.
category: Guides
order: -1
language: it
---

# Quick Start

Distribuisci un ambiente container cifrato e isolato sul tuo server. Nessun account cloud o dipendenza da SaaS. Tutto gira sull'hardware che controlli tu.

---

## Introduzione

### Concetti Chiave

Una repository è un singolo file cifrato su disco. Spostala, fai il backup, esegui un fork. È solo un file. Quando viene montata, diventa una cartella con un demone Docker dedicato e i dati della tua app all'interno.

Pensa a una repository come a una chiavetta USB. È qualcosa in mano tua, e quando la inserisci diventa visibile e accessibile al sistema. Le tue app e i tuoi dati sono completamente portabili. Plug & Run su qualsiasi macchina, su qualsiasi provider cloud.

**Due strumenti, due ruoli:**

- **rdc** = CLI sul tuo laptop (TypeScript, installato globalmente)
- **renet** = orchestratore sul server (binario Go, gestisce demoni/reti/isolamento)
- RDC provvede renet automaticamente durante `config machine setup`. Nessuna configurazione manuale sul server.

> [Architecture](/it/docs/architecture) spiega il modello di sicurezza. [rdc vs renet](/it/docs/rdc-vs-renet) spiega quale strumento usare quando.

### 1. Installa la CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Verifica: Node, chiave SSH, renet, Docker
```

> Windows, Alpine, Arch: vedi [Installation](/it/docs/installation). Requisiti di sistema completi: [Requirements](/it/docs/requirements).

### 2. Configurazione Chiave SSH

rdc si connette tramite SSH. Il server deve fidarsi della tua chiave pubblica prima che rdc possa raggiungerlo.

```bash
# Genera una chiave (salta se ne hai già una)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copia la chiave pubblica sul server (chiederà la password)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Indica a rdc quale chiave usare
rdc config ssh set --key ~/.ssh/id_ed25519
```

Ogni comando rdc si autentica ora con questa chiave. Nessuna password.

### 3. Aggiungi il Tuo Server

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # Provvede renet + crea il datastore
```

**Cosa succede:** la chiave host SSH viene scansionata, il binario renet viene caricato, il datastore cifrato viene inizializzato sul server. Pronto per le repository.

> Dimensionamento del datastore, Ceph RBD, provider cloud: [Machine Setup](/it/docs/setup). Errori SSH: [Troubleshooting](/it/docs/troubleshooting).

### 4. File di Config

```bash
rdc config show                            # Riepilogo leggibile
cat ~/.config/rediacc/rediacc.json         # JSON grezzo: macchine, repo, archiviazioni, chiave SSH
```

**Un file = un ambiente.** Copialo su un altro laptop e sei pronto.

---

## Lavorare con una Repository

### 1. Crea una Repository

```bash
rdc repo create --name my-app -m my-server --size 2G  # Crea una repository cifrata da 2 GB
```

Crea il volume cifrato, lo monta e avvia il suo demone Docker. La repository viene registrata nel tuo config ed è pronta per l'uso.

> Ridimensionamento, eliminazione, validazione: [Repositories](/it/docs/repositories).

### 2. Applica un Template

```bash
rdc repo template list                                        # Mostra i template incorporati
rdc repo template apply --name app-postgres -m my-server -r my-app  # Distribuisce docker-compose.yml + Rediaccfile
```

I template forniscono un `docker-compose.yml`, un `Rediaccfile` e file di supporto. Senza un template (o il tuo file compose), non c'è nulla da avviare.

### 3. Avvia la Repository

```bash
rdc repo up --name my-app -m my-server  # Esegui Rediaccfile up()
rdc repo list -m my-server                           # Vedi tutte le repository sulla macchina
rdc repo status --name my-app -m my-server  # Stato mount, Docker, dimensione, cifratura
```

`repo up` monta automaticamente se necessario. Nessun flag richiesto.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # Apre VS Code SSH, entra nel sandbox della repository
```

Stai modificando file *all'interno* del volume cifrato. `docker ps` mostra solo i container di questa repository. Salva, esegui compose up, itera.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Dove viene eseguito** | Il tuo laptop (CLI) | All'interno del sandbox VS Code |
| **Cosa fa** | SSH -> auto-mount -> esegue Rediaccfile `up()` | Esegue direttamente Rediaccfile `up()` |
| **Caso d'uso** | CI/CD, automazione, operazioni remote | Inner loop dello sviluppatore |
| **Isolamento** | Orchestra dall'esterno | Già all'interno del sandbox |

**Flusso demo:** `rdc repo template apply` -> `rdc vscode connect -m my-server -r my-app` -> modifica `docker-compose.yml` -> `renet dev up` -> vedi l'app in esecuzione -> itera.

> Struttura Rediaccfile: [Services](/it/docs/services). Quando usare quale strumento: [rdc vs renet](/it/docs/rdc-vs-renet).

### 6. Modello di Isolamento

- **Utente universale** (`rediacc`): Stesso UID su ogni macchina. Sposta una repository su un altro server e la proprietà dei file funziona immediatamente. Nessun problema con `chown`.
- **Demone Docker per repository**: Ogni repository ottiene il proprio demone Docker isolato. `docker ps` mostra solo i container di QUESTA repository.
- **Sandbox Landlock + OverlayFS**: La shell VS Code ha accesso al filesystem limitato. Non puoi leggere altre repository. Le scritture in `$HOME` sono overlay per repository.

> Come funziona l'isolamento: [Architecture](/it/docs/architecture). Ciclo di vita Rediaccfile: [Services](/it/docs/services).

### 7. Terminale, Sync e Tunnel

**Terminale:**
```bash
rdc term connect -m my-server -r my-app                            # SSH nel sandbox della repository
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # Esegui comando ed esci
rdc term connect -m my-server                                   # SSH sulla macchina (senza sandbox)
```

**Sincronizzazione file (rsync su SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # Carica una directory
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # Carica un singolo file
rdc repo sync download -m my-server -r my-app --local ./backup                              # Scarica una directory
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # Scarica un singolo file
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # Anteprima prima
```

**Tunnel (port-forwarding SSH al container):**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # Rileva automaticamente la porta per il container app
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # Tunnel Postgres
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # Porta locale personalizzata
```

Esegui il tunnel -> apri `localhost:3000` nel browser -> app live dal server remoto.

> Sync, terminale, dettagli VS Code: [Tools](/it/docs/tools).

---

## Fork e Backup

### 1. Repository Grand e Fork

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # Clone CoW istantaneo + avvio
rdc repo list -m my-server                                  # Mostra: my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # Elimina il fork, grand intatto
```

**Clone istantaneo, senza copia dei dati.** CoW (copy-on-write). Microsecondi, nessun dato copiato. I blocchi sono condivisi finché un lato non scrive.

**Casi d'uso:**
- **AI / ML:** Fork del dataset di produzione, esegui esperimento, scarta o promuovi
- **DevOps:** Fork -> testa la migrazione -> elimina se fallisce, promuovi se funziona
- **Backup:** Fork = snapshot istantaneo, caricalo fuori sede

> Ciclo di vita del fork, fork cross-machine: [Repositories](/it/docs/repositories).

### 2. Carica su un'Altra Macchina

```bash
# Carica la repository su un'altra macchina
rdc repo push --name my-app -m my-server --to backup-server

# Carica e distribuisci automaticamente sulla destinazione
rdc repo push --name my-app -m my-server --to backup-server --up

# Carica con checkpoint CRIU (migrazione live, preserva lo stato della memoria)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# Carica su una nuova macchina (provisioning automatico tramite provider cloud)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. Carica su Archiviazione Cloud (OneDrive, Google Drive, S3)

```bash
# Importa il tuo config rclone come backend di archiviazione
rdc config storage import --file ~/rclone.conf

# Elenca le archiviazioni disponibili
rdc storage list

# Carica la repository sull'archiviazione cloud
rdc repo push --name my-app -m my-server --to my-s3-backup

# Elenca i backup sull'archiviazione
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` rileva automaticamente se la destinazione è una macchina o un backend di archiviazione. Funziona con qualsiasi provider supportato da rclone: S3, R2, B2, OneDrive, Google Drive, SFTP, ecc.

### 4. Scarica da Remoto

```bash
# Scarica la repository da una macchina cloud al tuo server locale
rdc repo pull --name my-app -m my-local-server --from cloud-server

# Scarica dall'archiviazione cloud
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# Scarica e avvia immediatamente
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**Perché scaricare?** La tua macchina locale è dietro NAT. Il cloud non può caricare da te. Ma tu puoi raggiungere il cloud. Il pull porta la repository a casa.

**Ciclo completo:** Crea in sviluppo -> carica sul cloud -> scarica in produzione -> `--up`. Una repository, qualsiasi macchina, qualsiasi cloud.

> Pianificazione, backup automatici, ripristino: [Backup & Restore](/it/docs/backup-restore).

---

## Proxy e SSL

### 1. Config Infrastruttura

```bash
rdc config infra set -m my-server  # Configura: dominio base, IP pubblici, intervalli di porta
rdc config infra show -m my-server  # Rivedi la configurazione
rdc config infra push -m my-server  # Carica la config proxy in remoto
```

**Come funziona il routing:**
- Traefik rileva automaticamente i container tramite le label `rediacc.service_name` e `rediacc.service_port`
- Routes: `{service}-{networkId}.{baseDomain}` -> IP:porta del container
- SSL: Let's Encrypt tramite sfida DNS-01 Cloudflare (rinnovo automatico, certificati wildcard)

### 2. Template Proxy

```bash
rdc repo template apply --name proxy -m my-server -r infra  # Distribuisce il proxy in una repository
rdc repo up --name infra -m my-server  # Avvia Traefik
```

Traefik instrada ora il traffico esterno a tutte le repository su questa macchina. Ogni container ottiene automaticamente un endpoint HTTPS.

```bash
# Naviga su https://my-app.example.com → instradato al container
# Forwarding TCP/UDP per database:
#   rediacc.tcp_ports=3306,5432 → porte esterne allocate automaticamente
```

> Regole di routing, DNS, configurazione TLS: [Networking](/it/docs/networking).

---

## Prossimi Passi

- **[Migration Guide](/it/docs/migration)** - Porta i progetti esistenti nelle repository Rediacc
- **[Monitoring](/it/docs/monitoring)** - Salute della macchina, container, servizi, diagnostica
- **[CLI Reference](/it/docs/cli-application)** - Riferimento completo dei comandi
- **[Cheat Sheet](/it/docs/rdc-cheat-sheet)** - Consultazione rapida dei comandi
- **[Troubleshooting](/it/docs/troubleshooting)** - Soluzioni per i problemi comuni
- **[Rules of Rediacc](/it/docs/rules-of-rediacc)** - Best practice Rediaccfile e checklist di distribuzione
