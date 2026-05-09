---
title: "Panoramica sulla conformità"
description: "Come l'architettura self-hosted di Rediacc risponde ai requisiti di conformità in materia di protezione dei dati, privacy e sicurezza."
category: "Legal"
order: 0
language: it
---

Rediacc gira interamente sulla propria infrastruttura. Durante le operazioni di clonazione dell'ambiente, backup e distribuzione, i dati non lasciano mai la macchina. L'organizzazione rimane sia titolare sia responsabile del trattamento dei dati. Nessun SaaS di terze parti gestisce i propri dati.

Questa sezione mappa le capacità tecniche di Rediacc ai requisiti dei principali framework di conformità. Ogni pagina tratta un regolamento specifico con riferimenti a livello di articolo ai testi legali ufficiali.

## Matrice di conformità

| Framework | Ambito | Capacità chiave di Rediacc |
|-----------|-------|--------------------------|
| [GDPR](/it/docs/legal-gdpr) | Protezione dei dati e privacy nell'UE | Clonazione CoW sulla stessa macchina, cifratura LUKS2, config store zero-knowledge, log di audit, diritto alla cancellazione tramite `rdc repo destroy` |
| [SOC 2](/it/docs/legal-soc2) | Criteri di fiducia per le organizzazioni di servizi | Cifratura a riposo, sincronizzazione config zero-knowledge, isolamento di rete, traccia di audit, backup e ripristino |
| [HIPAA](/it/docs/legal-hipaa) | Protezione delle informazioni sanitarie negli USA | Cifratura LUKS2, config store zero-knowledge, accesso esclusivo via SSH, daemon Docker isolati, sicurezza della trasmissione |
| [CCPA](/it/docs/legal-ccpa) | Diritti alla privacy dei consumatori californiani | Self-hosted (nessuna vendita/condivisione di dati), cifratura zero-knowledge, cancellazione cifrata, inventario dei dati per repository |
| [ISO 27001](/it/docs/legal-iso27001) | Controlli di gestione della sicurezza delle informazioni | Gestione degli asset, controlli crittografici, config store zero-knowledge, controllo degli accessi, sicurezza operativa |
| [PCI DSS](/it/docs/legal-pci-dss) | Protezione dei dati delle carte di pagamento | Segmentazione di rete per architettura, cifratura obbligatoria, log di audit, riduzione dell'ambito tramite self-hosted |
| [NIS2 e DORA](/it/docs/legal-nis2-dora) | Cybersicurezza e resilienza finanziaria nell'UE | Eliminazione del rischio della supply chain, test di resilienza tramite clonazione CoW, cifratura, rilevamento degli incidenti |
| [Sovranità dei dati](/it/docs/legal-data-sovereignty) | Leggi globali sulla residenza dei dati (PIPL, LGPD, KVKK, PIPA e altre) | Self-hosted = i dati non lasciano mai la propria giurisdizione. Nessun trasferimento transfrontaliero, nessuna valutazione di adeguatezza |

## Fondamenta architetturali

Ogni framework di conformità in questa sezione si riconduce alle stesse proprietà tecniche:

- **Cifratura a riposo**: ogni repository è cifrato con LUKS2 AES-256. Le credenziali sono archiviate solo nella configurazione locale dell'operatore, mai sul server.
- **Isolamento di rete**: ogni repository dispone di un proprio daemon Docker, di una subnet IP loopback (/26) e di regole iptables. I container di repository diversi non possono comunicare.
- **Clonazione copy-on-write**: `rdc repo fork` utilizza reflink del filesystem (`cp --reflink=always`). I dati vengono duplicati sulla stessa macchina senza alcun trasferimento di rete.
- **Log di audit**: oltre 70 tipologie di eventi che coprono autenticazione (accesso, 2FA, cambio password, revoca sessione), ciclo di vita dei token API, operazioni sul config store, attività di abbonamento/licenza e operazioni CLI sulle macchine (ciclo di vita dei repository, backup, sincronizzazione, sessioni di terminale). Accessibili tramite dashboard di amministrazione, pagina attività del portale (con filtraggio per organizzazione) e CLI `rdc audit`. Le operazioni sulle macchine sono registrate anche nei log di sistema per una difesa in profondità.
- **Backup cifrato**: `rdc repo backup push/pull` trasferisce i dati tramite SSH. La destinazione del backup riceve volumi cifrati con LUKS.
- **Config store zero-knowledge**: sincronizzazione cifrata opzionale delle configurazioni tra dispositivi. Le configurazioni sono cifrate lato client con AES-256-GCM prima dell'upload. Il server archivia solo blob opachi. Il server non può leggere chiavi SSH, credenziali, indirizzi IP o dati di configurazione in chiaro. La derivazione della chiave utilizza l'estensione PRF della passkey e HKDF con separazione di dominio. L'accesso dei membri è gestito tramite scambio di chiavi X25519 e la revoca è immediata.

Per i dettagli su queste capacità, vedere [Architettura](/it/docs/architecture), [Repository](/it/docs/repositories), [Config Storage](/it/docs/config-storage) e [Sicurezza dell'account](/it/docs/account-security).

## Perché questo è rilevante

I fallimenti in materia di conformità sono costosi. Questi casi sanzionatori hanno riguardato problemi che l'architettura di Rediacc previene strutturalmente:

| Incidente | Sanzione | Cosa è andato storto |
|----------|------|----------------|
| [Meta: trasferimenti dati UE-USA](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | EUR 1,2 miliardi | Dati personali trasferiti oltre confine senza adeguate salvaguardie. Il self-hosted elimina il trasferimento. |
| [Equifax: dati non cifrati](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 milioni di dollari | 147 milioni di record archiviati non cifrati con scarsa segmentazione di rete. LUKS2 è obbligatorio, non opzionale. |
| [Target: movimento laterale](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 milioni di dollari | Gli aggressori si sono spostati da un fornitore HVAC ai sistemi di pagamento su una rete piatta. L'isolamento per repository impedisce questo tipo di attacco. |
| [Anthem: PHI non cifrati](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 milioni di dollari | 79 milioni di cartelle sanitarie archiviate senza cifratura. LUKS2 AES-256 è sempre attivo. |
| [Blackbaud: violazione a cascata SaaS](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 milioni di dollari | Un ransomware presso un vendor SaaS ha esposto i dati di oltre 13.000 organizzazioni clienti. Il self-hosted significa che una violazione del vendor non può raggiungere i propri dati. |
| [British Airways: scarsa segmentazione](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | GBP 20 milioni | Gli aggressori hanno iniettato codice malevolo a causa di controlli di rete inadeguati. I daemon Docker isolati e le regole iptables impediscono gli accessi laterali. |
| [Google: diritto alla cancellazione](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | EUR 50 milioni | Difficoltà nell'eliminare completamente i dati tra sistemi distribuiti. La cancellazione crittografica tramite LUKS destroy è immediata e completa. |

## Avviso importante

Queste pagine descrivono le capacità tecniche di Rediacc in relazione ai requisiti di conformità. La conformità a qualsiasi regolamento richiede politiche organizzative, procedure, formazione del personale e potenzialmente audit di terze parti che esulano dall'ambito di qualsiasi singolo strumento. Si raccomanda di consultare il proprio team legale e di conformità per una guida specifica alla propria organizzazione.
