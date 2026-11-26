---
title: "Risposta agli incidenti: indagare, dichiarare e preservare le prove"
description: "Aprite un'indagine su un repository o una macchina, leggete un'unica timeline di audit, esecuzioni, flussi e aperture di file, verificate le catene di hash, dichiarate un incidente per congelare le prove e avviare i timer di 24 ore, 72 ore e un mese, e gestite tutto da rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: it
sourceHash: "07d8b9d09d0e2191"
sourceCommit: "d93166e47a19c588a2284e21d263cca7f8a3578d"
---

# Risposta agli incidenti

Qui per incidente si intende uno che avviene nei repository del cliente. La pagina di indagine, i comandi `rdc incident` e i lettori `rdc repo flows` e `rdc repo opens` lavorano tutti sui record descritti nella [forensics](/it/docs/forensics). Gli incidenti nei sistemi di Rediacc seguono la [risposta agli incidenti di sicurezza](/it/docs/security-incident-response).

## Accesso

L'indagine richiede un piano a pagamento e il ruolo di proprietario o amministratore. L'apertura chiede una riautenticazione recente, e un'indagine aperta resta valida per 60 minuti. Ogni consultazione viene scritta nel log di audit.

Il supporto Rediacc vede i dati forensics solo con un'autorizzazione di supporto emessa dal cliente. Un'autorizzazione dura al massimo 7 giorni e può essere revocata in qualsiasi momento.

Le letture della CLI richiedono lo scope `forensics:read`, mentre dichiarare e chiudere richiedono `incident:manage`. Un login CLI li include entrambi per proprietari e amministratori dopo un'approvazione elevata nel browser. Quando un comando risponde che serve una recente approvazione elevata, il portale dell'account la richiede e il comando può essere rieseguito.

## La timeline

La pagina Investigate unisce un ambito (un repository o una macchina) in un'unica timeline con cinque tipi di riga: eventi di audit della console, esecuzioni, flussi di rete, aperture di file e anomalie. Le modifiche dall'ultimo snapshot si possono confrontare con esso. Un cursore della finestra temporale imposta la finestra, e una finestra copre al massimo 31 giorni.

Un tratto senza prove compare come riga di vuoto che indica la macchina e il motivo, mai come un tratto vuoto. Un grafico dei byte in uscita al minuto e un elenco delle destinazioni principali stanno sopra le righe.

Le stesse letture sono disponibili dalla riga di comando:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` e `--until` accettano un istante ISO 8601 o un intervallo a ritroso da adesso come `90m`, `24h` o `7d`. La finestra predefinita sono le ultime 24 ore. Le righe di flusso mostrano ora, processo, destinazione, byte in uscita e in entrata, e ASN e paese se noti. Le righe di apertura mostrano ora, processo e percorso, con i percorsi sensibili evidenziati.

## Verificare le prove

Verify evidence ricalcola nel browser la catena di hash dei file giornalieri di audit e le catene di batch firmati dei record forensics per la finestra, ed elenca ogni vuoto e ogni modifica. Le firme dei batch sono controllate con le chiavi di spool che il server degli account ha fissato per ogni macchina. Una chiave scritta all'interno delle prove non è mai considerata attendibile. Il risultato viene impresso nei report esportati.

Le prove oltre i 2 GiB sono troppo grandi per il browser. Lo stesso modulo gira dalla riga di comando:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

Il comando termina con codice 1 quando trova un vuoto o una modifica. `--machine-key <machine>=<64 hex characters>` fornisce una chiave esterna alla directory e può essere ripetuto. Una macchina senza chiave esterna fallisce.

## Dichiarare un incidente

Dichiarare congela le prove. Prima viene registrato l'incidente nell'account, poi il repository viene preparato per l'indagine:

1. L'incidente viene registrato con la sua finestra, chi lo ha dichiarato e quando l'organizzazione ne è venuta a conoscenza.
2. Un blocco di rimozione copre la finestra, e le regole di blocco del bucket si estendono su di essa, così FIFO non può eliminare quei giorni.
3. Il repository viene forkato come snapshot forense, con il tag `incident-<id>`.
4. Il livello di cattura del repository passa a Full.

Tre timer partono dal momento della presa di conoscenza, che può essere fissato prima della dichiarazione e mai dopo: l'allerta precoce scade 24 ore dopo la presa di conoscenza, la notifica 72 ore dopo, e il report finale un mese di calendario dopo la notifica (contato dalla scadenza della notifica finché non ne è registrata una). La pagina mostra ogni timer come in attesa, in scadenza entro 6 ore, scaduto o completato.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Un passaggio fallito sulla macchina lascia in sede il record e il suo blocco, termina con codice 1 e indica il comando che riesegue solo i passaggi falliti:

```bash
rdc incident declare mail --resume <id>
```

`--resume` mantiene la finestra e la presa di conoscenza della dichiarazione originale, quindi `--since`, `--until` e `--aware-at` non si combinano con esso.

## Esportare le prove

`rdc incident export` scrive la finestra dell'incidente in una directory: il record dell'incidente con i suoi timer, la timeline unita, gli aggregati dei byte in uscita, il manifest grezzo della catena e i file grezzi che elenca. Quando il manifest elenca file giornalieri di audit o file di header forensics, le catene vengono verificate lungo il percorso e il risultato va in `verification.json`. Il comando termina con codice 1 quando le prove mostrano un vuoto o una modifica.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Con `--stage`, lo stesso comando scrive invece un report firmato. Vedi i [report di incidente](/it/docs/incident-reports).

## Chiudere un incidente

```bash
rdc incident close <id>
```

Nulla viene rilasciato subito. Il blocco di rimozione e le regole di blocco del bucket terminano 30 giorni dopo la chiusura.

## Chiedere all'IA

La pagina di indagine ha un assistente che risponde a domande sull'ambito e la finestra aperti. Legge solo quell'ambito e quella finestra, con un ticket monouso emesso dall'indagine aperta e riscattabile per 15 minuti. La domanda e le righe lette vanno al provider di IA dell'organizzazione stessa. L'assistente può eseguire i comandi `rdc` qui sopra con le stesse regole di permesso di qualsiasi altro comando.

## Comandi

| Comando | Scopo |
|---|---|
| `rdc repo flows <ref>` | Flussi di rete di un repository in una finestra |
| `rdc repo opens <ref>` | Aperture di file sensibili di un repository in una finestra |
| `rdc forensics level <ref> <level>` | Impostare il livello di cattura |
| `rdc forensics verify` | Verificare una directory di prove o un report firmato |
| `rdc incident declare <ref>` | Registrare un incidente, forkare il repository e passare a Full |
| `rdc incident status [id]` | Elencare gli incidenti, o mostrarne uno con i suoi timer |
| `rdc incident export <id>` | Scrivere la finestra di prove, o un report firmato con `--stage` |
| `rdc incident close <id>` | Chiudere un incidente |
