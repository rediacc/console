---
title: "Download dei backup"
description: "Copia l'immagine cifrata di un repository in una directory locale o su un'unità esterna, la aggiorna sul posto nelle esecuzioni successive oppure la ricostruisce direttamente dallo store di backup, senza alcuna macchina."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: it
sourceHash: "c52e6a0471befc30"
---

# Download dei backup

`rdc backup download` mantiene una copia dell'immagine cifrata di un repository in una directory locale o su un'unità esterna. La copia è lo stesso testo cifrato che si trova sulla macchina, quindi nulla viene decifrato lungo il percorso. La credenziale che la apre resta nella configurazione, per cui l'iscrizione a [config storage](/it/docs/config-storage) è il modo per tenerla al sicuro. Senza la credenziale l'immagine non può essere aperta.

Le sorgenti sono due. Una macchina in esecuzione è quella predefinita. L'altra è lo store di backup, selezionato con `--store`.

## Download da una macchina

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` indica una directory esistente e scrivibile. Non viene mai creata, quindi l'unità va montata prima. L'immagine finisce in `<machine>/<name>.<tag>.img`, con un file `.state.json` accanto.

Ogni esecuzione crea un nuovo snapshot del repository, mantenuto solo finché dura il trasferimento, invia le differenze con rsync e confronta un sha256 del risultato con lo snapshot della macchina.

| Flag | Effetto |
|------|--------|
| `--all -m <machine>` | Copia ogni repository grand presente sulla macchina |
| `--include-forks` | Insieme a `--all`, copia anche i fork |
| `--bwlimit <rate>` | Limita la banda di rete, ad esempio `100Mbps` o `12.5M` |
| `--checkpoint` | Esegue il checkpoint e congela il repository prima dello snapshot (backup a caldo) |
| `--retries <n>` | Tentativi all'interno dell'esecuzione dopo un errore di rete (predefinito 3) |
| `--skip-verify` | Salta il confronto sha256; il checksum di rsync viene comunque eseguito |
| `--skip-space-check` | Avvisa invece di rifiutare quando la destinazione potrebbe non avere spazio libero |

### Aggiornare la copia

Una seconda esecuzione aggiorna sul posto l'immagine esistente tramite delta rsync. Un'esecuzione settimanale invia solo ciò che è cambiato, e la destinazione ha bisogno di spazio per una copia dell'immagine, non per due. Prima dell'avvio di un'esecuzione, lo spazio libero viene confrontato con la dimensione dell'immagine, e `--skip-space-check` trasforma un rifiuto in un avviso.

### Esecuzioni interrotte e ripresa

Il file di stato registra `status`. Il valore è `incomplete` da prima che venga scritto il primo byte fino alla verifica di un'esecuzione, e un'immagine `incomplete` non è utilizzabile. Ctrl-C, una connessione persa o un processo terminato forzatamente la lasciano così. Rieseguire lo stesso comando riprende il trasferimento, e vengono inviate solo le differenze. Il comando termina con codice 0 quando lo stato diventa `complete`.

### Requisiti

Il trasferimento richiede rsync 3.1.3 o successivo su questo computer e non prevede alcun ripiego su SFTP. Le distribuzioni Linux lo includono. Su macOS, `brew install rsync` sostituisce openrsync incluso nel sistema, che non può eseguire il trasferimento. Su Windows si installa MSYS2 con il pacchetto rsync, oppure si usa l'app desktop.

### Unità esterne

Il filesystem della destinazione decide ciò che ci sta.

- **FAT32** non può contenere un file di oltre 4 GiB, e il comando rifiuta l'esecuzione.
- **exFAT** senza supporto per i file sparsi memorizza l'immagine con la sua dimensione apparente completa, quindi il controllo dello spazio libero conta quella dimensione.
- Uno **snapshot copy-on-write** preso in locale della destinazione (btrfs, ZFS, APFS) conserva le versioni precedenti dell'immagine. Ogni aggiornamento sul posto costa allora i blocchi modificati oltre a quelli vecchi.

## Download dallo store di backup

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` ricostruisce l'immagine direttamente dallo store di chunk, senza alcuna macchina coinvolta. Il token in `REDIACC_TOKEN` richiede gli scope `backup:read` e `backup:restore`. Un login della CLI non include mai `backup:restore`, quindi il token si crea nella pagina API Tokens del portale. Deve appartenere a un team ed essere stato creato da un proprietario o amministratore attuale dell'organizzazione.

`--store` accetta esattamente un nome di repository. Non accetta `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` né `--skip-space-check`: il recupero dallo store ha una propria ripresa e verifica ogni chunk.

L'immagine viene scritta in `<dir>/<name>.<tag>.img`. Un recupero interrotto conserva la copia parziale, e lo stesso comando riprende da essa.

### Scegliere uno snapshot con `--at`

Per impostazione predefinita viene recuperato lo snapshot più recente. `--at <time|snapshot>` ne seleziona un altro, indicato come orario in ISO 8601 o come id di snapshot. Vale solo con `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Su una piattaforma diversa da Linux, l'immagine recuperata è cifrata e non può essere aperta in locale. Va inviata a una macchina Linux con `rdc backup upload`.

## Caricare una copia di ritorno

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` invia un'immagine scaricata a una macchina e la registra come nuovo repository. Il trasferimento riprende dopo un'interruzione, e la macchina controlla sha256 e intestazione LUKS prima di collocare l'immagine. Il file di stato accanto all'immagine fornisce la credenziale. Quando quel file è andato perso, `--from-repo <name>` indica il repository che la fornisce.

| Flag | Effetto |
|------|--------|
| `--as <name>` | Nome del nuovo repository (predefinito: il nome dell'immagine) |
| `--datastore <name>` | Colloca l'immagine su un datastore indicato per nome |
| `--from-repo <name>` | Fornisce credenziale e lineage quando il file di stato è inutilizzabile |
| `--bwlimit <rate>`, `--retries <n>` | Come per il download |
| `--up` | Avvia il repository una volta registrato |
| `--skip-verify` | Salta il confronto con lo sha256 registrato al download |

## Snapshot di trasferimento obsoleti

Un trasferimento terminato forzatamente può lasciare il suo snapshot sulla macchina. `rdc machine status` conta gli snapshot di trasferimento obsoleti nel riepilogo del pool, e `rdc machine prune <machine> --dry-run` li elenca. Eseguire `rdc machine prune <machine>` li rimuove.

Per gli snapshot verso lo storage a chunk, vedere [Backup e Ripristino](/it/docs/backup-restore).
