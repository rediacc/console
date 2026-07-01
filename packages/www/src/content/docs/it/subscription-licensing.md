---
title: Abbonamento e licenze
description: >-
  Scopri come account, rdc e renet gestiscono gli slot macchina, le licenze
  repository e i limiti del piano.
category: Guides
order: 7
language: it
sourceHash: 10e9f781881854be
sourceCommit: 2e3862505c06f97f846b7d879375434011954f95
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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Puoi anche iniettare il token direttamente tramite l'ambiente in modo che la CLI possa emettere e aggiornare le licenze repo senza alcun passaggio di login interattivo:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Slot macchina e licenze repo

### Slot macchina (lato server)

Il tracciamento degli slot macchina è applicato lato server. Quando la CLI emette una licenza repo, il server account verifica la quota degli slot macchina dell'abbonamento (ad esempio, 2 macchine per Community, 3 per Professional). Uno slot viene occupato per 5 ore dall'ultima emissione di licenza repo su quella macchina e viene rilasciato automaticamente dopo un periodo di inattività. Un piano Business da 10 slot può quindi coprire dozzine di macchine nel tempo, poiché gli slot vengono occupati solo durante il provisioning attivo.

Nessun file di licenza macchina viene memorizzato sulla macchina. L'applicazione degli slot avviene al momento dell'emissione sul server.

### Licenza repo

Una licenza repo è una licenza firmata per un repository su una macchina. È l'unico file di licenza memorizzato sulla macchina (`/var/lib/rediacc/license/repos/{guid}.json`).

Viene utilizzata per:

- `rdc repo create` e `rdc repo fork`, validata prima del provisioning (pre-emessa senza prove di identità, poi ri-emessa con prove di identità dopo la creazione)
- `rdc repo resize` e `rdc repo expand`, validazione completa inclusa la scadenza
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validata con **scadenza ignorata**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validata con **scadenza ignorata**
- autostart del repository al riavvio della macchina, validata con **scadenza ignorata**

Le licenze repo sono legate alla macchina e al repository target. Ogni licenza contiene l'ID macchina, il GUID del repository, l'ID abbonamento, i limiti del piano e la scadenza. Per i repository cifrati, Rediacc verifica anche l'identità LUKS del volume sottostante.

Più abbonamenti possono coesistere sulla stessa macchina. Ogni repository porta la propria licenza con il proprio contesto di abbonamento.

## Limiti predefiniti

La dimensione del repository dipende dal livello di diritti:

- Community: fino a `10 GB`
- piani a pagamento: limite del piano o del contratto

I limiti predefiniti dei piani a pagamento sono:

| Piano | Licenze floating | Dimensione repository | Emissioni di licenze repo al mese | Validità certificato delega predefinita / massima |
|-------|------------------|-----------------------|-------------------------------------|---------------------------------------------------|
| Community | 2 | 10 GB | 100 | 15g / 30g |
| Professional | 3 | 50 GB | 2.000+ | 60g / 120g |
| Business | 10 | 200 GB | 5.000+ | 90g / 180g |
| Enterprise | 25+ | 1 TB+ | 15.000+ | 120g / 365g |

I limiti specifici del contratto possono aumentare o ridurre questi valori per un cliente specifico. La validità del certificato di delega è anche limitata a `subscription.expiresAt + 3 giorno di grazia`, quindi gli abbonamenti con fatturazione mensile ottengono naturalmente certificati allineati al loro ciclo di fatturazione. Consulta [Catena di licenze e delega - Policy di validità](/it/docs/license-chain) per le regole complete.

## Periodo di grazia per migrazione VM

Quando un provider di hosting migra una VM su hardware fisico diverso, l'ID macchina cambia (è derivato da identificatori hardware come UUID DMI, `/etc/machine-id` e indirizzi MAC della scheda di rete). Le licenze repo sono legate all'ID macchina, quindi una migrazione invaliderebbe normalmente tutte le licenze.

Per gestire questo in modo trasparente, le licenze repo includono un **periodo di grazia di 40 giorni per l'ID macchina**. Se l'ID macchina non corrisponde ma la licenza è stata emessa meno di 40 giorni fa, la licenza viene comunque accettata. Poiché le licenze vengono aggiornate ogni 30 giorni, l'aggiornamento successivo si lega automaticamente al nuovo ID macchina.

In pratica:
- VM migrata, ID macchina cambia: i repository continuano a funzionare (entro la finestra di 40 giorni)
- L'operazione `rdc` successiva aggiorna la licenza con il nuovo ID macchina
- Nessun intervento manuale richiesto
- Verifica l'ID macchina e lo stato della licenza con `rdc machine query --system --licenses --name <machine>`

**Gli utenti del canale edge** ricevono 2X i limiti Community senza costi aggiuntivi (repository da 20 GB, 200 emissioni/mese, 4 macchine). I piani a pagamento sono disponibili solo sul canale Stable. Consulta [Canali di rilascio](/it/docs/release-channels) per i dettagli.

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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Per gli ambienti non interattivi, impostare `REDIACC_SUBSCRIPTION_TOKEN` è l'opzione più semplice. Il token dovrebbe avere scope limitato solo alle operazioni di abbonamento e licenza repo di cui l'agente ha bisogno.

Mostra lo stato dell'abbonamento supportato dall'account:

```bash
rdc subscription status
```

Mostra i dettagli di attivazione della macchina per una macchina:

```bash
rdc subscription activation status -m hostinger
```

Mostra i dettagli della licenza repo installata su una macchina:

```bash
rdc subscription repo status -m hostinger
```

Aggiornamento in blocco delle licenze repo su una macchina:

```bash
rdc subscription refresh repos -m hostinger
```

I repository rilevati sulla macchina ma assenti dalla configurazione `rdc` locale vengono rifiutati durante l'aggiornamento in blocco. Vengono segnalati come errori e non vengono classificati automaticamente.

Forza l'aggiornamento della licenza repo per un repository esistente:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

Al primo utilizzo, un'operazione su un repository con licenza o un backup che non trova una licenza repo utilizzabile può attivare automaticamente un handoff di autorizzazione account. La CLI stampa un URL di autorizzazione, cerca di aprire il browser nei terminali interattivi e riprova l'operazione una volta dopo che l'autorizzazione e l'emissione hanno avuto successo.

Negli ambienti non interattivi, la CLI non attende l'approvazione del browser. Invece, ti dice di fornire un token con scope specifico con `rdc subscription login --token ...` o `REDIACC_SUBSCRIPTION_TOKEN`.

Per la configurazione iniziale della macchina, consulta [Configurazione della macchina](/it/docs/setup).

## Comportamento offline e scadenza

La validazione della licenza avviene localmente sulla macchina. Non hai bisogno di contattare il server account per operare i tuoi repository.

Questo significa che:

- un ambiente in esecuzione non ha bisogno di connettività live all'account su ogni comando
- tutti i repository possono sempre essere avviati, fermati ed eliminati anche con licenze scadute; gli utenti non vengono mai bloccati dall'operare i propri repository
- le operazioni di provisioning (`create`, `fork`) richiedono una licenza repo pre-emessa, e le operazioni di crescita (`resize`, `expand`) richiedono una licenza repo valida
- le licenze repo veramente scadute devono essere aggiornate tramite `rdc` prima delle operazioni di ridimensionamento/espansione
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

Questi casi di fallimento immediato non consumano automaticamente chiamate di aggiornamento o emissione supportate dall'account.

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

Se hai bisogno di una vista rivolta al cliente dell'utilizzo e della cronologia recente delle emissioni di licenze repo, utilizza il portale account. Se hai bisogno dell'ispezione lato macchina, utilizza `rdc subscription activation status -m` e `rdc subscription repo status -m`.
