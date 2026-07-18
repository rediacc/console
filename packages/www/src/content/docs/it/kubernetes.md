---
title: "Kubernetes"
description: "Esegui Kubernetes con la mentalità del repository Rediacc: fai il fork o sposta un cluster in esecuzione, dati compresi, su un'altra macchina o datacenter con un breve cutover."
category: "Guides"
order: 6
language: it
sourceHash: "d36c468ae2350e25"
sourceCommit: "4401262fffbf29b9480dee8ecd209013e4b87f60"
---

# Kubernetes

Rediacc integra Kubernetes nel prodotto senza rinunciare alla mentalità del repository su cui si fonda il resto della piattaforma. L'affermazione che fa la differenza è diretta: puoi **fare il fork o spostare un cluster in esecuzione, dati compresi, su un'altra macchina o datacenter con un breve cutover**. Non si tratta di una migrazione ad arresto-e-ripristino, né di magia a zero downtime. I workload si riavviano sulla destinazione, il cutover si misura in secondi, e i dati viaggiano insieme.

Kubernetes è alimentato da [k3s](https://k3s.io/), una distribuzione Kubernetes certificata, incorporata in renet nello stesso modo degli altri binari lato server.

## Il modello a oggetti

Rediacc inverte la consueta immagine "il cluster racchiude tutto" affinché la mentalità del repository continui ad applicarsi:

- **Un cluster è il contenitore.** Una macchina ospita repository Docker (invariati) e/o cluster. Un cluster a singolo nodo su una macchina mantiene, a livello di cluster, la storia del "un solo file sposta l'intero sistema". Lo stato del cluster (la directory dati di k3s: il suo datastore incorporato e containerd) vive in file immagine copy-on-write supportati dal datastore, uno per nodo, con il `--data-dir` di k3s legato dentro il mount dell'immagine.
- **Un repository Kubernetes è un namespace.** `rdc repo create <repo> -m <name>` crea un repository la cui sede di esecuzione è il namespace Kubernetes `<repo>` all'interno di quel cluster.
- **I volumi persistenti sono unità copy-on-write separate.** I PV sono immagini RBD su Ceph, oppure piccoli file immagine del datastore tramite un provisioner di PV locale sul backend locale. Non sono mai directory all'interno di un'unica immagine di cluster opaca: il filesystem interno non ha reflink, quindi fork di repository indipendenti richiedono immagini di PV indipendenti.

Questa separazione è ciò che rende entrambe le promesse fisicamente possibili contemporaneamente: **fork di namespace sempre copy-on-write** (i dati di ogni repository si clonano indipendentemente) e **portabilità dell'intero cluster** (le immagini del cluster più ogni immagine di PV si spostano insieme).

| Concetto | Repository Docker | Repository Kubernetes |
|---|---|---|
| Sede di esecuzione | Daemon Docker isolato | Namespace in un cluster |
| Env iniettata | `DOCKER_HOST` | `KUBECONFIG` |
| Wrapper di deploy | `renet compose` | `renet kube` |
| Unità di dati | Un'immagine LUKS | Immagini del cluster più immagini per PV |
| Unità di fork | L'immagine del repository | Il namespace più i suoi cloni di PV |
| Clone dell'intero luogo | (il repository è il luogo) | `rdc cluster fork` / `rdc cluster migrate` |

## Dichiarare e creare un cluster

Un cluster è un insieme denominato di pool di nodi su una rete privata. Dichiaralo prima in configurazione, poi eseguine il provisioning.

```bash
# Dichiara un cluster con pool (nulla è ancora sottoposto a provisioning)
rdc config cluster add --name prod \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Esegui il provisioning dei membri dei pool, avvia renet su ciascuno, installa i componenti (Ceph per primo)
rdc cluster create --name prod
```

I ruoli dei pool sono `ceph`, `k8s-server`, `k8s-agent`, e `hyperconverged` (opt-in esplicito, poiché gli obiettivi di memoria di Ceph e le soglie di eviction del kubelet competono per la RAM). Ogni pool porta l'asimmetria hardware come dimensione e parametri disco per pool: nodi Ceph ricchi di disco, nodi Kubernetes ricchi di CPU/RAM.

I membri dei pool si materializzano in `resources.machines` come `<cluster>-<pool>-<n>` con un riferimento di ritorno, quindi **ogni comando `-m` esistente funziona su di essi**: `rdc machine query`, `rdc term connect`, i comandi repo e le strategie di backup vedono tutti i nodi del cluster come macchinari ordinari.

I provider cloud eseguono il provisioning tramite [OpenTofu](https://opentofu.org/), seguendo lo stesso registro `ProviderMapping` usato da `rdc machine provision`, esteso con un blocco di rete privata (VLAN o VPC, l'MTU da impostare, la denominazione della NIC privata). Il KVM locale è il percorso di test sempre disponibile tramite `rdc ops`.

```bash
# Ispeziona i cluster
rdc cluster status                 # elenca tutti i cluster
rdc cluster status --name prod     # configurazione completa di un cluster

# Aumenta o riduci un pool (aggiunge/rimuove macchinari, fa entrare/uscire nodi)
rdc cluster scale --name prod --pool k8s --count 5

# Installa i componenti sui membri già sottoposti a provisioning
rdc cluster install --name prod

# Smantella i membri sottoposti a provisioning e rimuove il cluster dalla configurazione
rdc cluster destroy --name prod
```

### Ottenere un kubeconfig

Il kubeconfig non è mai memorizzato nel tuo file di configurazione (è voluminoso e ruota). Viene recuperato su richiesta via SSH e messo in cache localmente con permessi `0600`, seguendo lo stesso schema di stato collaterale delle workdir di OpenTofu e della cache dei certificati.

```bash
rdc cluster kubeconfig --name prod
# Stampa: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Repository Kubernetes

Il flag di destinazione decide il runtime. Non c'è un flag di tipo.

```bash
# Repository Docker (invariato): un daemon Docker isolato su una macchina
rdc repo create --name shop -m server-1 --size 10G

# Repository Kubernetes: namespace "shop" più il suo storage, dentro un cluster
rdc repo create --name shop --cluster prod --size 10G
```

I verbi repo sono la superficie unica per il lavoro a livello di repository. Grazie all'imbuto di risoluzione della destinazione, praticamente l'intero set di comandi repo diventa compatibile con i cluster: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status`, e `log` accettano tutti `--cluster`. Una destinazione cluster si risolve nel suo nodo di controllo più il contesto KUBECONFIG fissato sul namespace del repository, l'analogo della risoluzione di una macchina in `DOCKER_HOST` più una directory di lavoro.

```bash
rdc repo sync upload --cluster prod -r shop --local ./config
rdc cluster kubeconfig --name prod           # esporta KUBECONFIG, poi usa kubectl direttamente
```

Anche i nodi del cluster si materializzano in `resources.machines`, quindi puoi connetterti via SSH a un nodo specifico con il comune `rdc term connect <cluster>-<pool>-<n>`.

### Rediaccfile a doppio runtime

La portabilità tra Docker e Kubernetes si fonda su una convenzione, non su una conversione automatica dei manifest. Un repository che fornisce sia un percorso `renet compose` sia un percorso `renet kube` sotto le stesse funzioni `up()` e `down()` migra liberamente in entrambe le direzioni, perché le convenzioni della directory dati sono identiche. renet inietta `DOCKER_HOST` su una destinazione macchina e `KUBECONFIG` su una destinazione cluster; `up()` legge quale dei due è impostato e si comporta di conseguenza.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Runtime Kubernetes
  else
    renet compose -- up -d             # Runtime Docker
  fi
}
```

Un repository privo del runtime di destinazione riceve un rifiuto chiaro **dopo** la fase di trasferimento dati: le immagini si spostano, e la fase di deploy ti informa che il repository non dichiara un percorso Kubernetes (o Docker), invece di corrompere lo stato.

## Fare il fork di un repository

`rdc repo fork` su un repository Kubernetes copia sempre i dati, sempre istantaneamente. Non c'è un flag `--full` né varianti.

```bash
rdc repo fork --parent shop --tag joseph --cluster prod
```

Questo crea il namespace `shop-joseph` nello stesso cluster, clona ogni volume in copy-on-write (un clone RBD su Ceph, un reflink dei file immagine di PV sul backend locale), e vi distribuisce i workload. L'URL del fork è live istantaneamente sotto il certificato wildcard del genitore, quindi non viene emesso alcun nuovo certificato o record DNS.

Escalation della destinazione:

- `--to-cluster <name>` esegue il fork verso un altro cluster esistente. Stesso backend Ceph: il clone RBD resta copy-on-write. Backend diverso: il meccanismo di push sposta le immagini.
- `--provider <p>` esegue prima il provisioning di un nuovo cluster, con specifiche dei pool predefinite che rispecchiano la forma del cluster sorgente (i flag hanno priorità).

Misurato nel laboratorio di test KVM, un fork di namespace si completa in circa uno-cinque secondi, con il workload genitore intatto e i due namespace che divergono indipendentemente.

## Fare il fork o spostare un intero cluster

Le operazioni sull'intero cluster vivono nel gruppo `rdc cluster`, perché agiscono su un oggetto diverso (l'intero luogo con tutti i suoi repository) e non possono essere espresse tramite un comando che accetta un singolo nome di repository. Questa è la storia di punta.

```bash
# Clona un intero cluster, dati dei suoi repository inclusi, in un nuovo cluster
rdc cluster fork --name prod --tag staging

# Sposta un intero cluster, dati dei suoi repository inclusi, su un'altra macchina o datacenter
rdc cluster migrate --name prod --to server-2
```

Entrambi coordinano un copy-on-write delle immagini del cluster più ogni immagine di PV dei repository, quindi riscrivono l'identità dei nodi affinché il clone o il cluster rilocato si avvii correttamente sui suoi nuovi indirizzi. Poiché k3s memorizza lo stato del control plane nel suo datastore incorporato, l'immagine del cluster è essa stessa lo snapshot: l'ordine di coerenza è prima il control plane, poi i PV, poi gli agent.

I numeri onesti, misurati end-to-end nel laboratorio di test KVM:

| Operazione | Cosa fa | Misurato |
|---|---|---|
| Fork di namespace | Clona il namespace di un repository più i suoi PV sul posto | ~1-5 s |
| Fork di una singola immagine RBD | Copy-on-write di un clone di PV su Ceph | ~5 s |
| Fork di un intero cluster a 2 nodi | Drena, reflink control plane e agent, riscrive l'identità verso nuovi IP, il genitore resta intatto | ~46 s |
| Migrazione di cluster cross-macchina | Pre-copia a caldo più il cutover di arresto-riavvio | ~16 s di cutover |

La coerenza predefinita è **crash-consistent e referenzialmente intatta**: la stessa semantica di uno spegnimento improvviso, che è ciò che vedono i workload. Snapshot application-consistent sono disponibili quando i filesystem del workload vengono congelati durante la copia. Questo non è deliberatamente presentato come zero-downtime. Nessun altro offre affatto "fai il fork di un cluster in esecuzione, dati compresi"; l'inquadramento onesto è un cutover breve e misurato, non un assoluto di marketing.

## Storage: ceph-csi e volumi persistenti

Ceph viene sottoposto a provisioning dal flusso cephadm di renet sul pool `ceph`, **al di fuori** di qualsiasi cluster Kubernetes, e i cluster lo consumano tramite manifest ceph-csi generati da renet. Ogni istanza di cluster (e ogni fork) ottiene il proprio namespace RBD/RADOS, che è la primitiva di isolamento per tenant. Lo storage sta sotto tutti i cluster, quindi supporta anche i semplici repository Docker e il backend datastore, e un fork di cluster clona le immagini RBD al di sotto di Kubernetes anziché fare il fork del proprio backend di storage.

Sul backend locale (senza Ceph), un provisioner di PV locale di renet supporta ogni PV con un piccolo file immagine copy-on-write nel datastore, clonato tramite reflink al momento del fork. Vedi [Riferimento server](/it/docs/server-reference) per il layout su disco e i comandi renet.

## Scegliere una distribuzione

La distribuzione è un'astrazione con una piccola interfaccia reale (install, join, kubeconfig, healthcheck, upgrade, e così via):

- **k3s** è la distribuzione predefinita e l'unica incorporata. È Apache-2.0, certificata CNCF, un singolo binario rilocabile, e sia il suo Traefik incorporato sia ServiceLB sono disabilitati a favore del proxy Rediacc. Il suo `--data-dir` si lega all'avvio, il che è esattamente ciò di cui hanno bisogno il fork e la migrazione del cluster quando cambia il percorso di mount dell'immagine. k3s è contrassegnato come `repoEmbeddable`.
- **external** consiste nel portare il proprio kubeconfig. Solo `getKubeconfig` e `healthcheck` svolgono un lavoro reale; i verbi del ciclo di vita restituiscono risultati "non applicabile" di prima classe anziché errori.
- **RKE2** è il terzo backend pianificato per i clienti FIPS/CIS, non incluso in questa release.

Il fork e la migrazione del cluster rifiutano di essere eseguiti su una distribuzione non `repoEmbeddable` con un errore chiaro invece di corrompere lo stato, perché incorporare lo stato del cluster in immagini del datastore richiede un data-dir che si leghi all'avvio.

## Registro

Due problemi di immagine distinti, due strumenti:

- **Dolore a monte** (limiti di rate di Docker Hub, pull negati, offline): una cache pull-through [zot](https://zotregistry.dev/) incorporata gira sul pool di controllo con `sync.onDemand` verso più sorgenti a monte (docker.io, ghcr.io, quay.io). È incorporata in renet allo stesso modo degli altri binari, e sostituisce il registro di test degli ops in modo che ogni run la eserciti.
- **Distribuzione intra-cluster**: il mirror di registro incorporato di k3s permette ai nodi di condividere le immagini già scaricate da pari a pari.

Il cablaggio è trasparente e senza riavvio grazie a `certs.d/hosts.toml` di containerd e a `registries.yaml` di k3s. Lo store containerd per repository all'interno dell'immagine di cluster resta la fonte di verità che fork e migrazioni usano; il registro è solo una cache davanti a internet, mai stato.

## Rete e URL

Gli URL dei repository Kubernetes seguono lo schema piatto, con l'identità del namespace ripiegata nella label più a sinistra e il cluster come secondo label stabile:

```
{service}--{repo}.{cluster}.{machine}.{base}          Repository Kubernetes (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (namespace = repo-tag)
```

Ogni namespace e ogni fork eredita il certificato wildcard e il record DNS del genitore, quindi gli URL dei fork sono live istantaneamente e nuovi certificati vengono emessi solo quando viene creato un nuovo cluster o repository. Il router scopre i servizi Kubernetes interrogando il cluster per i Service annotati con `rediacc.*`, l'analogo Kubernetes della lettura delle etichette Docker. Vedi [Networking](/it/docs/networking) per il modello di routing e [Architettura](/it/docs/architecture) per i backend di storage.

## Attribuzione

Rediacc trasporta diversi binari di terze parti (k3s, zot, e gli altri incorporati da renet). Stampa le loro versioni, identificatori di licenza SPDX, e URL degli archivi sorgente in qualsiasi momento:

```bash
rdc credits
rdc credits --licenses    # testo completo THIRD_PARTY_LICENSES incluso nelle build di release
```
