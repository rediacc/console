---
title: "Destinazioni di backup"
description: "Invia ogni strategia di backup a più di uno store, ripristina dallo store che contiene lo snapshot migliore e leggi una riga di stato per destinazione."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: it
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Destinazioni di backup

Una strategia di backup può scrivere in più di uno store. Ogni destinazione è un punto di ripristino a sé: ha il proprio snapshot, il proprio commit e la propria riga di stato, quindi uno store che fallisce non rovina gli altri.

Tutti gli store appartengono a un solo account. Una config, una licenza e una fattura li coprono tutti. Una macchina con l'accesso effettuato a due account continua a essere rifiutata, perché più destinazioni significano più store all'interno di un account.

## Store

Uno store è un bucket in cui il server degli account scrive per conto della macchina. Ogni abbonamento ne ha uno fin dal primo giorno, chiamato `home`: lo store ospitato che i comandi di backup hanno sempre usato. Una destinazione che non indica uno store scrive in `home`.

Oltre a questo si possono registrare due tipi.

| Tipo | Cos'è | Cosa richiede la registrazione |
|------|-------|--------------------------------|
| `hosted-r2` | Una seconda regione ospitata, scelta tra quelle offerte dal deployment | Un id e la regione. Nessuna credenziale |
| `customer-s3` | Un bucket gestito dal cliente, su S3, RustFS o qualsiasi servizio compatibile con S3 | Un id, l'endpoint HTTPS, il bucket, la regione di firma (predefinita `us-east-1`), un endpoint pubblico facoltativo e una coppia di chiavi di accesso |

Una macchina non detiene mai le chiavi di un bucket del cliente. Le chiavi restano sigillate sul server degli account, e la macchina riceve URL prefirmati di breve durata per l'unico store indicato dalla sua sessione.

### Registrare uno store

La registrazione è una chiamata all'API dell'account, non un comando `rdc`. `POST /backups/stores` registra uno store, `GET /backups/stores` elenca quelli registrati e `DELETE /backups/stores/<id>` ne ritira uno. Registrare, ruotare e ritirare richiedono un token API con lo scope `backup:manage` creato da un owner o un admin attuale dell'organizzazione, e ogni operazione viene sottoposta ad audit. L'elenco richiede `backup:read`.

Il server controlla uno store prima di accettarlo.

- **Sonda di conformità.** Il server esegue gli stessi controlli che uno store ospitato supera. Uno store che non impone i checksum viene rifiutato alla registrazione, invece di scoprirlo al primo backup.
- **Sonda di eliminazione.** La sonda prova anche a eliminare. Se lo store rifiuta, viene registrato con la pulizia disattivata (vedi sotto).
- **Regole sugli endpoint.** Solo HTTPS, porta 443 e nessun endpoint su una rete interna.
- **Limite di store.** Il numero di store per abbonamento dipende dal piano, `home` incluso e gli store ritirati esclusi.

| Piano | Store |
|-------|-------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Registrare un id già esistente ruota soltanto le sue credenziali, e la sonda viene eseguita di nuovo. Uno store le cui credenziali smettono di funzionare viene contrassegnato come sospeso dalla prima concessione rifiutata. `GET /backups/stores` mostra l'endpoint, il bucket e gli ultimi caratteri dell'id della chiave, mai un segreto.

Uno store non può essere ritirato finché una destinazione attiva lo indica ancora, e `home` non può essere ritirato.

## Indicare lo store di una destinazione

Una destinazione indica il proprio store con `--target`, da usare insieme a `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Opzione | Descrizione |
|---------|-------------|
| `--destination <name>` | La destinazione da creare o modificare |
| `--target <storeId>` | Id dello store registrato in cui scrive la destinazione (predefinito `home`). Richiede `--destination` |

Due destinazioni attive della stessa strategia non possono indicare lo stesso store, e uno store non registrato viene rifiutato mostrando l'elenco degli id registrati.

Ogni esecuzione pianificata crea uno snapshot per destinazione attiva, nell'ordine in cui le destinazioni sono state dichiarate, ciascuna con il proprio limite di banda. Ogni snapshot è un reflink copy-on-write nuovo, quindi ognuno è un punto nel tempo coerente di per sé. Una destinazione che fallisce non fa saltare la successiva. L'unità termina comunque con un codice diverso da zero quando una destinazione è fallita, così systemd e il controllo delle esecuzioni mancate vedono l'errore.

## Ripristinare da uno store

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` e `rdc backup download --store` accettano `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Senza `--from`, la CLI chiede al server degli account quali store contengono la discendenza del repository, ordinati con per primo lo store il cui snapshot più recente ha superato l'ultima verifica, e li prova in quell'ordine. Uno store senza snapshot viene saltato. Se la classifica non può essere letta, il ripristino usa `home` e lo segnala.

Senza `--from`, `backup restore`, `restore --path`, `browse --at` e `download --store` partono dal primo store di quella classifica e passano al successivo quando il guasto dipende dallo store: un errore del server, una concessione o una sessione rifiutata, o un endpoint che non risponde. Ciascuno indica quale store lo ha servito. Nessuno ripiega su un altro store per un difetto dello snapshot stesso. Uno snapshot mancante, scaduto o corrotto appare uguale in ogni store, quindi viene mostrato l'errore. Un comando con `--from` legge solo quello store e non ripiega mai.

Un id di snapshot indicato senza `--from` viene cercato in tutti gli store della discendenza.

## Stato per destinazione

`rdc backup status` stampa una riga per destinazione accanto alla tabella della pianificazione:

| Colonna | Significato |
|---------|-------------|
| Store | L'id dello store in cui scrive la destinazione |
| Last run | Quando è terminata l'ultima esecuzione per quello store |
| Result | L'esito di quell'esecuzione |
| Newest snapshot | Lo snapshot più recente contenuto nello store |
| Verify | L'esito dell'ultima verifica dello store |
| Clean-up | `enabled`, oppure disattivata con il motivo |

Uno store su cui l'account non può riferire mostra `-` nelle sue colonne. Il controllo delle esecuzioni mancate avviene per store, quindi uno store che ha smesso di ricevere backup fa scattare un proprio allarme mentre gli altri restano verdi.

## Cosa conta per la quota

Gli store ospitati, `home` e ogni seconda regione, vengono misurati in byte univoci memorizzati fisicamente, e i loro byte contano per la stessa quota del piano. `rdc backup usage` li mostra.

I byte di un bucket del cliente non sono memorizzati da Rediacc e non contano per la quota. I metadati che l'account conserva per esso (righe di manifest, esecuzioni di verifica e oggetti di indice) vengono misurati come quelli di uno store ospitato.

## Store con pulizia disattivata

Uno store che rifiuta l'eliminazione conserva ogni oggetto. Retention e garbage collection non eliminano mai nulla da esso. Quando uno snapshot scade, lo sweep lo contrassegna come scaduto sull'account, smette di proporlo per il ripristino e lascia i suoi oggetti nel bucket.

`rdc backup status` e il riepilogo sulla salute dei backup segnalano lo store come pulizia disattivata. Il bucket continua a crescere finché non vengono aggiunte credenziali di eliminazione registrando di nuovo lo stesso id con chiavi autorizzate a eliminare.
