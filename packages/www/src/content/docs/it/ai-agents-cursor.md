---
title: Guida alla configurazione di Cursor
description: Configura Cursor IDE per lavorare con l'infrastruttura Rediacc usando .cursorrules e l'integrazione con il terminale.
category: Guides
order: 32
language: it
sourceHash: "b5e835461de00400"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

In breve: `.cursorrules` carica il contesto Rediacc nell'AI di Cursor; il terminale gli permette di eseguire comandi `rdc` sulle tue macchine reali.

## Configurazione rapida

1. Installa la CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copia il [template AGENTS.md](/en/docs/agents-md-template) nella root del tuo progetto come `.cursorrules`
3. Apri il progetto in Cursor

Cursor legge `.cursorrules` all'avvio. Tieni presente che si applicano i limiti della context window: mantieni il file focalizzato sulle tue macchine e repository effettivi, invece di riempirlo con testo generico.

## Configurazione .cursorrules

Crea `.cursorrules` nella root del tuo progetto con il contesto dell'infrastruttura Rediacc. Consulta il [template AGENTS.md](/en/docs/agents-md-template) completo per una versione esaustiva.

Le sezioni principali da includere:

- Nome dello strumento CLI (`rdc`) e installazione
- Comandi comuni con il flag `--output json`
- Panoramica dell'architettura (isolamento dei repository, daemon Docker)
- Regole di terminologia (adapter, non modalità)

## Integrazione con il terminale

Cursor può eseguire comandi `rdc` tramite il suo terminale integrato. Pattern comuni:

### Controllo dello stato

Chiedi a Cursor: *"Controlla lo stato del mio server di produzione"*

Cursor esegue nel terminale:
```bash
rdc machine query --name prod-1 -o json
```

### Distribuzione delle modifiche

Chiedi a Cursor: *"Distribuisci la configurazione nextcloud aggiornata"*

Cursor esegue nel terminale:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### Visualizzazione dei log

Chiedi a Cursor: *"Mostrami i log recenti del container mail"*

Cursor esegue nel terminale:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## Impostazioni del workspace

Per i progetti di team, aggiungi le impostazioni Cursor specifiche per Rediacc in `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Suggerimenti

- La modalità Composer di Cursor funziona bene per attività di infrastruttura multi-step
- Usa `@terminal` nella chat di Cursor per fare riferimento all'output recente del terminale
- Il comando `rdc agent capabilities` fornisce a Cursor un riferimento completo dei comandi
- Combina `.cursorrules` con un file `CLAUDE.md` per la massima compatibilità tra gli strumenti AI
