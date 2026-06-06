---
title: Gestione dell'account
description: Organizzazioni, team, membri e abbonamenti in Rediacc. È possibile gestire l'intera struttura dell'organizzazione con pochi clic.
category: Guides
order: 12
language: it
sourceHash: "974885635641ed70"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

### Organizzazioni

Registra un account e Rediacc crea automaticamente un'organizzazione per te. Quella org è il contenitore di livello superiore per tutto cio' che possiedi: macchine, repository, abbonamenti e le persone che inviti. Non ne creerai una seconda per errore. C'è esattamente una org per account, e ogni team e risorsa dipende da essa.

![Registration Flow](/img/account-registration-flow.svg)

Ogni organizzazione ha:
- Un nome univoco (predefinito all'indirizzo email)
- Un piano di abbonamento (inizia con COMMUNITY)
- Un team predefinito (tutti i membri vi aderiscono automaticamente)

### Membri e ruoli

Le organizzazioni supportano tre ruoli:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Ruolo | Capacità |
|-------|----------|
| **Owner** | Controllo completo: fatturazione, trasferimento della proprietà, gestione di tutti i membri e team |
| **Admin** | Invitare e rimuovere membri, creare e gestire team, revocare token API |
| **Member** | Visualizzare i dati dell'organizzazione, creare token API, accedere ai team assegnati |

Invitare membri:
```bash
# Dal portale: Organization > Members > Invite
# Oppure tramite API
```

Quando un membro viene rimosso, i suoi token API e i token di archiviazione della configurazione vengono revocati automaticamente.

### Team

I team consentono di circoscrivere le risorse all'interno di un'organizzazione. Ogni org inizia con un team predefinito.

![Team Structure](/img/account-team-structure.svg)

Ruoli nel team:
- **Team Admin**: Può aggiungere/rimuovere membri del team all'interno del team
- **Member**: Può accedere alle risorse con scope del team

I proprietari e gli amministratori dell'organizzazione hanno automaticamente accesso a tutti i team senza appartenenza esplicita.

### Abbonamenti e piani

Rediacc offre quattro piani:

| Piano | Macchine | Licenze repo/mese | Validità cert delegazione predefinita / max | Funzionalità |
|-------|----------|-------------------|---------------------------------------------|--------------|
| COMMUNITY | 2 | 500 | 15g / 30g | Base |
| PROFESSIONAL | 5 | 5.000 | 60g / 120g | Gruppi di permessi, registro audit, branding personalizzato, supporto prioritario |
| BUSINESS | 20 | 20.000 | 90g / 180g | Ceph, analisi avanzate, priorità coda, coda avanzata |
| ENTERPRISE | 50 | 100.000 | 120g / 365g | Account manager dedicato |

![Subscription Flow](/img/account-subscription-flow.svg)

Tutti i piani iniziano con un periodo di grazia di 3 giorni. Gli slot macchina vengono tracciati per team e rilasciati automaticamente dopo 1 ora di inattività. Consulta [Abbonamento e licenze](/en/docs/subscription-licensing) per i dettagli.

### Fatturazione

Solo il **proprietario** dell'organizzazione può gestire la fatturazione:
- Creare una sessione di checkout Stripe per gli aggiornamenti del piano
- Accedere al portale di fatturazione Stripe per modificare il metodo di pagamento
- Richiedere rimborsi self-service (entro 14 giorni, con un cooldown di 30 giorni)

### Regione dei dati

Il tuo account è archiviato nella regione dati selezionata durante la registrazione (EU, US o Asia Pacifico). Questa scelta è permanente. Il badge di regione nel portale mostra in quale regione risiedono i tuoi dati. Consulta [Regioni dei dati](/en/docs/data-regions) per i dettagli.

### Canale Edge

Se il tuo account è sul canale Edge, vedrai un badge "Edge" nella barra laterale del portale. Gli account Edge hanno limiti 2X rispetto a Community ma non hanno accesso ai piani a pagamento. Consulta [Canali di rilascio](/en/docs/release-channels) per le differenze tra Edge e Stable.

### Certificati di delegazione

Per le distribuzioni on-premise e air-gapped, puoi gestire i tuoi certificati di delegazione dal portale clienti su **/account/delegation-certs**. La pagina è visibile a tutti i clienti indipendentemente dal piano; solo le scadenze predefinite per livello differiscono.

#### Controllo d'accesso per ruolo

| Azione | Org Owner | Org Admin | Member |
|--------|-----------|-----------|--------|
| Elenco / visualizzazione / download certificati | ✓ | ✓ | ✓ |
| Creazione nuovo certificato | ✓ | ✓ | ✗ |
| Revoca certificato | ✓ | ✓ | ✗ |
| Generazione token auto-rinnovo | ✓ | ✓ | ✗ |
| Elaborazione richiesta di rinnovo air-gapped | ✓ | ✓ | ✗ |

I membri possono visualizzare l'elenco e scaricare i certificati esistenti (utile per distribuire il certificato a un insieme di macchine), ma solo i proprietari e gli amministratori possono generarli o revocarli.

#### Applicazione del singolo certificato attivo

Un abbonamento può avere **un solo certificato di delegazione attivo alla volta**. Ogni installazione on-premise applica le quote mensili e per macchina nel proprio registro locale; più certificati attivi moltiplicherebbero la quota effettiva senza possibilità di riconciliazione.

Se si tenta di creare un secondo certificato mentre uno è già attivo, il portale mostra una finestra di dialogo con due opzioni:

- **Rinnova (consigliato)** - estende la catena esistente. Tutte le licenze repo precedentemente emesse continuano a funzionare con il certificato rinnovato. Da utilizzare quando si ruota un certificato in scadenza sulla stessa installazione on-premise.
- **Revoca e crea nuovo** - scarta la catena esistente e riparte da zero. Le licenze repo precedentemente emesse diventano non verificabili una volta superata la data validUntil del VECCHIO certificato. Da utilizzare solo quando si è migrati a una nuova installazione on-prem con una chiave di firma diversa, o quando si recupera da una chiave compromessa.

Se hai bisogno di ambienti separati (produzione + staging + DR + multi-regione), acquista un abbonamento per ogni installazione.

#### Bootstrap del rinnovo automatico

Per abilitare il rinnovo automatico on-premise, fai clic su **Ottieni token di auto-rinnovo** nella pagina Certificati di delegazione. Questo genera un token API con scope `delegation:renew` (perpetuo, senza scadenza) e mostra i valori da incollare nel file `.env` on-premise:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

Il token concede **solo** il rinnovo del certificato di delegazione. Non può' leggere o modificare nessun'altra risorsa. Questo è l'unico modo per generare un token `delegation:renew`; il flusso standard `/portal/api-tokens` non include questo scope.

#### Rinnovo air-gapped

Se la tua installazione on-premise non ha accesso HTTPS in uscita, usa il flusso del manifesto offline:

1. Nella pagina di amministrazione on-premise, fai clic su **Scarica richiesta di rinnovo**. L'installazione on-premise genera un manifesto firmato contenente la testa della catena locale.
2. Trasferisci il manifesto all'upstream (USB, email cifrata, qualsiasi canale).
3. Nel portale upstream, fai clic su **Carica richiesta di rinnovo** e seleziona il manifesto. L'upstream verifica la firma del manifesto, emette un nuovo certificato e lo restituisce come file `.json` scaricabile.
4. Trasferisci il nuovo certificato all'installazione on-premise e caricalo tramite la pagina di amministrazione on-premise.

L'upstream rifiuta i manifesti più vecchi di 7 giorni. Consulta [Installazione on-premise](/en/docs/on-premise) per la configurazione passo passo e [Catena di licenze e delegazione](/en/docs/license-chain) per il design crittografico.

#### Limite di frequenza

La creazione di certificati è limitata a **10 tentativi ogni 24 ore continue** per abbonamento, inclusi i tentativi falliti (spam di collisioni, input non valido). Se si raggiunge il limite, il portale mostra un valore `Retry-After` che indica quando riprovare.
