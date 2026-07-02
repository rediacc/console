---
title: "Conformità GDPR"
description: "Come l'architettura self-hosted di Rediacc si mappa ai requisiti GDPR per la protezione dei dati e la privacy."
category: "Legal"
order: 1
language: it
sourceHash: "76d2b3a911e0d14c"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Il Regolamento generale sulla protezione dei dati (GDPR) è la legge dell'Unione Europea sulla protezione dei dati, in vigore dal maggio 2018. Disciplina le modalità con cui le organizzazioni raccolgono, trattano e archiviano i dati personali degli individui nell'UE.

Testo integrale: [Regolamento (UE) 2016/679](https://gdpr-info.eu/)

## Mappatura degli articoli

La tabella seguente mappa gli articoli specifici del GDPR alle capacità tecniche di Rediacc.

| Articolo | Requisito | Capacità di Rediacc |
|---------|-------------|-------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Principi | Minimizzazione dei dati, integrità, riservatezza | I clone CoW (`cp --reflink=always`) duplicano i dati sulla stessa macchina senza trasferimento di rete. LUKS2 AES-256 cifra tutti i dati a riposo. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Diritto alla cancellazione | Cancellare i dati personali su richiesta | `rdc repo delete` cancella crittograficamente il volume LUKS. L'eliminazione di un fork rimuove completamente la copia clonata. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Protezione dei dati fin dalla progettazione | Privacy per impostazione predefinita | La cifratura è obbligatoria, non opzionale. Ogni repository dispone di un daemon Docker e di una rete isolati. Nessuna condivisione di dati tra repository. Il config store utilizza la cifratura zero-knowledge: le configurazioni sono cifrate lato client con AES-256-GCM prima dell'upload, pertanto il server non può leggere alcun dato in chiaro. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Responsabile del trattamento | Obblighi di trattamento dei dati da parte di terzi | Self-hosted: Rediacc gira sulla propria infrastruttura. Nessun dato lascia la macchina durante le operazioni di fork, clone o backup. Nessun componente SaaS tratta i dati personali. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Registro delle attività di trattamento | Tenere il registro delle attività di trattamento | Il log di audit traccia oltre 70 tipologie di eventi: autenticazione, token API, operazioni sul config store, licenze e operazioni CLI sulle macchine (ciclo di vita dei repository, backup, sincronizzazione, terminale). Esportazione tramite dashboard di amministrazione o pagina attività del portale (esportazione JSON disponibile). |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Sicurezza del trattamento | Misure tecniche adeguate | Cifratura LUKS2 AES-256 a riposo, isolamento di rete tramite iptables e daemon Docker separati, sottoreti IP loopback (/26) per repository. Il config store utilizza la cifratura a triplo livello: chiavi SDK con finestra temporale, derivazione CEK a chiave suddivisa (passkey + segreto server) e cifratura della passphrase organizzativa. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Notifica di violazione | Notifica entro 72 ore con traccia forense | I log di audit forniscono una traccia forense di tutte le operazioni. L'architettura self-hosted limita il raggio d'impatto ai singoli repository. |

## Residenza dei dati

I clone CoW non lasciano mai la macchina sorgente. Il comando `rdc repo fork` crea una copia a livello di filesystem tramite reflink. Nessun dato viene trasferito sulla rete.

Per le operazioni tra macchine diverse, `rdc repo push/pull` trasferisce i dati tramite SSH. La destinazione del backup riceve volumi cifrati con LUKS che non possono essere letti senza le credenziali dell'operatore.

## Clonazione dell'ambiente e mascheramento dei dati

Quando si clonano ambienti di produzione per lo sviluppo o il test, il lifecycle hook `up()` del Rediaccfile esegue script di sanitizzazione dopo la creazione del fork: rimozione delle informazioni personali identificabili (PII) dai database, sostituzione delle email reali con indirizzi di test, rimozione di token API e dati di sessione, anonimizzazione dei file di log. L'ambiente di sviluppo ottiene la struttura di produzione senza le identità di produzione, soddisfacendo il principio di minimizzazione dei dati ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Config store zero-knowledge

Il config store opzionale consente di sincronizzare le configurazioni CLI tra i dispositivi. È progettato in modo che il server non abbia alcuna conoscenza del contenuto delle configurazioni:

- **Cifratura lato client**: le configurazioni sono cifrate con AES-256-GCM prima dell'upload. La chiave di cifratura (CEK) viene derivata da un segreto PRF della passkey e da un segreto detenuto dal server tramite HKDF con separazione di dominio. Nessuna delle due parti può derivare la chiave da sola.
- **Il server vede solo blob opachi**: chiavi SSH, credenziali, indirizzi IP, topologia di rete. Nulla di tutto ciò è visibile al server. Solo i metadati (ID configurazione, versioni, timestamp) sono archiviati in chiaro.
- **Accesso dei membri tramite X25519**: quando si aggiunge un membro del team, la CEK viene cifrata con la sua chiave pubblica X25519 e inoltrata dal server. Il server non vede mai la CEK in chiaro.
- **Revoca immediata**: la rimozione di un membro cancella la sua CEK avvolta e revoca i suoi token. Le configurazioni future utilizzano nuove epoche SDK inaccessibili al membro rimosso.
- **Token rotanti**: l'autenticazione CLI utilizza token monouso rotanti (finestra di tolleranza di 3 richieste), vincolati all'IP al primo utilizzo, con scadenza automatica dopo 24 ore.

Anche una compromissione completa del server non può esporre il contenuto delle configurazioni. Il server non dispone mai della chiave.

Per i dettagli, vedere [Config Storage](/it/docs/config-storage).

## Titolare e responsabile del trattamento

Poiché Rediacc è un software self-hosted, la propria organizzazione è sia titolare sia responsabile del trattamento dei dati. Rediacc (l'azienda) non accede, tratta né archivia i dati dell'organizzazione. Non è richiesto alcun accordo sul trattamento dei dati con Rediacc per il prodotto self-hosted, poiché nessun dato personale fluisce verso l'infrastruttura di Rediacc.

Il config store è l'unico componente che interagisce con i server di Rediacc (per la sincronizzazione), ma il suo design zero-knowledge significa che il server archivia solo blob cifrati che non è in grado di decifrare.
