---
title: "Conformità SOC 2"
description: "Come Rediacc si allinea ai criteri dei Trust Service Criteria SOC 2 per sicurezza, disponibilità e riservatezza."
category: "Legal"
order: 2
language: it
---

SOC 2 (System and Organization Controls 2) è un framework sviluppato dall'American Institute of Certified Public Accountants (AICPA) per valutare i controlli di un'organizzazione relativi a sicurezza, disponibilità, integrità del trattamento, riservatezza e privacy.

Riferimento: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Mappatura dei Trust Service Criteria

| Principio di Fiducia | Criteri | Capacità di Rediacc |
|----------------|----------|-------------------|
| **Sicurezza** (CC6) | Controlli di accesso logico, crittografia | Crittografia LUKS2 AES-256 a riposo. Le credenziali sono conservate solo nella configurazione locale dell'operatore (`~/.config/rediacc/`), mai sul server. Accesso basato su chiave SSH. Daemon Docker isolati per repository. |
| **Disponibilità** (A1) | Ripristino del sistema e resilienza | `rdc repo backup push/pull` con copie offsite cifrate verso SSH, S3, B2, Azure o GDrive. Snapshot CoW per rollback istantaneo. Aggiornamenti basati su fork per modifiche senza downtime. |
| **Integrità del Trattamento** (PI1) | Trattamento accurato e completo | Gli hook deterministici del ciclo di vita del Rediaccfile (`up`/`down`) garantiscono deployment coerenti. `rdc repo validate` verifica l'integrità del repository e lo stato dei backup dopo spegnimenti imprevisti o operazioni di backup. |
| **Riservatezza** (C1) | Protezione dei dati da accessi non autorizzati | Crittografia per repository con credenziali LUKS univoche. Isolamento di rete tramite iptables, daemon Docker separati e sottoreti IP di loopback. I container di repository diversi non si vedono tra loro. Il config store zero-knowledge cifra le configurazioni lato client prima del caricamento. Il server conserva solo blob opachi che non può decifrare. |
| **Privacy** (P1-P8) | Gestione dei dati personali | Self-hosted: nessun egress di dati durante le operazioni. Audit trail per tutti gli accessi ai dati. Gestione delle chiavi di crittografia sotto il controllo del cliente. Il config store utilizza la derivazione a chiave divisa (passkey PRF + segreto del server) in modo che nessuna delle due parti da sola possa accedere ai dati. |

## Audit Trail

Rediacc registra oltre 70 tipi di evento che coprono:

- **Autenticazione**: login, logout, cambio password, abilitazione/disabilitazione 2FA, revoca sessione
- **Autorizzazione**: creazione/revoca token API, cambio ruolo, appartenenza al team
- **Configurazione**: push/pull del config store, gestione dei membri, accessi falliti (IP non corrispondente, SDK negato)
- **Licenze**: emissione licenza repository, tracciamento slot macchina, modifiche all'abbonamento
- **Operazioni macchina**: creazione/avvio/arresto/eliminazione repository, fork, backup push/pull, sincronizzazione file, sessioni terminale

Questi log sono accessibili tramite la dashboard amministrativa (con filtri per utente, team e data), la pagina delle attività del portale (con filtro per tipo e data limitato all'organizzazione per gli amministratori) e la CLI `rdc audit` per l'esportazione programmatica. Le operazioni macchina sono registrate anche nei log di sistema per una difesa in profondità.

## Gestione dei Cambiamenti

Il flusso basato su fork supporta una gestione controllata dei cambiamenti:

1. Fork di un repository di produzione (`rdc repo fork`)
2. Applicazione e test delle modifiche sul fork
3. Validazione indipendente del fork
4. Promozione del fork in produzione (`rdc repo takeover`)

Ogni passaggio è registrato con timestamp e identificazione dell'attore.

## Controllo degli Accessi

- **Accesso alla macchina**: solo autenticazione con chiave SSH. Nessun SSH basato su password.
- **Token API**: permessi limitati, binding IP opzionale, revoca automatica alla rimozione dal team.
- **Isolamento del repository**: ogni repository ha il proprio socket del daemon Docker. L'accesso a un repository non garantisce l'accesso a un altro sulla stessa macchina.
- **Token del config store**: token rotativi a uso singolo con binding IP al primo utilizzo, scadenza automatica in 24 ore e finestra di grazia da 3 richieste per la concorrenza. L'accesso dei membri è gestito tramite scambio di chiavi X25519 con revoca immediata.
