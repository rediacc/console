---
title: "Catena di Licenze e Delega"
description: "Emissione di licenze a prova di manomissione, firma delegata per on-premise e rilevamento dei fork."
category: "Guides"
tags:
  - account
  - security
subcategory: account
order: 8
language: it
sourceHash: "d6d980d721be2373"
sourceCommit: "fc24769cfd0684622952395c5bafe44e6180530d"
---

# Catena di Licenze e Delega

Rediacc utilizza una catena di hash a prova di manomissione per l'emissione delle licenze e un modello di certificato di delega per i deployment on-premise. Questa pagina spiega come il sistema protegge da manomissioni, attacchi di replay e condivisione delle licenze.

## Perché una Catena?

Ogni licenza emessa da un server account viene registrata in un registro append-only. Ogni voce è collegata alla precedente tramite un hash SHA-256, formando una catena. La catena ha tre proprietà che rendono rilevabile qualsiasi manomissione:

1. I **numeri di sequenza** sono globali e monotoni per abbonamento. Saltare o riordinare le voci interrompe la catena.
2. Gli **hash della catena** vincolano ogni voce a tutte le voci precedenti. Modificare qualsiasi voce passata invalida tutte le voci successive.
3. **Renet memorizza la sequenza più alta che ha visto** per chiave di firma e abbonamento. Un server che fa rollback della sua sequenza viene rilevato immediatamente.

## Come Viene Emessa una Licenza

Quando la CLI richiede una licenza per un repository, il server account:

1. Legge la testa corrente della catena (ultima sequenza + hash) per l'abbonamento.
2. Costruisce il payload della licenza con il numero di sequenza successivo e l'hash della catena precedente inclusi.
3. Firma il payload con Ed25519.
4. Calcola `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Aggiunge la voce al registro di emissione in modo atomico. Se due richieste concorrenti collidono sulla stessa sequenza, quella perdente acquisisce la sequenza successiva e ri-firma.
6. Restituisce il blob firmato con l'hash della catena alla CLI.

`sequence` e `prevChainHash` sono all'interno del payload firmato (non possono essere modificati senza invalidare la firma). `chainHash` è nell'envelope (calcolato dopo la firma per evitare una dipendenza circolare).

## Come Viene Rinnovata una Licenza

L'emissione parte dalla tua workstation, autenticata come te. Il rinnovo parte invece dalla macchina, che non conserva alcuna credenziale dell'account. Serve quindi una porta diversa:

```
POST /licenses/renew
{ license: <il blob firmato installato>, machineId, clusterId? }
```

**La licenza presentata è la credenziale.** Su questo endpoint non c'è alcun token API. Il server verifica la firma Ed25519 del blob, e attraverso il certificato di delega quando il blob ne porta uno, esattamente come fa Renet sulla macchina. Possedere una licenza validamente firmata per un repository è già la prova del diritto, e una macchina che ne ha una se l'è vista concedere in precedenza.

L'URL completo di questo endpoint viaggia dentro ogni licenza che il server emette o rinnova, nel campo `renewalUrl`. Una macchina legge l'indirizzo del proprio server account dalla propria licenza invece di esserne configurata, ed è questo che permette a una macchina che serve due universi account di rinnovare presso entrambi.

Il blob rinnovato mantiene il GUID del repository, il GUID grand e il tipo di quello presentato, prende la sequenza successiva dallo stesso registro con l'hash della catena che ne deriva, e ottiene finestre di validità ricalcolate. L'ID macchina viene rilegato alla macchina che ha presentato il blob, ed è così che una migrazione di VM si ripara da sola entro la grazia di 40 giorni. L'identità dello storage (l'UUID LUKS o il fingerprint dello storage) viene riportata invariata, perché una chiamata di rete non può ri-scansionare il disco che sta descrivendo.

### Rifiuti

| Code | Status | Significato |
|---|---|---|
| `INVALID_LICENSE_SIGNATURE` | 403 | La firma del blob non è stata verificata, oppure il suo hash della catena non corrisponde al registro del server a quella sequenza |
| `INVALID_LICENSE_PAYLOAD` | 400 | Il blob è malformato |
| `DELEGATION_CERT_INVALID` | 403 | Il certificato allegato ha violato un vincolo o la firma della sua chiave master |
| `DELEGATION_CERT_EXPIRED` | 403 | Il certificato allegato è fuori dalla sua finestra di validità |
| `DELEGATION_CERT_REVOKED` | 403 | Il certificato allegato è stato revocato a monte |
| `LICENSE_IDENTITY_MISMATCH` | 403 | La macchina che presenta la licenza non è quella licenziata e la grazia di 40 giorni è scaduta |
| `SUBSCRIPTION_LAPSED` | 403 | L'abbonamento è scaduto o è sospeso |
| `GRACE_PERIOD_ENDED` | 403 | Il periodo di grazia dell'abbonamento è terminato |
| `TRIAL_REQUIRED` | 403 | L'abbonamento richiede una prova o un piano attivo |
| `REPO_GUID_OWNERSHIP_CONFLICT` | 403 | Il GUID del repository appartiene a un altro abbonamento |
| `LICENSE_RENEWAL_FAILED` | 500 | Qualsiasi caso non classificato |

Un rifiuto lascia intatta la licenza installata. La macchina continua a funzionare con quello che ha fino alla scadenza hard di quella licenza.

### Rinnovo e slot macchina

Un rinnovo riuscito tocca la riga di attivazione della macchina: occupa uno slot se la macchina non ne aveva, e lo aggiorna se ne aveva già uno. A differenza dell'emissione, non viene mai rifiutato per superamento del limite. La risposta porta `overLimit`, e l'attivazione viene contrassegnata perché il portale, l'endpoint di stato della licenza e `rdc subscription status` possano mostrarla. L'emissione di una licenza davvero nuova, invece, si blocca sempre contro il tetto. Il ragionamento è spiegato in [Abbonamento e licenze - Slot macchina](/it/docs/subscription-licensing).

### Ordine di deployment

I server account vengono distribuiti prima delle build della CLI e dell'agente Renet che dipendono dai campi qui sopra. Un agente Renet che non trova alcun `renewalUrl` in una licenza salta quel repository e lo segnala invece di fallire, così una licenza più vecchia continua a funzionare finché un aggiornamento dalla workstation non popola il campo. Farlo nell'ordine inverso lascia macchine che chiedono un endpoint non ancora esistente.

## Come Renet Valida

Ogni macchina che esegue Renet memorizza il suo ultimo stato della catena noto in `{licenseDir}/chain-state.json` (cioè `/var/lib/rediacc/license/chain-state.json`, una directory gemella della `repos/` per repository). Lo stato della catena ha scope per chiave di firma, abbonamento, repository e datastore, con chiave nel formato `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` (la parte del datastore resta vuota per un repository sul datastore predefinito della macchina).

Le parti relative al repository e al datastore di quella chiave sono determinanti. Sul server i numeri di sequenza sono per abbonamento, quindi su una macchina che ospita più repository sotto un solo abbonamento una testa della catena registrata per il repository B si troverebbe più avanti della licenza che il repository A sta per presentare, e il repository A verrebbe rifiutato come un replay con cui non c'entrava nulla. Un fork del datastore acuisce lo stesso problema: il clone mantiene il GUID del repository e viene coniata di nuovo solo la sua identità di datastore, quindi senza la parte del datastore la licenza più recente del fork farebbe avanzare una testa contro cui l'originale valida ancora. Ancorare la testa registrata al repository e al datastore indicati dalla licenza elimina entrambi i casi. Le voci scritte da un agente Renet più vecchio in un formato di chiave più corto vengono eliminate al primo salvataggio dello stato, e la validazione successiva ricostruisce la testa.

Lo stato della catena viene letto e fatto avanzare solo sulle operazioni validate al livello completo. Il livello operativo non lo legge né lo fa avanzare, quindi avviare un repository non può mai spostare una testa.

A ogni validazione della licenza, Renet verifica:

| Verifica | Il fallimento significa |
|---|---|
| La firma Ed25519 è valida | La licenza è stata contraffatta o manomessa |
| `sequence >= lastKnownSequence` | Il server ha fatto rollback della catena (attacco di replay) |
| Una ripetizione di `lastKnownSequence` porta lo stesso `chainHash` | Una catena forkata ha riutilizzato un numero di sequenza |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | La voce della catena è stata modificata |

Rivalidare la licenza già installata non è una regressione: la stessa sequenza con lo stesso hash della catena viene accettata, ed è questo che permette a una macchina di validare lo stesso file a ogni avvio di un repository.

Se una qualsiasi verifica fallisce, la licenza viene rifiutata e viene segnalato il motivo del fallimento.

## Certificati di Delega (On-Premise)

Per i deployment air-gapped o self-hosted, il server account upstream emette un **certificato di delega** che autorizza un server on-premise a firmare licenze con la propria chiave Ed25519. Il certificato vincola ciò che il server on-premise può fare.

### Struttura del certificato

Un certificato di delega contiene:

- `subscriptionId` -- a quale abbonamento si applica questo certificato
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- limiti del piano inclusi
- `maxTotalIssuances` -- limite superiore sul numero di sequenza della catena
- `delegatedPublicKey` -- la chiave pubblica Ed25519 del server on-premise (SPKI base64). La sua impronta esadecimale a 16 cifre (i primi 8 byte dello `SHA-256` calcolato sulla chiave grezza) è il `publicKeyId` registrato su ogni blob di licenza firmato da questa chiave. `publicKeyId` è sempre un'impronta di chiave reale, mai un segnaposto come `"default"`.
- `genesisHash` -- il punto di partenza della catena (continuazione dal precedente certificato, o "genesis")
- `genesisSequence` -- sequenza della catena al momento dell'emissione. Usato da `/onprem/cert-upload` per validare che il nuovo certificato si colleghi a una voce nota nel registro di emissione locale quando la catena è avanzata durante il transito. Opzionale per retrocompatibilità (trattato come 0 se assente).
- `validFrom`, `validUntil` -- finestra di validità (regolata dalla politica di validità di seguito)
- Firmato dalla chiave master Ed25519 upstream

### Come funziona la delega

1. L'amministratore aziendale genera una coppia di chiavi Ed25519 sul server on-premise.
2. L'amministratore richiede un certificato di delega dall'upstream:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. L'upstream firma il certificato con la sua chiave master e lo restituisce.
4. Il server on-premise memorizza il certificato e la sua chiave privata, pronto a firmare licenze.
5. Quando una CLI richiede una licenza dal server on-premise, il server firma con la sua chiave delegata e **include l'intero certificato di delega dentro il blob di licenza** (il campo `delegationCert`). Il certificato non viene recuperato separatamente; viaggia con ogni licenza di repository.
6. Renet esegue una **validazione a due livelli**, in questo ordine:
   - Verifica la firma del certificato rispetto alla chiave master upstream inclusa.
   - Applica la finestra di validità del certificato (`validFrom` / `validUntil`) sulle operazioni di crescita (`repo create`, `fork`, `resize`, `expand`) e sul trasferimento dei backup (`repo push`, `pull`, backup). Il livello operativo (`repo up`, `up all`, avvio automatico) salta solo la finestra, così come già salta la scadenza della licenza: i carichi di lavoro in esecuzione non si fermano mai perché un certificato è scaduto, ma un certificato scaduto non può autorizzare nulla di nuovo. La firma, il binding della chiave e ogni altro vincolo del certificato restano applicati a tutti i livelli.
   - Richiede che `fingerprint(cert.delegatedPublicKey) == blob.publicKeyId` (l'impronta esadecimale a 16 cifre della chiave), in modo che il certificato possa garantire solo le licenze firmate esattamente con la chiave a cui delega.
   - Verifica la firma del blob rispetto alla chiave delegata dal certificato.
   - Applica i vincoli del certificato: corrispondenza dell'abbonamento, corrispondenza del piano, limite di dimensione (`maxRepositorySizeGb`) e `blob.sequence <= cert.maxTotalIssuances`.
   - Applica tutte le verifiche standard della catena.

Un fallimento del certificato fallisce immediatamente con un motivo dedicato: `cert_expired` (fuori dalla finestra di validità) o `cert_invalid` (firma della chiave master non valida o un vincolo violato). Questi vengono controllati **prima** di `invalid_signature`, quindi prevale il motivo del certificato.

Il server on-premise non può:
- Contraffare una licenza al di fuori dei limiti del piano del certificato di delega (renet la rifiuta).
- Emettere più di `maxTotalIssuances` operazioni totali (renet rifiuta l'overflow della sequenza).
- Continuare a firmare licenze eseguibili oltre il `validUntil` del certificato (la finestra viene applicata anche sulle operazioni che saltano la scadenza).
- Modificare il certificato (la firma upstream si rompe).

## Politica di Validità

La finestra di validità di un certificato di delega è calcolata da un helper di politica condiviso (`computeDelegationCertValidity()`) che viene eseguito sia sul backend upstream che sul frontend del portale clienti. Gli stessi input producono sempre lo stesso `validUntil`, quindi i clienti possono visualizzare in anteprima la validità effettiva nella finestra di creazione prima di inviare.

### Valori predefiniti e limiti per piano

| Piano | Validità predefinita | Limite del piano |
|---|---|---|
| COMMUNITY | 15 giorni | 30 giorni |
| PROFESSIONAL | 60 giorni | 120 giorni |
| BUSINESS | 90 giorni | 180 giorni |
| ENTERPRISE | 120 giorni | 365 giorni |

Il valore predefinito è quello scelto dall'endpoint di creazione quando il chiamante omette `validDays`. Il limite è il massimo che il chiamante può richiedere.

### Override per abbonamento

Gli amministratori possono impostare un valore `delegationCertDefaultDays` personalizzato su un abbonamento specifico tramite la pagina di dettaglio dell'abbonamento nell'amministrazione. **L'override sostituisce sia il valore predefinito che il limite per quell'abbonamento.** È una via d'uscita per clienti speciali (ad esempio, un contratto enterprise che necessita di un certificato di 200 giorni su un piano COMMUNITY). Lo schema Zod applica comunque un intervallo assoluto di `1..365`.

### Limite rigido: fine abbonamento + 3 giorni di grazia

Indipendentemente dal limite del piano e dall'override, ogni certificato è limitato rigidamente a `subscription.expiresAt + 3 days` (il `SUBSCRIPTION_CONFIG.gracePeriodDays` esistente). Questo significa:

- Per gli abbonamenti perpetui (`expiresAt = null`), non si applica alcun limite di scadenza: solo il limite del piano.
- Per gli abbonamenti mensili fatturati da Stripe, il limite è approssimativamente la prossima data di fatturazione + 3 giorni. Quando Stripe aggiorna `expiresAt` ogni mese, il limite si sposta di conseguenza.
- Per gli abbonamenti di prova, il limite è la fine della prova + 3 giorni.

### Giorni effettivi e motivo

Ogni risposta di creazione/rinnovo include `effectiveDays` e `reason` in modo che il chiamante possa vedere esattamente perché il certificato ha ottenuto la validità che ha:

| Motivo | Significato |
|---|---|
| `plan_default` | Nessuna richiesta, nessun override: usato il valore predefinito del piano |
| `subscription_override` | Nessuna richiesta: usato l'override dell'abbonamento come valore predefinito |
| `requested` | Richiesta del chiamante soddisfatta entro tutti i limiti |
| `plan_max_clamp` | La richiesta del chiamante ha superato il limite del piano: ridotta |
| `override_max_clamp` | La richiesta del chiamante ha superato l'override dell'abbonamento: ridotta |
| `subscription_cap_clamp` | Il target altrimenti valido sopravviverebbe all'`expiresAt + 3 days` dell'abbonamento |

La finestra di creazione del portale clienti utilizza questi motivi per mostrare un'anteprima in tempo reale ("Riceverai un certificato di 18 giorni. Ridotto perché il certificato non può sopravvivere alla data di fine abbonamento di più di 3 giorni.") in modo che i clienti non inviino alla cieca.

### Soglia di rinnovo adattiva

Il ciclo di rinnovo automatico on-premise utilizza una soglia adattiva modellata su Let's Encrypt:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

Un certificato COMMUNITY di 15 giorni si rinnova con 5 giorni rimanenti. Un certificato BUSINESS di 90 giorni si rinnova con 14 giorni rimanenti (il limite configurato nell'ambiente entra in gioco). Un certificato ENTERPRISE di 120 giorni si rinnova con 14 giorni rimanenti. Questo evita che i certificati di breve durata attivino il rinnovo immediatamente, garantendo al contempo un margine confortevole per i certificati di lunga durata.

## Applicazione del Singolo Attivo

Un abbonamento può avere **al massimo un certificato di delega attivo alla volta** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Perché uno solo?

Ogni installazione on-premise applica `maxRepoLicenseIssuancesPerMonth`, `maxActivations` e l'integrita' della catena rispetto al proprio registro di emissione locale. L'on-premise non sincronizza i conteggi di utilizzo con l'upstream. Questo è il punto centrale della delega con capacita' offline.

Se un abbonamento avesse più certificati attivi (uno per installazione), ogni installazione applicherebbe il limite in modo indipendente:

- Un abbonamento da 500/mese con 3 certificati attivi consente fino a **1.500 emissioni/mese** in pratica.
- Tre catene parallele, ciascuna ancorata al genesis, senza possibile riconciliazione dell'audit.

L'upstream non può rilevare questo aggiramento perché gli on-prem sono progettati per operare offline. **Il singolo attivo è l'unico modello applicabile.** I clienti con più installazioni (produzione + staging + DR) devono acquistare un abbonamento per installazione.

### Comportamento in caso di collisione

`POST /admin/delegation-certs` e `POST /portal/delegation-certs` rifiutano una seconda creazione con:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

Il portale clienti mostra questo con una finestra dedicata che spiega le conseguenze:

- **Rinnova (consigliato)** - estende la catena esistente. Tutte le licenze di repository emesse in precedenza continuano a funzionare.
- **Revoca e Crea** - scarta la catena esistente e ricomincia dal genesis. Le licenze di repository emesse in precedenza diventano inverificabili una volta passata la `validUntil` del VECCHIO certificato. Usa questa opzione solo quando hai migrato a un nuovo on-prem con una chiave di firma diversa, o stai recuperando da una chiave compromessa.

`renew()` è lo swap atomico che preserva il singolo attivo e **non** è soggetto al controllo di collisione 409.

### Limite di frequenza

Anche con il singolo attivo, un chiamante malintenzionato potrebbe eseguire un ciclo `revoca -> crea -> revoca -> crea` per consumare i cicli di firma della chiave master upstream. Entrambi gli endpoint di creazione limitano a **10 tentativi per 24 ore rotanti** per abbonamento tramite la tabella `rateLimits` esistente:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

Il contatore si incrementa a ogni tentativo indipendentemente dall'esito (anche i cicli di spam da collisione sono limitati).

## Rilevamento dei Fork

Se un cliente condivide il proprio certificato di delega con un'altra parte (o esegue due server on-premise dallo stesso certificato), le catene divergono. L'upstream lo rileva al momento del rinnovo.

### Flusso di rinnovo

1. L'amministratore on-premise chiama `POST /admin/delegation-certs/renew` con la testa corrente della catena:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. L'upstream percorre le voci della catena rispetto al proprio registro.
3. Se `currentChainHash` non corrisponde alla catena registrata dall'upstream a `currentSequence`, fork rilevato:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. Il `genesisHash` del nuovo certificato viene impostato all'hash corrente della catena, in modo che le macchine con il vecchio stato della catena possano continuare da dove si erano fermate.

Se il certificato viene condiviso con un non-cliente:
- Possono usarlo durante il periodo di validità del certificato.
- Al primo rinnovo, l'upstream vede solo una catena (quella legittima).
- Il `genesisHash` del nuovo certificato corrisponde solo alla catena legittima.
- Le macchine sulla catena condivisa rifiuteranno immediatamente le nuove licenze perché il loro `chainHash` memorizzato non si collega al `genesisHash` del nuovo certificato.

## Rinnovo Air-Gapped

Per le installazioni on-premise senza accesso HTTPS in uscita verso l'upstream, il flusso di rinnovo è completamente offline. Ci sono tre nuovi endpoint che chiudono il ciclo:

**Sull'on-premise (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - scarica il certificato firmato attualmente caricato (backup, audit, re-import)
- `GET /onprem/renewal-request` - genera un manifest firmato contenente la testa della catena locale + la chiave pubblica delegata, firmato dalla chiave privata on-premise

**Sull'upstream (admin o portale con ambito org):**
- `POST /admin/delegation-certs/process-renewal-request` (root di sistema cross-cliente)
- `POST /portal/delegation-certs/process-renewal-request` (proprietario/admin dell'org)

### Manifest della richiesta di rinnovo

La richiesta di rinnovo è un piccolo documento JSON:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

La firma viene calcolata sulla codifica canonica del manifest (chiavi ordinate alfabeticamente, poi `JSON.stringify`) usando la chiave privata on-premise. Questo garantisce che entrambe le parti calcolino byte identici indipendentemente dall'ordine di costruzione dell'oggetto.

### Verifica all'upstream

`processRenewalManifest()` esegue cinque verifiche:

1. **Il certificato attivo esiste** per l'abbonamento del manifest. Restituisce `404 NO_ACTIVE_CERT` altrimenti: il cliente dovrebbe usare il flusso di creazione, non il rinnovo.
2. **La chiave pubblica delegata corrisponde** al certificato attivo. Restituisce `400 DELEGATED_KEY_MISMATCH` altrimenti: protegge dal replay da un on-prem diverso.
3. **La firma del manifest viene verificata** rispetto alla `delegatedPublicKey` del certificato attivo. Restituisce `400 MANIFEST_SIGNATURE_INVALID` altrimenti: dimostra che il manifest proviene da un detentore della chiave privata on-premise.
4. **L'età del manifest** è entro 7 giorni (`RENEWAL_MANIFEST_MAX_AGE_MS`). Restituisce `400 MANIFEST_EXPIRED` altrimenti: ancoraggio anti-replay.
5. **Il collegamento dell'hash della catena** a `currentSequence` del manifest corrisponde al registro dell'upstream. Restituisce `409 CHAIN_FORK_DETECTED` altrimenti: protegge da catene biforcate.

Se tutte le verifiche passano, `processRenewalManifest` chiama il flusso `renew()` esistente, che fa scadere atomicamente il vecchio certificato e ne inserisce uno nuovo. **Non è soggetto al 409 del singolo attivo lato creazione** perché è uno swap atomico, non un revoca+crea in 2 passi.

### Avanzamento della sequenza durante il transito

Un manifest di richiesta di rinnovo cattura la testa della catena nel momento della generazione. Mentre il manifest è in transito (consegna USB, email cifrata), l'on-premise può continuare a emettere licenze di repository, avanzando la sua catena locale.

Quando il nuovo certificato viene caricato sull'on-premise, `/onprem/cert-upload` valida che il `genesisSequence` del nuovo certificato si colleghi ancora a una voce nota nel registro di emissione locale:

- Se `cert.genesisSequence > localHead.sequence` restituisce `409 CHAIN_HEAD_BEHIND` (l'upstream è su una catena biforcata).
- Se `cert.genesisSequence > 0` e la voce del registro locale a quella sequenza ha un `chainHash` diverso da `cert.genesisHash` restituisce `409 CHAIN_FORK_ON_UPLOAD` (la catena locale è divergita).
- Altrimenti, il certificato viene accettato. Le future emissioni continuano da `localHead.sequence + 1`.

Ciò significa che **non è necessario alcun blocco delle scritture durante il transito**. La catena si estende naturalmente su entrambi i lati. Corrisponde a come il rinnovo del certificato X.509 gestisce i numeri seriali in volo.

## Audit Periodico

L'upstream fornisce un endpoint di audit per verificare l'integrità della catena senza rinnovare il certificato:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

L'upstream percorre le voci e restituisce `{ valid: true }` o `{ valid: false, divergedAtSequence: N, expected, actual }`.

I server on-premise dovrebbero chiamare questo endpoint periodicamente (impostazione predefinita: settimanalmente tramite la variabile d'ambiente `UPSTREAM_AUDIT_URL`) per rilevare i fork in anticipo.

### Prove di audit lato macchina

Renet può verificare la continuità della catena localmente usando `VerifyAuditProof`. Quando una macchina rinnova la sua licenza dopo un lungo intervallo, il server può restituire le voci intermedie della catena come prova. La macchina percorre la prova per verificare che ogni `chainHash` derivi dal precedente `prevHash + blobHash` tramite SHA-256, rilevando qualsiasi manomissione senza contattare l'upstream.

## Sicurezza della Concorrenza

D1 (il database di Cloudflare) non supporta transazioni interattive. L'emissione concorrente di licenze per lo stesso abbonamento potrebbe collidere sul numero di sequenza. Il server account gestisce questo:

1. Legge la sequenza successiva + l'hash della catena precedente.
2. Costruisce e firma il blob con quella sequenza inclusa.
3. Inserisce la voce del registro con `onConflictDoNothing`.
4. Se l'inserimento restituisce 0 righe modificate, la sequenza è stata acquisita da un'altra richiesta: ri-acquisisce la sequenza, ri-costruisce, **ri-firma** e riprova.
5. Dopo 10 tentativi falliti, fallisce con un errore.

Il dettaglio critico: il retry **ri-firma** il blob. Un retry ingenuo che aggiornasse solo la voce del registro lascerebbe il blob firmato con un numero di sequenza obsoleto, rompendo la catena.

## Trasporto Email

Il server account può inviare email transazionali (magic link, reset password, notifiche di sicurezza) tramite due trasporti collegabili:

| Trasporto | Configurazione |
|---|---|
| `ses` (predefinito) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Entrambi i trasporti funzionano per i deployment cloud e on-premise. Scegli quello più adatto alla tua infrastruttura: AWS SES con il tuo account AWS, o qualsiasi server SMTP (Microsoft Exchange, Postfix, SendGrid, Mailgun, ecc.).

Il trasporto viene selezionato all'avvio tramite la variabile d'ambiente `EMAIL_TRANSPORT`. SMTP utilizza il connection pooling e il lazy loading, quindi la libreria client SMTP viene inizializzata solo se SMTP è selezionato.

Tutti i template email e l'API email pubblica sono identici tra i trasporti.

## Documentazione Correlata

- [Installazione On-Premise](/it/docs/on-premise) -- come distribuire il server on-premise
- [Abbonamento e Licenze](/it/docs/subscription-licensing) -- limiti del piano e slot macchina
- [Canali di Rilascio](/it/docs/release-channels) -- canali edge vs stable
- [Regioni dei Dati](/it/docs/data-regions) -- residenza dei dati regionale
