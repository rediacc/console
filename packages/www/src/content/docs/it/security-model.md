---
title: Modello di sicurezza
description: Chi può vedere cosa nell'archivio di configurazione, come sono delimitate le chiavi, cosa possono raggiungere gli agenti e l'MCP remoto e cosa è recuperabile.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: it
sourceHash: "dd01eccb85dd4e7c"
sourceCommit: "467795d4f62f378389037e0027cac2676125b437"
---

# Modello di sicurezza

Questa pagina descrive cosa protegge l'archivio di configurazione, quale chiave apre cosa e a cosa può accedere ogni tipo di chiamante. Per i passaggi di configurazione vedi [Archivio di Configurazione](/it/docs/config-storage); per sessioni e token vedi [Sicurezza dell'account e API](/it/docs/account-security).

## Chi può vedere cosa

![Gerarchia delle chiavi](/img/security-key-hierarchy.svg)

*Il server custodisce le chiavi del livello SDK e della passphrase dell'organizzazione; solo i titolari di slot di chiave aprono la CEK.*

![Chi può vedere il contenuto delle configurazioni](/img/security-who-can-see.svg)

*Che cosa può leggere ogni tipo di attaccante.*

Una configurazione archiviata è cifrata su tre livelli. Il livello SDK e il livello della passphrase dell'organizzazione sono gestiti dal server. Il livello intermedio è la chiave di cifratura del contenuto (CEK), che possono sbloccare solo i titolari di uno slot di chiave: un segreto di slot conservato sul dispositivo si combina con un segreto conservato dal server, e nessuna delle due metà da sola la apre.

| L'attaccante possiede | Vede il contenuto della configurazione | Motivo |
|---|---|---|
| Solo una copia del database | No | Nell'archiviazione a oggetti stanno i blob di configurazione, non nel database |
| Il database e l'archiviazione a oggetti | No | Il livello della passphrase dell'organizzazione richiede il segreto del Worker, e il livello CEK un segreto di slot |
| Una compromissione completa del server | Non senza un segreto di slot | Cadono i livelli del server, ma la CEK resta protetta dall'output PRF del passkey o dal kit di recupero a 160 bit, e nessuno dei due è indovinabile |
| Il dispositivo di un membro rimosso | Ciò che ha già scaricato | Le versioni successive restano chiuse dopo una rotazione della CEK |
| Un URL di agente trapelato | Una configurazione, come quell'utente | Vedi [Agenti e MCP remoto](#agenti-e-mcp-remoto) |

Il server può ancora vedere i metadati (id di configurazione, team, versioni, timestamp, dimensioni dei blob) e può rifiutare, ritardare o eliminare richieste. Un operatore che serve codice del portale malevolo può leggere le chiavi nel browser. Ogni blob è legato al proprio archivio, alla configurazione, al team e alla versione, quindi il server non può sostituirne o modificarne uno senza che lo si noti, e la CLI rifiuta una versione più vecchia di una già vista.

## Ambito delle chiavi

![Ambito delle chiavi](/img/security-key-scope.svg)

*Un archivio e una CEK per organizzazione; i team sono controllo degli accessi, non chiavi separate.*

- Un archivio di configurazione per organizzazione e una CEK per archivio. Quanto ai team, sono controllo degli accessi lato server, non isolamento crittografico: un kit di recupero o uno slot di chiave apre la CEK dell'intera organizzazione.
- Gli slot di chiave sono unici per archivio, utente e metodo, quindi c'è un kit di recupero per utente e per organizzazione. Un utente in due organizzazioni ha due kit, e non esiste un kit di team.
- Un segreto macchina è uno per macchina e per organizzazione e serve a registrare una macchina headless.
- Ogni configurazione ha una propria chiave di contenuto sotto la CEK. Una concessione agente porta la chiave di contenuto di una sola configurazione, quindi con essa non si apre nessun'altra configurazione dell'organizzazione.
- La policy di autorizzazione di ogni configurazione è un record separato, sotto una chiave derivata dalla CEK e dal puntatore del record. Chi possiede la chiave di una policy apre solo i record di quel puntatore.

## Agenti e MCP remoto

![Flusso MCP remoto](/img/security-remote-mcp-flow.svg)

*Una chiamata del client passa dal Worker MCP all'esecutore dell'organizzazione; una concessione scaduta rimanda il client a riautorizzarsi.*

Una concessione agente è il tipo di titolare di chiavi che sta dietro un URL MCP remoto. Porta la chiave di contenuto di una configurazione e le chiavi di policy della configurazione di team della concessione e della configurazione a livello di organizzazione, mai la CEK, quindi un agente legge esattamente ciò che legge la sua persona.

- **Durata.** Un URL dura 7 giorni per impostazione predefinita e 30 al massimo, poi scade o viene revocato. Una concessione scaduta viene rifiutata e il client riautorizza.
- **Ambito.** Una concessione raggiunge una configurazione e appartiene a una regione (eu, us o asia). Un URL presentato a un'altra regione viene rifiutato indicando la regione corretta, mai inoltrato. Le installazioni on-premise sono a regione singola.
- **Policy.** Un agente agisce solo dove l'adesione esplicita di una persona e il tetto della policy lo consentono entrambi. Il tetto è la policy dell'organizzazione ristretta da quella del team. Un agente non può modificare la policy, leggere valori segreti o ampliare la propria concessione.
- **Raggio d'azione.** Un URL trapelato agisce come quell'utente sulla sua unica configurazione finché non scade o viene revocato. Non apre nulla al di fuori dell'executor ospitato della sua regione.

L'output degli strumenti raggiunge il provider di modelli che l'utente collega, e che Rediacc non sceglie.

### On-premise

Non c'è Cloudflare nel percorso. Nel cloud, i segreti Worker diventano variabili d'ambiente o configurazione sull'host del cliente, quindi l'accesso all'host sostituisce il confine del segreto Worker nella tabella sopra, e le chiamate agli strumenti vengono eseguite sull'executor daemon del cliente.

## Policy

![Tetto della policy](/img/security-policy-ceiling.svg)

*Un agente agisce solo dove l'adesione umana e l'intersezione tra policy dell'organizzazione e del team lo consentono.*

La policy è un record separato, sigillato per voce di configurazione con dati autenticati che legano archivio, configurazione, team, versione e generazione della chiave. Il server non può leggerlo, e un record riproposto o scambiato fallisce il proprio tag di integrità. Vengono rifiutati i record di policy di versione 1.

Solo un proprietario o amministratore dell'organizzazione scrive la policy dell'organizzazione, e solo un amministratore di team (o un proprietario o amministratore) scrive la policy di quel team. Una scrittura richiede la 2FA e una sessione elevata, e un passkey associato quando l'archivio richiede i passkey. Ogni membro e ogni executor che lo serve la legge. Una chiave che l'organizzazione blocca viene ignorata nella policy di un team.

## Cosa è recuperabile

![Percorsi di sblocco e recupero](/img/security-unlock-recovery.svg)

*Ogni metodo di sblocco termina nella CEK, e il kit di recupero è obbligatorio.*

| Situazione | Recupero |
|---|---|
| Passkey perso | Sblocca con il kit di recupero, poi registra un nuovo passkey |
| Kit perso | Rigeneralo da un passkey funzionante; la vecchia stampa smette di funzionare |
| Entrambi persi | Un proprietario o amministratore riaggiunge il membro tramite il passaggio di consegne del membro |
| L'ultimo titolare di chiave perde entrambi | Irrecuperabile, ed è per questo che si consiglia un secondo titolare di chiave |
| Membro rimosso | Slot e token del membro spariscono subito; una rotazione della CEK chiude le versioni successive a una chiave che ha conservato |
| Rotazione della CEK | Reincapsula la CEK sotto una nuova generazione e invalida ogni kit di recupero |

Il server rifiuta l'eliminazione di uno slot, la rimozione di un membro o l'uscita di un membro che lascerebbe meno di due titolari di chiave e nessuno slot di recupero. Ogni membro riceve un kit di recupero obbligatorio al momento della registrazione, e conservarlo è responsabilità del membro.
