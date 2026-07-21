---
title: Guida alla configurazione di Claude Code
description: "Guida passo passo per configurare Claude Code per la gestione autonoma dell'infrastruttura Rediacc. È già compatibile con la CLI rdc: la configurazione è più rapida del previsto."
category: Guides
order: 31
language: it
sourceHash: "c0034de091da3349"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Claude Code funziona nativamente con Rediacc tramite la CLI `rdc`. Questa guida illustra la configurazione, i permessi e i flussi di lavoro comuni.

> **Prima di tutto la sicurezza**: Prima di connettere un agente a qualcosa che tocca i segreti, leggi [Sicurezza e guardrail per agenti AI](/en/docs/ai-agents-safety). Claude Code in esecuzione sotto `rdc` viene rilevato come agente. Le mutazioni sensibili richiedono `--current <previous-value>` (precondizione in stile passwd) oppure `--rotate-secret` (rotazione confermata, verificata). Simmetrico per umani e agenti. L'editor interattivo, `--reveal` e l'SSH diretto alla macchina vengono rifiutati per impostazione predefinita, a meno che non li si apra esplicitamente tramite `REDIACC_ALLOW_CONFIG_EDIT`. Quando una precondizione fallisce, il campo `errors[].next.options[].run` dell'envelope JSON indica all'agente l'esatto comando CLI da suggerire all'utente. Riproducilo testualmente.

## Configurazione rapida

1. Installa la CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copia il [template AGENTS.md](/en/docs/agents-md-template) nella root del tuo progetto come `CLAUDE.md`
3. Avvia Claude Code nella directory del progetto

Claude Code legge `CLAUDE.md` all'avvio e lo utilizza come contesto persistente per tutte le interazioni.

## Configurazione CLAUDE.md

Posiziona questo file nella root del tuo progetto. Consulta il [template AGENTS.md](/en/docs/agents-md-template) completo per una versione esaustiva. Sezioni principali:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine|repo-ref>

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Permessi degli strumenti

Claude Code richiederà il permesso di eseguire comandi `rdc`. Puoi pre-autorizzare le operazioni comuni aggiungendo alle impostazioni di Claude Code:

- Consenti `rdc machine status *`, controlli di stato in sola lettura
- Consenti `rdc machine status * --containers`, elenco dei container
- Consenti `rdc machine health *`, controlli di salute
- Consenti `rdc repo list`, elenco dei repository

Per le operazioni distruttive (`rdc repo up`, `rdc repo delete`), Claude Code chiederà sempre conferma, a meno che non le si autorizzi esplicitamente.

## Esempi di flussi di lavoro

### Controlla lo stato dell'infrastruttura

```
Tu: "Qual è lo stato di prod-1?"

Claude Code esegue: rdc machine status prod-1 -o json
→ Mostra lo stato della macchina, i repository, i container e i servizi
```

### Distribuisci un repository

```
Tu: "Distribuisci il repo mail su prod-1"

Claude Code esegue: rdc repo up mail@prod-1 --dry-run -o json
→ Mostra cosa succederebbe
Claude Code esegue: rdc repo up mail@prod-1 --yes
→ Distribuisce il repository
```

### Diagnostica problemi ai container

```
Tu: "Perché il container nextcloud non è in salute?"

Claude Code esegue: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Elenca gli stati dei container
Claude Code esegue: rdc repo logs nextcloud@prod-1 -c nextcloud-app --lines 50 "docker logs nextcloud-app --tail 50"
→ Controlla i log recenti
```

### Sincronizzazione file

```
Tu: "Carica la configurazione locale nel repo mail"

Claude Code esegue: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Mostra i file che verrebbero sincronizzati
Claude Code esegue: rdc repo sync upload mail@prod-1 --local ./config
→ Sincronizza i file
```

## Suggerimenti

- Claude Code rileva automaticamente i contesti non-TTY e passa all'output JSON; nella maggior parte dei casi non è necessario specificare `-o json`
- Usa `rdc --help-all` per consentire a Claude Code di scoprire tutti i comandi disponibili
- Il flag `--fields` aiuta a ridurre l'utilizzo della finestra di contesto quando servono solo dati specifici
