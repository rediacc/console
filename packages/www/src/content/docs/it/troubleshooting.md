---
title: "Risoluzione dei Problemi"
description: "Soluzioni per i problemi più comuni con SSH, configurazione, repository, servizi e Docker."
category: "Guides"
order: 10
language: it
sourceHash: "17dc03eb0589d606"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Risoluzione dei Problemi

Problemi comuni e come risolverli. In caso di dubbio, inizia con `rdc doctor` per eseguire una diagnostica completa.

## Connessione SSH Fallita

- Verifica di poter connetterti manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Esegui `rdc config machine scan-keys -m server-1` per aggiornare le chiavi host
- Controlla che la porta SSH corrisponda: `--port 22`
- Testa con un comando semplice: `rdc term connect -m server-1 -c "hostname"`

## Mancata Corrispondenza della Chiave Host

Se un server è stato reinstallato o le sue chiavi SSH sono cambiate, vedrai "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

Questo recupera le chiavi host aggiornate e aggiorna la tua configurazione.

## Configurazione della Macchina Fallita

- Assicurati che l'utente SSH abbia accesso sudo senza password, oppure configura `NOPASSWD` per i comandi richiesti
- Controlla lo spazio su disco disponibile sul server
- Esegui con `--debug` per output dettagliato: `rdc config machine setup --name server-1 --debug`

## Problemi di Configurazione Specifici per Distribuzione

I cinque sistemi operativi server ufficialmente supportati (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) sono distribuiti con policy di sicurezza e gestori di pacchetti diversi. La maggior parte delle configurazioni "funziona subito"; i casi seguenti coprono quelli che non lo fanno.

### Negazioni SELinux (Fedora 43, Oracle Linux 10)

Entrambi eseguono SELinux in modalità enforcing. rdc setup non installa una policy SELinux personalizzata; il daemon Docker per repository viene eseguito nel contesto standard `container_t`. Se la configurazione fallisce con negazioni AVC, controlla il log di audit e identifica il dominio:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Oppure:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Se una negazione punta al binario renet o a un percorso file specifico, la correzione è quasi sempre rietichettare (`restorecon -v /path`) piuttosto che disabilitare SELinux. Come soluzione temporanea mentre indaghi, `sudo setenforce 0` porta il sistema in modalità permissive. Riabilita con `sudo setenforce 1` una volta confermato che la rietichettatura sia stabile.

### Negazioni AppArmor (Ubuntu 24.04, openSUSE Leap 16.0)

Entrambi eseguono AppArmor per impostazione predefinita; il daemon Docker per repository usa il profilo container predefinito. Se un container all'interno di un repository viene bloccato:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU è il caso noto che colpisce AppArmor. Renet imposta automaticamente `security_opt: apparmor=unconfined` sui container etichettati con `rediacc.checkpoint=true`. Non dovresti dover configurare profili AppArmor tu stesso per altro. Consulta le note su CRIU in [Rules of Rediacc](/en/docs/rules-of-rediacc).

### Firme di errore del gestore di pacchetti

| OS | Gestore pacchetti | Errore tipico | Risoluzione |
|----|-----------------|---------------|------------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cache edge Cloudflare dietro l'origine. Riprova `apt-get update` dopo circa 15 secondi; il controllo di integrità passa al prossimo tentativo. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | I metadati del repository RPM nella cache su disco sono obsoleti. Esegui `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Esegui `sudo zypper refresh rediacc` una volta; le installazioni successive dovrebbero funzionare. |

### Modulo btrfs mancante (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Se `rdc config machine setup` o `renet system check-btrfs` fallisce con:

```
Module btrfs not found
```

...il server sta eseguendo il kernel stock di RHEL 10, che non include il modulo btrfs in-tree. Non si tratta di un bug di Rediacc; RHEL 10 ha rimosso btrfs intenzionalmente. La correzione è eseguire **Oracle Linux 10**. Oracle 10 usa per impostazione predefinita l'Unbreakable Enterprise Kernel (UEK), che mantiene btrfs. Consulta [Requirements -> Why UEK?](/en/docs/requirements) per la storia completa.

## Creazione del Repository Fallita

- Verifica che la configurazione sia stata completata: la directory del datastore deve esistere
- Controlla lo spazio su disco sul server
- Assicurati che il binario renet sia installato (esegui nuovamente la configurazione se necessario)

## I Servizi Non Si Avviano

- Controlla la sintassi del Rediaccfile: deve essere Bash valido
- Assicurati che il tuo Rediaccfile usi `renet compose --` (non `docker compose`)
- Verifica che le immagini Docker siano accessibili (considera `renet compose -- pull` in `up()`)
- Controlla i log del container usando il socket Docker del repository:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Oppure visualizza tutti i container:

```bash
rdc machine containers --name server-1
```

## Errori di Permesso Negato

- Le operazioni sui repository richiedono i privilegi di root sul server (renet viene eseguito tramite `sudo`)
- Verifica che il tuo utente SSH sia nel gruppo `sudo`
- Controlla che la directory del datastore abbia i permessi corretti

## Problemi con il Socket Docker

Ogni repository ha il proprio daemon Docker. Quando esegui comandi Docker manualmente, devi specificare il socket corretto:

```bash
# Usando rdc term (configurato automaticamente):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Oppure manualmente con il socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Sostituisci `2816` con l'ID di rete del tuo repository (trovabile in `rediacc.json` o `rdc repo status`).

## `docker run` non ha rete, `apt update` fallisce, `curl` si blocca

All'interno di una shell di repository, eseguire un container senza `--network host` ti fornisce un container isolato con solo un'interfaccia loopback, senza DNS e senza connettività in uscita. Comandi come `apt update`, `pip install`, `curl https://...`, o qualsiasi richiesta di rete falliranno immediatamente con errori DNS.

Questo è intenzionale. Il modello di rete di Rediacc è **host networking per ogni servizio**, imposto da `renet compose`. Un bridge Docker predefinito con NAT aggirerebbe l'isolamento loopback a livello kernel che impedisce a un repo di raggiungere i servizi di un altro repo, quindi il daemon Docker per repository (`FlavorRediacc`) è configurato con `"bridge": "none"` e `"iptables": false`. Non esiste un bridge instradabile a cui un container `docker run` normale possa connettersi. (I daemon Hub per utente (`FlavorHub`) utilizzati dagli ambienti di sviluppo sono l'eccezione: abilitano bridge e iptables in modo che i container dell'utente abbiano connettività di rete in uscita.)

**Per ottenere accesso alla rete in un container ad hoc, usa host networking:**

```bash
# All'interno di una shell di repository (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Ora apt update, curl, pip install funzionano tutti.
```

**Per i servizi di produzione, usa un Rediaccfile con `renet compose`** invece di `docker run` diretto. `renet compose` inietta automaticamente `network_mode: host`, etichette IP di servizio ed etichette di routing Traefik. Consulta [Services](/en/docs/services) per i dettagli.

## VS Code: Permesso Negato sui File Sandbox

Quando ci si connette con `rdc vscode connect -m <machine> -r <repo>` dopo una sessione VS Code precedente, le versioni precedenti di renet producevano errori come `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied`. La causa: proprietà mista dei file all'interno della directory sandbox, dove sia l'utente SSH che l'utente interno `rediacc` avevano scritto file.

Le versioni moderne di renet risolvono questo problema:

- Creando lo spazio di lavoro sandbox per repository (`/mnt/rediacc/.interim/sandbox/<repo>/`) con gruppo `rediacc` e il bit set-group-ID (mode `2775`), in modo che ogni file scritto al di sotto erediti il gruppo corretto.
- Applicando umask `002` all'interno del runtime sandbox in modo che i nuovi file vengano creati con permesso di scrittura per il gruppo (`0664`/`0775`).
- Normalizzando un sottoalbero `.vscode-server/` esistente all'avvio in modo che i file obsoleti precedenti alla correzione vengano riparati automaticamente.

Se vedi ancora errori di permesso, riavvia il daemon Docker del repository una volta con `sudo systemctl restart rediacc-docker-<network-id>` da una shell sulla macchina in modo che la normalizzazione venga eseguita, poi riprova `rdc vscode connect`.

## Il Daemon Non Si Avvia Dopo un Aggiornamento di renet

Prima di ogni avvio, `renet daemon start-foreground` riscrive `daemon.json` e `containerd.toml` nella directory di configurazione del repository dai template correnti, quindi un repository la cui configurazione è stata generata da una versione precedente di renet acquisisce automaticamente il nuovo formato. Non è necessario eseguire alcun comando di migrazione né rigenerare manualmente l'unità systemd. Riavvia semplicemente il servizio:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Se l'unità continua a fallire, controlla il journal per un errore specifico:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Container Creati sul Daemon Docker Sbagliato

Se i tuoi container appaiono sul daemon Docker del sistema host invece del daemon isolato del repository, la causa più comune è l'uso di `sudo docker` all'interno di un Rediaccfile.

`sudo` reimposta le variabili d'ambiente, quindi `DOCKER_HOST` viene perso e Docker usa il socket di sistema (`/var/run/docker.sock`). Rediacc blocca questo automaticamente, ma se lo incontri:

- **Usa `docker` direttamente**, le funzioni del Rediaccfile vengono già eseguite con privilegi sufficienti
- Se devi usare sudo, usa `sudo -E docker` per preservare le variabili d'ambiente
- Controlla il tuo Rediaccfile per eventuali comandi `sudo docker` e rimuovi il `sudo`

## Il Terminale Non Funziona

Se `rdc term` non riesce ad aprire una finestra del terminale:

- Usa la modalità inline con `-c` per eseguire comandi direttamente:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Forza il terminale esterno con `--external` se la modalità inline ha problemi
- Su Linux, assicurati di avere `gnome-terminal`, `xterm` o un altro emulatore di terminale installato

## Esegui la Diagnostica

```bash
rdc doctor
```

Questo controlla il tuo ambiente, l'installazione di renet, la configurazione e lo stato di autenticazione. Ogni controllo riporta OK, Avviso o Errore con una breve spiegazione.
