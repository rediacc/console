---
title: Limiti e Quote
description: >-
  Riferimento per i limiti, i massimi e le quote applicabili a repository,
  servizi, rete e archiviazione di Rediacc.
category: Reference
order: 99
language: it
sourceHash: "ece2d423d416e7ec"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# Limiti e Quote

Limiti di deployment di Rediacc. Tre sono rigidi e non possono essere modificati aggiungendo hardware: il limite di 61 servizi per repository (allocazione dello spazio di indirizzi di rete), il kernel 6.1 minimo (requisiti CRIU) e il limite di rilascio di Let's Encrypt di 50 certificati wildcard per dominio registrato per settimana. Tutto il resto è flessibile: si sposta quando aggiungi hardware. Conosci la differenza prima di impegnarti in una topologia.

---

## Servizi per Repository

Ogni repository supporta fino a **61 servizi** in esecuzione contemporaneamente.

Questo è un limite rigido determinato dallo spazio degli indirizzi di rete allocato a ogni repository. Ogni servizio ottiene il proprio indirizzo IP privato dedicato, e il blocco di indirizzi di ogni repository accoglie esattamente 61 slot di servizio.

Consideralo così: quando raggiungi 61 servizi in un repository, di solito indica un problema architetturale, non un vincolo di Rediacc. La soluzione è spostare i sidecar e gli agenti di monitoraggio nel loro repository con un confine di isolamento separato, oppure ridurre il numero di processi in esecuzione indipendente all'interno dell'applicazione stessa.

---

## Repository per Macchina

Non esiste un limite rigido imposto da Rediacc. Il limite pratico dipende dalle risorse della tua macchina:

| Risorsa | Impatto |
|----------|--------|
| Spazio su disco | Ogni repository è un'immagine disco cifrata. Una macchina con 1 TB di archiviazione utilizzabile può contenere molti repository, ma la dimensione totale di tutte le immagini deve rientrare nel pool del datastore. |
| RAM | Ogni repository in esecuzione avvia il proprio daemon Docker e i container. L'utilizzo della memoria dipende dai tuoi carichi di lavoro. |
| CPU | Le operazioni parallele sui repository (avvio, backup, fork) aggiungono un carico CPU temporaneo. |

**I deployment tipici** eseguono da 10 a 50 repository per macchina senza problemi. Le macchine con 32 GB+ di RAM e 500 GB+ di archiviazione eseguono regolarmente 100+ repository.

### Limite di ID di rete a livello di sistema

A ogni repository viene assegnato un **ID di rete** univoco, un numero usato per calcolare il suo intervallo di indirizzi IP privati. Questo pool è condiviso tra tutte le macchine e i repository gestiti dalla stessa configurazione di Rediacc.

| Limite | Valore |
|-------|-------|
| ID di rete totali disponibili | ~261.944 |
| Ambito | Per configurazione (condiviso tra tutte le macchine in una configurazione) |

Quando un repository viene eliminato, il suo ID di rete viene liberato e diventa disponibile per il riutilizzo. Rediacc alloca gli ID in modo sequenziale e cerca gli spazi liberi solo quando il contatore forward si avvicina al limite. In pratica questo limite non viene mai raggiunto. Non lo abbiamo mai visto accadere. L'esaurimento del pool richiederebbe la creazione e il tracciamento di centinaia di migliaia di repository nel corso della vita di una singola configurazione.

---

## Fork

Non esiste un limite al numero di fork attivi di un repository. Ogni fork è un clone copy-on-write completo con la propria archiviazione cifrata, indirizzi di rete e daemon Docker. I fork consumano spazio su disco proporzionale ai dati scritti dopo la creazione (non alle dimensioni complete del genitore).

---

## Porte Esterne

### Porte sempre attive

Le porte vengono aperte solo dopo aver configurato un IP pubblico con `rdc config infra set --public-ipv4`. Fino ad allora, nessuna porta è aperta sulla macchina. Una volta configurate:

| Porta | Protocollo | Scopo |
|------|----------|---------|
| 80 | TCP | HTTP: gestito da Traefik; restituisce 404 per i domini non configurati, non viene passato ad alcun servizio |
| 443 | TCP | HTTPS: come sopra; le richieste senza una route corrispondente vengono rifiutate al livello del proxy |
| 10000–10010 | TCP | Intervallo dinamico per il forwarding TCP gestito da Rediacc |

HTTP/HTTPS differiscono dalle porte TCP raw: anche se le porte 80 e 443 sono aperte, ogni richiesta viene validata dal reverse proxy rispetto a una tabella di routing esplicita. Senza un servizio configurato e un dominio corrispondente, nessun codice applicativo viene raggiunto e nessun dato viene esposto.

### Forwarding TCP/UDP su richiesta

Tutte le altre porte (database, cache, message broker, DNS, posta) sono **chiuse per impostazione predefinita** e devono essere aperte esplicitamente. Questo mantiene minima la superficie di attacco della macchina.

Per esporre una porta da un servizio specifico:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Per aprire una porta a livello di macchina (disponibile a tutti i servizi):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Non esporre mai le porte di database o cache esternamente a meno che tu non abbia un requisito specifico. Usa le auto-route HTTPS per i servizi web e mantieni i servizi di archiviazione interni.

---

## Datastore

Il datastore è un pool di dimensioni fisse creato quando una macchina viene configurata per la prima volta. La sua dimensione non cresce automaticamente.

- **Dimensione minima consigliata**: 50 GB
- **Dimensione massima**: limitata dal tuo disco. Un singolo pool può occupare un disco intero.
- **Ridimensionamento**: usa `rdc datastore resize` per modificare la dimensione del pool (tutti i repository devono essere smontati prima).
- **File system**: Rediacc usa BTRFS internamente per snapshot copy-on-write e forking efficiente. Richiede una macchina con **Linux kernel 6.1 o successivo** per la piena stabilità in produzione.

Ogni repository ha una dimensione massima impostata al momento della creazione (predefinita: 10 GB). Usa `rdc repo resize` per modificarla manualmente, oppure imposta una [policy di dimensione automatica](/it/docs/repositories#policy-di-dimensione-automatica) affinché la macchina la faccia crescere online quando si riempie (limitata da un tetto esplicito per-repository e da una riserva di spazio libero nel pool). L'auto-grow si applica solo ai singoli repository; il pool stesso non cresce mai automaticamente.

Le immagini di repository sono sparse: un repository occupa nel pool solo quanto ha effettivamente scritto, e lo spazio liberato dalle eliminazioni torna al pool tramite [`repo trim`](/it/docs/repositories#recupera-spazio-trim) o un auto-trim pianificato. Le quote possono quindi sommarsi a più della dimensione del pool, con il [report sulla salute dello storage](/it/docs/monitoring#salute-dellarchiviazione) che mostra il livello di riempimento reale.

---

## Route HTTP

Ogni servizio con l'etichetta `rediacc.service_port` ottiene automaticamente una route HTTPS. Non esiste un limite al numero di servizi con route, soggetto al massimo di 61 servizi per repository.

I certificati TLS wildcard vengono provisioning per repository al primo deployment tramite Let's Encrypt (sfida DNS-01 Cloudflare). Let's Encrypt limita il rilascio a **50 certificati per dominio registrato per settimana**. Poiché Rediacc usa un certificato wildcard per repository (non per servizio), un deployment che crea 50+ nuovi repository in una singola settimana raggiungerà questo limite.

I fork riutilizzano il certificato wildcard esistente del repository genitore e non consumano alcuna quota di certificati.

---

## Checkpoint / Restore (CRIU)

La migrazione live tramite CRIU ha i seguenti vincoli:

- **Su richiesta**: solo i container con l'etichetta `rediacc.checkpoint=true` vengono sottoposti a checkpoint. I database e i servizi senza stato sono esclusi per impostazione predefinita e si avviano di nuovo al restore.
- **Requisito del kernel**: Linux 6.1+ sia sulla macchina sorgente che su quella di destinazione.
- **Modalità di rete**: CRIU richiede la modalità di rete host. I container che utilizzano configurazioni di rete personalizzate non possono essere sottoposti a checkpoint.
- **Memoria**: la dimensione dei dati del checkpoint è uguale alla memoria residente del processo sottoposto a checkpoint. Set di dati in memoria di grandi dimensioni (ad esempio, un'app Node.js che memorizza nella cache 4 GB di dati) producono file di checkpoint da 4 GB.
- **Connessioni TCP**: le applicazioni devono tollerare la perdita di connessione al restore. Le connessioni TCP attive **non** vengono preservate. Il processo ripristinato vede i socket come chiusi e deve riconnettersi. Questo si applica sia ai percorsi di restore sulla stessa macchina che tra macchine diverse.
- **Il fork live sulla stessa macchina reindirizza gli indirizzi del padre**: `rdc repo fork --parent X --tag Y --checkpoint` seguito da `rdc repo up` funziona mentre il repository padre continua a girare. I processi ripristinati portano gli indirizzi loopback del padre al momento del checkpoint, quindi il sistema li reindirizza in modo trasparente verso gli indirizzi propri del fork (stesso servizio, copia dei dati del fork). Il primo uso di una connessione TCP ripristinata fallisce comunque e l'app deve riconnettersi, come da punto TCP sopra.

---

## Backup

| Limite | Valore |
|-------|-------|
| Destinazioni di backup per repository | Illimitate |
| Job di backup simultanei | 1 per repository (i job si accodano se attivati contemporaneamente) |
| Frequenza di backup | Nessun intervallo minimo imposto; limitata dalla larghezza di banda di archiviazione. Usa `rdc config backup-strategy set --name <name> --bwlimit "6M"` per limitare la velocità di upload (sintassi rclone `--bwlimit`: semplice `6M`, direzionale `6M:off`, o timetable `08:00,3M;22:00,10M`) |
| Conservazione | Controllata dal tuo provider di archiviazione (S3, Cloudflare R2, ecc.). Rediacc non applica politiche di conservazione. |
| Backup tra macchine | Supportato; la macchina di destinazione deve avere spazio sufficiente nel datastore |

---

## CLI e API

| Limite | Valore |
|-------|-------|
| Comandi `rdc` concorrenti verso la stessa macchina | Illimitati (ogni comando apre la propria connessione SSH) |
| Concorrenza predefinita di avvio parallelo dei repository | 3 (regolabile con `--concurrency`) |
| Timeout di connessione SSH | 30 secondi per la connessione iniziale |
| Durata della sessione `rdc` | Nessun timeout; le operazioni di lunga durata mantengono la connessione attiva |

---

## Versioni OS Supportate

Le macchine remote devono eseguire uno dei seguenti sistemi per soddisfare i requisiti di kernel, file system e isolamento di rete di Rediacc. Questo elenco è il set testato in CI (matrice Bridge Workers) e deve rimanere sincronizzato con [Requisiti](/en/docs/requirements):

| OS | Versione Minima | Kernel Predefinito | Note |
|----|-----------------|----------------|-------|
| Ubuntu | 24.04 LTS *(consigliato)* | 6.8 | AppArmor predefinito. |
| Debian | 13 (Trixie); 12 Bookworm funziona anch'esso | 6.12 (6.1 su Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing predefinito. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor predefinito. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK mantiene btrfs; SELinux enforcing predefinito. |

**Kernel minimo richiesto: 6.1.** Le macchine con kernel più vecchi vengono rifiutate al momento della configurazione con un messaggio di errore chiaro.

> **Perché il kernel 6.1?** Rediacc usa BTRFS per l'archiviazione cifrata dei repository e il forking copy-on-write. Linux 6.1 ha introdotto miglioramenti critici a BTRFS che riducono significativamente i tempi di mount per datastore di grandi dimensioni, migliorano le prestazioni di eliminazione degli snapshot e correggono problemi di integrità dei dati presenti nei kernel precedenti. Il kernel 6.1 è anche necessario per gli hook di isolamento di rete a livello kernel che applicano l'isolamento tra repository, riscrivendo in modo trasparente le chiamate `bind()` e bloccando le connessioni tra repository.

> **Perché non Rocky Linux 10 / RHEL 10 stock kernel?** Il kernel stock di RHEL 10 non include il modulo `btrfs` (`modprobe btrfs` fallisce con "Module btrfs not found"). Il backend di archiviazione cifrata di Rediacc non può funzionare senza btrfs. **Oracle Linux 10 è l'unico target compatibile con RHEL nell'elenco supportato** perché usa per impostazione predefinita l'Unbreakable Enterprise Kernel (UEK), che mantiene btrfs. Vedi [Requisiti -> Perché UEK?](/en/docs/requirements) per la spiegazione completa.

### Matrice delle funzionalità del kernel

Leggi la matrice come una panoramica rapida di ciò che ogni OS testato in CI fornisce immediatamente. Tutti e cinque soddisfano ogni requisito, quindi questa è un riferimento per gli operatori, non un criterio di esclusione.

| OS | Modulo btrfs | cgroups v2 | Landlock (ABI >= 1) | Hook cgroup eBPF |
|----|--------------|------------|--------------------|-------------------|
| Ubuntu 24.04 | in-tree | gerarchia unificata | sì (5.13+) | sì |
| Debian 13 | in-tree | gerarchia unificata | sì | sì |
| Fedora 43 | in-tree | gerarchia unificata | sì | sì |
| openSUSE Leap 16.0 | in-tree | gerarchia unificata | sì | sì |
| Oracle Linux 10 (UEK) | in-tree (tramite UEK) | gerarchia unificata | sì | sì |
