---
title: Cosa ci hanno detto gli acquirenti nel primo ciclo di audit NIS2
description: >-
  Lo stack di conformità a cinque strumenti che le entità mid-market essenziali
  stanno silenziosamente assemblando nel 2026, cosa consolida un control plane
  self-hosted, e le voci di costo che restano comunque a carico
  dell'organizzazione.
author: Rediacc
publishedDate: 2026-05-09T00:00:00.000Z
category: guide
tags:
  - nis2
  - guida-acquisto
  - conformita
  - costi
  - mid-market
featured: false
language: it
sourceHash: 29fbcbffd8a304bc
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

**Sintesi.** Il primo ciclo di audit NIS2 è ormai alle spalle per l'ondata tedesca. Gli acquirenti con cui abbiamo parlato da dicembre descrivono tutti una variante dello stesso stack: cinque strumenti, tre contratti, due audit log sovrapposti e un gap che non riescono a chiudere. Questo articolo è la versione strutturale di quelle conversazioni. Cosa consolida un control plane self-hosted, cosa rimane comunque nel budget e perché la domanda giusta per il ciclo di rinnovo 2026 non è "costa meno di Veeam?" ma "meno voci nel registro, meno sovrapposizioni, gli stessi gap nominati onestamente."

- Frontier Economics stima il costo annuo della conformità NIS2 a livello UE in EUR 31,2 miliardi. La realtà per organizzazione, nel mid-market, è: "avevamo già uno stack di sicurezza; NIS2 ha reso visibile ciò che mancava."
- Lo stack a cinque strumenti: backup, DR, mascheramento o dati di test, contratto di pen test, GRC. Ognuno fa una parte del lavoro. Nessuno copre l'intero.
- Rediacc consolida backup, DR, fork-as-test-data e ripristino istantaneo in un unico control plane con un unico audit log. Non consolida GRC, certificazioni, formazione, MFA aziendale, pen testing, SIEM o SOC.
- La tabella onesta "resta a tuo carico" è il punto centrale di questo articolo. Un acquirente che la legge e conclude che Rediacc sostituisce Drata deluderà il proprio auditor.

A dicembre 2025, il BSI tedesco ha emesso 47 diffide formali a entità ritenute in scope per NIS2 ma non registrate. ANSSI in Francia ha avviato un esercizio parallelo. ACN in Italia ha cominciato a contattare circa 2.000 entità che riteneva non registrate. La prima ondata di entità essenziali e importanti mid-market è entrata nel primo ciclo di audit NIS2.

Da allora abbiamo parlato con circa trenta di loro. Settori diversi, dimensioni diverse, per lo più Germania e Italia con qualche caso nei Paesi Bassi e in Estonia. Le conversazioni si somigliano tutte. Ogni team ha un vendor di backup, un piano DR che potrebbe o non potrebbe essere stato testato, una storia sull'ambiente di staging che è solo parzialmente vera, e un budget procurement approvato prima che NIS2 comparisse su qualsiasi slide.

Questo articolo è la versione strutturale di quelle conversazioni. Cosa viene effettivamente chiesto di firmare a un CFO o a un responsabile acquisti nel 2026, cosa cambia nella fattura un control plane self-hosted, e quale sia l'onesto costo residuo. Non è intenzionalmente un calcolatore TCO. Gli acquirenti con cui parliamo non hanno bisogno di un altro foglio di calcolo; hanno bisogno di una mappa strutturale di dove va il denaro e quali voci si sovrappongono.

Per l'argomento sul rischio della supply chain dietro l'affermazione "il self-hosted conta", vedere il [post di approfondimento sull'Articolo 21(2)(d)](/it/blog/nis2-supply-chain-self-hosted). Per l'argomento a livello SRE su perché i pen test annuali non bastano più, vedere il [post sull'efficacia continua](/it/blog/nis2-effectiveness-without-theatre). Questo articolo si colloca tra i due, nella conversazione sul budget.

## Il numero macro, e cosa significa e non significa

Lo studio 2024 di Frontier Economics per la Commissione Europea ha quantificato il costo diretto annuo della conformità NIS2 nell'UE in EUR 31,2 miliardi. Il dato è ampiamente citato; è anche ampiamente frainteso.

EUR 31,2 miliardi sono distribuiti su circa 160.000 entità essenziali e importanti. Per organizzazione, la media si colloca tra EUR 150.000 e EUR 250.000, con il settore e le dimensioni che spiegano la maggior parte della varianza. Un'entità mid-market essenziale con 250 dipendenti nel manifatturiero o nella sanità si trova verso il limite superiore di quel range. Un'entità importante con 60 dipendenti in un settore meno data-intensive si trova verso il limite inferiore.

La stessa guida ENISA sui costi di implementazione (Allegato IV del Regolamento di esecuzione (UE) 2024/2690) è coerente con il dato Frontier ma lo articola diversamente: circa il 35-45 percento sugli strumenti, il 30-40 percento su personale e formazione, il 15-20 percento su certificazione e audit, il 5-10 percento su retainer per incident response e managed services.

Cosa significa per un CFO che firma il budget 2026: lo strato di tooling vale circa EUR 50.000-120.000 all'anno per il mid-market, a seconda di ciò che è già in essere. Questo strato di tooling è quello che analizzeremo.

Cosa non significa: che acquistare un bundle NIS2-ready risolva il problema. I budget per la formazione del personale e per le certificazioni sono più grandi del budget di tooling per la maggior parte dei team, e nessun vendor di tooling li riduce. Un pitch commerciale che afferma una riduzione del 50 percento dei costi NIS2 quasi sempre fa i calcoli sulla sola voce tooling, non sull'intero programma.

## Lo stack a cinque strumenti che i team mid-market hanno silenziosamente assemblato

Nelle trenta conversazioni con acquirenti, lo stack è lo stesso nel 90 percento dei casi. Cinque categorie, con uno o due vendor nominati per categoria. Le etichette delle categorie sono stabili; le scelte dei vendor variano.

**1. Vendor di backup.** Veeam Data Platform Foundation o Premium è la risposta prevalente. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect nelle realtà più piccole. Costo annuo tra EUR 15.000 e EUR 60.000 per il mid-market. Di solito la voce di costo più longeva; precede NIS2 di anni.

**2. Sito DR o DR-as-a-service.** Una regione cloud secondaria con un runbook, una tenancy Veeam Cloud Connect o Rubrik Cloud Vault, oppure un contratto con un provider DR gestito. Costo annuo EUR 8.000-35.000. Raramente testato in pratica; il runbook è solitamente più aspirazionale che operativo.

**3. Strumento per test data o data masking.** Delphix (ora Perforce DevOps Data) è il riferimento enterprise. Tonic.ai, Redgate Test Data Manager, occasionalmente uno script rsync-and-mask fatto in casa. Costo annuo EUR 25.000-90.000 per le opzioni con licenza. La maggior parte dei team nelle nostre chiamate non ha questa voce; ha quello che spera sia un ambiente di staging sufficientemente buono. La conversazione di audit sull'Articolo 21(2)(e) è ciò che la porta nel budget.

**4. Contratto di pen test.** Un retainer con una società di security testing o una piattaforma autonoma come Pentera o Horizon3.ai. Costo annuo EUR 15.000-50.000 per gli strumenti autonomi, EUR 20.000-80.000 per gli engagement condotti da esperti. La maggior parte dei team ce l'ha. La maggior parte lo fa una o due volte all'anno.

**5. Piattaforma GRC.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Talvolta un foglio di calcolo artigianale per i team più piccoli. Costo annuo EUR 12.000-60.000. Usata per il registro dei fornitori, l'attestazione del framework di controllo, la raccolta delle evidenze, e (sempre più) il supporto agli audit SOC 2 o ISO 27001.

Cinque voci, da tre a cinque vendor nominati, tipicamente EUR 75.000-295.000 all'anno prima di personale e formazione. La varianza è ampia ma la struttura è consistente.

I cinque contratti spesso non comunicano tra loro. Gli audit log non sono unificati. I piani di uscita sono redatti separatamente. Le revisioni dei vendor vengono condotte separatamente, a volte da responsabili acquisti diversi. Questa è la forma strutturale che NIS2 rende scomoda.

## Dove si trovano le sovrapposizioni

Ogni categoria nello stack si sovrappone ad almeno un'altra.

**Backup si sovrappone a DR.** I vendor di backup moderni affermano tutti di supportare il DR. Veeam Data Platform con Cloud Connect è un prodotto DR. Rubrik con Cloud Vault è un prodotto DR. Le due voci di costo spesso pagano capacità adiacenti presso lo stesso vendor. Gli acquirenti che storicamente non hanno consolidato le voci avevano ragioni operative (team separati, SLA separati); sotto l'aspettativa NIS2 di "singola fonte di verità per il ripristino", la motivazione si indebolisce.

**Backup si sovrappone ai test data.** Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles offrono tutti una forma di backup montabile per il testing. Non sono sostituti completi di Delphix (lo strato di mascheramento è separato, l'integrazione con i database è più superficiale), ma per molti casi d'uso di test data lo strumento di backup è metà della risposta. La maggior parte dei team non se ne rende conto.

**Pen test si sovrappone al testing autonomo.** Il pen test human-led basato su retainer e il testing continuo in stile Pentera vengono a volte presentati come alternative, a volte come complementi. In pratica, un acquirente con entrambi paga due volte per capacità adiacenti. Un acquirente senza nessuno dei due ha un gap sull'Articolo 21(2)(f).

**GRC si sovrappone a tutto.** Drata afferma di integrarsi con backup, DR, identity, vulnerability management, formazione e incident response. Le integrazioni variano in profondità. Una piattaforma GRC con un'integrazione superficiale a uno strumento di backup produce evidenze di conformità che non equivalgono alle evidenze dello strumento di backup stesso; gli auditor stanno iniziando a chiedere quale sia quella canonica.

Le sovrapposizioni non sono uno spreco. Sono la conseguenza di uno stack assemblato nell'arco di un decennio, prima che NIS2 rendesse strutturale la domanda di consolidamento.

## Dove si trovano i gap

I gap sono più interessanti delle sovrapposizioni, perché sono ciò che NIS2 porta alla luce.

**Validazione delle patch rispetto ai dati reali di produzione.** Nessuna delle cinque categorie lo fa bene. Gli strumenti di backup montano il backup; l'ambiente montato è il backup ripristinato, non la produzione corrente. Gli strumenti di test data mascherano i dati di produzione; l'ambiente mascherato è realistico nella forma ma perde i delta di configurazione. I contratti di pen test testano ciò a cui vengono puntati, che nell'90 percento dei casi è lo staging. Il gap tra "abbiamo gli strumenti" e "possiamo testare una patch CVE contro un ambiente equivalente alla produzione corrente in meno di un'ora" è reale e strutturale.

**Valutazione continua dell'efficacia.** La cadenza annuale è quella della maggior parte dei team. L'Articolo 21(2)(f) vuole qualcosa di più frequente. Nessuna delle cinque categorie produce evidenze settimanali o bisettimanali per impostazione predefinita. L'acquirente o esegue esercitazioni personalizzate (rare, costose) oppure accetta la cadenza annuale e spera che l'auditor la accetti (sempre più spesso, non è così).

**Compressione del registro della supply chain.** Ciascuno dei cinque vendor è una propria voce nel registro. Ciascuno porta il proprio DPA, le proprie SCC, la lista dei sub-processor e il piano di uscita. Il registro ha cinque voci di primo livello prima che vengano aggiunti gli strumenti di formazione del personale, gli strumenti di identity, gli strumenti di osservabilità e l'IaaS. La conversazione sulla supply chain, in termini NIS2, è tanto una conversazione di gestione del registro quanto una conversazione di sicurezza. Vedere il [post sulla supply chain](/it/blog/nis2-supply-chain-self-hosted) per l'argomentazione strutturale.

**Workflow di notifica dell'Articolo 23.** L'early warning a 24 ore, la notifica a 72 ore e il report a un mese non vengono prodotti automaticamente da nessuna delle cinque categorie. Richiedono un SIEM, un SOC (interno o in outsourcing), e una persona che sappia come presentare la comunicazione al CSIRT nazionale. I team più piccoli spesso non hanno questo. Il primo incidente diventa la dolorosa esperienza di apprendimento.

## Cosa consolida Rediacc

Rediacc è un unico control plane con un audit log unificato, che sostituisce la capacità core di quattro delle cinque categorie per le infrastrutture self-hosted.

**Il backup** gira in due modalita'. La modalita' hot e' uno snapshot BTRFS crash-consistent. Nessun downtime. La modalita' cold esegue un ciclo stop, snapshot, start. Entrambe si schedulano su systemd timer. Entrambe spediscono verso molte destinazioni via rclone. I volumi sono cifrati con LUKS. L'operatore detiene la chiave. Rediacc-the-company non vede mai il testo in chiaro. Vedi [Backup & Restore](/it/docs/backup-restore) e [Cross Backup Strategy](/it/docs/cross-backup).

**DR**: stessa primitiva del backup, più `rdc repo migrate` per il trasferimento dati tra macchine, più la primitiva di fork per il rapido avvio dello stato ripristinato su una macchina parallela. Il sito DR può essere un'altra macchina Hetzner, una macchina OVH, un rack on-prem, ovunque SSH sia raggiungibile. Nessun cloud del vendor DR nel percorso dei dati.

**Il test data e il full-stack cloning** girano su BTRFS reflink. Il fork e' a tempo costante, indipendentemente dalla dimensione del repo. Full-stack significa dati, configurazioni, container e servizi. Abbiamo forkato un repo da 128 GB in 7,2 secondi nel nostro [test PocketOS](/it/blog/i-tested-rediacc-against-the-pocketos-incident). Il fork e' la produzione corrente, non una copia di staging semplificata. Vedi [Risk-Free Upgrades](/it/docs/risk-free-upgrades).

**Ripristino istantaneo**: `rdc repo backup pull` da qualsiasi destinazione rclone in un fork fresco, avviato su un sottodominio specifico del fork coperto dal certificato wildcard del repository padre. Nessun rimescolamento DNS, nessuna complessità con i certificati.

**Audit log unificato.** Oltre 70 tipi di eventi sull'intero control plane. Coprono accessi, API token, scritture di configurazione, ciclo di vita dei repo, backup, sync, sessioni terminale e operazioni sulle macchine. La catena e' hash-linked sulla workstation dell'operatore. `rdc audit verify` la controlla da un capo all'altro.

Per un'entità essenziale mid-market con 250 dipendenti, il consolidamento passa da quattro vendor nominati (backup, DR, test-data, ripristino istantaneo) a uno. Una licenza, un audit log, un insieme di decisioni di aggiornamento, una voce nel registro.

La quinta categoria, GRC, non viene consolidata. Ne riparliamo tra poco.

## Cosa resta comunque nel vostro budget

Questa è la sezione che determina se il resto dell'articolo è onesto. La tabella a due colonne:

| Rimosso da Rediacc | Ancora a vostro carico, voce per voce |
|---|---|
| Licenza del vendor di backup | Piattaforma GRC (Drata, Vanta, OneTrust, AuditBoard, DataGuard) per il registro dei fornitori, l'attestazione del framework di controllo, la raccolta delle evidenze e il supporto agli audit SOC 2 o ISO 27001 |
| Contratto del sito DR o tenancy DR-as-a-service | Costi di audit per le certificazioni (ISO 27001, SOC 2, BSI C5 se necessari; Rediacc stessa non è ancora certificata, quindi questo costo resta a vostro carico nel frattempo) |
| Licenza dello strumento di test data o masking | Budget per la formazione del personale e la sensibilizzazione alla sicurezza (Articolo 21(2)(g) NIS2) |
| Licenza di instant-recovery presso il vendor di backup | Soluzione MFA aziendale più ampia; Rediacc ha TOTP sul portale, non una piattaforma MFA aziendale |
| | Contratto di pen testing o piattaforma di testing autonomo; Rediacc fornisce l'ambiente di destinazione, non la capacità di testing |
| | SIEM e SOC per il rilevamento e la reportistica dell'Articolo 23; Rediacc fornisce artefatti di grado forense, non il livello di reportistica operativa |
| | Provider IaaS (Hetzner, OVH, il vostro colo, il vostro bare metal); Rediacc gira sopra l'infrastruttura, non al suo posto |
| | Personale che gestisce il programma. Rediacc è uno strato di tooling, non un team di sicurezza |

Il lato destro della tabella è più lungo del lato sinistro. Questa è la forma onesta di ciò che NIS2 costa. Eliminare la sovrapposizione backup-DR-test-data fa risparmiare denaro reale e voci reali nel registro; non trasforma un programma di sicurezza in un abbonamento SaaS.

Un acquirente che legge questo e conclude "posso sostituire Drata con Rediacc" deluderà il proprio auditor. La lettura corretta è: il consolidamento dei vendor del data plane che Rediacc rende possibile è la cosa che gli strumenti GRC non possono fare, e il lavoro di gestione del registro e delle evidenze che gli strumenti GRC fanno è la cosa che Rediacc non fa. I due sono complementari.

Altri tre link se vuoi andare in profondita'. La mappatura pubblica e' su [NIS2 e DORA](/it/docs/legal-nis2-dora). Il quadro piu' ampio e' su [Panoramica sulla Conformità](/it/docs/legal-overview). Il lato commerciale di Rediacc e' su [Abbonamento e Licenze](/it/docs/subscription-licensing).

## Uno scenario di riferimento, strutturale e non numerico

Si consideri un'azienda manifatturiera tedesca con 250 dipendenti. Classificazione Allegato II "entità importante". Dati di produzione su 4-6 server, prevalentemente self-hosted con uno o due strumenti SaaS (CRM, paghe). EUR 80M di fatturato annuo. Team di sicurezza esistente di 3 persone.

**Prima**, il loro stack di data plane:

- Veeam Data Platform Foundation, EUR 24.000/anno
- Veeam Cloud Connect per DR, EUR 12.000/anno
- Uno schema rsync-plus-pg_dump fatto in casa per i dati di test, gratuito in licenza ma costa a un SRE mezza giornata ogni due settimane
- Pen test annuale, EUR 22.000
- Drata per GRC, EUR 18.000/anno

Cinque contratti. Due di essi (Veeam, Veeam Cloud Connect) sono con lo stesso vendor ma con SKU diversi. Le voci di data plane totalizzano EUR 36.000/anno prima di contare pen test o GRC. Il team produce un test di ripristino annuale, nessuna evidenza di efficacia continua e un registro dei fornitori con cinque voci solo sul lato data plane.

**Dopo**, con Rediacc su Hetzner per i workload self-hosted:

- Rediacc tier Business, EUR 8.400/anno (copre la dimensione dei loro repo)
- Hetzner IaaS per primario e secondario, EUR 9.600/anno combinati (già nel budget; nessuna nuova voce)
- Il contratto di pen test rimane (EUR 22.000)
- Drata rimane (EUR 18.000)
- Lo schema di test data fatto in casa viene ritirato; la mezza giornata bisettimanale dell'SRE viene destinata all'esecuzione della routine settimanale di efficacia

Consolidamento del data plane: da 5 voci a 1 (Rediacc) più la linea IaaS esistente. La sezione data plane del registro dei fornitori scende da 5 voci a 2. La storia dell'efficacia continua è ora costituita da esercitazioni settimanali con evidenze dell'audit log con hash chain; la storia del test di ripristino è ora supportata dall'output di `rdc machine backup status` e da un'esercitazione di ripristino settimanale.

I numeri sono illustrativi, non promesse. Il vostro stack è diverso. La forma, da quattro a cinque voci che collassano in una più l'IaaS esistente, è quella di una conversazione reale con un acquirente.

## Una nota su cosa non è questo articolo

Questo articolo non è un attacco a Veeam né un calcolatore TCO. Veeam detiene la quota di mercato più grande nel VM-backup in Europa per buone ragioni: il prodotto è maturo, la rete di partner è ampia, il marketing NIS2 è forte, e un acquirente che sceglie Veeam nel 2026 non sta commettendo un errore. I numeri nello scenario di riferimento sono illustrativi, tratti da conversazioni reali con acquirenti, non da benchmark. Eseguite l'analisi strutturale rispetto ai vostri contratti.

Cos'è questo articolo: un inquadramento dal lato acquirente per un CFO che sta rinegoziando un contratto di backup, DR o conformità nei prossimi dodici mesi e vuole sapere cosa cambia nelle voci di costo un control plane self-hosted.

## Cosa fare adesso

Se state entrando in un ciclo di rinnovo con il budget aperto, tre mosse concrete:

1. **Estraete le tre voci di spesa più significative dell'anno scorso per sicurezza e infrastruttura.** Inviatele al vostro DPO, al vostro CISO e al vostro auditor. Chiedete quali erano già ridondanti prima che NIS2 lo rendesse visibile. La maggior parte dei team trova almeno una sovrapposizione che sta pagando da tempo.
2. **Mappate il vostro stack di data plane attuale rispetto all'elenco delle cinque categorie sopra.** Annotate per quali categorie avete un vendor, per quali due, e per quali nessuno. Le celle "nessuno" sono i gap che NIS2 porterà alla luce.
3. **Eseguite l'esercizio sul registro dei fornitori del [post sulla supply chain](/it/blog/nis2-supply-chain-self-hosted)** per ciascun vendor di data plane. Contate le voci nel registro. Il numero è di solito più alto di quanto il team si aspettasse.

Se siamo nella vostra shortlist, l'offerta è concreta. Inviateci le tre voci di spesa più significative dell'anno scorso per sicurezza e infrastruttura. Vi diremo quali possono essere consolidate e quali no, per iscritto, entro una settimana. La risposta includerà i gap, perché nominare i gap è ciò che rende attendibile il resto della risposta.

Altri tre documenti se vuoi approfondire. [Backup a costo zero](/it/docs/zero-cost-backup) spiega perche' siamo piu' leggeri dei vendor tradizionali sullo storage. [Cross Backup Strategy](/it/docs/cross-backup) copre il DR intercontinentale. [Abbonamento e Licenze](/it/docs/subscription-licensing) e' il lato commerciale.
