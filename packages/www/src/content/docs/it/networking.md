---
title: "Rete"
description: "Esponi i servizi con il reverse proxy, le etichette Docker, i certificati TLS, il DNS e il forwarding TCP/UDP. È tutto configurabile e già pronto all'uso."
category: "Guides"
order: 6
language: it
sourceHash: "d60a43cd573517a1"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Rete

Questa pagina spiega come i servizi in esecuzione all'interno di daemon Docker isolati diventano accessibili da Internet. Copre il sistema di reverse proxy, le etichette Docker per il routing, i certificati TLS, il DNS e il forwarding TCP/UDP.

Per come i servizi ottengono i loro IP di loopback e il sistema di slot `.rediacc.json`, vedi [Servizi](/en/docs/services#service-networking-rediaccjson).

## Isolamento di Rete

Ogni repository è automaticamente isolato a livello di kernel usando hook di rete. Questo richiede Linux kernel 6.1 o successivo. Non è necessaria alcuna configurazione.

- **Riscrittura automatica del bind**: I servizi possono fare bind su `0.0.0.0` o `127.0.0.1` come di consueto. Il kernel riscrive in modo trasparente l'indirizzo all'IP di loopback assegnato al servizio. Non è necessario fare bind esplicitamente su `${SERVICE_IP}`.
- **Blocco delle connessioni tra repository**: Se un servizio tenta di connettersi a un IP di loopback al di fuori della sottorete `/26` del suo repository, il kernel lo blocca. Un processo nel repository A non può raggiungere i servizi nel repository B.
- **Nessuna modifica all'applicazione richiesta**: I servizi usano `0.0.0.0` o `localhost` per il binding, e il kernel garantisce che ascoltino solo sul loro IP di loopback corretto. L'isolamento è completamente trasparente.

## Come Funziona

Rediacc usa un sistema proxy a due componenti per instradare il traffico esterno verso i container:

1. **Route server**, un servizio systemd che scopre i container in esecuzione su tutti i daemon Docker dei repository. Ispeziona le etichette dei container e genera la configurazione di routing, servita come endpoint YAML.
2. **Traefik**, un reverse proxy che interroga il route server ogni 5 secondi e applica le route scoperte. Gestisce il routing HTTP/HTTPS, la terminazione TLS e il forwarding TCP/UDP.

Il flusso è il seguente:

```
Internet -> Traefik (ports 80/443/TCP/UDP)
               | polls every 5s
           Route Server (discovers containers)
               | inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               |
           Containers (bound to 127.x.x.x loopback IPs)
```

Quando aggiungi le etichette giuste a un container e lo avvii con `renet compose`, diventa automaticamente instradabile, senza necessità di configurazione manuale del proxy.

> Il binario del route server viene mantenuto sincronizzato con la tua versione CLI. Quando la CLI aggiorna il binario renet su una macchina, il route server viene riavviato automaticamente (circa 1-2 secondi). Questo non causa downtime: Traefik continua a servire il traffico con la sua ultima configurazione nota durante il riavvio e raccoglie la nuova configurazione al prossimo polling. Le connessioni client esistenti non vengono influenzate. I tuoi container applicativi non vengono toccati.

## Etichette Docker

Il routing è controllato dalle etichette dei container Docker. Ci sono due livelli:

### Livello 1: Etichette `rediacc.*` (Automatiche)

Queste etichette vengono **iniettate automaticamente** da `renet compose` all'avvio dei servizi. Non è necessario aggiungerle manualmente.

| Etichetta | Descrizione | Esempio |
|-------|-------------|---------|
| `rediacc.service_name` | Identità del servizio | `myapp` |
| `rediacc.service_ip` | IP di loopback assegnato | `127.0.11.2` |
| `rediacc.network_id` | ID daemon del repository | `2816` |
| `rediacc.repo_name` | Nome del repository | `marketing` |
| `rediacc.tcp_ports` | Porte TCP su cui il servizio è in ascolto | `8080,8443` |
| `rediacc.udp_ports` | Porte UDP su cui il servizio è in ascolto | `53` |

Quando un container ha solo etichette `rediacc.*` (nessun `traefik.enable=true`), il route server genera una **auto-route** usando il nome del repository e il sottodominio della macchina:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Ad esempio, un servizio chiamato `myapp` in un repository chiamato `marketing` sulla macchina `server-1` con dominio base `example.com` ottiene:

```
myapp.marketing.server-1.example.com
```

Per i fork, il nome del servizio viene combinato con la parola riservata `fork` e il tag:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Ad esempio, un fork di `marketing` con tag `staging` ottiene:

```
myapp-fork-staging.marketing.server-1.example.com
```

Ogni URL di fork si trova nel sottodominio del repository genitore ed è coperto dal suo certificato wildcard esistente, quindi non è necessario alcun nuovo certificato. Il separatore `-fork-` previene le collisioni con qualsiasi nome di servizio reale nel repository di produzione. Per i servizi con domini personalizzati, usa le etichette di Livello 2 o l'etichetta `rediacc.domain`.

#### Dominio Personalizzato tramite `rediacc.domain`

Puoi impostare un dominio personalizzato per un servizio usando l'etichetta `rediacc.domain` nel tuo `docker-compose.yml`. Sono supportati sia i nomi brevi che i domini completi:

```yaml
labels:
  # Short name, resolved to cloud.example.com using the machine's baseDomain
  - "rediacc.domain=cloud"

  # Full domain, used as-is
  - "rediacc.domain=cloud.example.com"
```

Un valore senza punti viene trattato come nome breve e riceve automaticamente il `baseDomain` della macchina aggiunto. Un valore con punti viene usato come dominio completo. Questo si applica sia alla generazione dell'auto-route che alla visualizzazione CLI.

Quando `machineName` è configurato, i servizi con dominio personalizzato ottengono **due route**: una sul dominio base (`cloud.example.com`) e una sul sottodominio della macchina (`cloud.server-1.example.com`).

### Livello 2: Etichette `traefik.*` (Definite dall'Utente)

Aggiungi queste etichette al tuo `docker-compose.yml` quando desideri routing con dominio personalizzato, TLS o entrypoint specifici. Impostare `traefik.enable=true` indica al route server di usare le tue regole personalizzate invece di generare un'auto-route.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Questi usano la [sintassi delle etichette Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/) standard.

> **Suggerimento:** I servizi solo interni (database, cache, code di messaggi) **non** devono avere `traefik.enable=true`. Necessitano solo delle etichette `rediacc.*`, che vengono iniettate automaticamente.

## Esposizione dei Servizi HTTP/HTTPS

### Prerequisiti

1. Infrastruttura configurata sulla macchina ([Setup Macchina, Configurazione Infrastruttura](/en/docs/setup#infrastructure-configuration)):

   ```bash
   # Shared credentials (once per config, applies to all machines)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Machine-specific settings
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. Record DNS che puntano il tuo dominio all'IP pubblico del server (vedi [Configurazione DNS](#configurazione-dns) di seguito).

### Aggiunta delle Etichette

Aggiungi le etichette `traefik.*` ai servizi che vuoi esporre nel tuo `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # No traefik labels, database is internal only
```

| Etichetta | Scopo |
|-------|---------|
| `traefik.enable=true` | Abilita il routing Traefik personalizzato per questo container |
| `traefik.http.routers.{name}.rule` | Regola di routing, tipicamente `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Su quali porte ascoltare: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Resolver del certificato, usa `letsencrypt` per Let's Encrypt automatico |
| `traefik.http.services.{name}.loadbalancer.server.port` | La porta su cui la tua applicazione è in ascolto all'interno del container |

`{name}` nelle etichette e' un identificatore arbitrario. Deve solo restare coerente tra le etichette router/servizio/middleware correlate.

> **Nota:** Le etichette `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) vengono iniettate automaticamente da `renet compose`. Non è necessario aggiungerle al tuo file compose.

## Certificati TLS

I certificati TLS vengono ottenuti automaticamente tramite Let's Encrypt usando la sfida DNS-01 di Cloudflare. Le credenziali vengono configurate una volta per configurazione (condivise tra tutte le macchine):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Le auto-route usano **certificati wildcard** a livello di sottodominio del repository (`*.marketing.server-1.example.com`) invece di certificati per servizio. Il certificato viene provisioning automaticamente da Traefik al primo `repo up`; nessun passaggio manuale richiesto. I fork riutilizzano il wildcard esistente del repository genitore, quindi non attivano mai una nuova richiesta di certificato. Le route con dominio personalizzato usano wildcard a livello di macchina (`*.server-1.example.com`).

> **Richiede le credenziali Cloudflare.** I certificati wildcard usano la sfida DNS-01. Senza `--cf-dns-token` (e opzionalmente `--cert-email`), Traefik non può completare la sfida e HTTPS non funzionerà. HTTP rimane funzionale. Configura le credenziali con `rdc config infra set` prima del primo deploy.

Per le route di Livello 2 con `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, i SAN del dominio wildcard vengono iniettati automaticamente in base all'hostname della route.

Il token API DNS di Cloudflare necessita del permesso `Zone:DNS:Edit` per i domini che vuoi proteggere.

### Ciclo di Vita del Certificato TLS

Il percorso completo che un certificato Let's Encrypt percorre dall'emissione ai container di ogni repository:

1. **Emissione sull'host.** Un container Traefik a livello di macchina (`rediacc-proxy`, distribuito in `/opt/rediacc/proxy/`) gestisce il rinnovo ACME. Memorizza tutto lo stato in `/opt/rediacc/proxy/letsencrypt/acme.json` sull'host. Il rinnovo si attiva automaticamente circa 30 giorni prima della scadenza; nessuna azione dell'operatore necessaria finché `--cf-dns-token` è configurato.

2. **Dump per repository (opzionale).** I servizi che necessitano di file di certificato all'interno del proprio container (ad esempio, un server di posta che legge direttamente un `.pem`) distribuiscono un piccolo container `traefik-certs-dumper` insieme a sé stessi. Il dumper monta in bind `/opt/rediacc/proxy/letsencrypt` in sola lettura e scrive il certificato estratto + la chiave nel volume di dati del repository come `cert.pem` / `key.pem`. Perché questo funzioni, il daemon Docker per repository deve avere `/opt/rediacc/proxy` nella sua lista di autorizzazioni mount-namespace. Questo è già incluso per impostazione predefinita.

3. **Cache lato client (`rediacc.json`).** La CLI memorizza nella cache una copia compressa di `acme.json` sotto `acmeCertCache` nel tuo file di configurazione, indicizzata per `baseDomain`. Questo consente a più macchine di condividere i certificati (tramite `rdc config cert-cache push -m <machine>`) e funge da inventario offline.

**Trigger di sincronizzazione per la cache client:**

- Automaticamente dopo `rdc repo up`, ma solo se la cache locale per il `baseDomain` della macchina ha più di 6 ore. Le cache fresche vengono lasciate intatte in modo che i deploy consecutivi non sovraccarichino SSH.
- Su richiesta: `rdc config cert-cache pull -m <machine>` (pull forzato) o `rdc machine query --name <machine> --sync-certs` (pull come effetto collaterale di una query di stato).
- Su `rdc config infra push`, la cache viene inviata alla macchina (i certificati locali con scadenza più lunga vincono su quelli remoti).

**Manutenzione della cache:**

- Le voci auto-route obsolete (vecchi domini con tag network-ID come `service-3200.rediacc.io`) vengono eliminate durante ogni pull.
- I certificati il cui `notAfter` è a più di 7 giorni nel passato vengono rimossi definitivamente. Sono inerti e gonfiano solo la cache.
- `rdc config cert-cache clear` cancella tutto; `rdc config cert-cache status` mostra l'inventario.

**Risoluzione dei problemi:** se `traefik-certs-dumper` va in crashloop con `/traefik/acme.json: no such file or directory`, il daemon per repository non riesce a vedere il letsencrypt store dell'host. Verifica (a) che `/opt/rediacc/proxy/letsencrypt/acme.json` esista sull'host (questa è responsabilità del `rediacc-proxy` a livello host), e (b) che il daemon per repository sia stato avviato con un renet abbastanza recente da autorizzare `/opt/rediacc/proxy`. Ridistribuisci il repository con `rdc repo up` dopo aver aggiornato renet per applicare.

> **Sperimentale:** La cadenza di auto-sincronizzazione e la potatura basata sulla scadenza sono state rilasciate in renet 0.9+. Le versioni precedenti di CLI/renet usano la sincronizzazione puramente manuale tramite `rdc config cert-cache pull`.

## Forwarding TCP/UDP

Per i protocolli non HTTP (server di posta, DNS, database esposti esternamente), usa il forwarding TCP/UDP.

### Passo 1: Registra le Porte

Aggiungi le porte richieste durante la configurazione dell'infrastruttura:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Questo crea entrypoint Traefik denominati `tcp-{port}` e `udp-{port}`.

> Dopo aver aggiunto o rimosso porte, esegui sempre di nuovo `rdc config infra push` per aggiornare la configurazione del proxy.

### Passo 2: Aggiungi le Etichette TCP/UDP

Usa le etichette `traefik.tcp.*` o `traefik.udp.*` nel tuo file compose:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Concetti chiave:
- **`HostSNI(\`*\`)`** corrisponde a qualsiasi hostname (per i protocolli che non inviano SNI, come SMTP semplice)
- **`tls.passthrough=true`** significa che Traefik inoltra la connessione TLS raw senza decriptare; l'applicazione gestisce TLS da sola
- I nomi degli entrypoint seguono la convenzione `tcp-{port}` o `udp-{port}`

### Esempio TCP Semplice (Database)

Per esporre un database esternamente senza TLS passthrough (Traefik inoltra TCP raw):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

La porta 5432 è preconfigurata (vedi di seguito), quindi non è necessaria alcuna configurazione `--tcp-ports`.

> **Nota sulla sicurezza:** Esporre un database a Internet è un rischio. Usa questa opzione solo quando i client remoti necessitano di accesso diretto. Per la maggior parte delle configurazioni, mantieni il database interno e connettiti tramite la tua applicazione.

### Porte Preconfigurate

Le seguenti porte TCP/UDP hanno entrypoint per impostazione predefinita (non è necessario aggiungerle tramite `--tcp-ports`). Gli entrypoint vengono generati solo per le famiglie di indirizzi configurate; gli entrypoint IPv4 richiedono `--public-ipv4`, gli entrypoint IPv6 richiedono `--public-ipv6`:

| Porta | Protocollo | Uso Comune |
|------|----------|------------|
| 80 | HTTP | Web (reindirizzamento automatico a HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | Intervallo dinamico (auto-allocazione) |

## Configurazione DNS

### DNS Automatico (Cloudflare)

Quando `--cf-dns-token` è configurato, `rdc config infra push` crea automaticamente record DNS per il sottodominio della macchina in Cloudflare:

| Record | Tipo | Contenuto | Creato da |
|--------|------|---------|------------|
| `server-1.example.com` | A / AAAA | IP pubblico della macchina | `push-infra` |
| `*.server-1.example.com` | A / AAAA | IP pubblico della macchina | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | IP pubblico della macchina | `repo up` |

I record a livello di macchina vengono creati da `push-infra` e coprono le route con dominio personalizzato (`rediacc.domain`). I record wildcard per repository vengono creati automaticamente da `repo up` e coprono le auto-route per quel repository.

Questa operazione e' idempotente: i record esistenti vengono aggiornati se l'IP cambia, e lasciati invariati se gia' corretti.

Il wildcard del dominio base (`*.example.com`) deve essere creato manualmente se usi etichette di dominio personalizzato come `rediacc.domain=erp`.

### DNS Manuale

Se non usi Cloudflare o gestisci il DNS manualmente, crea record A (IPv4) e/o AAAA (IPv6):

```
# Machine subdomain (for custom domain routes like rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Per-repo wildcards (for auto-routes like myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Base domain wildcard (for custom domain services like rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Con il DNS Cloudflare configurato, i record wildcard per repository vengono creati automaticamente da `repo up`. Con più macchine, ogni macchina ottiene i propri record DNS che puntano al proprio IP.

## Middleware

I middleware Traefik modificano le richieste e le risposte. Applicali tramite etichette.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Buffering per Upload di File di Grandi Dimensioni

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Middleware Multipli

Concatena i middleware separandoli con virgole:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Per l'elenco completo dei middleware disponibili, vedi la [documentazione dei middleware Traefik](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnostiche

Se un servizio non è accessibile, connettiti via SSH al server e controlla gli endpoint del route server:

### Controllo di Salute

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Mostra lo stato generale, il numero di router e servizi scoperti e se le auto-route sono abilitate.

### Route Scoperte

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Elenca tutti i router HTTP, TCP e UDP con le loro regole, entrypoint e servizi backend.

### Allocazioni delle Porte

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Mostra i mapping delle porte TCP e UDP per le porte allocate dinamicamente.

### Problemi Comuni

| Problema | Causa | Soluzione |
|---------|-------|----------|
| Servizio non nelle route | Container non in esecuzione o etichette mancanti | Verifica con `docker ps` sul daemon del repository; controlla le etichette |
| Certificato non emesso | DNS non punta al server, o token Cloudflare non valido | Verifica la risoluzione DNS; controlla i permessi del token API Cloudflare |
| 502 Bad Gateway | L'applicazione non è in ascolto sulla porta dichiarata | Verifica che l'app sia in esecuzione e che la porta corrisponda a `loadbalancer.server.port` |
| Porta TCP non raggiungibile | Porta non registrata nell'infrastruttura | Esegui `rdc config infra set --tcp-ports ...` e `push-infra` |
| Route server con versione obsoleta | Il binario è stato aggiornato ma il servizio non è stato riavviato | Avviene automaticamente durante il provisioning; manuale: `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN non raggiungibile | Indirizzi relay memorizzati nella cache all'avvio | Ricrea il servizio dopo modifiche DNS o IP in modo da raccogliere la nuova configurazione di rete |

## Esempio Completo

Questo distribuisce un'applicazione web con un database PostgreSQL. L'app è accessibile pubblicamente su `app.example.com` con TLS; il database è solo interno.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # No traefik labels, internal only
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Crea un record A che punta `app.example.com` all'IP pubblico del tuo server:

```
app.example.com   A   203.0.113.50
```

### Deploy

```bash
rdc repo up --name my-app -m server-1
```

Nel giro di pochi secondi, il route server scopre il container, Traefik raccoglie la route, richiede un certificato TLS e `https://app.example.com` è attivo.
