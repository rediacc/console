---
title: Requisiti
description: Requisiti di sistema e piattaforme supportate per eseguire Rediacc.
category: Guides
order: 0
language: it
sourceHash: "e84db3bb90270473"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Requisiti

La maggior parte di questa configurazione è standard per server Linux. Alcuni dettagli sono specifici di come funziona Rediacc, quindi verificali prima di iniziare.

## Workstation (Control Plane)

La CLI `rdc` viene eseguita sulla tua workstation e orchestra i server remoti tramite SSH.

| Piattaforma | Versione minima | Note |
|-------------|-----------------|------|
| macOS | 12 (Monterey)+ | Supporto Intel e Apple Silicon |
| Linux (x86_64) | Qualsiasi distribuzione moderna | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Supporto nativo tramite installer PowerShell |

**Requisiti aggiuntivi:**
- Una coppia di chiavi SSH (ad esempio `~/.ssh/id_ed25519` o `~/.ssh/id_rsa`)
- Accesso di rete ai server remoti sulla porta SSH (predefinita: 22)

## Server remoto (Data Plane)

Il binario `renet` viene eseguito sui server remoti con privilegi di root. Gestisce immagini disco cifrate, daemon Docker isolati e orchestrazione dei servizi.

Se non sei sicuro di quale binario usare, consulta [rdc vs renet](/it/docs/rdc-vs-renet). In breve: usa `rdc` per le operazioni normali, e `renet` direttamente solo per operazioni avanzate lato server.

### Sistemi operativi supportati

I server remoti eseguono il binario `renet` e ospitano i daemon Docker cifrati per singolo repository. Le seguenti cinque distribuzioni sono verificate dalla matrice Bridge Workers in CI a ogni pull request e sono le uniche ufficialmente supportate:

| OS | Versione | Kernel predefinito | Note |
|----|----------|-------------------|------|
| Ubuntu | 24.04 LTS | 6.8 | Consigliato. AppArmor abilitato per impostazione predefinita. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 funziona anch'esso (kernel minimo 6.1). |
| Fedora | 43 | 6.12 | SELinux in modalità enforcing per impostazione predefinita. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor abilitato per impostazione predefinita. |
| Oracle Linux | 10 | UEK 7+ | Usa UEK, che mantiene il modulo btrfs. SELinux in modalità enforcing per impostazione predefinita. Vedi "Perché UEK?" di seguito. |

Tutte le righe sono `x86_64`. `arm64` viene compilato ma non testato continuamente per ogni OS server; apri una segnalazione se ne hai bisogno su una distribuzione specifica. Altre distribuzioni Linux con systemd, supporto Docker e cryptsetup potrebbero funzionare, ma non sono ufficialmente supportate e potrebbero smettere di funzionare dopo aggiornamenti senza preavviso.

#### Perché UEK? (e perché Rocky 10 / RHEL 10 stock non sono supportati)

Il backend di archiviazione cifrata di Rediacc richiede il modulo kernel `btrfs` incluso nell'albero sorgente. **Il kernel stock di RHEL 10 non lo include**: `modprobe btrfs` fallisce con "Module btrfs not found" e `dnf search btrfs` non restituisce nulla. Rocky Linux 10 e AlmaLinux 10 ereditano lo stesso kernel e pertanto non possono essere usati come server Rediacc.

Oracle Linux 10 usa l'**Unbreakable Enterprise Kernel (UEK)** per impostazione predefinita, che mantiene btrfs incorporato. Questo è l'unico target compatibile con RHEL nell'elenco supportato. Se devi usare un server della famiglia RHEL, usa Oracle Linux 10 con UEK. (La fonte definitiva di questa decisione si trova in `.github/workflows/ct-tests.yml` come matrice CI Bridge Workers.)

#### Solo workstation (target di installazione CLI)

La CLI `rdc` si installa correttamente anche su Alpine 3.19+ (APK con il layer di compatibilità `gcompat`, installato automaticamente) e Arch Linux (rolling, tramite pacman). Questi sono percorsi di installazione solo lato client (vedi [Installazione](/it/docs/installation)) e non sono supportati come target server per `renet`.

### Policy di sicurezza per OS

Il daemon Docker per singolo repository e i container del repository stesso vengono eseguiti con **etichette container predefinite** su ogni OS supportato. `rdc config machine setup` non installa policy SELinux personalizzate né profili AppArmor. Comportamento per OS:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor è abilitato per impostazione predefinita. Si applica il profilo docker-container predefinito; nessuna configurazione aggiuntiva richiesta.
- **Fedora 43, Oracle Linux 10**: SELinux è in modalità enforcing. Il daemon per singolo repository assegna ai container il contesto standard `container_t`. Non è necessaria alcuna policy SELinux personalizzata.
- **CRIU** (checkpoint/restore) è l'unico caso che aggira il profilo AppArmor con `apparmor=unconfined`, poiché il supporto AppArmor di CRIU upstream non è ancora stabile. Consulta le note su CRIU in [Regole di Rediacc](/it/docs/rules-of-rediacc).

Se un passaggio di configurazione fallisce con denial AVC SELinux o rifiuti AppArmor, consulta [Risoluzione dei problemi](/it/docs/troubleshooting) → Problemi di configurazione specifici per distribuzione.

### Prerequisiti server

- Un account utente con privilegi `sudo` (sudo senza password consigliato)
- La tua chiave pubblica SSH aggiunta a `~/.ssh/authorized_keys`
- Almeno 20 GB di spazio libero su disco (di più a seconda dei carichi di lavoro)
- Accesso a Internet per il pull di immagini Docker (o un registro privato)

### Installato automaticamente

Il comando `rdc config machine setup` installa quanto segue sul server remoto:

- **Docker** e **containerd** (runtime container)
- **cryptsetup** (crittografia disco LUKS)
- Binario **renet** (caricato tramite SFTP)

Non è necessario installarli manualmente.

## Macchine virtuali locali (opzionale)

Se vuoi testare i deployment localmente usando `rdc ops`, la tua workstation necessita del supporto alla virtualizzazione: KVM su Linux o QEMU su macOS. Consulta la guida [VM sperimentali](/it/docs/experimental-vms) per i passaggi di configurazione e i dettagli sulla piattaforma.
