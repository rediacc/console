---
title: "Riferimento Rapido RDC CLI"
description: "Guida rapida ai comandi rdc più usati: configurazione, repository, macchine, sincronizzazione e gestione dei container così da avere tutto a portata di mano."
category: Guides
order: 3
language: it
sourceHash: "ad0ae49efa847fbc"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Riferimento Rapido RDC CLI

Riferimento rapido per i comandi `rdc` più comuni. Esegui qualsiasi comando con `--help` per le opzioni complete.

## Ciclo di Vita della Repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Crea una nuova repository su una macchina |
| `rdc repo up --name <repo> -m <machine>` | Distribuisce o aggiorna una repository |
| `rdc repo down --name <repo> -m <machine>` | Ferma una repository |
| `rdc repo delete --name <repo> -m <machine>` | Elimina una repository |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Esegui il fork di una repository (quasi istantaneo, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Prendi la proprietà di una repository esistente |
| `rdc config repository list` | Elenca tutte le repository con nome e GUID |

## Segreti per Repository

Credenziali di deploy in sola scrittura. `get` restituisce solo il digest. Il valore non viene mai restituito. Vedi [Repositories § Secrets](/it/docs/repositories#secrets) per la guida completa.

| Comando | Descrizione |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Crea un nuovo segreto (`--current ""` per la prima scrittura) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Sovrascrive un segreto esistente (precondizione in stile passwd) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Sovrascrive senza verificare il valore precedente (registrato come rotazione) |
| `rdc repo secret list --name <repo>` | Elenca i nomi dei segreti e le modalità di consegna (mai valori, mai digest) |
| `rdc repo secret get --name <repo> --key <KEY>` | Mostra il digest del segreto e la modalità (nessun valore in chiaro, mai) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Elimina un segreto |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Elimina senza verificare il valore precedente |

> I fork non ereditano segreti. Impostali sul fork esplicitamente con `rdc repo secret set --name <repo>:<tag>`.

## Backup e Ripristino

| Comando | Descrizione |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Carica un backup della repository nell'archiviazione |
| `rdc repo push --to <storage> -m <machine>` | Carica tutte le repository nell'archiviazione |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Ripristina una repository dall'archiviazione |
| `rdc repo pull --from <storage> -m <machine>` | Ripristina tutte le repository dall'archiviazione |
| `rdc repo push ... --bwlimit <limit>` | Limita la banda rsync durante il push (es. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limita la banda rsync durante il pull |
| `rdc repo push ... --checkpoint` | Crea un checkpoint dei container prima del push |
| `rdc repo backup list --from <storage> -m <machine>` | Elenca i backup disponibili nell'archiviazione |
| `rdc storage browse --name <storage>` | Naviga nel contenuto dell'archiviazione |

## Migrazione della Repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Sposta una repository tra macchine |
| `rdc repo migrate ... --provision` | Provisioning sulla destinazione prima del trasferimento |
| `rdc repo migrate ... --checkpoint` | Crea un checkpoint prima della migrazione |
| `rdc repo migrate ... --skip-dns` | Salta l'aggiornamento DNS dopo la migrazione |
| `rdc repo migrate ... --bwlimit <limit>` | Limita la banda di trasferimento |

## Strategie di Backup

| Comando | Descrizione |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Crea o aggiorna una strategia di backup nominata |
| `rdc config backup-strategy list` | Elenca tutte le strategie di backup definite |
| `rdc config backup-strategy show --name <name>` | Mostra i dettagli di una strategia |
| `rdc config backup-strategy remove --name <name>` | Rimuove una strategia |
| `rdc machine backup schedule -m <machine>` | Distribuisce le strategie di backup configurate su una macchina |

## Operazioni di Backup

| Comando | Descrizione |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Distribuisce le strategie associate come timer systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Anteprima delle unità timer senza distribuirle (token mascherati) |
| `rdc machine backup now -m <machine>` | Esegui immediatamente tutte le strategie associate |
| `rdc machine backup now -m <machine> --strategy <name>` | Esegui immediatamente una strategia specifica |
| `rdc machine backup status -m <machine>` | Mostra lo stato dei timer e i risultati dei job recenti |
| `rdc machine backup status -m <machine> --strategy <name>` | Mostra lo stato di una strategia specifica |
| `rdc machine backup cancel -m <machine>` | Annulla i backup in esecuzione |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Annulla un backup specifico in esecuzione |

## Gestione delle Macchine

| Comando | Descrizione |
|---------|-------------|
| `rdc machine query --name <machine>` | Stato completo della macchina (sistema, container, servizi, repository, rete) |
| `rdc machine query --name <machine> --system` | Solo informazioni di sistema |
| `rdc machine query --name <machine> --containers` | Solo elenco container |
| `rdc machine query --name <machine> --repositories` | Solo elenco repository |
| `rdc machine query --name <machine> --services` | Solo elenco servizi |
| `rdc machine query --name <machine> --network` | Solo informazioni di rete |
| `rdc machine query --name <machine> --block-devices` | Solo informazioni sui dispositivi a blocchi |
| `rdc machine list` | Elenca tutte le macchine nel config |
| `rdc config machine setup --name <machine>` | Esegui il provisioning iniziale della macchina |
| `rdc machine prune --name <machine>` | Rimuovi le risorse inutilizzate dalla macchina |
| `rdc machine deprovision --name <machine>` | Deprovisionamento completo di una macchina |
| `rdc machine vault-status --name <machine>` | Mostra lo stato del vault LUKS |

## Terminale e Sync

| Comando | Descrizione |
|---------|-------------|
| `rdc term connect -m <machine>` | Apri il terminale SSH sulla macchina |
| `rdc term connect -m <machine> -r <repo>` | Apri il terminale SSH sulla repository (imposta DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Esegui un comando sulla macchina |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Carica uno o più file/directory locali nella repository |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Carica un singolo file locale in un percorso remoto esplicito |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Scarica la directory della repository in locale |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Scarica un singolo file remoto in una directory locale |
| `rdc vscode connect -m <machine> -r <repo>` | Apri una sessione VS Code Remote SSH |

## Configurazione

| Comando | Descrizione |
|---------|-------------|
| `rdc config init --name <name>` | Crea un file di config nominato |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Aggiungi una macchina al config |
| `rdc config storage import --file rclone.conf` | Importa provider di archiviazione dalla config rclone |
| `rdc config storage list` | Elenca i provider di archiviazione configurati |
| `rdc config backup-strategy set ...` | Definisci una strategia di backup nominata |
| `rdc --config <name> <command>` | Usa un file di config nominato |

## Debug e Valvola di Sicurezza

| Comando | Descrizione |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Elenca i container in una repository |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Recupera i log del container |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Esegui un comando nel container |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Riavvia un container |
