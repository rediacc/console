---
title: "Avvio automatico e ripristino"
description: "Come funziona l'avvio automatico, il riconciliatore periodico che ripristina i repository che si interrompono dopo l'avvio, e come verificare lo stato di ripristino."
category: "Guides"
order: 5
language: it
sourceHash: "7fa4f919475b304e"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Avvio automatico e ripristino

I repository con l'autostart abilitato si avviano automaticamente al boot. Se uno si interrompe in seguito, il riconciliatore periodico lo riporta in funzione. Nessuna richiesta. Nessun riavvio manuale.

Per abilitare o disabilitare l'autostart su un repository, vedere [Servizi: Autostart all'avvio](/it/docs/services#autostart-on-boot).

## Come funziona l'autostart

Quando abiliti l'autostart per un repository, Rediacc genera un keyfile LUKS casuale di 256 byte e lo aggiunge allo slot 1 LUKS del volume cifrato. Il keyfile è memorizzato in:

```
{datastore}/.credentials/keys/{guid}.key
```

Questo consente alla macchina di montare il repository senza richiedere la passphrase. Lo slot 0 LUKS (la tua passphrase) non viene modificato.

Lo slot del keyfile usa il KDF veloce PBKDF2: un keyfile casuale di 256 byte costituisce già di per sé un margine di sicurezza sufficiente, quindi un KDF memory-hard aggiungerebbe latenza di sblocco senza offrire protezione aggiuntiva. I montaggi si aprono in molto meno di un secondo. I repository creati prima di questa ottimizzazione pagano ancora una derivazione Argon2id di più secondi per ogni montaggio; è possibile convertirli sul posto (con il repository smontato) tramite il comando operatore `renet repository kdf-migrate --name <guid>` sulla macchina. Lo slot 0 mantiene Argon2id: la scelta giusta per una passphrase umana.

All'avvio, un servizio systemd one-shot chiamato `rediacc-autostart.service` legge l'elenco dei repository con autostart abilitato, monta ognuno usando il proprio keyfile, avvia il daemon Docker per repository ed esegue l'hook `up()` del Rediaccfile. All'arresto, il servizio esegue `down()`, ferma Docker e chiude i volumi LUKS.

> **Nota di sicurezza:** Il keyfile fornisce accesso a livello root al repository senza la passphrase. Chiunque abbia accesso root al server può montare i repository con autostart abilitato. Valuta questo in base al tuo modello di minaccia prima di abilitare l'autostart su repository sensibili.

## Il divario di ripristino

L'autostart all'avvio viene eseguito esattamente una volta per ogni avvio. Il watchdog del router, che gira continuamente dopo quell'evento, riavvia solo i *container all'interno di un repository già in esecuzione con un daemon Docker attivo*. Non può rimontare un volume LUKS né riavviare un daemon Docker per rete che si è fermato.

Ciò significa che se il volume LUKS di un repository viene smontato o il suo daemon Docker si ferma dopo che il server è stato avviato, né il servizio di avvio né il watchdog lo recupereranno. Prima che esistesse il riconciliatore, un repository in questo stato rimaneva fermo finché un operatore non interveniva.

## Riconciliatore periodico

Il timer systemd `rediacc-autostart-reconcile.timer` si attiva circa ogni 3 minuti ed esegue `renet repository reconcile`. Per ogni repository con autostart abilitato, il riconciliatore verifica tre cose:

1. Il volume LUKS è montato?
2. Il daemon Docker per rete è in esecuzione?
3. I servizi del repository sono attivi?

Se un controllo fallisce, il riconciliatore recupera il repository usando il suo keyfile: monta il volume, avvia il daemon Docker ed esegue `up()`. Non è richiesta alcuna passphrase.

I repository che sono sani, attualmente in uso da un'esecuzione di backup cold, o all'interno della finestra di back-off vengono saltati.

### Back-off e marcatori di fallimento persistenti

Un repository che non riesce a recuperarsi non riprova immediatamente a ogni tick. Il riconciliatore usa un back-off esponenziale:

| Numero di fallimenti | Attesa prima del prossimo tentativo |
|----------------------|-------------------------------------|
| 1 | 1 minuto |
| 2 | 2 minuti |
| 3 | 5 minuti |
| 4 | 15 minuti |
| 5+ | 30 minuti, poi 60 minuti |

Dopo 5 fallimenti consecutivi, il riconciliatore scrive un file marcatore durevole in:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Questo file sopravvive alla rotazione dei log. La sua presenza significa che il repository richiede l'intervento dell'operatore. Il riconciliatore registra il fallimento a livello di errore e smette di tentare il recupero automatico per quel repository finché il marcatore non viene rimosso.

Cause comuni di fallimento persistente del recupero:

- **Licenza del repository non attendibile o scaduta**: il controllo della licenza viene eseguito prima di `up()`.
- **Keyfile mancante**: se il keyfile in `{datastore}/.credentials/keys/{guid}.key` è stato eliminato, il riconciliatore non può montare il volume senza una passphrase.
- **Rediaccfile non funzionante**: un errore di sintassi o un hook `up()` che termina sempre con codice non zero.

### Relazione con il watchdog del router

Il riconciliatore e il watchdog del router gestiscono diversi livelli di fallimento e sono progettati per complementarsi:

| Livello | Cosa gestisce |
|---------|---------------|
| **Watchdog del router** | Riavvii a livello di container all'interno di un repository in esecuzione, montato, con un daemon Docker attivo |
| **Riconciliatore (`rediacc-autostart-reconcile.timer`)** | Recupero a livello di repository: rimontaggio LUKS, riavvio del daemon Docker, riesecuzione di `up()` |

Se un singolo container si blocca all'interno di un repository sano, il watchdog lo gestisce. Se l'intero daemon del repository si ferma, il riconciliatore lo gestisce.

## Ispezione dello stato di ripristino

### Stato del timer e del servizio

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Log del riconciliatore

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Marcatori di fallimento persistenti

Elenca i repository con marcatori di fallimento durevoli:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Ogni nome file è un GUID di repository. Usa `rdc config repository list` per mappare i GUID ai nomi dei repository.

Per rimuovere un marcatore dopo aver risolto il problema sottostante, elimina il file:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

Il riconciliatore tenterà il recupero di nuovo al prossimo tick del timer.

## Pagine correlate

- [Servizi: Autostart all'avvio](/it/docs/services#autostart-on-boot): abilitazione e disabilitazione dell'autostart, gestione del keyfile
- [Backup e Ripristino](/it/docs/backup-restore): interazione del backup cold con i servizi in esecuzione
