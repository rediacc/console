---
title: "Strumenti"
description: "Sincronizzazione file, accesso al terminale, integrazione con VS Code e aggiornamenti della CLI. È possibile gestire tutto senza mai lasciare il tuo ambiente di sviluppo preferito."
category: "Guides"
order: 9
language: it
sourceHash: "f350872720c99d58"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Strumenti

Rediacc include strumenti per lavorare con repository remoti: sincronizzazione file, terminale SSH, integrazione con VS Code e aggiornamenti della CLI.

## Sincronizzazione File (sync)

Trasferisci file tra la tua workstation e un repository remoto tramite rsync via SSH.

### Caricamento File

`--local` accetta uno o più percorsi. Ogni percorso può essere un file o una directory. I file vengono depositati in `<remote>/<basename>`; il contenuto delle directory viene unito in `<remote>/`. Per un singolo file, preferisci `--remote-file` per specificare esplicitamente il percorso di destinazione.

```bash
# Directory (contenuto unito nel remoto)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# File singolo inserito in una directory remota (basename preservato)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# File singolo, percorso di destinazione esplicito
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Sorgenti multiple in una sola chiamata
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` e `--remote-file` si escludono a vicenda. `--remote-file` richiede esattamente un percorso `--local` che punta a un file.

`--mirror` non può essere combinato con una sorgente file; eliminerebbe i file adiacenti nella directory remota.

### Scaricamento File

Usa `--remote` per una directory (predefinito) o `--remote-file` per un singolo file. I due flag si escludono a vicenda.

```bash
# Directory
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# File singolo -- --local deve essere una directory esistente
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Verifica Stato di Sincronizzazione

```bash
rdc repo sync status -m server-1 -r my-app
```

### Opzioni

| Opzione | Descrizione |
|---------|-------------|
| `-m, --machine <name>` | Macchina di destinazione |
| `-r, --repository <name>` | Repository di destinazione |
| `--local <paths...>` | Uno o più percorsi locali di file o directory (upload) o directory di destinazione locale (download) |
| `--remote <path>` | Directory remota (relativa al mount del repository) |
| `--remote-file <path>` | Percorso file remoto per upload o download di file singoli (alternativa a `--remote`) |
| `--dry-run` | Anteprima delle modifiche senza trasferimento |
| `--mirror` | Specchia la sorgente nella destinazione, elimina i file extra (solo sorgenti directory) |
| `--verify` | Verifica i checksum dopo il trasferimento |
| `--confirm` | Conferma interattiva con vista dettagliata |
| `--exclude <patterns...>` | Escludi pattern di file |
| `--skip-router-restart` | Salta il riavvio del server di routing dopo l'operazione |

## Terminale SSH (term)

Apri una sessione SSH interattiva verso una macchina o nell'ambiente di un repository.

### Sintassi Abbreviata

Il modo più rapido per connettersi:

```bash
rdc term connect -m server-1                    # Connetti a una macchina
rdc term connect -m server-1 -r my-app             # Connetti a un repository
```

### Esegui un Comando

Esegui un comando senza aprire una sessione interattiva:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Quando ci si connette a un repository, `DOCKER_HOST` viene impostato automaticamente sul socket Docker isolato del repository, quindi `docker ps` mostra solo i container di quel repository.

### Sottocomando connect

Il sottocomando `connect` fa la stessa cosa con flag espliciti:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Azioni sui Container

Interagisci direttamente con un container in esecuzione:

```bash
# Apri una shell all'interno di un container
rdc term connect -m server-1 -r my-app --container <container-id>

# Visualizza i log del container
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Segui i log in tempo reale
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Visualizza le statistiche del container
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Esegui un comando in un container
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| Opzione | Descrizione |
|---------|-------------|
| `--container <id>` | ID del container Docker di destinazione |
| `--container-action <action>` | Azione: `terminal` (predefinita), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Numero di righe di log da mostrare (predefinito: 50) |
| `--follow` | Segui i log continuamente |
| `--external` | Usa un terminale esterno invece di SSH inline |

## Integrazione VS Code (vscode)

Apri una sessione SSH remota in VS Code, preconfigurata con le impostazioni SSH corrette.

### Connetti a un Repository

```bash
rdc vscode connect -r my-app -m server-1
```

Questo comando:
1. Rileva la tua installazione di VS Code
2. Configura la connessione SSH in `~/.ssh/config`
3. Mantiene la chiave SSH per la sessione
4. Apre VS Code con una connessione Remote SSH al percorso del repository

### Elenca le Connessioni Configurate

```bash
rdc vscode list
```

### Pulisci le Connessioni

```bash
rdc vscode cleanup
```

Rimuove le configurazioni SSH di VS Code non più necessarie.

### Verifica la Configurazione

```bash
rdc vscode check
```

Verifica l'installazione di VS Code, l'estensione Remote SSH e le connessioni attive.

> **Prerequisito:** Installa l'estensione [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) in VS Code.

## Aggiornamenti della CLI (update)

Mantieni la CLI `rdc` aggiornata.

### Controlla gli Aggiornamenti

```bash
rdc update --check-only
```

### Applica l'Aggiornamento

```bash
rdc update
```

Gli aggiornamenti vengono scaricati e applicati in loco. La CLI sceglie automaticamente il binario corretto per la tua piattaforma (Linux, macOS o Windows). La nuova versione diventa attiva alla prossima esecuzione.

### Rollback

```bash
rdc update --rollback
```

Ripristina la versione precedentemente installata. Disponibile solo dopo che un aggiornamento è stato applicato.

### Stato dell'Aggiornamento

```bash
rdc update --status
```

Mostra la versione corrente, il canale di aggiornamento e la configurazione dell'aggiornamento automatico.

#### Canali di Rilascio

```bash
rdc update --channel edge      # Aggiornamenti di produzione continuamente distribuiti
rdc update --channel stable    # Promosso da edge dopo 7 giorni di maturazione (predefinito)
rdc update --status            # Mostra il canale corrente e le informazioni sulla versione
```
