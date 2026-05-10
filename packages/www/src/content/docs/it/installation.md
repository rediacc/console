---
title: "Installazione"
description: "Installa la CLI Rediacc su Linux, macOS o Windows. È sufficiente un singolo comando e l'installazione è completata in pochi secondi."
category: "Guides"
order: 1
language: it
---

# Installazione

Installa la CLI `rdc` sulla tua workstation. Questo è l'unico strumento che devi installare manualmente -- tutto il resto viene gestito automaticamente quando configuri le macchine remote.

## Installazione Rapida

### Linux e macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

Questo scarica il binario `rdc` in `$HOME/.local/bin/`. Assicurati che questa directory sia nel tuo PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Aggiungi questa riga al profilo della tua shell (`~/.bashrc`, `~/.zshrc`, ecc.) per renderla permanente.

### Windows

Esegui in PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Questo scarica `rdc.exe` in `%LOCALAPPDATA%\rediacc\bin\`. Il programma di installazione ti chiederà di aggiungerlo al PATH se necessario.

## Gestori di Pacchetti

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / compatibile RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux e Rocky Linux utilizzano tutti lo stesso flusso DNF; qualsiasi distribuzione compatibile con RHEL che abbia `dnf` può utilizzare il repository sopra. Nota: **Oracle Linux 10 è l'unica distribuzione della famiglia RHEL ufficialmente supportata come target server Rediacc** (vedi [Requisiti](/en/docs/requirements)). Rocky/Alma 10 non dispongono del modulo kernel btrfs necessario per il piano dati renet, anche se la CLI `rdc` si installa correttamente su di essi.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Testato su openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Nota: Il pacchetto `gcompat` (livello di compatibilità glibc) viene installato automaticamente come dipendenza.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

### npm (Node.js)

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz
```

Richiede Node.js 22 o versioni successive. Per installare una versione specifica:

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-0.8.5.tgz
```

## Docker

Scarica ed esegui la CLI come container:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Crea un alias per comodità:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Tag Docker disponibili:

| Tag | Descrizione |
|-----|-------------|
| `:stable` | Ultima versione stabile (raccomandato) |
| `:edge` | Ultima versione edge |
| `:0.8.4` | Versione fissata (immutabile) |
| `:latest` | Alias per `:stable` |

## Verifica l'Installazione

```bash
rdc --version
```

## Aggiornamento

Aggiorna all'ultima versione:

```bash
rdc update
```

Controlla la presenza di aggiornamenti senza installarli:

```bash
rdc update --check-only
```

Visualizza lo stato attuale degli aggiornamenti:

```bash
rdc update --status
```

Torna alla versione precedente:

```bash
rdc update --rollback
```

## Canali di Rilascio

Rediacc utilizza un sistema di rilascio basato su canali. Il canale determina quale versione ricevi per gli aggiornamenti della CLI, le installazioni dei gestori di pacchetti e i pull Docker.

| Canale | Descrizione | Quando viene aggiornato |
|---------|-------------|--------------|
| `stable` | Produzione, promosso da edge dopo 7 giorni di soak | Promozione settimanale di soak |
| `edge` | Produzione con deployment continuo | Ad ogni merge su main |
| `pr-N` | Build di anteprima PR | Automaticamente per ogni pull request |

### Cambio di Canale

```bash
rdc update --channel edge      # Passa al canale edge
rdc update --channel stable    # Torna al canale stable
```

Installa direttamente dal canale edge:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

Per i gestori di pacchetti, sostituisci `stable` con `edge` nell'URL del repository:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### Come Funzionano i Canali

Il canale si applica uniformemente a tutti i metodi di distribuzione:

- **Script di installazione**: la variabile d'ambiente `REDIACC_CHANNEL` seleziona il canale
- **Repository dei pacchetti**: `releases.rediacc.com/{format}/{channel}/`
- **Tag Docker**: `ghcr.io/rediacc/elite/cli:{channel}`
- **Aggiornamenti CLI**: `rdc update` controlla il canale configurato durante l'installazione

### Configurazione Automatica dell'Anteprima PR

Quando installi da un deployment di anteprima PR (es. `pr-420.rediacc.workers.dev`), il canale e il server account vengono configurati automaticamente:

- Il binario CLI viene scaricato dal canale `pr-420`
- `rdc update` controlla il canale `pr-420` per gli aggiornamenti
- Tutti i comandi account/abbonamento si connettono al server di anteprima PR
- I comandi Docker sul sito di anteprima mostrano `cli:pr-420`

Nessuna configurazione manuale necessaria. Lo script di installazione rileva il contesto di deployment dall'URL.

## Aggiornamenti Binari Remoti

Quando esegui comandi su una macchina remota, la CLI provisiona automaticamente il binario `renet` corrispondente. Se il binario viene aggiornato, il server di routing (`rediacc-router`) viene riavviato automaticamente in modo che recepisca la nuova versione.

Il riavvio è trasparente e non causa **alcun downtime**:

- Il server di routing si riavvia in circa 1-2 secondi.
- Durante quella finestra, Traefik continua a servire il traffico utilizzando la sua ultima configurazione di routing conosciuta. Nessuna route viene eliminata.
- Traefik recepisce la nuova configurazione al prossimo ciclo di polling (entro 5 secondi).
- **Le connessioni client esistenti (HTTP, TCP, UDP) non sono interessate.** Il server di routing è un provider di configurazione -- non si trova nel percorso dei dati. Traefik gestisce tutto il traffico direttamente.
- I tuoi container applicativi non vengono toccati -- viene riavviato solo il processo del server di routing a livello di sistema.

Per saltare il riavvio automatico, passa `--skip-router-restart` a qualsiasi comando, o imposta la variabile d'ambiente `RDC_SKIP_ROUTER_RESTART=1`.
