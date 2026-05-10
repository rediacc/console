---
title: "Sovranità dei dati"
description: "Come l'architettura self-hosted di Rediacc soddisfa i requisiti di residenza e sovranità dei dati nelle diverse giurisdizioni globali."
category: "Legal"
order: 7
language: it
---

Molti paesi richiedono che i dati personali dei propri cittadini siano archiviati ed elaborati entro i confini nazionali. L'architettura self-hosted di Rediacc soddisfa questi requisiti per progettazione: i dati rimangono sulla propria macchina, nel proprio data center, nella propria giurisdizione. Nessun dato lascia la macchina durante la clonazione e nessun SaaS di terze parti elabora i dati dell'organizzazione.

## Perché il self-hosted risolve la sovranità dei dati

Il trasferimento transfrontaliero di dati è il problema di conformità più complesso nel cloud computing. Ogni giurisdizione ha regole diverse, decisioni di adeguatezza e meccanismi di trasferimento distinti. Il self-hosted elimina l'intera categoria:

- **Nessun trasferimento transfrontaliero**: la clonazione CoW (`cp --reflink=always`) duplica i dati sulla stessa macchina
- **Nessun responsabile del trattamento terzo**: Rediacc gira sulla propria infrastruttura, non sui server di Rediacc
- **Nessuna valutazione di adeguatezza necessaria**: i dati non lasciano mai la giurisdizione, pertanto le norme sui trasferimenti non si applicano
- **Nessuna clausola contrattuale standard**: non esiste alcun flusso di dati internazionale da regolamentare

## Copertura giurisdizionale

### Unione Europea

Il [GDPR](https://gdpr-info.eu/) limita i trasferimenti di dati personali al di fuori dell'UE/SEE salvo che la destinazione garantisca una protezione adeguata. La storica sentenza Schrems II ha invalidato il Privacy Shield UE-USA e la [multa di 1,2 miliardi di euro inflitta a Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) ha dimostrato il costo degli errori nei trasferimenti transfrontalieri.

Rediacc self-hosted distribuito nell'UE mantiene tutti i dati all'interno dell'UE. Non è necessario alcun meccanismo di trasferimento. Vedere [Conformità GDPR](/it/docs/legal-gdpr) per la mappatura a livello di articolo.

### Cina

La [Personal Information Protection Law (PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) richiede che i dati personali dei cittadini cinesi siano archiviati in Cina. I trasferimenti transfrontalieri richiedono valutazioni di sicurezza da parte della Cyberspace Administration of China (CAC). Rediacc self-hosted su infrastruttura cinese evita completamente le valutazioni di sicurezza CAC.

### Brasile

La [Lei Geral de Protecao de Dados (LGPD)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) richiede misure di sicurezza adeguate e limita i trasferimenti internazionali. Il self-hosted in Brasile elimina i problemi legati ai trasferimenti e soddisfa il requisito di misure tecniche dell'Art. 46 tramite la cifratura LUKS2 e l'isolamento di rete.

### India

Il [Digital Personal Data Protection Act (DPDP Act, 2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) limita i trasferimenti verso paesi non inclusi in un elenco approvato dal governo. Il self-hosted su infrastruttura indiana significa nessun trasferimento, indipendentemente dai paesi inseriti nella lista nera. I settori governativo e della difesa indiani privilegiano fortemente le soluzioni on-premises.

### Turchia

La [KVKK (Legge n. 6698)](https://kvkk.gov.tr/en/) limita i trasferimenti internazionali con requisiti di adeguatezza complessi. La Turchia non figura nell'elenco di adeguatezza dell'UE, pertanto i trasferimenti transfrontalieri richiedono un'approvazione esplicita. Il self-hosted in Turchia elimina questo problema del tutto.

### Corea del Sud

Il [Personal Information Protection Act (PIPA)](https://www.pipc.go.kr/eng/index.do) è tra i più severi a livello globale e impone espressamente la cifratura dei dati personali durante l'archiviazione e la trasmissione. LUKS2 AES-256 soddisfa direttamente questo requisito. Le sanzioni possono arrivare fino al 3% del fatturato.

### Giappone

La [Act on Protection of Personal Information (APPI)](https://www.ppc.go.jp/en/legal/) limita i trasferimenti transfrontalieri salvo che il paese destinatario garantisca una protezione adeguata. Il self-hosted in Giappone evita le restrizioni sui trasferimenti e si allinea alla preferenza culturale del mercato per le soluzioni on-premises.

### Australia

Il [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) rende responsabile l'entità che divulga i dati per la gestione degli stessi da parte del destinatario estero (APP 8). Il self-hosted elimina completamente questa responsabilità. La cifratura LUKS2 e l'isolamento di rete costituiscono "misure ragionevoli" concrete ai sensi dell'APP 11.

### Emirati Arabi Uniti

Il [Federal Decree-Law No. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) richiede misure di sicurezza adeguate e limita i trasferimenti transfrontalieri. I settori governativo e finanziario degli EAU privilegiano fortemente le installazioni on-premises.

### Arabia Saudita

La [Personal Data Protection Law (PDPL)](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) richiede che i dati personali dei residenti sauditi siano archiviati ed elaborati in Arabia Saudita. Il self-hosted soddisfa direttamente questo rigoroso requisito di localizzazione.

### Singapore

Il [Personal Data Protection Act (PDPA)](https://sso.agc.gov.sg/Act/PDPA2012) richiede una sicurezza adeguata e limita i trasferimenti transfrontalieri. Il self-hosted a Singapore, importante hub dati APAC, soddisfa i requisiti di conformità regionali per le operazioni ASEAN.

### Russia

La [Legge federale 242-FZ](https://pd.rkn.gov.ru/) richiede che i dati personali dei cittadini russi siano archiviati su server ubicati in Russia. Le violazioni possono comportare il blocco del sito web. Il self-hosted su suolo russo garantisce la conformità per architettura.

## Lo schema ricorrente

In tutte le giurisdizioni l'equazione di conformità è la stessa:

| Proprietà | Cloud/SaaS | Rediacc self-hosted |
|----------|-----------|-------------------|
| Posizione dei dati | Data center del fornitore (possono attraversare confini) | La propria macchina, la propria giurisdizione |
| Meccanismo di trasferimento necessario | Sì (SCCs, adeguatezza, consenso) | No (nessun trasferimento avviene) |
| Responsabilità del responsabile del trattamento terzo | Sì | No |
| Controllo della cifratura | Chiavi gestite dal fornitore | Le proprie credenziali LUKS, archiviate localmente |
| Clonazione/staging dei dati | Può attraversare confini o uscire dal proprio controllo | CoW sulla stessa macchina, nella stessa giurisdizione |

## Servizio hosted: residenza regionale dei dati

Per gli utenti del servizio hosted Rediacc (non self-hosted), la residenza dei dati è garantita tramite infrastruttura regionale. Sono disponibili tre regioni: UE (Francoforte), USA (Virginia) e Asia Pacifico (Tokyo). Ogni regione dispone di database e storage indipendenti senza flussi di dati tra regioni. La posta elettronica transazionale viene inviata tramite AWS SES; UE e USA utilizzano endpoint regionali dedicati, Asia Pacifico utilizza l'endpoint UE (eu-central-1). La regione UE applica il vincolo giurisdizionale sullo storage R2. Vedere [Regioni dati](/it/docs/data-regions) per la descrizione tecnica completa.
