---
title: "Installazione On-Premise"
description: "Esecuzione del server account e distribuzione della CLI sulla propria infrastruttura."
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: it
sourceHash: "6b60637180f58cc2"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Rediacc può funzionare interamente sulla propria infrastruttura. L'immagine Docker standalone include il server account, il portale web, il sito di marketing e l'endpoint di distribuzione della CLI. Non è richiesta alcuna dipendenza esterna dai servizi ospitati da Rediacc.

## Installare con rdc

`rdc server install` installa il server degli account come repository su una macchina raggiungibile dalla CLI via SSH. Un solo comando copre il controllo della macchina, la configurazione di renet, il DNS, il TLS, la generazione delle chiavi, la licenza, l'avvio e l'account del proprietario. Ogni valore ha il suo flag. In un terminale il valore mancante viene chiesto; con `--yes` non si chiede nulla e un valore mancante viene rifiutato. Ogni passaggio viene registrato, quindi una nuova esecuzione salta ciò che è già fatto.

I passaggi, in ordine: `preflight` (sudo senza password, architettura, porte 80 e 443, spazio su disco, scarto dell'orologio), `setup` (`rdc machine setup`, solo se manca renet), `dns`, `tls`, `repo`, `keys`, `licence`, `image`, `up` e `owner`.

### Prima le macchine esistenti

L'installazione punta a una macchina già esistente: un server in un data center o un dispositivo della LAN. Una macchina configurata si indica come argomento. Una macchina non ancora registrata si aggiunge con il suo indirizzo:

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` e `--name` impostano la porta SSH e il nome con cui la macchina viene registrata. Una VM cloud si crea prima con `rdc machine provision`; l'installazione non ne crea mai una.

### DNS

L'installazione stampa i record A e AAAA per il dominio del server e per quello del suo archivio di backup (`--store-domain`, per impostazione predefinita `<nome>-store.<resto del dominio>`), poi attende che entrambi risolvano verso la macchina. Nessun record viene mai scritto in una zona. `--no-dns-wait` stampa i record e prosegue, utile per un nome di LAN servito da un resolver locale.

### TLS

`--tls` sceglie uno dei tre metodi:

| Metodo | Requisiti | Note |
|---|---|---|
| `letsencrypt` | Porte 80 e 443 raggiungibili da internet | Challenge HTTP-01. `--cert-email` riceve gli avvisi di scadenza; per impostazione predefinita, il proprietario. |
| `cloudflare` | `--cf-token` | Challenge DNS-01 tramite un token API di Cloudflare. |
| `byo` | `--tls-cert` e `--tls-key` | Un certificato PEM esistente che copra entrambi i domini. `--tls-ca` indica la CA di cui si fida il controllo di integrità. |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### Immagine

Il passaggio dell'immagine scarica per impostazione predefinita `ghcr.io/rediacc/server:latest` sulla macchina. `--image` sceglie un altro riferimento. `--image-file` invia un tar prodotto da `docker save`, e `--local-image` salva l'`--image` dal Docker locale e la invia. Entrambi evitano qualsiasi accesso a un registry dalla macchina.

### Licenza e piano gratuito

`--licence auto` (il valore predefinito) usa un certificato di delega dell'account collegato, oppure parte con il piano gratuito se non ce n'è. `--licence free` parte sempre con il piano gratuito. Un account che ha effettuato l'accesso prima dell'esistenza del comando di installazione deve rieseguire `rdc subscription login` per avere lo scope giusto.

Per una macchina senza accesso al server degli account, `--cert <file>` accetta un certificato di delega ottenuto altrove. Il certificato deve indicare la chiave generata sulla macchina, quindi l'ordine abituale è prima un'installazione con il piano gratuito, poi il certificato:

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence` porta un server dal piano gratuito a un certificato dell'account collegato o di `--cert`. Il passaggio 3 della sezione sulle licenze, più sotto, descrive cosa verifica il server.

### Pacchetto di ripristino

Tutte le chiavi vengono generate sulla macchina e scritte solo nel `secrets.env` del repository. In un terminale l'installazione termina stampando una sola volta un pacchetto di ripristino: la coppia di chiavi delegata, la chiave del server di configurazione dell'account e le credenziali dell'archivio di oggetti. Il pacchetto non viene mai registrato nei log né incluso in `--output json`. Senza terminale non viene stampato, e la riga finale cita `rdc server backup`.

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` scrive il file con modo 0600; senza di esso il pacchetto va su stdout. `--bws-project <id>` durante l'installazione copia le chiavi anche in un progetto Bitwarden Secrets Manager, e `--rotate` sostituisce un valore memorizzato che differisce. Senza `--bws-project`, le chiavi lasciano il server solo nel pacchetto di ripristino che l'installazione stampa e nel file scritto da `rdc server backup --out`.

### Stato

```bash
rdc server status accounts.example.com
```

Lo stato mostra integrità, piano, certificato e immagine del server. `--machine` e `--repo` indicano il bersaglio quando il dispositivo non ha un record di installazione per il dominio.

### Aggiornamenti

| Componente | Comando |
|---|---|
| CLI | `rdc update` |
| renet sulla macchina | `rdc machine setup <machine>` |
| Immagine e modello del server | `rdc server upgrade <domain>` |

`rdc server upgrade` esegue un fork del repository come punto di ripristino, posiziona la nuova immagine, riapplica il modello quando quello integrato è più recente e riavvia. Accetta `--image`, `--image-file` e `--local-image` come l'installazione, così una macchina isolata si aggiorna da un tar di immagine salvato.

## Immagine Docker

Scarica l'immagine standalone:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Avvia con le impostazioni predefinite:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

L'immagine serve:
- API account su `/account/api/v1/`
- Portale web su `/account/`
- Sito di marketing su `/`
- Artefatti CLI su `/releases/`
- Binari renet su `/bin/`

## Installazione della CLI dal Proprio Server

Installa la CLI direttamente dal tuo server on-premise. Lo script di installazione rileva automaticamente il canale di aggiornamento e configura la CLI per controllare gli aggiornamenti sul tuo server.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Questo singolo comando:
1. Scarica il binario della CLI dall'endpoint `/releases/` del tuo server
2. Interroga `/account/api/v1/.well-known/server-info` per scoprire il canale di aggiornamento
3. Scrive la configurazione predefinita (`rediacc.json`) con l'URL del tuo server, il canale di aggiornamento e le chiavi di cifratura sotto i suoi campi `account.*`
4. Configura `rdc update` per controllare gli aggiornamenti futuri sul tuo server

La variabile `REDIACC_CHANNEL` non è necessaria. Lo script di installazione legge il canale dalla configurazione del server automaticamente.

## Configurazione della CLI con Config Nominati

Se ti connetti a più server (on-premise, produzione, edge), i config nominati mantengono ogni ambiente isolato:

```bash
# Crea un config per il tuo server on-premise
rdc config init myserver --server https://account.example.com

# Accedi usando quel config
rdc --config myserver subscription login

# Tutti i comandi con --config usano il server on-premise
rdc --config myserver machine status prod-1
```

Ogni config nominato memorizza il proprio URL del server account (sotto `account.*`) e il proprio token API dell'account, conservato accanto al config in `api-token-<name>.json`. Cambiare config cambia l'intero contesto del server.

## Ambienti Air-Gapped

Per ambienti senza accesso a Internet, imposta sia l'URL del server che un URL di releases personalizzato:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

La CLI verificherà `account.example.com/releases/cli/stable/manifest.json` per gli aggiornamenti invece del CDN pubblico.

Se il server è completamente offline, installa la CLI tramite npm dal tarball incluso:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Riferimento Variabili d'Ambiente

| Variabile | Usata da | Scopo |
|---|---|---|
| `REDIACC_SERVER_URL` | Script di installazione | URL del server account. Rileva automaticamente il canale e le chiavi di cifratura. |
| `REDIACC_RELEASES_URL` | Script di installazione, updater CLI | Endpoint releases personalizzato per i binari CLI. Predefinito: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Script di installazione | Override del canale di aggiornamento. Rilevato automaticamente dal server se non impostato. |
| `REDIACC_ACCOUNT_SERVER` | Runtime CLI | Override dell'URL del server account per tutti i comandi CLI. |
| `REDIACC_UPDATE_CHANNEL` | Runtime CLI | Override del canale di aggiornamento per `rdc update`. |

## Configurazione del Server

L'immagine Docker on-premise utilizza la stessa variabile `ENVIRONMENT` del servizio ospitato. Impostala nel tuo ambiente Docker o nella configurazione di orchestrazione:

- `ENVIRONMENT=production` (predefinito): limiti di risorse standard; le CLI che si connettono a questo server usano per default il canale di aggiornamento **stable**. Il nome del valore `production` è un identificatore di deploy legacy. Entrambe le modalità `production` ed `edge` sono di qualità produzione.
- `ENVIRONMENT=edge`: limiti Community 2X; le CLI usano per default il canale di aggiornamento **edge**

Vedi [Canali di Rilascio](/it/docs/release-channels) per i dettagli su cosa fornisce ciascun ambiente.

## Cosa il Server Comunica alla CLI

Quando la CLI si connette al tuo server, interroga `/.well-known/server-info` per scoprire:

- **Chiave pubblica di cifratura E2E**: per la memorizzazione di config a conoscenza zero
- **Versione minima della CLI**: blocca le CLI obsolete dalla connessione
- **Canale di aggiornamento**: indica alla CLI quale canale di rilascio usare per gli aggiornamenti
- **Ambiente**: quale profilo di deploy esegue il server (limiti standard vs. edge con limiti 2X)

Questa auto-configurazione significa che hai bisogno solo dell'URL del server. Tutto il resto viene scoperto automaticamente.

## Licenza per Deployment Air-Gapped

I server on-premise air-gapped e self-hosted emettono licenze localmente usando un **certificato di delega** firmato dalla chiave master upstream. Il certificato vincola il server on-premise ai limiti del suo piano e crea una catena a prova di manomissione. Vedi [License Chain & Delegation](/it/docs/license-chain) per il design crittografico (integrità della catena, rilevamento fork, prove di audit).

Questa sezione copre la configurazione operativa: generazione delle chiavi, richiesta del certificato, configurazione del rinnovo automatico e il flusso di rinnovo offline (air-gapped).

### Una sottoscrizione, un'installazione on-premise

Una sottoscrizione può avere **al massimo un certificato di delega attivo alla volta**. Ogni installazione on-premise impone limiti mensili e per macchina rispetto al proprio registro di emissione locale, quindi più certificati attivi moltiplicherebbero la quota effettiva senza possibilità di riconciliazione.

Se hai bisogno di ambienti separati (produzione, staging, DR, multi-regione), acquista una sottoscrizione per installazione. L'applicazione single-active codifica questo contratto: un tentativo di creare un secondo certificato attivo restituisce `409 DELEGATION_CERT_ALREADY_ACTIVE` con l'id del certificato esistente e le istruzioni per rinnovare (preferito, preserva la catena) o revocare-e-creare (reimposta la catena).

### 1. Genera la coppia di chiavi Ed25519 on-premise

Il server on-premise usa una coppia di chiavi Ed25519 separata per firmare le licenze. Il certificato di delega upstream autorizza questa specifica chiave pubblica.

```bash
# Genera una nuova coppia di chiavi
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Converti in base64 (il formato atteso dall'on-premise nelle variabili d'ambiente)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Memorizza la chiave privata insieme agli altri segreti (ad esempio, un Docker secret o un Kubernetes Secret). Non lascia mai il server on-premise.

### 2. Richiedi un certificato di delega dall'upstream

Puoi richiedere il certificato dal portale account upstream in tre modi:

**Opzione A: Self-service del cliente (consigliato).** Accedi al portale upstream come proprietario o amministratore dell'organizzazione e vai su **/account/delegation-certs**. Fai clic su **Create New**, incolla la chiave pubblica on-premise (SPKI base64), scegli una validita (o accetta il valore predefinito del piano) e scarica il file `.json` risultante.

**Opzione B: Admin (cross-customer).** Il supporto Rediacc o l'amministratore di sistema upstream può chiamare `POST /admin/delegation-certs` con gli stessi parametri.

**Opzione C: CLI `rdc` (pianificato).** Un futuro comando CLI integrera il flusso del portale.

Il `.json` restituito appare come:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

La validità del certificato è disciplinata dalla politica di validità (valori predefiniti e limiti massimi per piano, override per sottoscrizione, limitata alla fine della sottoscrizione + 3 giorni di grazia). La risposta include anche `effectiveDays` e `reason` per capire perché è stato scelto quel valore. Vedi [License Chain - Validity Policy](/it/docs/license-chain) per le regole complete.

### 3. Installa il certificato sul server on-premise

Il server legge il suo certificato di delega da un unico file sul volume dei dati, `/data/delegation-cert.json` (`DELEGATION_CERT_PATH` lo indica). Nessuna variabile d'ambiente contiene il certificato stesso. `rdc server install` vi deposita il certificato scaricato e `rdc server licence` lo sostituisce in seguito:

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

Entrambi i comandi consegnano il certificato al server in esecuzione tramite la sua casella dei certificati (`data/web/cert-inbox/new.json`). Il server lo verifica e risponde con `applied.json` o `rejected.json`, e il comando conferma l'id del nuovo certificato con `rdc server status` (gli stessi dati di `cert-status` del passaggio 6). `rdc server upgrade` usa la stessa casella. Il server non legge più `DELEGATION_CERT_BASE64`: un passaggio dell'aggiornamento sposta un valore rimasto in `secrets.env` nella casella, così una macchina installata prima dell'esistenza della casella conserva il suo certificato.

Il server carica il certificato all'avvio e lo confronta con la chiave con cui firma le licenze: l'impronta della chiave di firma deve coincidere con quella del `delegatedPublicKey` del certificato, perché le licenze firmate con una chiave non autorizzata dal certificato non sarebbero validabili su nessuna macchina. Mantieni sincronizzati la coppia di chiavi di firma e il `delegatedPublicKey` del certificato.

Un certificato che il server rifiuta all'avvio (firma non valida, chiave sbagliata, `UPSTREAM_PUBLIC_KEY` mancante o file malformato) non lo ferma. Il server parte con il livello gratuito e sposta il file difettoso in `delegation-cert.rejected.json`, accanto all'originale. La firma delle licenze dei repo risponde `503 DELEGATION_CERT_REFUSED` finché non c'è un certificato valido, e `rdc server status` mostra `cert REFUSED (reason)`. Esegui `rdc server licence` con un certificato valido per ripristinare. Un certificato scaduto viene comunque caricato: si degrada in modo morbido invece di essere rifiutato.

### 4. Configura la verifica upstream e il rinnovo automatico (opzionale ma consigliato)

Se il tuo on-premise ha accesso HTTPS in uscita all'upstream, configura il rinnovo automatico in modo che il certificato si aggiorni prima della scadenza senza intervento manuale:

```bash
# Richiesto per /onprem/cert-upload per verificare i certificati caricati rispetto alla chiave master upstream.
# Fallisce velocemente all'avvio se UPSTREAM_API_KEY è impostato senza questo.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# Richiesto per il loop di rinnovo automatico. Genera tramite il portale:
#   Proprietario/admin org → /account/delegation-certs → "Get auto-renew token"
# Questo è l'UNICO modo per ottenere un token api con scope delegation:renew.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Tuning opzionale (valori predefiniti mostrati).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

Il loop di rinnovo automatico on-premise viene eseguito una volta all'avvio e poi all'intervallo configurato. Usa una **soglia adattiva** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) in modo che un certificato COMMUNITY da 15 giorni si rinnovi a 5 giorni rimanenti invece di avviare il rinnovo il primo giorno. Un certificato BUSINESS da 90 giorni si rinnova a 14 giorni rimanenti (il limite configurato nell'ambiente).

Se il rinnovo fallisce, il certificato rimane in uso fino alla scadenza naturale. Il fallimento ha un backoff di 1 ora e viene registrato in `${DELEGATION_CERT_PATH}.status.json` ed esposto tramite `GET /onprem/cert-status`.

### 5. Rinnovo air-gapped (senza HTTPS in uscita)

Se il tuo on-premise non riesce a raggiungere l'upstream, usa il flusso di trasferimento manuale:

1. **Scarica una richiesta di rinnovo dal portale admin on-premise.** Come root del sistema on-premise, effettua una richiesta `GET /onprem/renewal-request`. Restituisce un manifesto JSON contenente la testa della catena locale, la chiave pubblica delegata e una firma Ed25519 a prova di manomissione dalla chiave privata on-premise.
2. **Trasferisci il manifesto all'upstream** tramite USB, email cifrata o qualsiasi canale fuori banda. Il manifesto è piccolo (pochi KB) e non contiene segreti.
3. **Processa il manifesto all'upstream.** Il proprietario/admin dell'organizzazione apre **/account/delegation-certs** -> **Upload renewal request** -> seleziona il file del manifesto. L'upstream verifica la firma del manifesto rispetto alla `delegatedPublicKey` del certificato attivo (dimostrando che proviene da un detentore della chiave privata on-premise), controlla l'anti-replay (i manifesti più vecchi di 7 giorni vengono rifiutati) e poi emette un nuovo certificato.
4. **Scarica il nuovo certificato** dal portale upstream come file `.json`.
5. **Trasferisci il certificato** all'on-premise.
6. **Carica sull'on-premise** tramite il portale admin locale (`POST /onprem/cert-upload`). L'on-premise verifica il nuovo certificato rispetto a `UPSTREAM_PUBLIC_KEY` e convalida che il `genesisSequence` del certificato sia ancora collegato a una voce della catena nel registro di emissione locale (l'avanzamento della sequenza durante il transito è supportato - la catena si estende naturalmente).

Questo intero flusso non richiede mai uscita di rete dall'on-premise.

#### Modalità di errore del manifesto

| Codice | Causa | Correzione |
|---|---|---|
| `NO_ACTIVE_CERT` | L'upstream non ha un certificato attivo per questa sottoscrizione | Emetti un nuovo certificato tramite il flusso di creazione invece di rinnovare |
| `DELEGATED_KEY_MISMATCH` | La `delegatedPublicKey` del manifesto differisce dal certificato attivo | Il manifesto potrebbe essere un replay di un'installazione on-premise diversa |
| `MANIFEST_SIGNATURE_INVALID` | La firma non si verifica rispetto alla chiave pubblica delegata | Il manifesto è stato manomesso in transito, o è stato generato su un on-premise diverso |
| `MANIFEST_EXPIRED` | Il manifesto ha più di 7 giorni | Genera una nuova richiesta di rinnovo dall'on-premise |

#### Modalità di errore del caricamento del certificato

`POST /onprem/cert-upload` risponde `{uploaded: true, bootstrap, certId}` in caso di successo. Un certificato rifiutato restituisce `{error, code}`: `error` contiene il dettaglio e `code` è uno dei motivi della tabella. Ogni certificato applicato o rifiutato viene registrato nel log e inviato via e-mail al proprietario della macchina.

`rdc server licence` deposita il certificato via SSH nella casella di ingresso della macchina (`data/web/cert-inbox`) e rilegge `applied.json` o `rejected.json`. Poi conferma il nuovo id del certificato tramite `cert-status`. Un rifiuto riporta gli stessi motivi, più `not-a-regular-file` e `too-large`, generati dalla casella stessa.

| Codice | HTTP | Causa |
|---|---|---|
| `malformed` | 400 | Il file caricato non è un certificato valido |
| `bad-signature` | 400 | Il certificato non è firmato con la `UPSTREAM_PUBLIC_KEY` configurata |
| `wrong-key` | 400 | Il certificato è stato emesso per una chiave diversa da quella di questa installazione on-premise |
| `expired` | 400 | Il certificato ha già superato il proprio `validUntil` |
| `not-newer` | 409 | Il certificato non è più recente di quello in vigore |
| `other-subscription` | 409 | Il certificato appartiene a un'altra sottoscrizione |
| `chain-ahead` | 409 | Il `genesisSequence` del certificato è in anticipo rispetto alla testa della catena locale |
| `chain-fork` | 409 | L'hash della catena al `genesisSequence` del certificato non corrisponde al registro locale |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY` non è configurata |
| `write-failed` | 500 | Non è stato possibile scrivere il certificato su disco |
| `adoption-failed` | 500 | Il server non è riuscito a caricare il certificato scritto |

Per `bad-signature`, verifica che `UPSTREAM_PUBLIC_KEY` corrisponda alla chiave pubblica master upstream. Per `no-upstream-key`, imposta `UPSTREAM_PUBLIC_KEY`.

### 6. Stato e monitoraggio

Interroga lo stato del certificato locale on-premise in qualsiasi momento:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Restituisce il `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` del certificato caricato, oltre al blocco `autoRenew` (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Integra questo nel tuo stack di monitoraggio per avvisarti su `lastSuccessAt` non aggiornato o `lastError` non nullo.

Per backup e audit, l'admin on-premise può anche scaricare il certificato firmato attualmente caricato tramite `GET /onprem/cert-current` (richiede sessione elevata).

### Riferimento variabili d'ambiente del certificato di delega

| Variabile | Richiesta? | Scopo |
|---|---|---|
| `ON_PREMISE_MODE` | Sì | Imposta a `true` per abilitare il sottoinsieme di route on-premise |
| `ON_PREMISE_PRIVATE_KEY` | Sì | Chiave privata Ed25519 PKCS8 base64 per la firma delegata |
| `ON_PREMISE_PUBLIC_KEY` | Sì | Chiave pubblica Ed25519 SPKI base64 (deve corrispondere alla `delegatedPublicKey` del certificato) |
| `DELEGATION_CERT_PATH` | Opzionale | Percorso del filesystem al JSON del certificato firmato. Predefinito `/data/delegation-cert.json` sul volume dei dati. Sostituisci il certificato con `rdc server licence`, non a mano. |
| `UPSTREAM_PUBLIC_KEY` | Richiesta se `UPSTREAM_API_KEY` è impostato, o per il funzionamento di `/onprem/cert-upload` | SPKI base64 della chiave pubblica master upstream. Senza di essa il server rifiuta ogni certificato all'avvio (`no-upstream-key`) e funziona con il piano gratuito, come descrive il passaggio 3. |
| `UPSTREAM_URL` | Per il rinnovo automatico | URL base del server account upstream, es. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Per il rinnovo automatico | Un token api con scope `delegation:renew`. Genera tramite il portale - vedi Passo 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Opzionale | Predefinito 24. Con quale frequenza verificare se il certificato necessita di rinnovo. |
| `RENEW_THRESHOLD_DAYS` | Opzionale | Predefinito 14. Funge da limite massimo sulla soglia adattiva di 1/3 della validità. |

### Riepilogo del modello di minaccia

Il modello del certificato di delega difende da:

- **Licenze contraffatte**: l'on-premise può firmare solo entro i limiti del suo piano; renet rifiuta qualsiasi cosa al di fuori dei limiti del certificato.
- **Condivisione del certificato tra deployment**: la divergenza della catena viene rilevata al rinnovo (restituisce `CHAIN_FORK_DETECTED`).
- **Bypass della quota tramite multi-install**: applicato dall'upstream tramite single-active (un certificato per sottoscrizione).
- **Rollback della catena**: renet memorizza la sequenza più alta vista per sottoscrizione e rifiuta qualsiasi blob con una sequenza inferiore.
- **Credenziali upstream compromesse**: il token di bootstrap `delegation:renew` è generabile solo tramite l'endpoint del portale dedicato ed è amministrato. Il token concede solo il rinnovo - non può leggere o modificare nessun'altra risorsa.
- **Attacchi replay sui manifesti**: i manifesti più vecchi di 7 giorni vengono rifiutati.

Da cosa **non** difende:

- **Chiave privata on-premise compromessa**: una chiave privata trapelata consente a un attaccante di firmare licenze fino al `validUntil` del certificato. Mitigazione: ruota la coppia di chiavi (revoca il vecchio certificato + crea uno nuovo con una nuova chiave) e tratta tutte le licenze firmate dalla vecchia chiave come sospette.
- **Chiave master upstream compromessa**: questa è la radice di fiducia. Le procedure di rotazione esulano dall'ambito di questo documento.
