---
title: Abbonamento e licenze
description: >-
  Scopri come account, rdc e renet gestiscono gli slot macchina, le licenze
  repository e i limiti del piano.
category: Guides
tags:
  - account
order: 7
language: it
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
---

# Abbonamento e licenze

Le licenze Rediacc si dividono in tre componenti principali:

- `account` firma i diritti di utilizzo e tiene traccia dell'utilizzo
- `rdc` si autentica, richiede le licenze, le consegna alle macchine e le applica a runtime
- `renet` (il runtime sulla macchina) valida le licenze installate localmente senza contattare il server account

Questa pagina spiega come questi componenti si integrano tra loro per i deployment locali.

## Cosa fanno le licenze

Le licenze controllano due aspetti distinti:

- **Contabilizzazione dell'accesso alla macchina** tramite **licenze floating**
- **Autorizzazione runtime del repository** tramite **licenze repo**

Questi aspetti sono correlati, ma non rappresentano lo stesso artefatto.

## Come funzionano le licenze

`account` è la fonte di verità per i piani, le sovrascritture contrattuali, lo stato degli slot macchina e le emissioni mensili di licenze repo.

`rdc` viene eseguito sulla tua workstation. Effettua il login sul server account, richiede le licenze necessarie e le installa sulle macchine remote tramite SSH. Quando esegui un comando repository, `rdc` assicura che le licenze richieste siano in atto e le valida sulla macchina a runtime.

Il flusso normale è il seguente:

1. Ti autentica con `rdc subscription login`
2. Esegui un comando repository come `rdc repo create`, `rdc repo up` o `rdc repo down`
3. Se la licenza richiesta è mancante o scaduta, `rdc` la richiede ad `account`
4. `rdc` scrive la licenza firmata sulla macchina
5. La licenza viene validata localmente sulla macchina e l'operazione continua

Consulta [rdc vs renet](/it/docs/rdc-vs-renet) per la divisione workstation/server, e [Repository](/it/docs/repositories) per il ciclo di vita del repository stesso.

Per automazione e agenti AI, utilizza un token di abbonamento con scope specifico invece del login tramite browser:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Puoi anche iniettare il token direttamente tramite l'ambiente in modo che la CLI possa emettere e aggiornare le licenze repo senza alcun passaggio di login interattivo:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slot macchina e licenze repo

### Slot macchina (lato server)

Il tracciamento degli slot macchina è applicato lato server. Quando la CLI emette una licenza repo, il server account verifica la quota di slot macchina dell'abbonamento. Ogni piano self-service (Community, Professional, Business) include uno slot macchina; i deployment multi-macchina sono una configurazione Enterprise dimensionata insieme ai nostri partner. Uno slot viene occupato per 5 ore dall'ultima emissione di licenza repo su quella macchina e viene rilasciato automaticamente dopo un periodo di inattività. Poiché uno slot viene occupato solo mentre stai eseguendo provisioning attivamente, un singolo slot può comunque coprire più macchine nel corso di un mese.

Il tetto viene letto dal record del tuo abbonamento, non da una costante di piano scritta nel codice, quindi un numero di attivazioni concordato vale non appena viene impostato sull'abbonamento. Il livello del piano decide soltanto il valore di partenza.

Emissione e rinnovo vengono applicati in modo diverso, e la differenza conta:

- **L'emissione di una nuova licenza si blocca al tetto.** Se tutti gli slot sono occupati, la richiesta fallisce con `MAX_MACHINES_REACHED` e non viene fatto alcun provisioning.
- **Il rinnovo di una licenza esistente non si blocca mai.** Una macchina che rinnova mentre tutti gli slot sono occupati continua a funzionare e il suo slot viene registrato come oltre il limite. Lo vedi nel portale nella pagina Macchine, in `rdc subscription status` e nel campo `overLimitCount` dell'API di stato delle licenze. Il contrassegno si azzera da solo quando la macchina rientra nel limite.

Il rinnovo è deliberatamente la strada più morbida. Una macchina che rinnova una licenza che già possiede non è nuova capacità, e rifiutarla fermerebbe i backup su un'infrastruttura già pagata. Quello che resta bloccato è l'aggiunta di capacità.

Nessun file di licenza macchina viene memorizzato sulla macchina. L'applicazione degli slot avviene al momento dell'emissione sul server.

### Licenza repo

Una licenza repo è una licenza firmata per un repository su una macchina. È l'unico file di licenza memorizzato sulla macchina, organizzato per datastore e per chiave di firma:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

I repository sullo storage predefinito di una macchina usano il primo percorso. I repository in un datastore con nome usano il secondo, dove `{datastoreId}` è l'identità assegnata a quel datastore alla creazione. È questa separazione a far sì che il fork di un datastore venga contabilizzato onestamente: un datastore forkato riceve un'identità completamente nuova, quindi i suoi repository partono senza alcuna licenza, riportano `missing` alla loro prima operazione sotto licenza e ottengono le proprie licenze. Un repository la cui licenza indica un datastore diverso da quello in cui si trova fallisce subito con `identity_mismatch` invece di essere riemesso automaticamente, ed è questo che impedisce di copiare un file di licenza da una parte all'altra.

`{keyId}` è un'impronta esadecimale a 16 cifre (i primi 8 byte dello `SHA-256` della chiave pubblica Ed25519 del server firmatario). Un repository gestito da più di un universo account (ad esempio produzione e bench che effettuano il deployment sulla stessa macchina) mantiene un file per ogni chiave di firma nella propria directory `{guid}`. La build renet della macchina valida solo il file che la sua chiave incorporata, o un certificato di delega concatenato ad essa, può verificare; i file degli altri universi restano inerti. Il passaggio tra universi non invalida mai le licenze: la prima operazione in un nuovo universo emette la licenza di quell'universo una volta sola (un risultato `missing` la emette automaticamente), e da quel momento coesistono entrambe.

Viene utilizzata per:

- `rdc repo create`, `rdc repo fork` e `rdc repo commit`, validata prima del provisioning (pre-emessa senza prove di identità, poi ri-emessa con prove di identità dopo la creazione, perché al momento del controllo il repository non esiste ancora)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` e `rdc repo promote`, **validazione completa, scadenza inclusa**
- il trasferimento dei backup, **validazione completa, scadenza inclusa**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` e i backup pianificati
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` e l'autostart del repository al riavvio della macchina, validati **saltando sia la scadenza sia la finestra del certificato di delega**
- `rdc repo down`, `rdc repo delete` e i comandi di sola lettura come l'elenco dei repository non richiedono alcuna licenza

Firme, binding della chiave, binding della macchina, binding del repository e ogni vincolo del certificato di delega restano applicati in tutti questi casi. L'ultimo gruppo allenta soltanto le due finestre temporali, così che una licenza scaduta o un certificato decaduto non possano mai impedirti di far girare o di fermare i tuoi stessi dati.

Le licenze repo sono legate alla macchina e al repository target. Ogni licenza contiene l'ID macchina, il GUID del repository, l'ID abbonamento, i limiti del piano e la scadenza. Per i repository cifrati, Rediacc verifica anche l'identità LUKS del volume sottostante.

Più abbonamenti possono coesistere sulla stessa macchina. Ogni repository porta la propria licenza con il proprio contesto di abbonamento.

## Cluster

Il clustering viene venduto tramite i nostri partner nell'ambito di un accordo Enterprise. Non è un'opzione di piano self-service, e i punti qui sotto descrivono come viene contabilizzato, non come acquistarlo.

**Un nodo è una macchina.** Un cluster non ha un'identità di licenza propria. Ogni nodo che lo compone è una macchina ordinaria con l'agente Renet installato, e viene conteggiato esattamente come una macchina a sé stante.

**Non c'è alcun raggruppamento.** Un cluster di cinque nodi non attinge da un unico slot cluster condiviso. Ogni nodo occupa il proprio slot la prima volta che vi viene collocato un repository, e quello slot segue la stessa fluttuazione di 5 ore di qualsiasi altro: resta occupato per 5 ore dall'ultima emissione di licenza repo su quel nodo e poi si libera da solo.

**Costruire il cluster è gratis. Sono i repository a far scattare il contatore.** Creare il cluster, aggiungere nodi, installare il livello di storage distribuito e mettere in piedi il control plane Kubernetes non costano alcuno slot. La contabilizzazione inizia quando un repository arriva su un nodo.

**Il fork di un cluster ricontabilizza repository per repository.** Forkare un intero cluster assegna al datastore forkato una nuova identità, quindi ogni repository del fork ottiene la propria licenza la prima volta che viene toccato, sul nodo su cui sta girando. La semplice migrazione è il caso opposto: spostare un repository tra macchine porta con sé la sua licenza e continua a validare, perché nulla della sua identità di storage è cambiato.

**Il rinnovo su un cluster segue la regola morbida vista sopra.** I nodi rinnovano le proprie licenze senza supervisione, quindi un cluster cresciuto oltre il proprio numero di attivazioni continua a funzionare e segnala i nodi oltre il limite invece di far fallire i backup nel cuore della notte. L'aggiunta di un nuovo nodo, invece, si blocca comunque al tetto.

Dimensionare un cluster è una conversazione, non una casella da spuntare. I numeri di attivazione per i cluster si concordano nell'ordine, e il tuo partner li imposta direttamente sull'abbonamento. Consulta [Contatti](/it/contact) per avviare quella conversazione.

## Limiti predefiniti

La dimensione del repository dipende dal livello di diritti:

- Community: fino a `10 GB`
- piani a pagamento: limite del piano o del contratto

I limiti predefiniti dei piani a pagamento sono:

| Piano | Licenze floating | Dimensione repository | Emissioni di licenze repo al mese | Validità certificato delega predefinita / massima |
|-------|------------------|-----------------------|-------------------------------------|---------------------------------------------------|
| Community | 1 | 10 GB | 100 | 15g / 30g |
| Professional | 1 | 100 GB | 2.000+ | 60g / 120g |
| Business | 1 | 500 GB | 5.000+ | 90g / 180g |
| Enterprise | Personalizzato | 1 TB+ | 15.000+ | 120g / 365g |

I limiti specifici del contratto possono aumentare o ridurre questi valori per un cliente specifico. La validità del certificato di delega è anche limitata a `subscription.expiresAt + 3 giorno di grazia`, quindi gli abbonamenti con fatturazione mensile ottengono naturalmente certificati allineati al loro ciclo di fatturazione. Consulta [Catena di licenze e delega - Policy di validità](/it/docs/license-chain) per le regole complete.

## Prova gratuita e ripiego su Community

Le nuove registrazioni iniziano con una prova gratuita di 14 giorni sul piano Professional o Business. La carta di credito viene richiesta al momento della registrazione, ma il primo addebito avviene solo alla fine del periodo di prova, quindi disdire prima di allora non comporta alcun costo. È disponibile una sola prova gratuita per cliente.

Community resta il piano gratuito di base permanente. Non è più selezionabile direttamente in fase di registrazione per i nuovi account; un account passa a Community ogni volta che un abbonamento termina: disdetta durante la prova, disdetta successiva di un piano a pagamento, oppure un pagamento non riuscito. Nel piano Community di riserva mantieni una macchina con 10 GB per repository e 100 configurazioni al mese. Gli account creati prima del lancio del modello basato su prova gratuita mantengono il loro accesso a Community esistente.

L'applicazione resta permissiva dove conta di più: i repository in esecuzione continuano a funzionare anche dopo la fine di un abbonamento (`up`, `down`, `delete`, autostart). Oltre a questo valgono due regole diverse, ed è confonderle che fa sembrare incoerente la grazia di 60 giorni:

- **Le operazioni che hanno bisogno del server account** non possono avvenire senza un abbonamento attivo, perché il server si rifiuta di firmare. Sono `create`, `fork` e qualsiasi aggiornamento o rinnovo di licenza. Una volta decaduto l'abbonamento, non viene più fatto il provisioning di nulla di nuovo.
- **Le operazioni che richiedono solo una licenza installata valida** continuano a funzionare fino alla scadenza hard di quella licenza, senza alcun server coinvolto. Sono `resize` ed `expand` sui repository che hai già, e il trasferimento dei backup (`push`, `pull`, backup pianificati). La licenza primaria di un repository raggiunge la scadenza hard 60 giorni dopo la data di fine abbonamento, ed è da lì che viene la grazia di 60 giorni. La licenza di un fork ha vita molto più breve, limitata a 7 giorni, ed è per questo che le macchine con molti fork dipendono dall'auto-rinnovo descritto più avanti.

Quindi un abbonamento decaduto ti impedisce subito di far crescere il tuo parco macchine, e 60 giorni dopo di far crescere i repository che contiene.

## Periodo di grazia per migrazione VM

Quando un provider di hosting migra una VM su hardware fisico diverso, l'ID macchina cambia (è derivato da identificatori hardware come UUID DMI, `/etc/machine-id` e indirizzi MAC della scheda di rete). Le licenze repo sono legate all'ID macchina, quindi una migrazione invaliderebbe normalmente tutte le licenze.

Per gestire questo in modo trasparente, le licenze repo includono un **periodo di grazia di 40 giorni per l'ID macchina**. Se l'ID macchina non corrisponde ma la licenza è stata emessa meno di 40 giorni fa, la licenza viene comunque accettata. Poiché le licenze vengono aggiornate ogni 30 giorni, l'aggiornamento successivo si lega automaticamente al nuovo ID macchina.

In pratica:
- VM migrata, ID macchina cambia: i repository continuano a funzionare (entro la finestra di 40 giorni)
- L'operazione `rdc` successiva aggiorna la licenza con il nuovo ID macchina
- Nessun intervento manuale richiesto
- Verifica l'ID macchina e lo stato della licenza con `rdc machine status <machine> --system --licenses`

**Gli account sul canale Edge** operano sul piano Community con il doppio dei limiti (repository da 20 GB, 200 configurazioni/mese, 2 macchine). I piani a pagamento sono disponibili solo sul canale Stable. Consulta [Canali di rilascio](/it/docs/release-channels) per i dettagli.

## Cosa succede durante la creazione, l'avvio, l'arresto e il riavvio di un repository

### Creazione e fork del repository

Quando crei o forki un repository:

1. `rdc` assicura che il tuo token di abbonamento sia disponibile (attiva l'autenticazione con device-code se necessario)
2. `rdc` pre-emette una licenza repo dal server account (il server verifica la quota degli slot macchina e i limiti mensili di emissione in questo momento)
3. La licenza repo pre-emessa viene scritta sulla macchina e validata localmente (firma, ID macchina, GUID del repository, scadenza e limite di dimensione)
4. Dopo la creazione riuscita, `rdc` ri-emette la licenza repo con le prove di identità del repository (UUID LUKS o fingerprint dello storage)

Quella emissione supportata dall'account conta per il tuo utilizzo mensile di **emissioni di licenze repo**. Ogni licenza contiene l'email e il nome dell'azienda del titolare dell'account, che vengono registrati quando renet valida la licenza.

### Avvio, arresto ed eliminazione del repository

`rdc` valida la licenza repo installata sulla macchina ma **ignora il controllo della scadenza**. Firma, ID macchina, GUID del repository e identità vengono comunque verificati. Gli utenti non vengono mai bloccati dall'operare i propri repository, anche con un abbonamento scaduto.

### Ridimensionamento ed espansione del repository

`rdc` esegue la validazione completa della licenza repo inclusa la scadenza e i limiti di dimensione.

### Riavvio della macchina e autostart

L'autostart utilizza le stesse regole di `rdc repo up`: la scadenza viene ignorata, quindi i repository si riavviano sempre liberamente.

Le licenze repo utilizzano un modello di validità a lungo termine:

- `refreshRecommendedAt` è il punto di aggiornamento soft
- `hardExpiresAt` è il punto di blocco

Se la licenza repo è obsoleta ma ancora prima della scadenza hard, il runtime può continuare. Una volta raggiunta la scadenza hard, `rdc` deve aggiornarla per le operazioni di ridimensionamento/espansione.

### Altre operazioni di repository

Le operazioni come la lista dei repository, l'ispezione delle informazioni del repository e il montaggio non richiedono alcuna validazione della licenza.

## Verifica dello stato e aggiornamento delle licenze

Login utente:

```bash
rdc subscription login
```

Login per automazione o agenti AI:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Per gli ambienti non interattivi, impostare `REDIACC_TOKEN` è l'opzione più semplice. Il token dovrebbe avere scope limitato solo alle operazioni di abbonamento e licenza repo di cui l'agente ha bisogno.

Mostra lo stato dell'abbonamento supportato dall'account:

```bash
rdc subscription status
```

Mostra i dettagli di attivazione della macchina per una macchina:

```bash
rdc subscription status -m hostinger
```

Mostra i dettagli della licenza repo installata su una macchina:

```bash
rdc subscription status -m hostinger
```

Aggiorna la licenza di un repository su una macchina:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

Il ref `--repo` deve risolversi nella tua configurazione `rdc` locale. Un repository rilevato sulla macchina ma assente dalla configurazione locale viene rifiutato: viene segnalato come errore e non viene classificato automaticamente.

Al primo utilizzo, un'operazione su un repository con licenza o un backup che non trova una licenza repo utilizzabile può attivare automaticamente un handoff di autorizzazione account. La CLI stampa un URL di autorizzazione, cerca di aprire il browser nei terminali interattivi e riprova l'operazione una volta dopo che l'autorizzazione e l'emissione hanno avuto successo.

Negli ambienti non interattivi, la CLI non attende l'approvazione del browser. Invece, ti dice di fornire un token con scope specifico con `rdc subscription login --token ...` o `REDIACC_TOKEN`.

Per la configurazione iniziale della macchina, consulta [Configurazione della macchina](/it/docs/setup).

## Auto-rinnovo delle licenze

Tutto quanto sopra presuppone che tu sia davanti a una tastiera. I backup pianificati non lo sono, ed è proprio per quel caso che esiste l'auto-rinnovo.

Un backup pianificato viene validato al livello stretto, quindi gli serve una licenza non scaduta. La licenza di un fork è limitata a 7 giorni. Le tue macchine non conservano credenziali dell'account per scelta progettuale, così prima dell'auto-rinnovo il backup di un fork semplicemente si fermava una settimana dopo la sua creazione, in silenzio, alle tre di notte.

### Come una macchina rinnova senza possedere un token

Ogni licenza che Rediacc emette o rinnova porta un `renewalUrl`, l'indirizzo completo dell'endpoint di rinnovo sul server account che l'ha firmata. Una macchina legge quell'indirizzo dalla propria licenza installata, quindi non c'è mai bisogno di dirle dove si trova il suo server account.

La macchina presenta poi la licenza installata a quell'endpoint. La licenza è la credenziale di se stessa: è firmata, il server ne verifica la firma, e non entra in gioco alcun token API. Il server restituisce una licenza fresca con nuove finestre di validità, e la macchina la installa e la rivalida prima di considerare concluso il rinnovo.

Il rinnovo è un'operazione che riguarda l'intera macchina:

```bash
sudo renet license renew
```

I repository vengono raggruppati per server firmatario, così una macchina che serve due universi account contatta ciascuno una sola volta. Un file di lock impedisce che due rinnovi girino contemporaneamente, e `--jitter` distribuisce nel tempo un parco di macchine che altrimenti si sveglierebbero tutte allo scoccare dell'ora.

Il server rifiuta un rinnovo in tre casi, e ciascuno significa qualcosa di diverso:

| Rifiuto | Che cosa significa |
|---|---|
| L'abbonamento è decaduto, è sospeso, o ha superato il periodo di grazia | Fatturazione. Il rinnovo riprende da solo una volta che l'abbonamento torna attivo |
| Il certificato di delega è scaduto o revocato | Configurazione on-premise. Rinnova il certificato sul tuo server on-premise, poi le macchine rinnovano normalmente |
| L'identità della macchina non corrisponde più e la grazia di 40 giorni è passata | La licenza appartiene a una macchina che non è questa. Riemetti dal contesto della macchina corrente |

Un rifiuto non ferma mai l'intera esecuzione. Un repository decaduto non blocca il rinnovo degli altri sulla stessa macchina.

### I backup pianificati si rinnovano da soli

Ogni unità di backup che Rediacc scrive esegue prima un rinnovo:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

Il `-` iniziale lo marca come best effort di proposito. Un rinnovo rifiutato, un'interruzione di rete o un agente Renet più vecchio che non conosce ancora il comando non devono mai far saltare il backup stesso. Il backup viene eseguito, e la licenza viene rinnovata strada facendo ogni volta che è possibile.

### Quando un backup è bloccato

Se il sistema di licenze rifiuta davvero un backup, la macchina lo registra. Quel marcatore è l'unico segnale che i backup non presidiati hanno smesso di copiare dati, perciò viene messo bene in evidenza:

```bash
rdc machine status <machine> --licenses
```

La colonna `backups` mostra `BLOCKED` con il motivo, e la stessa informazione viene stampata sotto la tabella come errore, così da non perdersi tra trenta repository. La colonna `renewed` mostra com'è andato l'ultimo rinnovo non presidiato, incluso il codice di rifiuto del server quando c'è stato, ed è questo a dirti se la soluzione è una questione di fatturazione o di certificato on-premise.

Un rinnovo riuscito cancella il marcatore, e lo fa anche un backup che supera il proprio controllo di licenza. Non c'è nulla da confermare o da azzerare a mano.

## Comportamento offline e scadenza

La validazione della licenza avviene localmente sulla macchina. Non hai bisogno di contattare il server account per operare i tuoi repository.

Questo significa che:

- un ambiente in esecuzione non ha bisogno di connettività live all'account su ogni comando
- tutti i repository possono sempre essere avviati, fermati ed eliminati anche con licenze scadute; gli utenti non vengono mai bloccati dall'operare i propri repository
- le operazioni di provisioning (`create`, `fork`) richiedono una licenza repo pre-emessa, e le operazioni di crescita (`resize`, `expand`) richiedono una licenza repo valida
- le licenze repo veramente scadute devono essere sostituite prima delle operazioni di ridimensionamento/espansione, tramite `rdc` dalla tua workstation oppure con la macchina che si rinnova da sola
- le firme delle licenze vengono verificate rispetto a una chiave pubblica incorporata; la verifica della firma non può essere disabilitata

## Comportamento di ripristino

Il ripristino automatico è intenzionalmente limitato:

- `missing`: `rdc` può autorizzare l'accesso all'account se necessario, aggiornare in blocco le licenze repo e riprovare una volta
- `expired`: `rdc` può aggiornare in blocco le licenze repo e riprovare una volta
- `machine_mismatch`: fallisce immediatamente e ti dice di ri-emettere dal contesto della macchina corrente
- `repository_mismatch`: fallisce immediatamente e ti dice di aggiornare le licenze repo esplicitamente
- `sequence_regression`: fallisce immediatamente come problema di integrità/stato della licenza repo
- `invalid_signature`: fallisce immediatamente come problema di integrità/stato della licenza repo
- `identity_mismatch`: fallisce immediatamente, l'identità del repository non corrisponde alla licenza installata
- `cert_expired`: fallisce immediatamente sulle operazioni di crescita (`create`, `fork`, `resize`) e sul trasferimento dei backup (`push`, `pull`); `repo up` e l'avvio automatico continuano a funzionare, in linea con il modello permissivo di scadenza della licenza. Riemetti il certificato di delega
- `cert_invalid`: fallisce immediatamente, il certificato di delega non ha soddisfatto un vincolo (firma della chiave master non valida, mancata corrispondenza di abbonamento/piano, limite di dimensione o sequenza superiore a `maxTotalIssuances`). Riemetti il certificato dopo aver corretto il limite sottostante

Questi casi di fallimento immediato non consumano automaticamente chiamate di aggiornamento o emissione supportate dall'account.

Due note per leggere questo elenco:

- `missing` non è sempre un problema. È anche il risultato normale la prima volta che un repository viene toccato dentro un datastore appena forkato, ed è esattamente ciò che fa scattare la contabilizzazione di quel fork: la licenza viene emessa, uno slot viene occupato e l'operazione prosegue. `identity_mismatch` è l'opposto voluto: un file di licenza copiato da un altro datastore fallisce subito invece di essere riemesso in silenzio.
- Questo elenco descrive il ripristino dalla tua workstation. Una macchina che si rinnova da sola ha esiti propri, riportati da `rdc machine status <machine> --licenses` anziché sollevati come errore di comando, perché un backup pianificato non ha nessuno a cui dirlo.

## Certificati di delega per on-premise

Per i deployment on-premise e air-gapped, questo diventa complesso. Il server account upstream emette un **certificato di delega** che autorizza la tua installazione on-premise a firmare licenze con la propria chiave Ed25519. Questo ti vincola ai limiti del tuo piano e crea una catena a prova di manomissione.

Punti chiave per i titolari dell'abbonamento:

- **Un certificato attivo per abbonamento.** Ogni installazione on-premise applica le quote mensili e per macchina rispetto al proprio registro locale, quindi installazioni multiple moltiplicherebbero la quota effettiva senza possibilità di riconciliazione. I clienti che hanno bisogno di produzione + staging + DR devono acquistare un abbonamento per installazione.
- **Validità predefinita basata sul tier** (15g / 60g / 90g / 120g) e limiti massimi (30g / 120g / 180g / 365g) - consulta la tabella dei limiti sopra.
- **Self-service dal portale clienti.** I proprietari e gli amministratori dell'organizzazione possono creare, rinnovare e revocare i certificati di delega su `/account/delegation-certs`. La pagina è visibile a tutti i clienti indipendentemente dal tier del piano - solo i limiti differiscono.
- **Il rinnovo automatico** è supportato tramite un bootstrap con un clic che conia un token API con scope `delegation:renew` per l'on-premise da utilizzare per le chiamate di rinnovo upstream.
- **Il rinnovo air-gapped** è supportato tramite un manifesto di richiesta di rinnovo firmato che l'amministratore on-premise scarica, trasferisce offline all'upstream, e l'upstream elabora per emettere un nuovo certificato.

Consulta [Installazione on-premise - Licenze per deployment air-gapped](/it/docs/on-premise) per la configurazione operativa, e [Catena di licenze e delega](/it/docs/license-chain) per il design crittografico.

## Emissioni mensili di licenze repo

Questa metrica conta le attività di emissione di licenze repo supportate dall'account avvenute con successo nel mese di calendario UTC corrente.

Include:

- emissione della licenza repo per la prima volta
- aggiornamento della licenza repo riuscito che restituisce una licenza firmata di recente

Non include:

- voci in blocco non modificate
- tentativi di emissione non riusciti
- repository non tracciati rifiutati prima dell'emissione

Se hai bisogno di una vista rivolta al cliente dell'utilizzo e della cronologia recente delle emissioni di licenze repo, utilizza il portale account. Se hai bisogno dell'ispezione lato macchina, utilizza `rdc subscription status -m` e `rdc subscription status -m`.
