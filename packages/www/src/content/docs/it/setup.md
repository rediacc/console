---
title: "Configurazione della macchina"
description: "Crea una config, aggiungi macchine, esegui il provisioning dei server e configura l'infrastruttura."
category: "Guides"
order: 3
language: it
sourceHash: "19a208e453f7d742"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Configurazione della macchina

Quattro passi mettono in funzione la tua prima macchina: creare una config, registrare il server, eseguirne il provisioning e, facoltativamente, configurare l'infrastruttura per il traffico pubblico.

## Passo 1: Crea una config

Una **config** è un file di configurazione con nome che memorizza le credenziali SSH, le definizioni delle macchine e i mapping dei repository. Considerala come un workspace di progetto.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opzione | Richiesta | Descrizione |
|---------|-----------|-------------|
| `--ssh-key <path>` | Sì | Percorso alla tua chiave SSH privata. La tilde (`~`) viene espansa automaticamente. |
| `--renet-path <path>` | No | Percorso personalizzato al binario renet sulle macchine remote. Usa per impostazione predefinita la posizione di installazione standard. |

Questo crea una config denominata `my-infra` e la memorizza in `~/.config/rediacc/my-infra.json`. La config predefinita (quando non viene fornito alcun nome) viene memorizzata come `~/.config/rediacc/rediacc.json`.

> Puoi avere più config (es. `production`, `staging`, `dev`). Passa da una all'altra con il flag `--config` su qualsiasi comando.

## Passo 2: Aggiungi una macchina

Registra il tuo server remoto come macchina nella config:

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Opzione | Richiesta | Predefinito | Descrizione |
|---------|-----------|-------------|-------------|
| `--ip <address>` | Sì | - | Indirizzo IP o hostname del server remoto |
| `--user <username>` | Sì | - | Nome utente SSH sul server remoto |
| `--port <port>` | No | `22` | Porta SSH |
| `--datastore <path>` | No | `/mnt/rediacc` | Percorso sul server in cui Rediacc memorizza i repository cifrati |

Dopo aver aggiunto la macchina, rdc esegue automaticamente `ssh-keyscan` per recuperare le chiavi host del server. Puoi anche eseguire questa operazione manualmente:

```bash
rdc config machine scan-keys -m server-1
```

Per visualizzare tutte le macchine registrate:

```bash
rdc config machine list
```

## Passo 3: Configura la macchina

Esegui il provisioning del server remoto con tutte le dipendenze richieste:

```bash
rdc config machine setup --name server-1
```

Questo comando:
1. Carica il binario renet sul server tramite SFTP
2. Installa Docker, containerd e cryptsetup (se non presenti)
3. Crea l'utente di sistema `rediacc` (UID 7111)
4. Crea la directory del datastore e la prepara per i repository cifrati

| Opzione | Richiesta | Predefinito | Descrizione |
|---------|-----------|-------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directory del datastore sul server |
| `--datastore-size <size>` | No | `95%` | Quanto dello spazio disco disponibile allocare per il datastore |
| `--debug` | No | `false` | Abilita l'output dettagliato per la risoluzione dei problemi |

> La configurazione deve essere eseguita solo una volta per macchina. È sicuro rieseguirla se necessario.

## Gestione delle chiavi host

Se la chiave host SSH di un server cambia (es. dopo la reinstallazione), aggiorna le chiavi memorizzate:

```bash
rdc config machine scan-keys -m server-1
```

Questo aggiorna il campo `knownHosts` nella tua config per quella macchina.

## Test della connettività SSH

Dopo aver aggiunto una macchina, verifica che sia raggiungibile:

```bash
rdc term connect -m server-1 -c "hostname"
```

Questo apre una connessione SSH alla macchina ed esegue il comando. Se ha successo, la configurazione SSH è corretta.

Per una diagnostica più dettagliata, esegui:

```bash
rdc doctor
```

> **Suggerimento**: per verificare la connettività SSH, esegui `rdc term connect -m <machine> -c "hostname"` oppure usa `ssh` direttamente.

## Configurazione dell'infrastruttura

Per le macchine che devono servire traffico pubblicamente, configura le impostazioni dell'infrastruttura:

### Imposta l'infrastruttura

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opzione | Ambito | Descrizione |
|---------|--------|-------------|
| `--public-ipv4 <ip>` | Macchina | Indirizzo IPv4 pubblico; gli entrypoint proxy vengono creati solo per le famiglie di indirizzi configurate |
| `--public-ipv6 <ip>` | Macchina | Indirizzo IPv6 pubblico; gli entrypoint proxy vengono creati solo per le famiglie di indirizzi configurate |
| `--base-domain <domain>` | Macchina | Dominio base per le applicazioni (es. `example.com`) |
| `--cert-email <email>` | Config | Email per i certificati TLS Let's Encrypt (condivisa tra le macchine) |
| `--cf-dns-token <token>` | Config | Token API DNS Cloudflare per le sfide ACME DNS-01 (condiviso tra le macchine) |
| `--tcp-ports <ports>` | Macchina | Porte TCP aggiuntive da forwardare, separate da virgola (es. `25,143,465,587,993`) |
| `--udp-ports <ports>` | Macchina | Porte UDP aggiuntive da forwardare, separate da virgola (es. `53`) |

Le opzioni con ambito macchina vengono memorizzate per ogni macchina. Le opzioni con ambito config (`--cert-email`, `--cf-dns-token`) sono condivise tra ogni macchina nella config. Impostale una volta e si applicano ovunque.

### Visualizza l'infrastruttura

```bash
rdc config infra show -m server-1
```

### Pubblica sul server

Genera e distribuisce la configurazione del reverse proxy Traefik sul server:

```bash
rdc config infra push -m server-1
```

Questo comando:
1. Distribuisce il binario renet sulla macchina remota
2. Configura il reverse proxy Traefik, il router e i servizi systemd
3. Crea i record DNS Cloudflare per il sottodominio della macchina (`server-1.example.com` e `*.server-1.example.com`) se `--cf-dns-token` è impostato

Il passaggio DNS è automatico e idempotente: crea i record mancanti, aggiorna i record con IP modificati e salta i record già corretti. Se non è configurato alcun token Cloudflare, il DNS viene ignorato con un avviso. I record DNS wildcard per singolo repository (per le route automatiche) vengono creati automaticamente quando esegui `rdc repo up`.

## Provisioning cloud

Invece di creare manualmente le VM, puoi configurare un provider cloud e lasciare che `rdc` esegua il provisioning delle macchine automaticamente usando [OpenTofu](https://opentofu.org/).

### Prerequisiti

Installa OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Assicurati che la tua config SSH abbia una chiave registrata con `rdc`:

```bash
# Legge il file della chiave e incorpora il contenuto in /credentials/ssh.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Aggiungi un provider cloud

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Opzione | Richiesta | Descrizione |
|---------|-----------|-------------|
| `--provider <source>` | Sì* | Sorgente provider nota (es. `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Sì* | Sorgente provider OpenTofu personalizzata (per provider sconosciuti) |
| `--token <token>` | Sì | Token API per il provider cloud |
| `--region <region>` | No | Regione predefinita per le nuove macchine |
| `--type <type>` | No | Tipo/dimensione di istanza predefinita |
| `--image <image>` | No | Immagine OS predefinita |
| `--ssh-user <user>` | No | Nome utente SSH (predefinito: `root`) |

\* È richiesto `--provider` o `--source`. Usa `--provider` per i provider noti (valori predefiniti incorporati). Usa `--source` con i flag aggiuntivi `--resource`, `--ipv4-output`, `--ssh-key-attr` per i provider personalizzati.

### Esegui il provisioning di una macchina

```bash
rdc machine provision --name prod-2 --provider my-linode
```

Questo singolo comando:
1. Crea una VM sul provider cloud tramite OpenTofu
2. Attende la connettività SSH
3. Registra la macchina nella tua config
4. Installa renet e tutte le dipendenze
5. Configura il proxy Traefik e il DNS Cloudflare (rileva automaticamente il dominio base dalle macchine adiacenti, o passa `--base-domain` esplicitamente)

| Opzione | Descrizione |
|---------|-------------|
| `--provider <name>` | Nome del provider cloud (da `add-provider`) |
| `--region <region>` | Sovrascrive la regione predefinita del provider |
| `--type <type>` | Sovrascrive il tipo di istanza predefinito |
| `--image <image>` | Sovrascrive l'immagine OS predefinita |
| `--base-domain <domain>` | Dominio base per l'infrastruttura. Rilevato automaticamente dalle macchine adiacenti se non specificato |
| `--no-infra` | Salta completamente la configurazione dell'infrastruttura (proxy + DNS) |
| `--debug` | Mostra l'output dettagliato del provisioning |

### Deprovisioning di una macchina

```bash
rdc machine deprovision --name prod-2
```

Distrugge la VM tramite OpenTofu e la rimuove dalla tua config. Richiede conferma a meno che non sia usato `--force`. Funziona solo per le macchine create con `machine provision`.

### Elenca i provider

```bash
rdc config provider list
```

## Impostazione dei valori predefiniti

Imposta valori predefiniti in modo da non doverli specificare ad ogni comando:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Macchina predefinita
rdc config set --key team --value my-team                   # Team predefinito per l'archivio di configurazione
```

Dopo aver impostato una macchina predefinita, puoi omettere `-m server-1` dai comandi:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Config multiple

Gestisci più ambienti con config con nome:

```bash
# Crea config separate
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# Usa una config specifica
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Visualizza tutte le config:

```bash
rdc config list
```

Mostra i dettagli della config corrente:

```bash
rdc config show
```
