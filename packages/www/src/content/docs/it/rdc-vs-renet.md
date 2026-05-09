---
title: "rdc vs renet"
description: "Quando usare rdc e quando usare renet. È una distinzione fondamentale, più semplice di quanto sembri."
category: "Concepts"
order: 1
language: it
---

# rdc vs renet

Rediacc ha due binari. Ecco quando usare ciascuno.

| | rdc | renet |
|---|-----|-------|
| **Viene eseguito su** | La tua workstation | Il server remoto |
| **Si connette tramite** | SSH | Viene eseguito localmente con root |
| **Usato da** | Tutti | Solo per il debug avanzato |
| **Installazione** | Lo installi tu | `rdc` lo provvede automaticamente |

> Per il lavoro quotidiano, usa `rdc`. Raramente hai bisogno di `renet` direttamente.

## Come Lavorano Insieme

`rdc` si connette al tuo server tramite SSH ed esegue i comandi `renet` per te. Digiti un singolo comando sulla tua workstation, e `rdc` si occupa del resto:

1. Legge il tuo config locale (`~/.config/rediacc/rediacc.json`)
2. Si connette al server tramite SSH
3. Aggiorna il binario `renet` se necessario
4. Esegue l'operazione `renet` corrispondente sul server
5. Restituisce il risultato al tuo terminale

## Usa `rdc` per il Lavoro Normale

Tutti i compiti comuni passano attraverso `rdc` sulla tua workstation:

```bash
# Configura un nuovo server
rdc config machine setup --name server-1

# Crea e avvia una repository
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# Ferma una repository
rdc repo down --name my-app -m server-1

# Controlla la salute della macchina
rdc machine health --name server-1
```

Vedi il [Quick Start](/it/docs/quick-start) per una guida completa.

## Usa `renet` per il Debug Lato Server

Hai bisogno di `renet` direttamente solo quando accedi via SSH a un server per:

- Debug di emergenza quando `rdc` non riesce a connettersi
- Controllo degli interni del sistema non disponibili tramite `rdc`
- Operazioni di ripristino a basso livello

Tutti i comandi `renet` richiedono privilegi root (`sudo`). Vedi [Server Reference](/it/docs/server-reference) per l'elenco completo dei comandi `renet`.

## Sperimentale: `rdc ops` (VM Locali)

`rdc ops` racchiude `renet ops` per la gestione di cluster di VM locali sulla tua workstation:

```bash
rdc ops setup              # Installa i prerequisiti (KVM o QEMU)
rdc ops up --basic         # Avvia un cluster minimo
rdc ops status             # Controlla lo stato delle VM
rdc ops ssh --vm-id 1  # SSH nella VM bridge
rdc ops ssh --vm-id 1 -c hostname  # Esegui un comando sulla VM bridge
rdc ops down               # Distruggi il cluster
```

> Richiede l'adapter locale. Non disponibile con l'adapter cloud.

Questi comandi eseguono `renet` localmente (non tramite SSH). Vedi [Experimental VMs](/it/docs/experimental-vms) per la documentazione completa.

## Nota sul Rediaccfile

Potresti vedere `renet compose -- ...` all'interno di un `Rediaccfile`. Questo è normale: le funzioni Rediaccfile vengono eseguite sul server dove `renet` è disponibile.

Dalla tua workstation, avvia e ferma i carichi di lavoro con `rdc repo up` e `rdc repo down`.
