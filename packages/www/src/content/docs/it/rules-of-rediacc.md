---
title: "Regole di Rediacc"
description: "Regole e convenzioni essenziali per creare applicazioni sulla piattaforma Rediacc. Tratta Rediaccfile, compose, networking, storage, CRIU e deployment. È necessario conoscerle per ottenere la massima qualità."
category: "Guides"
order: 5
language: it
sourceHash: "1d227a06272a0050"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Regole di Rediacc

Ogni repository Rediacc viene eseguito in un ambiente isolato con il proprio daemon Docker, volume LUKS cifrato e intervallo IP dedicato. Queste regole garantiscono il corretto funzionamento dell'applicazione all'interno di questa architettura.

## Rediaccfile

- **Ogni repository necessita di un Rediaccfile**, uno script bash con funzioni di ciclo di vita.
- **Funzioni del ciclo di vita**: `up()`, `down()`. Opzionale: `info()`.
- `up()` avvia i tuoi servizi. `down()` li ferma.
- `info()` fornisce informazioni di stato (stato dei container, log recenti, health).
- Il Rediaccfile viene sourced da renet; ha accesso alle variabili di shell, non solo alle variabili d'ambiente.

### Variabili d'ambiente disponibili nel Rediaccfile

| Variabile | Esempio | Descrizione |
|-----------|---------|-------------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Percorso root del repository montato |
| `REDIACC_NETWORK_ID` | `6336` | Identificatore di isolamento della rete |
| `REDIACC_REPOSITORY` | `abc123-...` | GUID del repository |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | IP loopback per servizio (nome servizio in maiuscolo) |

### Rediaccfile minimale

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

- **Usa `renet compose`, mai `docker compose`**: renet inietta l'isolamento della rete, host networking, IP loopback ed etichette di servizio.
- **Non impostare `network_mode`** nel tuo file compose: renet forza `network_mode: host` su tutti i servizi. Qualsiasi valore impostato viene sovrascritto.
- **Non impostare etichette `rediacc.*`**: renet inietta automaticamente `rediacc.network_id`, `rediacc.service_ip` e `rediacc.service_name`.
- **I mapping `ports:` vengono ignorati** in modalità host networking. Aggiungi l'etichetta `rediacc.service_port` per il routing HTTP (i servizi senza questa etichetta non ottengono route HTTP). Usa le etichette `rediacc.tcp_ports`/`rediacc.udp_ports` per il forwarding TCP/UDP.
- **Le policy di restart (`restart: always`, `on-failure`, ecc.) sono sicure da usare**: renet le rimuove automaticamente per compatibilità con CRIU. Il watchdog del router ripristina automaticamente i container fermi in base alla policy originale salvata in `.rediacc.json`.
- **Le impostazioni pericolose sono bloccate per impostazione predefinita**: `privileged: true`, `pid: host`, `ipc: host` e i bind mount dell'host verso percorsi di sistema vengono rifiutati. Usa `renet compose --unsafe` per sovrascrivere a tuo rischio.

### Variabili d'ambiente all'interno dei container

Renet inietta automaticamente queste in ogni container:

| Variabile | Descrizione |
|-----------|-------------|
| `SERVICE_IP` | L'IP loopback dedicato di questo container |
| `REDIACC_NETWORK_ID` | ID di isolamento della rete |

### Denominazione e routing dei servizi

- Il **nome del servizio** compose diventa il prefisso URL della route automatica.
- **Repository grand**: `https://{service}.{repo}.{machine}.{baseDomain}` (es. `https://myapp.marketing.server-1.example.com`).
- **Repository fork**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (es. `https://myapp-fork-staging.marketing.server-1.example.com`). Il separatore `-fork-` previene collisioni URL con i nomi dei servizi del repository grand. L'URL del fork usa sempre il certificato wildcard esistente del repository genitore, quindi non è necessario un nuovo certificato.
- Per i domini personalizzati, usa le etichette Traefik (nota: i domini personalizzati NON sono compatibili con i fork, il dominio appartiene al repository grand).

## Networking

- **Ogni repository ottiene il proprio daemon Docker** su `/var/run/rediacc/docker-<networkId>.sock`.
- **Ogni servizio ottiene un IP loopback univoco** all'interno di una subnet /26 (es. `127.0.24.192/26`).
- **Il binding è automatico**: I servizi possono fare bind su `0.0.0.0` o `localhost` - il kernel riscrive in modo trasparente l'indirizzo all'IP loopback assegnato al servizio. Il binding esplicito con `${SERVICE_IP}` funziona ancora ma non è più necessario.
- **Gli health check possono usare `localhost`** o `${SERVICE_IP}`. Esempio: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Le connessioni cross-repo sono bloccate dal kernel**: Il kernel blocca automaticamente le connessioni agli IP loopback al di fuori della subnet `/26` del repository. Un servizio in un repository non può raggiungere servizi in un altro repository.
- **Comunicazione inter-servizio**: Usa i **nomi dei servizi** (es. `db`, `redis`) - renet inietta automaticamente ogni nome di servizio come hostname che risolve all'IP corretto. I nomi DNS Docker NON funzionano in modalità host, ma i nomi dei servizi tramite `/etc/hosts` sì. Evita di incorporare `${DB_IP}` o simili in file di configurazione persistenti (es. stringhe di connessione memorizzate in un database) - in caso di fork, l'IP grezzo viene ereditato e punta al repository sbagliato. I nomi dei servizi risolvono sempre correttamente per ogni repository.
- **I conflitti di porta sono impossibili** tra repository, ognuno ha il proprio daemon Docker e intervallo IP.
- **Forwarding TCP/UDP**: Aggiungi etichette per esporre porte non HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Storage

- **Tutti i dati Docker sono memorizzati all'interno del repository cifrato**: il `data-root` di Docker si trova in `{mount}/.rediacc/docker/data` all'interno del volume LUKS. I volumi denominati, le immagini e i layer dei container sono tutti cifrati, inclusi nei backup e nel fork automaticamente.
- **I bind mount su `${REDIACC_WORKING_DIR}/...` sono consigliati** per chiarezza, ma i volumi denominati funzionano anch'essi in modo sicuro.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (consigliato)
    - pgdata:/var/lib/postgresql/data      # volume denominato (anch'esso sicuro)
  ```
- Il volume LUKS è montato su `/mnt/rediacc/mounts/<guid>/`.
- Gli snapshot BTRFS catturano l'intero file di backing LUKS, inclusi tutti i dati montati tramite bind.
- Il datastore è un file pool BTRFS a dimensione fissa sul disco di sistema. Usa `rdc machine query --name <name> --system` per vedere lo spazio libero effettivo. Espandi con `rdc datastore resize`.

## CRIU (Live Migration)

- **Opt-in tramite etichetta**: Aggiungi `rediacc.checkpoint=true` ai container di cui vuoi fare checkpoint. I container senza di essa (database, cache) si avviano da zero e si ripristinano tramite i propri meccanismi (WAL, LDF, AOF).
- **`repo down --checkpoint`** salva lo stato del processo prima di fermarsi; il successivo `repo up` ripristina automaticamente. **Questo è il flusso principale sulla stessa macchina**, verificato funzionante.
- **`backup push --checkpoint`** cattura la memoria del processo in esecuzione e lo stato del disco per i container etichettati, poi trasferisce il volume su un'altra macchina. Ripristina sulla macchina di destinazione tramite `repo up`.
- **`repo fork --checkpoint`** cattura lo stato del processo prima del fork e clona il checkpoint con il fork tramite CoW. ⚠️ Sulla stessa macchina, il successivo `repo up` sul fork **attualmente fallisce** con `criu failed: type RESTORE errno 0` quando il genitore è ancora in esecuzione. Bug CRIU upstream [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Usa `repo down --checkpoint` per il salvataggio/ripristino in-place, o `backup push --checkpoint` per la migrazione cross-machine.
- **`repo up`** rileva automaticamente i dati di checkpoint e li ripristina se trovati. Usa `--skip-checkpoint` per forzare un avvio da zero.
- **Ripristino consapevole delle dipendenze**: Usa `depends_on` di compose per avviare prima i database (attendere che siano healthy), poi ripristinare i container dell'app tramite CRIU.
- **Le connessioni TCP diventano obsolete dopo il ripristino**; le app devono gestire `ECONNRESET` e riconnettersi. CRIU non preserva lo stato attivo delle connessioni TCP attraverso il ripristino in nessun flusso supportato.
- **La modalità sperimentale di Docker** è abilitata automaticamente sui daemon per singolo repository.
- **CRIU viene installato** durante `rdc config machine setup`.
- **`/etc/criu/runc.conf`** è configurato con `tcp-established` per impostazione predefinita.
- **Le impostazioni di sicurezza del container vengono iniettate automaticamente per i container etichettati**: `renet compose` aggiunge quanto segue ai container con `rediacc.checkpoint=true`:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (set minimale per CRIU su kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (il supporto AppArmor di CRIU non è ancora stabile upstream)
  - `userns_mode: host` (CRIU richiede accesso al namespace init per `/proc/pid/map_files`)
- I container senza l'etichetta vengono eseguiti con una postura di sicurezza più pulita (nessuna capability aggiuntiva).
- Il profilo seccomp predefinito di Docker viene preservato; CRIU usa `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) per sospendere temporaneamente i filtri durante checkpoint/restore.
- **Non impostare manualmente le capability CRIU** nel tuo file compose; renet le gestisce in base all'etichetta.
- Consulta il [template heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) per un'implementazione di riferimento compatibile con CRIU.

### Pattern di applicazione compatibili con CRIU

- Gestisci `ECONNRESET` su tutte le connessioni persistenti (pool di database, websocket, code messaggi).
- Usa librerie di pool di connessioni che supportano la riconnessione automatica.
- Aggiungi `process.on("uncaughtException")` come rete di sicurezza per gli errori di socket obsoleti dagli oggetti interni delle librerie.
- Le policy di restart sono gestite automaticamente da renet (rimosse per CRIU, il watchdog gestisce il ripristino).
- Evita di fare affidamento sul DNS Docker; usa gli IP loopback per la comunicazione inter-servizio.

### Policy di sicurezza dell'host per OS

Su tutti e cinque gli OS server ufficialmente supportati (vedi [Requisiti](/it/docs/requirements)), il daemon docker per singolo repository e i container che esegue usano **etichette container predefinite**. `rdc config machine setup` non installa una policy SELinux personalizzata né un profilo AppArmor.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor è abilitato per impostazione predefinita. I container vengono eseguiti con il profilo docker-container predefinito. L'unica eccezione è CRIU (`apparmor=unconfined` per i container con `rediacc.checkpoint=true`, come indicato sopra).
- **Fedora 43 / Oracle Linux 10**: SELinux è in modalità enforcing per impostazione predefinita. I container ottengono il contesto standard `container_t`. Non è necessaria l'installazione di policy aggiuntive. Se un passaggio di configurazione fallisce con denial AVC, consulta [Risoluzione dei problemi → Denial SELinux](/it/docs/troubleshooting).
- **Debian 13**: AppArmor è disponibile ma non applicato per impostazione predefinita su tutti i domini. I container usano comunque il profilo docker-container.

Non è richiesto alcun flag di postura di sicurezza per OS; `rdc` e `renet` rilevano l'ambiente in esecuzione e producono lo stesso isolamento per singolo repository su tutte le cinque distribuzioni.

## Sicurezza

- **La cifratura LUKS** è obbligatoria per i repository standard. Ogni repository ha la propria chiave di cifratura.
- **Le credenziali sono memorizzate nella config della CLI** (`~/.config/rediacc/rediacc.json`). Perdere la config significa perdere l'accesso ai volumi cifrati.
- **Non fare mai commit delle credenziali** nel version control. Usa `env_file` e genera i segreti in `up()`.
- **Isolamento dei repository**: Il daemon Docker, la rete e lo storage di ogni repository sono completamente isolati dagli altri repository sulla stessa macchina.
- **Isolamento degli agenti**: Gli agenti AI operano in modalità fork-only per impostazione predefinita. Ogni repository ha la propria chiave SSH con enforcement sandbox lato server (`sandbox-gateway` ForceCommand). Tutte le connessioni sono sandboxate con Landlock LSM, OverlayFS home overlay e TMPDIR per singolo repository. L'accesso al filesystem cross-repo è bloccato dal kernel.
- **`sudo` è disabilitato all'interno di una sandbox di repository per progetto.** L'isolamento filesystem Landlock richiede `NoNewPrivs`, che impedisce qualsiasi elevazione dei privilegi, quindi `sudo` fallirà con `no new privileges flag is set`. L'utente proprietario del repository ha già i permessi necessari per tutto ciò che si trova nel mount del repository e nel socket Docker. Per operazioni veramente privilegiate (installazione di pacchetti host, tuning del kernel), eseguile fuori dalla sandbox o da una funzione `up()` del Rediaccfile eseguita dal percorso dell'infrastruttura.
- **Il bridge networking Docker è disabilitato sui daemon per singolo repository.** Il `daemon.json` (`FlavorRediacc`) di ogni repository contiene `"bridge": "none"` e `"iptables": false`, quindi un semplice `docker run <image>` crea un container con solo un'interfaccia loopback e nessuna connettività in uscita. Questo non è un bug, è come viene applicato l'isolamento cross-repo: gli hook eBPF a livello kernel che bloccano un repository dall'accesso agli IP loopback di un altro repository si applicano solo ai container che risiedono nel namespace di rete dell'host. Per i servizi di produzione usa `renet compose`, che inietta `network_mode: host` automaticamente. Per i container one-off ad hoc in una shell, passa `--network host` esplicitamente. (I daemon Hub per utente (`FlavorHub`, ambienti di sviluppo) sono l'eccezione: abilitano `bridge="docker0"` e `iptables=true` in modo che i container avviati dall'utente abbiano normale connettività in uscita.)

## Deployment

- **`rdc repo up`** monta automaticamente il volume LUKS se non montato, poi esegue `up()` in tutti i Rediaccfile.
- **`rdc repo down`** esegue `down()` e ferma il daemon Docker.
- **`rdc repo down --unmount`** chiude anche il volume LUKS (blocca lo storage cifrato).
- **I fork** (`rdc repo fork`) creano un clone CoW (copy-on-write) con un nuovo GUID e networkId, in **tempo costante indipendentemente dalle dimensioni del repository**. BTRFS reflink duplica i metadati dell'immagine, non i dati, quindi un repository da 100 GB effettua il fork negli stessi pochi secondi di uno da 1 GB. Il fork condivide la chiave di cifratura del genitore.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) sostituisce i dati del repository grand con quelli del fork. Il grand mantiene la propria identità (GUID, networkId, domini, autostart, catena di backup). I vecchi dati di produzione vengono preservati come fork di backup. Usa per: testa l'aggiornamento sul fork, verifica, poi esegui takeover in produzione. Ripristina con `rdc repo takeover --name <backup-fork> -m <machine>`.
- **Le route proxy** diventano attive circa 3 secondi dopo il deployment. L'avviso "Proxy is not running" durante `repo up` è informativo negli ambienti ops/dev.
- **`rdc repo up` e `rdc repo fork --up` stampano il pattern URL** per i servizi etichettati con `rediacc.service_port` al termine del deployment. Sostituisci `{service}` con il nome del servizio esposto per ottenere l'URL esatto. I servizi senza `rediacc.service_port` (database, worker) non ottengono route e non vengono mostrati.

## Errori comuni

- Usare `docker compose` invece di `renet compose`: i container non otterranno l'isolamento di rete.
- Le policy di restart sono sicure; renet le rimuove automaticamente e il watchdog gestisce il ripristino.
- Usare `privileged: true`: non necessario, renet inietta le capability CRIU specifiche al suo posto.
- Inserire IP grezzi in file di configurazione persistenti - usa i nomi dei servizi per le connessioni per mantenere l'isolamento del fork.
- Usare `rdc term connect -c` come workaround per comandi falliti: segnala invece i bug.
- `repo delete` esegue una pulizia completa inclusi IP loopback e unità systemd. Esegui `rdc machine prune --name <name>` per ripulire i residui di eliminazioni legacy.
