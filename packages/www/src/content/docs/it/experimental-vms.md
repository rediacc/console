---
title: "VM Sperimentali"
description: "Provisiona cluster VM locali per sviluppo e test con rdc ops. È una funzionalità sperimentale attivabile subito."
category: "Concepts"
order: 2
language: it
---

# VM Sperimentali

Provisiona cluster VM locali sulla tua workstation per sviluppo e test, senza la necessità di provider cloud esterni.

## Requisiti

`rdc ops` richiede l'**adattatore locale**. Non è disponibile con l'adattatore cloud.

```bash
rdc ops check
```

## Panoramica

I comandi `rdc ops` ti permettono di creare e gestire cluster VM sperimentali in locale. Questa è la stessa infrastruttura utilizzata dalla pipeline CI per i test di integrazione, ora disponibile per la sperimentazione pratica.

Casi d'uso:
- Testare i deployment Rediacc senza provider VM esterni (Linode, Vultr, ecc.)
- Sviluppare e fare debug delle configurazioni dei repository in locale
- Imparare la piattaforma in un ambiente completamente isolato
- Eseguire test di integrazione sulla tua workstation

## Supporto Piattaforme

| Piattaforma | Architettura | Backend | Stato |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Testato in CI |
| macOS | Intel | QEMU + HVF | Testato in CI |
| Linux | ARM64 | KVM (libvirt) | Supportato (non testato in CI) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Supportato (non testato in CI) |
| Windows | x86_64 / ARM64 | Hyper-V | Pianificato |

**Linux (KVM)** utilizza libvirt per la virtualizzazione hardware nativa con rete bridge.

**macOS (QEMU)** utilizza QEMU con il framework Hypervisor di Apple (HVF) per prestazioni quasi native, con rete in modalità utente e port forwarding SSH.

Il supporto **Windows (Hyper-V)** è pianificato. Vedi [issue #380](https://github.com/rediacc/console/issues/380) per i dettagli. Richiede Windows Pro/Enterprise.

## Prerequisiti e Configurazione

### Linux

```bash
# Installa i prerequisiti automaticamente
rdc ops setup

# Oppure manualmente:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Installa i prerequisiti automaticamente
rdc ops setup

# Oppure manualmente:
brew install qemu cdrtools
```

### Verifica la Configurazione

```bash
rdc ops check
```

Questo esegue controlli specifici per la piattaforma e riporta il risultato pass/fail per ogni prerequisito.

## Avvio Rapido

```bash
# 1. Verifica i prerequisiti
rdc ops check

# 2. Provisiona un cluster minimale (bridge + 1 worker)
rdc ops up --basic

# 3. Controlla lo stato delle VM
rdc ops status

# 4. Accedi via SSH alla VM bridge
rdc ops ssh --vm-id 1

# 4b. Oppure esegui un comando direttamente
rdc ops ssh --vm-id 1 -c hostname

# 5. Smantella il cluster
rdc ops down
```

## Composizione del Cluster

Per impostazione predefinita, `rdc ops up` provisiona:

| VM | ID | Ruolo |
|----|-----|------|
| Bridge | 1 | Nodo primario, esegue il servizio bridge Rediacc |
| Worker 1 | 11 | Nodo worker per i deployment dei repository |
| Worker 2 | 12 | Nodo worker per i deployment dei repository |

Usa il flag `--basic` per provisiona solo il bridge e il primo worker (ID 1 e 11).

Usa `--skip-orchestration` per provisiona le VM senza avviare i servizi Rediacc, utile per testare il layer VM in isolamento.

## Configurazione

La VM bridge utilizza valori predefiniti più piccoli rispetto alle VM worker:

| Ruolo VM | CPU | RAM | Disco |
|---------|------|-----|------|
| Bridge | 1 | 1024 MB | 8 GB |
| Worker | 2 | 4096 MB | 16 GB |

Le variabili d'ambiente sovrascrivono le risorse delle VM worker:

| Variabile | Predefinito | Descrizione |
|----------|---------|-------------|
| `VM_CPU` | 2 | Core CPU per VM worker |
| `VM_RAM` | 4096 | RAM in MB per VM worker |
| `VM_DSK` | 16 | Dimensione disco in GB per VM worker |
| `VM_NET_BASE` | 192.168.111 | Base di rete (solo KVM) |
| `RENET_DATA_DIR` | ~/.renet | Directory dei dati per i dischi VM e la configurazione |

## Riferimento Comandi

| Comando | Descrizione |
|---------|-------------|
| `rdc ops setup` | Installa i prerequisiti della piattaforma (KVM o QEMU) |
| `rdc ops check` | Verifica che i prerequisiti siano installati e funzionanti |
| `rdc ops up [options]` | Provisiona il cluster VM |
| `rdc ops down` | Elimina tutte le VM e pulisce |
| `rdc ops status` | Mostra lo stato di tutte le VM |
| `rdc ops ssh --vm-id <id> [command...]` | Accedi via SSH a una VM, o esegui un comando su di essa |

### Opzioni di `rdc ops up`

| Opzione | Descrizione |
|--------|-------------|
| `--basic` | Cluster minimale (bridge + 1 worker) |
| `--lite` | Salta il provisioning delle VM (solo chiavi SSH) |
| `--force` | Forza la ricreazione delle VM esistenti |
| `--parallel` | Provisiona le VM in parallelo |
| `--skip-orchestration` | Solo VM, nessun servizio Rediacc |
| `--backend <kvm\|qemu>` | Sovrascrive il backend rilevato automaticamente |
| `--os <name>` | Immagine OS (predefinito: ubuntu-24.04) |
| `--debug` | Output dettagliato |

## Differenze tra Piattaforme

### Linux (KVM)
- Utilizza libvirt per la gestione del ciclo di vita delle VM
- Rete bridge, le VM ottengono IP su una rete virtuale (192.168.111.x)
- SSH diretto agli IP delle VM
- Richiede `/dev/kvm` e il servizio libvirtd

### macOS (QEMU + HVF)
- Utilizza processi QEMU gestiti tramite file PID
- Rete in modalità utente con port forwarding SSH (localhost:222XX)
- SSH tramite porte inoltrate, non IP diretti
- ISO cloud-init creati tramite `mkisofs`

## Risoluzione dei Problemi

### Modalità debug

Aggiungi `--debug` a qualsiasi comando per un output dettagliato:

```bash
rdc ops up --basic --debug
```

### Problemi comuni

**KVM non disponibile (Linux)**
- Verifica che `/dev/kvm` esista: `ls -la /dev/kvm`
- Abilita la virtualizzazione nel BIOS/UEFI
- Carica il modulo kernel: `sudo modprobe kvm_intel` oppure `sudo modprobe kvm_amd`

**libvirtd non in esecuzione (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU non trovato (macOS)**
```bash
brew install qemu cdrtools
```

**Le VM non si avviano**
- Controlla lo spazio su disco in `~/.renet/disks/`
- Esegui `rdc ops check` per verificare tutti i prerequisiti
- Prova `rdc ops down` e poi `rdc ops up --force`
