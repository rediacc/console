---
title: Panoramica sull'integrazione degli agenti AI
description: Come gli assistenti di programmazione AI come Claude Code, Cursor e Cline si integrano con l'infrastruttura Rediacc per il deployment e la gestione autonoma. È possibile iniziare subito.
category: Guides
order: 30
language: it
---

Gli assistenti di programmazione AI possono gestire l'infrastruttura Rediacc in modo autonomo tramite la CLI `rdc`. Questa guida illustra gli approcci di integrazione e come iniziare.

## Perché self-hosted e agenti AI

L'architettura di Rediacc è naturalmente compatibile con gli agenti:

- **CLI-first**: ogni operazione è un comando `rdc`, nessuna GUI richiesta
- **Basata su SSH**: il protocollo che gli agenti conoscono meglio dai dati di addestramento
- **Output JSON**: tutti i comandi supportano `--output json` con un envelope coerente
- **Isolamento Docker**: ogni repository ha il proprio daemon e namespace di rete
- **Scriptabile**: `--yes` salta le conferme, `--dry-run` mostra in anteprima le operazioni distruttive

## Approcci di integrazione

### 1. Template AGENTS.md / CLAUDE.md

Il modo più rapido per iniziare. Copia il nostro [template AGENTS.md](/en/docs/agents-md-template) nella root del progetto:

- `CLAUDE.md` per Claude Code
- `.cursorrules` per Cursor
- `.windsurfrules` per Windsurf

Questo fornisce all'agente il contesto completo sui comandi disponibili, l'architettura e le convenzioni.

### 2. Pipeline di output JSON

Quando gli agenti invocano `rdc` in una subshell, l'output passa automaticamente a JSON (rilevamento non-TTY). Ogni risposta JSON usa un envelope coerente:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Le risposte di errore includono i campi `retryable` e `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Rilevamento delle capacità dell'agente

Il sottocomando `rdc agent` fornisce introspezione strutturata:

```bash
# Elenca tutti i comandi con argomenti e opzioni
rdc agent capabilities

# Mostra lo schema dettagliato per un comando specifico
rdc agent schema --command "machine query"

# Esegui un comando con stdin JSON
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Flag chiave per gli agenti

| Flag | Scopo |
|------|---------|
| `--output json` / `-o json` | Output JSON leggibile dalla macchina |
| `--yes` / `-y` | Salta le conferme interattive |
| `--quiet` / `-q` | Sopprime l'output informativo su stderr |
| `--fields name,status` | Limita l'output a campi specifici |
| `--dry-run` | Mostra in anteprima le operazioni distruttive senza eseguirle |

## Sicurezza e guardrail

La CLI tratta gli agenti AI diversamente dagli esseri umani alla tastiera. Le operazioni sensibili richiedono la prova di una conoscenza previa (il flag `--current`), i flussi con editor interattivo vengono rifiutati per impostazione predefinita e ogni rifiuto viene registrato nel log di audit. Il riferimento [Sicurezza e guardrail degli agenti AI](/en/docs/ai-agents-safety) descrive la tabella completa del firewall, il modello knowledge-gate, il scope-override `REDIACC_ALLOW_CONFIG_EDIT` e il log di audit con hash a catena.

## Passi successivi

- [Sicurezza e guardrail degli agenti AI](/en/docs/ai-agents-safety), cosa possono e non possono fare gli agenti, knowledge-gate, log di audit
- [Guida alla configurazione di Claude Code](/en/docs/ai-agents-claude-code), configurazione passo-passo di Claude Code
- [Guida alla configurazione di Cursor](/en/docs/ai-agents-cursor), integrazione con Cursor IDE
- [Riferimento output JSON](/en/docs/ai-agents-json-output), documentazione completa dell'output JSON
- [Template AGENTS.md](/en/docs/agents-md-template), template di configurazione dell'agente pronto all'uso
