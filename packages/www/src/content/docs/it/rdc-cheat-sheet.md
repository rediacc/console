---
title: Guida rapida alla CLI RDC
description: "Riferimento rapido per rdc: configurazioni, repository, macchine, sincronizzazione file e container. Opzioni complete: aggiungi --help a qualsiasi comando."
category: Guides
order: 3
language: it
sourceHash: "bc52628ba870dfbb"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Guida rapida alla CLI RDC

Non tutti i comandi `rdc` sono elencati qui, solo quelli più usati in ogni deployment. Per il set completo di opzioni, esegui qualsiasi comando rdc con `--help`. I casi limite e le opzioni poco usate si trovano nel riferimento completo.

## Ciclo di vita dei repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Crea un nuovo repository su una macchina |
| `rdc repo up --name <repo> -m <machine>` | Esegui il deploy o aggiorna un repository |
| `rdc repo down --name <repo> -m <machine>` | Arresta un repository |
| `rdc repo delete --name <repo> -m <machine>` | Elimina un repository |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Crea un fork di un repository (quasi istantaneo, reflink BTRFS) |
| `rdc repo takeover --name <repo> -m <machine>` | Prendi possesso di un repository esistente |
| `rdc config repository list` | Elenca tutti i repository con nome e GUID |

## Segreti per repository

Credenziali di deploy accessibili solo in scrittura. `get` restituisce solo il digest. Il valore non è mai restituito. Consulta [Repositories § Secrets](/it/docs/repositories#secrets) per la guida completa.

| Comando | Descrizione |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Crea un nuovo segreto (`--current ""` per la prima scrittura) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Sovrascrive un segreto esistente (precondizione in stile passwd) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Sovrascrive senza verificare il valore precedente (registrato come rotazione) |
| `rdc repo secret list --name <repo>` | Elenca i nomi dei segreti e le modalità di consegna (mai i valori, mai i digest) |
| `rdc repo secret get --name <repo> --key <KEY>` | Mostra il digest e la modalità del segreto (nessun valore in chiaro, mai) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Elimina un segreto |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Elimina senza verificare il valore precedente |

> I fork non ereditano segreti. Impostali esplicitamente sul fork con `rdc repo secret set --name <repo>:<tag>`.

## Backup e ripristino

| Comando | Descrizione |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Invia il backup di un repository sullo storage |
| `rdc repo push --to <storage> -m <machine>` | Invia tutti i repository sullo storage |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Ripristina un repository dallo storage |
| `rdc repo pull --from <storage> -m <machine>` | Ripristina tutti i repository dallo storage |
| `rdc repo push ... --bwlimit <limit>` | Limita la banda rsync durante il push (es. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limita la banda rsync durante il pull |
| `rdc repo push ... --checkpoint` | Esegui il checkpoint dei container prima del push |
| `rdc repo backup list --from <storage> -m <machine>` | Elenca i backup disponibili nello storage |
| `rdc storage browse --name <storage>` | Esplora il contenuto dello storage |

## Migrazione dei repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Sposta un repository tra macchine |
| `rdc repo migrate ... --provision` | Esegui il provisioning sulla destinazione prima del trasferimento |
| `rdc repo migrate ... --checkpoint` | Esegui il checkpoint prima della migrazione |
| `rdc repo migrate ... --skip-dns` | Salta l'aggiornamento DNS dopo la migrazione |
| `rdc repo migrate ... --bwlimit <limit>` | Limita la banda di trasferimento |

## Strategie di backup

| Comando | Descrizione |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Crea o aggiorna una strategia di backup con nome |
| `rdc config backup-strategy list` | Elenca tutte le strategie di backup definite |
| `rdc config backup-strategy show --name <name>` | Mostra i dettagli di una strategia |
| `rdc config backup-strategy remove --name <name>` | Rimuove una strategia |
| `rdc machine backup schedule -m <machine>` | Distribuisce le strategie di backup configurate su una macchina |

## Operazioni di backup

| Comando | Descrizione |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Distribuisce le strategie collegate come timer systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Anteprima delle unità timer senza distribuzione (token mascherati) |
| `rdc machine backup now -m <machine>` | Esegue immediatamente tutte le strategie collegate |
| `rdc machine backup now -m <machine> --strategy <name>` | Esegue immediatamente una strategia specifica |
| `rdc machine backup status -m <machine>` | Mostra lo stato dei timer e i risultati recenti |
| `rdc machine backup status -m <machine> --strategy <name>` | Mostra lo stato di una strategia specifica |
| `rdc machine backup cancel -m <machine>` | Annulla i backup in esecuzione |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Annulla un backup specifico in esecuzione |

## Gestione delle macchine

| Comando | Descrizione |
|---------|-------------|
| `rdc machine query --name <machine>` | Stato completo della macchina (sistema, container, servizi, repository, rete) |
| `rdc machine query --name <machine> --system` | Solo informazioni di sistema |
| `rdc machine query --name <machine> --containers` | Solo elenco dei container |
| `rdc machine query --name <machine> --repositories` | Solo elenco dei repository |
| `rdc machine query --name <machine> --services` | Solo elenco dei servizi |
| `rdc machine query --name <machine> --network` | Solo informazioni di rete |
| `rdc machine query --name <machine> --block-devices` | Solo informazioni sui dispositivi a blocchi |
| `rdc machine list` | Elenca tutte le macchine nella configurazione |
| `rdc config machine setup --name <machine>` | Esegui il provisioning iniziale della macchina |
| `rdc machine prune --name <machine>` | Rimuove le risorse inutilizzate dalla macchina |
| `rdc machine deprovision --name <machine>` | Esegui il deprovisioning completo di una macchina |
| `rdc machine vault-status --name <machine>` | Mostra lo stato del vault LUKS |

## Terminale e sincronizzazione

| Comando | Descrizione |
|---------|-------------|
| `rdc term connect -m <machine>` | Apri un terminale SSH alla macchina |
| `rdc term connect -m <machine> -r <repo>` | Apri un terminale SSH al repository (imposta DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Esegui un comando sulla macchina |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Carica uno o più file o directory locali nel repository |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Carica un singolo file locale in un percorso remoto esplicito |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Scarica una directory del repository in locale |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Scarica un singolo file remoto in una directory locale |
| `rdc vscode connect -m <machine> -r <repo>` | Apri una sessione VS Code Remote SSH |

## Configurazione

| Comando | Descrizione |
|---------|-------------|
| `rdc config init --name <name>` | Crea un file di configurazione con nome |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Aggiungi una macchina alla configurazione |
| `rdc config storage import --file rclone.conf` | Importa i provider di storage da una configurazione rclone |
| `rdc config storage list` | Elenca i provider di storage configurati |
| `rdc config backup-strategy set ...` | Definisci una strategia di backup con nome |
| `rdc --config <name> <command>` | Usa un file di configurazione con nome |

## Debug e via di uscita

| Comando | Descrizione |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Elenca i container in un repository |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Recupera i log di un container |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Esegui un comando in un container |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Riavvia un container |
