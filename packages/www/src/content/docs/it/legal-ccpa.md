---
title: "Conformità CCPA"
description: "Come il modello self-hosted di Rediacc risponde ai requisiti del California Consumer Privacy Act per la protezione dei dati dei consumatori."
category: "Legal"
order: 4
language: it
---

Il California Consumer Privacy Act (CCPA) è una legge statale che attribuisce ai consumatori californiani diritti sui propri dati personali, tra cui il diritto di sapere quali dati vengono raccolti, il diritto di cancellarli e il diritto di opporsi alla loro vendita.

Riferimento: [California Attorney General, CCPA](https://oag.ca.gov/privacy/ccpa)

## Mappatura dei diritti dei consumatori

Il CCPA si concentra sui diritti dei consumatori relativi alle informazioni personali. Rediacc è uno strumento self-hosted distribuito sulla propria infrastruttura, non un servizio di terze parti che raccoglie o vende dati dei consumatori. La tabella seguente mappa i diritti CCPA alle modalità con cui Rediacc supporta la conformità della propria organizzazione.

| Diritto CCPA | Requisito | Capacità di Rediacc |
|-----------|-------------|-------------------|
| Diritto di conoscere (1798.100) | Comunicare le categorie e le finalità dei dati raccolti | I log di audit tracciano tutte le operazioni sui dati. Self-hosted: la propria organizzazione mantiene piena visibilità sui dati presenti in ciascun repository. |
| Diritto di cancellazione (1798.105) | Cancellare i dati personali del consumatore su richiesta | `rdc repo destroy` cancella crittograficamente il volume LUKS cifrato. L'eliminazione di un fork rimuove le copie clonate. |
| Diritto di opposizione (1798.120) | Non vendere né condividere le informazioni personali | Architettura self-hosted: nessun trasferimento di dati verso Rediacc o terze parti. I dati rimangono sui propri server. La sincronizzazione del config store utilizza la cifratura zero-knowledge. Nemmeno il server di sincronizzazione può leggere i dati. |
| Sicurezza dei dati (1798.150) | Implementare misure di sicurezza adeguate | Cifratura LUKS2 AES-256, isolamento di rete, accesso esclusivo via SSH, daemon Docker isolati, log di audit. Il config store utilizza la cifratura a triplo livello con derivazione a chiave suddivisa e token monouso rotanti. |

## Stato di fornitore di servizi

Rediacc come software non accede, elabora né archivia i dati dei consumatori. Il team IT della propria organizzazione gestisce Rediacc sulla propria infrastruttura. Nessun dato fluisce verso Rediacc come azienda. Le implicazioni:

- Rediacc non è un "fornitore di servizi" ai sensi del CCPA (non elabora dati per conto dell'organizzazione)
- Non è richiesto alcun accordo sul trattamento dei dati con Rediacc per il prodotto self-hosted
- Gli obblighi CCPA sussistono tra la propria organizzazione e i propri consumatori

## Inventario dei dati

Ogni repository Rediacc è un'unità di dati discreta e cifrata con un GUID univoco. È possibile inventariare esattamente quali dati esistono e dove:

- `rdc machine query --name <machine> --repositories` elenca tutti i repository su una macchina con dimensioni e stato di montaggio
- Ogni repository è isolato a livello di filesystem, di rete e di container
- Le relazioni di fork sono tracciate, consentendo di identificare tutte le copie di un dataset

Il CCPA richiede la mappatura dei dati. Il modello a repository di Rediacc la fornisce: un GUID per dataset, enumerabile per macchina, con la derivazione dei fork tracciata.
