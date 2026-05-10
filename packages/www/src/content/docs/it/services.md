---
title: Servizi
description: >-
  Distribuisci e gestisci servizi containerizzati usando Rediaccfile, networking
  dei servizi e autostart. È possibile configurare l'avvio automatico così il servizio non si interrompe mai.
category: Guides
order: 5
language: it
---

# Servizi

Questa pagina descrive come distribuire e gestire servizi containerizzati: Rediaccfile, networking dei servizi, avvio/arresto, operazioni in blocco e autostart.

## Il Rediaccfile

Il **Rediaccfile** è uno script Bash che definisce come i tuoi servizi vengono avviati e fermati. Viene **sourced** (non eseguito come processo separato), quindi le sue funzioni condividono lo stesso contesto shell e hanno accesso a tutte le variabili d'ambiente esportate. Deve essere denominato `Rediaccfile` o `rediaccfile` (senza distinzione tra maiuscole e minuscole) e posizionato all'interno del filesystem montato del repository.

I Rediaccfile vengono rilevati in due posizioni:
1. La **root** del percorso di mount del repository
2. Le **sottodirectory di primo livello** del percorso di mount (non ricorsivo)

Le directory nascoste (nomi che iniziano con `.`) vengono ignorate.

### Funzioni del ciclo di vita

Un Rediaccfile contiene fino a due funzioni:

| Funzione | Quando viene eseguita | Scopo | Comportamento in caso di errore |
|----------|-----------------------|-------|----------------------------------|
| `up()` | All'avvio | Avvia i servizi (es. `renet compose -- up -d`) | Il fallimento nella root è **critico** (ferma tutto). I fallimenti nelle sottodirectory sono **non critici** (registrati, continua) |
| `down()` | All'arresto | Ferma i servizi (es. `renet compose -- down`) | **Best-effort** -- i fallimenti vengono registrati ma tutti i Rediaccfile vengono sempre tentati |

Entrambe le funzioni sono opzionali. Se una funzione non è definita, viene ignorata silenziosamente.

### Ordine di esecuzione

- **Avvio (`up`):** Il Rediaccfile root per primo, poi le sottodirectory in **ordine alfabetico** (dalla A alla Z).
- **Arresto (`down`):** Le sottodirectory in **ordine alfabetico inverso** (dalla Z alla A), poi la root per ultima.

### Variabili d'ambiente

Quando una funzione Rediaccfile viene eseguita, sono disponibili le seguenti variabili d'ambiente:

| Variabile | Descrizione | Esempio |
|-----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Percorso di mount del repository | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID del repository | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID rete (intero) | `2816` |
| `DOCKER_HOST` | Socket Docker per il daemon isolato di questo repository | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP loopback per ogni servizio definito in `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Le variabili `{SERVICE}_IP` vengono generate automaticamente dai mapping degli slot in `.rediacc.json` ed esportate prima dell'esecuzione delle funzioni del Rediaccfile. La convenzione di denominazione converte il nome del servizio in maiuscolo con i trattini sostituiti da underscore, poi aggiunge `_IP`. Ad esempio, un servizio denominato `listmonk-app` con slot `0` diventa `LISTMONK_APP_IP=127.0.11.2`.

> **Attenzione: Non usare `sudo docker` nei Rediaccfile.** Il comando `sudo` reimposta le variabili d'ambiente, il che significa che `DOCKER_HOST` viene perso e i comandi Docker punteranno al daemon di sistema invece del daemon isolato del repository. Questo rompe l'isolamento dei container e può causare conflitti di porta. Rediacc bloccherà l'esecuzione se rileva `sudo docker` senza `-E`.
>
> Usa `renet compose` nei tuoi Rediaccfile: gestisce automaticamente `DOCKER_HOST`, inietta le etichette di networking per la scoperta delle route e configura il networking dei servizi. Consulta [Networking](/it/docs/networking) per i dettagli su come i servizi vengono esposti tramite il reverse proxy. Se chiami Docker direttamente, usa `docker` senza `sudo`; le funzioni Rediaccfile vengono già eseguite con privilegi sufficienti. Se devi usare sudo, usa `sudo -E docker` per preservare le variabili d'ambiente.
>
> `renet` è lo strumento remoto di basso livello. Per i normali workflow utente dalla tua workstation, preferisci i comandi `rdc` come `rdc repo up` e `rdc repo down`. Consulta [rdc vs renet](/it/docs/rdc-vs-renet).

### Esempio

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Importante:** Usa sempre `renet compose --` invece di `docker compose`. Il wrapper `renet compose` applica host networking, allocazione IP ed etichette di service discovery richieste da renet-proxy. Le capability di checkpoint/restore CRIU vengono aggiunte ai container con l'etichetta `rediacc.checkpoint=true`. L'uso diretto di `docker compose` viene rifiutato dalla validazione del Rediaccfile. Consulta [Networking](/it/docs/networking) per i dettagli.

### Layout multi-servizio

Per progetti con più gruppi di servizi indipendenti, usa le sottodirectory:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: configurazione condivisa
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Servizi database
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # Server API
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, ecc.
    └── docker-compose.yml
```

Ordine di esecuzione per `up`: root, poi `backend`, `database`, `monitoring` (A-Z).
Ordine di esecuzione per `down`: `monitoring`, `database`, `backend`, poi root (Z-A).

## Networking dei servizi (.rediacc.json)

Ogni repository ottiene una subnet /26 (64 IP) nell'intervallo loopback `127.x.x.x`. I servizi fanno bind su IP loopback univoci in modo da poter essere eseguiti sulle stesse porte senza conflitti.

### Il file .rediacc.json

Mappa i nomi dei servizi ai numeri di **slot**. Ogni slot corrisponde a un indirizzo IP univoco all'interno della subnet del repository.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Generazione automatica da Docker Compose

Non è necessario creare `.rediacc.json` manualmente. Quando esegui `rdc repo up`, Rediacc automaticamente:

1. Scansiona tutte le directory contenenti un Rediaccfile alla ricerca di file compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` o `compose.yaml`)
2. Estrae i nomi dei servizi dalla sezione `services:`
3. Assegna il successivo slot disponibile ai nuovi servizi
4. Salva il risultato in `{repository}/.rediacc.json`

### Calcolo dell'IP

L'IP per un servizio viene calcolato dall'ID rete del repository e dallo slot del servizio. L'ID rete viene distribuito nel secondo, terzo e quarto ottetto di un indirizzo loopback `127.x.y.z`. I servizi iniziano dall'offset 2:

| Offset | Indirizzo | Scopo |
|--------|-----------|-------|
| .0 | `127.0.11.0` | Indirizzo di rete (riservato) |
| .1 | `127.0.11.1` | Gateway (riservato) |
| .2 - .62 | `127.0.11.2` - `127.0.11.62` | Servizi (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (riservato) |

**Esempio** per ID rete `2816` (`0x0B00`), indirizzo base `127.0.11.0`:

| Servizio | Slot | Indirizzo IP |
|----------|------|--------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Ogni repository supporta fino a **61 servizi** (slot da 0 a 60).

### Uso degli IP dei servizi in Docker Compose

Poiché ogni repository esegue un daemon Docker isolato, `renet compose` configura automaticamente `network_mode: host` per tutti i servizi. Il kernel riscrive in modo trasparente le chiamate `bind()` all'IP loopback assegnato al servizio, in modo che i servizi possano fare bind su `0.0.0.0` o `localhost` senza conflitti. Per le connessioni **verso altri servizi**, usa il **nome del servizio** - renet inietta ogni nome di servizio come hostname che risolve sempre all'IP corretto, anche nei fork:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # Nessun listen_addresses esplicito necessario - il kernel riscrive il bind all'IP loopback corretto

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # usa il nome del servizio
      LISTEN_ADDR: 0.0.0.0:8080                                      # il kernel riscrive all'IP del servizio
```

> **Nomi dei servizi per le connessioni:** Usa il **nome del servizio** (es. `postgres`, `redis`) per **connetterti** ad altri servizi - renet mappa automaticamente ogni nome di servizio al suo IP loopback tramite `/etc/hosts`. Incorporare `${POSTGRES_IP}` nelle stringhe di connessione memorizzate nei database o nei file di configurazione codificherà l'IP grezzo, il che rompe l'isolamento del fork ed è un **errore di validazione**. Le variabili `${SERVICE_IP}` sono ancora disponibili per l'uso esplicito, ma il binding viene gestito automaticamente dal kernel.

> **Nota:** Non aggiungere `network_mode: host` manualmente; `renet compose` lo inietta automaticamente. Le policy di restart (es. `restart: always`) sono sicure da usare; renet le rimuove automaticamente per compatibilità con CRIU e il watchdog del router gestisce il ripristino dei container.

### Ripristino dei container e policy di restart

renet e Docker non sono d'accordo, intenzionalmente, su come gestire i restart dei container. Capire la divisione è importante per capire perché un container è tornato attivo o no.

**Traduzione della policy di restart.** Quando scrivi `restart: always` (o `unless-stopped`, o `on-failure`) nel tuo file compose, renet la **rimuove** durante la sintesi del deployment compose effettivo e la sostituisce con `restart: no`. Il valore originale viene salvato nel `.rediacc.json` del repository sotto `services.<name>.restart_policy`. Questo impedisce al restart automatico a livello di daemon di Docker di interferire con il checkpoint/restore CRIU (un restart guidato dal daemon riprenderebbe da uno stato pre-checkpoint obsoleto).

**Applicazione del watchdog.** Il watchdog del router viene eseguito periodicamente su ogni macchina. Ad ogni ciclo:

1. Legge `.rediacc.json` per ogni repository e trova i servizi con una `restart_policy` recuperabile.
2. Elenca tutti i container per il daemon di quel repository, identifica quelli fermi e li riavvia secondo la policy salvata. Un periodo di grazia di 30 secondi impedisce conflitti con un operatore che ha appena eseguito `docker stop`.
3. Lo stesso ciclo elabora anche `/var/run/rediacc/cold-backup-<guid>.running.json` (vedi [Semantica del Cold Backup](backup-restore.md#cold-backup-semantics)). I container elencati vengono riavviati indipendentemente dalla policy salvata, perché il sidecar significa "renet li ha fermati intenzionalmente e deve un restart all'operatore."

**Perché `on-failure` può sembrare non funzionare.** La policy `on-failure` di Docker riavvia solo quando il container esce con un codice non zero. Un arresto ordinato (exit 0) da `docker stop` o da uno shutdown del daemon non è un "fallimento" e NON attiva un restart, né dalla logica nativa di Docker né dal percorso della policy salvata del watchdog. Il sidecar cold-backup è la rete di sicurezza: qualsiasi container fermato intenzionalmente viene riavviato indipendentemente dalla sua policy.

**Come interpretare lo stato di runtime:**

- `docker inspect <container>` → `RestartPolicy.Name`: sarà sempre `no` per i container gestiti da renet. Non fare affidamento su questo per la policy semantica.
- `.rediacc.json` nella root di mount del repository → `services.<name>.restart_policy`: l'intenzione reale.
- `docker ps --format '{{.Status}}'`: stato di runtime.

**Come correggere una deriva.** Se la policy salvata in `.rediacc.json` di un container è errata (ad esempio, perché hai modificato compose ma non hai mai ricreato il container), riesegui `rdc repo up --name <repo> -m <machine>`. Il container viene ricreato con la policy aggiornata registrata.

> **Sperimentale:** Il ripristino basato sul sidecar cold-backup e il flag `--sync-certs` su `rdc machine query` sono stati introdotti in renet 0.9+. Le versioni precedenti si affidano esclusivamente alla `restart_policy` salvata per il ripristino del watchdog, il che può lasciare i container `on-failure` bloccati dopo un cold backup.

> **Il bridge networking Docker è disabilitato per i daemon gestiti da rediacc.** Ogni daemon per singolo repository è configurato con `"bridge": "none"` e `"iptables": false`. Un semplice `docker run <image>` all'interno di una shell di repository si avvierà comunque, ma il container ottiene solo un'interfaccia loopback e non ha DNS né connettività in uscita. Questo è by design, poiché l'isolamento loopback tra repository è applicato dagli hook cgroup eBPF che un container in bridge aggirerebbe. I servizi di produzione dovrebbero usare `renet compose` (che inietta host networking automaticamente); per il debug ad hoc, passa `--network host` esplicitamente: `docker run --rm --network host -it ubuntu bash`.

> **Nota:** I repository fork ottengono route automatiche nel sottodominio del genitore: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. I domini personalizzati vengono ignorati per i fork.

## Avvio dei servizi

Monta il repository e avvia tutti i servizi:

```bash
rdc repo up --name my-app -m server-1
```

| Opzione | Descrizione |
|---------|-------------|
| `--skip-router-restart` | Salta il riavvio del server delle route dopo l'operazione |

La sequenza di esecuzione è:
1. Monta il repository cifrato con LUKS (auto-monta se non montato)
2. Avvia il daemon Docker isolato
3. Genera automaticamente `.rediacc.json` dai file compose
4. Esegue `up()` in tutti i Rediaccfile (ordine A-Z)

Dopo il deployment, l'output mostra una sezione **PROXY ROUTES** con gli URL effettivi per ogni servizio. I servizi con etichette Traefik personalizzate (es. `traefik.http.routers.myapp.rule=Host(...)`) mostrano i loro domini personalizzati come URL primari:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

I servizi senza etichette Traefik personalizzate mostrano solo la route generata automaticamente. Usa questi URL (non il pattern generico stampato dalla CLI) per l'accesso tramite browser, le chiamate API e la configurazione cross-servizio.

## Arresto dei servizi

```bash
rdc repo down --name my-app -m server-1
```

| Opzione | Descrizione |
|---------|-------------|
| `--unmount` | Smonta il repository cifrato dopo l'arresto. Se non ha effetto, usa `rdc repo unmount` separatamente. |
| `--skip-router-restart` | Salta il riavvio del server delle route dopo l'operazione |

La sequenza di esecuzione è:
1. Esegue `down()` in tutti i Rediaccfile (ordine inverso Z-A, best-effort)
2. Ferma il daemon Docker isolato (se `--unmount`)
3. Smonta e chiude il volume cifrato LUKS (se `--unmount`)

## Operazioni in blocco

Avvia o ferma tutti i repository su una macchina in una volta sola:

```bash
rdc repo up -m server-1
```

| Opzione | Descrizione |
|---------|-------------|
| `--include-forks` | Include i repository forkati |
| `--mount-only` | Monta soltanto, senza avviare i container |
| `--dry-run` | Mostra cosa verrebbe fatto |
| `--parallel` | Esegue le operazioni in parallelo |
| `--concurrency <n>` | Numero massimo di operazioni concorrenti (predefinito: 3) |
| `--skip-router-restart` | Salta il riavvio del server delle route dopo l'operazione |

## Autostart all'avvio

Per impostazione predefinita, i repository devono essere montati e avviati manualmente dopo un riavvio del server. **Autostart** configura i repository affinché vengano montati automaticamente, avviino Docker ed eseguano `up()` del Rediaccfile all'avvio del server.

### Come funziona

Quando abiliti l'autostart per un repository:

1. Viene generato un keyfile LUKS casuale da 256 byte e aggiunto allo slot 1 LUKS del repository (lo slot 0 rimane la passphrase dell'utente)
2. Il keyfile viene memorizzato in `{datastore}/.credentials/keys/{guid}.key` con permessi `0600` (solo root)
3. Un servizio systemd (`rediacc-autostart`) viene eseguito all'avvio per montare tutti i repository abilitati e avviare i loro servizi

All'arresto, il servizio ferma ordinatamente tutti i servizi (Rediaccfile `down()`), ferma i daemon Docker e chiude i volumi LUKS.

> **Nota di sicurezza:** L'abilitazione dell'autostart memorizza un keyfile LUKS sul disco del server. Chiunque abbia accesso root al server può montare il repository senza la passphrase. Valuta questo in base al tuo modello di minaccia.

### Abilitazione

```bash
rdc repo autostart enable --name my-app -m server-1
```

Ti verrà chiesta la passphrase del repository.

### Abilitazione di tutti

```bash
rdc repo autostart enable -m server-1
```

### Disabilitazione

```bash
rdc repo autostart disable --name my-app -m server-1
```

Questo rimuove il keyfile e disattiva lo slot 1 LUKS.

### Aggiornamento del keyfile al deploy

Quando l'autostart è abilitato, `rdc repo up` valida il keyfile dello slot 1 LUKS.
Se il keyfile su disco corrisponde ancora allo slot LUKS, non vengono apportate modifiche.

Dopo aver trasferito un repository tra macchine tramite `repo push` / `repo pull`,
il keyfile sulla nuova macchina non corrisponderà. In questo caso, `repo up` rigenera
automaticamente il keyfile e aggiorna lo slot 1 LUKS. Vedrai messaggi di log:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

È sicuro: lo slot 0 (la tua passphrase) non viene mai modificato. Se l'autostart non è
abilitato, la verifica viene ignorata silenziosamente. I fallimenti non sono fatali e non bloccano
il deploy.

### Elenco dello stato

```bash
rdc repo autostart list -m server-1
```

## Esempio completo

Questo distribuisce un'applicazione web con PostgreSQL, Redis e un server API.

### 1. Configurazione

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Montaggio e preparazione

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Creazione dei file dell'applicazione

All'interno del repository, crea:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Avvio

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Abilitazione dell'autostart

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Uso dei segreti per singolo repository in compose

Il segnaposto `POSTGRES_PASSWORD: changeme` qui sopra va bene per un tutorial, ma le app reali richiedono credenziali reali, e farne commit nel file compose (o in un file `.env` all'interno del repository) significa che un fork li eredita. Per le credenziali al momento del deploy, usa `rdc repo secret`. I valori risiedono al di fuori dell'immagine cifrata del repository, quindi i fork partono con una mappa dei segreti vuota.

Due modalità di consegna funzionano in compose:

**Modalità `env`**. Interpola tramite `${REDIACC_SECRET_<KEY>}` in qualsiasi valore `environment:`. Il wrapper renet passa il valore nell'ambiente del container al momento del deploy.

**Modalità `file`**. Il valore arriva in un file tmpfs lato host su `/var/run/rediacc/secrets/<networkID>/<KEY>`, e lo monti nel container tramite il blocco `secrets:` standard di Docker compose. Il container legge `/run/secrets/<key>`. Preferisci questa modalità per qualsiasi dato sensibile. I valori non compaiono mai in `docker inspect` o `/proc/<pid>/environ`.

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Inizializza i valori con `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` e l'equivalente in modalità file. Consulta [Repository § Segreti](/it/docs/repositories#secrets) per la guida completa e [Segreti per singolo repository](/it/docs/rdc-cheat-sheet#per-repo-secrets) sul cheat sheet per il riferimento ai comandi.

> **I percorsi cross-repo vengono rifiutati al momento della validazione.** Un `secrets: file:` compose (o `configs: file:`, o `env_file:`) che punta alla directory `/var/run/rediacc/secrets/<other-networkID>/` di un altro repository viene rifiutato definitivamente dal wrapper renet prima che docker compose venga eseguito. `--unsafe` NON sovrascrive. Difesa in profondità: la sandbox Landlock attorno alla shell Rediaccfile limita le letture alla directory dei segreti della rete corrente, quindi un `cat /var/run/rediacc/secrets/<other>/X` dalla shell bash del Rediaccfile fallisce con EACCES anche se aggira il validatore YAML. Non è necessario attivarlo; è abilitato per impostazione predefinita per ogni `repo up`.
