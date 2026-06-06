---
title: "Guida alla Migrazione"
description: "Migra i progetti esistenti in repository Rediacc cifrati."
category: "Guides"
order: 11
language: it
sourceHash: "4517142676f9fa8f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Guida alla Migrazione

Migra un progetto esistente -- file, servizi Docker, database -- da un server tradizionale o da un ambiente di sviluppo locale in un repository Rediacc cifrato.

## Prerequisiti

- CLI `rdc` installato ([Installazione](/en/docs/installation))
- Una macchina aggiunta e configurata ([Setup](/en/docs/setup))
- Spazio su disco sufficiente sul server per il tuo progetto (verifica con `rdc machine query`)

## Passo 1: Crea un Repository

Crea un repository cifrato dimensionato per il tuo progetto. Alloca spazio extra per le immagini Docker e i dati dei container.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **Suggerimento:** Puoi ridimensionare in seguito con `rdc repo resize` se necessario, ma il repository deve essere smontato prima. È più semplice iniziare con spazio sufficiente.

## Passo 2: Carica i Tuoi File

Usa `rdc repo sync upload` per trasferire i file del tuo progetto nel repository.

```bash
# Anteprima di ciò che verrà trasferito (nessuna modifica effettuata)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Carica i file
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

Il repository deve essere montato prima del caricamento. Se non lo è già:

```bash
rdc repo mount --name my-project -m server-1
```

Per sincronizzazioni successive in cui vuoi che il remoto corrisponda esattamente alla tua directory locale:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> Il flag `--mirror` elimina i file sul remoto che non esistono localmente. Usa prima `--dry-run` per verificare.

## Passo 3: Correggi la Proprietà dei File

I file caricati arrivano con l'UID del tuo utente locale (ad esempio, 1000). Rediacc usa un utente universale (UID 7111) in modo che VS Code, le sessioni terminale e gli strumenti abbiano accesso coerente. Esegui il comando di proprietà per convertire:

```bash
rdc repo ownership --name my-project -m server-1
```

### Esclusione Consapevole di Docker

Se i container Docker sono in esecuzione (o sono stati eseguiti), il comando di proprietà rileva automaticamente le loro directory di dati scrivibili e **le salta**. Questo evita di rompere i container che gestiscono i propri file con UID diversi (ad esempio, MariaDB usa UID 999, Nextcloud usa UID 33).

Il comando riporta ciò che fa:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Quando Eseguirlo

- **Dopo aver caricato i file**, per convertire il tuo UID locale a 7111
- **Dopo aver avviato i container**, se vuoi che le directory dei volumi Docker vengano auto-escluse. Se i container non sono stati ancora avviati, non ci sono volumi da escludere e tutte le directory vengono cambiate di proprietà (il che va bene, i container ricreeranno i loro dati al primo avvio)

### Modalità Forzata

Per saltare il rilevamento dei volumi Docker e cambiare proprietà di tutto, incluse le directory dei dati dei container:

```bash
rdc repo ownership --name my-project -m server-1
```

> **Attenzione:** Questo potrebbe rompere i container in esecuzione. Fermali prima con `rdc repo down` se necessario.

### UID Personalizzato

Per impostare un UID diverso da quello predefinito 7111:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

> **Attenzione:** `7111` è l'UID universale di Rediacc usato ovunque (corrisponde all'utente `rediacc` integrato nell'immagine del devcontainer). Sovrascrivilo con `--uid` solo per compatibilità con file appartenenti a un UID esterno specifico. **Non** è un target di migrazione. I nuovi repository dovrebbero mantenere il valore predefinito.

## Passo 4: Configura il Tuo Rediaccfile

Crea un `Rediaccfile` nella radice del tuo progetto. Questo script Bash definisce come i tuoi servizi vengono avviati e fermati.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

Le due funzioni del ciclo di vita:

| Funzione | Scopo | Comportamento in caso di errore |
|----------|---------|----------------|
| `up()` | Avvia i servizi | Il fallimento della radice è critico; i fallimenti nelle sottodirectory vengono registrati e l'esecuzione continua |
| `down()` | Ferma i servizi | Best-effort: tenta sempre tutto |

> **Importante:** Usa sempre `renet compose --` invece di `docker compose` nel tuo Rediaccfile. Il wrapper `renet compose` impone la rete host, le capacità di checkpoint/restore CRIU, l'allocazione IP e il service discovery richiesti da renet-proxy. Usare `docker compose` direttamente bypassa tutto ciò e verrà rifiutato durante la validazione.
>
> Non usare mai nemmeno `sudo docker`: `sudo` reimposta le variabili d'ambiente incluso `DOCKER_HOST`, il che causa la creazione di container sul daemon Docker di sistema invece del daemon isolato del repository. Le funzioni del Rediaccfile vengono già eseguite con privilegi sufficienti.

Vedi [Servizi](/en/docs/services) per i dettagli completi su Rediaccfile, layout multi-servizio e ordine di esecuzione.

## Passo 5: Configura la Rete dei Servizi

Rediacc esegue un daemon Docker isolato per repository. I servizi usano `network_mode: host` e si legano a IP di loopback univoci in modo da poter usare porte standard senza conflitti tra repository.

### Adattamento del docker-compose.yml

**Prima (tradizionale):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Dopo (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

Modifiche chiave:

1. **Rimuovi i mapping `ports:`** - `renet compose` usa la rete host e rimuove automaticamente i mapping delle porte
2. **Rimuovi `network_mode: host`** - `renet compose` lo aggiunge per te
3. **Le politiche di restart sono sicure da mantenere** - renet le rimuove automaticamente per la compatibilità con CRIU e il watchdog del router recupera automaticamente i container fermati
4. **Usa i nomi dei servizi per le connessioni tra servizi** (ad esempio `postgres`, `redis`) - renet inietta ogni nome di servizio come hostname risolvibile. Non incorporare IP raw nelle stringhe di connessione che vengono memorizzate in database o file di configurazione; usa il nome del servizio per mantenere l'isolamento del fork
5. **Il binding è automatico** - il kernel riscrive `bind()` all'IP di loopback corretto. I servizi possono usare `0.0.0.0` o `localhost`

Le variabili `{SERVICE}_IP` sono ancora disponibili se ne hai bisogno, ma il binding esplicito non è più necessario. Il binding avviene automaticamente. La convenzione di denominazione: maiuscolo, trattini sostituiti con underscore, con suffisso `_IP`. Ad esempio, `listmonk-app` diventa `LISTMONK_APP_IP`.

Vedi [Rete dei Servizi](/en/docs/services#service-networking-rediaccjson) per i dettagli sull'assegnazione degli IP e su `.rediacc.json`.

## Passo 6: Avvia i Servizi

Monta il repository (se non già montato) e avvia tutti i servizi:

```bash
rdc repo up --name my-project -m server-1
```

Questo farà:
1. Montare il repository cifrato
2. Avviare il daemon Docker isolato
3. Auto-generare `.rediacc.json` con le assegnazioni IP dei servizi
4. Eseguire `up()` da tutti i Rediaccfile

Verifica che i tuoi container siano in esecuzione:

```bash
rdc machine containers --name server-1
```

## Passo 7: Abilita l'Avvio Automatico (Opzionale)

Per impostazione predefinita, i repository devono essere montati e avviati manualmente dopo un riavvio del server. Abilita l'avvio automatico in modo che i tuoi servizi si avviino automaticamente:

```bash
rdc repo autostart enable --name my-project -m server-1
```

Ti verrà chiesta la passphrase del repository.

> **Nota sulla sicurezza:** L'avvio automatico memorizza un keyfile LUKS sul server. Chiunque abbia accesso root può montare il repository senza la passphrase. Vedi [Avvio Automatico](/en/docs/services#autostart-on-boot) per i dettagli.

## Scenari di Migrazione Comuni

### WordPress / PHP con Database

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress files (UID 33 when running)
├── database/data/          # MariaDB data (UID 999 when running)
└── wp-content/uploads/     # User uploads
```

1. Carica i file del progetto
2. Avvia prima i servizi (`rdc repo up`) in modo che i container creino le loro directory di dati
3. Esegui la correzione della proprietà; le directory dei dati di MariaDB e dell'app vengono auto-escluse

### Node.js / Python con Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Application source
├── node_modules/           # Dependencies
└── redis-data/             # Redis persistence (UID 999 when running)
```

1. Carica il progetto (considera di escludere `node_modules` e di scaricarli in `up()`)
2. Esegui la correzione della proprietà dopo che i container sono stati avviati

### Progetto Docker Personalizzato

Per qualsiasi progetto con servizi Docker:

1. Carica i file del progetto
2. Adatta `docker-compose.yml` (vedi Passo 5)
3. Crea un `Rediaccfile` con le funzioni del ciclo di vita
4. Esegui la correzione della proprietà
5. Avvia i servizi

## Risoluzione dei Problemi

### Permesso Negato Dopo il Caricamento

I file hanno ancora il tuo UID locale. Esegui il comando di proprietà:

```bash
rdc repo ownership --name my-project -m server-1
```

### Il Container Non Si Avvia

Verifica che i servizi siano in esecuzione e controlla i loro log:

```bash
# Verifica gli IP assegnati
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# Controlla i log del container
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### Conflitto di Porte tra Repository

Ogni repository ottiene IP di loopback univoci, e il kernel riscrive automaticamente le chiamate `bind()` all'IP corretto. I conflitti di porte tra repository non si verificano. Se vedi comportamenti inattesi, verifica che i servizi siano avviati tramite `renet compose` (non `docker compose`). Per connettersi **ad** altri servizi, usa il nome del servizio (ad esempio `postgres`) invece degli IP raw. I nomi dei servizi vengono risolti correttamente in ogni fork.

### La Correzione della Proprietà Rompe i Container

Se hai eseguito `rdc repo ownership` e un container ha smesso di funzionare, i file di dati del container sono stati cambiati di proprietà. Ferma il container, elimina la sua directory di dati e riavvia. Il container la ricrea:

```bash
rdc repo down --name my-project -m server-1
# Elimina la directory di dati del container (ad esempio, database/data)
rdc repo up --name my-project -m server-1
```
