---
title: "git diff per immagini disco cifrate: diffing dei fork senza decifrarli"
description: "rdc repo diff confronta le immagini cifrate a livello di blocco e riporta A/M/D/R. Nessuna chiave viene toccata. Il costo segue i blocchi modificati, non la dimensione del repository."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-28
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: it
sourceHash: "516ffb7de9941f15"
sourceCommit: "0a3e9865997659698502ad551e078be854b4b2c4"
---

> **TL;DR.** `rdc repo diff` mostra la differenza a livello di file tra due repository forkati con la grammatica di `git status --short` (A/M/D/R), senza decifrare nessuno dei due.
>
> - Confronta i due file immagine LUKS a livello di blocco con l'ioctl FIEMAP, che legge solo i metadati della mappa delle estensioni. Nessuna chiave viene caricata, nessun testo in chiaro viene letto.
> - aes-xts conserva la lunghezza e cifra ogni settore da 512 byte in modo indipendente, quindi un settore in chiaro modificato produce un settore cifrato modificato allo stesso offset (spostato dall'offset dati LUKS di 16 MiB). Sottrai l'offset, mappa gli intervalli del dispositivo ai nomi di file attraverso la mappa delle estensioni ext4, e ottieni un elenco di file.
> - Il costo segue il numero di blocchi modificati, non la dimensione del repository. Un fork da 1 GB e uno da 100 GB producono un diff negli stessi millisecondi, perché il confronto e' solo sui metadati.

Quindi, un fork in Rediacc e' un `cp --reflink=always` dell'immagine LUKS di un repository. Istantaneo, e non dipende dalla dimensione. Un repository da 100 GB si forka veloce quanto uno da 1 GB. Lo so che sembra marketing, ma e' semplicemente come funzionano i reflink: btrfs copia la mappa delle estensioni e condivide i blocchi sottostanti. Ci appoggiamo molto su questo. I fork sono la sandbox di test, il branch usa-e-getta, la copia di staging che si butta via quando si e' finito.

Quello che non avevamo era una risposta economica alla domanda ovvia successiva: cosa ha cambiato effettivamente questo fork. La via ingenua: monta il fork, sblocca il container LUKS, percorri l'ext4 interno, calcola l'hash di ogni file contro il parent. Scala con la dimensione del repository sia in letture che in decifratura. Richiede le chiavi attive nel percorso del diff. E butta via l'unica cosa che il layer di storage gia' conosce gratuitamente: quali blocchi sono divergenti. `rdc repo diff` prende l'altra strada. Scala con i blocchi modificati. Non carica nessuna chiave. Ottiene l'elenco dei file confrontando le due immagini cifrate.

## Lo stack che stai confrontando

Permettimi di essere preciso su cosa significano "due repository" su disco. L'intero trucco dipende da questo. Dal basso verso l'alto: un SSD, lo storage dell'host, un pool btrfs. Sopra, un file immagine LUKS2 per repository. Sblocca e ottieni un dispositivo dm-crypt. All'interno si trova il filesystem ext4 che usano i container. Un repository e' un file sul pool btrfs.

Un fork e' un reflink di quel file. Subito dopo il fork, i due file immagine sono identici byte per byte. Condividono ogni blocco fisico. Il parent e il fork non sono due copie dei dati. Sono due mappe di estensioni che puntano agli stessi blocchi. Quando scrivi all'interno del fork, il layer di storage alloca un blocco nuovo per la regione modificata. Solo la mappa di estensioni di quel fork viene riscritta. I blocchi del parent rimangono intatti.

Quindi "confronta due repository" si riduce a "confronta due file che condividono la maggior parte delle loro estensioni." Il kernel puo' gia' rispondere a questa domanda. Nessuno deve leggere un singolo byte di nessuno dei due file.

## FIEMAP: chiedere al kernel cosa e' cambiato senza leggerlo

L'ioctl FIEMAP restituisce la mappa delle estensioni di un file: una lista di tuple (offset logico, offset fisico, lunghezza). Ogni tupla indica dove si trova una parte del file su disco. Sono puri metadati del filesystem. Non legge i dati del file. Per un'immagine cifrata non ha bisogno di nessuna chiave. Il testo cifrato e' solo byte che il kernel non deve mai interpretare.

Confronta le due mappe di estensioni. Qualsiasi intervallo logico in cui entrambi i fork puntano allo stesso blocco fisico e' condiviso. Condiviso significa identico, perche' e' letteralmente lo stesso blocco sul dispositivo. Gli intervalli in cui il fork ha il proprio blocco privato sono le scritture. Sono i blocchi modificati. Ottenuti dai metadati che il layer di storage mantiene comunque.

Ecco da dove viene la storia del costo. Il confronto FIEMAP legge i record delle estensioni, non i dati. Il suo lavoro scala con quante estensioni sono cambiate, non con la dimensione del repository. Il fork da 1 GB e quello da 100 GB restituiscono la stessa lista corta di estensioni private. Stessi millisecondi, se hanno cambiato gli stessi file. Caveat onesto: il tempo di attraversamento delle estensioni scala con la frammentazione dell'immagine, non con la dimensione. Un'immagine copy-on-write sotto scritture casuali intense accumula estensioni. Il walk completo `filefrag` ha impiegato 3,19 secondi sull'immagine di produzione piu' frammentata che ho misurato. Vedi il post sul benchmark della frammentazione. Questo e' il limite sul lato dei metadati. E' una scansione in background, non una lettura dei dati.

## Da un blocco modificato a un nome di file, attraverso due layer cifrati

Una lista di intervalli di byte modificati nell'immagine cifrata non e' ancora utile. Gli intervalli sono posizioni nel testo cifrato. I nomi che vuoi si trovano due layer sopra, nell'ext4 interno. Il ponte tra loro e' aritmetica degli indirizzi, non decifratura.

LUKS cifra con aes-xts. Conserva la lunghezza e cifra ogni settore da 512 byte per conto proprio. Un settore in chiaro modificato produce un settore cifrato modificato allo stesso offset. L'unico spostamento e' l'offset dati LUKS. Sono i 16 MiB di header e keyslot davanti al payload cifrato. Sottrai quell'offset da ogni intervallo dell'immagine modificata. Ora hai l'intervallo corrispondente sul dispositivo dm-crypt. E' il dispositivo a blocchi su cui risiede l'ext4 interno. Nessuna chiave e' stata usata. E' solo sottrazione.

Ora mappa gli intervalli del dispositivo ai file. ext4 mantiene anche una mappa delle estensioni per inode. Stessa struttura (logico, fisico, lunghezza). La raggiungi tramite FIEMAP sul filesystem interno montato. Percorri gli inode una volta per costruire un indice da blocco a file. Poi cerca ogni intervallo del dispositivo modificato in quell'indice. Un intervallo che si sovrappone alle estensioni dati dell'inode 1234 appartiene al percorso di quell'inode. Quel percorso e' il file che e' cambiato.

Dichiaro esplicitamente cosa questo non fa mai. Non ricava mai il testo in chiaro dall'immagine modificata. Legge la struttura del filesystem a offset noti. Lo fa sia sul lato cifrato che sul lato decifrato. Poi li unisce per indirizzo. Il filtro dei blocchi dice quali regioni del dispositivo sono cambiate. La mappa delle estensioni ext4 dice quale file possiede ogni regione. Nessuno dei due passi ispeziona il contenuto di un blocco modificato per decidere se e' cambiato.

## Aggiunte, cancellazioni e ridenominazioni: il walk dell'identita' degli inode

Le modifiche emergono direttamente dal confronto dei blocchi. Aggiunte, cancellazioni e ridenominazioni richiedono un'osservazione in piu'. Il reflink ce la fornisce gratuitamente: un fork conserva i numeri di inode. Il reflink dell'intera immagine clona byte per byte l'intero filesystem interno prima che qualcosa diverga. Quindi un inode che esisteva nel parent ha lo stesso numero nel fork.

Questo rende l'identita' un confronto di insiemi. Un inode su entrambi i lati con un percorso diverso e' una ridenominazione. Un inode solo sul lato nuovo e' un'aggiunta. Un inode solo sul lato vecchio e' una cancellazione. Una ridenominazione e' confermata dalla sovrapposizione delle estensioni del dispositivo. I blocchi dati del file rinominato si trovano agli stessi offset del dispositivo su entrambi i fork. I due fork condividono un sistema di coordinate. Quella sovrapposizione esclude anche il riutilizzo di un numero di inode per dati non correlati. Una pura ridenominazione appare con i blocchi dati del file invariati. Solo la voce di directory e' cambiata.

Ecco la forma predefinita del name-status, la stessa grammatica A/M/D/R che gia' leggi da `git status --short`:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Un file modificato in un repository da 1 GB. Riportato da un confronto di blocchi che non ha letto nessun dato del file. Nulla e' stato sbloccato.

Il default fa un'altra cosa per la correttezza. Il filtro dei blocchi e' un sovrainsieme. Un'estensione btrfs puo' coprire piu' byte di quelli effettivamente cambiati. Quindi una scrittura su un file puo' segnalare un vicino che condivide un'estensione. Per evitare di segnalare un file che non e' cambiato, il default conferma ogni candidato segnalato dai blocchi. Calcola l'hash solo di quel file su entrambi i lati. Calcola l'hash dei candidati, non del repository. Quindi il costo della conferma segue ancora il set di modifiche. `--fast` si fida del filtro dei blocchi e salta la conferma. Usalo quando vuoi la risposta velocemente e tolleri qualche falso positivo occasionale.

## Perche' un agente AI ha bisogno di questo

Il motivo per cui questo comando esiste e' il workflow degli agenti. Continuavo a vedere agenti forkare la produzione, eseguire modifiche e poi non avere un modo pulito per riferire cosa avevano effettivamente toccato. Un agente AI puo' forkare la produzione istantaneamente. Esegue una modifica rischiosa all'interno del fork isolato. Poi deve sapere esattamente cosa ha toccato prima di promuovere qualcosa. Il fork e' il branch. Il diff e' la revisione.

L'agente non legge il name-status, legge `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

L'output strutturato fornisce all'agente un set di modifiche preciso. Quali percorsi ha modificato, creato, cancellato. Con `--stat`, la dimensione della modifica per file in byte e blocchi. Un agente che vede il proprio diff prima di promuovere e' uno a cui puoi lasciare avvicinare alla produzione. Il raggio d'azione e' ispezionabile, non solo dichiarato. Le altre modalità servono lo stesso loop di revisione. `--name-only` per una lista di percorsi pura. `--content <path>` per un diff unificato in testo di un singolo file (solo testo; un file binario riporta `Binary files differ`). `--stat` quando l'agente deve sapere cosa è cambiato e quanto.

## Perche' il testing DR ne ha bisogno

La stessa primitiva risponde a una domanda DR che prima era imbarazzante da porre senza rischi. Forka la produzione. Ripristina un backup nel fork. Confronta il fork con la produzione. Il diff dice se il ripristino ha riprodotto il set di file atteso. Lo fa senza fermare la produzione. E non decifra nulla nel percorso del diff.

Questo è un test che puoi eseguire su schedulazione. Il ripristino atterra in un fork isolato. Il diff riporta il delta con la grammatica di git. Un test pulito: il set di modifiche corrisponde a ciò che il backup avrebbe dovuto contenere. Stai validando il recovery contro la produzione live. La copia non costa nulla da fare e nulla da buttare via.

## Limiti onesti

Il diff del contenuto e' solo testo. `--content` produce un diff unificato per i file di testo. Per tutto il resto riporta `Binary files differ`, nello stesso modo di git. Un diff orientato alle righe di un blob cifrato-poi-compresso e' rumore.

Confronta fork correlati, non repository arbitrari. L'intero meccanismo si basa su un sistema di coordinate condiviso. Le estensioni condivise provano l'uguaglianza. I numeri di inode conservati ancorano l'identità. Un offset dati comune lega tutto insieme. Due repository che non sono mai stati forkati da un antenato comune non condividono nulla di tutto ciò. Non esiste un diff economico tra loro. Questa è una caratteristica, non un bug. Nello stesso modo in cui `git diff` tra due storie non correlate non è significativo.

Il rilevamento delle ridenominazioni è basato sugli inode. È preciso per le ridenominazioni che il filesystem registra effettivamente come ridenominazioni. Una cancellazione seguita da una creazione di contenuto identico sotto un nuovo nome? Due operazioni sulla tabella degli inode. Quindi viene riportata come una cancellazione e un'aggiunta, non come una ridenominazione. L'euristica di somiglianza del contenuto di git chiamerebbe quella una ridenominazione. Il walk degli inode non lo farà. Questa è la risposta corretta su cosa ha fatto il filesystem. Anche se non è la risposta su cosa intendeva un umano.

E il walk dei metadati scala con la frammentazione. Su un'immagine altamente frammentata l'enumerazione delle estensioni richiede secondi, non millisecondi. È comunque indipendente dalla dimensione del repository. È comunque priva di qualsiasi lettura dei dati. Ma non è letteralmente istantanea sulle immagini più frammentate.

## Il punto

`rdc repo diff` porta l'ergonomia del controllo di versione su infrastrutture cifrate e in esecuzione. L'interfaccia è deliberatamente git. A/M/D/R, diff unificati, `--stat`. Nulla di nuovo da imparare. Se sai leggere `git status --short`, sai leggere un diff tra due immagini LUKS. L'ingegneria sottostante è la parte che vale la pena di capire. Si riduce a due rifiuti. Non decifra mai. aes-xts permette a un confronto FIEMAP a livello di blocco di localizzare ogni settore modificato per indirizzo. E non paga mai per dati che non sono cambiati. Il layer di storage ha già registrato quali blocchi sono divergenti. Il fork è il branch. Il diff è la revisione. La revisione costa quanto costa la modifica, non quanto pesa il repository.
