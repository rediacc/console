---
title: "GPU"
description: "Dare a un repo l'accesso a una GPU tramite una concessione di dispositivo CDI: elencare le GPU della macchina, concedere e revocare dispositivi per repo, riservare una scheda in esclusiva e lavorare su WSL."
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: it
sourceHash: "5a113ad69c52c63d"
---

# GPU

Un repo raggiunge una GPU solo tramite una **concessione di dispositivo**. La macchina pubblica le GPU che ha come dispositivi con nome, e un operatore concede a un repo i nomi che può usare. Un repo senza concessione non ottiene alcuna GPU, e un [fork](/it/docs/repositories) parte senza concessione anche quando il repo d'origine ne ha una.

I nomi seguono il Container Device Interface (CDI), lo standard con cui Docker 25 e successivi descrive un dispositivo e tutto ciò che serve a un container per usarlo. Un nome CDI ha la forma `<vendor>/<class>=<device>`, per esempio `nvidia.com/gpu=all`.

## Che cos'è una concessione CDI

Ogni repo esegue il proprio demone Docker dietro un gate API che rifiuta qualsiasi modo di collegare hardware a un container, quindi una GPU non si raggiunge con le opzioni di `docker run`. La concessione è l'unica porta. Registra un nome CDI esatto per un repo, e il gate ammette allora una richiesta di container che nomini quel dispositivo e nessun altro.

- Le concessioni hanno effetto alla richiesta Docker successiva, senza riavviare il demone.
- Una concessione nomina esattamente un dispositivo. Concedere `nvidia.com/gpu=all` ammette `nvidia.com/gpu=all` e non `nvidia.com/gpu=0`. Per dare a un repo una sola scheda si concede il nome di quella scheda.
- Alla scrittura, una concessione viene verificata rispetto alle specifiche dei dispositivi della macchina, quindi un nome scritto male viene rifiutato anziché registrato.
- Una concessione appartiene al repo per cui è stata fatta. Fork e copie hanno bisogno della propria.

## Preparare la macchina

`rdc machine setup <machine>` rileva le GPU della macchina e registra il risultato in `/etc/rediacc/gpu/inventory.json`. Quando è presente una GPU NVIDIA, il setup installa anche il NVIDIA Container Toolkit e genera la specifica CDI in `/etc/cdi/nvidia.yaml`. Una macchina senza GPU riceve comunque un file di inventario con liste vuote.

L'installazione del toolkit si controlla con l'opzione `--install-nvidia-toolkit` di `renet setup`:

| Valore | Comportamento |
|---|---|
| `auto` | Il toolkit viene installato quando è presente una GPU NVIDIA. È il valore predefinito. |
| `true` | Il toolkit viene installato in ogni caso. |
| `false` | Il toolkit viene saltato e non viene generata alcuna specifica NVIDIA. |

Il setup non configura alcun runtime di container, perché è ammesso solo `runc`. Il toolkit serve soltanto per la specifica, rigenerata a ogni setup per seguire i cambi di driver.

Due tipi di dispositivo provengono da Rediacc stesso e non richiedono componenti userspace del produttore, perché mappano solo nodi di dispositivo:

| Tipo | Dispositivi | Origine |
|---|---|---|
| `rediacc.io/dri` | Uno per nodo di rendering, come `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` per una scheda AMD e `all` | `/dev/kfd` più il nodo di rendering della scheda |

I dispositivi NVIDIA provengono dalla specifica del toolkit: `nvidia.com/gpu=all` e un nome per scheda. Il calcolo AMD richiede lo userspace ROCm nell'immagine del container, perché il setup non installa ROCm.

## Elencare le GPU

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

La tabella mostra ogni GPU con nome, versione del driver e memoria, la piattaforma (nativa o WSL), l'età dell'inventario e ogni nome di dispositivo CDI che può essere concesso. `-o json` stampa l'inventario così com'è registrato sulla macchina. Le concessioni attive vengono lette in diretta dalla macchina.

## Concedere e revocare

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` è il nome di un repo, con una macchina facoltativa, come `gpu-a@wsl-gpu`. Entrambi i comandi si possono ripetere con valori diversi di `--device`. Dopo una concessione, un container di quel repo parte con il dispositivo:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

Lo stesso container viene rifiutato in un repo senza la concessione, e il messaggio nomina la concessione mancante.

## Concessioni esclusive

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Una concessione esclusiva riserva un dispositivo a un solo repo. Viene rifiutata quando un altro repo ha lo stesso nome, e finché esiste, ogni concessione di quel nome a un altro repo viene rifiutata. Il controllo avviene al momento della concessione, sotto un blocco su tutte le concessioni della macchina.

Una concessione esclusiva è una prenotazione, non uno scheduler. Due container dello stesso repo autorizzato condividono comunque la scheda.

## Forme rifiutate

Ogni altra via verso una GPU resta rifiutata, con o senza concessione. La forma CDI sostituisce ciascuna di esse.

| Rifiutato | Da usare invece |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` in Compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` in Compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` in Compose | `devices: [nvidia.com/gpu=all]` |
| Dispositivi `/dev/dri` o `/dev/kfd` grezzi, o un bind sotto `/dev` | `rediacc.io/dri=renderD128` o `rediacc.io/amd=gpu0` |
| Regole cgroup dei dispositivi | Una concessione CDI per il dispositivo |

Un servizio Compose che usa un dispositivo concesso ha questo aspetto:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Aggiungere un gruppo come `video` o `render` con `group_add` è accettato ma non concede nulla, perché il gruppo non dà accesso a un dispositivo che il repo non ha ricevuto.

## WSL

Su WSL2 il driver Windows fornisce la GPU tramite `/dev/dxg` e le librerie in `/usr/lib/wsl/lib`. La macchina dichiara la propria piattaforma come `wsl`, e il setup genera la specifica NVIDIA in formato WSL:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

Il driver sta sul lato Windows, quindi un aggiornamento lì viene recepito alla successiva esecuzione di `rdc machine setup`. I comandi per concedere, elencare e revocare funzionano come su una macchina nativa.

## NVIDIA nativo

Su una macchina NVIDIA nativa, il servizio `nvidia-cdi-refresh` del toolkit rigenera la specifica dopo un'installazione, un cambio di driver e un avvio. Il setup lo punta a `/etc/cdi/nvidia.yaml`, l'unica directory di specifiche che il demone Docker di un repo legge. Quando `nvidia-persistenced` è in esecuzione, il suo socket viene reso visibile ai demoni dei repo, perché la specifica lo monta nei container.
