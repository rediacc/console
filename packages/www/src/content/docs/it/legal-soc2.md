---
title: "Conformità SOC 2"
description: "Dove Rediacc ti fornisce evidenze SOC 2: i log, la traccia di change management e i controlli su cui gli auditor fanno domande."
category: "Legal"
order: 2
language: it
sourceHash: "9ba8477a07292a7d"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Conosco SOC 2 perché ho partecipato a riunioni di audit. Gli auditor usano il framework AICPA per verificare che i tuoi controlli funzionino davvero, non solo che tu dica che funzionano. Cinque Trust Service Criteria: sicurezza, disponibilità, integrità del trattamento, riservatezza e privacy.

Riferimento: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Mappatura dei Trust Service Criteria

| Principio di Fiducia | Criteri | Capacità di Rediacc |
|----------------|----------|-------------------|
| **Sicurezza** (CC6) | Controlli di accesso logico, crittografia | Crittografia LUKS2 AES-256 a riposo. Le credenziali sono conservate solo nella configurazione locale dell'operatore (`~/.config/rediacc/`), mai sul server. Accesso basato su chiave SSH. Daemon Docker isolati per repository. |
| **Disponibilità** (A1) | Ripristino del sistema e resilienza | `rdc repo push/pull` con copie offsite cifrate verso SSH, S3, B2, Azure o GDrive. Snapshot CoW per rollback istantaneo. Aggiornamenti basati su fork per modifiche senza downtime. |
| **Integrità del Trattamento** (PI1) | Trattamento accurato e completo | Gli hook deterministici del ciclo di vita del Rediaccfile (`up`/`down`) garantiscono deployment coerenti. `rdc repo validate` verifica l'integrità del repository e lo stato dei backup dopo spegnimenti imprevisti o operazioni di backup. |
| **Riservatezza** (C1) | Protezione dei dati da accessi non autorizzati | Crittografia per repository con credenziali LUKS univoche. Isolamento di rete tramite iptables, daemon Docker separati e sottoreti IP di loopback. I container di repository diversi non si vedono tra loro. Il config store zero-knowledge cifra le configurazioni lato client prima del caricamento. Il server conserva solo blob opachi che non può decifrare. |
| **Privacy** (P1-P8) | Gestione dei dati personali | Self-hosted: nessun egress di dati durante le operazioni. Audit trail per tutti gli accessi ai dati. Gestione delle chiavi di crittografia sotto il controllo del cliente. Il config store utilizza la derivazione a chiave divisa (passkey PRF + segreto del server) in modo che nessuna delle due parti da sola possa accedere ai dati. |

## Audit Trail

Rediacc registra oltre 70 tipi di evento diversi. Azioni dell'utente, modifiche di sistema, aggiornamenti di configurazione, modifiche al controllo degli accessi, eventi di sicurezza, operazioni di fork, trail di audit. So che può sembrare moltissimo, ma gli auditor in realtà vogliono vedere queste cose.

- **Autenticazione**: login, logout, cambio password, abilitazione/disabilitazione 2FA, revoca sessione
- **Autorizzazione**: creazione/revoca token API, cambio ruolo, appartenenza al team
- **Configurazione**: push/pull del config store, gestione dei membri, accessi falliti (IP non corrispondente, SDK negato)
- **Licenze**: emissione licenza repository, tracciamento slot macchina, modifiche all'abbonamento
- **Operazioni macchina**: creazione/avvio/arresto/eliminazione repository, fork, backup push/pull, sincronizzazione file, sessioni terminale

Ci sono due modi per ottenere questi log. Dashboard amministrativa con filtri per utente, team e data. Pagina attività del portale per gli amministratori dell'organizzazione, con filtri per tipo e data e un'esportazione JSON che puoi collegare ai tuoi strumenti. Le operazioni macchina vengono registrate anche nei log di sistema, quindi hai una difesa in profondità.

## Gestione dei Cambiamenti

I fork rendono la gestione dei cambiamenti verificabile. Fai un fork della produzione, ottieni una copia dello stato live. Testalo. Revisionalo. Promuovilo o scartalo. Ogni passaggio timestampato e collegato a una persona. Questo è quello che gli auditor vogliono vedere: niente modifiche anonime.

1. Fork di un repository di produzione (`rdc repo fork`)
2. Applicazione e test delle modifiche sul fork
3. Validazione indipendente del fork
4. Promozione del fork in produzione (`rdc repo takeover`)

Ogni passaggio: registrato. Timestampato. Associato a una persona. Niente "non so chi ha cambiato questo" momenti.

## Controllo degli Accessi

- **Accesso alla macchina**: solo autenticazione con chiave SSH. Nessun SSH basato su password.
- **Token API**: permessi limitati, binding IP opzionale, revoca automatica alla rimozione dal team.
- **Isolamento del repository**: ogni repository ha il proprio socket del daemon Docker. L'accesso a un repository non garantisce l'accesso a un altro sulla stessa macchina.
- **Token del config store**: token rotativi a uso singolo con binding IP al primo utilizzo, scadenza automatica in 24 ore e finestra di grazia da 3 richieste per la concorrenza. L'accesso dei membri è gestito tramite scambio di chiavi X25519 con revoca immediata.
