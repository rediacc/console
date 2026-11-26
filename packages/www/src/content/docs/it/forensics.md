---
title: "Forensics: prove dall'interno di un repository compromesso"
description: "Registrazioni dei flussi di rete e delle aperture di file sensibili per repository, al livello scelto dal cliente, spedite ogni 30 secondi come batch firmati e concatenati. Copre i tre livelli di cattura, il trigger di picco, le quote dei piani, il rilevamento offline e lato server e ciò che il server può leggere."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: it
sourceHash: "c349f479d246dee4"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Forensics

La forensics risponde a due domande quando il software in esecuzione in un repository è compromesso: quando sono stati sottratti i dati e quali. Rediacc non può chiudere una falla nel software di terze parti, perciò la funzione registra prove che sopravvivono alla compromissione. Le registrazioni sono scritte da un collector con privilegi root sulla macchina, fuori dalla sandbox del repository, e spedite in un bucket che gli amministratori del cliente non possono raggiungere.

Le registrazioni mostrano volume, destinazione e tempi. Un record di flusso prova volume e destinazione, non il contenuto. Il [flusso di lavoro per gli incidenti](/it/docs/incident-response) le legge, e i [report di incidente](/it/docs/incident-reports) le trasformano in documenti firmati per un'autorità di controllo.

## Cosa viene registrato

La cattura è per repository. Poiché ogni repository usa la rete dell'host, il traffico viene attribuito tramite cgroup (la slice del repository stesso), mai tramite indirizzo IP.

| Record | Contenuto |
|---|---|
| Flusso di rete | Ora, processo, indirizzo e porta di destinazione, protocollo, byte in uscita e in entrata, nome DNS se noto, e ASN e paese della destinazione se noti |
| Apertura di file | Ora, processo e percorso, per un percorso che corrisponde all'elenco dei percorsi sensibili |
| Heartbeat | Un marcatore firmato in ogni batch, così un collector fermo appare come un vuoto e non come silenzio |

L'elenco sensibile predefinito comprende i file `.env`, i file di chiavi e certificati (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), i database di password (`*.kdbx`), i dump e i file di database (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) e le directory dati dei database come `pgdata`. Un repository può estendere l'elenco o sostituirlo con i propri pattern.

Il contenuto dei pacchetti e dei file non viene mai registrato.

## Livelli di cattura

Ogni repository ha un solo livello, e per impostazione predefinita è il più basso. Un livello superiore registra tutto ciò che registra uno inferiore.

| Livello | Registrato |
|---|---|
| `basic` | Un riepilogo ogni 5 minuti per destinazione, porta e protocollo, con byte in entrata e in uscita |
| `standard` | Un record di flusso al minuto, con processo e nome DNS |
| `full` | Standard, più le aperture di file su percorsi sensibili |

Il livello si imposta per repository:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

Il collector limita il livello a ciò che il piano include. Quando un piano non ha quota forensics, il repository non registra nulla.

### Il trigger di picco

Ogni livello arma un trigger. Quando i byte in uscita di un repository in un minuto superano di dieci volte la sua media mobile (e i 50 MiB al minuto), dopo che il repository è stato osservato per 24 ore, passa a Full per 24 ore. Un minuto che fa scattare il trigger non alimenta la media, così una singola esfiltrazione non può alzare la baseline che dovrebbe individuare la successiva.

## Piani e quote

La forensics è per i piani a pagamento e registra solo finché il piano è pagato. Un upgrade parte senza storico.

| Piano | Quota forensics |
|---|---|
| Free, Community | 0 (non viene registrato nulla) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, o una quota personalizzata fissata dagli amministratori Rediacc |

La quota è un quarto della quota di backup del piano ed è contabilizzata separatamente dai backup. Più quota si ottiene solo con un upgrade di piano.

Quando la quota è piena, i record più vecchi vengono rimossi per primi (FIFO). Gli ultimi 7 giorni sono bloccati e non vengono mai rimossi, perché il bucket li blocca per 7 giorni. Se i soli byte bloccati superassero la quota, i nuovi batch vengono rifiutati. Se l'ingestione prevista su 7 giorni non ci stesse, il livello viene limitato a Basic. Proprietari e amministratori ricevono un avviso all'80 percento della quota, quando il limite scende a Basic e quando un batch viene rifiutato.

Restano esclusi dalla rimozione, fino a 30 giorni dopo la chiusura dell'incidente, i record compresi in un incidente dichiarato. Vedi la [risposta agli incidenti](/it/docs/incident-response).

## Spedizione e integrità

Il collector chiude un batch ogni 30 secondi. Ogni batch è firmato con la chiave di spool della macchina e porta l'hash del batch precedente, quindi un batch rimosso o modificato spezza la catena. Il caricamento avviene tramite URL prefirmati di sola creazione, generati dal blob di licenza della macchina, perciò la macchina può aggiungere record ma non sovrascriverli né eliminarli. Quando la connessione cade, i batch attendono in uno spool locale firmato e partono al ritorno della connessione.

La compattazione notturna unisce i batch in un file giornaliero per repository e un file di header per macchina, in cui ogni header firmato è elencato e ogni vuoto è segnalato. Anche i file giornalieri di audit dell'account sono concatenati allo stesso modo, per organizzazione e giorno.

`rdc forensics verify` e il pulsante Verify evidence della pagina di indagine ricalcolano queste catene. Vedi la [risposta agli incidenti](/it/docs/incident-response).

## Rilevamento

Il rilevamento delle anomalie gira due volte. Un rilevatore statistico sulla macchina reagisce subito, portando il repository a Full. Il server esegue i propri rilevatori in fase di ingestione, quindi il rilevamento sopravvive a un host compromesso. Nessuna IA viene eseguita su ogni record di log.

Ogni repository impara dal proprio traffico, e i rilevatori sono a più livelli:

| Rilevatore | Cerca |
|---|---|
| Baseline per ora della settimana | Byte, connessioni, destinazioni distinte, nuovi nomi DNS e nuovi processi fuori dal ritmo abituale del repository per quell'ora della settimana |
| Half-Space Trees | Un flusso diverso da quelli visti in precedenza |
| ECOD e HBOS | Batch di flussi con punteggio anomalo, con le caratteristiche che hanno determinato il punteggio |
| Prima volta | Un processo che apre un file sensibile che non aveva mai aperto |

Ogni rilevamento porta i motivi per caratteristica che lo hanno prodotto, e la spiegazione è un modello costruito a partire da quei motivi. Offline non c'è alcun modello linguistico. Un rilevamento diventa un avviso dell'account e un'e-mail a proprietari, amministratori e al contatto di sicurezza. Quando la macchina è offline, agisce subito in locale (cattura Full e una voce nel suo spool firmato) e consegna l'allerta al ritorno della connessione, mantenendo l'ora di rilevamento originale.

### Bundle di modelli

Sono pubblicati come bundle firmati su `data.rediacc.com/models/` i parametri dei rilevatori: file indirizzati per contenuto, un manifest firmato con una chiave di modello Ed25519 offline incorporata in renet, una versione minima di renet e una versione che può solo crescere, così un downgrade viene rifiutato. Un bundle viene verificato prima dell'installazione, e il precedente può essere ripristinato.

```bash
renet models status
renet models update
renet models rollback
```

Le installazioni air-gapped ricevono lo stesso bundle firmato dentro `rdc server bundle`, a meno che non venga passato `--no-models`.

## Cosa può leggere il server

Il server degli account legge le registrazioni, perché la timeline, la verifica e i rilevatori del server ne hanno bisogno: destinazioni, porte, nomi di processo, nomi DNS, contatori di byte e percorsi di file sensibili. Non riceve il contenuto dei pacchetti né quello dei file.

Un indirizzo client in ingresso viene memorizzato troncato nei record (a /24 per IPv4 e a /48 per IPv6), e l'indirizzo completo si trova in una sezione separata che viene eliminata dopo 30 giorni. L'hash della sezione eliminata resta nell'header firmato, quindi la catena si verifica ancora e il verificatore segnala l'indirizzo come oscurato. Le destinazioni in uscita restano intere, perché sono la prova.

Le registrazioni si aprono tramite un'indagine, che richiede un piano a pagamento, il ruolo di proprietario o amministratore e una riautenticazione recente, e ogni consultazione viene sottoposta ad audit. Il supporto Rediacc vede i dati forensics solo con un'autorizzazione a tempo emessa dal cliente. Le condizioni del trattamento sono nell'[accordo sul trattamento dei dati](/it/data-processing-agreement).
