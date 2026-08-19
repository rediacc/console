---
title: Guida rapida alla CLI RDC
description: "Riferimento rapido per rdc: configurazioni, repository, macchine, sincronizzazione file e container. Opzioni complete: aggiungi --help a qualsiasi comando."
category: Guides
tags:
  - cli
order: 3
cardGrid: true
language: it
sourceHash: "14ed5791afa44326"
sourceCommit: "45cd71f8a80949d4cd621f233377c48715bbf531"
---

# Guida rapida alla CLI RDC

Non tutti i comandi `rdc` sono elencati qui, solo quelli più usati in ogni deployment. Per il set completo di opzioni, esegui qualsiasi comando rdc con `--help`. I casi limite e le opzioni poco usate si trovano nel riferimento completo.

## Ciclo di vita dei repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo create <repo> -m <machine>` | Crea un nuovo repository su una macchina |
| `rdc repo up <repo>@<machine>` | Esegui il deploy o aggiorna un repository |
| `rdc repo down <repo>@<machine>` | Arresta un repository |
| `rdc repo delete <repo>@<machine>` | Elimina un repository |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Crea un fork di un repository (quasi istantaneo, reflink BTRFS) |
| `rdc repo promote <repo>:<tag>` | Promuovi un fork convalidato in produzione con il nome del repository originale |
| `rdc repo list` | Elenca tutti i repository con nome e GUID |
| `rdc repo resize <repo> --size <size>` | Ridimensiona il volume di un repository fermo |
| `rdc repo expand <repo> --size <size>` | Espandi sul posto il volume di un repository in esecuzione |

## Segreti per repository

Credenziali di deploy accessibili solo in scrittura. `get` restituisce solo il digest. Il valore non è mai restituito. Consulta [Repositories § Secrets](/it/docs/repositories#secrets) per la guida completa.

| Comando | Descrizione |
|---------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Crea un nuovo segreto (`--current ""` per la prima scrittura) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Sovrascrive un segreto esistente (precondizione in stile passwd) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Sovrascrive senza verificare il valore precedente (registrato come rotazione) |
| `rdc repo secret list <repo>` | Elenca i nomi dei segreti e le modalità di consegna (mai i valori, mai i digest) |
| `rdc repo secret get <repo> --key <KEY>` | Mostra il digest e la modalità del segreto (nessun valore in chiaro, mai) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Elimina un segreto |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Elimina senza verificare il valore precedente |

> I fork non ereditano segreti. Impostali esplicitamente sul fork con `rdc repo secret set <repo>:<tag>`.

## Backup e ripristino

| Comando | Descrizione |
|---------|-------------|
| `rdc repo push ... --bwlimit <limit>` | Limita la banda rsync durante il push (es. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limita la banda rsync durante il pull |
| `rdc repo push ... --checkpoint` | Esegui il checkpoint dei container prima del push |
| `rdc backup manifests <repo-ref>` | Elenca gli snapshot contenuti nello storage a chunk |
| `rdc backup browse <repo-ref>` | Elenca i file contenuti in un repository (locale, sola lettura) |
| `rdc backup snapshot <repo>` | Carica uno snapshot su storage a chunk: prima l'inventario completo, poi solo le celle modificate |
| `rdc backup snapshot <repo> --dry-run` | Pianifica lo snapshot senza caricare; riporta cosa verrebbe spostato |
| `rdc backup verify <repo>` | Verifica l'ancora di backup di un repository rispetto allo storage a chunk |
| `rdc backup usage` | Mostra i byte memorizzati nello storage a chunk rispetto alla tua quota |
| `rdc backup manifests <repo>` | Elenca i manifest degli snapshot registrati sul server |
| `rdc storage browse <storage>` | Esplora il contenuto dello storage |

## Migrazione dei repository

| Comando | Descrizione |
|---------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Sposta un repository tra macchine |
| `rdc repo migrate ... --provision` | Esegui il provisioning sulla destinazione prima del trasferimento |
| `rdc repo migrate ... --checkpoint` | Esegui il checkpoint prima della migrazione |
| `rdc repo migrate ... --skip-dns` | Salta l'aggiornamento DNS dopo la migrazione |
| `rdc repo migrate ... --bwlimit <limit>` | Limita la banda di trasferimento |

## Strategie di backup

| Comando | Descrizione |
|---------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Crea o aggiorna una strategia di backup con nome |
| `rdc backup strategy list` | Elenca tutte le strategie di backup definite |
| `rdc backup strategy show <name>` | Mostra i dettagli di una strategia |
| `rdc backup strategy remove <name>` | Rimuove una strategia |
| `rdc backup schedule -m <machine>` | Distribuisce le strategie di backup configurate su una macchina |

## Operazioni di backup

| Comando | Descrizione |
|---------|-------------|
| `rdc backup schedule -m <machine>` | Distribuisce le strategie collegate come timer systemd |
| `rdc backup schedule -m <machine> --dry-run` | Anteprima delle unità timer senza distribuzione (token mascherati) |
| `rdc backup run -m <machine>` | Esegue immediatamente tutte le strategie collegate |
| `rdc backup run <name> -m <machine>` | Esegue immediatamente una strategia specifica |
| `rdc backup status -m <machine>` | Mostra lo stato dei timer e i risultati recenti |
| `rdc backup status <name> -m <machine>` | Mostra lo stato di una strategia specifica |
| `rdc backup cancel -m <machine>` | Annulla i backup in esecuzione |
| `rdc backup cancel <name> -m <machine>` | Annulla un backup specifico in esecuzione |

## Gestione delle macchine

| Comando | Descrizione |
|---------|-------------|
| `rdc machine status <machine>` | Stato completo della macchina (sistema, container, servizi, repository, rete) |
| `rdc machine status <machine> --system` | Solo informazioni di sistema |
| `rdc machine status <machine> --containers` | Solo elenco dei container |
| `rdc machine status <machine> --repositories` | Solo elenco dei repository |
| `rdc machine status <machine> --services` | Solo elenco dei servizi |
| `rdc machine status <machine> --network` | Solo informazioni di rete |
| `rdc machine status <machine> --block-devices` | Solo informazioni sui dispositivi a blocchi |
| `rdc machine list` | Elenca tutte le macchine nella configurazione |
| `rdc machine setup <machine>` | Esegui il provisioning iniziale della macchina |
| `rdc machine health <machine>` | Verifica lo stato di salute di una macchina |
| `rdc machine scan-keys <machine>` | Aggiorna le chiavi host SSH dopo una ricostruzione |
| `rdc machine prune <machine>` | Rimuove le risorse inutilizzate dalla macchina |
| `rdc machine deprovision <machine>` | Esegui il deprovisioning completo di una macchina |

## Terminale e sincronizzazione

| Comando | Descrizione |
|---------|-------------|
| `rdc term connect <machine>` | Apri un terminale SSH alla macchina |
| `rdc term connect <repo>@<machine>` | Apri un terminale SSH al repository (imposta DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Esegui un comando sulla macchina |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Carica uno o più file o directory locali nel repository |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Carica un singolo file locale in un percorso remoto esplicito |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Scarica una directory del repository in locale |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Scarica un singolo file remoto in una directory locale |
| `rdc vscode connect <repo>@<machine>` | Apri una sessione VS Code Remote SSH |
| `rdc vscode list` | Elenca le configurazioni SSH create da `vscode connect` |
| `rdc vscode cleanup --all` | Rimuovi tutte le configurazioni SSH scritte da `vscode connect` |
| `rdc repo tunnel <repo> -c <container> --port <port>` | Inoltra la porta di un container via SSH |

## Configurazione

| Comando | Descrizione |
|---------|-------------|
| `rdc config init <name>` | Crea un file di configurazione con nome |
| `rdc config list` | Elenca tutte le configurazioni su questa macchina |
| `rdc config set machine <alias>` | Punta un alias verso un'altra macchina |
| `rdc machine add <machine> --ip <host> --user <user>` | Aggiungi una macchina alla configurazione |
| `rdc storage import rclone.conf` | Importa i provider di storage da una configurazione rclone |
| `rdc storage list` | Elenca i provider di storage configurati |
| `rdc backup strategy set ...` | Definisci una strategia di backup con nome |
| `rdc --config <name> <command>` | Usa un file di configurazione con nome |

## Debug e via di uscita

| Comando | Descrizione |
|---------|-------------|
| `rdc repo logs <repo>@<machine> -c <container> --lines 200 --follow` | Trasmetti i log di un container (preferito) |
| `rdc repo exec <repo>@<machine> -c <container> -- <command>` | Esegui un comando in un container (preferito) |
| `rdc repo exec <repo>@<machine> -c <container> -i -- bash` | Apri una shell interattiva nel container |
| `rdc term connect <repo>@<machine> -c "docker ps"` | Elenca i container in un repository |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Recupera i log di un container |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Esegui un comando in un container |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Riavvia un container |
